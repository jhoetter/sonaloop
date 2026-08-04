from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent


def _is_source_checkout() -> bool:
    """True when running from the repo (editable/dev), false when pip-installed.

    In a wheel the package sits in site-packages with no pyproject.toml beside it;
    in the repo, ROOT/pyproject.toml exists. We use this to keep the dev workflow
    writing to repo/data while an installed package writes to a per-user dir."""
    return (ROOT / "pyproject.toml").exists()


def _resolve_data_dir() -> Path:
    """Where the writable runtime lives (DB, assets, settings).

    Precedence: SONALOOP_DATA_DIR env override -> repo/data (source checkout) ->
    per-user data dir (installed package; platformdirs, XDG fallback)."""
    env = os.getenv("SONALOOP_DATA_DIR")
    if env:
        return Path(env).expanduser()
    if _is_source_checkout():
        return ROOT / "data"
    try:
        from platformdirs import user_data_dir
        return Path(user_data_dir("sonaloop", appauthor=False))
    except Exception:
        base = os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(base).expanduser() / "sonaloop"


DATA_DIR = _resolve_data_dir()
DEFAULT_DB_PATH = DATA_DIR / "sonaloop.db"


# --- request-bound data partitions (multi-tenant extensions) -----------------
# One workspace = one partition: a directory holding its own sonaloop.db plus
# its user artifacts (exports, sessions, prototypes). A multi-tenant extension
# (sonaloop-cloud) binds the active workspace's partition around each request;
# local single-user mode never sets one, so partition_dir() == DATA_DIR and
# every path below resolves exactly as before.

import contextvars  # noqa: E402  (kept beside its single consumer)

_REQUEST_PARTITION: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "sonaloop_request_partition", default=None)


def set_request_partition(root: Path | str | None) -> contextvars.Token:
    """Bind the current context to a data partition rooted at `root` (None = the
    default DATA_DIR). Returns a token; pass it to reset_request_partition() in a
    finally block — partitions must never leak across requests."""
    return _REQUEST_PARTITION.set(Path(root) if root else None)


def reset_request_partition(token: contextvars.Token) -> None:
    _REQUEST_PARTITION.reset(token)


def partition_dir() -> Path:
    """The active writable-file root.

    An explicit legacy/SQLite partition wins.  In shared-Postgres row-tenancy the
    active workspace from the request scope supplies the equivalent file partition;
    a missing scope is quarantined and a malformed scope fails closed instead of
    falling back to the process-global ``DATA_DIR``. Local single-user mode remains
    exactly ``DATA_DIR``.
    """
    explicit = _REQUEST_PARTITION.get()
    if explicit is not None:
        return explicit
    if postgres_row_tenancy_enabled():
        scope = request_tenant_scope()
        if scope is None or not scope[1]:
            # Modules may resolve registry paths during process startup, before any
            # request can bind a tenant.  Quarantine that state instead of crashing
            # startup or (worse) falling back to the shared global runtime tree.
            return DATA_DIR / "workspaces" / ".unbound"
        active_id = str(scope[1])
        # Workspace ids are generated as ws_<opaque>.  Keep the value human-auditable
        # on disk while accepting only one conservative path component; never hash or
        # normalize an unsafe value into a surprising shared location.
        if not re.fullmatch(r"ws_[A-Za-z0-9][A-Za-z0-9_.-]{0,126}", active_id):
            raise ValueError(f"unsafe active workspace id for file partition: {active_id!r}")
        return DATA_DIR / "workspaces" / active_id
    return DATA_DIR


def request_partition() -> Path | None:
    """The RAW request-bound partition (None when unbound — callers that outlive the
    binding request, e.g. an SSE stream, capture this and re-bind per access)."""
    return _REQUEST_PARTITION.get()


