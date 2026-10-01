"""Draft writers. A writer turns a SeoBrief plus APPROVED FACTS into a draft; it may use nothing else.

The default FactsOnlyWriter is deterministic: every paragraph is an approved fact, cited by id, so a draft cannot contain a
claim nobody approved. It does not paraphrase. An LLM-backed writer can implement the same protocol later, and its output
still has to clear the same QA (evidence grounding, claims gate, no unsourced numbers). No LLM provider is configured today."""

from __future__ import annotations

import re
from typing import List, Protocol

from packages.content_engine.seo.brief import words
from packages.content_engine.seo.models import ApprovedFact, DraftParagraph, DraftSection, SeoBrief


class WriterError(Exception):
    pass


class DraftPayload:
    def __init__(self, title: str, meta_description: str, sections: List[DraftSection], internal_links_used: List[str], fact_ids_used: List[str]):
        self.title, self.meta_description, self.sections = title, meta_description, sections
        self.internal_links_used, self.fact_ids_used = internal_links_used, fact_ids_used


class DraftWriter(Protocol):
    name: str

    def write(self, brief: SeoBrief, facts: List[ApprovedFact]) -> DraftPayload: ...


def _first_sentence(text: str, limit: int) -> str:
    s = re.split(r"(?<=[.!?])\s", text.strip())[0]
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


class FactsOnlyWriter:
    name = "facts-only-v1"

    def write(self, brief: SeoBrief, facts: List[ApprovedFact]) -> DraftPayload:
        meta_only = brief.content_type.value == "title and description update"
        title = brief.proposed_title.value
        if not title:
            raise WriterError("The brief has no grounded title and no wording basis; a human must supply one.")
        is_query = brief.lineage.type == "QUERY_PAGE_MATCH_GAP"
        topic_words = words(str(brief.target.value or "")) if is_query else set()
        relevant = [f for f in facts if (words(f.text) & topic_words)] if topic_words else list(facts)
        if not relevant:
            raise WriterError("No approved fact is relevant to this brief; nothing may be written without a source.")
        meta = _first_sentence(relevant[0].text, 160)
        used = [relevant[0].id]
        sections: List[DraftSection] = []
        if not meta_only:
            sections.append(DraftSection(level=1, heading=title.split(" | ")[0], paragraphs=[DraftParagraph(text=relevant[0].text, fact_ids=[relevant[0].id])]))
            rest = relevant[1:]
            for q in (brief.primary_questions.value or []):
                qw = words(q)
                matched = [f for f in rest if words(f.text) & qw] or rest[:1]
                if matched:
                    sections.append(DraftSection(level=2, heading=q, paragraphs=[DraftParagraph(text=f.text, fact_ids=[f.id]) for f in matched]))
                    used += [f.id for f in matched]
        links = [l.url for l in brief.internal_links]
        return DraftPayload(title, meta, sections, links, list(dict.fromkeys(used)))
