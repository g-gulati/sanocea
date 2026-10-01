"""Autonomy policy for the SEO content workflow: autonomous approval records, publish eligibility gates, Class C prohibition,
rollback information, human override. Evaluation only: no publisher exists and nothing is published."""

import json
import os
import shutil
import subprocess

import pytest

from packages.content_engine.seo import workflow as wf
from packages.content_engine.seo.brief import ContentWorkflowError, build_brief, valid_approval
from packages.content_engine.seo.models import ApprovedFact, TenantProfile
from packages.content_engine.seo.policy import PublishTarget, build_rollback, classify_action, evaluate_publish_eligibility, mode_allows
from packages.content_engine.seo.source import OpportunityControl
from packages.content_engine.seo.store import SeoContentStore

TENANT = TenantProfile(tenant_id="sanocea", brand="SANOCEA", domain="www.sanocea.com", audience="Operations leads at multichannel ecommerce brands")
PAGES = [{"url": "https://www.sanocea.com/", "title": "SANOCEA", "h1Text": "Ecommerce operations", "staticWords": 400}]
FACTS = [ApprovedFact(id="f1", text="Marketplace payouts rarely match order totals because fees, returns and delays are netted off separately.", source="owner"),
         ApprovedFact(id="f2", text="Payout reconciliation compares each payout line with its order before the books are closed.", source="owner")]
AUTO = {"by": "autonomous:sanocea-autonomy-policy@1.0.0", "at": "2026-10-02T00:00:00Z", "actorType": "AUTONOMOUS_AGENT", "policy": "sanocea-autonomy-policy@1.0.0",
        "reason": "All authorisation gates passed under sanocea-autonomy-policy@1.0.0: Class B permitted in AUTONOMOUS_CONTENT.", "actionClass": "B", "approvedAction": "CREATE_NEW_PAGE"}
HUMAN = {"by": "human:asha", "at": "2026-10-02T00:00:00Z", "actorType": "HUMAN", "policy": "human-manual", "reason": "ok", "actionClass": "B", "approvedAction": "CREATE_NEW_PAGE"}
TARGET = PublishTarget(tenant_id="sanocea", base_url="https://www.sanocea.com", path_prefixes=["/"])


def opp(action="CREATE_NEW_PAGE", approval=AUTO, status="APPROVED", target="marketplace payouts mismatch", oid="OPP-1", type_="QUERY_PAGE_MATCH_GAP", ev=None):
    ev = ev if ev is not None else {"query": target, "impressions": 80, "clicks": 0, "bestMatchUrl": PAGES[0]["url"], "bestMatchOverlap": 0.0, "pagesCompared": 1, "limitation": "Only audited pages were compared."}
    return {"opportunityId": oid, "type": type_, "target": target, "status": status, "source": "[OBSERVED: PERSISTED GSC SNAPSHOT]", "reason": "r", "detectedAt": "2026-10-01T00:00:00Z",
            "recommendedAction": action, "evidence": ev, "decision": {"action": action, "rationale": "No audited page shares the query's words.", "checks": ["compared"], "requiresApproval": True}, "approval": approval}


class Ctl(OpportunityControl):
    def __init__(self):
        self.calls = []
        super().__init__(post_json=lambda p, b: (self.calls.append((p, b)) or {"ok": True}))


class _W:
    name = "w"
    def __init__(self, text=None, meta=None):
        self.text, self.meta = text, meta
    def write(self, brief, facts):
        from packages.content_engine.seo.draft import DraftPayload, FactsOnlyWriter
        from packages.content_engine.seo.models import DraftParagraph, DraftSection
        if self.text is None:
            return FactsOnlyWriter().write(brief, facts)
        return DraftPayload("Marketplace Payouts | SANOCEA", self.meta or facts[0].text, [DraftSection(level=1, heading="Marketplace Payouts", paragraphs=[DraftParagraph(text=self.text, fact_ids=["f1"])])], [], ["f1"])


def ready(tmp_path, approval=AUTO, **kw):
    st = SeoContentStore(str(tmp_path))
    o = opp(approval=approval, **kw)
    b = wf.create_brief(o, TENANT, PAGES, st)
    d = wf.generate_draft(b, o, FACTS, PAGES, st)
    return st, o, b, d


def decide(st, b, d, o, mode="AUTONOMOUS_CONTENT", target=TARGET, rb="auto", now="2026-10-02T01:00:00Z"):
    rb = build_rollback(b, d) if rb == "auto" else rb
    return evaluate_publish_eligibility(b, d, o, mode, target, st, rb, now)


# ── policy parity and classes ────────────────────────────────────────────────