# --- request-bound TENANT SCOPE (cloud row-level tenancy; page: cloud-data-model) ----------
# The shared-Postgres successor to the partition file-swap: a request binds the SET of
# workspace_ids the principal may read + the ACTIVE workspace (write destination). The
# Postgres backend turns this into RLS session vars (app.workspace_ids / app.active_workspace);
# open-core (SQLite) ignores it entirely — scope stays None, single-tenant, unchanged.
_REQUEST_TENANT_SCOPE: contextvars.ContextVar[tuple[tuple[str, ...], str] | None] = \
    contextvars.ContextVar("sonaloop_request_tenant_scope", default=None)


def set_request_tenant_scope(accessible_ids, active_id: str) -> contextvars.Token:
    """Bind the request's tenant scope: `accessible_ids` (every workspace the principal may
    READ) + `active_id` (the workspace new rows are WRITTEN to). A finally block must
    reset_request_tenant_scope() — the scope must never leak across requests (the Postgres
    backend explicitly clears and re-binds its session GUCs on pooled connections)."""
    return _REQUEST_TENANT_SCOPE.set((tuple(accessible_ids), active_id))


def reset_request_tenant_scope(token: contextvars.Token) -> None:
    _REQUEST_TENANT_SCOPE.reset(token)


def request_tenant_scope() -> tuple[tuple[str, ...], str] | None:
    """The active (accessible_ids, active_id) scope, or None (open-core / unscoped)."""
    return _REQUEST_TENANT_SCOPE.get()


def postgres_row_tenancy_enabled() -> bool:
    """Whether this process is the shared-Postgres, RLS-enforced cloud runtime.

    Requiring both switches keeps local/SQLite behaviour unchanged even if a stray
    ``SONALOOP_PG_TENANT=1`` is present. Web file delivery uses this boundary to avoid
    exposing the process-global runtime tree in a row-tenanted deployment.
    """
    url = (os.getenv("DATABASE_URL") or "").lower()
    return os.getenv("SONALOOP_PG_TENANT") == "1" and url.startswith(
        ("postgres://", "postgresql://"))


def product_tour_enabled() -> bool:
    """Whether the optional browser product tour is available.

    Local/single-user installs keep the tour as an onboarding aid.  Shared Cloud
    deployments default it off so a customer workspace cannot accidentally load
    the bundled onboarding showcase.  Operators can explicitly override either
    default with ``SONALOOP_PRODUCT_TOUR_ENABLED``.
    """
    raw = os.getenv("SONALOOP_PRODUCT_TOUR_ENABLED")
    if raw is None or not raw.strip():
        return not postgres_row_tenancy_enabled()
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_env(path: Path | None = None) -> None:
    """Load a simple .env file without requiring python-dotenv at import time.

    Cold-start contract (ticket one-sentence-mcp-install): a missing .env is the
    NORMAL first-run state, never an error. In a source checkout the file lives at
    repo/.env; for an installed package (uvx/pipx) ROOT is site-packages, so the
    per-user DATA_DIR/.env is read as well — the one writable, documented place."""
    candidates = [path] if path else [ROOT / ".env", DATA_DIR / ".env"]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def database_path() -> Path:
    part = _REQUEST_PARTITION.get()
    if part is not None:  # an explicit per-request partition outranks everything
        return part / "sonaloop.db"
    url = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///")).expanduser()
    if url.startswith("sqlite://"):
        return Path(url.removeprefix("sqlite://")).expanduser()
    raise ValueError("Only sqlite DATABASE_URL values are supported in this build.")


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    # Microsecond precision: rapid back-to-back creates (e.g. seeding a whole project in one process)
    # get DISTINCT, monotonically increasing timestamps, so created_at ordering is correct without
    # relying on tie-breaks. fromisoformat / [:10] / [:19] slices still parse it.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# --- Memory & simulation settings (spec/memory-and-simulation-architecture.md) ---

MEMORY_SCHEMA_VERSION = 4


# --- Methodology engine & prototyping (spec/methodology-engine-and-prototyping.md) ---

def methodologies_dir() -> Path:
    """Built-in methodology specs ship inside the package (read-only package data)."""
    return PACKAGE_DIR / "methodologies"


