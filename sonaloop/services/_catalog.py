"""Persona-catalog services — the core half of sonaloop-data's pull story
(tickets sonaloop-data/persona-pull-correctness +
sonaloop/catalog-sync-status-drift-safe-pull-refresh): browse the curated
catalog, recommend, PULL personas into the current store, and check STATUS —
the fetch/status half of the git analogy that pull alone was missing.

This lives in the service layer so core can use the catalog natively (CLI,
other services like refresh_persona_from_source); the MCP tools in
mcp_server/_tools_catalog.py are thin wrappers over these functions.

Layering (sonaloop-data depends on core, never the reverse, so nothing here
imports `sonaloop_data` at module level):

1. **sonaloop-data installed** (lazy import): the full surface — local-checkout
   or remote pulls via `load_into`/`pull_remote` (identical provenance stamping,
   idempotent re-pulls), facet derivation + the deterministic `recommend` scorer.
2. **Not installed**: `catalog_search`, `catalog_pull` and `catalog_status` keep
   working against the PUBLISHED catalog through a thin built-in fallback
   (stdlib urllib, zero extra dependencies) that mirrors sonaloop-data's URL
   contract (`manifest.json`, `packs/<id>.json`, `personas/<slug>/<file>`) and
   its `provenance.catalog` stamp. The published catalog is the deployed site —
   data.sonaloop.com serves the raw files next to the UI (override with
   SONALOOP_CATALOG_BASE_URL); an explicit git `ref` goes to
   raw.githubusercontent instead (the site only serves the current state). The duplication
   is deliberate and small (~60 lines): browse+pull must be usable from ANY
   sonaloop install, and the price is keeping `_PERSONA_FILES`/`RAW_URL`/the
   stamp shape in sync with `sonaloop_data.remote` — guarded by tests on both
   sides. Everything richer (packs metadata, facets, recommend) answers in-band
   with an "install sonaloop-data" note instead of erroring.

Sync semantics (the git analogy, deliberately):
- `catalog_status` == fetch+status: per pulled persona, is the catalog newer
  (`behind`), did it live on locally (`locally_modified`), both (`diverged`),
  or is it gone upstream (`removed_upstream`)? Exact when the catalog index
  carries per-persona `updated_at` (local checkout always does; the published
  manifest does since core's export emits it), coarse (`possibly_behind`, from
  manifest `generated_at`) otherwise.
- `catalog_pull` == pull: drift-SAFE by default — personas modified locally
  after their last pull are skipped and reported instead of silently
  overwritten; `force=True` restores plain overwrite. Lived local memories were
  never at risk (memory rows upsert by id); the guard protects the profile row.

`catalog_search` paginates per the shared convention (docs/pagination.md:
limit default 25 + opaque cursor, {items,total,has_more,next_cursor} envelope).

Tiers (the free/premium catalog split): manifest persona entries MAY carry
`tier: "free"|"premium"` — search/status surface it when present and treat its
absence as free/unknown (pre-tier manifests keep working untouched). Premium
persona files answer 401/403 to anonymous requests; SONALOOP_CATALOG_TOKEN (the
catalog token from app.sonaloop.com's Workspace page) rides as a Bearer only to
the configured HTTPS catalog origin, never manifest-owned CDN URLs or redirects.
Without a token, free personas stay 100%
functional and a pull that hits premium personas skips them IN-BAND
(`skipped_premium`, with the sign-in recipe) — never an error.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import embeddings_enabled, utc_now_iso
from ..storage import Store

CATALOG_REPO = "jhoetter/sonaloop-data"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"
DEFAULT_BASE_URL = "https://data.sonaloop.com"
TOKEN_ENV = "SONALOOP_CATALOG_TOKEN"

# Per-request catalog credential (multi-tenant hosts): a hosted deployment knows
# the signed-in user's entitlement and binds a catalog token around the request —
# it outranks the env var. Local single-user use keeps the env-var contract.
import contextvars  # noqa: E402  (kept beside its single consumer)

_REQUEST_CATALOG_TOKEN: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sonaloop_request_catalog_token", default=None)


def set_request_catalog_token(token: str | None) -> contextvars.Token:
    """Bind a catalog bearer to the current context (None = fall back to the
    SONALOOP_CATALOG_TOKEN env). Pass the returned token to
    reset_request_catalog_token() in a finally block."""
    return _REQUEST_CATALOG_TOKEN.set(token)


def reset_request_catalog_token(token: contextvars.Token) -> None:
    _REQUEST_CATALOG_TOKEN.reset(token)


def _base_url() -> str:
    """The published catalog's HTTP base — the deployed site serves the raw catalog
    files next to the UI (sonaloop-data ui/scripts/publish-catalog.mjs). Override
    with SONALOOP_CATALOG_BASE_URL. Keep in lockstep with sonaloop_data.remote."""
    return os.environ.get("SONALOOP_CATALOG_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    port = parts.port
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, (parts.hostname or "").lower(), port


def _catalog_credential_target(url: str) -> bool:
    """Whether a URL may receive the premium catalog bearer.

    Absolute avatar/CDN URLs are content from the catalog manifest, not part of
    the authorization origin. Keep the bearer pinned to the configured HTTPS
    catalog origin; explicit git refs and insecure overrides remain anonymous.
    """
    target = _origin(url)
    return target == _origin(_base_url()) and target[0] == "https"

# Mirror of sonaloop_data.remote.PERSONA_FILES (the per-persona snapshot files;
# profile.json is required, the rest optional). Keep in lockstep.
_PERSONA_FILES = ("profile.json", "SOUL.md", "MEMORY.md", "calendar.json",
                  "experiences.json", "daily_summaries.json", "memory.json", "eval.json")

INSTALL_NOTE = ("The sonaloop-data package is not installed — catalog_search, catalog_status "
                "and catalog_pull keep working against the published catalog "
                "(data.sonaloop.com; override with SONALOOP_CATALOG_BASE_URL), but facet "
                "filtering, recommendation and local-checkout pulls need it: "
                "`uv add sonaloop-data` (or pip install).")

FORCE_HINT = ("skipped personas were modified locally after their last pull — "
              "catalog_pull(force=True) overwrites them; catalog_status shows the drift")

PREMIUM_NOTE = ("premium persona — sign in at https://app.sonaloop.com, copy your catalog "
                "token from the Workspace page, and set SONALOOP_CATALOG_TOKEN")


class CatalogFetchError(RuntimeError):
    """A remote catalog fetch failed for a reason other than a plain 404."""


class CatalogAuthError(CatalogFetchError):
    """The catalog answered 401/403 — a premium persona fetched without (or with an
    invalid) SONALOOP_CATALOG_TOKEN. The pull paths absorb this in-band
    (`skipped_premium` + PREMIUM_NOTE); it never surfaces as a traceback."""


def _data_pkg():
    """The optional sonaloop-data package, or None — NEVER imported at module level
    (sonaloop-data depends on core; core only ever looks for it lazily)."""
    try:
        import sonaloop_data
        return sonaloop_data
    except ImportError:
        return None


def _local_root(pkg) -> Path | None:
    """The installed package's local catalog root (repo checkout or
    SONALOOP_DATA_CATALOG_ROOT) — None when there is no manifest to read."""
    try:
        from sonaloop_data.paths import catalog_root
        root = catalog_root()
        return root if (root / "manifest.json").exists() else None
    except Exception:
        return None


def _fetch_bytes(url: str) -> bytes | None:
    """stdlib fetcher mirroring sonaloop_data.remote._urllib_fetcher (None == 404).
    SONALOOP_CATALOG_TOKEN rides only to the configured HTTPS catalog origin.
    It is deliberately an unredirected header, so redirects and manifest-owned
    avatar/CDN URLs cannot receive a workspace credential."""
    headers = {"User-Agent": "sonaloop"}
    token = _REQUEST_CATALOG_TOKEN.get() or os.environ.get(TOKEN_ENV)
    req = urllib.request.Request(url, headers=headers)
    if token and _catalog_credential_target(url):
        # `unredirected_hdrs` are sent on this request but Python's redirect
        # handler intentionally does not copy them into the redirected Request.
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — https only
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (401, 403):
            raise CatalogAuthError(f"GET {url} -> HTTP {exc.code} (auth required)") from exc
        raise CatalogFetchError(f"GET {url} -> HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise CatalogFetchError(f"GET {url} failed: {exc.reason}") from exc


def _get(ref: str, path: str, *, required: bool = False) -> bytes | None:
    # Default ref -> the published catalog API (data.sonaloop.com); explicit ref ->
    # git raw (the site only serves the CURRENT state; history stays a git concern).
    url = (f"{_base_url()}/{path}" if ref == "main"
           else RAW_URL.format(repo=CATALOG_REPO, ref=ref, path=path))
    data = _fetch_bytes(url)
    if data is None and required:
        raise CatalogFetchError(f"{path} not found at {url}")
    return data


def catalog_avatar(slug: str, ref: str = "main") -> bytes | None:
    pkg = _data_pkg()
    if ref == "main" and pkg is not None and (root := _local_root(pkg)) is not None:
        path = root / "personas" / slug / "avatar.png"
        return path.read_bytes() if path.exists() else None
    return _get(ref, f"personas/{slug}/avatar.png")


# --------------------------------------------------------------------------- #
# search                                                                        #
# --------------------------------------------------------------------------- #

def _facet_summary(entries: list[dict[str, Any]], cap: int = 10) -> dict[str, dict[str, int]]:
    """Facet value counts over the FULL filtered set (never just the visible page)."""
    counts: dict[str, dict[str, int]] = {}
    for e in entries:
        for facet, values in (e.get("facets") or {}).items():
            bucket = counts.setdefault(facet, {})
            for v in values:
                bucket[v] = bucket.get(v, 0) + 1
    return {f: dict(sorted(vals.items(), key=lambda kv: (-kv[1], kv[0]))[:cap])
            for f, vals in sorted(counts.items())}


def _local_entries(pkg) -> list[dict[str, Any]]:
    """Browse rows from the local catalog: identity + derived facets + search text."""
    entries = []
    for profile in pkg.read_persona_files():
        role = (profile.get("role") or {}).get("title") or ""
        tier = profile.get("tier") or "free"
        facets = pkg.derive_facets(profile)
        facets["tier"] = [tier]
        entry = {"slug": profile.get("slug"), "display_name": profile.get("display_name", ""),
                 "role": role, "has_avatar": bool(profile.get("avatar")),
                 "facets": facets}
        if profile.get("tier"):                          # absent == free (pre-tier profiles)
            entry["tier"] = profile["tier"]
        entry["_text"] = " ".join([entry["slug"] or "", entry["display_name"], role,
                                   " ".join(profile.get("goals") or []),
                                   " ".join(profile.get("pain_points") or [])]).casefold()
        entries.append(entry)
    return entries


def _remote_entries(ref: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Browse rows from the published manifest (no checkout, no extra package)."""
    manifest = json.loads(_get(ref, "manifest.json", required=True))
    entries = []
    for p in manifest.get("personas", []):
        tier = p.get("tier") or "free"
        entry = {"slug": p.get("slug"), "display_name": p.get("display_name", ""),
                 "role": p.get("role", ""), "has_avatar": bool(p.get("has_avatar")),
                 "facets": {"tier": [tier]}}
        if p.get("tier"):                                # absent == free (pre-tier manifests)
            entry["tier"] = p["tier"]
        entry["_text"] = " ".join(str(v) for v in (entry["slug"], entry["display_name"],
                                                   entry["role"]) if v).casefold()
        entries.append(entry)
    return entries, manifest


