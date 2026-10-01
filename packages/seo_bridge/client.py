"""Read-only bridge from the SANOCEA API to the SEO monitoring worker (packages/seo-stack).

Why this exists: the SEO worker listens on 127.0.0.1 only and has no authentication of its own; some of its GET
endpoints MUTATE state (/sync-gsc, /run-tier2, /sync-rankcommand). The browser must never reach it directly. This
bridge is the only path, and it enforces:

1. ACCESS by the EXISTING demo-session credential and nothing else (see `require_demo_session`): the merchant-scoped
   operator key POST /demo/sessions mints, bound to a currently-unexpired demo_ephemeral_sessions row. No new
   credential type and no login. The SEO worker's tenant is Sanocea's own internal tenant, NOT a merchant: it has no
   `merchants` row and never needs one.
2. An ALLOWLIST of persisted-read views (`VIEWS`). Anything else, including every mutating endpoint, is unreachable.
3. NO DISCLOSURE. Refusals are generic. Error text never contains the worker URL, and worker-internal fields
   (host:pid, filesystem paths, setting names) are redacted before anything reaches a browser (`redact`).
4. TRUTH. Data is passed through unmodified, with the worker's own provenance labels and timestamps. A view that
   fails is reported as unavailable with a short error; nothing is defaulted, cached, or filled in.
5. NO WRITES. This module and its route perform no database writes of any kind.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from fastapi import Header, HTTPException, Request

from sanocea.packages.authn import AuthContext

# view name -> worker path. Persisted-read endpoints only. NEVER add /sync-*, /run-* or any state-changing path.
VIEWS: dict[str, str] = {
    "gsc_summary": "/gsc-summary",
    "rank_movement_gsc": "/rank-movement",
    "serp_rank_movement": "/serp-rank-movement",
    "competitive_intel": "/competitive-intel",
    "authority": "/authority",
    "scheduler": "/scheduler",
    "bing": "/bing",
    "model_visibility": "/model-visibility",
    "agent_roster": "/agent-roster",
    "signals": "/search-signals",
    "gsc_snapshots": "/gsc-snapshots",
    "heartbeats": "/heartbeats",
    "deltas": "/deltas",
    "opportunities": "/opportunities",
    "gsc_property": "/google-search-state",
}

# Worker-internal fields that must never reach a browser: process owner (hostname:pid) and filesystem/DB paths.
_REDACT_KEYS = {"owner", "dbPath", "db_path", "hostname", "pid", "opportunityId"}  # opportunityId: internal reference, never sent to a browser
_REDACT_STR = re.compile(
    r"(?:/(?:opt|root|home|var|etc|usr|srv|tmp)/[^\s\"',}]+)"          # filesystem paths
    r"|(?:\b[A-Za-z][A-Za-z0-9-]*:\d{2,7}\b(?=$|[\s,;]))"            # host:pid
    r"|(?:\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,}\b)"                       # ENV_VAR_NAMES (config setting names)
)


_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")


def redact(obj: Any) -> Any:
    """Recursively drops worker-internal keys and scrubs filesystem paths, host:pid tokens and ENV_VAR-style setting names from strings. Everything
    else (values, provenance labels, timestamps) passes through byte-for-byte."""
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items() if k not in _REDACT_KEYS}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        if _IDENTIFIER.fullmatch(obj):
            return obj  # a whole-string identifier (a role, status or type such as AI_CONTENT_AUDITOR) is data, not a leaked setting name
        return _REDACT_STR.sub(lambda m: "a required setting" if m.group(0).isupper() and "_" in m.group(0) else "<redacted>", obj)
    return obj


def _get_path(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


# view name -> the field the worker itself reports as that view's persisted-data time. A view with no such field
# reports None (the UI says so); a time is never computed, guessed or filled in here.
_TIMESTAMP_FIELDS: dict[str, str] = {
    "gsc_summary": "snapshot.capturedAt",
    "competitive_intel": "lastUpdated",
    "scheduler": "lastHeartbeat.tickAt",
    "signals": "analyzedAt",
    "agent_roster": "lastSynchronizedAt",
}


def _view_updated_at(name: str, data: Any) -> str | None:
    if name == "rank_movement_gsc" and isinstance(data, dict):
        stamps = [t.get("lastFetchedAt") for dim in ("site", "pages") for t in ((data.get(dim) or {}).get("trajectories") or []) if isinstance(t, dict) and t.get("lastFetchedAt")]
        return max(stamps) if stamps else None
    if name in ("heartbeats", "deltas") and isinstance(data, list):
        stamps = [r.get("timestamp") for r in data if isinstance(r, dict) and r.get("timestamp")]
        return max(stamps) if stamps else None
    if name == "gsc_snapshots" and isinstance(data, list):
        stamps = [r.get("capturedAt") for r in data if isinstance(r, dict) and r.get("capturedAt")]
        return max(stamps) if stamps else None
    if name == "gsc_property" and isinstance(data, dict):
        c = data.get("connection")
        return c.get("lastCheckedAt") if isinstance(c, dict) else None
    if name == "opportunities" and isinstance(data, dict):
        stamps = [o.get("lastSeenAt") for o in (data.get("opportunities") or []) if isinstance(o, dict) and o.get("lastSeenAt")]
        return max(stamps) if stamps else None
    if name == "authority" and isinstance(data, dict):
        stamps = [r.get("fetchedAt") for r in (data.get("rows") or []) if isinstance(r, dict) and r.get("fetchedAt")]
        return max(stamps) if stamps else None
    field = _TIMESTAMP_FIELDS.get(name)
    value = _get_path(data, field) if field else None
    return value if isinstance(value, str) else None

DEFAULT_WORKER_URL = "http://127.0.0.1:8089"

_DEMO_FORBIDDEN_DETAIL = "demo session required"


def _is_active_demo_session(store: Any, merchant_id: str) -> bool:
    """True iff `merchant_id` is a live row in demo_ephemeral_sessions (the same durable table POST /demo/sessions
    writes and touch_lease reads). Read-only. A store without a Postgres DSN (in-memory) has no sessions: fail closed."""
    dsn = getattr(store, "dsn", None)
    if not dsn:
        return False
    import psycopg2

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM demo_ephemeral_sessions WHERE merchant_id = %s AND expires_at > now()", (merchant_id,))
        return cur.fetchone() is not None


async def require_demo_session(request: Request, authorization: str | None = Header(default=None)) -> AuthContext:
    """The existing demo-session credential (the merchant-scoped operator key POST /demo/sessions mints) and nothing
    else: no new credential type, no new login. Allows ONLY an operator key bound to exactly one merchant that is a
    currently-unexpired demo session. Fail closed:
    - no/invalid/revoked key                          -> 401
    - any other key (service, internal-operator, a real merchant's key, an expired/unknown session) -> 403, generic."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    store = request.app.state.store
    record = store.resolve_api_key(authorization[len("Bearer "):].strip())
    if record is None:
        raise HTTPException(status_code=401, detail="invalid or revoked api key")
    merchant_id = record.get("merchant_id")
    if record.get("role") != "operator" or record.get("allowed_merchants") or not merchant_id or not _is_active_demo_session(store, merchant_id):
        raise HTTPException(status_code=403, detail=_DEMO_FORBIDDEN_DETAIL)
    return AuthContext(principal_type="operator", principal_id=record["id"], merchant_id=merchant_id, role="operator")


class SeoWorkerUnreachable(Exception):
    """The worker could not be reached or answered with a non-JSON / non-200 response."""


class SeoBridge:
    def __init__(self, worker_url: str | None = None, timeout_s: float = 5.0) -> None:
        self.worker_url = (worker_url or os.environ.get("SEO_WORKER_URL") or DEFAULT_WORKER_URL).rstrip("/")
        self.timeout_s = timeout_s

    def _scrub(self, text: str) -> str:
        return text.replace(self.worker_url, "<seo-worker>")

    def _get(self, path: str) -> Any:
        try:
            with urllib.request.urlopen(f"{self.worker_url}{path}", timeout=self.timeout_s) as resp:  # noqa: S310 (fixed http worker URL)
                if resp.status != 200:
                    raise SeoWorkerUnreachable(f"worker returned HTTP {resp.status} for {path}")
                return json.loads(resp.read().decode("utf-8"))
        except SeoWorkerUnreachable:
            raise
        except urllib.error.HTTPError as exc:
            raise SeoWorkerUnreachable(f"worker returned HTTP {exc.code} for {path}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise SeoWorkerUnreachable(self._scrub(f"worker unreachable: {exc}")) from exc
        except json.JSONDecodeError as exc:
            raise SeoWorkerUnreachable(f"worker returned non-JSON for {path}") from exc

    def overview(self) -> dict[str, Any]:
        """Aggregate of every allowlisted view of the SEO worker's own (internal) tenant. Callers are already
        authorized by `require_demo_session`; a worker that does not report its tenant is treated as
        unavailable rather than guessed at."""
        health = self._get("/health")
        tenant_id = health.get("tenantId") if isinstance(health, dict) else None
        if not tenant_id:
            raise SeoWorkerUnreachable("worker did not report its tenant")

        views: dict[str, Any] = {}
        for name, path in VIEWS.items():
            try:
                data = redact(self._get(path))
                views[name] = {"ok": True, "updated_at": _view_updated_at(name, data), "data": data}
            except SeoWorkerUnreachable as exc:
                views[name] = {"ok": False, "updated_at": None, "error": str(exc)}
        return {
            "monitored": True,
            "tenant_id": tenant_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "worker_status": health.get("status"),
            "views": views,
        }
