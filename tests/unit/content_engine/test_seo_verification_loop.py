"""Closed loop after autonomous publication: publish -> RE-OBSERVE -> verify -> learn / rollback / investigate."""
import os

import pytest

from packages.content_engine.seo.publisher import PublishRequest, StaticSiteReleasePublisher
from packages.content_engine.seo.sitemap import evaluate_sitemap_eligibility, plan_sitemap_fix
from packages.content_engine.seo.source import OpportunityControl
from packages.content_engine.seo.verify import observe_sitemap_facts, verify_publication
from tests.unit.content_engine.test_seo_sitemap_publisher import AUTO, DEST, HOST, LISTED, ROBOTS, SITEMAP, TARGET, fetcher, opp, world  # noqa


EXPECT = [{"kind": "sitemap_lists", "subject": DEST, "equals": DEST}, {"kind": "sitemap_lists", "subject": LISTED, "absent": True}, {"kind": "redirects_to", "subject": DEST, "absent": True}]


class Judge(OpportunityControl):
    """Stands in for the worker's verifyOutcome (already tested in TypeScript); implements the same contract on the same expectations."""
    def __init__(self):
        self.calls = []
        super().__init__(post_json=self._post)

    def _post(self, path, body):
        self.calls.append((path, body))
        obs = body["observed"]
        checks = []
        for e in EXPECT:
            f = [o for o in obs if o["kind"] == e["kind"] and o["subject"] == e["subject"]]
            checks.append(None if (not e.get("absent") and not f) else (not f) if e.get("absent") else any(o["value"] == e["equals"] for o in f))
        if any(c is False for c in checks):
            return {"status": "NOT_MET", "next": "ROLLBACK" if body["rollbackAvailable"] else "INVESTIGATE", "reason": "contradicted", "checks": checks}
        if any(c is None for c in checks):
            return {"status": "INCONCLUSIVE", "next": "INVESTIGATE", "reason": "facts missing", "checks": checks}
        return {"status": "MET", "next": "LEARN", "reason": "ok", "checks": checks}


def published(world):
    root, st = world
    p = plan_sitemap_fix(LISTED, SITEMAP, HOST, fetcher(), ROBOTS, TARGET, "sanocea")
    d = evaluate_sitemap_eligibility(opp(), p, "AUTONOMOUS_SEO", st, "sanocea")
    req = PublishRequest(tenant_id="sanocea", opportunity_id="OPP-S1", change_id=d.draft_id, action="FIX_SITEMAP_ENTRY", target="/sitemap.xml", file_changes={"sitemap.xml": p.after_xml},
                         before_sha256=p.before_sha256, after_sha256=p.after_sha256, expected_outcome=EXPECT)
    pub = StaticSiteReleasePublisher(root, "sanocea")
    return pub, st, pub.publish(req, d, st), root


def test_receipt_carries_what_verification_needs(world):
    pub, st, r, root = published(world)
    assert r.opportunity_id == "OPP-S1" and r.expected_outcome == EXPECT and r.verification_required
    assert r.target == "/sitemap.xml" and r.previous_release == "rel-1" and r.rollback_ref == "rel-1" and r.published_at and r.changed_files[0].before_sha256 != r.changed_files[0].after_sha256


def test_met_is_learned_from_RE_OBSERVED_facts_not_from_the_publisher_result(world):
    pub, st, r, root = published(world)
    live = open(os.path.join(root, "current", "sitemap.xml")).read()
    facts = observe_sitemap_facts(live, LISTED, DEST, fetcher(**{DEST: (200, {}, "")}))
    assert {f["kind"] for f in facts} == {"sitemap_lists"} and all(f["source"].startswith("[OBSERVED: LIVE POST") for f in facts)
    out = verify_publication(r, facts, Judge(), pub, st)
    assert out["verification"]["status"] == "MET" and out["action_taken"] == "LEARNED"
    assert os.path.realpath(os.path.join(root, "current")).endswith(r.new_release), "a successful change stays live"
    assert any(e["type"] == "VERIFICATION_MET" for e in st.audit_events("sanocea"))


def test_not_met_rolls_back_to_the_exact_previous_release(world):
    pub, st, r, root = published(world)
    # live observation contradicts the expectation (the old entry is still present)
    facts = observe_sitemap_facts(SITEMAP, LISTED, DEST, fetcher(**{DEST: (200, {}, "")}))
    out = verify_publication(r, facts, Judge(), pub, st)
    assert out["verification"]["status"] == "NOT_MET" and out["action_taken"] == "ROLLED_BACK"
    assert os.path.realpath(os.path.join(root, "current")).endswith("rel-1") and open(os.path.join(root, "current", "sitemap.xml")).read() == SITEMAP
    ev = {e["type"] for e in st.audit_events("sanocea")}
    assert {"SITEMAP_ROLLED_BACK", "VERIFICATION_ROLLBACK"} <= ev


def test_not_met_without_a_valid_rollback_investigates_instead_of_pretending(world):
    pub, st, r, root = published(world)
    os.replace(os.path.join(root, "current"), os.path.join(root, "current.x"))
    later = os.path.join(root, "releases", "later"); os.makedirs(later); open(os.path.join(later, "sitemap.xml"), "w").write(SITEMAP)
    os.symlink(later, os.path.join(root, "current"))  # something else is live now: rollback would undo it
    out = verify_publication(r, observe_sitemap_facts(SITEMAP, LISTED, DEST, fetcher(**{DEST: (200, {}, "")})), Judge(), pub, st)
    assert out["action_taken"] == "INVESTIGATE_ROLLBACK_UNAVAILABLE" and os.path.realpath(os.path.join(root, "current")) == os.path.realpath(later)


def test_inconclusive_and_unobservable_never_count_as_success(world):
    pub, st, r, root = published(world)
    assert observe_sitemap_facts("<urlset><broken", LISTED, DEST, fetcher()) == [], "unreadable live sitemap => no facts"
    assert observe_sitemap_facts(SITEMAP, LISTED, DEST, fetcher(**{DEST: (500, {}, "")})) == [], "destination unobservable => no facts"
    out = verify_publication(r, [], Judge(), pub, st)
    assert out["verification"]["status"] == "INCONCLUSIVE" and out["action_taken"] == "INVESTIGATE"
    assert os.path.realpath(os.path.join(root, "current")).endswith(r.new_release), "inconclusive does not roll back and does not claim success"
    assert not any(e["type"] == "VERIFICATION_MET" for e in st.audit_events("sanocea"))
    # the destination redirecting again contradicts the expectation
    again = observe_sitemap_facts(open(os.path.join(root, "current", "sitemap.xml")).read(), LISTED, DEST, fetcher(**{DEST: (301, {"location": DEST + "x"}, "")}))
    assert verify_publication(r, again, Judge(), pub, st)["verification"]["status"] == "NOT_MET"
