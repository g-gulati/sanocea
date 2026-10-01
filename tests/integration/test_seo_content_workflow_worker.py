"""REAL worker, FIXTURE opportunity. Starts the actual SEO worker daemon (new build) on a throwaway SQLite database seeded with
one deterministic content-eligible opportunity (no live content opportunity exists), then drives the Python workflow through
the worker's real HTTP lifecycle and control endpoint: submit -> agent cannot approve -> human approves -> brief -> draft."""

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

import pytest

from packages.content_engine.seo import workflow as wf
from packages.content_engine.seo.brief import ContentWorkflowError
from packages.content_engine.seo.models import ApprovedFact, TenantProfile
from packages.content_engine.seo.source import OpportunityControl, OpportunitySource
from packages.content_engine.seo.store import SeoContentStore

DIST = "packages/seo-stack/dist/src"
pytestmark = pytest.mark.skipif(not shutil.which("node") or not os.path.exists(f"{DIST}/worker/workerDaemon.js"), reason="seo-stack is not built")

SEED = """
import('./%(dist)s/persistence/seoDb.js').then(async ({SeoDatabase}) => {
  const {OpportunityEngine} = await import('./%(dist)s/opportunities/opportunityEngine.js');
  const db = new SeoDatabase(process.argv[1]);
  const pages = [
    {url:'https://www.sanocea.com/', status:200, staticWords:400, bodyWords:420, title:'SANOCEA', h1Text:'Ecommerce operations', h1Count:1, jsonLdTypes:[], retiredSchemaTypes:[], finalUrl:'https://www.sanocea.com/', redirected:false},
    {url:'https://www.sanocea.com/solutions/marketplace-reconciliation', status:200, staticWords:0, bodyWords:0, title:'', h1Text:'', h1Count:0, jsonLdTypes:[], retiredSchemaTypes:[], finalUrl:'https://www.sanocea.com/solutions/marketplace-reconciliation', redirected:false}];
  db.recordAgentTaskExecution({taskId:'t1', tenantId:'sanocea', agentId:'agent-ai-content-auditor', agentName:'AI Content Auditor', role:'AI_CONTENT_AUDITOR', status:'COMPLETED', currentTask:'x', outputSummary:'x', provenance:'[OBSERVED: LIVE PAGE FETCH]', executedAt:new Date().toISOString(), nextScheduledAt:'', details:{checkedAt:new Date().toISOString(), pages}});
  db.saveGscSnapshot('sanocea', {snapshotId:'S1', siteUrl:'sc-domain:sanocea.com', dateRange:{startDate:'2026-09-01', endDate:'2026-09-28'}, totalClicks:0, totalImpressions:80, averageCtr:0, averagePosition:12,
    queryRows:[{query:'amazon payout mismatch', clicks:0, impressions:80, ctr:0, position:12}], pageRows:[], capturedAt:'2026-09-29T00:00:00Z'});
  const eng = new OpportunityEngine(db); console.log(JSON.stringify(eng.refresh('sanocea'))); db.close();
});
""" % {"dist": DIST}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def worker(tmp_path):
    db = str(tmp_path / "seo.sqlite")
    seeded = subprocess.run(["node", "-e", SEED, db], capture_output=True, text=True, timeout=60)
    assert seeded.returncode == 0, seeded.stderr
    port, token = _free_port(), "t" * 40
    env = dict(os.environ, SEO_WORKER_PORT=str(port), SEO_DB_PATH=db, SEO_WORKER_CONTROL_TOKEN=token, SEO_MONITORED_DOMAIN="localhost.invalid", SEO_TENANT_ID="sanocea", TIER1_INTERVAL_MS="86400000")
    env.pop("GSC_SERVICE_ACCOUNT_PATH", None)
    env.pop("GSC_SERVICE_ACCOUNT_KEY", None)
    proc = subprocess.Popen(["node", f"{DIST}/worker/workerDaemon.js"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{base}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("worker did not start")
    yield base, token
    proc.terminate()
    proc.wait(timeout=10)


def _get(base):
    return lambda p: json.loads(urllib.request.urlopen(base + p, timeout=10).read())


def _post(base, token):
    def go(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json", "x-seo-control-token": token})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=10).read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:160]}")
    return go


TENANT = TenantProfile(tenant_id="sanocea", brand="SANOCEA", domain="www.sanocea.com", audience="Operations leads at multichannel ecommerce brands")
FACTS = [ApprovedFact(id="f1", text="Marketplace payouts rarely match order totals because fees, returns and delays are netted off separately.", source="owner: operations notes"),
         ApprovedFact(id="f2", text="Payout reconciliation compares each payout line with its order before the books are closed.", source="owner: operations notes")]


def test_real_lifecycle_to_draft_with_a_fixture_opportunity(worker, tmp_path):
    base, token = worker
    src, control, store = OpportunitySource(_get(base)), OpportunityControl(_post(base, token)), SeoContentStore(str(tmp_path / "content"))
    opps = src.list()["opportunities"]
    elig = [o for o in opps if o["contentEligible"]]
    assert [o["type"] for o in elig] == ["QUERY_PAGE_MATCH_GAP"], "exactly the fixture opportunity is content-eligible"
    assert all(not o["contentEligible"] for o in opps if o["type"] != "QUERY_PAGE_MATCH_GAP"), "technical opportunities are never eligible"
    o = elig[0]
    assert o["status"] == "DISCOVERED" and o["approval"] is None and o["decision"]["action"] == "CREATE_SEO_PAGE"

    wf.submit_for_approval(o, control)  # agent steps only
    o = src.get(o["opportunityId"])
    assert o["status"] == "AWAITING_APPROVAL" and o["approval"] is None

    # the worker itself refuses an agent approval, even with the control token
    with pytest.raises(RuntimeError, match="only a human"):
        control.transition(o["opportunityId"], "APPROVED", "agent:content-workflow", "self-approve")
    with pytest.raises(ContentWorkflowError):
        wf.create_brief(src.get(o["opportunityId"]), TENANT, src.site_pages(), store)

    # without the control token every write is refused
    with pytest.raises(RuntimeError, match="HTTP 403"):
        _post(base, "wrong-token-wrong-token-wrong-token-1")("/opportunities/transition", {"opportunityId": o["opportunityId"], "to": "APPROVED", "actor": "human:asha", "note": "x"})
    assert src.get(o["opportunityId"])["status"] == "AWAITING_APPROVAL"

    wf.approve(o, control, "human:asha", "Approved for a brief")
    o = src.get(o["opportunityId"])
    assert o["status"] == "APPROVED" and o["approval"]["by"] == "human:asha"

    brief = wf.create_brief(o, TENANT, src.site_pages(), store, control)
    assert brief.lineage.approval["by"] == "human:asha" and brief.target.value == "amazon payout mismatch"
    assert src.get(o["opportunityId"])["resultingAction"] == f"brief:{brief.brief_id}"

    draft = wf.generate_draft(brief, src.get(o["opportunityId"]), FACTS, src.site_pages(), store, control=control)
    assert draft.status == "DRAFT_READY", draft.qa.failure_reasons if draft.qa else draft.error
    assert src.get(o["opportunityId"])["resultingAction"] == f"draft:{draft.draft_id}"
    assert src.get(o["opportunityId"])["status"] == "APPROVED", "drafting never advances the opportunity further (no publishing here)"
    why = wf.explain(store, "sanocea", draft.draft_id)["why"]
    assert "QUERY_PAGE_MATCH_GAP" in why and "human:asha" in why and "f1" in why


def test_technical_opportunities_cannot_enter_the_content_workflow(worker, tmp_path):
    base, token = worker
    src, control = OpportunitySource(_get(base)), OpportunityControl(_post(base, token))
    tech = [o for o in src.list()["opportunities"] if o["type"] != "QUERY_PAGE_MATCH_GAP"]
    assert tech, "the seeded pages produce real technical opportunities"
    for o in tech:
        with pytest.raises(ContentWorkflowError) as e:
            wf.submit_for_approval(o, control)
        assert e.value.code == "NOT_CONTENT_ELIGIBLE"
        assert src.get(o["opportunityId"])["status"] == "DISCOVERED", "refused before any state change"


def test_real_autonomous_path_policy_decides_and_records_autonomous_approval(worker, tmp_path):
    """Real worker + fixture opportunity: default tenant is recommend-only (denied); a human sets AUTONOMOUS_CONTENT; the policy
    then approves as AUTONOMOUS_AGENT (not human); brief/draft follow; publish eligibility is evaluated (nothing is published)."""
    from packages.content_engine.seo.policy import PublishTarget, build_rollback, evaluate_publish_eligibility
    base, token = worker
    src, control, store = OpportunitySource(_get(base)), OpportunityControl(_post(base, token)), SeoContentStore(str(tmp_path / "content"))
    post = _post(base, token)
    assert src.autonomy()["mode"] == "RECOMMEND_ONLY", "no configuration => recommend-only"
    o = [x for x in src.list()["opportunities"] if x["contentEligible"]][0]

    denied = wf.authorize_autonomously(o, control)["decision"]
    assert denied["allowed"] is False and "recommend-only" in denied["reason"].lower()
    assert src.get(o["opportunityId"])["status"] == "AWAITING_APPROVAL" and src.get(o["opportunityId"])["approval"] is None

    with pytest.raises(RuntimeError, match="only a human"):
        post("/autonomy/mode", {"mode": "AUTONOMOUS_CONTENT", "actor": "autonomous:sanocea-autonomy-policy@1.0.0"})
    with pytest.raises(RuntimeError, match="only a human"):
        post("/autonomy/mode", {"mode": "AUTONOMOUS_CONTENT", "actor": "agent:content-workflow"})
    assert src.autonomy()["mode"] == "RECOMMEND_ONLY"
    post("/autonomy/mode", {"mode": "AUTONOMOUS_CONTENT", "actor": "human:owner"})
    assert src.autonomy()["mode"] == "AUTONOMOUS_CONTENT"

    out = wf.authorize_autonomously(src.get(o["opportunityId"]), control)
    assert out["decision"]["allowed"] is True and out["decision"]["actionClass"] == "B"
    o = src.get(o["opportunityId"])
    ap = o["approval"]
    assert o["status"] == "APPROVED" and ap["actorType"] == "AUTONOMOUS_AGENT" and ap["by"].startswith("autonomous:") and ap["policy"] == "sanocea-autonomy-policy@1.0.0" and "gates passed" in ap["reason"]
    again = wf.authorize_autonomously(o, control)
    assert again["decision"]["allowed"] is True, "idempotent"

    pages = src.site_pages()
    brief = wf.create_brief(o, TENANT, pages, store, control)
    draft = wf.generate_draft(brief, src.get(o["opportunityId"]), FACTS, pages, store, control=control)
    assert draft.status == "DRAFT_READY" and draft.lineage["approval_actor_type"] == "AUTONOMOUS_AGENT"
    rb = build_rollback(brief, draft)
    d = evaluate_publish_eligibility(brief, draft, src.get(o["opportunityId"]), src.autonomy()["mode"], PublishTarget(tenant_id="sanocea", base_url="https://www.sanocea.com", path_prefixes=["/"]), store, rb)
    assert d.eligible and d.action_class == "B"
    assert store.get_publication("sanocea", rb.target) is None, "eligibility is not publication"
    assert "AUTONOMOUS_AGENT" in wf.explain(store, "sanocea", draft.draft_id)["why"]

    # a human halts it: the autonomous approval stays on record, the human act is recorded as HUMAN, publication is blocked
    wf.human_override(src.get(o["opportunityId"]), control, "human:asha", "Not now")
    after = src.get(o["opportunityId"])
    assert after["status"] == "REJECTED" and after["approval"]["actorType"] == "AUTONOMOUS_AGENT"
    blocked = evaluate_publish_eligibility(brief, draft, after, src.autonomy()["mode"], PublishTarget(tenant_id="sanocea", base_url="https://www.sanocea.com", path_prefixes=["/"]), store, rb)
    assert not blocked.eligible and "standing_approval" in blocked.blocked_by


def test_technical_opportunities_are_class_c_and_never_authorised_even_in_the_most_permissive_mode(worker):
    base, token = worker
    src, control, post = OpportunitySource(_get(base)), OpportunityControl(_post(base, token)), _post(base, token)
    post("/autonomy/mode", {"mode": "AUTONOMOUS_DISTRIBUTION", "actor": "human:owner"})
    for o in [x for x in src.list()["opportunities"] if not x["contentEligible"]]:
        for to in ("QUALIFIED", "ACTIONABLE", "AWAITING_APPROVAL"):
            control.transition(o["opportunityId"], to, "agent:test", "prep")
        r = control.authorize(o["opportunityId"])
        assert r["decision"]["allowed"] is False and r["decision"]["actionClass"] == "C", o["type"]
        assert src.get(o["opportunityId"])["approval"] is None
