"""Executor bridge: the SEO worker (Node) invokes this module to carry out an ALREADY-AUTHORISED change and to re-observe it.

    echo '{"command": "execute" | "observe" | "rollback", ...}' | python -m packages.content_engine.seo.executor   -> one JSON object on stdout

It decides nothing about whether work is permitted: the worker's autonomy policy authorised it (approval is part of the input) and
publish eligibility (plan gates + policy gates + audit event) is re-evaluated here, so the publisher still refuses anything not
eligible. The tenant -> publish-target binding comes from config/seo_publish_targets.json; a tenant without an entry cannot publish.

Source of truth: the repository file the site build copies into the release must equal the live file before publication (else
BLOCKED: the next deploy would silently revert or fight the change), and it is updated + committed (that one path only) afterwards.
Every outcome is a JSON status; nothing is raised across the process boundary except as {"status": "ERROR"}."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from packages.content_engine.seo.policy import PublishTarget
from packages.content_engine.seo.publisher import PublishReceipt, PublishRequest, PublisherError, StaticSiteReleasePublisher
from packages.content_engine.seo.sitemap import SITEMAP_PATH, _canonical, _locs, _norm, evaluate_sitemap_eligibility, plan_sitemap_fix, sha
from packages.content_engine.seo.pageedit import evaluate_page_edit_eligibility, page_file_for, plan_canonical_fix
from packages.content_engine.seo.source import OpportunitySource
from packages.content_engine.seo.store import SeoContentStore

Fetch = Callable[[str], Tuple[int, Dict[str, str], str]]
OBS_SRC = "[OBSERVED: LIVE POST-PUBLICATION FETCH]"
SUPPORTED = ("FIX_SITEMAP_ENTRY", "CHANGE_CANONICAL")


def targets_path() -> str:
    return os.environ.get("SEO_PUBLISH_TARGETS", os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "seo_publish_targets.json"))


def load_target(tenant_id: str) -> Optional[Dict[str, Any]]:
    try:
        with open(targets_path(), "r", encoding="utf-8") as f:
            t = json.load(f).get("targets", {}).get(tenant_id)
    except (OSError, ValueError):
        return None
    return t if isinstance(t, dict) and t.get("kind") == "static-site" and t.get("www_root") and t.get("host") else None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # never follow: the 3xx itself is the observation
        return None


def make_fetch(host: str, timeout: float = 15.0) -> Fetch:
    """HTTP GET that does NOT follow redirects and refuses any host other than the tenant's own (no open fetcher)."""
    opener = urllib.request.build_opener(_NoRedirect)

    def fetch(url: str) -> Tuple[int, Dict[str, str], str]:
        p = urlsplit(url)
        if p.scheme != "https" or p.netloc.lower() != host.lower():
            return 0, {}, ""
        try:
            with opener.open(urllib.request.Request(url, headers={"User-Agent": "SanoceaSEO-Executor/1.0"}), timeout=timeout) as r:  # noqa: S310 (host-restricted above)
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(2_000_000).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, ""
        except Exception:
            return 0, {}, ""  # unobservable: callers must treat 0 as "could not observe", never as a result

    return fetch


def _publisher(tenant_id: str, tgt: Dict[str, Any], fetch: Fetch) -> StaticSiteReleasePublisher:
    def healthy(_release: str) -> bool:
        return all(fetch(u)[0] == 200 for u in tgt.get("health_urls", []))
    return StaticSiteReleasePublisher(tgt["www_root"], tenant_id, health_check=healthy if tgt.get("health_urls") else None)


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=60)


def _commit_source(repo: str, rel: str, message: str) -> Optional[str]:
    """Commit exactly one path (never `git add -A`); returns the commit sha or None."""
    if _git(repo, "add", "--", rel).returncode != 0:
        return None
    c = _git(repo, "commit", "-m", message, "--only", "--", rel)
    return _git(repo, "rev-parse", "HEAD").stdout.strip() if c.returncode == 0 else None


def _result(status: str, **kw: Any) -> Dict[str, Any]:
    return {"status": status, **kw}


