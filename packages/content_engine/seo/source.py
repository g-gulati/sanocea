"""Read access to the SEO worker's opportunities, and the guarded control-plane writes.

READS use the worker's persisted-read endpoints only. WRITES (status transitions, linking a result) go through the worker's
control endpoints, which require SEO_WORKER_CONTROL_TOKEN; without it every write is refused. Both transports are injectable
so the workflow is testable without a network."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable, Dict, List, Optional

GetJson = Callable[[str], Any]
PostJson = Callable[[str, Dict[str, Any]], Any]


def _worker_url() -> str:
    return os.environ.get("SEO_WORKER_URL", "http://127.0.0.1:8089").rstrip("/")


def http_get_json(path: str) -> Any:
    with urllib.request.urlopen(f"{_worker_url()}{path}", timeout=10) as r:  # noqa: S310 (loopback worker)
        return json.loads(r.read().decode("utf-8"))


def http_post_json(path: str, body: Dict[str, Any]) -> Any:
    token = os.environ.get("SEO_WORKER_CONTROL_TOKEN", "")
    if not token:
        raise PermissionError("SEO_WORKER_CONTROL_TOKEN is not set: control writes are refused")
    req = urllib.request.Request(f"{_worker_url()}{path}", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "x-seo-control-token": token})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


class OpportunitySource:
    def __init__(self, get_json: GetJson = http_get_json):
        self._get = get_json

    def list(self) -> Dict[str, Any]:
        return self._get("/opportunities")

    def get(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        return next((o for o in self.list().get("opportunities", []) if o.get("opportunityId") == opportunity_id), None)

    def autonomy(self) -> Dict[str, Any]:
        """The tenant's autonomy mode as the worker holds it (default RECOMMEND_ONLY when unconfigured)."""
        return self._get("/autonomy")

    def site_pages(self) -> List[Dict[str, Any]]:
        """Pages from the latest published-page audit (url/title/h1). Empty when the audit has not completed."""
        roster = self._get("/agent-roster").get("roster", [])
        a = next((r for r in roster if r.get("role") == "AI_CONTENT_AUDITOR" and r.get("status") == "COMPLETED"), None)
        pages = (a or {}).get("details", {}).get("pages", []) if a else []
        return [p for p in pages if isinstance(p, dict) and p.get("url")]


class OpportunityControl:
    """The only writer of opportunity state from this workflow."""

    def __init__(self, post_json: PostJson = http_post_json):
        self._post = post_json

    def transition(self, opportunity_id: str, to: str, actor: str, note: str) -> Dict[str, Any]:
        return self._post("/opportunities/transition", {"opportunityId": opportunity_id, "to": to, "actor": actor, "note": note})

    def authorize(self, opportunity_id: str) -> Dict[str, Any]:
        """Ask the worker's policy to authorise (AUTONOMOUS_AGENT) an opportunity awaiting approval."""
        return self._post("/opportunities/authorize", {"opportunityId": opportunity_id})

    def link_result(self, opportunity_id: str, ref: str, actor: str) -> Dict[str, Any]:
        return self._post("/opportunities/link-result", {"opportunityId": opportunity_id, "ref": ref, "actor": actor})
