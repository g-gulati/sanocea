"""Post-publication verification: RE-OBSERVE the live site, let the worker's verifyOutcome() judge it, act on the verdict.

The publisher's own receipt is never trusted as proof. Facts are re-collected from the live sitemap and the live URLs with the
injected `fetch` (no redirect following). MET -> outcome recorded (learn) and monitoring continues; NOT_MET -> roll back if the
receipt's rollback is valid, otherwise INVESTIGATE; INCONCLUSIVE -> INVESTIGATE. Missing evidence is never success."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from packages.content_engine.seo.publisher import PublishReceipt, PublisherError, StaticSiteReleasePublisher
from packages.content_engine.seo.sitemap import Fetch, _locs, _norm
from packages.content_engine.seo.source import OpportunityControl
from packages.content_engine.seo.store import SeoContentStore


def _fid(kind: str, subject: str, value) -> str:
    return f"fact:{kind}:" + hashlib.sha1(f"{subject}|{value}".encode()).hexdigest()[:8]


def observe_sitemap_facts(live_sitemap_xml: str, listed_url: str, destination: str, fetch: Fetch) -> List[Dict[str, Any]]:
    """Facts in the worker's schema ({id, kind, subject, value, source}) about the live state of this change."""
    src = "[OBSERVED: LIVE POST-PUBLICATION FETCH]"
    facts: List[Dict[str, Any]] = []
    try:
        locs = [_norm(x) for x in _locs(live_sitemap_xml)]
    except Exception:
        return []  # the live sitemap is unreadable: no facts, so verification cannot succeed
    for u in (listed_url, destination):
        if _norm(u) in locs:
            facts.append({"id": _fid("sitemap_lists", u, u), "kind": "sitemap_lists", "subject": u, "value": u, "source": src})
    status, headers, _ = fetch(destination)
    if status in (301, 302, 303, 307, 308) and headers.get("location"):
        facts.append({"id": _fid("redirects_to", destination, headers["location"]), "kind": "redirects_to", "subject": destination, "value": headers["location"], "source": src})
    elif status != 200:
        return []  # the destination could not be observed: do not guess
    return facts


def verify_publication(receipt: PublishReceipt, observed: List[Dict[str, Any]], control: OpportunityControl, publisher: StaticSiteReleasePublisher, store: SeoContentStore) -> Dict[str, Any]:
    """Judge freshly observed facts; roll back on a contradiction when the rollback is valid. Returns the verdict and what was done."""
    v = control.verify(receipt.opportunity_id, observed, True)
    result: Dict[str, Any] = {"verification": v, "action_taken": "NONE"}
    if v["status"] == "NOT_MET" and v["next"] == "ROLLBACK":
        try:
            rb = publisher.rollback(receipt, store)
            store.append_audit(receipt.tenant_id, "evt_vrb_" + receipt.change_id, {"type": "VERIFICATION_ROLLBACK", "change_id": receipt.change_id, "reason": v["reason"], "restored_release": rb.restored_release, "at": rb.rolled_back_at})
            result["action_taken"] = "ROLLED_BACK"
        except PublisherError as e:  # no valid rollback: never pretend; leave it for investigation
            store.append_audit(receipt.tenant_id, "evt_vinv_" + receipt.change_id, {"type": "VERIFICATION_INVESTIGATE", "change_id": receipt.change_id, "reason": f"verification failed and rollback is not possible: {e.code}"})
            result["action_taken"] = "INVESTIGATE_ROLLBACK_UNAVAILABLE"
    elif v["status"] == "MET":
        store.append_audit(receipt.tenant_id, "evt_vmet_" + receipt.change_id, {"type": "VERIFICATION_MET", "change_id": receipt.change_id, "next": "LEARN_AND_MONITOR"})
        result["action_taken"] = "LEARNED"
    else:
        store.append_audit(receipt.tenant_id, "evt_vinv_" + receipt.change_id, {"type": "VERIFICATION_INVESTIGATE", "change_id": receipt.change_id, "reason": v["reason"]})
        result["action_taken"] = "INVESTIGATE"
    return result
