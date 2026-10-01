"""Opportunity -> (human approval) -> brief -> draft. Stops at DRAFT: it never publishes, distributes or measures.

Approval boundary: opportunities reach AWAITING_APPROVAL through agent steps, but only an actor labelled `human:` can move
one to APPROVED (enforced by the SEO worker's lifecycle and re-checked here). Briefs and drafts are created only for
APPROVED, content-eligible opportunities. Records are idempotent and tenant-scoped."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from packages.content_engine.seo.brief import ContentWorkflowError, build_brief, content_eligibility, brief_id_for, valid_approval
from packages.content_engine.seo.draft import DraftWriter, FactsOnlyWriter
from packages.content_engine.seo.models import ApprovedFact, SeoBrief, SeoDraft, TenantProfile
from packages.content_engine.seo.qa import evaluate_draft
from packages.content_engine.seo.source import OpportunityControl
from packages.content_engine.seo.store import SeoContentStore

AGENT = "agent:content-workflow"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def submit_for_approval(opp: Dict[str, Any], control: OpportunityControl) -> Dict[str, Any]:
    """Agent steps only: DISCOVERED -> ... -> AWAITING_APPROVAL, for content-eligible opportunities. Never approves."""
    ok, why = content_eligibility(opp)
    if not ok:
        raise ContentWorkflowError("NOT_CONTENT_ELIGIBLE", why)
    path = {"DISCOVERED": ["QUALIFIED", "ACTIONABLE", "AWAITING_APPROVAL"], "QUALIFIED": ["ACTIONABLE", "AWAITING_APPROVAL"], "RESEARCHING": ["ACTIONABLE", "AWAITING_APPROVAL"],
            "ACTIONABLE": ["AWAITING_APPROVAL"], "AWAITING_APPROVAL": []}.get(opp["status"])
    if path is None:
        raise ContentWorkflowError("BAD_STATE", f"Opportunity is {opp['status']}; it cannot be submitted for approval.")
    out = opp
    for to in path:
        out = control.transition(opp["opportunityId"], to, AGENT, "Content-eligible opportunity prepared for human approval")
    return out


def approve(opp: Dict[str, Any], control: OpportunityControl, human: str, note: str) -> Dict[str, Any]:
    """The human decision. The actor must be `human:<name>`; anything else is refused before any call is made."""
    if not human or not human.startswith("human:") or len(human) <= len("human:"):
        raise ContentWorkflowError("HUMAN_REQUIRED", "Only a human actor (human:<name>) can approve; agents cannot approve their own work.")
    ok, why = content_eligibility(opp)
    if not ok:
        raise ContentWorkflowError("NOT_CONTENT_ELIGIBLE", why)
    if opp["status"] != "AWAITING_APPROVAL":
        raise ContentWorkflowError("BAD_STATE", f"Opportunity is {opp['status']}, not AWAITING_APPROVAL.")
    return control.transition(opp["opportunityId"], "APPROVED", human, note)


def create_brief(opp: Dict[str, Any], tenant: TenantProfile, pages: List[Dict[str, Any]], store: SeoContentStore, control: Optional[OpportunityControl] = None, now: Optional[str] = None) -> SeoBrief:
    """Idempotent: the same approved opportunity always yields the same brief id and returns the stored brief."""
    bid = brief_id_for(tenant.tenant_id, opp)
    existing = store.get_brief(tenant.tenant_id, bid)
    if existing:
        return existing
    brief = build_brief(opp, tenant, pages, now)
    store.save_brief(brief)
    if control:
        control.link_result(opp["opportunityId"], f"brief:{brief.brief_id}", AGENT)
    return brief


def generate_draft(brief: SeoBrief, opp_now: Dict[str, Any], facts: List[ApprovedFact], pages: List[Dict[str, Any]], store: SeoContentStore, writer: Optional[DraftWriter] = None,
                   control: Optional[OpportunityControl] = None, retry: bool = False, now: Optional[str] = None) -> SeoDraft:
    """Only while the opportunity is still human-approved. Idempotent; a failed generation is recorded, never half-saved."""
    if opp_now.get("opportunityId") != brief.lineage.opportunity_id:
        raise ContentWorkflowError("LINEAGE_MISMATCH", "The opportunity does not belong to this brief.")
    if opp_now.get("status") not in ("APPROVED", "IN_PROGRESS") or not valid_approval(opp_now.get("approval"))[0]:
        raise ContentWorkflowError("NOT_APPROVED", "A draft is only generated while a valid approval stands (human, or autonomous under the policy).")
    did = "draft_" + hashlib.sha1(brief.brief_id.encode()).hexdigest()[:12]
    prior = store.get_draft(brief.tenant_id, did)
    if prior and not (retry and prior.status != "DRAFT_READY"):
        return prior
    writer = writer or FactsOnlyWriter()
    now = now or _now()
    lineage = {"brief_id": brief.brief_id, "opportunity_id": brief.lineage.opportunity_id, "approved_by": brief.lineage.approval["by"], "approval_actor_type": brief.lineage.approval.get("actorType"), "approval_policy": brief.lineage.approval.get("policy")}
    try:
        payload = writer.write(brief, facts)
    except Exception as exc:  # recorded as a failure so it is visible and not silently retried
        failed = SeoDraft(draft_id=did, brief_id=brief.brief_id, tenant_id=brief.tenant_id, created_at=now, status="GENERATION_FAILED", writer=getattr(writer, "name", "unknown"), error=str(exc)[:300], lineage=lineage)
        store.save_draft(failed)
        return failed
    draft = SeoDraft(draft_id=did, brief_id=brief.brief_id, tenant_id=brief.tenant_id, created_at=now, status="NEEDS_REVISION", writer=writer.name, title=payload.title, meta_description=payload.meta_description,
                     sections=payload.sections, internal_links_used=payload.internal_links_used, fact_ids_used=payload.fact_ids_used, lineage=lineage)
    prior_texts = [" ".join([d.title, d.meta_description] + [p.text for s in d.sections for p in s.paragraphs]) for d in store.list_drafts(brief.tenant_id) if d.draft_id != did and d.status == "DRAFT_READY"]
    draft.qa = evaluate_draft(draft, brief, facts, pages, prior_texts)
    draft.status = "DRAFT_READY" if draft.qa.passed else "NEEDS_REVISION"
    store.save_draft(draft)
    if control and draft.status == "DRAFT_READY":
        control.link_result(brief.lineage.opportunity_id, f"draft:{draft.draft_id}", AGENT)
    return draft


def explain(store: SeoContentStore, tenant_id: str, item_id: str) -> Dict[str, Any]:
    """Answers "Why did SANOCEA create this content?" from stored records only (no model, no memory)."""
    draft = store.get_draft(tenant_id, item_id) if item_id.startswith("draft_") else None
    brief = store.get_brief(tenant_id, draft.brief_id if draft else item_id)
    if not brief:
        raise ContentWorkflowError("NOT_FOUND", "No such brief or draft for this tenant.")
    l = brief.lineage
    fields = {k: getattr(brief, k).basis for k in ("content_type", "target", "intent", "audience", "existing_page_assessment", "overlap", "proposed_title", "proposed_meta_description", "primary_questions", "supporting_questions", "entities", "research_requirements", "schema_opportunity", "canonical")}
    chain = {
        "opportunity": {"type": l.type, "target": l.target, "detected_at": l.detected_at, "source": l.source, "reason": l.reason},
        "evidence": l.evidence,
        "decision": l.decision,
        "approval": l.approval,  # includes actorType (HUMAN | AUTONOMOUS_AGENT), policy and the evidence-backed reason
        "brief": {"brief_id": brief.brief_id, "created_at": brief.created_at, "field_basis": fields, "not_available": brief.not_available},
        "draft": ({"draft_id": draft.draft_id, "status": draft.status, "writer": draft.writer, "fact_ids_used": draft.fact_ids_used, "qa_passed": bool(draft.qa and draft.qa.passed)} if draft else None),
    }
    why = (f"SANOCEA observed {l.type} for {l.target} (source {l.source}, detected {l.detected_at}). Recommended action: {l.recommended_action} ({l.decision.get('rationale')}). "
           f"It was approved by {l.approval['by']} ({l.approval.get('actorType')}, policy {l.approval.get('policy')}) at {l.approval['at']}: {l.approval.get('reason')} The brief {brief.brief_id} was built from that evidence" + (f" and the draft {draft.draft_id} was written by {draft.writer} using only approved facts {', '.join(draft.fact_ids_used)}." if draft else "."))
    return {"why": why, "chain": chain}


def authorize_autonomously(opp: Dict[str, Any], control: OpportunityControl) -> Dict[str, Any]:
    """Qualify (agent steps), then ask the worker's policy to authorise. Returns the worker's decision with every gate.
    Never writes an approval itself: only the policy can, and it records AUTONOMOUS_AGENT, never a human label."""
    oid = opp["opportunityId"]
    if opp.get("status") not in ("AWAITING_APPROVAL", "APPROVED", "IN_PROGRESS"):  # already-approved work is returned as such (idempotent)
        submit_for_approval(opp, control)
    return control.authorize(oid)


def human_override(opp: Dict[str, Any], control: OpportunityControl, human: str, note: str) -> Dict[str, Any]:
    """A human halts work the policy approved (or declines to approve). Recorded as HUMAN; the autonomous approval stays on record."""
    if not human or not human.startswith("human:") or len(human) <= len("human:"):
        raise ContentWorkflowError("HUMAN_REQUIRED", "A human override must be made by a human actor (human:<name>).")
    if opp.get("status") not in ("AWAITING_APPROVAL", "APPROVED", "IN_PROGRESS"):
        raise ContentWorkflowError("BAD_STATE", f"Opportunity is {opp.get('status')}; there is nothing to override.")
    return control.transition(opp["opportunityId"], "REJECTED", human, note)