def test_python_policy_matches_the_workers_policy():
    dist = "packages/seo-stack/dist/src/opportunities/autonomyPolicy.js"
    if not shutil.which("node") or not os.path.exists(dist):
        pytest.skip("seo-stack is not built")
    acts = ["IMPROVE_TITLE_META", "ADD_INTERNAL_LINKS", "IMPROVE_SCHEMA", "DISTRIBUTE_EXISTING_CONTENT", "CREATE_NEW_PAGE", "CREATE_SUPPORTING_CONTENT", "UPDATE_EXISTING_PAGE",
            "FIX_TECHNICAL_SEO", "DELETE_PAGE", "CHANGE_DNS", "CHANGE_CREDENTIALS", "NO_ACTION", "WHATEVER"]
    modes = ["AUTONOMY_DISABLED", "RECOMMEND_ONLY", "AUTONOMOUS_SEO", "AUTONOMOUS_CONTENT", "AUTONOMOUS_DISTRIBUTION"]
    js = f"import('./{dist}').then(m=>{{const o={{}};for(const a of {json.dumps(acts)}){{o[a]=m.classifyAction(a);for(const md of {json.dumps(modes)})o[a+'|'+md]=m.modeAllows(md,m.classifyAction(a),a).allowed}}console.log(JSON.stringify(o))}})"
    ts = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    for a in acts:
        assert ts[a] == classify_action(a), a
        for md in modes:
            assert ts[f"{a}|{md}"] == mode_allows(md, classify_action(a), a)[0], (a, md)


# ── approval records: autonomous is accepted, mislabelled is refused ──────────

def test_autonomous_approval_drives_brief_and_draft_with_correct_attribution(tmp_path):
    st, o, b, d = ready(tmp_path)
    assert b.lineage.approval["actorType"] == "AUTONOMOUS_AGENT" and b.lineage.approval["by"].startswith("autonomous:")
    assert d.lineage["approval_actor_type"] == "AUTONOMOUS_AGENT" and d.lineage["approval_policy"] == "sanocea-autonomy-policy@1.0.0"
    why = wf.explain(st, "sanocea", d.draft_id)
    assert "AUTONOMOUS_AGENT" in why["why"] and "sanocea-autonomy-policy@1.0.0" in why["why"] and "All authorisation gates passed" in why["why"]
    assert "human" not in why["why"].lower(), "an autonomous decision is never described as human"
    assert why["chain"]["approval"]["actorType"] == "AUTONOMOUS_AGENT"


@pytest.mark.parametrize("bad", [
    dict(AUTO, by="human:asha"),                       # autonomous record claiming a human identity
    dict(HUMAN, by="autonomous:sanocea-autonomy-policy@1.0.0"),  # human record under an autonomous identity
    dict(AUTO, policy=""), dict(AUTO, actorType="UNKNOWN"), dict(HUMAN, by="human:"), dict(AUTO, by="agent:x"), None])
def test_mislabelled_or_incomplete_approvals_are_refused(bad, tmp_path):
    assert valid_approval(bad)[0] is False
    with pytest.raises(ContentWorkflowError) as e:
        wf.create_brief(opp(approval=bad), TENANT, PAGES, SeoContentStore(str(tmp_path)))
    assert e.value.code == "NOT_APPROVED"
    assert valid_approval(AUTO)[0] and valid_approval(HUMAN)[0]


def test_authorize_autonomously_runs_agent_steps_then_asks_the_policy_and_never_writes_an_approval(tmp_path):
    c = Ctl()
    wf.authorize_autonomously(dict(opp(approval=None), status="DISCOVERED"), c)
    assert [(p, b.get("to")) for p, b in c.calls] == [("/opportunities/transition", "QUALIFIED"), ("/opportunities/transition", "ACTIONABLE"), ("/opportunities/transition", "AWAITING_APPROVAL"), ("/opportunities/authorize", None)]
    assert not any(b.get("to") == "APPROVED" for _, b in c.calls)


def test_human_override_requires_a_human_and_halts_work():
    c = Ctl()
    for who in ["agent:x", "autonomous:sanocea-autonomy-policy@1.0.0", "", "human:", None]:
        with pytest.raises(ContentWorkflowError) as e:
            wf.human_override(opp(), c, who, "stop")
        assert e.value.code == "HUMAN_REQUIRED", who
    assert c.calls == []
    wf.human_override(opp(), c, "human:asha", "Stop")
    assert c.calls[-1][1] == {"opportunityId": "OPP-1", "to": "REJECTED", "actor": "human:asha", "note": "Stop"}
    with pytest.raises(ContentWorkflowError):
        wf.human_override(opp(status="COMPLETED"), c, "human:asha", "x")