def catalog_search(query: str | None = None, facets: dict[str, list[str]] | None = None,
                   limit: int = 25, cursor: str | None = None, ref: str = "main") -> dict[str, Any]:
    pkg = _data_pkg()
    notes: list[str] = []
    manifest_meta: dict[str, Any] = {}
    if pkg is not None and _local_root(pkg) is not None:
        source = "local-catalog"
        entries = _local_entries(pkg)
    else:
        source = f"{CATALOG_REPO}@{ref}"
        entries, manifest = _remote_entries(ref)
        manifest_meta = {"generated_at": manifest.get("generated_at"),
                         "schema_version": manifest.get("schema_version")}
        if pkg is None:
            notes.append(INSTALL_NOTE)
        if facets:
            remote_facets = {k: v for k, v in facets.items() if k == "tier"}
            ignored = sorted(k for k in facets if k != "tier")
            if ignored:
                notes.append("facet filtering beyond tier needs the sonaloop-data package "
                             "with a local catalog — IGNORED for this remote search: "
                             + ", ".join(ignored))
            facets = remote_facets or None

    if query:
        needle = query.strip().casefold()
        entries = [e for e in entries if needle in e["_text"]]
    for facet, wanted in sorted((facets or {}).items()):
        wanted_set = {str(v) for v in wanted}
        entries = [e for e in entries if wanted_set & set((e.get("facets") or {}).get(facet, []))]

    for e in entries:
        e.pop("_text", None)
    entries.sort(key=lambda e: e["slug"] or "")
    fp = {"query": query or "", "facets": facets or {}, "source": source}
    page = paginate(entries, lambda e: e["slug"] or "",            # noqa: F821 (bound)
                    limit=limit, cursor=cursor, filters=fp)
    summary = _facet_summary(entries) if source == "local-catalog" or (facets and set(facets) <= {"tier"}) else None
    return {**page, "source": source, "facet_summary": summary,
            **({"manifest": manifest_meta} if manifest_meta else {}),
            **({"notes": notes} if notes else {})}


