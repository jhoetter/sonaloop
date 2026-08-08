# Remote stimulus admission

Remote MCP needs real product screens for a Reaction Test, but it must not turn the
long-lived Cloud process into a URL fetcher or filesystem reader. The dedicated contract is:

```text
begin_research_job
  -> run_step (product_understanding dispatch)
  -> admit_remote_screenshot × N
  -> record_flow_manifest
  -> record_product_understanding (exact manifest + coverage)
  -> run_step continues
```

## Direct bytes only

`admit_remote_screenshot` accepts canonical base64 bytes plus `filename`, `media_type`,
`captured_at` and `target_revision`. It has no `path`, URL, redirect or remote-fetch input.
SSRF, private-address traversal, DNS rebinding and redirect revalidation are therefore outside
the reachable contract rather than delegated to model instructions. Generic `attach_asset`,
`add_artifact`, host browsers and local paths remain outside Cloud workspace-user profiles.

Every new intent requires all of:

- the active workspace from the authenticated request context (never a caller-selected field);
- an existing project and active governed run in that workspace;
- a stable `operation_id`, reused unchanged on transport retries;
- the exact Product Understanding `dispatch_token` issued for that project/run.

The operation fingerprint includes the workspace, project, run, SHA-256, filename/MIME,
capture time, target revision and labels. An exact retry returns the existing authorization
identity. Reusing the operation id with changed content or provenance fails before project
mutation. Asset ids also include the workspace; two tenants uploading identical bytes never
share an authorization id. Content-addressed physical storage may deduplicate a verified blob
inside its authorized partition.

## Admission pipeline

The following gates run before the project record can cite the bytes:

1. base64 and 10 MB encoded/decoded bounds;
2. basename and allow-listed extension (`png`, `jpg`/`jpeg`, `webp`);
3. exact declared MIME, magic and decoded Pillow format agreement;
4. exact container end (PNG `IEND`, JPEG EOI, WebP RIFF length), rejecting trailing/polyglot
   payloads;
5. Pillow `verify()` and a separate full `load()`, single-frame requirement, 10,000-pixel
   dimension, 20-million-pixel and 80 MB decoded-pixel budgets;
6. a narrow built-in EICAR-signature check; and
7. the configured external scanner, before admission.

The built-in check is **not general antivirus**. Shared PostgreSQL production defaults
`SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED` to true and fails closed when no scanner is
configured, when it cannot start, times out or exits non-zero. Configure a real, separately
installed/pinned scanner as a JSON argv vector:

```dotenv
SONALOOP_REMOTE_ASSET_SCANNER_ARGV_JSON=["/usr/bin/clamscan","--no-summary","{path}"]
SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED=1
SONALOOP_REMOTE_ASSET_SCANNER_TIMEOUT_SECONDS=30
```

The executable must be an absolute executable file. `{path}` is accepted only as one exact
argv element; if absent, the quarantined path is appended. The process runs with `shell=False`,
a minimal environment, bounded output and timeout. Candidate files are deleted with their
temporary quarantine directory. Scanner output is not persisted; the immutable receipt stores
only status, engine basename, policy digest and timestamp.

Exact retries reuse the immutable scan receipt rather than producing a time-dependent second
verdict. If a record created without an external scanner is restored or migrated into an
environment that now requires one, replay fails with `REMOTE_ASSET_REPLAY_SCAN_INSUFFICIENT`;
a local-only receipt can never be promoted into shared-production evidence by retrying it.

## Immutable flow versions and Product Understanding

`record_flow_manifest` accepts an ordered list of at most 50
`{asset_version_id, label}` entries. Every entry must be a screenshot admitted for the same
workspace/project/run and `target_revision`. A stable `flow_key` has append-only integer
versions; each manifest freezes:

- ordered asset ids and their `sha256:` digests;
- human labels, expected task, target revision and capture timestamps;
- workspace/project/run/operation provenance;
- `supersedes` lineage and its own SHA-256 manifest digest.

Exact retries return the same version; changed content under one operation id is rejected.
The compatibility projection in `project.flows` is immutable and carries the same id, version
and digest, so existing artifact walkthroughs can consume it without weakening the contract.

A Product Understanding that cites such a flow must also submit
`stimulus_manifest={id, version, target_revision, manifest_digest}` and a coverage checklist
with exactly one `status=inspected` entry per ordered step, citing that step's exact asset
version. Its `revision` must equal the frozen target revision. The binding and resolved
asset digests are copied into the immutable Product Understanding version. A later manifest
version therefore cannot retroactively change an older preflight.

For a manifest-bound Product Understanding, the Reaction-Test evidence gate narrows admissible
claim citations to that exact manifest id and the exact asset versions in its frozen coverage.
A screen or manifest uploaded later is only a candidate for a new preflight; it cannot silently
enter the already-bound council or synthesis.

## Reads, audit and failure behavior

Workspace users can read admitted records through `list_assets`, `get_asset`, `view_asset`,
`list_flow_manifests` and `get_flow_manifest`. `view_asset` resolves only an opaque project-owned
asset id. The Cloud execution ledger always redacts `content_base64`, even when bounded content
capture is opted in; replay uses the admitted SHA-256 and provenance rather than pixel bodies.

Any validation/scanner/identity failure leaves the project without a new evidence record.
Reaction Test completion does not downgrade to an evidence-free path: Product Understanding
still needs the exact admitted manifest and complete coverage, followed by the normal evidence,
claim-posture and completeness gates.
