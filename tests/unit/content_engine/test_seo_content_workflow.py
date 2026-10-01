"""SEO content workflow: opportunity -> human approval -> brief -> draft. Fixture-driven (no live content opportunity exists:
every real opportunity today is technical, which is itself asserted below)."""

import json
import os
import shutil
import subprocess

import pytest

from packages.content_engine.seo import workflow as wf
from packages.content_engine.seo.brief import ContentWorkflowError, build_brief, content_eligibility
from packages.content_engine.seo.draft import FactsOnlyWriter, WriterError
from packages.content_engine.seo.models import ApprovedFact, TenantProfile
from packages.content_engine.seo.source import OpportunityControl, OpportunitySource
from packages.content_engine.seo.store import SeoContentStore

TENANT = TenantProfile(tenant_id="sanocea", brand="SANOCEA", domain="www.sanocea.com", audience="Operations leads at multichannel ecommerce brands")
PAGES = [
    {"url": "https://www.sanocea.com/", "title": "SANOCEA", "h1Text": "AI-assisted ecommerce operations", "staticWords": 21},
    {"url": "https://www.sanocea.com/solutions/marketplace-reconciliation", "title": "", "h1Text": "", "staticWords": 0},
]
FACTS = [
    ApprovedFact(id="f1", text="Marketplace payouts rarely match order totals because fees, returns and delays are netted off separately.", source="owner: operations notes"),
    ApprovedFact(id="f2", text="Reconciliation compares each payout line with its order before the books are closed.", source="owner: operations notes"),
]


def opp(type_="QUERY_PAGE_MATCH_GAP", action="CREATE_SEO_PAGE", status="APPROVED", by="human:asha", target="amazon payout mismatch", oid="OPP-1", ev=None):
    ev = ev if ev is not None else {"query": target, "impressions": 80, "clicks": 0, "bestMatchUrl": PAGES[0]["url"], "bestMatchOverlap": 0.0, "pagesCompared": 2, "limitation": "Only audited pages were compared."}
    return {"opportunityId": oid, "type": type_, "target": target, "status": status, "source": "[OBSERVED: PERSISTED GSC SNAPSHOT]", "reason": "Search Console reports 80 impressions.",
            "detectedAt": "2026-10-01T00:00:00Z", "recommendedAction": action, "evidence": ev,
            "decision": {"action": action, "rationale": "No audited page shares the query's words.", "checks": ["compared"], "requiresApproval": True},
            "approval": ({"by": by, "at": "2026-10-01T01:00:00Z", "actorType": "HUMAN" if by.startswith("human:") else "AUTONOMOUS_AGENT" if by.startswith("autonomous:") else "UNKNOWN", "policy": "human-manual" if by.startswith("human:") else "p@1", "reason": "approved"} if by else None)}


class FakeControl(OpportunityControl):
    def __init__(self):
        self.calls = []
        super().__init__(post_json=self._rec)

    def _rec(self, path, body):
        self.calls.append((path, body))
        return {"status": body.get("to", "APPROVED")}


@pytest.fixture()
def store(tmp_path):
    return SeoContentStore(str(tmp_path))


# ── eligibility ───────────────────────────────────────────────────────────────

def test_only_content_opportunities_are_eligible_and_every_real_technical_one_is_refused():
    assert content_eligibility(opp())[0] is True
    assert content_eligibility(opp("HIGH_IMPRESSIONS_LOW_CTR", "UPDATE_TITLE_META", target="https://www.sanocea.com/", ev={"page": "https://www.sanocea.com/"}))[0] is True
    for t in ["SERVER_RENDERED_CONTENT_GAP", "MISSING_STATIC_H1", "SITEMAP_URL_REDIRECTS", "GOOGLE_INDEX_STATUS_ISSUE", "SITEMAP_REPORTED_ISSUES"]:
        for a in ["FIX_TECHNICAL_SEO", "CREATE_SEO_PAGE", "UPDATE_EXISTING_PAGE"]:
            assert content_eligibility(opp(t, a))[0] is False, (t, a)
        with pytest.raises(ContentWorkflowError) as e:
            build_brief(opp(t, "FIX_TECHNICAL_SEO"), TENANT, PAGES)
        assert e.value.code == "NOT_CONTENT_ELIGIBLE"
    assert content_eligibility(opp("QUERY_PAGE_MATCH_GAP", "FIX_TECHNICAL_SEO"))[0] is False


