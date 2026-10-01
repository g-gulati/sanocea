"""Brief builder: an APPROVED, content-eligible opportunity -> a structured, fully-sourced SeoBrief.

Nothing here invents a metric. Every field states its basis; anything without a source is NOT_AVAILABLE or
REQUIRES_VERIFICATION. Technical opportunities never reach this module (see eligibility)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from packages.content_engine.dedup.engine import DeduplicationEngine
from packages.content_engine.seo.models import InternalLink, OpportunityRef, SeoBrief, Sourced, TenantProfile

CONTENT_ACTIONS = {"CREATE_SEO_PAGE", "CREATE_SUPPORTING_CONTENT", "UPDATE_EXISTING_PAGE", "UPDATE_TITLE_META"}
CONTENT_TYPES = {"HIGH_IMPRESSIONS_LOW_CTR", "QUERY_PAGE_MATCH_GAP"}  # mirrors the worker's rule (opportunityEngine.ts)
QUERY_OVERLAP_MIN = 0.5  # same threshold the worker uses to call a page a match
LINK_OVERLAP_MIN = 1  # shared meaningful words needed to justify an internal link


def valid_approval(approval: Dict[str, Any] | None) -> Tuple[bool, str]:
    """An approval stands only if its actor type and actor identity agree: a HUMAN approval has a `human:` actor, an
    AUTONOMOUS_AGENT approval has an `autonomous:` actor and a named policy. A mismatch (an agent claiming to be human,
    or a human record under an autonomous label) is refused: autonomous decisions are never relabelled as human."""
    a = approval or {}
    by, kind, policy = str(a.get("by", "")), a.get("actorType"), str(a.get("policy", ""))
    if kind == "HUMAN" and by.startswith("human:") and len(by) > 6:
        return True, "human approval"
    if kind == "AUTONOMOUS_AGENT" and by.startswith("autonomous:") and "@" in policy:
        return True, f"autonomous approval under {policy}"
    return False, "No valid approval: actor type and identity must agree (HUMAN/human: or AUTONOMOUS_AGENT/autonomous: with a policy)."


class ContentWorkflowError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def content_eligibility(opp: Dict[str, Any]) -> Tuple[bool, str]:
    action = (opp.get("decision") or {}).get("action") or opp.get("recommendedAction")
    if opp.get("type") not in CONTENT_TYPES:
        return False, "Technical opportunity: handled as a technical fix, never as content."
    if action not in CONTENT_ACTIONS:
        return False, f"Recommended action {action} is not a content action."
    return True, "Search-wording or page-content opportunity with a content action."


def brief_id_for(tenant_id: str, opp: Dict[str, Any]) -> str:
    return "brief_" + hashlib.sha1(f"{tenant_id}|{opp['type']}|{opp['target']}".encode()).hexdigest()[:12]


def words(text: str) -> set:
    return {w.rstrip("s") if len(w) > 3 else w for w in DeduplicationEngine._tokenize(text)}


def _page_words(p: Dict[str, Any]) -> set:
    path = re.sub(r"^https?://[^/]+", "", p.get("url", ""))
    return words(f"{path.replace('-', ' ').replace('/', ' ')} {p.get('title', '')} {p.get('h1Text', '')}")


def overlap(query: str, page: Dict[str, Any]) -> Tuple[float, List[str]]:
    q = words(query)
    if not q:
        return 0.0, []
    shared = sorted(q & _page_words(page))
    return len(shared) / len(q), shared


def _title_case(s: str) -> str:
    return " ".join(w if w.isupper() else w.capitalize() for w in s.split())


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


_INTENT_CUES = [(r"^(how to|how do|how can)\b", "how-to guidance"), (r"^(what is|what are|meaning of)\b", "definition"), (r"\b(vs|versus|compare|comparison|alternative)\b", "comparison"),
                (r"\b(price|pricing|cost|buy|software|tool)\b", "evaluation or purchase")]


def _intent(query: str) -> Sourced:
    for pat, label in _INTENT_CUES:
        if re.search(pat, query.lower()):
            return Sourced(value=label, basis="INFERRED", evidence_refs=["evidence.query"], note=f"Lexical cue in the query text only (the query reads as {label}); no search-results or behaviour data was used.")
    return Sourced(value=None, basis="NOT_AVAILABLE", note="Intent is not inferred: the query carries no explicit cue and no SERP data source exists.")


FACTUAL_CONSTRAINTS = [
    "Every factual statement must cite an approved fact or an authoritative source; unsourced statements are removed, not softened.",
    "No statistic, percentage, ranking, traffic, conversion, ROI or customer-outcome claim without a cited source.",
    "No claim that Google or any AI assistant will rank, index, cite or feature the page.",
    "Do not use FAQ or HowTo markup for search benefit: Google no longer shows those rich results.",
    "Brand rules of the existing content engine apply (no hype language, no retired slogans).",
]
NOT_AVAILABLE_METRICS = ["search volume", "ranking position", "traffic", "conversion value", "AI citation rate", "related-question data", "search intent beyond a lexical cue"]


def build_brief(opp: Dict[str, Any], tenant: TenantProfile, pages: List[Dict[str, Any]], now: str | None = None) -> SeoBrief:
    ok, why = content_eligibility(opp)
    if not ok:
        raise ContentWorkflowError("NOT_CONTENT_ELIGIBLE", why)
    approval = opp.get("approval") or {}
    ok_ap, why_ap = valid_approval(approval)
    if opp.get("status") != "APPROVED" or not ok_ap:
        raise ContentWorkflowError("NOT_APPROVED", "A brief is only created from an approved opportunity (human, or autonomous under the policy). " + why_ap)
    now = now or datetime.now(timezone.utc).isoformat()
    ev: Dict[str, Any] = opp.get("evidence") or {}
    decision: Dict[str, Any] = opp.get("decision") or {}
    action = decision.get("action") or opp.get("recommendedAction")
    ref = OpportunityRef(opportunity_id=opp["opportunityId"], type=opp["type"], target=opp["target"], status=opp["status"], detected_at=opp["detectedAt"], source=opp["source"],
                         recommended_action=action, reason=opp.get("reason", ""), evidence=ev, decision=decision, approval=dict(approval))
    is_query = opp["type"] == "QUERY_PAGE_MATCH_GAP"
    topic = ev.get("query") if is_query else None
    target_url = None if is_query else (ev.get("page") or opp["target"])

    # overlap / cannibalisation against every known page
    scored = []
    if is_query:
        for p in pages:
            o, shared = overlap(topic, p)
            scored.append({"url": p["url"], "overlap": round(o, 3), "shared_words": shared})
    scored.sort(key=lambda r: (-r["overlap"], r["url"]))
    covering = [s for s in scored if s["overlap"] >= QUERY_OVERLAP_MIN]
    if is_query and action == "CREATE_SEO_PAGE" and covering:
        raise ContentWorkflowError("CANNIBALIZATION_RISK", f"{covering[0]['url']} already shares {covering[0]['overlap']:.0%} of the query's words; update it instead of creating a competing page.")

    existing = next((p for p in pages if p["url"] == target_url or p["url"].rstrip("/") == (target_url or "").rstrip("/")), None)
    if is_query:
        best = scored[0] if scored else None
        existing_assess = Sourced(value={"best_match_url": best["url"] if best else None, "overlap": best["overlap"] if best else None, "pages_compared": len(pages)}, basis="CALCULATED",
                                  evidence_refs=["evidence.bestMatchUrl", "evidence.bestMatchOverlap"], note="Overlap = share of the query's words found in a page's address, title and heading. Page bodies were not compared.")
        overlap_res = Sourced(value={"covering_pages": covering, "ranked": scored[:5]}, basis="CALCULATED", note=f"A page counts as covering the query at >= {QUERY_OVERLAP_MIN:.0%} word overlap.")
    else:
        existing_assess = Sourced(value={"url": target_url, "current_title": (existing or {}).get("title") or None, "current_h1": (existing or {}).get("h1Text") or None, "static_words": (existing or {}).get("staticWords")},
                                  basis="OBSERVED" if existing else "NOT_AVAILABLE", evidence_refs=["published-page audit"], note=None if existing else "The page is not in the latest published-page audit.")
        overlap_res = Sourced(value={"covering_pages": [], "ranked": []}, basis="NOT_AVAILABLE", note="No query is available (Google withholds queries at this volume), so query overlap cannot be computed.")

    content_type = {"CREATE_SEO_PAGE": "new page", "CREATE_SUPPORTING_CONTENT": "supporting content", "UPDATE_EXISTING_PAGE": "update to an existing page", "UPDATE_TITLE_META": "title and description update"}[action]
    canonical_val = (f"/{_slug(topic)}" if (is_query and action == "CREATE_SEO_PAGE") else (best["url"] if is_query and scored and action == "UPDATE_EXISTING_PAGE" else target_url))
    links: List[InternalLink] = []
    if is_query:
        for s in scored:
            if len(s["shared_words"]) >= LINK_OVERLAP_MIN:
                links.append(InternalLink(url=s["url"], justification=f"Shares the words: {', '.join(s['shared_words'])}.", direction="both"))
    meta = Sourced(value=None, basis="REQUIRES_VERIFICATION", note="Written at draft time from approved facts only (70-160 characters); never from unsourced claims.")
    if is_query:
        title = Sourced(value=f"{_title_case(topic)} | {tenant.brand}", basis="GENERATED_RECOMMENDATION", evidence_refs=["evidence.query"], note="Built only from the observed query and the brand name.")
        questions = Sourced(value=[f"What is {topic}?", f"How does {topic} work in practice?"], basis="GENERATED_RECOMMENDATION", evidence_refs=["evidence.query"], note="Template questions from the query text; no question data source exists. A human must confirm them.")
        entities = Sourced(value=[tenant.brand, topic], basis="GENERATED_RECOMMENDATION", evidence_refs=["evidence.query"], note="Brand and query phrase only; no entity data source exists.")
    else:
        title = Sourced(value=None, basis="REQUIRES_VERIFICATION", note="No query data is available, so wording cannot be tied to what people search. A writer proposes a title from approved facts; it must be reviewed.")
        questions = Sourced(value=[], basis="NOT_AVAILABLE", note="No query or question data for this page.")
        entities = Sourced(value=[tenant.brand], basis="GENERATED_RECOMMENDATION", note="Brand only.")
    return SeoBrief(
        brief_id=brief_id_for(tenant.tenant_id, opp), tenant_id=tenant.tenant_id, created_at=now, lineage=ref,
        content_type=Sourced(value=content_type, basis="CALCULATED", evidence_refs=["decision.action", "decision.rationale"], note=decision.get("rationale")),
        target=Sourced(value=topic or target_url, basis="OBSERVED", evidence_refs=["evidence.query" if is_query else "evidence.page"], note="Google Search Console snapshot" if ev else None),
        intent=_intent(topic) if is_query else Sourced(value=None, basis="NOT_AVAILABLE", note="No query is available for this page."),
        audience=Sourced(value=tenant.audience, basis="EDITORIAL" if tenant.audience else "NOT_AVAILABLE", note=None if tenant.audience else "No audience is defined for this tenant; a draft cannot pass QA until one is."),
        existing_page_assessment=existing_assess, overlap=overlap_res, proposed_title=title, proposed_meta_description=meta,
        primary_questions=questions,
        supporting_questions=Sourced(value=[], basis="NOT_AVAILABLE", note="Needs a related-questions data source, which is not connected."),
        entities=entities, internal_links=links, internal_links_basis="CALCULATED",
        research_requirements=Sourced(value=["Collect an authoritative primary source for every factual claim before drafting.", "Confirm each approved fact is still accurate."], basis="REQUIRES_VERIFICATION", note="No source has been collected yet."),
        schema_opportunity=Sourced(value={"types": ["WebPage", "BreadcrumbList"], "excluded": ["FAQPage", "HowTo"]}, basis="GENERATED_RECOMMENDATION", note="Markup describes the page; it does not guarantee any rich result."),
        canonical=Sourced(value=canonical_val, basis="GENERATED_RECOMMENDATION" if canonical_val and canonical_val.startswith("/") else "OBSERVED", note="Self-referencing canonical."),
        factual_constraints=FACTUAL_CONSTRAINTS,
        claims_requiring_verification=["Any number, percentage or comparison that appears in the draft.", "Every approved fact supplied to the writer (confirm with the owner).", "Any statement about how Google or an AI assistant treats the page."],
        not_available=NOT_AVAILABLE_METRICS,
    )
