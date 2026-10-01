"""Publish eligibility under the autonomy policy (decision point 2). Evaluates, never publishes.

Authorisation (worker, decision point 1) lets SANOCEA START work. Eligibility decides whether finished work MAY be
published automatically: every gate must pass, or nothing is published and the item stays in review/blocked.

Gates (Class B: all; Class A: the safety subset, because content safety is never weakened; Class C: never eligible):
 evidence-backed opportunity, valid decision, standing approval with consistent actor type, no unacceptable page overlap,
 content grounding, ClaimsGate, SEO QA, duplicate check (draft similarity AND no existing publication), tenant authorisation,
 publish-target authorisation, audit event, rollback/reversal information.
Mirrors the worker's action classes and mode matrix (parity-tested). Fail closed on anything unknown."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from packages.content_engine.seo.brief import QUERY_OVERLAP_MIN, valid_approval
from packages.content_engine.seo.models import SeoBrief, SeoDraft
from packages.content_engine.seo.store import SeoContentStore

POLICY_REF = "sanocea-autonomy-policy@1.0.0"
CLASS_A = {"IMPROVE_TITLE_META", "ADD_INTERNAL_LINKS", "IMPROVE_SCHEMA", "DISTRIBUTE_EXISTING_CONTENT"}
CLASS_B = {"CREATE_NEW_PAGE", "CREATE_SUPPORTING_CONTENT", "UPDATE_EXISTING_PAGE"}
CLASS_C = {"DELETE_PAGE", "DELETE_DATA", "CHANGE_DNS", "CHANGE_DOMAIN_OWNERSHIP", "CHANGE_CREDENTIALS", "CHANGE_ACCESS", "CHANGE_SECURITY", "CHANGE_PAYMENT",
           "DESTRUCTIVE_DATABASE", "CHANGE_INFRASTRUCTURE", "OUT_OF_SCOPE", "FIX_TECHNICAL_SEO"}


def classify_action(action: str) -> str:
    if action in CLASS_C:
        return "C"
    if action in CLASS_A:
        return "A"
    if action in CLASS_B:
        return "B"
    return "C"  # unknown => fail closed


def mode_allows(mode: str, cls: str, action: str) -> tuple[bool, str]:
    if cls == "C":
        return False, f"Class C action ({action}) requires explicit human authorisation in every mode."
    if mode == "AUTONOMY_DISABLED":
        return False, "Autonomy is disabled for this tenant."
    if mode == "RECOMMEND_ONLY":
        return False, "This tenant is recommend-only."
    if action == "DISTRIBUTE_EXISTING_CONTENT" and mode != "AUTONOMOUS_DISTRIBUTION":
        return False, f"Distribution needs AUTONOMOUS_DISTRIBUTION (tenant mode is {mode})."
    if cls == "A":
        return True, f"Class A permitted in {mode}."
    if mode == "AUTONOMOUS_SEO":
        return False, "Class B needs AUTONOMOUS_CONTENT or higher."
    return True, f"Class B permitted in {mode}."


class PublishTarget(BaseModel):
    """Where SANOCEA is authorised to publish for a tenant. Absent target => the gate fails: nothing is assumed."""
    tenant_id: str
    kind: str = "website"
    base_url: str
    path_prefixes: List[str] = Field(default_factory=list)


class RollbackInfo(BaseModel):
    change_id: str
    kind: str  # "create" | "update"
    target: str
    content_sha256: str
    previous_version_ref: Optional[str] = None
    previous_content_sha256: Optional[str] = None
    reversal: str


def build_rollback(brief: SeoBrief, draft: SeoDraft, previous_version_ref: Optional[str] = None, previous_content_sha256: Optional[str] = None) -> RollbackInfo:
    """What is needed to identify and reverse this exact change. A new page is reversed by unpublishing it; an update needs the previous version."""
    body = json.dumps({"t": draft.title, "m": draft.meta_description, "s": [s.model_dump() for s in draft.sections]}, sort_keys=True)
    sha = hashlib.sha256(body.encode()).hexdigest()
    kind = "create" if brief.content_type.value == "new page" else "update"
    target = str(brief.canonical.value or brief.target.value)
    return RollbackInfo(change_id="chg_" + hashlib.sha1(f"{draft.draft_id}|{sha}".encode()).hexdigest()[:12], kind=kind, target=target, content_sha256=sha,
                        previous_version_ref=previous_version_ref, previous_content_sha256=previous_content_sha256,
                        reversal="Unpublish the new page (restore the previous sitemap/internal-link state)." if kind == "create" else "Restore the previous version identified by previous_version_ref.")


class Gate(BaseModel):
    gate: str
    passed: bool
    detail: str


class PublishDecision(BaseModel):
    draft_id: str
    tenant_id: str
    action: str
    action_class: str
    eligible: bool
    policy: str = POLICY_REF
    evaluated_at: str
    gates: List[Gate]
    blocked_by: List[str]
    rollback: Optional[RollbackInfo] = None
    status: str  # "ELIGIBLE" | "BLOCKED"


def _qa(draft: SeoDraft, name: str) -> Optional[bool]:
    for c in (draft.qa.checks if draft.qa else []):
        if c.check_name == name:
            return c.passed
    return None


def evaluate_publish_eligibility(brief: SeoBrief, draft: SeoDraft, opp_now: Dict[str, Any], autonomy_mode: str, target: Optional[PublishTarget],
                                 store: SeoContentStore, rollback: Optional[RollbackInfo] = None, now: Optional[str] = None) -> PublishDecision:
    now = now or datetime.now(timezone.utc).isoformat()
    lin = brief.lineage
    action = lin.recommended_action
    cls = classify_action(action)
    approval = opp_now.get("approval") or lin.approval
    gates: List[Gate] = []

    def g(name: str, ok: bool, detail: str) -> None:
        gates.append(Gate(gate=name, passed=bool(ok), detail=detail))

    g("evidence_backed_opportunity", bool(lin.evidence) and bool(lin.source), f"source {lin.source}")
    g("valid_decision", bool(lin.decision.get("rationale")) and lin.decision.get("action") == action, f"action {action}")
    ok_ap, why_ap = valid_approval(approval)
    g("standing_approval", ok_ap and opp_now.get("status") in ("APPROVED", "IN_PROGRESS"), f"{why_ap}; status {opp_now.get('status')}")
    overl = (brief.overlap.value or {}).get("covering_pages", []) if brief.overlap.basis == "CALCULATED" else []
    g("no_page_overlap", not (action == "CREATE_NEW_PAGE" and overl), f"{len(overl)} existing page(s) at or above {QUERY_OVERLAP_MIN:.0%} overlap" if overl else "no covering page")
    for name, label in (("evidence_grounding", "content_grounding"), ("claims_gate", "claims_gate")):
        r = _qa(draft, name)
        g(label, r is True, "passed" if r is True else "failed or not evaluated")
    if cls != "A":
        g("seo_qa", bool(draft.qa and draft.qa.passed) and draft.status == "DRAFT_READY", "; ".join(draft.qa.failure_reasons) if draft.qa and draft.qa.failure_reasons else "all QA checks passed" if draft.qa else "no QA result")
        dup = _qa(draft, "duplication")
        published = store.get_publication(draft.tenant_id, rollback.target if rollback else str(brief.canonical.value))
        g("duplicate_check", dup is True and published is None, "no near-duplicate draft and nothing already published at this target" if dup is True and published is None else "near-duplicate draft or already published")
    allowed, mode_reason = mode_allows(autonomy_mode, cls, action)
    g("tenant_authorization", allowed, mode_reason)
    tgt_ok = bool(target and target.tenant_id == draft.tenant_id and rollback and any(rollback.target.startswith(p) or rollback.target.startswith(target.base_url.rstrip("/") + p) for p in target.path_prefixes))
    g("publish_target_authorization", tgt_ok, f"target within {target.base_url}{target.path_prefixes}" if tgt_ok else "no authorised publish target covers this content")
    rb_ok = bool(rollback and rollback.content_sha256 and (rollback.kind == "create" or rollback.previous_version_ref))
    g("rollback_information", rb_ok, f"change {rollback.change_id}: {rollback.reversal}" if rb_ok else "no way to identify and reverse this change (an update needs its previous version)")
    # audit event: written BEFORE any publication would happen; its presence is itself a gate
    eid = "evt_" + hashlib.sha1(f"{draft.draft_id}|publish_eligibility|{[x.model_dump() for x in gates]}".encode()).hexdigest()[:16]
    blocked = [x.gate for x in gates if not x.passed]
    if cls == "C":
        blocked = ["class_c_requires_human"] + blocked
    store.append_audit(draft.tenant_id, eid, {"type": "PUBLISH_ELIGIBILITY_EVALUATED", "draft_id": draft.draft_id, "brief_id": brief.brief_id, "opportunity_id": lin.opportunity_id,
                                              "actor_type": "AUTONOMOUS_AGENT", "policy": POLICY_REF, "action": action, "action_class": cls, "blocked_by": blocked, "at": now,
                                              "approval_actor_type": approval.get("actorType") if approval else None})
    g("audit_event", any(e["event_id"] == eid for e in store.audit_events(draft.tenant_id)), f"event {eid}")
    blocked = ([ "class_c_requires_human"] if cls == "C" else []) + [x.gate for x in gates if not x.passed]
    d = PublishDecision(draft_id=draft.draft_id, tenant_id=draft.tenant_id, action=action, action_class=cls, eligible=not blocked, evaluated_at=now, gates=gates, blocked_by=blocked,
                        rollback=rollback, status="ELIGIBLE" if not blocked else "BLOCKED")
    store._write(store._path(draft.tenant_id, draft.draft_id).replace(".json", ".eligibility.json"), json.loads(d.model_dump_json()))
    return d