def _expected(opp: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = opp.get("actionPlan") or {}
    sel = next((c for c in plan.get("candidates", []) if c.get("action") == plan.get("selected")), None)
    return list((sel or {}).get("expected_outcome", []))


def _publication_for_opportunity(store: SeoContentStore, tenant: str, opportunity_id: str, action: str, since: str) -> Optional[Dict[str, Any]]:
    """A publication by THIS opportunity, for THIS action, made since the current approval was given. An opportunity can carry several
    changes over its life (e.g. canonical, then sitemap), so only the current approval cycle's change counts as a crash-resume match."""
    d = os.path.join(store._dir(tenant), "publications")
    if not os.path.isdir(d):
        return None
    for n in sorted(os.listdir(d)):
        rec = store._read(os.path.join(d, n))
        if rec and rec.get("opportunity_id") == opportunity_id and rec.get("action") == action and rec.get("status") in ("PUBLISHED", "NOOP_ALREADY_PUBLISHED") and str(rec.get("published_at", "")) >= since:
            return rec
    return None


def _authority(tenant: str, opportunity_id: str, source: Optional[OpportunitySource]) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    """The opportunity, its approval and the tenant mode as the WORKER holds them (its persisted policy decision).
    Whatever the caller put in the request about approval, status or mode is never used: a forged request authorises nothing."""
    src = source or OpportunitySource()
    try:
        opp, mode = src.get(opportunity_id), src.autonomy().get("mode", "RECOMMEND_ONLY")
    except Exception as e:
        return None, "RECOMMEND_ONLY", f"the worker's persisted policy state could not be read ({type(e).__name__}); nothing is executed without it"
    if not opp or opp.get("tenantId") != tenant:
        return None, mode, "no such opportunity for this tenant in the worker's state"
    return opp, mode, None


def execute(p: Dict[str, Any], fetch: Optional[Fetch] = None, store: Optional[SeoContentStore] = None, now: Optional[datetime] = None, source: Optional[OpportunitySource] = None) -> Dict[str, Any]:
    tenant = p["tenant_id"]
    opp, mode, why = _authority(tenant, p.get("opportunity_id", ""), source)
    if opp is None:
        return _result("BLOCKED", blocked_by=["worker_policy_state"], reason=why)
    if opp.get("status") not in ("APPROVED", "IN_PROGRESS") or not opp.get("approval"):
        return _result("BLOCKED", blocked_by=["standing_approval"], reason=f"The worker records this opportunity as {opp.get('status')} with {'an' if opp.get('approval') else 'no'} approval; only an approved opportunity is executed.")
    action = (opp.get("decision") or {}).get("action") or opp.get("recommendedAction")
    if action not in SUPPORTED:
        return _result("UNSUPPORTED", reason=f"{action} has no supported publisher")
    tgt = load_target(tenant)
    if not tgt:
        return _result("BLOCKED", blocked_by=["publish_target_configured"], reason="No authorised publish target is configured for this tenant.")
    fetch = fetch or make_fetch(tgt["host"])
    store = store or SeoContentStore()
    since = str((opp.get("approval") or {}).get("at", ""))
    prior_pub = _publication_for_opportunity(store, tenant, opp["opportunityId"], action, since)
    if prior_pub and not any(e.get("event_id") in ("evt_rb_" + prior_pub["change_id"], "evt_vrb_" + prior_pub["change_id"]) for e in store.audit_events(tenant)):
        return _result("ALREADY_PUBLISHED", receipt={k: v for k, v in prior_pub.items() if k not in ("key", "tenant_id_")}, change_id=prior_pub["change_id"])  # crash-safe resume: never apply twice
    pub = _publisher(tenant, tgt, fetch)
    target = PublishTarget(tenant_id=tenant, kind="static-site", base_url=tgt["base_url"], path_prefixes=list(tgt["path_prefixes"]))
    listed = (opp.get("evidence") or {}).get("listedUrl")
    if not listed:
        return _result("BLOCKED", blocked_by=["listed_url_known"], reason="The opportunity records no listed URL.")
    try:
        robots = pub.live_file("robots.txt")
    except OSError:
        robots = None
    intended = (opp.get("diagnosis") or {}).get("intended")
    if action == "CHANGE_CANONICAL":
        if not intended:
            return _result("BLOCKED", blocked_by=["intended_address_established"], reason="The worker's diagnosis has not established which address is intended.")
        rel = page_file_for(intended)
        if not rel:
            return _result("BLOCKED", blocked_by=["page_file_resolved"], reason="The intended address does not map to a single page file.")
    else:
        rel = SITEMAP_PATH
    try:
        live_text = pub.live_file(rel)
    except OSError:
        return _result("BLOCKED", blocked_by=["live_file_readable"], reason=f"{rel} could not be read from the live release.")
    # Source-of-truth gate: the repo file the build uses must correspond to the live file, or the next deploy would fight this change.
    src_rel = (tgt.get("source_files") or {}).get(rel)
    src_abs = os.path.join(tgt["source_repo"], src_rel) if src_rel else None
    if not src_abs or not os.path.isfile(src_abs):
        return _result("BLOCKED", blocked_by=["source_of_truth_known"], reason=f"No repository source file is configured for the live {rel}.")
    with open(src_abs, encoding="utf-8") as f:
        src_text = f.read()
    if action == "FIX_SITEMAP_ENTRY":  # copied verbatim by the build: must be byte-identical
        if sha(src_text) != sha(live_text):
            return _result("BLOCKED", blocked_by=["source_of_truth_matches_live"],
                           reason=f"{src_rel} differs from the live sitemap; publishing would be reverted by, or conflict with, the next deploy. Reconcile the source first.")
        plan = plan_sitemap_fix(listed, live_text, tgt["host"], fetch, robots, target, tenant)
        decision = evaluate_sitemap_eligibility(opp, plan, mode, store, tenant)
        new_text, new_src_text, destination, summary = plan.after_xml, plan.after_xml, plan.destination, f"sitemap entry {listed} -> {plan.destination}"
    else:  # a built page: the build rewrites asset paths, so correspondence is checked on the declared addresses (see plan gate)
        plan = plan_canonical_fix(listed, intended, intended, live_text, src_text, tgt["host"], fetch, robots, target, tenant)
        decision = evaluate_page_edit_eligibility(opp, plan, mode, store, tenant)
        new_text, new_src_text, destination, summary = plan.after_html, plan.source_after_html, intended, f"page address declarations {listed} -> {intended} in {rel}"
    if not plan.ok or not decision.eligible:
        return _result("BLOCKED", blocked_by=decision.blocked_by, reason=plan.blocked_reason or "; ".join(g.detail for g in decision.gates if not g.passed),
                       gates=[g.model_dump() for g in decision.gates], evidence=plan.evidence)
    change_id = decision.draft_id
    if p.get("dry_run"):
        return _result("ELIGIBLE", change_id=change_id, destination=destination)
    if store.get_publication(tenant, change_id) and any(e.get("event_id") in ("evt_rb_" + change_id, "evt_vrb_" + change_id) for e in store.audit_events(tenant)):
        return _result("BLOCKED", blocked_by=["previously_rolled_back"], reason="This exact change was published and then rolled back; it will not be re-applied without new evidence.")
    req = PublishRequest(tenant_id=tenant, opportunity_id=opp["opportunityId"], change_id=change_id, action=action, target=listed, file_changes={rel: new_text or ""},
                         before_sha256=plan.before_sha256, after_sha256=plan.after_sha256 or "", expected_outcome=_expected(opp), source_path=src_rel)
    try:
        receipt = pub.publish(req, decision, store)
    except PublisherError as e:
        return _result("BLOCKED" if e.code in ("NOT_ELIGIBLE", "STALE_BEFORE_STATE", "NO_AUDITED_DECISION", "HEALTH_CHECK_FAILED") else "ERROR", blocked_by=[e.code], reason=str(e))
    out: Dict[str, Any] = {"receipt": json.loads(receipt.model_dump_json()), "change_id": change_id}
    if receipt.status == "PUBLISHED":  # keep the repository source in step so the next full build does not revert this
        with open(src_abs, "w", encoding="utf-8") as f:
            f.write(new_src_text or "")
        commit = _commit_source(tgt["source_repo"], src_rel, f"seo(autonomous): {receipt.change_id} {summary}\n\nPublished by the SEO executor under {decision.policy}; release {receipt.new_release}.") if tgt.get("commit_source") else None
        store._write(os.path.join(store._dir(tenant), "source_sync", change_id + ".json"), {"path": src_rel, "before_text": src_text, "after_text": new_src_text, "commit": commit})
        out["source_sync"] = {"path": src_rel, "commit": commit}
    return _result("PUBLISHED" if receipt.status == "PUBLISHED" else "ALREADY_PUBLISHED", **out)


def observe(p: Dict[str, Any], fetch: Optional[Fetch] = None, store: Optional[SeoContentStore] = None) -> Dict[str, Any]:
    """Re-observe the LIVE site for each expectation. If anything cannot be observed, `observable` is False and no verdict may be drawn."""
    tenant = p["tenant_id"]
    tgt = load_target(tenant)
    if not tgt:
        return _result("ERROR", reason="no publish target for tenant", observable=False, facts=[])
    fetch = fetch or make_fetch(tgt["host"])
    expected = p.get("expected_outcome", [])
    if p.get("change_id"):  # the outcome recorded WHEN the change was published; the opportunity's plan may have moved on since
        rec = (store or SeoContentStore()).get_publication(tenant, p["change_id"])
        if not rec:
            return _result("ERROR", reason="no publication record for this change", observable=False, facts=[])
        expected = rec.get("expected_outcome", [])
    facts: List[Dict[str, Any]] = []
    unobservable: List[str] = []

    def fact(kind: str, subject: str, value: Optional[str]) -> None:
        facts.append({"id": f"fact:{kind}:" + hashlib.sha1(f"{subject}|{value}".encode()).hexdigest()[:8], "kind": kind, "subject": subject, "value": value, "source": OBS_SRC})

    # The public sitemap as served (not the on-disk file): this is what Google reads.
    st, _, body = fetch(tgt["base_url"].rstrip("/") + "/" + SITEMAP_PATH)
    locs: Optional[List[str]] = None
    if st == 200:
        try:
            locs = [_norm(x) for x in _locs(body)]
        except Exception:
            locs = None
    for e in expected:
        kind, subject = e.get("kind"), e.get("subject", "")
        if kind == "sitemap_lists":
            if locs is None:
                unobservable.append(f"sitemap_lists {subject}")
            elif _norm(subject) in locs:
                fact(kind, subject, subject)
        elif kind == "redirects_to":
            s, h, _ = fetch(subject)
            if s in (301, 302, 303, 307, 308) and h.get("location"):
                fact(kind, subject, h["location"])
            elif s != 200:
                unobservable.append(f"redirects_to {subject} (HTTP {s})")
        elif kind == "destination_canonical":
            s, _, b = fetch(subject)
            if s != 200:
                unobservable.append(f"destination_canonical {subject} (HTTP {s})")
            else:
                fact(kind, subject, _canonical(b))
        else:
            unobservable.append(f"{kind} (no observer)")
    return _result("OBSERVED", observable=not unobservable, unobservable=unobservable, facts=facts, expected_outcome=expected)


def rollback(p: Dict[str, Any], fetch: Optional[Fetch] = None, store: Optional[SeoContentStore] = None, source: Optional[OpportunitySource] = None) -> Dict[str, Any]:
    tenant, change_id = p["tenant_id"], p["change_id"]
    opp, _, why = _authority(tenant, p.get("opportunity_id", ""), source)
    if opp is None or opp.get("resultingAction") != f"change:{change_id}" or opp.get("status") not in ("COMPLETED", "MEASURING"):
        return _result("BLOCKED", blocked_by=["worker_policy_state"], reason=why or "The worker does not record this change as the executed result of a completed opportunity; it will not be rolled back on request alone.")
    tgt = load_target(tenant)
    if not tgt:
        return _result("ERROR", reason="no publish target for tenant")
    store = store or SeoContentStore()
    rec = store.get_publication(tenant, change_id)
    if not rec:
        return _result("ERROR", reason="no publication record for this change")
    pub = _publisher(tenant, tgt, fetch or make_fetch(tgt["host"]))
    receipt = PublishReceipt(**{k: v for k, v in rec.items() if k not in ("key", "tenant_id_")})
    try:
        rb = pub.rollback(receipt, store)
    except PublisherError as e:
        return _result("ROLLBACK_UNAVAILABLE", code=e.code, reason=str(e))
    sync = store._read(os.path.join(store._dir(tenant), "source_sync", change_id + ".json"))
    source_restored = False
    if sync:
        abs_ = os.path.join(tgt["source_repo"], sync["path"])
        if os.path.isfile(abs_):
            with open(abs_, encoding="utf-8") as f:
                unchanged = sha(f.read()) == sha(sync["after_text"])
            if unchanged:  # only restore if nobody has edited the source since
                with open(abs_, "w", encoding="utf-8") as f:
                    f.write(sync["before_text"])
                if tgt.get("commit_source"):
                    _commit_source(tgt["source_repo"], sync["path"], f"seo(autonomous): roll back {change_id} (verification contradicted the expected outcome)")
                source_restored = True
    return _result("ROLLED_BACK", restored_release=rb.restored_release, live_sha256=rb.live_sha256, source_restored=source_restored)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        out = {"execute": execute, "observe": observe, "rollback": rollback}[payload.get("command")](payload)
    except Exception as e:  # never a traceback across the process boundary
        out = _result("ERROR", reason=f"{type(e).__name__}: {str(e)[:300]}")
    sys.stdout.write(json.dumps(out, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
