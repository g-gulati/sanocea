from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, Request


@dataclass
class AuthContext:
    """The smallest reusable auth foundation, not a general IAM product. Distinguishes exactly the
    principal types Phase 4.5 requires: machine/service (background worker, internal jobs), human/
    operator (merchant-scoped), and webhook (verified separately, at the connector layer, by per-
    merchant HMAC secret - see ShopifyConnector._verify_hmac, already real since Phase 0)."""

    principal_type: str  # "operator" | "service"
    principal_id: str  # the api_keys.id - this is what Approval.decided_by becomes, never free text
    merchant_id: str | None  # None only for a service-wide key
    role: str


def _resolve(request: Request, authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    raw_key = authorization[len("Bearer "):].strip()
    store = request.app.state.store
    record = store.resolve_api_key(raw_key)
    if record is None:
        raise HTTPException(status_code=401, detail="invalid or revoked api key")
    return record


async def require_operator(request: Request, authorization: str | None = Header(default=None)) -> AuthContext:
    """A caller must never be able to choose another merchant_id and gain access merely by changing the
    URL: this dependency reads the merchant_id (or, for an internal-operator key, the explicit
    allowed_merchants set) from the AUTHENTICATED key record, and separately verifies the URL path's
    merchant_id is actually authorized - or access is denied. A 'service' key may act for any merchant
    (internal worker use only, e.g. the recovery worker) - genuinely unrestricted, unlike
    allowed_merchants below, which is always an explicit, finite set.

    Internal-operator multi-merchant keys (Command Center demo-switching UX correction): a key minted
    with `allowed_merchants` (api_keys.merchant_id is NULL for such a key - see
    PostgresStore.create_api_key) is authorized ONLY for merchant_ids in that explicit set - never
    derived from the request, the frontend dropdown, or any client-supplied value. A merchant_id absent
    from the set (including one that doesn't exist at all) is rejected here, before any business logic
    runs - fail closed. An ordinary single-merchant operator key (the overwhelming majority - every
    existing key predating this change) has no allowed_merchants rows and behaves EXACTLY as before:
    scoped to its own api_keys.merchant_id alone."""
    merchant_id_in_path = request.path_params.get("merchant_id")
    record = _resolve(request, authorization)
    if record["role"] not in {"operator", "service"}:
        raise HTTPException(status_code=403, detail="key does not grant operator access")
    if record["role"] == "operator":
        allowed_merchants = record.get("allowed_merchants")
        if allowed_merchants:
            if merchant_id_in_path not in allowed_merchants:
                raise HTTPException(status_code=403, detail="api key is not authorized for this merchant")
        elif record["merchant_id"] != merchant_id_in_path:
            raise HTTPException(status_code=403, detail="api key is not authorized for this merchant")
    return AuthContext(principal_type=record["role"], principal_id=record["id"], merchant_id=merchant_id_in_path, role=record["role"])


async def require_service(request: Request, authorization: str | None = Header(default=None)) -> AuthContext:
    """Machine/service authentication only - for the background recovery worker and other internal
    jobs. Never merchant-scoped by URL; the key itself carries no merchant binding."""
    record = _resolve(request, authorization)
    if record["role"] != "service":
        raise HTTPException(status_code=403, detail="service credential required")
    return AuthContext(principal_type="service", principal_id=record["id"], merchant_id=None, role="service")