def prototype_templates_dir() -> Path:
    return PACKAGE_DIR / "prototype_templates"


def suggestions_dir() -> Path:
    """Editable, MCP-served SUGGESTIONS (capabilities/roles/artifact-types/templates). Pure
    data — never enforced. See spec/methodology-constellations.md §2.3. Ships as package data."""
    return PACKAGE_DIR / "suggestions"


def taxonomy_path() -> Path:
    """The canonical Job/Framework/Format taxonomy (docs/job-framework-format.md is its
    human-readable companion). Read-only package data; loaded via sonaloop.job_taxonomy."""
    return PACKAGE_DIR / "taxonomy.json"


def prototypes_dir() -> Path:
    """Where generated/registered prototype apps live (writable runtime).

    Dev (source checkout): alongside the repo at ./prototypes (committed, runnable
    locally). Installed: under the per-user data dir so a read-only install still works."""
    if (_is_source_checkout() and _REQUEST_PARTITION.get() is None
            and not postgres_row_tenancy_enabled()):
        return ROOT / "prototypes"
    return partition_dir() / "prototypes"


def sessions_dir() -> Path:
    """Where usability-session artifacts live (writable runtime, like data/personas and the
    avatar output dir): per-step screenshots under data/sessions/<session_id>/step-<index>.png
    (spec: the usability-session artifact — the session is the deliverable)."""
    return partition_dir() / "sessions"


def max_browser_sessions() -> int:
    try:
        return max(1, min(16, int(os.getenv("PERSONA_COUNCIL_MAX_BROWSER_SESSIONS", 4))))
    except (TypeError, ValueError):
        return 4

# NOTE: there is intentionally NO LLM-text-generation config. The host (Claude)/subagents
# author all text via MCP; the OpenAI key is embeddings + image generation only.
# (spec/deep-design-thinking-and-diamond.md §2 — locked principle.)


def embedding_model() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def embeddings_enabled() -> bool:
    """Semantic retrieval is on when an embedding PROVIDER is active and not disabled
    (provider-agnostic: openai | ollama | none — see sonaloop/embeddings.py)."""
    if os.getenv("PERSONA_COUNCIL_DISABLE_EMBEDDINGS", "").lower() in {"1", "true", "yes"}:
        return False
    from . import embeddings as _emb
    return _emb.active_provider() != "none"


def retrieval_weights() -> dict[str, float]:
    """Hybrid recall weights: semantic, keyword/entity, recency, importance."""
    def _w(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, default))
        except (TypeError, ValueError):
            return default

    return {
        "semantic": _w("PERSONA_COUNCIL_W_SEMANTIC", 0.45),
        "keyword": _w("PERSONA_COUNCIL_W_KEYWORD", 0.25),
        "recency": _w("PERSONA_COUNCIL_W_RECENCY", 0.15),
        "importance": _w("PERSONA_COUNCIL_W_IMPORTANCE", 0.15),
    }


def recency_halflife_days() -> float:
    try:
        return float(os.getenv("PERSONA_COUNCIL_RECENCY_HALFLIFE_DAYS", 30.0))
    except (TypeError, ValueError):
        return 30.0


def default_sample_days_per_month() -> int:
    try:
        return int(os.getenv("PERSONA_COUNCIL_SAMPLE_DAYS_PER_MONTH", 4))
    except (TypeError, ValueError):
        return 4


def critic_threshold() -> int:
    """Minimum per-dimension score (1-5) the LLM critic must reach for semantic
    'top'. Tunable via PERSONA_COUNCIL_CRITIC_THRESHOLD; clamped to 1-5, default 4."""
    try:
        return max(1, min(5, int(os.getenv("PERSONA_COUNCIL_CRITIC_THRESHOLD", 4))))
    except (TypeError, ValueError):
        return 4


