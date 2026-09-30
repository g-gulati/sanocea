"""Read-only bridge from the Command Centre API to the SEO monitoring worker (packages/seo-stack).

Why this exists: the SEO worker listens on 127.0.0.1 only and has no authentication of its own; some of its GET
endpoints MUTATE state (/sync-gsc, /run-tier2, /sync-rankcommand). The browser must never reach it directly. This
bridge is the only path, and it enforces:

1. AUTHORIZATION BY KEY CLASS, not by merchant. The SEO worker's tenant is Sanocea's own internal SEO tenant. It is
   NOT a merchant: it has no `merchants` row, no config, no channels, and it never needs one. Access is granted only to
   service keys and internal-operator keys (an operator key authorized for an explicit set of merchants). Every
   single-merchant key, including every prospect and demo-session key, is refused. The decision reads only the
   authenticated key record, never anything the client supplies. See `require_internal_operator`.
2. An ALLOWLIST of persisted-read views. Anything else (including every mutating endpoint) is unreachable.
3. NO DISCLOSURE. Refusals are generic. Error text never contains the worker URL, and no credential is ever read,
   stored or returned here.
4. TRUTH. Data is passed through unmodified. A view that fails is reported as unavailable with a short error; nothing
   is defaulted, cached, or filled in.
5. NO WRITES. This module and its route perform no database writes of any kind.
"""

from __future__ import annotations

import json
import os
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
}

DEFAULT_WORKER_URL = "http://127.0.0.1:8089"

_FORBIDDEN_DETAIL = "internal operator or service credential required"


async def require_internal_operator(request: Request, authorization: str | None = Header(default=None)) -> AuthContext:
    """Allow ONLY: (a) a service key, or (b) an operator key that is an internal-operator key, i.e. one authorized for
    an explicit, non-empty set of merchants (`allowed_merchants`). Everything else is refused, fail closed:
    - no/invalid/revoked key            -> 401
    - single-merchant operator key      -> 403 (this includes every prospect / demo-session key)
    - any other role                    -> 403
    The 403 body is deliberately generic: it names no tenant, merchant, route target or worker detail."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    record = request.app.state.store.resolve_api_key(authorization[len("Bearer "):].strip())
    if record is None:
        raise HTTPException(status_code=401, detail="invalid or revoked api key")
    role = record.get("role")
    if role == "service":
        return AuthContext(principal_type="service", principal_id=record["id"], merchant_id=None, role="service")
    if role == "operator" and record.get("allowed_merchants"):
        return AuthContext(principal_type="operator", principal_id=record["id"], merchant_id=None, role="operator")
    raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)


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
        authorized by `require_internal_operator`; a worker that does not report its tenant is treated as
        unavailable rather than guessed at."""
        health = self._get("/health")
        tenant_id = health.get("tenantId") if isinstance(health, dict) else None
        if not tenant_id:
            raise SeoWorkerUnreachable("worker did not report its tenant")

        views: dict[str, Any] = {}
        for name, path in VIEWS.items():
            try:
                views[name] = {"ok": True, "data": self._get(path)}
            except SeoWorkerUnreachable as exc:
                views[name] = {"ok": False, "error": str(exc)}
        return {
            "monitored": True,
            "tenant_id": tenant_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "worker_status": health.get("status"),
            "views": views,
        }
