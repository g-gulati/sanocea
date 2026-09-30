"""Read-only bridge from the Command Centre API to the SEO monitoring worker (packages/seo-stack).

Why this exists: the SEO worker listens on 127.0.0.1 only and has no authentication of its own; some of its GET
endpoints MUTATE state (/sync-gsc, /run-tier2, /sync-rankcommand). The browser must never reach it directly. This
bridge is the only path, and it enforces three things:

1. An ALLOWLIST of persisted-read views. Anything else (including every mutating endpoint) is unreachable.
2. TENANT ISOLATION. The worker serves exactly one tenant. A caller may see its data only when the authenticated
   merchant_id equals the worker's own tenant id; every other merchant gets "not monitored" and no data. The worker's
   tenant id is never disclosed to a non-matching caller.
3. TRUTH. Data is passed through unmodified. A view that fails is reported as unavailable with its error; nothing is
   defaulted, cached, or filled in.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

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


class SeoWorkerUnreachable(Exception):
    """The worker could not be reached or answered with a non-JSON / non-200 response."""


class SeoBridge:
    def __init__(self, worker_url: str | None = None, timeout_s: float = 5.0) -> None:
        self.worker_url = (worker_url or os.environ.get("SEO_WORKER_URL") or DEFAULT_WORKER_URL).rstrip("/")
        self.timeout_s = timeout_s

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
            raise SeoWorkerUnreachable(f"worker unreachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SeoWorkerUnreachable(f"worker returned non-JSON for {path}") from exc

    def overview(self, merchant_id: str) -> dict[str, Any]:
        """Aggregate of every allowlisted view for `merchant_id`, or a not-monitored marker (no data) when the
        worker's tenant is a different tenant."""
        health = self._get("/health")
        worker_tenant = health.get("tenantId") if isinstance(health, dict) else None
        if not worker_tenant or worker_tenant != merchant_id:
            return {"monitored": False, "merchant_id": merchant_id, "reason": "No SEO monitor is configured for this tenant."}

        views: dict[str, Any] = {}
        for name, path in VIEWS.items():
            try:
                views[name] = {"ok": True, "data": self._get(path)}
            except SeoWorkerUnreachable as exc:
                views[name] = {"ok": False, "error": str(exc)}
        return {
            "monitored": True,
            "merchant_id": merchant_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "worker_status": health.get("status"),
            "views": views,
        }
