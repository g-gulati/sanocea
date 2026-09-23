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

from sanocea.packages.audit import AuditLedger
from sanocea.packages.notifications.phone import PhoneValidationError, normalize_phone

from .reset import reset_prospect_tenant
from .tenants import PROSPECT_TENANTS

DEFAULT_SESSION_TTL = timedelta(minutes=12)  # see module docstring: an active chat keeps sliding this
# forward (touch_lease), so this is really the ABANDONED-session window, not a hard cap on a real visit.

_lock = threading.Lock()
# merchant_id -> {"key_id": str | None, "expires_at": datetime}
_leases: dict[str, dict[str, Any]] = {}


class NoDemoTenantAvailable(RuntimeError):
    """Every configured prospect demo tenant is currently in an active, unexpired session."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _has_active_persisted_contact(store, merchant_id: str) -> bool:
    """Safety check against a real bug: the in-memory `_leases` dict is wiped by every process restart
    (or deploy), but a real visitor's `DemoSessionContact` is persisted in Postgres and survives it. Without
    this check, a restart makes every tenant look "free" again to the very next lease request, which then
    calls reset_prospect_tenant on a tenant a real visitor is still actively using - wiping their session
    contact out from under them. This makes the in-memory dict a cache/optimization, not the sole source
    of truth, so a restart can no longer cause a premature reset of a real active session."""
    from sanocea.packages.domain_contract.models import DemoSessionContact

    now = _now()
    try:
        contacts = store.list(DemoSessionContact, merchant_id)
    except Exception:
        return False  # never let a lookup failure block leasing - fail open on the safety check itself
    return any(c.cleared_at is None and c.expires_at > now for c in contacts)


def touch_lease(store, merchant_id: str, *, ttl: timedelta = DEFAULT_SESSION_TTL) -> datetime | None:
    """Slides an in-progress session's expiry forward on real activity (called from the /chat route on
    every message) - an actively-engaged visitor should not hit an arbitrary fixed cutoff. Extends BOTH
    the in-memory tenant lease and the persisted DemoSessionContact (if one exists for this merchant), and
    returns the new expiry so the caller can hand it back to the frontend - the countdown the visitor sees
    should always reflect real backend state, never a stale client-side guess from session creation.
    Returns None if this merchant has no active lease at all (nothing to extend)."""
    from sanocea.packages.domain_contract.models import DemoSessionContact

    now = _now()
    new_expiry = now + ttl
    with _lock:
        if merchant_id not in _leases or _leases[merchant_id]["expires_at"] <= now:
            return None
        _leases[merchant_id]["expires_at"] = new_expiry
    try:
        for contact in store.list(DemoSessionContact, merchant_id):
            if contact.cleared_at is None and contact.expires_at > now:
                contact.expires_at = new_expiry
                store.put(contact)
    except Exception:
        pass  # the in-memory lease extension above is what actually matters; this is best-effort
    return new_expiry


def lease_demo_session(
    store, *, dsn: str | None = None, ttl: timedelta = DEFAULT_SESSION_TTL, whatsapp_number: str | None = None,
) -> dict[str, Any]:
    """Leases one free (or expired) prospect tenant to a new anonymous visitor: resets it to its
    canonical baseline and mints a fresh merchant-scoped operator key scoped to it. Reclaiming an expired
    lease revokes its stale key first, so the fixed tenant pool self-heals with no background cleanup
    job - the next visitor's request is what triggers the reclaim.

    `whatsapp_number`, if given, is lead-context only (the WhatsApp-style chat demo collects it, but no
    WAHA transport is provisioned - see docs/architecture/integrations/WHATSAPP_DEMO_TRANSPORT_COMPARISON.md
    - so nothing is actually sent to it). Recorded as a normal audit event, the same durable record every
    other operator-visible action already produces, so it's visible via the existing
    GET /merchants/{id}/audit route rather than a new lead-capture pipe. A malformed number never blocks
    starting the demo itself - it's just not recorded."""
    with _lock:
        now = _now()
        candidate = next(
            (
                mid for mid in PROSPECT_TENANTS
                if (mid not in _leases or _leases[mid]["expires_at"] <= now)
                and not _has_active_persisted_contact(store, mid)
            ),
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

    if whatsapp_number:
        try:
            from sanocea.packages.notifications.resolution import DemoApprovalNotificationService
            from sanocea.packages.notifications.transport import WebChatTransport

            contact = DemoApprovalNotificationService(store, WebChatTransport()).set_session_contact(
                candidate, phone_e164=whatsapp_number, session_label="web_chat_demo", consented=True, ttl=ttl,
            )
            AuditLedger(store).record(
                merchant_id=candidate, actor="prospect", source="web_chat_demo", action="demo_lead_captured",
                object_type="DemoSessionContact", object_id=contact.id, result="consented",
            )
        except PhoneValidationError:
            pass  # cosmetic/lead-context only (see docstring) - never blocks starting the demo itself

    return {
        "session_id": f"demosess_{os.urandom(12).hex()}",
        "merchant_id": candidate,
        "display_name": result["display_name"],
        "api_key": result["operator_api_key"],
        "expires_at": expires_at.isoformat(),
    }
