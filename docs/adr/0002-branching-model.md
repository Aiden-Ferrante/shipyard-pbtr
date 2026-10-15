# ADR 0002: branching model — main is prod, dev is the workbench

Date: 2026-07-09
Status: accepted

## Context

The fleet needs a dev/prod separation at the *code* level to match the one that
already exists at the *run* level (`make dev` vs `make prod`, dev ports vs prod
ports). Solo development; single working copy per repo; Mission Control starts
apps from the checkout directory.

## Decision

Two long-lived branches, nothing more:

- **`main` = prod.** What Mission Control runs. Always startable: `make test`
  passes and `make prod` boots before anything merges here.
- **`dev` = the workbench.** Day-to-day commits land here. Messy is fine;
  history tells the story.

**Promotion** is a merge: `git checkout main && git merge dev`, run
`make test`, restart the app in MC, `git checkout dev` to keep working.
Feature branches off `dev` are allowed for risky experiments but not required.

Rejected: GitFlow (release/hotfix ceremony has no consumer here), trunk-only
(no stable pointer for "what MC runs" when mid-experiment).

## Consequences

- "Is prod broken?" has a git answer: `main` is the last known-good state.
- The promotion moment is explicit — the natural time to run tests, bump the
  wiki, and check the shipyard checklist.
- This model becomes the fleet default; candidates for a future standards.yaml
  item once proven on a second repo.
