# Contributing

Notes for anyone (human or coding agent) changing this repo.

- **Run both suites before you commit:** `make test` (pytest, then vitest) and
  `make check` (the frontend dependency rule in `frontend/scripts/check-ui.mjs`).
  The suite is hermetic: `tests/conftest.py` builds its own fixture repos and
  points every data path at a temp dir.
- **The chart is the only state this app owns.** It lives in `data/shipyard.sqlite`
  and is mirrored one way to markdown on every write (ADR 0003). Never edit the
  mirror by hand; author chart nodes as JSON and run `make chart-seed`.
- **The gates are the point.** `_open_gate` and `_review_gate` in
  `backend/app/main.py` refuse at the API. A change that lets work route around a
  refusal is a bug, even if every test passes. Destructive writes need the
  `impact_token` their impact read returned (`backend/app/tokens.py`).
- **One Conventional Commit per logical change.** Record user-visible changes under
  `## Unreleased` in `CHANGELOG.md`; decisions that change a contract get an ADR in
  `docs/adr/`.
- **Frontend layering:** `ui.jsx` owns visual primitives, `kit.jsx` holds domain
  helpers, views compose them. Colours and type sizes come from `styles.css` and the
  vendored `frontend/src/vendor/fleet-ui/fleet.css`, never from component literals.
- Never commit a secret, a `.env`, or anything under `data/`.
