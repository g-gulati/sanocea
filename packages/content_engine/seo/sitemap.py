"""FIX_SITEMAP_ENTRY: checks, plan and eligibility. Changes ONE sitemap <loc>; never an HTTP redirect, canonical or page.

A plan is built from observed facts only (injected `fetch`, no network of its own). Nothing is guessed: the destination is the
redirect's own Location header; if it cannot be established as safe the plan is BLOCKED with the exact reason and the evidence."""

from __future__ import annotations

import hashlib
import re
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, Field

from packages.content_engine.seo.brief import valid_approval
from packages.content_engine.seo.policy import Gate, POLICY_REF, PublishDecision, PublishTarget, classify_action, mode_allows
from packages.content_engine.seo.store import SeoContentStore

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAP_PATH = "sitemap.xml"
# fetch(url) -> (status, headers(lower-case keys), body_text). MUST NOT follow redirects.
Fetch = Callable[[str], Tuple[int, Dict[str, str], str]]


class SitemapPlan(BaseModel):
    ok: bool
    action: str = "FIX_SITEMAP_ENTRY"
    listed_url: str
    destination: Optional[str] = None
    gates: List[Gate] = Field(default_factory=list)
    blocked_by: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    before_xml: str = ""
    after_xml: Optional[str] = None
    before_sha256: str = ""
    after_sha256: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    touched_files: List[str] = Field(default_factory=list)  # only the sitemap; asserted by QA and by the publisher


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm(u: str) -> str:
    p = urlsplit(u.strip())
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path}" + (f"?{p.query}" if p.query else "")


def _locs(xml: str) -> List[str]:
    root = ET.fromstring(xml)
    return [(e.text or "").strip() for e in root.iter(f"{{{NS}}}loc")]


def _canonical(html: str) -> Optional[str]:
    m = re.search(r"<link\b[^>]*\brel=[\"']canonical[\"'][^>]*>", html, re.I)
    h = re.search(r"href=[\"']([^\"']+)[\"']", m.group(0), re.I) if m else None
    return h.group(1).strip() if h else None


def validate_sitemap(xml: str, host: str, expected_count: Optional[int] = None) -> List[Tuple[str, bool, str]]:
    """Sitemap QA rules. Each tuple: (rule, passed, detail)."""
    out: List[Tuple[str, bool, str]] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return [("well_formed_xml", False, str(e)[:120])]
    out.append(("well_formed_xml", True, "parses"))
    out.append(("urlset_namespace", root.tag == f"{{{NS}}}urlset", f"root is {root.tag}"))
    locs = _locs(xml)
    out.append(("every_loc_absolute_https_same_host", all(urlsplit(l).scheme == "https" and urlsplit(l).netloc.lower() == host.lower() for l in locs), f"{len(locs)} locs, host {host}"))
    out.append(("no_duplicate_locs", len({_norm(l) for l in locs}) == len(locs), "no duplicates" if len({_norm(l) for l in locs}) == len(locs) else "duplicate loc present"))
    out.append(("within_protocol_limits", len(locs) <= 50000 and len(xml.encode()) <= 52_428_800, f"{len(locs)} urls"))
    if expected_count is not None:
        out.append(("entry_count_unchanged", len(locs) == expected_count, f"{len(locs)} vs {expected_count}"))
    return out


