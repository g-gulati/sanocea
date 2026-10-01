"""CHANGE_CANONICAL through the executor: bounded page edit, human-approval authority, source sync, observation by recorded outcome, rollback.
Temporary release dirs and a temporary git repo only; fetch is injected."""

import json
import os
import subprocess

import pytest

from packages.content_engine.seo import executor
from packages.content_engine.seo.pageedit import page_file_for
from packages.content_engine.seo.policy import POLICY_REF
from packages.content_engine.seo.publisher import PAGE_FILE_RE, paths_allowed
from packages.content_engine.seo.store import SeoContentStore

HOST = "www.sanocea.com"
WRONG = "https://www.sanocea.com/solutions/marketplace-reconciliation"
INTENDED = WRONG + "/"
REL = "solutions/marketplace-reconciliation/index.html"
SRC_REL = "website/solutions/marketplace-reconciliation/index.html"
SITEMAP = f'<?xml version="1.0"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>https://www.sanocea.com/</loc></url>\n  <url><loc>{WRONG}</loc></url>\n</urlset>\n'


def page(assets):
    return (f'<html><head><link rel="canonical" href="{WRONG}" /><meta property="og:url" content="{WRONG}" />{assets}\n'
            f'<script type="application/ld+json">{{"url": "{WRONG}", "item": "{WRONG}", "other": "https://www.sanocea.com/"}}</script></head>'
            f'<body><a href="{WRONG}/more">keep this link</a><p>text mentioning {WRONG} stays</p></body></html>\n')


LIVE_PAGE = page('<script src="../../assets/app.js"></script>')
SRC_PAGE = page('<script src="/src/app.jsx"></script>')
HUMAN = {"by": "human:owner-instruction", "at": "2026-09-30T00:00:00+00:00", "actorType": "HUMAN", "policy": "human-manual", "reason": "owner decision", "actionClass": "B", "approvedAction": "CHANGE_CANONICAL"}
AUTO = {"by": "autonomous:sanocea-autonomy-policy@1.0.0", "at": "2026-09-30T00:00:00+00:00", "actorType": "AUTONOMOUS_AGENT", "policy": POLICY_REF, "reason": "ok", "actionClass": "B", "approvedAction": "CHANGE_CANONICAL"}
PLAN = {"selected": "CHANGE_CANONICAL", "candidates": [{"action": "CHANGE_CANONICAL", "expected_outcome": [{"kind": "destination_canonical", "subject": INTENDED, "equals": INTENDED}]}]}


def opp(approval=HUMAN, intended=INTENDED, status="APPROVED"):
    return {"opportunityId": "OPP-C1", "tenantId": "sanocea", "type": "SITEMAP_URL_REDIRECTS", "target": WRONG, "status": status, "source": "[OBSERVED: LIVE PAGE FETCH]", "recommendedAction": "CHANGE_CANONICAL",
            "resultingAction": None, "evidence": {"listedUrl": WRONG, "finalUrl": INTENDED}, "decision": {"action": "CHANGE_CANONICAL", "rationale": "r", "checks": ["c"]},
            "approval": approval, "actionPlan": PLAN, "diagnosis": {"intended": intended}}


class Worker:
    def __init__(self, o, mode="AUTONOMOUS_SEO"):
        self.o, self.mode = o, mode

    def get(self, oid):
        return self.o if oid == self.o["opportunityId"] else None

    def autonomy(self):
        return {"mode": self.mode}


class Site:
    def __init__(self, root):
        self.root, self.over = root, {}

    def __call__(self, url):
        if url in self.over:
            return self.over[url]
        cur = os.path.join(self.root, "current")
        if url == "https://www.sanocea.com/sitemap.xml":
            return 200, {}, open(os.path.join(cur, "sitemap.xml")).read()
        if url == "https://www.sanocea.com/":
            return 200, {}, "<html>home</html>"
        if url == WRONG:
            return 301, {"location": INTENDED}, ""
        if url == INTENDED:
            return 200, {}, open(os.path.join(cur, REL)).read()
        return 404, {}, ""