# ── publish eligibility ──────────────────────────────────────────────────────

def test_all_class_b_gates_pass_means_eligible_and_an_audit_event_exists_once(tmp_path):
    st, o, b, d = ready(tmp_path)
    assert d.status == "DRAFT_READY"
    r1 = decide(st, b, d, o); r2 = decide(st, b, d, o)
    assert r1.eligible and r1.status == "ELIGIBLE" and r1.action_class == "B" and r1.blocked_by == []
    assert {g.gate for g in r1.gates} >= {"evidence_backed_opportunity", "valid_decision", "standing_approval", "no_page_overlap", "content_grounding", "claims_gate", "seo_qa", "duplicate_check", "tenant_authorization", "publish_target_authorization", "rollback_information", "audit_event"}
    ev = [e for e in st.audit_events("sanocea") if e["type"] == "PUBLISH_ELIGIBILITY_EVALUATED"]
    assert len(ev) == 1, "re-evaluating the same state does not duplicate the audit event"
    assert ev[0]["actor_type"] == "AUTONOMOUS_AGENT" and ev[0]["approval_actor_type"] == "AUTONOMOUS_AGENT" and ev[0]["policy"] == "sanocea-autonomy-policy@1.0.0"
    assert r1.rollback.kind == "create" and "Unpublish" in r1.rollback.reversal and r1.rollback.change_id == r2.rollback.change_id
    assert os.path.exists(os.path.join(str(tmp_path), "sanocea", d.draft_id + ".eligibility.json"))


@pytest.mark.parametrize("mode,blocked", [("RECOMMEND_ONLY", "tenant_authorization"), ("AUTONOMY_DISABLED", "tenant_authorization"), ("AUTONOMOUS_SEO", "tenant_authorization")])
def test_policy_denial_by_tenant_mode_blocks_publication(mode, blocked, tmp_path):
    st, o, b, d = ready(tmp_path)
    r = decide(st, b, d, o, mode=mode)
    assert r.eligible is False and blocked in r.blocked_by and r.status == "BLOCKED"


def test_failed_qa_failed_claims_failed_grounding_and_duplicates_each_block(tmp_path):
    st = SeoContentStore(str(tmp_path / "q"))
    o = opp(); b = wf.create_brief(o, TENANT, PAGES, st)
    d = wf.generate_draft(b, o, FACTS, PAGES, st, writer=_W("Our customers saw a 47% reduction in reconciliation time."))
    r = decide(st, b, d, o)
    assert not r.eligible and {"seo_qa"} <= set(r.blocked_by)
    st2 = SeoContentStore(str(tmp_path / "c"))
    b2 = wf.create_brief(o, TENANT, PAGES, st2)
    d2 = wf.generate_draft(b2, o, FACTS, PAGES, st2, writer=_W("Magically automate everything with guaranteed results."))
    r2 = decide(st2, b2, d2, o)
    assert not r2.eligible and "claims_gate" in r2.blocked_by
    st3 = SeoContentStore(str(tmp_path / "g"))
    b3 = wf.create_brief(o, TENANT, PAGES, st3)
    d3 = wf.generate_draft(b3, o, FACTS, PAGES, st3, writer=_W("Payouts are reconciled by hand every day."))
    r3 = decide(st3, b3, d3, o)
    assert not r3.eligible and "content_grounding" in r3.blocked_by
    # near-duplicate of an earlier ready draft
    st4, o4, b4, d4 = ready(tmp_path / "d")
    o5 = opp(target="marketplace payouts mismatches", oid="OPP-5")
    b5 = wf.create_brief(o5, TENANT, PAGES, st4); d5 = wf.generate_draft(b5, o5, FACTS, PAGES, st4)
    r5 = decide(st4, b5, d5, o5)
    assert not r5.eligible and "duplicate_check" in r5.blocked_by


def test_a_blocked_draft_is_never_published_and_the_decision_says_why(tmp_path):
    st, o, b, d = ready(tmp_path)
    r = decide(st, b, d, o, mode="RECOMMEND_ONLY")
    assert r.eligible is False and r.status == "BLOCKED"
    assert any(g.gate == "tenant_authorization" and not g.passed and "recommend-only" in g.detail for g in r.gates)
    assert st.get_publication("sanocea", r.rollback.target) is None