def plan_sitemap_fix(listed_url: str, sitemap_xml: str, tenant_host: str, fetch: Fetch, robots_txt: Optional[str], target: Optional[PublishTarget], tenant_id: str) -> SitemapPlan:
    gates: List[Gate] = []
    ev: Dict[str, Any] = {"listed_url": listed_url}
    plan = SitemapPlan(ok=False, listed_url=listed_url, before_xml=sitemap_xml, before_sha256=sha(sitemap_xml), evidence=ev, touched_files=[SITEMAP_PATH])

    def g(name: str, ok: bool, detail: str) -> bool:
        gates.append(Gate(gate=name, passed=bool(ok), detail=detail))
        return bool(ok)

    def stop(reason: str) -> SitemapPlan:
        plan.gates, plan.blocked_by = gates, [x.gate for x in gates if not x.passed]
        plan.blocked_reason = reason
        plan.evidence = dict(ev)  # observed facts are preserved with the block
        return plan

    # 7. publisher authorised (checked first: nothing else matters if we may not write)
    if not g("publisher_authorized", bool(target and target.tenant_id == tenant_id and target.kind == "static-site" and any(SITEMAP_PATH == p.lstrip("/") for p in target.path_prefixes)),
             "publish target covers /sitemap.xml for this tenant" if target and target.tenant_id == tenant_id else "no authorised static-site publish target covering /sitemap.xml for this tenant"):
        return stop("The sitemap publisher is not authorised for this tenant.")
    # before-state present and the entry is in it exactly once
    try:
        locs = _locs(sitemap_xml)
    except ET.ParseError as e:
        g("before_state_valid", False, f"current sitemap does not parse: {e}")
        return stop("The current sitemap is not valid XML; nothing was changed.")
    n = [l for l in locs if _norm(l) == _norm(listed_url)]
    if not g("entry_present_once", len(n) == 1, f"{len(n)} matching <loc> entries"):
        return stop("The listed URL is not present exactly once in the current sitemap.")
    # 1. resolve (no following)
    st, hd, _ = fetch(listed_url)
    ev["listed_status"], ev["listed_location_header"] = st, hd.get("location")
    if not g("listed_url_is_a_permanent_redirect", st in (301, 308) and bool(hd.get("location")), f"HTTP {st}, Location {hd.get('location')!r}"):
        return stop("The listed URL is not a permanent redirect with a Location header; there is no observed destination to use.")
    dest = urljoin(listed_url, hd["location"])
    plan.destination = ev["destination"] = dest
    # 4. same host
    same = urlsplit(dest).netloc.lower() == tenant_host.lower() == urlsplit(listed_url).netloc.lower() and urlsplit(dest).scheme == "https"
    if not g("same_host_https", same, f"destination host {urlsplit(dest).netloc}, tenant host {tenant_host}"):
        return stop("The redirect destination is on a different host or not https; refusing to put it in this tenant's sitemap.")
    # 2 + 5. destination is a final 200 (not itself a redirect)
    dst, dhd, dbody = fetch(dest)
    ev["destination_status"] = dst
    if not g("destination_returns_200", dst == 200, f"HTTP {dst}"):
        return stop(f"The destination returned HTTP {dst}, not 200.")
    g("destination_is_not_a_redirect", dst not in (301, 302, 303, 307, 308) and not dhd.get("location"), "final response, no Location header")
    # 3. canonical for itself (explicit tag required; absence is not assumed)
    canon = _canonical(dbody)
    ev["destination_canonical"] = canon
    if not g("destination_is_its_own_canonical", bool(canon) and _norm(canon) == _norm(dest), f"canonical {canon!r} vs destination {dest!r}"):
        return stop(f"The destination's own canonical is {canon!r}, not the destination. Putting the destination in the sitemap would contradict the page's canonical; the correct fix is a canonical/redirect decision (not a sitemap-entry fix).")
    # 6. robots
    if robots_txt is not None:
        rp = urllib.robotparser.RobotFileParser(); rp.parse(robots_txt.splitlines())
        if not g("destination_not_blocked_by_robots", rp.can_fetch("*", dest), "allowed for User-agent: *" if rp.can_fetch("*", dest) else "disallowed for User-agent: *"):
            return stop("robots.txt blocks the destination.")
    else:
        g("destination_not_blocked_by_robots", False, "robots.txt could not be read")
        return stop("robots.txt could not be read; cannot confirm the destination is crawlable.")
    # 9. apply ONLY the entry change (exact, single replacement)
    needle = f"<loc>{n[0]}</loc>"
    if sitemap_xml.count(needle) != 1:
        g("single_exact_replacement", False, f"{sitemap_xml.count(needle)} exact occurrences of the entry text")
        return stop("The entry could not be replaced unambiguously.")
    after = sitemap_xml.replace(needle, f"<loc>{dest}</loc>", 1)
    # 10 + 12. validate the result and prove only that entry changed
    rules = validate_sitemap(after, tenant_host, expected_count=len(locs))
    for rule, ok, detail in rules:
        g("sitemap_qa:" + rule, ok, detail)
    a_locs = _locs(after) if all(ok for _, ok, _ in rules[:1]) else []
    only_entry = [i for i, (x, y) in enumerate(zip(locs, a_locs)) if x != y] == [locs.index(n[0])] and len(a_locs) == len(locs)
    g("only_the_entry_changed", only_entry and re.sub(r"<loc>[^<]*</loc>", "<loc/>", after) == re.sub(r"<loc>[^<]*</loc>", "<loc/>", sitemap_xml), "every other element and entry is byte-identical")
    g("no_http_redirect_modified", plan.touched_files == [SITEMAP_PATH], "the change set contains the sitemap file only")
    plan.after_xml, plan.after_sha256 = after, sha(after)
    plan.evidence = dict(ev)
    plan.gates, plan.blocked_by = gates, [x.gate for x in gates if not x.passed]
    plan.ok = not plan.blocked_by
    if not plan.ok:
        plan.blocked_reason = "; ".join(x.detail for x in gates if not x.passed)
    return plan


