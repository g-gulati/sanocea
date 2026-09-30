/**
 * SANOCEA SEO Stack — Verification & Test Suite
 * Phase 3: Commercial Client-Audit & Dual-Track Intelligence Engine
 * 
 * Tests:
 * 1. Pixel Width & Typography Metric Calculations
 * 2. URL Discovery, Normalization & Scope Boundaries
 * 3. Exact Reproduction of Sanocea.com Baseline Findings (Title, Meta, SSR H1, Internal Outlinks)
 * 4. Confirmation of Why Screaming Frog Found Only a Handful of URLs
 * 5. GEO / AI Readiness Classification (Informational Observation, NOT an SEO error)
 * 6. Ecommerce Intelligence: Shopify Collection Dilution & InStock Schema Contradiction
 * 7. End-to-End Closed-Loop Remediation, Approval & Verification Pipeline
 * 8. Crawl Graph Construction & Orphan Page Detection
 * 9. Redirect Chain & Loop Tracing
 * 10. Track A Core SEO: Skipped Headings, Missing Image Alt, Thin Content & Generic Anchors
 * 11. Track B Ecommerce: Variant Canonicalization, Faceted Bloat & Price Mismatch
 * 12. Business Impact & Commercial Risk Quantification
 * 13. Client Report Generator (Interactive HTML Report)
 * 14. WhatsApp Executive Dispatch Formatting
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import * as cheerio from 'cheerio';

import { 
  calculateTitlePixelWidth, 
  calculateMetaDescPixelWidth, 
  GOOGLE_SERP_LIMITS 
} from '../src/core/pixelWidth.js';
import { 
  normalizeUrl, 
  isUrlInScope, 
  parseSitemapXml, 
  parseRobotsTxt,
  buildCrawlGraph,
  traceRedirects
} from '../src/core/urlDiscovery.js';
import { 
  SANOCEA_BASELINE_HTML, 
  SANOCEA_ROBOTS_TXT, 
  SHOPIFY_TEST_STORE_HTML 
} from '../src/fixtures/sanoceaFixtures.js';
import { 
  SeoAuditPipeline, 
  ClosedLoopRemediator 
} from '../src/pipeline/auditPipeline.js';
import { evaluateJsEscalationNeed } from '../src/core/crawler.js';
import { estimateCommercialRisk } from '../src/core/businessImpact.js';
import { runTechnicalSeoObserver } from '../src/observers/technicalSeoObserver.js';
import { runEcommerceObserver } from '../src/observers/ecommerceObserver.js';
import { ClientReportGenerator } from '../src/reporting/clientReportGenerator.js';
import { CrawledPage, PageAuditContext } from '../src/core/types.js';

test('1. Pixel Width Calculation — SERP Limits', () => {
  const sanoceaTitle = 'SANOCEA™ | AI-Assisted Ecommerce Operations & Marketplace Exception Automation';
  const pixelWidth = calculateTitlePixelWidth(sanoceaTitle);

  assert.equal(sanoceaTitle.length, 78);
  assert.ok(pixelWidth > GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS, `Title pixel width (${pixelWidth}px) must exceed ${GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS}px`);
  assert.ok(pixelWidth >= 610 && pixelWidth <= 630, `Calculated width (${pixelWidth}px) should match ~618px`);

  const conciseTitle = 'SANOCEA™ | AI-Assisted Ecommerce Operations';
  const conciseWidth = calculateTitlePixelWidth(conciseTitle);
  assert.ok(conciseWidth <= GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS, `Concise title (${conciseWidth}px) must fit within ${GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS}px`);

  const metaDesc = 'SANOCEA™ helps ecommerce businesses automate repetitive operational work across catalogue, inventory, pricing, orders, fulfilment, reconciliation, and marketplace exceptions — while keeping humans in control of important decisions.';
  assert.equal(metaDesc.length, 231);
  const metaDescWidth = calculateMetaDescPixelWidth(metaDesc);
  assert.ok(metaDescWidth > GOOGLE_SERP_LIMITS.META_DESC_MAX_PIXELS, `Meta desc width (${metaDescWidth}px) must exceed ${GOOGLE_SERP_LIMITS.META_DESC_MAX_PIXELS}px`);
});

test('2. URL Discovery & Normalization', () => {
  const messyUrl = 'https://www.SANOCEA.com/solutions/marketplace-reconciliation/?utm_source=google&utm_medium=cpc#diagnostic';
  const normalized = normalizeUrl(messyUrl);
  assert.equal(normalized, 'https://www.sanocea.com/solutions/marketplace-reconciliation');

  assert.ok(isUrlInScope('https://www.sanocea.com/demo.html', 'https://www.sanocea.com/'));
  assert.ok(isUrlInScope('https://book.sanocea.com/embed.js', 'https://www.sanocea.com/', true));
  assert.equal(isUrlInScope('https://book.sanocea.com/embed.js', 'https://www.sanocea.com/', false), false);
  assert.equal(isUrlInScope('https://google.com/', 'https://www.sanocea.com/'), false);

  const robots = parseRobotsTxt(`
User-agent: *
Disallow: /admin/
Sitemap: https://www.sanocea.com/sitemap.xml

User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Allow: /
  `);

  assert.equal(robots.sitemaps.length, 1);
  assert.equal(robots.sitemaps[0], 'https://www.sanocea.com/sitemap.xml');
  assert.equal(robots.aiBotDirectives['gptbot'].allowed, false);
  assert.equal(robots.aiBotDirectives['claudebot'].allowed, true);
});

test('3. Sanocea.com Baseline Findings Reproduction', async () => {
  const pipeline = new SeoAuditPipeline({
    seedUrl: 'https://www.sanocea.com/',
    maxPages: 1,
    maxDepth: 0,
    allowSubdomains: false,
    enableJsRendering: false,
    customRobotsTxt: SANOCEA_ROBOTS_TXT
  });

  (pipeline as any).crawler.crawlAll = async () => {
    const map = new Map();
    map.set('https://www.sanocea.com/', {
      url: 'https://www.sanocea.com/',
      status: 200,
      headers: {},
      rawHtml: SANOCEA_BASELINE_HTML,
      isJsRendered: false,
      executionTimeMs: 10,
      discoveredUrls: [],
      crawledAt: new Date().toISOString()
    });
    return map;
  };

  const report = await pipeline.runAudit();

  const titleFinding = report.findings.find(f => f.detectionRule === 'TITLE_PIXEL_WIDTH_EXCEEDED');
  assert.ok(titleFinding, 'Must detect TITLE_PIXEL_WIDTH_EXCEEDED');
  assert.equal(titleFinding.severity, 'HIGH');
  assert.equal(titleFinding.track, 'TRACK_A_CORE_SEO');
  assert.equal(titleFinding.evidenceClass, '[O] Observed');
  assert.ok(Number(titleFinding.exactEvidence.pixelWidth) > 561);

  const metaFinding = report.findings.find(f => f.detectionRule === 'META_DESCRIPTION_LENGTH_EXCEEDED');
  assert.ok(metaFinding, 'Must detect META_DESCRIPTION_LENGTH_EXCEEDED');
  assert.equal(metaFinding.severity, 'MEDIUM');
  assert.equal(metaFinding.exactEvidence.charLength, 231);

  const h1Finding = report.findings.find(f => f.detectionRule === 'H1_HEADING_MISSING_IN_SSR');
  assert.ok(h1Finding, 'Must detect H1_HEADING_MISSING_IN_SSR');
  assert.equal(h1Finding.severity, 'CRITICAL');
  assert.equal(h1Finding.observedValue, '0 <h1> tags found in static server-rendered HTML');

  const outlinkFinding = report.findings.find(f => f.detectionRule === 'PAGES_WITHOUT_INTERNAL_OUTLINKS');
  assert.ok(outlinkFinding, 'Must detect PAGES_WITHOUT_INTERNAL_OUTLINKS');
  assert.equal(outlinkFinding.severity, 'HIGH');

  const secFinding = report.findings.find(f => f.detectionRule === 'SECURITY_MISSING_X_CONTENT_TYPE_OPTIONS');
  assert.ok(secFinding, 'Must detect missing X-Content-Type-Options');
});

test('4. Diagnostic Analysis: Why Screaming Frog Found Only a Handful of URLs', () => {
  const escalation = evaluateJsEscalationNeed(SANOCEA_BASELINE_HTML);
  assert.ok(escalation.needsEscalation, 'Baseline HTML must trigger JS escalation');
  assert.ok(escalation.reasons.some(r => r.includes('#root')));
  assert.ok(escalation.reasons.some(r => r.includes('<h1>')));
  assert.ok(escalation.reasons.some(r => r.includes('internal <a> links')));

  const $ = cheerio.load(SANOCEA_BASELINE_HTML);
  const internalLinks = $('a[href]').length;
  assert.equal(internalLinks, 0, 'Sanocea baseline raw HTML contains 0 <a> tags; HTTP crawlers without JS cannot discover subsequent pages!');
});

test('5. GEO / AI Readiness Classification — Observations, NOT Errors', async () => {
  const pipeline = new SeoAuditPipeline({
    seedUrl: 'https://www.sanocea.com/',
    maxPages: 1,
    maxDepth: 0,
    allowSubdomains: false,
    enableJsRendering: false,
    customRobotsTxt: SANOCEA_ROBOTS_TXT
  });

  const report = await pipeline.runAudit();

  const llmsFinding = report.findings.find(f => f.category === 'GEO / AI Readiness');
  assert.ok(llmsFinding, 'Must identify GEO / AI Readiness item');
  assert.equal(llmsFinding.severity, 'INFO', 'GEO Readiness must be classified as INFO, NOT an SEO error');
  assert.equal(llmsFinding.evidenceClass, '[GEO] GEO Readiness', 'Evidence class must be [GEO] GEO Readiness');
  assert.equal(llmsFinding.track, 'GEO_READINESS');
  assert.equal(llmsFinding.remediationStatus, 'INFORMATIONAL', 'Status must be INFORMATIONAL');
});

test('6. Ecommerce Intelligence: Shopify Dilution & InStock Conflict', async () => {
  const pipeline = new SeoAuditPipeline({
    seedUrl: 'https://store.example.com/',
    maxPages: 1,
    maxDepth: 0,
    allowSubdomains: false,
    enableJsRendering: false
  });

  const page = await (pipeline as any).crawler.crawlSingle('https://store.example.com/');
  page.rawHtml = SHOPIFY_TEST_STORE_HTML;

  const report = await pipeline.runAudit();

  const dilutionFinding = report.findings.find(f => f.detectionRule === 'SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION');
  assert.ok(dilutionFinding, 'Must detect SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION');
  assert.equal(dilutionFinding.severity, 'HIGH');
  assert.equal(dilutionFinding.track, 'TRACK_B_ECOMMERCE_INTELLIGENCE');

  const stockLeakFinding = report.findings.find(f => f.detectionRule === 'STRUCTURED_DATA_INSTOCK_WHEN_OOS');
  assert.ok(stockLeakFinding, 'Must detect STRUCTURED_DATA_INSTOCK_WHEN_OOS');
  assert.equal(stockLeakFinding.severity, 'CRITICAL');
  assert.equal(stockLeakFinding.track, 'TRACK_B_ECOMMERCE_INTELLIGENCE');
  assert.ok(stockLeakFinding.commercialRisk, 'Must attach commercial risk');
  assert.equal(stockLeakFinding.commercialRisk?.riskType, 'GMC_ACCOUNT_SUSPENSION');

  const gtinFinding = report.findings.find(f => f.detectionRule === 'PRODUCT_SCHEMA_GTIN_MISSING');
  assert.ok(gtinFinding, 'Must detect PRODUCT_SCHEMA_GTIN_MISSING');
});

test('7. Closed-Loop Remediation, Approval & Verification Pipeline', () => {
  const initialHtml = SANOCEA_BASELINE_HTML;
  const initialTitle = 'SANOCEA™ | AI-Assisted Ecommerce Operations & Marketplace Exception Automation';
  assert.ok(calculateTitlePixelWidth(initialTitle) > 561);

  const finding = {
    findingId: 'SAN-TEST-TITLE-01',
    url: 'https://www.sanocea.com/',
    routeIntent: 'MARKETING_LANDING_PAGE' as const,
    detectionRule: 'TITLE_PIXEL_WIDTH_EXCEEDED',
    track: 'TRACK_A_CORE_SEO' as const,
    category: 'Technical SEO' as const,
    severity: 'HIGH' as const,
    evidenceClass: '[O] Observed' as const,
    observedValue: '618px',
    expectedValue: '≤ 561px',
    exactEvidence: { pixelWidth: 618 },
    reproductionMethod: 'calculateTitlePixelWidth()',
    businessImpact: 'SERP title truncation',
    recommendedRemediation: 'Shorten title',
    automaticallyFixable: true,
    requiredAccess: 'HTML source',
    remediationStatus: 'APPROVED' as const,
    beforeEvidence: initialTitle,
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const approvedTitle = 'SANOCEA™ | AI-Assisted Ecommerce Operations';
  const remediatedHtml = ClosedLoopRemediator.applyRemediation(initialHtml, finding, approvedTitle);

  assert.ok(remediatedHtml.includes(`<title>${approvedTitle}</title>`));
  assert.ok(!remediatedHtml.includes(initialTitle));

  const verification = ClosedLoopRemediator.verifyRemediation(finding, remediatedHtml, {
    seedUrl: 'https://www.sanocea.com/',
    maxPages: 1,
    maxDepth: 0,
    allowSubdomains: false,
    enableJsRendering: false
  });

  assert.equal(verification.isResolved, true, 'Finding must be independently verified as resolved');
  assert.equal(verification.findingAfter, null, 'No new finding of this type should be emitted');
  assert.equal(verification.afterEvidence, approvedTitle);
});

test('8. Crawl Graph Construction & Orphan Page Detection', () => {
  const crawledPages = new Map<string, CrawledPage>();
  
  // Page 1: Homepage links to /about and /products
  crawledPages.set('https://example.com/', {
    url: 'https://example.com/',
    status: 200,
    headers: {},
    rawHtml: '<html><body><a href="/about">About</a><a href="/products">Products</a></body></html>',
    isJsRendered: false,
    executionTimeMs: 10,
    discoveredUrls: [
      { url: 'https://example.com/about', source: 'internal_link', depth: 1 },
      { url: 'https://example.com/products', source: 'internal_link', depth: 1 }
    ],
    crawledAt: new Date().toISOString()
  });

  // Page 2: /about
  crawledPages.set('https://example.com/about', {
    url: 'https://example.com/about',
    status: 200,
    headers: {},
    rawHtml: '<html><body><a href="/">Home</a></body></html>',
    isJsRendered: false,
    executionTimeMs: 10,
    discoveredUrls: [{ url: 'https://example.com/', source: 'internal_link', depth: 2 }],
    crawledAt: new Date().toISOString()
  });

  // Page 3: /products
  crawledPages.set('https://example.com/products', {
    url: 'https://example.com/products',
    status: 200,
    headers: {},
    rawHtml: '<html><body><a href="/">Home</a></body></html>',
    isJsRendered: false,
    executionTimeMs: 10,
    discoveredUrls: [{ url: 'https://example.com/', source: 'internal_link', depth: 2 }],
    crawledAt: new Date().toISOString()
  });

  // Page 4: Orphan in sitemap but never linked in DOM
  const sitemapUrls = new Set([
    'https://example.com/',
    'https://example.com/about',
    'https://example.com/products',
    'https://example.com/unlinked-promo'
  ]);

  const { graph, summary } = buildCrawlGraph(crawledPages, sitemapUrls);

  assert.equal(summary.totalNodes, 4);
  assert.equal(summary.totalEdges, 4);
  assert.ok(summary.orphanPages.includes('https://example.com/unlinked-promo'), 'Must identify unlinked-promo as an orphan page');
  assert.equal(graph.get('https://example.com/unlinked-promo')?.isOrphan, true);
  assert.equal(graph.get('https://example.com/about')?.inDegree, 1);
  assert.equal(graph.get('https://example.com/')?.inDegree, 2);
});

test('9. Redirect Chain & Loop Tracing', async () => {
  // Test 3-hop redirect chain: A -> B -> C -> Final
  const mockFetch = async (url: string) => {
    if (url === 'https://example.com/a') {
      return { status: 301, location: 'https://example.com/b' };
    }
    if (url === 'https://example.com/b') {
      return { status: 302, location: 'https://example.com/c' };
    }
    if (url === 'https://example.com/c') {
      return { status: 200 };
    }
    return { status: 404 };
  };

  const trace = await traceRedirects('https://example.com/a', 5, mockFetch);
  assert.equal(trace.hopCount, 2);
  assert.equal(trace.finalUrl, 'https://example.com/c');
  assert.equal(trace.isLoop, false);

  // Test redirect loop: X -> Y -> X
  const mockLoopFetch = async (url: string) => {
    if (url === 'https://example.com/x') {
      return { status: 301, location: 'https://example.com/y' };
    }
    if (url === 'https://example.com/y') {
      return { status: 301, location: 'https://example.com/x' };
    }
    return { status: 200 };
  };

  const loopTrace = await traceRedirects('https://example.com/x', 5, mockLoopFetch);
  assert.equal(loopTrace.isLoop, true, 'Must detect redirect loop');
});

test('10. Track A Core SEO: Skipped Headings, Missing Image Alt, Thin Content & Generic Anchors', () => {
  const testHtml = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Short Title</title>
        <meta name="description" content="Valid meta description between 70 and 155 characters that provides clear value to readers.">
        <link rel="canonical" href="https://example.com/article">
      </head>
      <body>
        <h1>Primary Headline</h1>
        <h3>Skipped Level Subheading</h3>
        <p>Short paragraph with only few words.</p>
        <img src="/broken-asset.jpg">
        <a href="/dest">click here</a>
        <a href="/dest2">read more</a>
      </body>
    </html>
  `;

  const page: CrawledPage = {
    url: 'https://example.com/article',
    status: 200,
    headers: {
      'x-content-type-options': 'nosniff',
      'x-frame-options': 'DENY',
      'content-security-policy': "default-src 'self'",
      'strict-transport-security': 'max-age=31536000',
      'referrer-policy': 'strict-origin-when-cross-origin'
    },
    rawHtml: testHtml,
    isJsRendered: false,
    executionTimeMs: 15,
    discoveredUrls: [
      { url: 'https://example.com/dest', source: 'internal_link', depth: 1 }
    ],
    crawledAt: new Date().toISOString()
  };

  const context: PageAuditContext = {
    page,
    $: cheerio.load(testHtml),
    isRenderedDom: false,
    crawlConfig: { seedUrl: 'https://example.com/', maxPages: 1, maxDepth: 0, allowSubdomains: false, enableJsRendering: false }
  };

  const findings = runTechnicalSeoObserver(context);

  // Check skipped heading
  const skipFinding = findings.find(f => f.detectionRule === 'HEADING_LEVEL_SKIPPED');
  assert.ok(skipFinding, 'Must detect HEADING_LEVEL_SKIPPED (h1 to h3)');
  assert.equal(skipFinding.severity, 'LOW');

  // Check image alt missing
  const imgFinding = findings.find(f => f.detectionRule === 'IMAGE_ALT_TAGS_MISSING');
  assert.ok(imgFinding, 'Must detect IMAGE_ALT_TAGS_MISSING');
  assert.equal(imgFinding.severity, 'MEDIUM');

  // Check thin content (< 100 words)
  const thinFinding = findings.find(f => f.detectionRule === 'THIN_CONTENT_DETECTED');
  assert.ok(thinFinding, 'Must detect THIN_CONTENT_DETECTED');
  assert.equal(thinFinding.severity, 'HIGH');

  // Check generic anchors
  const anchorFinding = findings.find(f => f.detectionRule === 'GENERIC_ANCHOR_TEXT_DETECTED');
  assert.ok(anchorFinding, 'Must detect GENERIC_ANCHOR_TEXT_DETECTED (click here / read more)');
  assert.equal(anchorFinding.severity, 'LOW');
});

test('11. Track B Ecommerce: Variant Canonicalization, Faceted Bloat & Price Mismatch', () => {
  const ecomHtml = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Solar Panel 540W Mono</title>
        <link rel="canonical" href="https://shop.example.com/products/solar-panel-540w?variant=998877">
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "name": "Solar Panel 540W Mono",
          "offers": {
            "@type": "Offer",
            "price": "14999.00",
            "priceCurrency": "INR",
            "availability": "https://schema.org/InStock"
          }
        }
        </script>
      </head>
      <body>
        <h1>Solar Panel 540W Mono</h1>
        <div class="price">₹17,499</div>
      </body>
    </html>
  `;

  const page: CrawledPage = {
    url: 'https://shop.example.com/products/solar-panel-540w?variant=998877',
    status: 200,
    headers: {},
    rawHtml: ecomHtml,
    isJsRendered: false,
    executionTimeMs: 20,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  };

  const context: PageAuditContext = {
    page,
    $: cheerio.load(ecomHtml),
    isRenderedDom: false,
    crawlConfig: { seedUrl: 'https://shop.example.com/', maxPages: 1, maxDepth: 0, allowSubdomains: false, enableJsRendering: false }
  };

  const findings = runEcommerceObserver(context);

  // Check 1: Variant canonical retains ?variant=
  const variantCanonFinding = findings.find(f => f.detectionRule === 'VARIANT_CANONICAL_PARAM_DILUTION');
  assert.ok(variantCanonFinding, 'Must detect VARIANT_CANONICAL_PARAM_DILUTION');
  assert.equal(variantCanonFinding.severity, 'HIGH');

  // Check 2: Price Mismatch (DOM ₹17,499 vs Schema 14999.00)
  const priceMismatchFinding = findings.find(f => f.detectionRule === 'STRUCTURED_DATA_PRICE_MISMATCH');
  assert.ok(priceMismatchFinding, 'Must detect STRUCTURED_DATA_PRICE_MISMATCH');
  assert.equal(priceMismatchFinding.severity, 'HIGH');
  assert.ok(priceMismatchFinding.commercialRisk);
  assert.equal(priceMismatchFinding.commercialRisk.riskType, 'BUY_BOX_REVENUE_EROSION');
});

test('12. Business Impact & Commercial Risk Quantification', () => {
  const gmcRisk = estimateCommercialRisk('STRUCTURED_DATA_INSTOCK_WHEN_OOS', 'https://shop.waaree.com/products/inverter');
  assert.equal(gmcRisk.commercialRisk.riskType, 'GMC_ACCOUNT_SUSPENSION');
  assert.ok(gmcRisk.commercialRisk.estimatedMonthlyLossInr !== undefined && gmcRisk.commercialRisk.estimatedMonthlyLossInr >= 400000);
  assert.ok(gmcRisk.automationOpportunity?.automatable);

  const dilutionRisk = estimateCommercialRisk('SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION', 'https://store.com/collections/all');
  assert.equal(dilutionRisk.commercialRisk.riskType, 'CRAWL_BUDGET_DILUTION');
  assert.ok(dilutionRisk.commercialRisk.estimatedMonthlyLossInr !== undefined && dilutionRisk.commercialRisk.estimatedMonthlyLossInr > 0);
  assert.equal(dilutionRisk.automationOpportunity?.recipeType, 'SHOPIFY_LIQUID');
});

test('13. Client Report Generator (Interactive HTML Report)', () => {
  const mockReport = {
    id: 'SAN-REPORT-TEST',
    targetDomain: 'https://shop.waaree.com',
    crawledPagesCount: 15,
    discoveredUrlsCount: 42,
    findingsCount: 4,
    totalCommercialRiskInr: 520000,
    trackASummary: { findingsCount: 2, criticalCount: 1, highCount: 1 },
    trackBSummary: { findingsCount: 2, criticalCount: 1, highCount: 1 },
    geoSummary: { findingsCount: 1, readinessScore: 85 },
    severitySummary: { CRITICAL: 2, HIGH: 2, MEDIUM: 0, LOW: 0, INFO: 0 },
    evidenceClassSummary: { '[O] Observed': 4, '[I] Inferred': 0, '[V] Validation Required': 0, '[GEO] GEO Readiness': 0 },
    commercialRiskBreakdown: {
      GMC_ACCOUNT_SUSPENSION: 420000,
      BUY_BOX_REVENUE_EROSION: 100000,
      CRAWL_BUDGET_DILUTION: 0,
      SERP_CTR_LEAK: 0,
      INDEXATION_PURGE: 0,
      COMPLIANCE_PENALTY: 0,
      CONVERSION_FRICTION: 0
    },
    crawlGraphSummary: {
      totalNodes: 15,
      totalEdges: 35,
      orphanPages: ['https://shop.waaree.com/orphaned-page'],
      deepestPages: [],
      highestInDegreePages: []
    },
    redirectTraces: [],
    findings: [
      {
        findingId: 'FINDING-1',
        url: 'https://shop.waaree.com/products/panel',
        routeIntent: 'PRODUCT_DISPLAY_PAGE' as const,
        detectionRule: 'STRUCTURED_DATA_INSTOCK_WHEN_OOS',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE' as const,
        category: 'Ecommerce' as const,
        severity: 'CRITICAL' as const,
        evidenceClass: '[O] Observed' as const,
        observedValue: 'InStock',
        expectedValue: 'OutOfStock',
        exactEvidence: { stockFound: 'InStock', stockExpected: 'OutOfStock' },
        reproductionMethod: 'curl test',
        businessImpact: 'GMC suspension risk',
        commercialRisk: {
          riskType: 'GMC_ACCOUNT_SUSPENSION' as const,
          title: 'Google Merchant Center Suspension',
          estimatedMonthlyLossInr: 420000,
          currency: 'INR' as const,
          confidence: '[REQUIRES_ACCESS]' as const,
          source: 'requires_merchant_telemetry' as const,
          severityScore: 5 as const,
          calculationFormula: 'GMV exposure formula'
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'SCHEMA_INJECTION' as const,
          primaryMechanism: 'STOREFRONT_API' as const,
          fallbackMechanisms: ['SUPPLEMENTAL_FEED' as const],
          requiredAccessTier: 'FEED_ONLY' as const,
          requiredRole: 'ENGINEERING' as const,
          description: 'Fix schema availability'
        },
        recommendedRemediation: 'Output OutOfStock',
        automaticallyFixable: true,
        requiredAccess: 'Liquid',
        remediationStatus: 'ACTION_REQUIRED' as const,
        beforeEvidence: 'InStock',
        afterEvidence: null,
        verificationResult: null,
        timestamp: new Date().toISOString()
      }
    ],
    generatedAt: new Date().toISOString(),
    durationMs: 1200,
    crawlDiagnostics: {
      jsEscalationsCount: 0,
      sitemapsFound: [],
      robotsTxtPresent: true
    }
  };

  const html = ClientReportGenerator.generateHtmlReport(mockReport);
  assert.ok(html.includes('SANOCEA SEO & Commerce Audit'));
  assert.ok(html.includes('₹5,20,000'));
  assert.ok(html.includes('GMC ACCOUNT SUSPENSION'));
  assert.ok(html.includes('STRUCTURED_DATA_INSTOCK_WHEN_OOS'));
  assert.ok(html.includes('WhatsApp Executive Dispatch Preview'));
});

test('14. WhatsApp Executive Dispatch Formatting', () => {
  const mockReport = {
    id: 'SAN-REPORT-TEST',
    targetDomain: 'https://shop.waaree.com',
    crawledPagesCount: 15,
    discoveredUrlsCount: 42,
    findingsCount: 1,
    totalCommercialRiskInr: 420000,
    trackASummary: { findingsCount: 0, criticalCount: 0, highCount: 0 },
    trackBSummary: { findingsCount: 1, criticalCount: 1, highCount: 0 },
    geoSummary: { findingsCount: 0, readinessScore: 70 },
    severitySummary: { CRITICAL: 1, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 },
    evidenceClassSummary: { '[O] Observed': 1, '[I] Inferred': 0, '[V] Validation Required': 0, '[GEO] GEO Readiness': 0 },
    commercialRiskBreakdown: {
      GMC_ACCOUNT_SUSPENSION: 420000,
      BUY_BOX_REVENUE_EROSION: 0,
      CRAWL_BUDGET_DILUTION: 0,
      SERP_CTR_LEAK: 0,
      INDEXATION_PURGE: 0,
      COMPLIANCE_PENALTY: 0,
      CONVERSION_FRICTION: 0
    },
    crawlGraphSummary: { totalNodes: 1, totalEdges: 0, orphanPages: [], deepestPages: [], highestInDegreePages: [] },
    redirectTraces: [],
    findings: [
      {
        findingId: 'F-1',
        url: 'https://shop.waaree.com/products/solar-panel',
        routeIntent: 'PRODUCT_DISPLAY_PAGE' as const,
        detectionRule: 'STRUCTURED_DATA_INSTOCK_WHEN_OOS',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE' as const,
        category: 'Ecommerce' as const,
        severity: 'CRITICAL' as const,
        evidenceClass: '[O] Observed' as const,
        observedValue: 'InStock in schema while Sold Out on storefront',
        expectedValue: 'OutOfStock',
        exactEvidence: {},
        reproductionMethod: '',
        businessImpact: '',
        recommendedRemediation: '',
        automaticallyFixable: true,
        requiredAccess: '',
        remediationStatus: 'ACTION_REQUIRED' as const,
        beforeEvidence: null,
        afterEvidence: null,
        verificationResult: null,
        timestamp: new Date().toISOString()
      }
    ],
    generatedAt: new Date().toISOString(),
    durationMs: 500,
    crawlDiagnostics: { jsEscalationsCount: 0, sitemapsFound: [], robotsTxtPresent: true }
  };

  const waText = ClientReportGenerator.generateWhatsAppDispatch(mockReport);
  assert.ok(waText.includes('SANOCEA Technical & Commerce Intelligence Alert'));
  assert.ok(waText.includes('shop.waaree.com'));
  assert.ok(waText.includes('₹4,20,000/month'));
  assert.ok(waText.includes('STRUCTURED_DATA_INSTOCK_WHEN_OOS'));
});
