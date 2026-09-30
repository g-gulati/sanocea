/**
 * SANOCEA SEO Stack — Milestone 5.2 Ranking & Indexation Intelligence Test Suite
 * 
 * Verifies:
 * 1. Query ↔ URL Cannibalisation detection with deterministic thresholds
 * 2. Intent-to-URL mismatch identification (e.g. editorial ranking over PDP for commercial queries)
 * 3. GSC URL Inspection reconciliation (Canonical overrides, Crawled/Discovered not indexed, Soft 404s)
 * 4. Search Appearance & Schema reconciliation (Declared schema vs GSC rich appearance evidence)
 * 5. Strict adherence to financial provenance ([REQUIRES_ACCESS] / [OBSERVED])
 * 6. Dual-track pipeline integration with GSC telemetry
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 
  detectQueryCannibalisation, 
  formatCannibalisationFindings 
} from '../src/search-intel/rankingIntelligence.js';
import { 
  reconcileIndexationIntelligence 
} from '../src/search-intel/indexationIntelligence.js';
import { 
  reconcileSearchAppearance 
} from '../src/search-intel/searchAppearanceReconciler.js';
import { SeoAuditPipeline } from '../src/pipeline/auditPipeline.js';
import { 
  GscPerformanceRow, 
  GscSnapshot, 
  GscUrlInspectionRecord, 
  CrawledPage 
} from '../src/core/types.js';

test('Milestone 5.2.1 — Query Cannibalisation: Deterministic Thresholds & Intent Mismatch', () => {
  // Test Case A: Sub-threshold volume (< 100 impressions) -> Not flagged
  const lowVolumeRows: GscPerformanceRow[] = [
    { query: 'rare solar part 99', page: 'https://sanocea.com/products/part-a', clicks: 2, impressions: 30, ctr: 0.067, position: 5.0 },
    { query: 'rare solar part 99', page: 'https://sanocea.com/products/part-b', clicks: 1, impressions: 20, ctr: 0.05, position: 8.0 }
  ];
  const lowVolumeCases = detectQueryCannibalisation(lowVolumeRows);
  assert.equal(lowVolumeCases.length, 0, 'Should ignore query with total impressions < 100');

  // Test Case B: Dominant URL captures >= 80% share -> Not flagged (healthy clear primary URL)
  const healthyLeaderRows: GscPerformanceRow[] = [
    { query: 'solar panels for home', page: 'https://sanocea.com/collections/solar-panels', clicks: 90, impressions: 1800, ctr: 0.05, position: 3.2 },
    { query: 'solar panels for home', page: 'https://sanocea.com/blogs/solar-guide', clicks: 5, impressions: 200, ctr: 0.025, position: 14.5 }
  ];
  const healthyCases = detectQueryCannibalisation(healthyLeaderRows);
  assert.equal(healthyCases.length, 0, 'Should ignore queries where dominant URL has >= 80% impression share');

  // Test Case C: True Cannibalisation (split impressions: 55% vs 45%, volume = 1,000, both rank on Page 1/2)
  const cannibalRows: GscPerformanceRow[] = [
    { query: 'waaree 540w bifacial solar panel', page: 'https://sanocea.com/products/waaree-540w-bifacial', clicks: 35, impressions: 550, ctr: 0.064, position: 4.8 },
    { query: 'waaree 540w bifacial solar panel', page: 'https://sanocea.com/collections/waaree-solar-panels', clicks: 25, impressions: 450, ctr: 0.055, position: 6.2 }
  ];
  const cannibalCases = detectQueryCannibalisation(cannibalRows);
  assert.equal(cannibalCases.length, 1);
  assert.equal(cannibalCases[0].query, 'waaree 540w bifacial solar panel');
  assert.equal(cannibalCases[0].totalImpressions, 1000);
  assert.equal(cannibalCases[0].dominantShare, 0.55);
  assert.equal(cannibalCases[0].severity, 'HIGH');

  // Convert to findings
  const findings = formatCannibalisationFindings(cannibalCases);
  assert.equal(findings.length, 1);
  assert.equal(findings[0].detectionRule, 'QUERY_PAGE_CANNIBALISATION');
  assert.equal(findings[0].track, 'SEARCH_INTELLIGENCE');
  assert.equal(findings[0].category, 'Search Performance');
  assert.equal(findings[0].commercialRisk?.confidence, '[REQUIRES_ACCESS]');

  // Test Case D: Intent Mismatch (Commercial query where blog outranks product page)
  const intentMismatchRows: GscPerformanceRow[] = [
    { query: 'buy carzex led headlight bulb h7', page: 'https://sanocea.com/blogs/news/carzex-led-review', clicks: 12, impressions: 400, ctr: 0.03, position: 4.1 },
    { query: 'buy carzex led headlight bulb h7', page: 'https://sanocea.com/products/carzex-h7-led-bulb', clicks: 18, impressions: 300, ctr: 0.06, position: 7.5 }
  ];
  const mismatchCases = detectQueryCannibalisation(intentMismatchRows);
  assert.equal(mismatchCases.length, 1);
  assert.equal(mismatchCases[0].intentMismatch, true);
  assert.equal(mismatchCases[0].severity, 'CRITICAL', 'Intent mismatch on commercial query should escalate to CRITICAL');
});

test('Milestone 5.2.2 — Indexation & Coverage: Canonical Override, Soft 404, Crawled/Discovered Not Indexed', () => {
  const crawledPages = new Map<string, CrawledPage>();
  crawledPages.set('https://sanocea.com/products/solar-inverter', {
    url: 'https://sanocea.com/products/solar-inverter',
    status: 200,
    headers: {},
    rawHtml: '<html><head><title>Solar Inverter</title></head><body><h1>Inverter</h1></body></html>',
    isJsRendered: false,
    executionTimeMs: 15,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  });

  const sitemapUrls = new Set<string>([
    'https://sanocea.com/products/solar-inverter',
    'https://sanocea.com/products/solar-panel-400w',
    'https://sanocea.com/collections/accessories'
  ]);

  const inspectionRecords = new Map<string, GscUrlInspectionRecord>();

  // 1. Google-selected canonical override
  inspectionRecords.set('https://sanocea.com/products/solar-inverter', {
    url: 'https://sanocea.com/products/solar-inverter',
    verdict: 'NEUTRAL',
    coverageState: 'INDEXED',
    indexingStatus: 'INDEXED',
    userCanonical: 'https://sanocea.com/products/solar-inverter',
    googleCanonical: 'https://sanocea.com/products/solar-inverter?variant=default'
  });

  // 2. Discovered - currently not indexed
  inspectionRecords.set('https://sanocea.com/products/solar-panel-400w', {
    url: 'https://sanocea.com/products/solar-panel-400w',
    verdict: 'FAIL',
    coverageState: 'DISCOVERED_NOT_INDEXED',
    indexingStatus: 'EXCLUDED'
  });

  // 3. Crawled - currently not indexed
  inspectionRecords.set('https://sanocea.com/collections/accessories', {
    url: 'https://sanocea.com/collections/accessories',
    verdict: 'FAIL',
    coverageState: 'CRAWLED_NOT_INDEXED',
    indexingStatus: 'EXCLUDED'
  });

  // 4. Soft 404
  inspectionRecords.set('https://sanocea.com/products/discontinued-model', {
    url: 'https://sanocea.com/products/discontinued-model',
    verdict: 'FAIL',
    coverageState: 'SOFT_404',
    indexingStatus: 'EXCLUDED'
  });

  // 5. Indexed page missing from sitemap
  inspectionRecords.set('https://sanocea.com/pages/about-us', {
    url: 'https://sanocea.com/pages/about-us',
    verdict: 'PASS',
    coverageState: 'INDEXED',
    indexingStatus: 'INDEXED'
  });

  const findings = reconcileIndexationIntelligence({
    sitemapUrls,
    crawledPages,
    inspectionRecords
  });

  // Verify all 5 discrepancy cases are identified
  const overrideFinding = findings.find(f => f.detectionRule === 'GOOGLE_SELECTED_CANONICAL_OVERRIDE');
  assert.ok(overrideFinding);
  assert.equal(overrideFinding.severity, 'CRITICAL');
  assert.equal(overrideFinding.commercialRisk?.confidence, '[REQUIRES_ACCESS]');

  const discoveredFinding = findings.find(f => f.detectionRule === 'GSC_DISCOVERED_NOT_INDEXED');
  assert.ok(discoveredFinding);
  assert.equal(discoveredFinding.severity, 'HIGH');

  const crawledFinding = findings.find(f => f.detectionRule === 'GSC_CRAWLED_NOT_INDEXED');
  assert.ok(crawledFinding);
  assert.equal(crawledFinding.severity, 'HIGH');

  const soft404Finding = findings.find(f => f.detectionRule === 'SOFT_404_DETECTED');
  assert.ok(soft404Finding);
  assert.equal(soft404Finding.severity, 'HIGH');

  const missingSitemapFinding = findings.find(f => f.detectionRule === 'GSC_INDEXED_URL_MISSING_FROM_SITEMAP');
  assert.ok(missingSitemapFinding);
  assert.equal(missingSitemapFinding.severity, 'LOW');
});

test('Milestone 5.2.3 — Search Appearance & Schema: Declared vs Real Surfaced Rich Results', () => {
  const crawledPages = new Map<string, CrawledPage>();
  crawledPages.set('https://sanocea.com/products/solar-inverter', {
    url: 'https://sanocea.com/products/solar-inverter',
    status: 200,
    headers: {},
    rawHtml: `
      <html>
        <head>
          <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "Product",
              "name": "Solar Inverter 5kW",
              "offers": {
                "@type": "Offer",
                "price": "45000",
                "priceCurrency": "INR",
                "availability": "https://schema.org/InStock"
              }
            }
          </script>
        </head>
        <body><h1>Solar Inverter</h1></body>
      </html>
    `,
    isJsRendered: false,
    executionTimeMs: 12,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  });

  // Case 1: Storefront has Product schema, site receives 1,200 search impressions, but 0 Merchant Listings impressions
  const disqualifiedSnapshot: GscSnapshot = {
    snapshotId: 'snap-disqualified',
    siteUrl: 'https://sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    totalClicks: 80,
    totalImpressions: 1200,
    averageCtr: 0.067,
    averagePosition: 8.5,
    queryRows: [],
    pageRows: [],
    searchAppearanceRows: [
      // Only standard web search, 0 MERCHANT_LISTINGS or PRODUCT_SNIPPETS
      { searchAppearance: 'TRANSLATED_RESULT', clicks: 2, impressions: 15, ctr: 0.13, position: 4.0 }
    ],
    capturedAt: new Date().toISOString()
  };

  const audit1 = reconcileSearchAppearance({
    crawledPages,
    gscSnapshot: disqualifiedSnapshot
  });

  assert.equal(audit1.hasStorefrontProductSchema, true);
  assert.equal(audit1.gscSearchAppearanceActive, false);
  assert.equal(audit1.findings.length, 1);
  assert.equal(audit1.findings[0].detectionRule, 'STRUCTURED_DATA_SEARCH_APPEARANCE_DISQUALIFIED');
  assert.equal(audit1.findings[0].severity, 'HIGH');
  assert.equal(audit1.findings[0].track, 'TRACK_B_ECOMMERCE_INTELLIGENCE');

  // Case 2: URL Inspection rich results explicit failure
  const inspectionRecords = new Map<string, GscUrlInspectionRecord>();
  inspectionRecords.set('https://sanocea.com/products/solar-inverter', {
    url: 'https://sanocea.com/products/solar-inverter',
    verdict: 'FAIL',
    coverageState: 'INDEXED',
    indexingStatus: 'INDEXED',
    richResultsItems: [
      {
        name: 'Merchant listings',
        verdict: 'FAIL',
        issues: [
          { message: 'Missing field "shippingDetails"', severity: 'ERROR' },
          { message: 'Missing field "hasMerchantReturnPolicy"', severity: 'WARNING' }
        ]
      }
    ]
  });

  const audit2 = reconcileSearchAppearance({
    crawledPages,
    gscSnapshot: disqualifiedSnapshot,
    inspectionRecords
  });

  const richResultError = audit2.findings.find(f => f.detectionRule === 'GSC_RICH_RESULT_ELIGIBILITY_ERROR');
  assert.ok(richResultError);
  assert.equal(richResultError.severity, 'CRITICAL', 'Validation error in rich result should be CRITICAL');
  assert.ok(String(richResultError.observedValue).includes('shippingDetails'));

  // Case 3: Healthy Merchant Listings appearances active
  const healthySnapshot: GscSnapshot = {
    ...disqualifiedSnapshot,
    searchAppearanceRows: [
      { searchAppearance: 'MERCHANT_LISTINGS', clicks: 35, impressions: 620, ctr: 0.056, position: 3.4 },
      { searchAppearance: 'PRODUCT_SNIPPETS', clicks: 22, impressions: 380, ctr: 0.058, position: 4.1 }
    ]
  };

  const audit3 = reconcileSearchAppearance({
    crawledPages,
    gscSnapshot: healthySnapshot
  });

  assert.equal(audit3.gscSearchAppearanceActive, true);
  assert.equal(audit3.merchantListingsImpressions, 620);
  assert.equal(audit3.productSnippetsImpressions, 380);
  // Zero disqualification findings when appearances are active
  const disq = audit3.findings.find(f => f.detectionRule === 'STRUCTURED_DATA_SEARCH_APPEARANCE_DISQUALIFIED');
  assert.equal(disq, undefined);
});

test('Milestone 5.2.4 — Full Pipeline Integration with GSC Telemetry & Priority Engine', async () => {
  // Mock HTML for a target site
  const seedHtml = `
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <title>SANOCEA Test Storefront</title>
        <meta name="description" content="Official test store for high efficiency solar products and vehicle accessories.">
        <link rel="canonical" href="https://sanocea.com/products/inverter">
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "SANOCEA Pure Sine Wave Inverter",
            "offers": {
              "@type": "Offer",
              "price": "18500",
              "priceCurrency": "INR",
              "availability": "https://schema.org/InStock"
            }
          }
        </script>
      </head>
      <body>
        <main>
          <h1>SANOCEA Solar Inverter</h1>
          <p>High performance solar inverter with hybrid charge controller.</p>
        </main>
      </body>
    </html>
  `;

  const gscSnapshot: GscSnapshot = {
    snapshotId: 'snap-full-test',
    siteUrl: 'https://sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    totalClicks: 210,
    totalImpressions: 4500,
    averageCtr: 0.046,
    averagePosition: 6.2,
    queryRows: [
      { query: 'solar hybrid inverter 3kva', page: 'https://sanocea.com/products/inverter', clicks: 45, impressions: 600, ctr: 0.075, position: 4.2 },
      { query: 'solar hybrid inverter 3kva', page: 'https://sanocea.com/collections/inverters', clicks: 35, impressions: 500, ctr: 0.070, position: 5.8 }
    ],
    pageRows: [
      { page: 'https://sanocea.com/products/inverter', clicks: 120, impressions: 2500, ctr: 0.048, position: 5.1 }
    ],
    searchAppearanceRows: [
      // 0 Merchant Listings impressions -> triggers search appearance disqualification
      { searchAppearance: 'TRANSLATED_RESULT', clicks: 5, impressions: 40, ctr: 0.125, position: 3.0 }
    ],
    capturedAt: new Date().toISOString()
  };

  const gscUrlInspection = new Map<string, GscUrlInspectionRecord>();
  gscUrlInspection.set('https://sanocea.com/products/inverter', {
    url: 'https://sanocea.com/products/inverter',
    verdict: 'FAIL',
    coverageState: 'CRAWLED_NOT_INDEXED',
    indexingStatus: 'EXCLUDED'
  });

  const pipeline = new SeoAuditPipeline({
    seedUrl: 'https://sanocea.com/products/inverter',
    maxPages: 1,
    maxDepth: 0,
    allowSubdomains: false,
    enableJsRendering: false,
    customRobotsTxt: 'User-agent: *\nAllow: /',
    gscSnapshot,
    gscUrlInspection
  });

  (pipeline as any).crawler.crawlAll = async () => {
    const map = new Map();
    map.set('https://sanocea.com/products/inverter', {
      url: 'https://sanocea.com/products/inverter',
      status: 200,
      headers: {},
      rawHtml: seedHtml,
      isJsRendered: false,
      executionTimeMs: 10,
      discoveredUrls: [],
      crawledAt: new Date().toISOString()
    });
    return map;
  };

  const report = await pipeline.runAudit();

  // 1. Verify Search Intelligence Summary is attached
  assert.ok(report.searchIntelligence);
  assert.equal(report.searchIntelligence.gscConnected, true);
  assert.equal(report.searchIntelligence.cannibalisationCases?.length, 1);
  assert.equal(report.searchIntelligence.indexationDiscrepanciesCount, 1);
  assert.equal(report.searchIntelligence.searchAppearanceDiscrepanciesCount, 1);

  // 2. Verify Search Intel findings are present in master findings array
  const cannibalFinding = report.findings.find(f => f.detectionRule === 'QUERY_PAGE_CANNIBALISATION');
  assert.ok(cannibalFinding);
  assert.equal(cannibalFinding.track, 'SEARCH_INTELLIGENCE');

  const indexFinding = report.findings.find(f => f.detectionRule === 'GSC_CRAWLED_NOT_INDEXED');
  assert.ok(indexFinding);
  assert.equal(indexFinding.track, 'SEARCH_INTELLIGENCE');

  const appearanceFinding = report.findings.find(f => f.detectionRule === 'STRUCTURED_DATA_SEARCH_APPEARANCE_DISQUALIFIED');
  assert.ok(appearanceFinding);
  assert.equal(appearanceFinding.track, 'TRACK_B_ECOMMERCE_INTELLIGENCE');

  // 3. Verify Executive Decision Queue incorporates prioritised items
  assert.ok(report.executiveDecisionQueue && report.executiveDecisionQueue.length > 0);
  assert.ok(report.executiveDecisionQueue.length <= 5);

  // 4. Verify searchIntelSummary counts
  assert.ok(report.searchIntelSummary);
  assert.ok(report.searchIntelSummary.findingsCount >= 2);
});
