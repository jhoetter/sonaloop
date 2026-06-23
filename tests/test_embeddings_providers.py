"""Provider-agnostic embeddings: provider selection, the Ollama adapter, vector-space
safety (no mixing across providers/models), and the end-to-end keyless run."""
from __future__ import annotations

import io
import json

import pytest

from sonaloop import config
from sonaloop import embeddings as E
from sonaloop import memory as memory_mod
from sonaloop import services

from conftest import create_persona


@pytest.fixture(autouse=True)
def _provider_env(monkeypatch):
    """Tests own the provider env completely (conftest disables embeddings globally)."""
    for var in ("SONALOOP_EMBEDDINGS_PROVIDER", "OPENAI_API_KEY", "OPENAI_EMBEDDING_MODEL",
                "SONALOOP_OLLAMA_EMBED_MODEL", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    yield


def _fake_urlopen(monkeypatch, handler):
    class _Resp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake(req, timeout=0):
        return _Resp(json.dumps(handler(req)).encode())
    monkeypatch.setattr(E.urllib.request, "urlopen", fake)


# --- provider selection ----------------------------------------------------------------

def test_provider_resolution(monkeypatch):
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "0")
    assert E.active_provider() == "none"                       # keyless default: off, no probing
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert E.active_provider() == "openai"
    assert E.provider_model() == "text-embedding-3-small"      # compatible, un-namespaced
    monkeypatch.setenv("SONALOOP_EMBEDDINGS_PROVIDER", "ollama")
    assert E.active_provider() == "ollama"                     # explicit env wins over the key
    assert E.provider_model() == "ollama:nomic-embed-text"     # namespaced: a distinct vector space
    monkeypatch.setenv("SONALOOP_EMBEDDINGS_PROVIDER", "carrier-pigeon")
    with pytest.raises(ValueError):
        E.active_provider()
    monkeypatch.setenv("SONALOOP_EMBEDDINGS_PROVIDER", "openai")
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "1")
    assert E.active_provider() == "none"                       # the kill switch beats everything


def test_ollama_adapter_roundtrip(monkeypatch):
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "0")
    monkeypatch.setenv("SONALOOP_EMBEDDINGS_PROVIDER", "ollama")
    seen = {}
    def handler(req):
        seen["url"] = req.full_url
        seen["payload"] = json.loads(req.data)
        return {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
    _fake_urlopen(monkeypatch, handler)
    assert E.embed_texts(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]
    assert seen["url"] == "http://localhost:11434/api/embed"
    assert seen["payload"] == {"model": "nomic-embed-text", "input": ["a", "b"]}


def test_openai_adapter_unchanged_and_failsoft(monkeypatch):
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _fake_urlopen(monkeypatch, lambda req: {"data": [{"index": 1, "embedding": [2.0]},
                                                     {"index": 0, "embedding": [1.0]}]})
    assert E.embed_texts(["x", "y"]) == [[1.0], [2.0]]          # index-sorted
    def boom(req, timeout=0):
        raise OSError("network down")
    monkeypatch.setattr(E.urllib.request, "urlopen", boom)
    assert E.embed_texts(["x"]) is None                         # fail-soft, never raises


# --- vector-space safety ---------------------------------------------------------------

def _stub_vectors(monkeypatch, vec):
    monkeypatch.setattr(E, "_embed_ollama", lambda texts: [list(vec) for _ in texts])
    monkeypatch.setattr(E, "_embed_openai", lambda texts: [list(vec) for _ in texts])


def test_recall_never_mixes_vector_spaces(store, monkeypatch):
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "0")
    monkeypatch.setenv("SONALOOP_EMBEDDINGS_PROVIDER", "ollama")
    _stub_vectors(monkeypatch, [1.0, 0.0])
    pid = create_persona(store, "Spacey")
    assert memory_mod.upsert_object_embedding(store, "fact", "fact_1", pid, "loves offline tools")
    row = store.get_embedding("fact", "fact_1")
    assert row["model"] == "ollama:nomic-embed-text"            # persisted with its space
    # switch the model → the old space is ignored AND reported, never scored
    monkeypatch.setenv("SONALOOP_OLLAMA_EMBED_MODEL", "other-model")
    out = memory_mod.recall(store, pid, "offline tools")
    assert out["semantic_enabled"] is True
    assert out["embedding_space_mismatch"]["skipped"] == 1
    # backfill re-embeds into the ACTIVE space (model-aware has_embedding)
    assert store.has_embedding("fact", "fact_1")                 # any space: yes
    assert not store.has_embedding("fact", "fact_1", model="ollama:other-model")


def _real_fact(store, pid, fact_id, text):
    """Recall only scores objects in its pool, so the fact must really exist."""
    store.upsert_entity({"id": "ent_1", "persona_id": pid, "kind": "topic", "name": "meals",
                         "status": "active", "first_seen": "2026-06-01", "last_seen": "2026-06-01",
                         "created_at": "2026-06-01T00:00:00+00:00", "updated_at": "2026-06-01T00:00:00+00:00"})
    store.insert_entity_fact({"id": fact_id, "persona_id": pid, "entity_id": "ent_1", "fact": text,
                              "status": "active", "t_valid": "2026-06-01", "importance": 4,
                              "created_at": "2026-06-01T00:00:00+00:00"})


def test_end_to_end_keyless_with_local_provider(store, monkeypatch):
    """The done-when: the core runs semantically with NO OpenAI key set."""
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "0")
    monkeypatch.setenv("SONALOOP_EMBEDDINGS_PROVIDER", "ollama")
    _stub_vectors(monkeypatch, [0.6, 0.8])
    pid = create_persona(store, "Keyless")
    _real_fact(store, pid, "fact_k", "plans meals on sunday")
    memory_mod.upsert_object_embedding(store, "fact", "fact_k", pid, "plans meals on sunday")
    out = memory_mod.recall(store, pid, "sunday meal planning")
    assert out["semantic_enabled"] is True
    assert any(h["obj_id"] == "fact_k" and h["semantic"] > 0.9 for h in out["hits"])


def test_snapshot_manifest_records_vector_spaces(store, monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "0")
    monkeypatch.setenv("SONALOOP_EMBEDDINGS_PROVIDER", "ollama")
    _stub_vectors(monkeypatch, [1.0])
    pid = create_persona(store, "Snapped")
    memory_mod.upsert_object_embedding(store, "fact", "fact_s", pid, "text")
    out = services.export_snapshot(store=store)
    manifest = json.loads((config.ROOT / out["out_dir"] / "manifest.json").read_text())
    assert manifest["embedding_models"] == ["ollama:nomic-embed-text"]