def critic_sample_k() -> int:
    """How many activities the critic samples per run. Tunable via
    PERSONA_COUNCIL_CRITIC_SAMPLE_K; larger = more thorough on long horizons.
    Clamped to 1-100, default 12."""
    try:
        return max(1, min(100, int(os.getenv("PERSONA_COUNCIL_CRITIC_SAMPLE_K", 12))))
    except (TypeError, ValueError):
        return 12


# --- i18n: UI + generated-content language (German/English) -------------------
# Two independent axes:
#   - content_language: the language host-authored text (personas, days, councils,
#     syntheses) is written in. Auto-detected from what the user writes the first
#     time, then persisted so later runs and the web UI stay consistent.
#   - ui_language: the language of the web inspector chrome. Defaults to the
#     content language but can be toggled independently in the web UI.
# Persisted in data/settings.json (a tiny local KV; the DB stays the runtime).

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "en"

def _settings_path() -> Path:
    # Language preferences are authored content settings, so in Cloud they belong
    # to the active workspace just like persona files.  Local mode still resolves
    # to the historical DATA_DIR/settings.json.
    return partition_dir() / "settings.json"

# Common German function words / markers used for a cheap, dependency-free guess.
_GERMAN_MARKERS = {
    "der", "die", "das", "und", "ich", "nicht", "ist", "mit", "für", "auf", "ein",
    "eine", "einen", "wir", "sie", "ihr", "auch", "noch", "wenn", "aber", "oder",
    "soll", "sollen", "möchte", "wollen", "machen", "bitte", "wie", "was", "warum",
    "über", "bei", "von", "zum", "zur", "dass", "sind", "haben", "kann", "können",
}


def _read_settings() -> dict[str, str]:
    import json

    path = _settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _write_settings(settings: dict[str, str]) -> None:
    import json

    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def get_setting(key: str, default: str | None = None) -> str | None:
    env = os.getenv(f"PERSONA_COUNCIL_{key.upper()}")
    if env:
        return env
    return _read_settings().get(key, default)


def set_setting(key: str, value: str) -> None:
    settings = _read_settings()
    settings[key] = value
    _write_settings(settings)


def _normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()[:2]
    return v if v in SUPPORTED_LANGUAGES else None


def detect_language(text: str | None) -> str:
    """Cheap, dependency-free German/English guess from free text.

    Used to honor "answer in the language the user writes in". Falls back to the
    default language when the signal is weak or the text is empty.
    """
    if not text or not text.strip():
        return DEFAULT_LANGUAGE
    lowered = text.lower()
    if any(ch in lowered for ch in "äöüß"):
        return "de"
    words = [w.strip(".,;:!?()[]\"'«»") for w in lowered.split()]
    hits = sum(1 for w in words if w in _GERMAN_MARKERS)
    if hits >= 2 or (words and hits / max(1, len(words)) > 0.12):
        return "de"
    return DEFAULT_LANGUAGE


def content_language() -> str:
    return _normalize_language(get_setting("content_language")) or DEFAULT_LANGUAGE


def ui_language() -> str:
    return _normalize_language(get_setting("ui_language")) or content_language()


def set_content_language(language: str, *, also_ui: bool = True) -> str:
    lang = _normalize_language(language) or DEFAULT_LANGUAGE
    set_setting("content_language", lang)
    if also_ui and _normalize_language(_read_settings().get("ui_language")) is None:
        set_setting("ui_language", lang)
    return lang


def set_ui_language(language: str) -> str:
    lang = _normalize_language(language) or DEFAULT_LANGUAGE
    set_setting("ui_language", lang)
    return lang


def ensure_content_language(sample_text: str | None) -> str:
    """Persist a detected content language the first time the user writes, then
    keep it stable. Returns the active content language."""
    existing = _normalize_language(get_setting("content_language"))
    if existing:
        return existing
    return set_content_language(detect_language(sample_text))


def language_instruction(language: str | None = None) -> str:
    lang = _normalize_language(language) or content_language()
    if lang == "de":
        return "Write ALL generated content in German (Deutsch)."
    return "Write ALL generated content in English."
