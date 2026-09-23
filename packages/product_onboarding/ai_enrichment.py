"""AI-generation fallback for genuinely cosmetic product fields (description, tags) - tried BEFORE
bothering the owner over WhatsApp, never instead of real source data. Explicitly scoped: never touches
price/sku/currency/product_type or anything else that must come from a real source or the owner - see
ProductOnboardingWorkflow._handle_validated_draft, the only caller.

No LLM API key is configured anywhere in this environment. This shells out to the `agy` CLI - a locally
installed, already-authenticated Gemini-backed agent tool (see docs on today's Premium Basket rehearsal
work) - rather than requiring a new credential. Every call is wrapped so a missing/broken CLI, a timeout,
or empty output degrades to "AI could not fill this field," never an exception that could break
ingestion - the existing WhatsApp fallback path always remains the safety net.

Disabled by default. Set SANOCEA_ENABLE_AI_ENRICHMENT=1 to opt in - this must never change behavior for
anyone who hasn't explicitly turned it on.
"""

from __future__ import annotations

import os
import subprocess

_DESCRIPTION_PROMPT = """Write a short, SEO-friendly Shopify product description (2-3 sentences) for this snack product. ONLY use the facts given below - do NOT invent or add any ingredient, seasoning, packaging, or certification detail that isn't explicitly stated here, even if it sounds plausible. If a detail isn't given, keep the sentence generic instead of guessing.

Product name: {title}
Category: {product_type}

Output ONLY the description text, nothing else."""

_TAGS_PROMPT = """Suggest 3-5 short, lowercase, comma-separated Shopify product tags for this snack product, derived ONLY from the facts given below - do not invent any attribute not stated here.

Product name: {title}
Category: {product_type}

Output ONLY the comma-separated tags, nothing else."""


def _run_agy(prompt: str) -> str | None:
    try:
        result = subprocess.run(
            ["agy", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def is_enabled() -> bool:
    return os.environ.get("SANOCEA_ENABLE_AI_ENRICHMENT") == "1"


def generate_description_and_tags(
    title: str, product_type: str | None, fields: list[str] | set[str] | None = None,
) -> dict[str, str]:
    """Returns a dict with whatever of {"description", "tags"} it managed to generate - a field simply
    absent from the result means AI could not fill it (CLI unavailable, timed out, or returned nothing),
    which the caller must treat as "still missing," never as an error.

    If `fields` is supplied, only the specified subset of {"description", "tags"} will be generated,
    avoiding wasted CLI calls and LLM latency when only one field is actually required."""
    generated: dict[str, str] = {}
    category = product_type or "unknown"

    if fields is None or "description" in fields:
        description = _run_agy(_DESCRIPTION_PROMPT.format(title=title, product_type=category))
        if description:
            generated["description"] = description

    if fields is None or "tags" in fields:
        tags = _run_agy(_TAGS_PROMPT.format(title=title, product_type=category))
        if tags:
            generated["tags"] = tags

    return generated