# --------------------------------------------------------------------------- #
# recommend                                                                    #
# --------------------------------------------------------------------------- #

def catalog_recommend(spec: dict[str, Any]) -> dict[str, Any]:
    pkg = _data_pkg()
    if pkg is None:
        return {"skipped": True, "note": INSTALL_NOTE}
    if _local_root(pkg) is None:
        return {"skipped": True,
                "note": "sonaloop-data is installed but no local catalog was found — "
                        "recommendation scores full profiles, which only the checkout has. "
                        "Clone the catalog (or set SONALOOP_DATA_CATALOG_ROOT), or use "
                        "catalog_search + catalog_pull against the published catalog."}
    return pkg.recommend(spec)


# --------------------------------------------------------------------------- #
# status — the fetch/status half of the git analogy                            #
# --------------------------------------------------------------------------- #

def _catalog_index(ref: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """slug -> {updated_at} for the whole catalog, + source metadata. Exact
    per-persona timestamps from a local checkout (profiles always carry them) or
    from the published manifest when its index has them; otherwise updated_at is
    None and callers fall back to the coarse manifest `generated_at`."""
    pkg = _data_pkg()
    if pkg is not None and _local_root(pkg) is not None:
        index = {p.get("slug"): {"updated_at": p.get("updated_at"), "tier": p.get("tier")}
                 for p in pkg.read_persona_files()}
        return index, {"source": "local-catalog", "generated_at": None}
    manifest = json.loads(_get(ref, "manifest.json", required=True))
    index = {p.get("slug"): {"updated_at": p.get("updated_at"), "tier": p.get("tier")}
             for p in manifest.get("personas", [])}
    return index, {"source": f"{CATALOG_REPO}@{ref}",
                   "generated_at": manifest.get("generated_at")}


def _drift_reason(persona: dict[str, Any] | None) -> str | None:
    """Why overwriting this local persona would lose work — None when safe.
    ISO-8601 UTC strings compare lexicographically, so plain > is correct."""
    if persona is None:
        return None
    stamp = (persona.get("provenance") or {}).get("catalog")
    if not stamp:
        return "exists locally without catalog provenance (native/locally-authored persona)"
    if (persona.get("updated_at") or "") > (stamp.get("pulled_at") or ""):
        return (f"modified locally at {persona.get('updated_at')} "
                f"(last pulled {stamp.get('pulled_at')})")
    return None


def catalog_status(persona_slugs: list[str] | None = None, ref: str = "main",
                   store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    pulled = [p for p in store.list_personas()
              if (p.get("provenance") or {}).get("catalog")]
    if persona_slugs:
        wanted = set(persona_slugs)
        pulled = [p for p in pulled if p.get("slug") in wanted or p.get("id") in wanted]
    notes: list[str] = []
    if _data_pkg() is None:
        notes.append(INSTALL_NOTE)
    if not pulled:
        return {"items": [], "counts": {}, "source": None,
                "notes": notes + ["no catalog-pulled personas in this store"
                                  + (f" matching {sorted(set(persona_slugs))}" if persona_slugs else "")
                                  + " — catalog_pull brings some in"]}

    index, meta = _catalog_index(ref)
    items: list[dict[str, Any]] = []
    coarse = False
    for p in pulled:
        stamp = p["provenance"]["catalog"]
        pulled_at = stamp.get("pulled_at") or ""
        local_mod = (p.get("updated_at") or "") > pulled_at
        upstream = index.get(p.get("slug"))
        if upstream is None:
            status = "removed_upstream"
        else:
            if upstream.get("updated_at") is not None:
                behind = "behind" if upstream["updated_at"] > pulled_at else None
            else:
                gen = meta.get("generated_at") or ""
                behind = ("possibly_behind"
                          if gen > (stamp.get("manifest_generated_at") or "") else None)
                coarse = coarse or behind is not None
            if behind and local_mod:
                status = "diverged"
            elif behind:
                status = behind
            elif local_mod:
                status = "locally_modified"
            else:
                status = "up_to_date"
        item = {"slug": p.get("slug"), "id": p.get("id"), "status": status,
                "pulled_at": stamp.get("pulled_at"), "ref": stamp.get("ref"),
                "pack": stamp.get("pack"),
                "local_updated_at": p.get("updated_at"),
                "catalog_updated_at": (upstream or {}).get("updated_at")}
        if (upstream or {}).get("tier"):                 # absent == free (pre-tier manifests)
            item["tier"] = upstream["tier"]
        items.append(item)
    items.sort(key=lambda i: i["slug"] or "")
    counts: dict[str, int] = {}
    for i in items:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    if coarse:
        notes.append("the catalog index has no per-persona updated_at at this ref — "
                     "'possibly_behind' means the manifest was regenerated since the pull; "
                     "the persona itself may be unchanged")
    return {"items": items, "counts": counts, "source": meta["source"],
            "hint": ("catalog_pull refreshes 'behind' personas; locally_modified/diverged "
                     "need catalog_pull(force=True) to overwrite"),
            **({"notes": notes} if notes else {})}


# --------------------------------------------------------------------------- #
# pull                                                                         #
# --------------------------------------------------------------------------- #

def _pack_member_slugs(pack: str, ref: str, pkg) -> list[str]:
    """The pack's member slugs, from the local checkout when available, else the
    published catalog. Unknown pack raises KeyError (same as the pull paths)."""
    if pkg is not None:
        root = _local_root(pkg)
        if root is not None and (root / "packs" / f"{pack}.json").exists():
            raw = (root / "packs" / f"{pack}.json").read_text(encoding="utf-8")
            return json.loads(raw).get("personas") or []
    data = _get(ref, f"packs/{pack}.json")
    if data is None:
        raise KeyError(f"Unknown archetype pack: {pack!r} "
                       f"(no packs/{pack}.json in {CATALOG_REPO}@{ref})")
    return json.loads(data).get("personas") or []


def _builtin_pull(store: Store, persona_slugs: list[str] | None, pack: str | None,
                  ref: str, embed: bool) -> dict[str, Any]:
    """The dependency-free remote pull: fetch the selection from the published
    catalog (mirroring sonaloop_data.remote's URL contract), stamp
    `provenance.catalog` on each profile exactly like sonaloop_data.loader does,
    and import through core's own snapshot importer (idempotent upserts)."""
    manifest_raw = _get(ref, "manifest.json", required=True)
    manifest = json.loads(manifest_raw)
    roster = {p["slug"]: p for p in manifest.get("personas", [])}

    slugs: list[str] = []
    if pack:
        slugs.extend(_pack_member_slugs(pack, ref, None))
    for s in persona_slugs or []:
        if s not in slugs:
            slugs.append(s)
    unknown = [s for s in slugs if s not in roster]
    if unknown:
        raise ValueError(f"Unknown persona slug(s) in {CATALOG_REPO}@{ref}: {unknown}")

    stamp: dict[str, Any] = {"source": "sonaloop-data",
                             "manifest_generated_at": manifest.get("generated_at"),
                             "schema_version": manifest.get("schema_version"),
                             "pulled_at": utc_now_iso(),
                             "repo": CATALOG_REPO, "ref": ref}
    if ref == "main":
        stamp["base_url"] = _base_url()
    if pack:
        stamp["pack"] = pack

    pulled: list[str] = []
    skipped_premium: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="sonaloop-catalog-") as tmp:
        base = Path(tmp)
        (base / "manifest.json").write_bytes(manifest_raw)
        for slug in slugs:
            pdir = base / "personas" / slug
            pdir.mkdir(parents=True, exist_ok=True)
            try:
                for name in _PERSONA_FILES:
                    data = _get(ref, f"personas/{slug}/{name}", required=(name == "profile.json"))
                    if data is None:
                        continue
                    if name == "profile.json":
                        profile = json.loads(data)
                        profile.setdefault("provenance", {})["catalog"] = {**stamp, "slug": slug}
                        data = (json.dumps(profile, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
                    (pdir / name).write_bytes(data)
                if roster[slug].get("has_avatar"):
                    # avatar_url escape hatch (ticket sonaloop-data/avatar-policy-lean-distribution):
                    # an absolute URL on the roster entry wins over the in-repo path, so avatars can
                    # move to release assets/CDN later without breaking any consumer.
                    url = roster[slug].get("avatar_url")
                    avatar = (_fetch_bytes(url) if url
                              else _get(ref, f"personas/{slug}/avatar.png"))
                    if avatar is not None:
                        (pdir / "avatar.png").write_bytes(avatar)
            except CatalogAuthError:
                # Premium persona without a (valid) catalog token: 401/403 is the catalog's
                # tier gate, never a bug — answer in-band and keep pulling the free ones.
                shutil.rmtree(pdir, ignore_errors=True)
                skipped_premium.append({"slug": slug,
                                        "tier": roster[slug].get("tier") or "premium",
                                        "reason": PREMIUM_NOTE})
                continue
            pulled.append(slug)
        if pulled:
            try:
                out = import_snapshot(in_dir=str(base), store=store, embed=embed)  # noqa: F821 (bound)
            except ValueError:
                # import_snapshot computes a ROOT-relative summary path AFTER every DB write
                # (and the embed backfill); a temp snapshot outside the repo trips exactly that
                # last step. State is fully imported by then — same absorb as sonaloop_data.loader.
                store.commit()
                out = {"embeddings": "re-derived" if embed else "skipped"}
        else:
            out = {}
    return {**out, "personas": pulled, "repo": CATALOG_REPO, "ref": ref,
            "source": "built-in remote fallback", "note": INSTALL_NOTE,
            **({"skipped_premium": skipped_premium} if skipped_premium else {})}


def catalog_pull(persona_slugs: list[str] | None = None, pack: str | None = None,
                 ref: str = "main", embed: bool = False, force: bool = False,
                 store: Store | None = None) -> dict[str, Any]:
    if not persona_slugs and not pack:
        raise ValueError("catalog_pull is selective by design — pass persona_slugs and/or pack "
                         "(a full 300+-persona import belongs to sonaloop-data's load_into/CLI)")
    store = store or Store()
    pkg = _data_pkg()

    # Embeddings ride the pull whenever a provider is configured (the user's rule:
    # "create the embeddings as long as an API key is set — this should ALWAYS
    # happen when personas are synced"). The backfill is fail-soft, so `embed=True`
    # with no provider is a harmless no-op; callers can still force it on explicitly.
    embed = embed or embeddings_enabled()

    # Drift guard (the pull half of the git analogy): never silently overwrite a
    # persona that lived on locally. Pack membership is only resolved when the
    # store actually holds personas a pull could clobber, so the common
    # fresh-store path stays fetch-free.
    skipped: list[dict[str, Any]] = []
    pull_slugs = list(persona_slugs or [])
    use_pack = pack
    local = {p["slug"]: p for p in store.list_personas()}
    if not force and local:
        members = _pack_member_slugs(pack, ref, pkg) if pack else []
        candidates = pull_slugs + [m for m in members if m not in pull_slugs]
        skipped = [{"slug": s, "reason": reason} for s in candidates
                   if (reason := _drift_reason(local.get(s)))]
        skipped_slugs = {s["slug"] for s in skipped}
        pull_slugs = [s for s in pull_slugs if s not in skipped_slugs]
        if pack and skipped_slugs & set(members):
            # The pack pull would re-import skipped members — demote to an explicit
            # slug list instead (those personas lose the `pack` provenance field).
            pull_slugs += [m for m in members
                           if m not in skipped_slugs and m not in pull_slugs]
            use_pack = None
        if not pull_slugs and not use_pack:
            return {"personas": [], "landed": [], "skipped_locally_modified": skipped,
                    "note": "nothing pulled — every selected persona was modified locally "
                            "after its last pull; " + FORCE_HINT}

    if pkg is not None:
        if ref == "main" and _local_root(pkg) is not None:
            # Same data, no network: the checkout (or SONALOOP_DATA_CATALOG_ROOT) wins for
            # the default ref; pass an explicit ref to force a published-version pull.
            if use_pack:
                for slug in _pack_member_slugs(use_pack, ref, pkg):
                    if slug not in pull_slugs:
                        pull_slugs.append(slug)
                use_pack = None
            out = pkg.load_into(store, embed=embed, persona_slugs=pull_slugs or None)
            out.setdefault("source", "local-catalog")
        else:
            out = pkg.pull_remote(store, persona_slugs=pull_slugs or None, pack=use_pack,
                                  ref=ref, embed=embed)
            out.setdefault("source", f"{CATALOG_REPO}@{ref}")
    else:
        out = _builtin_pull(store, pull_slugs or None, use_pack, ref, embed)

    landed = []
    premium = {s["slug"] for s in out.get("skipped_premium") or []}    # skipped, not landed
    for slug in out.get("personas") or pull_slugs or []:
        if slug in premium:
            continue
        p = store.get_persona(slug)
        if p:
            landed.append({"slug": p["slug"], "id": p["id"],
                           "display_name": p.get("display_name", ""),
                           "provenance": (p.get("provenance") or {}).get("catalog")})
    out = {**out, "landed": landed}
    if skipped:
        out["skipped_locally_modified"] = skipped
        out["note"] = FORCE_HINT
    return out
