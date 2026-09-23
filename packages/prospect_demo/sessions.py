"""Self-service demo session leasing (browser self-service demo, Slice 1).

Reuses `reset_prospect_tenant` (tenant reset + real seed data) and `PostgresStore.create_api_key` /
`revoke_api_key` (scoped, revocable operator keys) exactly as they already exist for the operator-driven
`/merchants/{id}/demo/reset` route - this module adds only the one thing neither of those already
provides: "which prospect tenant is currently lent to which anonymous visitor, until when."

In-memory, single-process by design (see infra/systemd/sanocea-api.service.example - one uvicorn worker,
no Redis/queue in this topology). A lease does not need to survive a process restart: every tenant simply
looks free again, and the next lease still resets it before handing it out, so nothing is lost by keeping
this state in memory rather than standing up new infrastructure for it.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from .reset import reset_prospect_tenant
from .tenants import PROSPECT_TENANTS

DEFAULT_SESSION_TTL = timedelta(minutes=30)

_lock = threading.Lock()
# merchant_id -> {"key_id": str | None, "expires_at": datetime}
_leases: dict[str, dict[str, Any]] = {}


class NoDemoTenantAvailable(RuntimeError):
    """Every configured prospect demo tenant is currently in an active, unexpired session."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lease_demo_session(store, *, dsn: str | None = None, ttl: timedelta = DEFAULT_SESSION_TTL) -> dict[str, Any]:
    """Leases one free (or expired) prospect tenant to a new anonymous visitor: resets it to its
    canonical baseline and mints a fresh merchant-scoped operator key scoped to it. Reclaiming an expired
    lease revokes its stale key first, so the fixed tenant pool self-heals with no background cleanup
    job - the next visitor's request is what triggers the reclaim."""
    with _lock:
        now = _now()
        candidate = next(
            (mid for mid in PROSPECT_TENANTS if mid not in _leases or _leases[mid]["expires_at"] <= now),
            None,
        )
        if candidate is None:
            raise NoDemoTenantAvailable("every prospect demo tenant is currently in an active session")
        stale = _leases.get(candidate)
        # Reserve the slot before releasing the lock for the (slow) reset, so a concurrent request never
        # also picks `candidate`.
        _leases[candidate] = {"key_id": None, "expires_at": now + ttl}

    if stale is not None and stale["key_id"]:
        try:
            store.revoke_api_key(stale["key_id"])
        except Exception:
            pass  # best-effort: an already-revoked/missing key must never block minting the new one

    try:
        result = reset_prospect_tenant(candidate, dsn=dsn)
    except Exception:
        with _lock:
            _leases.pop(candidate, None)  # release the reservation so the tenant isn't stuck "busy"
        raise

    expires_at = _now() + ttl
    with _lock:
        _leases[candidate] = {"key_id": result["operator_key_id"], "expires_at": expires_at}

    return {
        "session_id": f"demosess_{os.urandom(12).hex()}",
        "merchant_id": candidate,
        "display_name": result["display_name"],
        "api_key": result["operator_api_key"],
        "expires_at": expires_at.isoformat(),
    }
