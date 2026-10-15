PY := backend/.venv/bin/python
PORT ?= 8845

# Loopback, not 0.0.0.0. Shipyard has no auth and a write-capable API, so binding
# every interface put a chart anyone on the LAN could delete from onto the LAN.
# Remote access is `tailscale serve` in front of this — tailnet only, real cert:
#   tailscale serve --bg --https=8845 http://127.0.0.1:8845
# Override for a deliberate exception, e.g. `make prod HOST=0.0.0.0`.
HOST ?= 127.0.0.1

# dev/prod depend on setup, and setup is driven by marker files rather than by
# the directories themselves. Both details matter: without the dependency a
# missing venv fails forever instead of self-healing, and keying off
# frontend/node_modules directly means an *empty* node_modules counts as
# satisfied — which is exactly how this repo ended up unable to start.
setup: backend/.venv/.deps frontend/node_modules/.installed

backend/.venv/.deps: backend/requirements.txt
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -q -r backend/requirements.txt
	touch backend/.venv/.deps

frontend/node_modules/.installed: frontend/package.json
	cd frontend && npm install --silent
	touch frontend/node_modules/.installed

dev: setup
	$(PY) -m uvicorn app.main:app --app-dir backend --reload --port $(PORT) &
	cd frontend && npm run dev

prod: setup
	cd frontend && npm run build
	$(PY) -m uvicorn app.main:app --app-dir backend --host $(HOST) --port $(PORT)

# Both suites, because a test that only runs when someone remembers the other
# command is the same silence as a skip (see test-ui below).
test: setup
	$(PY) -m pytest tests/ -q
	cd frontend && npm test

# The browser test needs three things plain `make test` cannot assume: a browser, a
# build to serve, and the app on a real port. It skips without the first two — and a
# skip is not a pass, so this target exists to make running it a single command.
# PLAYWRIGHT_CHROMIUM=/path/to/chrome skips the download and uses a browser you have.
# Every browser test, not a named one. The list was a single file, so a second
# browser test could be added, pass locally, and never run through the documented
# entry point again — which is the same silence as a skip.
test-ui: setup
	cd frontend && npm run build
	$(PY) -m playwright install chromium
	$(PY) -m pytest tests/test_graph_drawer.py tests/test_graph_legibility.py -q

# Both contracts this repo is held to: the frontend dependency rule, which lives
# here, and the fleet's colour and type scale, which lives in fleet-ui. Scoped to
# this repo on purpose — shipyard must not go red because another app drifted.
# fleet-ui is a sibling clone and may be absent; say so and carry on rather than
# failing a check nobody can act on from inside this repo.
FLEET_CHECK := $(CURDIR)/../fleet-ui/check.sh
check:
	node frontend/scripts/check-ui.mjs
	@if [ -f "$(FLEET_CHECK)" ]; then \
	  bash "$(FLEET_CHECK)" "$(CURDIR)/frontend/src"; \
	else \
	  echo "fleet check: skipped — no check.sh at $(FLEET_CHECK)"; \
	fi

# Put chart nodes authored as markdown into the store, which is where the app reads
# from (ADR 0003 — the export is one-way, so authoring in the file leaves the app
# blind to it). Idempotent; `make chart-seed ARGS=--dry-run` shows the plan first.
SEED ?= scripts/world-awareness.json
chart-seed: setup
	$(PY) scripts/seed_chart.py $(SEED) $(ARGS)

.PHONY: setup dev prod test test-ui check chart-seed
