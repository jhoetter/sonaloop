WEB_PORT ?= 8787
FORWARDED_WEB_PORT ?= 18787
FUGU_WEB_PORT ?= 58787

UV ?= uv

.PHONY: install dev dev-forwarded dev-forwarded-fugu mcp snapshot restore skills test test-smoke kill-ports playwright icons check-icons hooks template-deck ux

# Install the repo's git hooks (pre-push runs `check-icons`, so a stale vendored
# copy is caught locally before the design-sync CI goes red). Idempotent; `make
# install` runs it too. Skips on machines without ../sonaloop-design (see the hook).
hooks:
	@git config core.hooksPath .githooks && echo "git hooks installed (.githooks)"

# Refresh the vendored design-system modules (sonaloop/_icons.py + sonaloop/_tokens.py)
# from ../sonaloop-design. Run after editing icons.data.mjs / tokens.data.mjs + `npm run gen`.
icons:
	bash scripts/sync_icons.sh

# Drift guard: re-vendor and fail if sonaloop/_icons.py or _tokens.py differ from the
# design system — i.e. a token/icon change in ../sonaloop-design wasn't synced here. (CI / pre-push.)
check-icons:
	bash scripts/sync_icons.sh
	@git diff --exit-code -- sonaloop/_icons.py sonaloop/_tokens.py sonaloop/_components_css.py sonaloop/_charts.py sonaloop/_deck.py sonaloop/_deck_assets.py \
	  || { echo "✗ vendored design-system files are stale — run 'make icons' and commit"; exit 1; }
	@echo "✓ vendored design-system files are in sync with ../sonaloop-design"

# Render the deck master template (every layout, placeholder content) to a real .pptx —
# the harness view of what customers get. Same data the design docs preview at #/deck.
template-deck:
	$(UV) run sonaloop template-deck

# Symlink version-controlled skills into .claude/skills/ so Claude Code discovers
# them (.claude/skills is gitignored). Run once after clone.
skills:
	@mkdir -p .claude/skills
	@for d in claude-skills/*/; do n=$$(basename $$d); ln -sfn ../../$$d .claude/skills/$$n; echo "linked $$n"; done

# Write the portable, local-only snapshot of all generated state to data/export/.
snapshot:
	$(UV) run sonaloop export-snapshot

# Rebuild the runtime DB from data/export/ (use after `git clone` to reproduce
# the exact local state without regenerating).
restore:
	$(UV) run sonaloop import-snapshot

install:
	$(UV) sync
	$(UV) run playwright install chromium   # headless browser for prototype screenshots + meta-report PDF
	@$(MAKE) hooks
	@echo "installed - run 'make dev' for :$(WEB_PORT) or 'make dev-forwarded' for :$(FORWARDED_WEB_PORT)"

# --reload is scoped to the Python source: without --reload-dir the stat-poller
# walks the whole tree every 250ms (.venv/, data/ with its constantly-changing
# SQLite WAL, prototypes/) and pegs a CPU, which can wedge the server over time.
# --timeout-graceful-shutdown: open SSE streams (/api/events) otherwise block reload forever.
dev: kill-ports
	@echo "→ Web   http://127.0.0.1:$(WEB_PORT)"
	$(UV) run python -m uvicorn 'sonaloop.web:create_app' --factory --reload \
	  --reload-dir sonaloop --reload-exclude '*/data/*' \
	  --timeout-graceful-shutdown 3 \
	  --host 127.0.0.1 --port $(WEB_PORT)

# Forwarded dev profile for viewing this machine through an SSH tunnel.
#   ssh -L $(FORWARDED_WEB_PORT):127.0.0.1:$(FORWARDED_WEB_PORT) <host>
dev-forwarded:
	$(MAKE) dev WEB_PORT=$(FORWARDED_WEB_PORT)

# Same, but on the Fugu (non-EU) dev host's port range so it can be tunnelled
# alongside the EU host without local port clashes (FUGU = FORWARDED + 40000).
dev-forwarded-fugu:
	$(MAKE) dev WEB_PORT=$(FUGU_WEB_PORT)

mcp:
	$(UV) run sonaloop-mcp

# Full test suite (pytest, dev dependency-group). Hermetic: temp DB, no network.
test:
	$(UV) run --group dev pytest -q

# Visual regression (spec/ux-contract.md §5): seed a temp demo store, screenshot the canonical
# screens light+dark, pixel-diff against tests/ux_goldens/. UPDATE=1 rewrites the goldens.
ux:
	$(UV) run python scripts/ux_shots.py $(if $(UPDATE),--update,)

test-smoke:
	$(UV) run python -m compileall sonaloop
	$(UV) run sonaloop persona-list >/dev/null
	$(UV) run python -c "from sonaloop.web import create_app; app=create_app(); print(app.title)"

# Re-fetch just the chromium binary (the playwright package is a hard dependency via `uv sync`).
# Needed for prototype screenshots + the meta-report PDF export.
playwright:
	$(UV) run playwright install chromium

kill-ports:
	@for p in $(WEB_PORT); do \
	  pids=$$(lsof -ti :$$p 2>/dev/null); \
	  [ -n "$$pids" ] && kill -9 $$pids 2>/dev/null || true; \
	done; true
