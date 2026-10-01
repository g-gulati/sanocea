/**
 * SANOCEA SEO Stack — Retired Google rich-result registry
 *
 * Why this exists: a finding that tells a merchant "you are losing CTR because you lack X markup" is only true
 * while Google still renders X. Google has retired several rich results; markup for them is still valid
 * Schema.org vocabulary, but it earns no Google rich result, so SANOCEA must not attach a business impact or an
 * autonomous fix to its absence.
 *
 * Provenance: every entry cites the Google Search Central changelog (https://developers.google.com/search/updates).
 * FAQ, sitelinks search box and How-to were each re-verified against that changelog on 2026-10-01. The catalogue is
 * SANOCEA's own independent implementation (idea prompted by claude-seo's schema-deprecation reference, MIT; no code
 * copied). Add an entry only after checking the changelog yourself.
 */

export interface RetiredRichResult {
  /** schema.org @type values that used to drive the rich result. */
  schemaTypes: string[];
  feature: string;
  retired: string;
  source: string;
  /** What the markup still does, so the finding stays truthful rather than just dismissive. */
  stillUseful: string;
}

const CHANGELOG = 'https://developers.google.com/search/updates';

export const RETIRED_RICH_RESULTS: Record<string, RetiredRichResult> = {
  FAQ: {
    schemaTypes: ['FAQPage'],
    feature: 'FAQ rich result',
    retired: 'FAQ rich results no longer shown in Google Search (restricted Aug 2023; documentation removed May 2026)',
    source: CHANGELOG,
    stillUseful: 'Valid FAQPage markup is harmless and other consumers may read it, but Google Search no longer shows an FAQ accordion for it.'
  },
  SITELINKS_SEARCH_BOX: {
    schemaTypes: ['WebSite.potentialAction.SearchAction'],
    feature: 'Sitelinks search box',
    retired: 'Sitelinks search box no longer available in Google Search (Nov 2024)',
    source: CHANGELOG,
    stillUseful: 'WebSite markup still helps name the site; the SearchAction no longer produces a search box in results.'
  },
  HOW_TO: {
    schemaTypes: ['HowTo'],
    feature: 'How-to rich result',
    retired: 'How-to rich results no longer shown (Sep 2023)',
    source: CHANGELOG,
    stillUseful: 'Clear step headings still help readers; the markup no longer produces a Google rich result.'
  }
};

/** Detection rules whose premise is a retired feature. Their findings are informational only. */
export const RETIRED_FEATURE_RULES: Record<string, keyof typeof RETIRED_RICH_RESULTS> = {
  FAQPAGE_SCHEMA_MISSING: 'FAQ',
  FAQPAGE_SCHEMA_MALFORMED: 'FAQ',
  WEBSITE_SEARCH_ACTION_SCHEMA_MISSING: 'SITELINKS_SEARCH_BOX'
};

export function retiredFeatureForRule(detectionRule: string): RetiredRichResult | undefined {
  const key = RETIRED_FEATURE_RULES[detectionRule];
  return key ? RETIRED_RICH_RESULTS[key] : undefined;
}

/** Retired schema @types present in a set of JSON-LD @type names (case-sensitive per schema.org). */
export function findRetiredSchemaTypes(typeNames: Iterable<string>): Array<{ type: string; entry: RetiredRichResult }> {
  const present = new Set(typeNames);
  const out: Array<{ type: string; entry: RetiredRichResult }> = [];
  for (const entry of Object.values(RETIRED_RICH_RESULTS)) {
    for (const t of entry.schemaTypes) {
      if (!t.includes('.') && present.has(t)) out.push({ type: t, entry });
    }
  }
  return out;
}