@pytest.fixture()
def world(tmp_path, monkeypatch):
    www = tmp_path / "www"
    rel = www / "releases" / "rel-1"
    (rel / "solutions" / "marketplace-reconciliation").mkdir(parents=True)
    (rel / "sitemap.xml").write_text(SITEMAP)
    (rel / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    (rel / REL).write_text(LIVE_PAGE)
    os.symlink(str(rel), str(www / "current"))
    repo = tmp_path / "repo"
    (repo / "website" / "solutions" / "marketplace-reconciliation").mkdir(parents=True)
    (repo / "website" / "public").mkdir(parents=True)
    (repo / SRC_REL).write_text(SRC_PAGE)
    (repo / "website" / "public" / "sitemap.xml").write_text(SITEMAP)
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    cfg = tmp_path / "targets.json"
    cfg.write_text(json.dumps({"targets": {"sanocea": {"kind": "static-site", "host": HOST, "base_url": "https://www.sanocea.com", "www_root": str(www), "path_prefixes": ["/sitemap.xml", "/solutions/"],
                                                       "source_repo": str(repo), "source_files": {"sitemap.xml": "website/public/sitemap.xml", REL: SRC_REL}, "commit_source": True, "health_urls": ["https://www.sanocea.com/"]}}}))
    monkeypatch.setenv("SEO_PUBLISH_TARGETS", str(cfg))
    return str(www), str(repo), SeoContentStore(str(tmp_path / "content")), Site(str(www))


def run(world, o=None, mode="AUTONOMOUS_SEO", dry=False):
    www, repo, store, site = world
    o = o or opp()
    return executor.execute({"tenant_id": "sanocea", "opportunity_id": o["opportunityId"], "dry_run": dry}, fetch=site, store=store, source=Worker(o, mode))


def test_human_approved_change_edits_only_the_declared_addresses_syncs_source_and_verifies(world):
    www, repo, store, site = world
    r = run(world)
    assert r["status"] == "PUBLISHED", r
    live = open(os.path.join(www, "current", REL)).read()
    assert live == LIVE_PAGE.replace(f'"{WRONG}"', f'"{INTENDED}"')
    assert f'href="{WRONG}/more"' in live and f"text mentioning {WRONG} stays" in live, "links and visible text are untouched: only the quoted declarations change"
    assert live.count(f'"{INTENDED}"') == 4
    src = open(os.path.join(repo, SRC_REL)).read()
    assert src == SRC_PAGE.replace(f'"{WRONG}"', f'"{INTENDED}"') and "/src/app.jsx" in src, "the source keeps its own (unbuilt) asset lines and gets only the same address change"
    assert open(os.path.join(www, "current", "sitemap.xml")).read() == SITEMAP, "no other file changed"
    assert r["source_sync"]["commit"] and subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True).stdout.strip() == ""
    o = executor.observe({"tenant_id": "sanocea", "change_id": r["change_id"]}, fetch=site, store=store)
    assert o["observable"] and {(f["kind"], f["subject"], f["value"]) for f in o["facts"]} == {("destination_canonical", INTENDED, INTENDED)}
    assert o["expected_outcome"] == PLAN["candidates"][0]["expected_outcome"], "verification uses the outcome recorded at publication time"


def test_verification_uses_the_recorded_outcome_even_after_the_opportunity_plan_moves_on(world):
    www, repo, store, site = world
    r = run(world)
    stale = [{"kind": "sitemap_lists", "subject": INTENDED, "equals": INTENDED}]  # what the NEXT step's plan would expect
    o = executor.observe({"tenant_id": "sanocea", "change_id": r["change_id"], "expected_outcome": stale}, fetch=site, store=store)
    assert [f["kind"] for f in o["facts"]] == ["destination_canonical"] and o["expected_outcome"] != stale


def test_autonomous_approval_of_a_class_b_change_is_still_refused_in_seo_mode(world):
    www, repo, store, site = world
    r = run(world, opp(approval=AUTO))
    assert r["status"] == "BLOCKED" and "tenant_authorization" in r["blocked_by"]
    assert open(os.path.join(www, "current", REL)).read() == LIVE_PAGE


def test_it_needs_the_workers_established_intended_address(world):
    r = run(world, opp(intended=None))
    assert r["status"] == "BLOCKED" and r["blocked_by"] == ["intended_address_established"]


@pytest.mark.parametrize("name,over,gate", [
    ("wrong address no longer redirects", {WRONG: (200, {}, "")}, "wrong_address_redirects_to_intended"),
    ("intended returns 404", {INTENDED: (404, {}, "")}, "intended_returns_200"),
    ("intended is noindex", {INTENDED: (200, {}, '<meta name="robots" content="noindex">')}, "intended_is_indexable"),
])
def test_live_behaviour_must_agree_with_the_conclusion(world, name, over, gate):
    www, repo, store, site = world
    site.over.update(over)
    r = run(world)
    assert r["status"] == "BLOCKED" and gate in r["blocked_by"], name
    assert open(os.path.join(www, "current", REL)).read() == LIVE_PAGE