def test_python_eligibility_matches_the_workers_rule():
    """Parity with the TypeScript rule (opportunityEngine.ts) so the two cannot drift."""
    dist = "packages/seo-stack/dist/src/opportunities/opportunityEngine.js"
    if not shutil.which("node") or not os.path.exists(dist):
        pytest.skip("seo-stack is not built")
    types = ["SERVER_RENDERED_CONTENT_GAP", "MISSING_STATIC_H1", "SITEMAP_URL_REDIRECTS", "GOOGLE_INDEX_STATUS_ISSUE", "SITEMAP_REPORTED_ISSUES", "HIGH_IMPRESSIONS_LOW_CTR", "QUERY_PAGE_MATCH_GAP"]
    acts = ["CREATE_SEO_PAGE", "CREATE_SUPPORTING_CONTENT", "UPDATE_EXISTING_PAGE", "UPDATE_TITLE_META", "FIX_TECHNICAL_SEO", "NO_ACTION", "ADD_INTERNAL_LINK"]
    js = f"import('./{dist}').then(m=>{{const o={{}};for(const t of {json.dumps(types)})for(const a of {json.dumps(acts)})o[t+'|'+a]=m.contentEligibility(t,a).eligible;console.log(JSON.stringify(o))}})"
    ts = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    for t in types:
        for a in acts:
            assert ts[f"{t}|{a}"] == content_eligibility(opp(t, a))[0], (t, a)


# ── human approval ────────────────────────────────────────────────────────────

def test_agents_cannot_approve_and_nothing_is_called_when_they_try():
    c = FakeControl()
    for who in ["agent:content-workflow", "system", "", "human:", "human_operator", None]:
        with pytest.raises(ContentWorkflowError) as e:
            wf.approve(opp(status="AWAITING_APPROVAL", by=None), c, who, "x")
        assert e.value.code == "HUMAN_REQUIRED", who
    assert c.calls == [], "a refused approval must not reach the worker"
    wf.approve(opp(status="AWAITING_APPROVAL", by=None), c, "human:asha", "ok")
    assert c.calls[-1][1]["to"] == "APPROVED" and c.calls[-1][1]["actor"] == "human:asha"


def test_submit_for_approval_only_runs_agent_steps_and_never_approves():
    c = FakeControl()
    wf.submit_for_approval(opp(status="DISCOVERED", by=None), c)
    assert [b["to"] for _, b in c.calls] == ["QUALIFIED", "ACTIONABLE", "AWAITING_APPROVAL"]
    assert all(b["actor"].startswith("agent:") for _, b in c.calls)
    with pytest.raises(ContentWorkflowError):
        wf.submit_for_approval(opp("MISSING_STATIC_H1", "FIX_TECHNICAL_SEO", status="DISCOVERED", by=None), c)
    with pytest.raises(ContentWorkflowError):
        wf.approve(opp(status="DISCOVERED", by=None), c, "human:asha", "skipped the queue")


@pytest.mark.parametrize("o", [opp(status="AWAITING_APPROVAL", by=None), opp(by="agent:x"), opp(by=None), opp(status="REJECTED")])
def test_no_brief_without_a_standing_human_approval(o, store):
    with pytest.raises(ContentWorkflowError) as e:
        wf.create_brief(o, TENANT, PAGES, store)
    assert e.value.code == "NOT_APPROVED"


# ── brief: provenance, no invented metrics ────────────────────────────────────

