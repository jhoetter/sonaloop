"""i18n contract tests — keep the bilingual UI chrome honest.

These guard the invariants documented in sonaloop/web/_i18n.py:
  - STRINGS covers exactly SUPPORTED_LANGUAGES.
  - every language defines the SAME key set with the SAME {placeholders}.
  - every t("literal") in the codebase resolves to a defined key.
  - no key is defined-but-unused (no legacy strings lingering).
  - every vocabulary `label_key` (suggestions/*.json) is defined in every language —
    keys resolved from data (t(meta["label_key"])) are invisible to the literal scan.
  - the web layer never ASSEMBLES a t() key (prefix + value); the frozen prefix
    allowlist below is the complete set of legitimate dynamic calls.

The scans read the source so the tables cannot drift from their call sites.
"""
from __future__ import annotations

import json
import re
import pathlib

from sonaloop.config import SUPPORTED_LANGUAGES
from sonaloop.web._i18n import STRINGS, FALLBACK_LANGUAGE, t, _UI_LANG

_PKG = pathlib.Path(__file__).resolve().parent.parent / "sonaloop"
_PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")

# A real t("key") call: `t` not preceded by an identifier char (so `.get(`,
# `format(`, `dict(` don't match), one string literal, then `,` or `)`.
_LITERAL = re.compile(r'(?<![A-Za-z0-9_])t\(\s*f?["\']([a-z0-9_]+)["\']\s*[,)]')
# Dynamic keys built from a literal prefix: t("vote_" + x) / t(f"council_kicker_{m}").
_DYN_PREFIX = re.compile(r'(?<![A-Za-z0-9_])t\(\s*"([a-z0-9_]+)"\s*\+')
_DYN_FPREFIX = re.compile(r'(?<![A-Za-z0-9_])t\(\s*f"([a-z0-9_]+)\{')


def _placeholders(value: str) -> set[str]:
    return set(_PLACEHOLDER.findall(value))


def _scan_sources() -> tuple[set[str], set[str]]:
    """Return (literal keys, dynamic key-prefixes) used across the package."""
    literals: set[str] = set()
    prefixes: set[str] = set()
    for path in _PKG.rglob("*.py"):
        if path.name == "_i18n.py":
            continue
        src = path.read_text()
        literals |= set(_LITERAL.findall(src))
        prefixes |= set(_DYN_PREFIX.findall(src))
        prefixes |= set(_DYN_FPREFIX.findall(src))
    return literals, prefixes


