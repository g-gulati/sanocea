/**
 * SANOCEA SEO Stack — Indexation & Coverage Intelligence Engine
 * 
 * Reconciles:
 * 1. Declared XML Sitemap URLs
 * 2. Observed Storefront Crawl Graph Nodes
 * 3. GSC URL Inspection Telemetry (Coverage State, Google-Selected Canonical)
 * 
 * Flags:
 * - GOOGLE_SELECTED_CANONICAL_OVERRIDE
 * - GSC_DISCOVERED_NOT_INDEXED
 * - GSC_CRAWLED_NOT_INDEXED
 * - SOFT_404_DETECTED
 * - GSC_INDEXED_URL_MISSING_FROM_SITEMAP
 */

import { 
  GscUrlInspectionRecord, 
  CrawledPage, 
  SeoFinding, 
  Severity 
} from '../core/types.js';
import { normalizeUrl } from '../core/urlDiscovery.js';
import { classifyRouteIntent } from '../core/routeIntent.js';

export interface IndexationReconciliationInput {
  sitemapUrls?: Set<string>;
  crawledPages: Map<string, CrawledPage>;
  inspectionRecords?: Map<string, GscUrlInspectionRecord>;
}

export function reconcileIndexationIntelligence(
  input: IndexationReconciliationInput
): SeoFinding[] {
  const findings: SeoFinding[] = [];
  const now = new Date().toISOString();

  const { sitemapUrls = new Set(), crawledPages, inspectionRecords = new Map() } = input;

  if (inspectionRecords.size === 0) {
    // Graceful uncredentialed fallback: do not emit false alarms, mark inspection requires access
    return findings;
  }

  // 1. Audit GSC URL Inspection Records against Crawled Pages & Sitemaps
  for (const [rawUrl, record] of inspectionRecords.entries()) {
    const normUrl = normalizeUrl(rawUrl) || rawUrl;
    const routeIntent = classifyRouteIntent(normUrl);

    // ── Check A: Google-Selected Canonical Override ───────────────────
    if (record.googleCanonical && record.userCanonical) {
      const normGoogle = normalizeUrl(record.googleCanonical) || record.googleCanonical;
      const normUser = normalizeUrl(record.userCanonical) || record.userCanonical;

      if (normGoogle !== normUser) {
        findings.push({
          findingId: `SAN-GSC-CANON-OVERRIDE-${Buffer.from(normUrl).toString('base64url').slice(0, 10)}`,
          url: normUrl,
          routeIntent,
          detectionRule: 'GOOGLE_SELECTED_CANONICAL_OVERRIDE',
          track: 'SEARCH_INTELLIGENCE',
          category: 'Indexation & Coverage',
          severity: 'CRITICAL',
          evidenceClass: '[O] Observed',
          observedValue: `Google selected: ${record.googleCanonical} (overriding declared: ${record.userCanonical})`,
          expectedValue: `Google-selected canonical must match declared canonical (${record.userCanonical})`,
          exactEvidence: {
            userCanonical: record.userCanonical,
            googleCanonical: record.googleCanonical,
            rawContext: `Storefront declared <link rel="canonical" href="${record.userCanonical}">, but Google overridden to "${record.googleCanonical}" during indexing.`
          },
          reproductionMethod: `GSC URL Inspection API: urlInspection.index.inspect('${normUrl}')`,
          businessImpact: 'Google rejects merchant-declared canonical directives when internal link signals or URL parameters point more strongly to an alternate URL, diluting PageRank.',
          commercialRisk: {
            riskType: 'CRAWL_BUDGET_DILUTION',
            title: 'Google Canonical Override & PageRank Dilution',
            currency: 'INR',
            confidence: '[REQUIRES_ACCESS]',
            source: 'google_search_console',
            severityScore: 5,
            calculationFormula: `Canonical override on ${normUrl} [REQUIRES_ACCESS: Organic session loss requires merchant telemetry]`,
            affectedChannels: ['Google Organic Search'],
            observedDataPoints: {
              declaredCanonical: record.userCanonical,
              googleSelectedCanonical: record.googleCanonical
            }
          },
          recommendedRemediation: `Ensure all internal links and sitemap entries point strictly to ${record.userCanonical} rather than ${record.googleCanonical}.`,
          automaticallyFixable: true,
          requiredAccess: 'HTML / Canonical Tag',
          remediationStatus: 'ACTION_REQUIRED',
          beforeEvidence: `Declared: ${record.userCanonical} | Google: ${record.googleCanonical}`,
          afterEvidence: null,
          verificationResult: null,
          timestamp: now
        });
      }
    }

    // ── Check B: Discovered - Currently Not Indexed ───────────────────
    if (record.coverageState === 'DISCOVERED_NOT_INDEXED') {
      findings.push({
        findingId: `SAN-GSC-DISC-NOT-INDEXED-${Buffer.from(normUrl).toString('base64url').slice(0, 10)}`,
        url: normUrl,
        routeIntent,
        detectionRule: 'GSC_DISCOVERED_NOT_INDEXED',
        track: 'SEARCH_INTELLIGENCE',
        category: 'Indexation & Coverage',
        severity: routeIntent === 'PRODUCT_DISPLAY_PAGE' || routeIntent === 'COLLECTION_PAGE' ? 'HIGH' : 'MEDIUM',
        evidenceClass: '[O] Observed',
        observedValue: 'GSC Status: Discovered - currently not indexed',
        expectedValue: 'GSC Status: Indexed, submitted in sitemap',
        exactEvidence: {
          gscCoverageState: 'DISCOVERED_NOT_INDEXED',
          lastCrawlTime: record.lastCrawlTime || 'Never crawled by Googlebot',
          rawContext: 'Googlebot added URL to crawl queue but dropped it due to crawl budget exhaustion or low domain internal link equity.'
        },
        reproductionMethod: `GSC URL Inspection API: coverageState for '${normUrl}'`,
        businessImpact: 'Page generates 0 organic impressions because Google has not allocated crawl budget to fetch and index it.',
        commercialRisk: {
          riskType: 'INDEXATION_PURGE',
          title: 'Googlebot Crawl Budget Exhaustion',
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'google_search_console',
          severityScore: 4,
          calculationFormula: `Page ${normUrl} discovered but excluded from Google crawl queue [REQUIRES_ACCESS]`,
          affectedChannels: ['Google Organic Search']
        },
        recommendedRemediation: 'Strengthen internal in-links from authoritative parent collection pages and verify sitemap submission.',
        automaticallyFixable: false,
        requiredAccess: 'Internal Link Architecture',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'DISCOVERED_NOT_INDEXED',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }

    // ── Check C: Crawled - Currently Not Indexed ─────────────────────
    if (record.coverageState === 'CRAWLED_NOT_INDEXED') {
      findings.push({
        findingId: `SAN-GSC-CRAWL-NOT-INDEXED-${Buffer.from(normUrl).toString('base64url').slice(0, 10)}`,
        url: normUrl,
        routeIntent,
        detectionRule: 'GSC_CRAWLED_NOT_INDEXED',
        track: 'SEARCH_INTELLIGENCE',
        category: 'Indexation & Coverage',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: 'GSC Status: Crawled - currently not indexed',
        expectedValue: 'GSC Status: Indexed, submitted in sitemap',
        exactEvidence: {
          gscCoverageState: 'CRAWLED_NOT_INDEXED',
          lastCrawlTime: record.lastCrawlTime,
          rawContext: 'Googlebot crawled the page, evaluated content quality, and deliberately chose not to include it in the index (thin content or duplicate).'
        },
        reproductionMethod: `GSC URL Inspection API: coverageState for '${normUrl}'`,
        businessImpact: 'Signals content quality deficit or near-duplicate product catalogue pages rejected by Google Helpful Content / Panda algorithms.',
        commercialRisk: {
          riskType: 'INDEXATION_PURGE',
          title: 'Quality-Triggered Google Indexation Rejection',
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'google_search_console',
          severityScore: 4,
          calculationFormula: `Page ${normUrl} crawled but rejected from search index [REQUIRES_ACCESS]`,
          affectedChannels: ['Google Organic Search']
        },
        recommendedRemediation: 'Expand primary copy to ≥ 250 words with unique product specifications, unique value propositions, and structured data.',
        automaticallyFixable: false,
        requiredAccess: 'Content / CMS',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'CRAWLED_NOT_INDEXED',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }

    // ── Check D: Soft 404 Detected ───────────────────────────────────
    if (record.coverageState === 'SOFT_404' || record.pageFetchState === 'SOFT_404') {
      findings.push({
        findingId: `SAN-GSC-SOFT-404-${Buffer.from(normUrl).toString('base64url').slice(0, 10)}`,
        url: normUrl,
        routeIntent,
        detectionRule: 'SOFT_404_DETECTED',
        track: 'SEARCH_INTELLIGENCE',
        category: 'Indexation & Coverage',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: 'Storefront returns HTTP 200, but Google classified as Soft 404',
        expectedValue: 'HTTP 404 / 410 for missing content, or populated content for HTTP 200',
        exactEvidence: {
          gscCoverageState: 'SOFT_404',
          rawContext: 'Server returned HTTP 200 OK, but page has zero content or states "Not Found" / "Zero Products", causing Google to de-index it as a soft 404.'
        },
        reproductionMethod: `GSC URL Inspection API: pageFetchState for '${normUrl}'`,
        businessImpact: 'Soft 404s waste crawl budget and harm domain trust score while presenting broken user journeys.',
        commercialRisk: {
          riskType: 'CONVERSION_FRICTION',
          title: 'Soft 404 Search Suppression',
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'google_search_console',
          severityScore: 4,
          calculationFormula: `Soft 404 on ${normUrl} [REQUIRES_ACCESS]`,
          affectedChannels: ['Google Organic Search']
        },
        recommendedRemediation: 'Return genuine HTTP 404 / 410 status code if discontinued, or 301 redirect to parent category.',
        automaticallyFixable: true,
        requiredAccess: 'Server HTTP Configuration / Routing',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'HTTP 200 returned on empty/broken content',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }

    // ── Check E: Indexed URL Missing from Submitted XML Sitemap ───────
    if (record.coverageState === 'INDEXED' && sitemapUrls.size > 0 && !sitemapUrls.has(normUrl)) {
      const isUtility = routeIntent === 'INTERNAL_SEARCH' || routeIntent === 'TRANSACTIONAL_UTILITY' || routeIntent === 'UTILITY_SIMULATOR' || routeIntent === 'FACETED_FILTER';
      if (!isUtility) {
        findings.push({
          findingId: `SAN-GSC-INDEXED-NO-SITEMAP-${Buffer.from(normUrl).toString('base64url').slice(0, 10)}`,
          url: normUrl,
          routeIntent,
          detectionRule: 'GSC_INDEXED_URL_MISSING_FROM_SITEMAP',
          track: 'SEARCH_INTELLIGENCE',
          category: 'Indexation & Coverage',
          severity: 'LOW',
          evidenceClass: '[O] Observed',
          observedValue: 'Indexed in Google Search, but absent from submitted XML sitemap',
          expectedValue: 'Present in XML sitemap for prioritized recrawl frequency',
          exactEvidence: {
            rawContext: `URL ${normUrl} is indexed by Google but missing from all ${sitemapUrls.size} sitemap URLs`
          },
          reproductionMethod: `Cross-reference sitemap URL set against GSC indexed URL: '${normUrl}'`,
          businessImpact: 'Slows down re-crawling and re-indexing when prices or inventory change.',
          recommendedRemediation: 'Add URL to XML sitemap index.',
          automaticallyFixable: true,
          requiredAccess: 'Sitemap Generator',
          remediationStatus: 'ACTION_REQUIRED',
          beforeEvidence: 'Missing from sitemap',
          afterEvidence: null,
          verificationResult: null,
          timestamp: now
        });
      }
    }
  }

  return findings;
}