def test_brief_is_fully_sourced_and_invents_no_metric(store):
    c = FakeControl()
    b = wf.create_brief(opp(), TENANT, PAGES, store, c, now="2026-10-01T02:00:00Z")
    assert b.lineage.evidence["query"] == "amazon payout mismatch" and b.lineage.approval["by"] == "human:asha"
    assert b.target.basis == "OBSERVED" and b.content_type.basis == "CALCULATED"
    assert b.proposed_title.value == "Amazon Payout Mismatch | SANOCEA" and b.proposed_title.basis == "GENERATED_RECOMMENDATION"
    assert b.proposed_meta_description.value is None and b.proposed_meta_description.basis == "REQUIRES_VERIFICATION"
    assert b.intent.basis == "NOT_AVAILABLE" and b.supporting_questions.basis == "NOT_AVAILABLE"
    assert b.audience.basis == "EDITORIAL"
    assert "search volume" in b.not_available and "AI citation rate" in b.not_available
    assert b.schema_opportunity.value["excluded"] == ["FAQPage", "HowTo"]
    assert b.research_requirements.basis == "REQUIRES_VERIFICATION" and b.claims_requiring_verification
    dump = b.model_dump_json().lower()
    for banned in ["search_volume", "monthly searches", "expected traffic", "citability", "priority", "seo score"]:
        assert banned not in dump, banned
    assert c.calls[-1][0] == "/opportunities/link-result" and c.calls[-1][1]["ref"] == f"brief:{b.brief_id}"


def test_intent_is_only_inferred_from_an_explicit_lexical_cue(store):
    b = build_brief(opp(target="how to reconcile amazon payouts"), TENANT, PAGES)
    assert b.intent.basis == "INFERRED" and b.intent.value == "how-to guidance" and "lexical cue" in b.intent.note.lower()
    assert build_brief(opp(target="amazon payout mismatch"), TENANT, PAGES).intent.basis == "NOT_AVAILABLE"


def test_internal_links_each_carry_a_semantic_justification():
    b = build_brief(opp(target="marketplace fee reporting guide"), TENANT, [PAGES[0], dict(PAGES[1], title="Marketplace reconciliation")])
    assert b.internal_links, "a page that shares words must be linkable"
    assert all(l.justification.startswith("Shares the words:") for l in b.internal_links)
    assert PAGES[0]["url"] not in [l.url for l in b.internal_links]


def test_title_meta_brief_for_an_existing_page_states_what_is_missing_instead_of_guessing(store):
    o = opp("HIGH_IMPRESSIONS_LOW_CTR", "UPDATE_TITLE_META", target="https://www.sanocea.com/", ev={"page": "https://www.sanocea.com/", "impressions": 400, "clicks": 2, "ctr": 0.005})
    b = wf.create_brief(o, TENANT, PAGES, store)
    assert b.existing_page_assessment.basis == "OBSERVED" and b.existing_page_assessment.value["current_h1"] == "AI-assisted ecommerce operations"
    assert b.proposed_title.value is None and b.proposed_title.basis == "REQUIRES_VERIFICATION"
    assert b.overlap.basis == "NOT_AVAILABLE" and b.primary_questions.basis == "NOT_AVAILABLE"
    assert b.canonical.value == "https://www.sanocea.com/"


# ── duplicate / cannibalisation, idempotency, tenant isolation ───────────────

def test_new_page_is_refused_when_an_existing_page_already_covers_the_query():
    covered = [dict(PAGES[1], title="Amazon payout mismatch explained", h1Text="Amazon payout mismatch")]
    with pytest.raises(ContentWorkflowError) as e:
        build_brief(opp(), TENANT, PAGES + covered)
    assert e.value.code == "CANNIBALIZATION_RISK" and "update it instead" in str(e.value)
    assert build_brief(opp(action="UPDATE_EXISTING_PAGE"), TENANT, PAGES + covered).content_type.value == "update to an existing page"


