"""Impact tokens — a destructive write must present the token its impact read issued.

The pattern (fleet-wide, 2026-09-04; this file is copied verbatim into
mission-control and learnhub-core — plain functions, no shared package across
tiers): the impact read appends `token` to its payload and remembers
(kind, target, digest-of-the-impact, expiry). The destructive route takes
`token` as a query parameter and refuses, naming the read to make, when the
token is missing, unknown, expired, issued for another target, or when the
impact has changed since (the world moved between the read and the click).
Single use. Ten minutes. In-process only: a restart forgets every token, which
is the safe direction.

This turns "read before the button, never after" from a docstring into a gate.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time

TTL = 600.0
_ISSUED: dict[str, tuple[str, str, str, float]] = {}


def digest(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def issue(kind: str, target: str, payload) -> str:
    """Remember this impact and return the token that proves it was read."""
    _sweep()
    tok = secrets.token_urlsafe(16)
    _ISSUED[tok] = (kind, target, digest(payload), time.time() + TTL)
    return tok


def check(kind: str, target: str, token: str | None, payload, read: str) -> str | None:
    """None when the token is good (and consume it); else the refusal sentence.
    `read` names the GET the caller must make, e.g. "GET /api/problems/{pid}/impact"."""
    _sweep()
    if not token:
        return f"refused: read {read} first and pass its token — the impact is what you are agreeing to"
    rec = _ISSUED.get(token)
    if not rec:
        return f"refused: that token is unknown or expired — read {read} again and pass the new token"
    k, t, d, exp = rec
    if k != kind or t != target:
        return f"refused: that token was issued for a different {k} — read {read} for this one"
    if d != digest(payload):
        return f"refused: the impact has changed since the token was issued — read {read} again"
    del _ISSUED[token]
    return None


def _sweep() -> None:
    now = time.time()
    for k in [k for k, (_, _, _, exp) in _ISSUED.items() if exp < now]:
        del _ISSUED[k]


def _reset() -> None:  # tests
    _ISSUED.clear()