def _vocab_label_keys() -> set[str]:
    """Every `label_key` declared in the data-driven vocabularies (sonaloop/suggestions/*.json).
    These reach t() as data (t(meta["label_key"])) — invisible to the literal scan above."""
    keys: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "label_key" and isinstance(v, str):
                    keys.add(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in (_PKG / "suggestions").glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return keys


def test_languages_match_supported():
    assert set(STRINGS) == set(SUPPORTED_LANGUAGES)
    assert FALLBACK_LANGUAGE in STRINGS


def test_all_languages_define_the_same_keys():
    ref = set(STRINGS[FALLBACK_LANGUAGE])
    for lang, table in STRINGS.items():
        keys = set(table)
        assert not (ref - keys), f"{lang} is missing keys: {sorted(ref - keys)}"
        assert not (keys - ref), f"{lang} has extra keys: {sorted(keys - ref)}"


def test_placeholders_match_across_languages():
    ref = STRINGS[FALLBACK_LANGUAGE]
    for lang, table in STRINGS.items():
        for key, value in table.items():
            assert _placeholders(value) == _placeholders(ref[key]), (
                f"placeholder mismatch for {key!r} in {lang!r}: "
                f"{_placeholders(value)} vs {_placeholders(ref[key])}")


def test_every_used_literal_key_is_defined():
    literals, _ = _scan_sources()
    defined = set(STRINGS[FALLBACK_LANGUAGE])
    missing = sorted(k for k in literals if k not in defined)
    assert not missing, f"t() called with undefined keys: {missing}"


def test_no_legacy_unused_keys():
    literals, prefixes = _scan_sources()
    literals |= _vocab_label_keys()                          # resolved as data: t(meta["label_key"])
    # Namespaced ("ns.key") strings come from EXTENSIONS via register_strings() — their
    # call sites live in other repos, so the usage scan cannot see them. Parity for them
    # is extension_parity_problems() (tested below).
    defined = {k for k in STRINGS[FALLBACK_LANGUAGE] if "." not in k}

    def is_used(key: str) -> bool:
        if key in literals:
            return True
        if key.endswith("_one") and key[:-4] in literals:   # singular variant of a used count key (t() plural)
            return True
        return any(key != p and key.startswith(p) for p in prefixes)

    unused = sorted(k for k in defined if not is_used(k))
    assert not unused, f"defined but never used via t() (legacy — remove): {unused}"


def test_every_vocabulary_label_key_is_defined_in_every_language():
    # label_keys reach t() as DATA (e.g. t(stance_meta(v)["label_key"])) — the literal scan can't see
    # them, so a missing key would paint the raw key into the UI (the `stance_mixed` chip bug class).
    keys = _vocab_label_keys()
    assert keys, "no vocabulary label_keys found — did suggestions/*.json move?"
    for lang, table in STRINGS.items():
        missing = sorted(k for k in keys if k not in table)
        assert not missing, f"vocabulary label_keys missing from {lang!r}: {missing}"


# The complete set of legitimate dynamic t() prefixes in the web layer — each one is bounded by a code
# enum (vote order, council mode, severity, artifact kind, …), NEVER by stored free text. Do not add to
# this list for stored data: resolve a vocabulary `label_key` instead (parity-tested above).
_WEB_DYN_PREFIX_ALLOWLIST = {
    "h2h_decisive_", "rt_sev_", "council_kicker_", "council_mode_",
    "artifact_kind_", "coverage_level_", "asset_kind_",
    # product taxonomy: bounded by web/_primitive_taxonomy.py PRIMITIVES/FAMILIES and subtype_value().
    "primitive_", "primitive_family_", "subtype_",
    # session replay: both bounded by the recorder's code enums (services._usability_sessions
    # _FIDELITIES / _ACTION_TYPES, validated on record) and membership-guarded at the call site.
    "fidelity_", "action_",
}


def test_web_never_assembles_t_keys_outside_the_allowlist():
    # Guards the `stance_mixed` bug class: t("prefix" + stored_value) builds keys the parity tests can't
    # see, and t()'s raw-key fallback paints them into the UI. New dynamic keys must not appear.
    offenders = []
    for path in (_PKG / "web").rglob("*.py"):
        src = path.read_text()
        for prefix in set(_DYN_PREFIX.findall(src)) | set(_DYN_FPREFIX.findall(src)):
            if prefix not in _WEB_DYN_PREFIX_ALLOWLIST:
                offenders.append(f"{path.relative_to(_PKG)}: t(\"{prefix}\" + …)")
    assert not offenders, ("assembled t() keys in the web layer — resolve a vocabulary label_key "
                           "instead:\n  " + "\n  ".join(sorted(offenders)))


def test_register_strings_namespace_guard_and_parity():
    """The extension i18n seam (docs/i18n.md): register_strings() only accepts
    namespaced dotted keys (so an extension can never shadow a core string), keys
    resolve through the normal t(), and extension_parity_problems() reports any
    language the extension forgot."""
    import pytest
    from sonaloop.web._i18n import register_strings, extension_parity_problems

    with pytest.raises(ValueError):
        register_strings("fr", {"cloudx.usage_h": "Usage"})        # unsupported language
    with pytest.raises(ValueError):
        register_strings("en", {"settings": "hijacked"})           # flat key = core namespace
    with pytest.raises(ValueError):
        register_strings("en", {"cloudx.usage_h": 7})              # non-str value
    try:
        register_strings("en", {"cloudx.usage_h": "Usage of {n} runs"})
        problems = extension_parity_problems()
        assert problems and "cloudx.usage_h" in problems[0] and "de" in problems[0]
        register_strings("de", {"cloudx.usage_h": "Verbrauch"})    # placeholder mismatch
        assert any("placeholder" in p for p in extension_parity_problems())
        register_strings("de", {"cloudx.usage_h": "Verbrauch über {n} Runs"})
        assert extension_parity_problems() == []
        token = _UI_LANG.set("de")
        try:
            assert t("cloudx.usage_h", n=3) == "Verbrauch über 3 Runs"
        finally:
            _UI_LANG.reset(token)
    finally:                                                       # never leak into other tests
        for table in STRINGS.values():
            table.pop("cloudx.usage_h", None)


def test_t_translates_formats_and_falls_back():
    token = _UI_LANG.set("de")
    try:
        assert t("settings") == "Einstellungen"
        assert t("n_nodes", n=5) == "5 Knoten"
        # missing key degrades to the raw key, never raises
        assert t("__does_not_exist__") == "__does_not_exist__"
    finally:
        _UI_LANG.reset(token)
    token = _UI_LANG.set("en")
    try:
        assert t("settings") == "Settings"
    finally:
        _UI_LANG.reset(token)