def test_brief_and_draft_are_idempotent(store):
    c = FakeControl()
    b1 = wf.create_brief(opp(), TENANT, PAGES, store, c, now="2026-10-01T02:00:00Z")
    b2 = wf.create_brief(opp(), TENANT, PAGES, store, c, now="2026-10-02T09:00:00Z")
    assert b1.brief_id == b2.brief_id and b2.created_at == "2026-10-01T02:00:00Z"
    assert len([x for x in c.calls if x[0].endswith("link-result")]) == 1, "the second call links nothing again"
    d1 = wf.generate_draft(b1, opp(), FACTS, PAGES, store, now="2026-10-01T03:00:00Z")
    d2 = wf.generate_draft(b1, opp(), FACTS, PAGES, store, now="2026-10-05T03:00:00Z")
    assert d1.draft_id == d2.draft_id and d2.created_at == "2026-10-01T03:00:00Z"
    assert len(store.list_drafts("sanocea")) == 1


def test_tenant_isolation(store):
    b = wf.create_brief(opp(), TENANT, PAGES, store)
    other = TenantProfile(tenant_id="acme", brand="ACME", domain="acme.test", audience="x")
    assert store.get_brief("acme", b.brief_id) is None
    assert store.list_drafts("acme") == []
    ob = wf.create_brief(opp(), other, PAGES, store)
    assert ob.brief_id == wf.brief_id_for("acme", opp()) and store.get_brief("sanocea", ob.brief_id) is None
    for bad in ["../sanocea", "A/b", "", "x" * 80]:
        with pytest.raises(ValueError):
            store.get_brief(bad, b.brief_id)
    with pytest.raises(ContentWorkflowError) as nf:
        wf.explain(store, "acme", "brief_000000000000")
    assert nf.value.code == "NOT_FOUND"
    with pytest.raises(ContentWorkflowError):
        wf.explain(SeoContentStore(store.root), "nobody", b.brief_id)


# ── draft generation and QA ───────────────────────────────────────────────────

def test_draft_uses_only_approved_facts_and_passes_qa_with_no_score(store):
    b = wf.create_brief(opp(target="marketplace payouts mismatch"), TENANT, PAGES, store)
    d = wf.generate_draft(b, opp(target="marketplace payouts mismatch"), FACTS, PAGES, store)
    assert d.status == "DRAFT_READY", d.qa.failure_reasons if d.qa else d.error
    assert set(d.fact_ids_used) <= {"f1", "f2"}
    paragraphs = [p for s in d.sections for p in s.paragraphs]
    assert paragraphs and all(p.fact_ids and p.text in {f.text for f in FACTS} for p in paragraphs), "no sentence exists that is not an approved fact"
    assert d.lineage == {"brief_id": b.brief_id, "opportunity_id": "OPP-1", "approved_by": "human:asha", "approval_actor_type": "HUMAN", "approval_policy": "human-manual"}
    names = {c.check_name for c in d.qa.checks}
    assert {"evidence_grounding", "claims_gate", "no_unsourced_numbers", "duplication", "cannibalization", "intended_audience", "search_intent", "internal_links", "title", "meta_description", "heading_structure"} <= names
    assert not any(k in d.model_dump_json().lower() for k in ["seo_score", "citability", "priority"])


def test_draft_is_refused_unless_a_human_approval_still_stands(store):
    b = wf.create_brief(opp(), TENANT, PAGES, store)
    for o in [opp(by="agent:x"), opp(status="REJECTED"), opp(status="AWAITING_APPROVAL", by=None)]:
        with pytest.raises(ContentWorkflowError) as e:
            wf.generate_draft(b, o, FACTS, PAGES, store)
        assert e.value.code == "NOT_APPROVED"
    with pytest.raises(ContentWorkflowError) as e:
        wf.generate_draft(b, opp(oid="OPP-OTHER"), FACTS, PAGES, store)
    assert e.value.code == "LINEAGE_MISMATCH"