def change_id_for(tenant_id: str, opportunity_id: str, plan: SitemapPlan) -> str:
    return "chg_" + hashlib.sha1(f"{tenant_id}|{opportunity_id}|FIX_SITEMAP_ENTRY|{plan.listed_url}|{plan.after_sha256}".encode()).hexdigest()[:12]


def evaluate_sitemap_eligibility(opp: Dict[str, Any], plan: SitemapPlan, mode: str, store: SeoContentStore, tenant_id: str, now: Optional[str] = None) -> PublishDecision:
    """Policy + plan gates -> a persisted decision. The publisher will only act on a decision whose digest is in the audit log."""
    now = now or datetime.now(timezone.utc).isoformat()
    action = (opp.get("decision") or {}).get("action") or opp.get("recommendedAction")
    cls = classify_action(action)
    gates: List[Gate] = []
    gates.append(Gate(gate="action_is_fix_sitemap_entry", passed=action == "FIX_SITEMAP_ENTRY", detail=f"action {action} (class {cls})"))
    gates.append(Gate(gate="evidence_backed_opportunity", passed=bool(opp.get("evidence")) and bool(opp.get("source")), detail=str(opp.get("source"))))
    ok_ap, why = valid_approval(opp.get("approval"))
    gates.append(Gate(gate="standing_approval", passed=ok_ap and opp.get("status") in ("APPROVED", "IN_PROGRESS"), detail=f"{why}; status {opp.get('status')}"))
    allowed, reason = mode_allows(mode, cls, action)
    gates.append(Gate(gate="tenant_authorization", passed=allowed, detail=reason))
    gates += plan.gates
    gates.append(Gate(gate="before_after_state_captured", passed=bool(plan.before_sha256 and plan.after_sha256), detail=f"{plan.before_sha256[:12]} -> {(plan.after_sha256 or '')[:12]}"))
    cid = change_id_for(tenant_id, opp["opportunityId"], plan) if plan.after_sha256 else "chg_blocked"
    blocked = [x.gate for x in gates if not x.passed]
    digest = hashlib.sha1(f"{cid}|{action}|{sorted(blocked)}|{plan.before_sha256}|{plan.after_sha256}".encode()).hexdigest()[:16]
    store.append_audit(tenant_id, "evt_" + digest, {"type": "SITEMAP_ELIGIBILITY_EVALUATED", "change_id": cid, "opportunity_id": opp["opportunityId"], "action": action, "action_class": cls,
                                                    "eligible": not blocked, "blocked_by": blocked, "policy": POLICY_REF, "actor_type": "AUTONOMOUS_AGENT", "at": now,
                                                    "before_sha256": plan.before_sha256, "after_sha256": plan.after_sha256, "digest": digest})
    return PublishDecision(draft_id=cid, tenant_id=tenant_id, action=action, action_class=cls, eligible=not blocked, evaluated_at=now, gates=gates, blocked_by=blocked, status="ELIGIBLE" if not blocked else "BLOCKED")
