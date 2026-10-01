"""CHANGE_CANONICAL: plan and eligibility for correcting the address a static page DECLARES for itself. Changes nothing else.

The edit is the narrowest one that removes the conflict: every double-quoted occurrence of the wrong address (the page's canonical
tag, og:url, JSON-LD url / @id / item, breadcrumb items) becomes the intended address. No other byte of the page changes, no HTTP
redirect is touched, nothing outside the one page file is written. The intended address is NOT decided here: it comes from the
worker's diagnosis (authoritative state), and the plan only proceeds if the live site agrees with it (the wrong address redirects
to the intended one, which serves the page with HTTP 200 and is indexable and not blocked by robots.txt)."""

from __future__ import annotations

import hashlib
import re
import urllib.robotparser
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, Field

from packages.content_engine.seo.brief import valid_approval
from packages.content_engine.seo.policy import Gate, POLICY_REF, PublishDecision, PublishTarget, classify_action, mode_allows
from packages.content_engine.seo.sitemap import Fetch, _canonical, _norm, sha
from packages.content_engine.seo.store import SeoContentStore

ACTION = "CHANGE_CANONICAL"


class PageEditPlan(BaseModel):
    ok: bool
    action: str = ACTION
    wrong_url: str
    intended_url: str
    page_file: Optional[str] = None
    gates: List[Gate] = Field(default_factory=list)
    blocked_by: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    before_html: str = ""
    after_html: Optional[str] = None
    before_sha256: str = ""
    after_sha256: Optional[str] = None
    source_after_html: Optional[str] = None
    replacements: int = 0
    evidence: Dict[str, Any] = Field(default_factory=dict)


def page_file_for(url: str) -> Optional[str]:
    """Release-relative file that serves a directory-style page URL (/a/b/ -> a/b/index.html). None for anything unexpected."""
    p = urlsplit(url).path
    if not p.endswith("/") or ".." in p or "//" in p.replace("://", ""):
        return None
    rel = p.strip("/") + "/index.html"
    return rel if re.fullmatch(r"[a-z0-9][a-z0-9/_-]*/index\.html", rel) else None


def _swap(text: str, wrong: str, intended: str) -> Tuple[str, int]:
    token = f'"{wrong}"'
    return text.replace(token, f'"{intended}"'), text.count(token)


def plan_canonical_fix(wrong: str, intended: str, authoritative_intended: Optional[str], live_html: str, source_html: Optional[str], tenant_host: str, fetch: Fetch,
                       robots_txt: Optional[str], target: Optional[PublishTarget], tenant_id: str) -> PageEditPlan:
    gates: List[Gate] = []
    ev: Dict[str, Any] = {"wrong_url": wrong, "intended_url": intended}
    plan = PageEditPlan(ok=False, wrong_url=wrong, intended_url=intended, before_html=live_html, before_sha256=sha(live_html), evidence=ev)

    def g(name: str, ok: bool, detail: str) -> bool:
        gates.append(Gate(gate=name, passed=bool(ok), detail=detail))
        return bool(ok)

    def stop(reason: str) -> PageEditPlan:
        plan.gates, plan.blocked_by, plan.blocked_reason = gates, [x.gate for x in gates if not x.passed], reason
        return plan

    rel = page_file_for(intended)
    plan.page_file = rel
    if not g("page_file_resolved", rel is not None, f"{intended} is served from {rel}" if rel else "the intended address does not map to a directory-style page file"):
        return stop("The intended address does not map to exactly one page file.")
    path = urlsplit(intended).path
    if not g("publisher_authorized", bool(target and target.tenant_id == tenant_id and target.kind == "static-site" and any(path.startswith(p) and p.endswith("/") for p in target.path_prefixes)),
             f"publish target covers {path}" if target else "no authorised static-site publish target covers this page"):
        return stop("The page publisher is not authorised for this page.")
    if not g("intended_is_the_workers_conclusion", authoritative_intended == intended, f"the worker's diagnosis names {authoritative_intended!r}; this plan uses {intended!r}"):
        return stop("This plan does not match the address the worker's diagnosis established.")
    same = all(urlsplit(u).scheme == "https" and urlsplit(u).netloc.lower() == tenant_host.lower() for u in (wrong, intended))
    if not g("same_host_https", same, f"both addresses are https on {tenant_host}" if same else "an address is on another host or not https"):
        return stop("Both addresses must be https on the tenant's own host.")
    if not g("addresses_differ_only_by_trailing_slash", wrong != intended and wrong.rstrip("/") == intended.rstrip("/"), f"{wrong} vs {intended}"):
        return stop("The two addresses differ in more than a trailing slash; this edit does not handle that.")
    # live behaviour must agree with the conclusion: wrong -> 301/308 -> intended (200)
    st, hd, _ = fetch(wrong)
    ev["wrong_status"], ev["wrong_location"] = st, hd.get("location")
    resolved = urljoin(wrong, hd.get("location", "")) if hd.get("location") else ""
    if not g("wrong_address_redirects_to_intended", st in (301, 308) and _norm(resolved) == _norm(intended), f"HTTP {st}, Location {hd.get('location')!r}"):
        return stop("The live site does not redirect the wrong address to the intended one.")
    dst, dhd, dbody = fetch(intended)
    ev["intended_status"] = dst
    if not g("intended_returns_200", dst == 200 and not dhd.get("location"), f"HTTP {dst}"):
        return stop(f"The intended address returned HTTP {dst}, not a final 200.")
    noindex = bool(re.search(r'<meta[^>]+name=["\']robots["\'][^>]*noindex', dbody, re.I)) or "noindex" in dhd.get("x-robots-tag", "").lower()
    if not g("intended_is_indexable", not noindex, "no noindex directive" if not noindex else "the intended page carries a noindex directive"):
        return stop("The intended page is marked noindex.")
    if robots_txt is None:
        g("intended_not_blocked_by_robots", False, "robots.txt could not be read")
        return stop("robots.txt could not be read; cannot confirm the intended address is crawlable.")
    rp = urllib.robotparser.RobotFileParser(); rp.parse(robots_txt.splitlines())
    if not g("intended_not_blocked_by_robots", rp.can_fetch("*", intended), "allowed for User-agent: *"):
        return stop("robots.txt blocks the intended address.")
    canon = _canonical(live_html)
    ev["current_canonical"] = canon
    if not g("canonical_currently_names_the_wrong_address", canon is not None and _norm(canon) == _norm(wrong) and canon == wrong, f"canonical {canon!r}"):
        return stop(f"The page's canonical is {canon!r}, not the wrong address; there is nothing for this edit to correct.")
    after, k = _swap(live_html, wrong, intended)
    plan.replacements = k
    if not g("addresses_found", k >= 1 and live_html.count(f'"{intended}"') == after.count(f'"{intended}"') - k, f"{k} declared occurrence(s) of the wrong address"):
        return stop("The declared addresses could not be replaced unambiguously.")
    after_canon = _canonical(after)
    g("canonical_after_equals_intended", after_canon == intended, f"canonical becomes {after_canon!r}")
    g("only_the_declared_addresses_changed",
      after.count(f'"{wrong}"') == 0 and after.count(f'"{intended}"') == live_html.count(f'"{intended}"') + k and len(after) - len(live_html) == k * (len(intended) - len(wrong)),
      "the only differences are the replaced quoted addresses; every other byte of the page is identical")
    g("single_file_change_set", True, f"the change set is {rel} only")
    if source_html is not None:
        s_after, sk = _swap(source_html, wrong, intended)
        ok_src = sk == k and sk >= 1
        g("source_declares_the_same_addresses", ok_src, f"source has {sk} occurrence(s), live has {k}")
        plan.source_after_html = s_after if ok_src else None
    plan.after_html, plan.after_sha256 = after, sha(after)
    plan.evidence = dict(ev)
    plan.gates, plan.blocked_by = gates, [x.gate for x in gates if not x.passed]
    plan.ok = not plan.blocked_by
    if not plan.ok:
        plan.blocked_reason = "; ".join(x.detail for x in gates if not x.passed)
    return plan


