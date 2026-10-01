"""Executor bridge: execute / observe / rollback end to end against temporary release dirs and a temporary git repo.
Nothing touches /var/www, the real repository or the network (fetch is injected)."""

import json
import os
import subprocess

import pytest

from packages.content_engine.seo import executor
from packages.content_engine.seo.policy import POLICY_REF
from packages.content_engine.seo.store import SeoContentStore

HOST = "www.sanocea.com"
LISTED = "https://www.sanocea.com/solutions/marketplace-reconciliation"
DEST = LISTED + "/"
SITEMAP = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.sanocea.com/</loc></url>
  <url><loc>{LISTED}</loc></url>
</urlset>
'''
AUTO = {"by": "autonomous:sanocea-autonomy-policy@1.0.0", "at": "2026-10-02T00:00:00Z", "actorType": "AUTONOMOUS_AGENT", "policy": POLICY_REF, "reason": "ok", "actionClass": "A", "approvedAction": "FIX_SITEMAP_ENTRY"}
PLAN = {"selected": "FIX_SITEMAP_ENTRY", "candidates": [{"action": "FIX_SITEMAP_ENTRY", "expected_outcome": [
    {"kind": "sitemap_lists", "subject": DEST, "equals": DEST}, {"kind": "sitemap_lists", "subject": LISTED, "absent": True}, {"kind": "redirects_to", "subject": DEST, "absent": True}]}]}


def opp(action="FIX_SITEMAP_ENTRY", status="APPROVED", approval=AUTO):
    return {"opportunityId": "OPP-X1", "tenantId": "sanocea", "resultingAction": None, "type": "SITEMAP_URL_REDIRECTS", "target": LISTED, "status": status, "source": "[OBSERVED: LIVE PAGE FETCH]", "recommendedAction": action,
            "evidence": {"listedUrl": LISTED, "finalUrl": DEST}, "decision": {"action": action, "rationale": "r", "checks": ["c"]}, "approval": approval, "actionPlan": PLAN}


class Site:
    """A fake public site whose /sitemap.xml follows whatever `current` points at, like nginx would."""
    def __init__(self, root):
        self.root = root
        self.overrides = {}

    def __call__(self, url):
        if url in self.overrides:
            return self.overrides[url]
        if url == "https://www.sanocea.com/sitemap.xml":
            return 200, {}, open(os.path.join(self.root, "current", "sitemap.xml"), encoding="utf-8").read()
        if url == "https://www.sanocea.com/":
            return 200, {}, "<html>home</html>"
        if url == LISTED:
            return 301, {"location": DEST}, ""
        if url == DEST:
            return 200, {}, f'<html><head><link rel="canonical" href="{DEST}" /></head></html>'
        return 404, {}, ""


@pytest.fixture()
def world(tmp_path, monkeypatch):
    www = tmp_path / "www"
    rel = www / "releases" / "rel-1"
    rel.mkdir(parents=True)
    (rel / "sitemap.xml").write_text(SITEMAP)
    (rel / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    os.symlink(str(rel), str(www / "current"))
    repo = tmp_path / "repo"
    (repo / "website" / "public").mkdir(parents=True)
    (repo / "website" / "public" / "sitemap.xml").write_text(SITEMAP)
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    cfg = tmp_path / "targets.json"
    cfg.write_text(json.dumps({"targets": {"sanocea": {"kind": "static-site", "host": HOST, "base_url": "https://www.sanocea.com", "www_root": str(www), "path_prefixes": ["/sitemap.xml"], "source_repo": str(repo),
                                                       "source_files": {"sitemap.xml": "website/public/sitemap.xml"}, "commit_source": True, "health_urls": ["https://www.sanocea.com/"]}}}))
    monkeypatch.setenv("SEO_PUBLISH_TARGETS", str(cfg))
    return str(www), str(repo), SeoContentStore(str(tmp_path / "content")), Site(str(www))


class Worker:
    """The worker's persisted state as the executor reads it over loopback: the ONLY source of approval, status and mode."""
    def __init__(self, o, mode="AUTONOMOUS_SEO"):
        self.o, self.mode = o, mode

    def get(self, oid):
        return self.o if self.o and oid == self.o["opportunityId"] else None

    def autonomy(self):
        return {"mode": self.mode}


def done(r):
    return Worker({**opp(status="COMPLETED"), "resultingAction": f"change:{r['change_id']}"})


def run(world, **over):
    www, repo, store, site = world
    o = over.pop("opp", opp())
    return executor.execute({"tenant_id": "sanocea", "opportunity_id": o["opportunityId"], "dry_run": over.pop("dry_run", False)}, fetch=site, store=store, source=Worker(o, over.pop("mode", "AUTONOMOUS_SEO")))


def test_publish_switches_release_syncs_and_commits_source_then_observe_verifies(world):
    www, repo, store, site = world
    r = run(world)
    assert r["status"] == "PUBLISHED", r
    live = open(os.path.join(www, "current", "sitemap.xml")).read()
    assert f"<loc>{DEST}</loc>" in live and f"<loc>{LISTED}</loc>" not in live
    src = open(os.path.join(repo, "website", "public", "sitemap.xml")).read()
    assert src == live, "repo source stays in step so the next deploy does not revert the change"
    assert r["source_sync"]["commit"], "source change is committed (that one path)"
    assert subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True).stdout.strip() == ""
    o = executor.observe({"tenant_id": "sanocea", "expected_outcome": r["receipt"]["expected_outcome"]}, fetch=site)
    assert o["observable"] is True
    assert {(f["kind"], f["subject"]) for f in o["facts"]} == {("sitemap_lists", DEST)}


def test_second_execute_is_idempotent(world):
    assert run(world)["status"] == "PUBLISHED"
    assert run(world)["status"] == "ALREADY_PUBLISHED"  # the same opportunity is never applied twice


def test_unsupported_action_and_class_c_are_never_executed(world):
    assert run(world, opp=opp("CHANGE_REDIRECT"))["status"] == "UNSUPPORTED"
    assert run(world, opp=opp("CHANGE_SERVER_RENDERING"))["status"] == "UNSUPPORTED"


def test_tenant_without_a_target_cannot_publish(world):
    www, repo, store, site = world
    o = {**opp(), "tenantId": "other"}
    r = executor.execute({"tenant_id": "other", "opportunity_id": o["opportunityId"]}, fetch=site, store=store, source=Worker(o))
    assert r["status"] == "BLOCKED" and r["blocked_by"] == ["publish_target_configured"]


def test_recommend_only_mode_is_blocked_by_the_policy_gate_and_nothing_changes(world):
    www, repo, store, site = world
    r = run(world, mode="RECOMMEND_ONLY")
    assert r["status"] == "BLOCKED" and "tenant_authorization" in r["blocked_by"]
    assert open(os.path.join(www, "current", "sitemap.xml")).read() == SITEMAP


def test_source_that_differs_from_live_blocks_publication(world):
    www, repo, store, site = world
    open(os.path.join(repo, "website", "public", "sitemap.xml"), "w").write(SITEMAP + "<!-- drift -->")
    r = run(world)
    assert r["status"] == "BLOCKED" and r["blocked_by"] == ["source_of_truth_matches_live"]
    assert open(os.path.join(www, "current", "sitemap.xml")).read() == SITEMAP


def test_failed_plan_check_blocks_with_the_reason(world):
    www, repo, store, site = world
    site.overrides[DEST] = (200, {}, '<html><head><link rel="canonical" href="https://www.sanocea.com/other/" /></head></html>')
    r = run(world)
    assert r["status"] == "BLOCKED" and "destination_is_its_own_canonical" in r["blocked_by"]


def test_health_check_failure_switches_back(world):
    www, repo, store, site = world
    before = os.path.realpath(os.path.join(www, "current"))
    site.overrides["https://www.sanocea.com/"] = (503, {}, "")
    r = run(world)
    assert r["status"] == "BLOCKED" and r["blocked_by"] == ["HEALTH_CHECK_FAILED"]
    assert os.path.realpath(os.path.join(www, "current")) == before
    assert open(os.path.join(repo, "website", "public", "sitemap.xml")).read() == SITEMAP


def test_observe_is_not_a_verdict_when_the_live_site_cannot_be_read(world):
    www, repo, store, site = world
    r = run(world)
    site.overrides["https://www.sanocea.com/sitemap.xml"] = (503, {}, "")
    o = executor.observe({"tenant_id": "sanocea", "expected_outcome": r["receipt"]["expected_outcome"]}, fetch=site)
    assert o["observable"] is False and o["unobservable"], "an unreadable sitemap is never read as success or failure"


def test_rollback_restores_live_release_and_repo_source_and_blocks_reapplication(world):
    www, repo, store, site = world
    r = run(world)
    rb = executor.rollback({"tenant_id": "sanocea", "opportunity_id": "OPP-X1", "change_id": r["change_id"]}, fetch=site, store=store, source=done(r))
    assert rb["status"] == "ROLLED_BACK" and rb["source_restored"] is True
    assert open(os.path.join(www, "current", "sitemap.xml")).read() == SITEMAP
    assert open(os.path.join(repo, "website", "public", "sitemap.xml")).read() == SITEMAP
    again = run(world)
    assert again["status"] in ("BLOCKED",), again
    assert again["blocked_by"] == ["previously_rolled_back"]


def test_rollback_refused_when_a_later_release_exists(world):
    www, repo, store, site = world
    r = run(world)
    newer = os.path.join(www, "releases", "rel-later")
    os.makedirs(newer)
    for n in os.listdir(os.path.join(www, "current")):
        open(os.path.join(newer, n), "w").write(open(os.path.join(www, "current", n)).read())
    tmp = os.path.join(www, "current.tmp")
    os.symlink(newer, tmp)
    os.replace(tmp, os.path.join(www, "current"))
    rb = executor.rollback({"tenant_id": "sanocea", "opportunity_id": "OPP-X1", "change_id": r["change_id"]}, fetch=site, store=store, source=done(r))
    assert rb["status"] == "ROLLBACK_UNAVAILABLE" and rb["code"] == "ROLLBACK_CONFLICT"


def test_cli_wraps_errors_as_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO('{"command": "nope"}'))
    assert executor.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"


def test_dry_run_evaluates_every_gate_without_publishing(world):
    www, repo, store, site = world
    r = run(world, dry_run=True)
    assert r["status"] == "ELIGIBLE" and r["destination"] == DEST
    assert open(os.path.join(www, "current", "sitemap.xml")).read() == SITEMAP


def test_resume_after_crash_between_publish_and_recording_never_applies_twice(world):
    www, repo, store, site = world
    first = run(world)
    again = run(world)  # the worker crashed before recording COMPLETED and runs execute again
    assert again["status"] == "ALREADY_PUBLISHED" and again["change_id"] == first["change_id"]
    assert len(os.listdir(os.path.join(www, "releases"))) == 2


# ── the executor cannot be driven around the worker's policy decision ──────────

def test_forged_request_fields_are_ignored_the_workers_state_decides(world):
    www, repo, store, site = world
    unapproved = opp(status="AWAITING_APPROVAL", approval=None)
    forged = {"tenant_id": "sanocea", "opportunity_id": "OPP-X1", "opportunity": opp(), "mode": "AUTONOMOUS_DISTRIBUTION", "approval": AUTO, "status": "APPROVED"}
    r = executor.execute(forged, fetch=site, store=store, source=Worker(unapproved))
    assert r["status"] == "BLOCKED" and r["blocked_by"] == ["standing_approval"]
    assert open(os.path.join(www, "current", "sitemap.xml")).read() == SITEMAP


def test_mode_comes_from_the_worker_not_the_request(world):
    www, repo, store, site = world
    r = executor.execute({"tenant_id": "sanocea", "opportunity_id": "OPP-X1", "mode": "AUTONOMOUS_SEO"}, fetch=site, store=store, source=Worker(opp(), "RECOMMEND_ONLY"))
    assert r["status"] == "BLOCKED" and "tenant_authorization" in r["blocked_by"]


def test_unreachable_worker_state_means_nothing_is_executed(world):
    class Down:
        def get(self, oid):
            raise ConnectionRefusedError()
    www, repo, store, site = world
    r = executor.execute({"tenant_id": "sanocea", "opportunity_id": "OPP-X1"}, fetch=site, store=store, source=Down())
    assert r["status"] == "BLOCKED" and r["blocked_by"] == ["worker_policy_state"]


def test_rollback_is_refused_unless_the_worker_records_that_change_as_the_executed_result(world):
    www, repo, store, site = world
    r = run(world)
    for src in (Worker(opp(status="COMPLETED")), Worker({**opp(status="COMPLETED"), "resultingAction": "change:chg_other"}), Worker({**opp(status="APPROVED"), "resultingAction": f"change:{r['change_id']}"})):
        rb = executor.rollback({"tenant_id": "sanocea", "opportunity_id": "OPP-X1", "change_id": r["change_id"]}, fetch=site, store=store, source=src)
        assert rb["status"] == "BLOCKED"
    assert f"<loc>{DEST}</loc>" in open(os.path.join(www, "current", "sitemap.xml")).read()
