"""Draft QA: reuses the existing ClaimsGate, DeduplicationEngine similarity and QACheckItem/QAResult.

Produces pass/fail checks with plain details. It deliberately produces NO score (no SEO score, citability score or
priority score): a draft either clears every check or it does not."""

from __future__ import annotations

import re
from typing import Dict, List

from packages.content_engine.dedup.engine import DeduplicationEngine
from packages.content_engine.models import ContentCopy, QACheckItem, QAResult
from packages.content_engine.qa.claims_gate import ClaimsGate
from packages.content_engine.seo.brief import QUERY_OVERLAP_MIN, overlap
from packages.content_engine.seo.models import ApprovedFact, SeoBrief, SeoDraft

TITLE_MAX_CHARS = 60  # character heuristic; the SEO worker's pixel-width rule remains authoritative for display width
META_MIN, META_MAX = 70, 160  # same bounds the SEO worker's remediation rules use
DUPLICATE_THRESHOLD = 0.65  # the existing engine's duplicate threshold
_NUM = re.compile(r"\d[\d,.]*%?")


def _check(name: str, passed: bool, details: str) -> QACheckItem:
    return QACheckItem(check_name=name, passed=passed, details=details)


def evaluate_draft(draft: SeoDraft, brief: SeoBrief, facts: List[ApprovedFact], known_pages: List[Dict], prior_texts: List[str]) -> QAResult:
    fact_by_id = {f.id: f for f in facts}
    paragraphs = [p for s in draft.sections for p in s.paragraphs]
    body = " ".join(p.text for p in paragraphs)
    checks: List[QACheckItem] = []
    meta_only = brief.content_type.value == "title and description update"

    # 1. evidence grounding
    if meta_only:
        checks.append(_check("evidence_grounding", bool(draft.fact_ids_used) and all(i in fact_by_id for i in draft.fact_ids_used), "Title/description cite approved facts." if draft.fact_ids_used else "Title/description cite no approved fact."))
    else:
        norm = lambda t: " ".join(t.lower().split())
        # A paragraph is grounded only if it cites approved facts AND its text is contained in those facts (no paraphrase,
        # no extra claim riding on a citation). Conservative on purpose until a semantic grounding check exists.
        bad = [p.text[:50] for p in paragraphs if not p.fact_ids or any(i not in fact_by_id for i in p.fact_ids)
               or norm(p.text) not in norm(" ".join(fact_by_id[i].text for i in p.fact_ids))]
        placeholder = [p.text[:50] for p in paragraphs if p.text.lstrip().startswith("[NEEDS SOURCE")]
        ok = bool(paragraphs) and not bad and not placeholder
        checks.append(_check("evidence_grounding", ok, "Every paragraph cites approved facts." if ok else f"{len(bad)} paragraph(s) lack a valid approved-fact citation; {len(placeholder)} placeholder(s) remain."))

    # 2. factual claims (existing ClaimsGate on the full text) + 3. no number without a source
    text = " ".join([draft.title, draft.meta_description, body])
    copy = ContentCopy(headline_hook=draft.title or "-", problem_narrative=body or "-", mechanism_explanation=draft.meta_description or "-", solution_narrative="-", call_to_action="-", alt_text="-")
    claims_ok, claim_checks = ClaimsGate().validate(copy)
    checks.append(_check("claims_gate", claims_ok, "; ".join(c.details for c in claim_checks if not c.passed) or "No hype, retired slogans or fabricated statistics detected."))
    cited = " ".join(fact_by_id[i].text for i in set(draft.fact_ids_used) if i in fact_by_id)
    loose = sorted({n for n in _NUM.findall(text) if n.strip(".,") and n not in cited})
    checks.append(_check("no_unsourced_numbers", not loose, "Every number in the draft appears in a cited fact." if not loose else f"Numbers not found in any cited fact: {', '.join(loose)}."))

    # 4. duplication against earlier drafts, 5. cannibalisation against known pages
    dup = max((DeduplicationEngine.compute_similarity(text, t) for t in prior_texts), default=0.0)
    checks.append(_check("duplication", dup < DUPLICATE_THRESHOLD, f"Highest similarity to an earlier draft: {dup:.0%} (limit {DUPLICATE_THRESHOLD:.0%})."))
    if brief.lineage.type == "QUERY_PAGE_MATCH_GAP" and brief.content_type.value == "new page":
        topic = str(brief.target.value)
        top = max(((overlap(topic, p)[0], p["url"]) for p in known_pages), default=(0.0, None))
        checks.append(_check("cannibalization", top[0] < QUERY_OVERLAP_MIN, f"Closest existing page ({top[1]}) shares {top[0]:.0%} of the topic's words." if top[1] else "No known page to compare."))
    else:
        checks.append(_check("cannibalization", True, "Not a new page: no competing page is created."))

    # 6. audience and 7. intent
    checks.append(_check("intended_audience", brief.audience.basis != "NOT_AVAILABLE", f"Audience: {brief.audience.value}" if brief.audience.value else "No audience is defined for this tenant."))
    checks.append(_check("search_intent", True, f"Intent ({brief.intent.basis}): {brief.intent.value}" if brief.intent.value else "Not assessed: no evidence supports an intent."))

    # 8. internal links, 9. title, 10. meta description, 11. heading structure
    known = {p["url"] for p in known_pages}
    justified = {l.url for l in brief.internal_links}
    bad_links = [u for u in draft.internal_links_used if u not in known or u not in justified]
    checks.append(_check("internal_links", not bad_links, "Every internal link points to a known page with a recorded justification." if not bad_links else f"Unjustified or unknown links: {', '.join(bad_links)}."))
    checks.append(_check("title", 0 < len(draft.title) <= TITLE_MAX_CHARS, f"Title is {len(draft.title)} characters (limit {TITLE_MAX_CHARS}, a character heuristic)."))
    checks.append(_check("meta_description", META_MIN <= len(draft.meta_description) <= META_MAX, f"Description is {len(draft.meta_description)} characters (allowed {META_MIN}-{META_MAX})."))
    if meta_only:
        checks.append(_check("heading_structure", not draft.sections, "Title/description update has no body headings."))
    else:
        levels = [s.level for s in draft.sections]
        ok = levels.count(1) == 1 and levels[0] == 1 and all(b - a <= 1 for a, b in zip(levels, levels[1:]))
        checks.append(_check("heading_structure", ok, "One h1 first, no skipped levels." if ok else f"Heading levels {levels} break the one-h1, no-skip rule."))

    failures = [c.details for c in checks if not c.passed]
    return QAResult(passed=not failures, checks=checks, failure_reasons=failures, no_fabricated_stats=claims_ok and not loose, no_unsupported_claims=claims_ok)