def test_failed_generation_is_recorded_not_half_saved_and_retry_is_explicit(store):
    b = wf.create_brief(opp(), TENANT, PAGES, store)
    d = wf.generate_draft(b, opp(), [], PAGES, store)  # no approved facts: the writer refuses to invent
    assert d.status == "GENERATION_FAILED" and "No approved fact" in d.error and d.sections == [] and d.qa is None
    again = wf.generate_draft(b, opp(), FACTS, PAGES, store)
    assert again.status == "GENERATION_FAILED", "not silently retried"
    ok = wf.generate_draft(b, opp(), FACTS, PAGES, store, retry=True)
    assert ok.draft_id == d.draft_id and ok.status in ("DRAFT_READY", "NEEDS_REVISION") and ok.error is None

    class Boom:
        name = "boom"
        def write(self, brief, facts):
            raise RuntimeError("provider timeout")
    b2 = wf.create_brief(opp(target="gst invoice format", oid="OPP-2"), TENANT, PAGES, store)
    f = wf.generate_draft(b2, opp(target="gst invoice format", oid="OPP-2"), FACTS, PAGES, store, writer=Boom())
    assert f.status == "GENERATION_FAILED" and f.error == "provider timeout" and f.writer == "boom"


class _Fabricator:
    name = "fabricator"
    def __init__(self, text, fact_ids=("f1",)):
        self.text, self.fact_ids = text, list(fact_ids)
    def write(self, brief, facts):
        from packages.content_engine.seo.draft import DraftPayload
        from packages.content_engine.seo.models import DraftParagraph, DraftSection
        title = "Marketplace Payouts | SANOCEA"
        return DraftPayload(title, "Marketplace payouts rarely match order totals because fees, returns and delays are netted off separately.",
                            [DraftSection(level=1, heading="Marketplace Payouts", paragraphs=[DraftParagraph(text=self.text, fact_ids=self.fact_ids)])], [], self.fact_ids)


@pytest.mark.parametrize("text,check", [
    ("Our customers saw a 47% reduction in reconciliation time.", "no_unsourced_numbers"),
    ("Magically automate everything with guaranteed results.", "claims_gate"),
])
def test_qa_blocks_fabricated_numbers_and_hype(text, check, store):
    b = wf.create_brief(opp(target="marketplace payouts mismatch"), TENANT, PAGES, store)
    d = wf.generate_draft(b, opp(target="marketplace payouts mismatch"), FACTS, PAGES, store, writer=_Fabricator(text))
    failed = {c.check_name for c in d.qa.checks if not c.passed}
    assert d.status == "NEEDS_REVISION" and check in failed


def test_qa_blocks_a_claim_that_rides_on_a_citation(tmp_path):
    st = SeoContentStore(str(tmp_path / "e"))
    b = wf.create_brief(opp(target="marketplace payouts mismatch"), TENANT, PAGES, st)
    d = wf.generate_draft(b, opp(target="marketplace payouts mismatch"), FACTS, PAGES, st, writer=_Fabricator("Payouts are reconciled by hand every day."))  # cites f1 but is not f1's claim
    assert d.status == "NEEDS_REVISION" and "evidence_grounding" in {c.check_name for c in d.qa.checks if not c.passed}


def test_qa_blocks_uncited_paragraphs(tmp_path):
    st = SeoContentStore(str(tmp_path / "a"))
    b = wf.create_brief(opp(target="marketplace payouts mismatch"), TENANT, PAGES, st)
    d = wf.generate_draft(b, opp(target="marketplace payouts mismatch"), FACTS, PAGES, st, writer=_Fabricator("An uncited claim.", fact_ids=()))
    assert d.status == "NEEDS_REVISION" and "evidence_grounding" in {c.check_name for c in d.qa.checks if not c.passed}


def test_qa_blocks_a_draft_when_the_tenant_has_no_audience(tmp_path):
    st = SeoContentStore(str(tmp_path / "b"))
    noaud = TenantProfile(tenant_id="sanocea", brand="SANOCEA", domain="www.sanocea.com")
    nb = build_brief(opp(target="payouts mismatch guide", oid="OPP-3"), noaud, PAGES)
    st.save_brief(nb)
    nd = wf.generate_draft(nb, opp(target="payouts mismatch guide", oid="OPP-3"), FACTS, PAGES, st)
    assert "intended_audience" in {c.check_name for c in nd.qa.checks if not c.passed} and nd.status == "NEEDS_REVISION"