def test_source_that_does_not_declare_the_same_addresses_blocks(world):
    www, repo, store, site = world
    open(os.path.join(repo, SRC_REL), "w").write(SRC_PAGE.replace(f'"{WRONG}"', '"https://elsewhere.test/"', 1))
    r = run(world)
    assert r["status"] == "BLOCKED" and "source_declares_the_same_addresses" in r["blocked_by"]


def test_a_page_not_covered_by_the_target_or_the_config_is_never_edited(world, tmp_path):
    www, repo, store, site = world
    o = opp(intended="https://www.sanocea.com/private/x/")
    r = run(world, o)
    assert r["status"] == "BLOCKED" and ("source_of_truth_known" in r["blocked_by"] or "live_file_readable" in r["blocked_by"])


def test_publisher_path_rules_allow_exactly_one_directory_index_page():
    assert paths_allowed("CHANGE_CANONICAL", {REL})
    for bad in ({"sitemap.xml"}, {"robots.txt"}, {"assets/app.js"}, {REL, "index.html"}, {"../etc/passwd"}, {"a.html"}, set(), {"/abs/index.html"}):
        assert not paths_allowed("CHANGE_CANONICAL", bad), bad
    assert not paths_allowed("FIX_SITEMAP_ENTRY", {REL}) and not paths_allowed("CHANGE_REDIRECT", {REL})
    assert page_file_for(INTENDED) == REL and page_file_for(WRONG) is None and page_file_for("https://x/a/../b/") is None and PAGE_FILE_RE.match(REL)


def test_rollback_restores_page_and_source_and_the_change_is_not_reapplied(world):
    www, repo, store, site = world
    r = run(world)
    done = {**opp(status="COMPLETED"), "resultingAction": f"change:{r['change_id']}"}
    rb = executor.rollback({"tenant_id": "sanocea", "opportunity_id": "OPP-C1", "change_id": r["change_id"]}, fetch=site, store=store, source=Worker(done))
    assert rb["status"] == "ROLLED_BACK" and rb["source_restored"] is True
    assert open(os.path.join(www, "current", REL)).read() == LIVE_PAGE and open(os.path.join(repo, SRC_REL)).read() == SRC_PAGE
    assert run(world)["status"] == "BLOCKED"


def test_an_opportunity_can_carry_a_second_change_after_the_first(world):
    """Canonical first, then (later cycle) the sitemap: the second action must not be mistaken for a crash-resume of the first."""
    www, repo, store, site = world
    first = run(world)
    assert first["status"] == "PUBLISHED"
    sitemap_opp = {**opp(approval={**AUTO, "at": "2099-01-01T00:00:00+00:00", "actionClass": "A", "approvedAction": "FIX_SITEMAP_ENTRY"}), "recommendedAction": "FIX_SITEMAP_ENTRY",
                   "decision": {"action": "FIX_SITEMAP_ENTRY", "rationale": "r", "checks": ["c"]}, "actionPlan": {"selected": "FIX_SITEMAP_ENTRY", "candidates": [{"action": "FIX_SITEMAP_ENTRY", "expected_outcome": []}]}}
    r = run(world, sitemap_opp)
    assert r["status"] == "PUBLISHED" and r["change_id"] != first["change_id"], r
    assert f"<loc>{INTENDED}</loc>" in open(os.path.join(www, "current", "sitemap.xml")).read()


def test_publisher_still_refuses_a_canonical_change_without_an_audited_decision(world):
    from packages.content_engine.seo.policy import Gate, PublishDecision
    from packages.content_engine.seo.publisher import PublishRequest, PublisherError, StaticSiteReleasePublisher
    www, repo, store, site = world
    pub = StaticSiteReleasePublisher(www, "sanocea")
    forged = PublishDecision(draft_id="chg_forged", tenant_id="sanocea", action="CHANGE_CANONICAL", action_class="B", eligible=True, evaluated_at="x", gates=[Gate(gate="x", passed=True, detail="x")], blocked_by=[], status="ELIGIBLE")
    req = PublishRequest(tenant_id="sanocea", opportunity_id="OPP-C1", change_id="chg_forged", action="CHANGE_CANONICAL", target=WRONG, file_changes={REL: "x"}, before_sha256="a", after_sha256="b")
    with pytest.raises(PublisherError) as e:
        pub.publish(req, forged, store)
    assert e.value.code == "NO_AUDITED_DECISION"
