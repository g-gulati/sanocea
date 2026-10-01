"""FIX_SITEMAP_ENTRY checks, the generic static-site publisher, atomic releases, rollback, idempotency and policy enforcement.
Fixture-driven (temporary release directories); nothing touches /var/www or any real site."""

import os

import pytest

from packages.content_engine.seo.policy import Gate, POLICY_REF, PublishDecision, PublishTarget
from packages.content_engine.seo.publisher import PublishRequest, PublisherError, StaticSiteReleasePublisher, _tree_hashes
from packages.content_engine.seo.sitemap import evaluate_sitemap_eligibility, plan_sitemap_fix, sha, validate_sitemap
from packages.content_engine.seo.store import SeoContentStore

HOST = "www.sanocea.com"
LISTED = "https://www.sanocea.com/solutions/marketplace-reconciliation"
DEST = LISTED + "/"
SITEMAP = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.sanocea.com/</loc><priority>1.0</priority></url>
  <url><loc>{LISTED}</loc><priority>0.9</priority></url>
  <url><loc>https://www.sanocea.com/about</loc></url>
</urlset>
'''
ROBOTS = "User-agent: *\nAllow: /\n"
TARGET = PublishTarget(tenant_id="sanocea", kind="static-site", base_url="https://www.sanocea.com", path_prefixes=["/sitemap.xml"])
AUTO = {"by": "autonomous:sanocea-autonomy-policy@1.0.0", "at": "2026-10-02T00:00:00Z", "actorType": "AUTONOMOUS_AGENT", "policy": POLICY_REF, "reason": "ok", "actionClass": "A", "approvedAction": "FIX_SITEMAP_ENTRY"}


def page(canonical):
    return f'<html><head><link rel="canonical" href="{canonical}" /></head><body></body></html>' if canonical else "<html><head></head></html>"


def fetcher(**over):
    m = {LISTED: (301, {"location": DEST}, ""), DEST: (200, {}, page(DEST))}
    m.update(over)
    return lambda u: m.get(u, (404, {}, ""))


def opp(action="FIX_SITEMAP_ENTRY", approval=AUTO, status="APPROVED", oid="OPP-S1"):
    return {"opportunityId": oid, "type": "SITEMAP_URL_REDIRECTS", "target": LISTED, "status": status, "source": "[OBSERVED: LIVE PAGE FETCH]", "recommendedAction": action,
            "evidence": {"listedUrl": LISTED, "finalUrl": DEST}, "decision": {"action": action, "rationale": "r", "checks": ["c"]}, "approval": approval}


def plan(f=None, xml=SITEMAP, robots=ROBOTS, target=TARGET, tenant="sanocea", listed=LISTED):
    return plan_sitemap_fix(listed, xml, HOST, f or fetcher(), robots, target, tenant)


@pytest.fixture()
def world(tmp_path):
    root = tmp_path / "www"
    rel = root / "releases" / "rel-1"
    rel.mkdir(parents=True)
    (rel / "sitemap.xml").write_text(SITEMAP)
    (rel / "robots.txt").write_text(ROBOTS)
    (rel / "index.html").write_text("<html>home</html>")
    (rel / "assets").mkdir(); (rel / "assets" / "main.js").write_text("js")
    os.symlink(str(rel), str(root / "current"))
    return str(root), SeoContentStore(str(tmp_path / "content"))


def ready(world, mode="AUTONOMOUS_SEO", **kw):
    root, st = world
    p = plan(**kw)
    d = evaluate_sitemap_eligibility(opp(), p, mode, st, "sanocea")
    req = PublishRequest(tenant_id="sanocea", opportunity_id="OPP-S1", change_id=d.draft_id, action="FIX_SITEMAP_ENTRY", target="/sitemap.xml", file_changes={"sitemap.xml": p.after_xml or ""},
                         before_sha256=p.before_sha256, after_sha256=p.after_sha256 or "", source_path="website/public/sitemap.xml")
    return p, d, req


# ── plan checks ──────────────────────────────────────────────────────────────

def test_happy_plan_changes_exactly_one_entry_and_captures_before_after():
    p = plan()
    assert p.ok and p.destination == DEST and p.blocked_by == []
    assert p.before_sha256 == sha(SITEMAP) and p.after_sha256 == sha(p.after_xml) and p.before_sha256 != p.after_sha256
    assert p.after_xml == SITEMAP.replace(f"<loc>{LISTED}</loc>", f"<loc>{DEST}</loc>")
    assert {g.gate for g in p.gates} >= {"publisher_authorized", "listed_url_is_a_permanent_redirect", "same_host_https", "destination_returns_200", "destination_is_not_a_redirect", "destination_is_its_own_canonical",
                                         "destination_not_blocked_by_robots", "only_the_entry_changed", "no_http_redirect_modified", "sitemap_qa:well_formed_xml", "sitemap_qa:entry_count_unchanged"}
    assert p.touched_files == ["sitemap.xml"]


@pytest.mark.parametrize("name,f,gate", [
    ("destination 404", fetcher(**{DEST: (404, {}, "")}), "destination_returns_200"),
    ("destination is itself a redirect", fetcher(**{DEST: (301, {"location": DEST + "x"}, "")}), "destination_returns_200"),
    ("destination 500", fetcher(**{DEST: (500, {}, "")}), "destination_returns_200"),
    ("canonical points at the redirecting URL", fetcher(**{DEST: (200, {}, page(LISTED))}), "destination_is_its_own_canonical"),
    ("no canonical tag (never assumed)", fetcher(**{DEST: (200, {}, page(None))}), "destination_is_its_own_canonical"),
    ("other host", fetcher(**{LISTED: (301, {"location": "https://evil.example/x/"}, "")}), "same_host_https"),
    ("http downgrade", fetcher(**{LISTED: (301, {"location": "http://www.sanocea.com/x/"}, "")}), "same_host_https"),
    ("temporary redirect", fetcher(**{LISTED: (302, {"location": DEST}, "")}), "listed_url_is_a_permanent_redirect"),
    ("listed url is not a redirect", fetcher(**{LISTED: (200, {}, "")}), "listed_url_is_a_permanent_redirect"),
])
def test_each_destination_check_blocks_and_records_the_exact_reason(name, f, gate):
    p = plan(f=f)
    assert p.ok is False and gate in p.blocked_by, name
    assert p.blocked_reason and p.after_xml is None and p.after_sha256 is None, "nothing is prepared when a check fails"
    assert p.before_sha256 == sha(SITEMAP) and p.evidence["listed_url"] == LISTED, "evidence is preserved"
    if gate not in ("listed_url_is_a_permanent_redirect",):
        assert p.evidence.get("listed_status") in (301, 302, 200) and "listed_location_header" in p.evidence, "the observed HTTP facts are kept with the block"
    if gate in ("destination_returns_200", "destination_is_its_own_canonical"):
        assert p.evidence["destination"] == DEST and "destination_status" in p.evidence


def test_canonical_mismatch_explains_it_is_not_a_sitemap_fix_and_never_invents_a_destination():
    p = plan(f=fetcher(**{DEST: (200, {}, page(LISTED))}))
    assert "canonical" in p.blocked_reason and "not a sitemap-entry fix" in p.blocked_reason
    assert p.destination == DEST and p.after_xml is None


def test_robots_blocks_or_unreadable_robots_blocks():
    assert "destination_not_blocked_by_robots" in plan(robots="User-agent: *\nDisallow: /solutions/\n").blocked_by
    assert "destination_not_blocked_by_robots" in plan(robots=None).blocked_by


def test_publisher_authorisation_is_required_and_tenant_scoped():
    for t in (None, PublishTarget(tenant_id="acme", kind="static-site", base_url="https://x", path_prefixes=["/sitemap.xml"]),
              PublishTarget(tenant_id="sanocea", kind="static-site", base_url="https://x", path_prefixes=["/robots.txt"]), PublishTarget(tenant_id="sanocea", kind="website", base_url="https://x", path_prefixes=["/sitemap.xml"])):
        p = plan(target=t)
        assert p.blocked_by == ["publisher_authorized"] and p.after_xml is None


def test_entry_must_be_present_once_and_destination_must_not_already_be_listed():
    assert "entry_present_once" in plan(listed="https://www.sanocea.com/missing").blocked_by
    assert "entry_present_once" in plan(xml=SITEMAP.replace("</urlset>", f"<url><loc>{LISTED}</loc></url></urlset>")).blocked_by
    dup = plan(xml=SITEMAP.replace("</urlset>", f"<url><loc>{DEST}</loc></url></urlset>"))
    assert dup.ok is False and "sitemap_qa:no_duplicate_locs" in dup.blocked_by
    assert "before_state_valid" in plan(xml="<urlset><broken").blocked_by


def test_sitemap_qa_rules_reject_bad_sitemaps():
    bad = SITEMAP.replace("https://www.sanocea.com/about", "http://www.sanocea.com/about")
    assert any(r == "every_loc_absolute_https_same_host" and not ok for r, ok, _ in validate_sitemap(bad, HOST))
    assert any(r == "well_formed_xml" and not ok for r, ok, _ in validate_sitemap("<urlset", HOST))
    assert all(ok for _, ok, _ in validate_sitemap(SITEMAP, HOST, 3))


# ── policy / eligibility ─────────────────────────────────────────────────────

def test_policy_modes_actions_and_approval_gate_the_decision(world):
    root, st = world
    p = plan()
    for mode, ok in [("AUTONOMY_DISABLED", False), ("RECOMMEND_ONLY", False), ("AUTONOMOUS_SEO", True), ("AUTONOMOUS_CONTENT", True), ("AUTONOMOUS_DISTRIBUTION", True)]:
        d = evaluate_sitemap_eligibility(opp(), p, mode, st, "sanocea")
        assert d.eligible is ok and (ok or "tenant_authorization" in d.blocked_by), mode
    for bad_action in ["CHANGE_REDIRECT", "CHANGE_SERVER_RENDERING", "FIX_TECHNICAL_SEO", "DELETE_PAGE"]:
        d = evaluate_sitemap_eligibility(opp(action=bad_action), p, "AUTONOMOUS_DISTRIBUTION", st, "sanocea")
        assert d.eligible is False and d.action_class == "C" and "action_is_fix_sitemap_entry" in d.blocked_by and "tenant_authorization" in d.blocked_by
    assert "standing_approval" in evaluate_sitemap_eligibility(opp(approval=None, status="AWAITING_APPROVAL"), p, "AUTONOMOUS_SEO", st, "sanocea").blocked_by
    assert evaluate_sitemap_eligibility(opp(approval=dict(AUTO, by="human:asha", actorType="HUMAN", policy="human-manual")), p, "AUTONOMOUS_SEO", st, "sanocea").eligible
    blocked = evaluate_sitemap_eligibility(opp(), plan(f=fetcher(**{DEST: (404, {}, "")})), "AUTONOMOUS_SEO", st, "sanocea")
    assert blocked.eligible is False and "destination_returns_200" in blocked.blocked_by


# ── publisher: atomic release, hashes, receipt ───────────────────────────────

def test_publish_creates_a_new_release_and_never_edits_the_live_one_in_place(world):
    root, st = world
    p, d, req = ready(world)
    assert d.eligible
    live_before = os.path.realpath(os.path.join(root, "current"))
    hashes_before = _tree_hashes(live_before)
    pub = StaticSiteReleasePublisher(root, "sanocea")
    r = pub.publish(req, d, st)
    assert r.status == "PUBLISHED" and r.previous_release == "rel-1" and r.new_release != "rel-1" and r.rollback_ref == "rel-1"
    assert [c.path for c in r.changed_files] == ["sitemap.xml"] and r.changed_files[0].before_sha256 == p.before_sha256 and r.changed_files[0].after_sha256 == p.after_sha256
    assert os.path.islink(os.path.join(root, "current")) and os.path.realpath(os.path.join(root, "current")).endswith(r.new_release)
    assert _tree_hashes(live_before) == hashes_before, "the previous release is byte-for-byte untouched"
    new = _tree_hashes(os.path.join(root, "releases", r.new_release))
    assert {k for k in new if new[k] != hashes_before.get(k)} == {"sitemap.xml"}, "only the sitemap differs; redirects/pages/assets are identical"
    assert open(os.path.join(root, "current", "sitemap.xml")).read() == p.after_xml
    assert f"-  <url><loc>{LISTED}</loc>" in r.source_sync_patch and f"+  <url><loc>{DEST}</loc>" in r.source_sync_patch, "a source-sync patch is recorded (the repo source must follow or the next build reverts the change)"
    assert not os.path.lexists(os.path.join(root, "current.tmp"))
    ev = {e["type"] for e in st.audit_events("sanocea")}
    assert {"SITEMAP_ELIGIBILITY_EVALUATED", "SITEMAP_PUBLISHED"} <= ev
    assert st.get_publication("sanocea", req.change_id)["new_release"] == r.new_release


def test_publishing_the_same_change_twice_is_a_noop(world):
    root, st = world
    p, d, req = ready(world)
    pub = StaticSiteReleasePublisher(root, "sanocea")
    r1 = pub.publish(req, d, st)
    n = len(os.listdir(os.path.join(root, "releases")))
    r2 = pub.publish(req, d, st)
    assert r2.status == "NOOP_ALREADY_PUBLISHED" and r2.new_release == r1.new_release
    assert len(os.listdir(os.path.join(root, "releases"))) == n, "no second release"
    assert len([e for e in st.audit_events("sanocea") if e["type"] == "SITEMAP_PUBLISHED"]) == 1


# ── publisher cannot bypass policy ───────────────────────────────────────────

def test_publisher_refuses_ineligible_forged_unsupported_and_out_of_scope_requests(world):
    root, st = world
    pub = StaticSiteReleasePublisher(root, "sanocea")
    p, d, req = ready(world)
    before = _tree_hashes(os.path.realpath(os.path.join(root, "current")))
    nreleases = len(os.listdir(os.path.join(root, "releases")))
    forged = PublishDecision(draft_id=req.change_id, tenant_id="sanocea", action="FIX_SITEMAP_ENTRY", action_class="A", eligible=True, evaluated_at="x", gates=[Gate(gate="x", passed=True, detail="x")], blocked_by=[], status="ELIGIBLE")
    st2 = SeoContentStore(os.path.join(os.path.dirname(root), "other-audit"))
    with pytest.raises(PublisherError) as e: pub.publish(req, forged, st2)
    assert e.value.code == "NO_AUDITED_DECISION", "a decision object alone is not authority"
    blocked = evaluate_sitemap_eligibility(opp(), p, "RECOMMEND_ONLY", st, "sanocea")
    with pytest.raises(PublisherError) as e: pub.publish(req.model_copy(update={"change_id": blocked.draft_id}), blocked, st)
    assert e.value.code == "NOT_ELIGIBLE"
    for action in ["CHANGE_REDIRECT", "CHANGE_SERVER_RENDERING", "CREATE_SEO_PAGE", "UPDATE_EXISTING_PAGE", "CHANGE_INDEXABILITY", "DISTRIBUTE_EXISTING_CONTENT"]:
        with pytest.raises(PublisherError) as e: pub.publish(req.model_copy(update={"action": action}), d.model_copy(update={"action": action}), st)
        assert e.value.code == "UNSUPPORTED_ACTION", action
    for path in ["redirects.conf", "nginx.conf", "index.html", "robots.txt", "../outside.txt"]:
        with pytest.raises(PublisherError) as e: pub.publish(req.model_copy(update={"file_changes": {"sitemap.xml": req.file_changes["sitemap.xml"], path: "x"}}), d, st)
        assert e.value.code == "PATH_NOT_ALLOWED", path
    with pytest.raises(PublisherError) as e: StaticSiteReleasePublisher(root, "acme").publish(req, d, st)
    assert e.value.code == "TENANT_MISMATCH"
    with pytest.raises(PublisherError) as e: pub.publish(req.model_copy(update={"before_sha256": "0" * 64}), d, st)
    assert e.value.code in ("NO_AUDITED_DECISION", "STALE_BEFORE_STATE")
    assert _tree_hashes(os.path.realpath(os.path.join(root, "current"))) == before and len(os.listdir(os.path.join(root, "releases"))) == nreleases, "every refusal left the site untouched"


def test_stale_before_state_is_refused_not_overwritten(world):
    root, st = world
    p, d, req = ready(world)
    with open(os.path.join(root, "current", "sitemap.xml"), "a") as f:
        f.write("<!-- someone else changed it -->")
    with pytest.raises(PublisherError) as e:
        StaticSiteReleasePublisher(root, "sanocea").publish(req, d, st)
    assert e.value.code == "STALE_BEFORE_STATE"


def test_failed_health_check_switches_back_and_records_nothing(world):
    root, st = world
    p, d, req = ready(world)
    with pytest.raises(PublisherError) as e:
        StaticSiteReleasePublisher(root, "sanocea", health_check=lambda rel: False).publish(req, d, st)
    assert e.value.code == "HEALTH_CHECK_FAILED"
    assert os.path.realpath(os.path.join(root, "current")).endswith("rel-1"), "live release restored"
    assert st.get_publication("sanocea", req.change_id) is None


# ── rollback ─────────────────────────────────────────────────────────────────

def test_rollback_restores_the_exact_previous_release_and_state(world):
    root, st = world
    p, d, req = ready(world)
    pub = StaticSiteReleasePublisher(root, "sanocea")
    r = pub.publish(req, d, st)
    rb = pub.rollback(r, st)
    assert rb.restored_release == "rel-1" and rb.live_sha256 == p.before_sha256
    assert os.path.realpath(os.path.join(root, "current")).endswith("rel-1") and open(os.path.join(root, "current", "sitemap.xml")).read() == SITEMAP
    assert any(e["type"] == "SITEMAP_ROLLED_BACK" and e["change_id"] == req.change_id for e in st.audit_events("sanocea"))
    assert os.path.isdir(os.path.join(root, "releases", r.new_release)), "the rolled-back release is kept for inspection"


def test_rollback_refuses_when_something_was_published_after_the_change_or_the_previous_release_was_altered(world, tmp_path):
    root, st = world
    p, d, req = ready(world)
    pub = StaticSiteReleasePublisher(root, "sanocea")
    r = pub.publish(req, d, st)
    later = os.path.join(root, "releases", "later"); os.makedirs(later)
    for n in os.listdir(os.path.join(root, "releases", r.new_release)):
        if os.path.isfile(os.path.join(root, "releases", r.new_release, n)): open(os.path.join(later, n), "w").write(open(os.path.join(root, "releases", r.new_release, n)).read())
    os.replace(os.path.join(root, "current"), os.path.join(root, "current.old")); os.symlink(later, os.path.join(root, "current"))
    with pytest.raises(PublisherError) as e: pub.rollback(r, st)
    assert e.value.code == "ROLLBACK_CONFLICT"
    os.unlink(os.path.join(root, "current")); os.symlink(os.path.join(root, "releases", r.new_release), os.path.join(root, "current"))
    open(os.path.join(root, "releases", "rel-1", "sitemap.xml"), "a").write("tamper")
    with pytest.raises(PublisherError) as e: pub.rollback(r, st)
    assert e.value.code == "PREVIOUS_RELEASE_ALTERED"


# ── tenant isolation ─────────────────────────────────────────────────────────

def test_tenant_isolation_for_decisions_ledger_and_audit(world):
    root, st = world
    p, d, req = ready(world)
    StaticSiteReleasePublisher(root, "sanocea").publish(req, d, st)
    assert st.get_publication("acme", req.change_id) is None and st.audit_events("acme") == []
    d_acme = evaluate_sitemap_eligibility(opp(), plan(tenant="acme", target=PublishTarget(tenant_id="acme", kind="static-site", base_url="https://x", path_prefixes=["/sitemap.xml"])), "AUTONOMOUS_SEO", st, "acme")
    assert d_acme.tenant_id == "acme" and st.audit_events("acme") and all(e["tenant_id"] == "sanocea" for e in st.audit_events("sanocea"))
