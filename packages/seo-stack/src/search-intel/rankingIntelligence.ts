/**
 * SANOCEA SEO Stack — Ranking Intelligence Engine
 * 
 * Analyzes multi-dimensional GSC search telemetry to detect:
 * 1. Query ↔ URL Cannibalisation with strict deterministic thresholds
 * 2. Intent-to-URL Mismatches (e.g. blog ranking ahead of PDP for transactional query)
 * 3. Positions 4–10 Strike-Zone CTR Opportunities
 * 4. Ranking Winners and Bleeding Query Losers
 */

import { 
  GscPerformanceRow, 
  QueryCannibalisationCase, 
  CompetingUrlMetrics, 
  SeoFinding, 
  Severity 
} from '../core/types.js';
import { classifyRouteIntent } from '../core/routeIntent.js';

export interface CannibalisationThresholds {
  minTotalImpressions: number;
  maxDominantShare: number;
  maxRankPosition: number;
  minCompetingUrls: number;
}

export const DEFAULT_CANNIBALISATION_THRESHOLDS: CannibalisationThresholds = {
  minTotalImpressions: 100, // Total query search volume must be significant
  maxDominantShare: 0.80,    // Top URL has < 80% impression share (genuine split)
  maxRankPosition: 35.0,     // Both URLs rank in top 3 pages
  minCompetingUrls: 2        // At least 2 distinct URLs competing
};

/**
 * Detects query ↔ URL cannibalisation from multi-dimensional GSC query+page data
 */
export function detectQueryCannibalisation(
  rows: GscPerformanceRow[],
  thresholds: CannibalisationThresholds = DEFAULT_CANNIBALISATION_THRESHOLDS
): QueryCannibalisationCase[] {
  // 1. Group rows by normalized query
  const queryGroupMap = new Map<string, Map<string, GscPerformanceRow>>();

  for (const r of rows) {
    if (!r.query || !r.page) continue;
    const cleanQuery = r.query.trim().toLowerCase();

    if (!queryGroupMap.has(cleanQuery)) {
      queryGroupMap.set(cleanQuery, new Map());
    }
    const pageMap = queryGroupMap.get(cleanQuery)!;

    if (pageMap.has(r.page)) {
      // Accumulate metrics if multiple device/date rows exist for same page
      const existing = pageMap.get(r.page)!;
      existing.clicks += r.clicks;
      existing.impressions += r.impressions;
    } else {
      pageMap.set(r.page, { ...r });
    }
  }

  const cannibalisationCases: QueryCannibalisationCase[] = [];

  for (const [query, pageMap] of queryGroupMap.entries()) {
    if (pageMap.size < thresholds.minCompetingUrls) continue;

    const competingList = Array.from(pageMap.values());
    let totalImpressions = 0;
    let totalClicks = 0;

    for (const c of competingList) {
      totalImpressions += c.impressions;
      totalClicks += c.clicks;
    }

    if (totalImpressions < thresholds.minTotalImpressions) continue;

    // Filter to URLs ranking within active visibility range (<= maxRankPosition)
    const activeUrls = competingList.filter(c => c.position <= thresholds.maxRankPosition && c.impressions >= 10);
    if (activeUrls.length < thresholds.minCompetingUrls) continue;

    // Sort by impressions descending to find dominant URL
    activeUrls.sort((a, b) => b.impressions - a.impressions);

    const dominant = activeUrls[0];
    const dominantShare = dominant.impressions / totalImpressions;

    // Threshold gate: If dominant page holds >= 80% impressions, it's not a harmful cannibalisation
    if (dominantShare >= thresholds.maxDominantShare) continue;

    // Map to CompetingUrlMetrics
    const competingMetrics: CompetingUrlMetrics[] = activeUrls.map(c => ({
      url: c.page!,
      clicks: c.clicks,
      impressions: c.impressions,
      ctr: c.impressions > 0 ? (c.clicks / c.impressions) : 0,
      position: c.position,
      impressionShare: c.impressions / totalImpressions
    }));

    // Intent Mismatch Check: Does query contain purchase intent while ranking an informational URL?
    const hasPurchaseIntent = /(buy|price|cost|shop|order|supplier|inverter|battery|panel)/i.test(query);
    const dominantIntent = classifyRouteIntent(dominant.page!);
    const hasIntentMismatch = hasPurchaseIntent && (dominantIntent === 'EDITORIAL_ARTICLE' || dominantIntent === 'TRANSACTIONAL_UTILITY');

    const severity: Severity = hasIntentMismatch ? 'CRITICAL' : (dominantShare < 0.60 ? 'HIGH' : 'MEDIUM');

    let recommendedRemediation = `Consolidate internal link equity onto the primary authoritative URL (${dominant.page}).`;
    if (hasIntentMismatch) {
      recommendedRemediation = `Intent Mismatch Detected: Commercial query "${query}" is ranking informational URL (${dominant.page}). Redirect or canonicalize authority to the relevant product/category page.`;
    }

    cannibalisationCases.push({
      query,
      totalImpressions,
      totalClicks,
      competingUrls: competingMetrics,
      dominantUrl: dominant.page!,
      dominantShare,
      severity,
      intentMismatch: hasIntentMismatch,
      recommendedRemediation
    });
  }

  // Sort by commercial impact (highest total impressions first)
  cannibalisationCases.sort((a, b) => b.totalImpressions - a.totalImpressions);
  return cannibalisationCases;
}