def change_id_for(tenant_id: str, opportunity_id: str, plan: PageEditPlan) -> str:
    return "chg_" + hashlib.sha1(f"{tenant_id}|{opportunity_id}|{ACTION}|{plan.wrong_url}|{plan.after_sha256}".encode()).hexdigest()[:12]


def evaluate_page_edit_eligibility(opp: Dict[str, Any], plan: PageEditPlan, mode: str, store: SeoContentStore, tenant_id: str, now: Optional[str] = None) -> PublishDecision:
    """Policy + plan gates -> persisted decision. A human approval is itself the authority for a Class A/B change (the tenant mode only
    governs what SANOCEA may authorise on its own); Class C is never eligible. The publisher acts only on a decision whose digest is audited."""
    now = now or datetime.now(timezone.utc).isoformat()
    action = (opp.get("decision") or {}).get("action") or opp.get("recommendedAction")
    cls = classify_action(action)
    approval = opp.get("approval") or {}
    gates: List[Gate] = [Gate(gate="action_is_change_canonical", passed=action == ACTION, detail=f"action {action} (class {cls})"),
                         Gate(gate="evidence_backed_opportunity", passed=bool(opp.get("evidence")) and bool(opp.get("source")), detail=str(opp.get("source")))]
    ok_ap, why = valid_approval(approval)
    gates.append(Gate(gate="standing_approval", passed=ok_ap and opp.get("status") in ("APPROVED", "IN_PROGRESS") and approval.get("approvedAction") == action, detail=f"{why}; status {opp.get('status')}; approved action {approval.get('approvedAction')}"))
    if approval.get("actorType") == "HUMAN":
        allowed, reason = cls in ("A", "B"), f"Class {cls} change approved by a person ({approval.get('by')})."
    else:
        allowed, reason = mode_allows(mode, cls, action)
    gates.append(Gate(gate="tenant_authorization", passed=allowed, detail=reason))
    gates += plan.gates
    gates.append(Gate(gate="before_after_state_captured", passed=bool(plan.before_sha256 and plan.after_sha256), detail=f"{plan.before_sha256[:12]} -> {(plan.after_sha256 or '')[:12]}"))
    cid = change_id_for(tenant_id, opp["opportunityId"], plan) if plan.after_sha256 else "chg_blocked"
    blocked = [x.gate for x in gates if not x.passed]
    digest = hashlib.sha1(f"{cid}|{action}|{sorted(blocked)}|{plan.before_sha256}|{plan.after_sha256}".encode()).hexdigest()[:16]
    store.append_audit(tenant_id, "evt_" + digest, {"type": "PAGE_EDIT_ELIGIBILITY_EVALUATED", "change_id": cid, "opportunity_id": opp["opportunityId"], "action": action, "action_class": cls,
                                                    "eligible": not blocked, "blocked_by": blocked, "policy": POLICY_REF, "actor_type": approval.get("actorType") or "AUTONOMOUS_AGENT", "at": now,
                                                    "before_sha256": plan.before_sha256, "after_sha256": plan.after_sha256, "digest": digest})
    return PublishDecision(draft_id=cid, tenant_id=tenant_id, action=action, action_class=cls, eligible=not blocked, evaluated_at=now, gates=gates, blocked_by=blocked, status="ELIGIBLE" if not blocked else "BLOCKED")