def test_publish_target_must_exist_belong_to_the_tenant_and_cover_the_content(tmp_path):
    st, o, b, d = ready(tmp_path)
    assert "publish_target_authorization" in decide(st, b, d, o, target=None).blocked_by
    assert "publish_target_authorization" in decide(st, b, d, o, target=PublishTarget(tenant_id="acme", base_url="https://acme.test", path_prefixes=["/"])).blocked_by, "another tenant's target"
    assert "publish_target_authorization" in decide(st, b, d, o, target=PublishTarget(tenant_id="sanocea", base_url="https://www.sanocea.com", path_prefixes=["/blog/"])).blocked_by, "outside the configured scope"
    assert decide(st, b, d, o).eligible


def test_approval_withdrawn_or_overlap_found_blocks(tmp_path):
    st, o, b, d = ready(tmp_path)
    assert "standing_approval" in decide(st, b, d, dict(o, status="REJECTED")).blocked_by, "a human override stops publication"
    assert "standing_approval" in decide(st, b, d, dict(o, approval=dict(AUTO, by="human:asha"))).blocked_by, "mislabelled approval"
    b_over = b.model_copy(update={"overlap": b.overlap.model_copy(update={"value": {"covering_pages": [{"url": "https://www.sanocea.com/x", "overlap": 0.8}], "ranked": []}})})
    assert "no_page_overlap" in decide(st, b_over, d, o).blocked_by


# ── Class C ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("action", ["DELETE_PAGE", "DELETE_DATA", "CHANGE_DNS", "CHANGE_DOMAIN_OWNERSHIP", "CHANGE_CREDENTIALS", "CHANGE_ACCESS", "CHANGE_PAYMENT", "DESTRUCTIVE_DATABASE", "CHANGE_INFRASTRUCTURE", "OUT_OF_SCOPE", "FIX_TECHNICAL_SEO", "SOMETHING_NEW"])
def test_class_c_is_never_eligible_even_if_every_other_gate_passes(action, tmp_path):
    st, o, b, d = ready(tmp_path)
    forged = b.model_copy(update={"lineage": b.lineage.model_copy(update={"recommended_action": action, "decision": dict(b.lineage.decision, action=action)})})
    r = decide(st, forged, d, dict(o, recommendedAction=action), mode="AUTONOMOUS_DISTRIBUTION")
    assert r.eligible is False and r.action_class == "C" and r.blocked_by[0] == "class_c_requires_human"


# ── rollback, duplicate publication, tenant isolation ────────────────────────

def test_rollback_information_identifies_the_change_and_updates_need_a_previous_version(tmp_path):
    st, o, b, d = ready(tmp_path)
    rb = build_rollback(b, d)
    assert rb.change_id.startswith("chg_") and len(rb.content_sha256) == 64 and rb.kind == "create" and rb.previous_version_ref is None
    d2 = d.model_copy(update={"title": d.title + " v2"})
    assert build_rollback(b, d2).content_sha256 != rb.content_sha256 and build_rollback(b, d2).change_id != rb.change_id
    upd_b = b.model_copy(update={"content_type": b.content_type.model_copy(update={"value": "update to an existing page"})})
    no_prev = build_rollback(upd_b, d)
    assert no_prev.kind == "update"
    assert "rollback_information" in decide(st, upd_b, d, o, rb=no_prev).blocked_by, "an update with no previous version cannot be reversed"
    with_prev = build_rollback(upd_b, d, previous_version_ref="rev-41", previous_content_sha256="a" * 64)
    assert "rollback_information" not in decide(st, upd_b, d, o, rb=with_prev).blocked_by
    assert "rollback_information" in decide(st, b, d, o, rb=None).blocked_by


def test_duplicate_publication_is_blocked_and_the_ledger_is_write_once(tmp_path):
    st, o, b, d = ready(tmp_path)
    r = decide(st, b, d, o)
    assert r.eligible
    st.record_publication("sanocea", r.rollback.target, {"draft_id": d.draft_id, "change_id": r.rollback.change_id})
    again = decide(st, b, d, o)
    assert not again.eligible and "duplicate_check" in again.blocked_by
    with pytest.raises(FileExistsError):
        st.record_publication("sanocea", r.rollback.target, {"draft_id": "x"})


def test_tenant_isolation_audit_and_ledger_are_per_tenant(tmp_path):
    st, o, b, d = ready(tmp_path)
    decide(st, b, d, o)
    assert st.audit_events("sanocea") and st.audit_events("acme") == []
    st.record_publication("sanocea", "/marketplace-payouts-mismatch", {"x": 1})
    assert st.get_publication("acme", "/marketplace-payouts-mismatch") is None
    for bad in ["../sanocea", "A/b", ""]:
        with pytest.raises(ValueError):
            st.audit_events(bad)