def test_qa_blocks_a_near_duplicate_of_an_earlier_ready_draft(tmp_path):
    st = SeoContentStore(str(tmp_path / "c"))
    first = wf.generate_draft(wf.create_brief(opp(target="marketplace payouts mismatch"), TENANT, PAGES, st), opp(target="marketplace payouts mismatch"), FACTS, PAGES, st)
    assert first.status == "DRAFT_READY"
    b2 = wf.create_brief(opp(target="marketplace payouts mismatches", oid="OPP-4"), TENANT, PAGES, st)
    dup = wf.generate_draft(b2, opp(target="marketplace payouts mismatches", oid="OPP-4"), FACTS, PAGES, st)
    assert dup.draft_id != first.draft_id and "duplication" in {c.check_name for c in dup.qa.checks if not c.passed}


def test_qa_blocks_a_heading_structure_with_two_h1s(tmp_path):
    from packages.content_engine.seo.models import DraftSection, DraftParagraph
    from packages.content_engine.seo.qa import evaluate_draft
    st = SeoContentStore(str(tmp_path / "d"))
    b = wf.create_brief(opp(target="marketplace payouts mismatch"), TENANT, PAGES, st)
    d = wf.generate_draft(b, opp(target="marketplace payouts mismatch"), FACTS, PAGES, st)
    d.sections.append(DraftSection(level=1, heading="Second h1", paragraphs=[DraftParagraph(text=FACTS[0].text, fact_ids=["f1"])]))
    r = evaluate_draft(d, b, FACTS, PAGES, [])
    assert "heading_structure" in {c.check_name for c in r.checks if not c.passed}


def test_title_meta_draft_has_no_body_and_needs_a_title_source(store):
    o = opp("HIGH_IMPRESSIONS_LOW_CTR", "UPDATE_TITLE_META", target="https://www.sanocea.com/", ev={"page": "https://www.sanocea.com/", "impressions": 400, "clicks": 2, "ctr": 0.005})
    b = wf.create_brief(o, TENANT, PAGES, store)
    d = wf.generate_draft(b, o, FACTS, PAGES, store)
    assert d.status == "GENERATION_FAILED" and "no grounded title" in d.error  # the brief has none and the writer will not invent one


# ── provenance: "why did SANOCEA create this?" ───────────────────────────────

def test_explain_answers_from_stored_records_only(store):
    o = opp(target="marketplace payouts mismatch")
    b = wf.create_brief(o, TENANT, PAGES, store)
    d = wf.generate_draft(b, o, FACTS, PAGES, store)
    for item in (b.brief_id, d.draft_id):
        r = wf.explain(store, "sanocea", item)
        assert "QUERY_PAGE_MATCH_GAP" in r["why"] and "human:asha" in r["why"] and "[OBSERVED: PERSISTED GSC SNAPSHOT]" in r["why"]
        assert r["chain"]["evidence"]["query"] == "marketplace payouts mismatch"
        assert r["chain"]["decision"]["action"] == "CREATE_SEO_PAGE" and r["chain"]["approval"]["by"] == "human:asha"
        assert r["chain"]["brief"]["field_basis"]["proposed_title"] == "GENERATED_RECOMMENDATION"
    assert wf.explain(store, "sanocea", d.draft_id)["chain"]["draft"]["fact_ids_used"] == d.fact_ids_used


def test_source_and_control_are_injectable_and_control_fails_closed_without_a_token(monkeypatch):
    from packages.content_engine.seo import source
    src = OpportunitySource(get_json=lambda p: {"/opportunities": {"opportunities": [opp()]}, "/agent-roster": {"roster": [{"role": "AI_CONTENT_AUDITOR", "status": "COMPLETED", "details": {"pages": PAGES}}]}}[p])
    assert src.get("OPP-1")["type"] == "QUERY_PAGE_MATCH_GAP" and src.get("nope") is None and len(src.site_pages()) == 2
    monkeypatch.delenv("SEO_WORKER_CONTROL_TOKEN", raising=False)
    with pytest.raises(PermissionError):
        source.http_post_json("/opportunities/transition", {})
