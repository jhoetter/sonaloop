# Pagination in core

The convention is cross-repo and lives in **sonaloop-data**:
[`docs/pagination.md`](https://github.com/jhoetter/sonaloop-data/blob/main/docs/pagination.md).
One rule set for every Sonaloop surface that lists things — this note records
how core adopts it.

## Machine surfaces (MCP tools)

`limit` (default 25) + an **opaque cursor** over a stable sort key; the
response is the shared envelope:

```json
{ "items": [...], "total": 311, "has_more": true, "next_cursor": "…" }
```

- `next_cursor` is present exactly when `has_more` is true.
- The cursor also fingerprints the **filter set** it was issued under —
  reusing it with different filters is rejected (restart from page 1).
- **Backward compatible**: no params → the first page + the `has_more` hint.

Implementation: `sonaloop/services/_pagination.py` (`paginate` /
`encode_cursor` / `decode_cursor`). Adopters:

| Tool | Sort key |
|---|---|
| `list_personas` | `display_name`, slug-tiebroken |
| `list_councils` | `created_at` + id, newest first |
| `list_notes` | `created_at` + id, creation order |
| `get_corpus` (`include_chunks=True` → `chunk_list`) | chunk `idx` |
| `catalog_search` (sonaloop-data catalog) | catalog `slug` |

Beyond lists, the **output budget** (tests/test_mcp_output_budget.py) keeps
every read tool ≤ ~80k chars (~20k tokens) on a realistic fixture: big single
documents answer summary-first or capped, always with the totals and an
in-band `note` naming the param/tool that returns the rest (e.g.
`get_calendar_period` → `get_activity`; `get_timeline` →
`max_facts`/`max_events`). Never a silent truncation.

The substrate `query_*` tools keep their own versioned `limit`/`offset`
contract (`substrate_version` pins it; see docs/substrate.md) — older adopter,
same spirit.

## Web lists (the inspector)

Numbered pages: `?page=N` lives in the URL **alongside** the `?q=` filter, so
views are shareable and back/forward restores them. Submitting the filter box
drops the page param (a changed filter resets to page 1); the h1 count and
`Page N of M` are computed over the **full filtered set**. ~25 rows per page.

Adopters: `/personas`, `/jobs` (components: `_page_window` / `_pager` /
`_list_filter_box` in `sonaloop/web/_pager.py`).