/**
 * Converts detected cannibalisation cases into standardized SeoFinding records
 */
export function formatCannibalisationFindings(cases: QueryCannibalisationCase[]): SeoFinding[] {
  const now = new Date().toISOString();
  return cases.map(c => {
    const urlsSnippet = c.competingUrls.map(u => 
      `${u.url} (Rank: ${u.position.toFixed(1)}, Share: ${(u.impressionShare * 100).toFixed(0)}%, Clicks: ${u.clicks})`
    ).join(' vs ');

    return {
      findingId: `SAN-GSC-CANNIBAL-${Buffer.from(c.query).toString('base64url').slice(0, 10)}`,
      url: c.dominantUrl,
      routeIntent: classifyRouteIntent(c.dominantUrl),
      detectionRule: 'QUERY_PAGE_CANNIBALISATION',
      track: 'SEARCH_INTELLIGENCE',
      category: 'Search Performance',
      severity: c.severity,
      evidenceClass: '[O] Observed',
      observedValue: `${c.competingUrls.length} URLs competing for "${c.query}": ${urlsSnippet}`,
      expectedValue: `Single authoritative landing page capturing ≥ 85% impression share for "${c.query}"`,
      exactEvidence: {
        rawContext: `Query "${c.query}" generated ${c.totalImpressions} impressions split across ${c.competingUrls.length} pages. Top page has only ${(c.dominantShare * 100).toFixed(1)}% share.`,
        competingUrls: c.competingUrls.map(u => ({
          url: u.url,
          clicks: u.clicks,
          impressions: u.impressions,
          position: u.position,
          share: u.impressionShare
        }))
      },
      reproductionMethod: `GSC Search Analytics query: dimensions=['query', 'page'], query="${c.query}"`,
      businessImpact: 'Competing internal URLs fragment PageRank, oscillate positions between page 1 and page 3, and depress click-through rate.',
      commercialRisk: {
        riskType: 'CRAWL_BUDGET_DILUTION',
        title: 'Keyword Cannibalisation Ranking & CTR Fragmentation',
        currency: 'INR',
        confidence: '[REQUIRES_ACCESS]',
        source: 'google_search_console',
        severityScore: 4,
        calculationFormula: `Query "${c.query}" split across ${c.competingUrls.length} URLs [REQUIRES_ACCESS: Exact revenue loss requires conversion telemetry]`,
        affectedChannels: ['Google Organic Search'],
        observedDataPoints: {
          query: c.query,
          totalImpressions: c.totalImpressions,
          totalClicks: c.totalClicks,
          competingUrlCount: c.competingUrls.length,
          dominantSharePct: Math.round(c.dominantShare * 100)
        }
      },
      recommendedRemediation: c.recommendedRemediation,
      automationOpportunity: {
        automatable: true,
        recipeType: 'CANONICAL_RULE',
        primaryMechanism: 'TAG_MANAGER_SCRIPT',
        fallbackMechanisms: ['STOREFRONT_API', 'GIT_PULL_REQUEST'],
        requiredAccessTier: 'TAG_MANAGER_ONLY',
        requiredRole: 'GROWTH',
        description: 'Establish canonical or redirect consolidation to the primary commercial landing page.'
      },
      automaticallyFixable: true,
      requiredAccess: 'HTML / Canonical Tag',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: urlsSnippet,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    };
  });
}
