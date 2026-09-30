/**
 * SANOCEA SEO Stack — Phase 1 Credibility Protection Test Suite
 * 
 * Deliberately tests:
 * 1. Internal search routes (?s=, ?q=, /search?q=)
 * 2. Transactional endpoints (/checkout, /cart, /my-account)
 * 3. Interactive simulators (/demo.html, /calculator)
 * 4. Faceted navigation filters (?filter.p.color=blue)
 * 5. Strict financial provenance ([OBSERVED] / [CALCULATED] / [ESTIMATED] / [REQUIRES_ACCESS])
 * 
 * Verifies ZERO false-positive commercial alerts on non-commercial utility routes,
 * and ZERO benchmark assumptions disguised as calculated numbers.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as cheerio from 'cheerio';
import { classifyRouteIntent, isExpectedNoindex, isUtilityOrNonIndexableIntent } from '../src/core/routeIntent.js';
import { runIndexabilityObserver } from '../src/observers/indexabilityObserver.js';
import { runTechnicalSeoObserver } from '../src/observers/technicalSeoObserver.js';
import { estimateCommercialRisk } from '../src/core/businessImpact.js';
import { PriorityDecisionEngine } from '../src/core/priorityEngine.js';
import { PageAuditContext, CrawledPage } from '../src/core/types.js';

function createMockPageContext(url: string, html: string, headers: Record<string, string> = {}): PageAuditContext {
  const $ = cheerio.load(html);
  const page: CrawledPage = {
    url,
    status: 200,
    headers,
    rawHtml: html,
    isJsRendered: false,
    executionTimeMs: 45,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  };

  return {
    page,
    $,
    isRenderedDom: false,
    crawlConfig: {
      seedUrl: url,
      maxPages: 10,
      maxDepth: 2,
      allowSubdomains: false,
      enableJsRendering: false
    }
  };
}

test('Phase 1.1 — Internal Search Routes: Zero Material False-Positive Commercial Alerts', () => {
  const searchUrls = [
    'https://store.example.com/?s=inverter',
    'https://store.example.com/?q=solar+panel',
    'https://store.example.com/search?q=battery&search_type=product',
    'https://store.example.com/catalogsearch/result/?q=cable'
  ];

  for (const searchUrl of searchUrls) {
    const intent = classifyRouteIntent(searchUrl);
    assert.equal(intent, 'INTERNAL_SEARCH', `Route ${searchUrl} must be classified as INTERNAL_SEARCH`);
    assert.ok(isExpectedNoindex(searchUrl), `Route ${searchUrl} must expect noindex directive`);
    assert.ok(isUtilityOrNonIndexableIntent(intent), `INTERNAL_SEARCH must be recognized as utility/non-indexable`);

    // Simulate search results page with standard noindex and dynamic listing
    const searchHtml = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Search results for query - Store</title>
          <meta name="robots" content="noindex, follow">
        </head>
        <body>
          <div class="search-header">Search results</div>
          <div class="results">Found 12 matching items</div>
        </body>
      </html>
    `;

    const ctx = createMockPageContext(searchUrl, searchHtml);
    const indexabilityFindings = runIndexabilityObserver(ctx);
    const technicalFindings = runTechnicalSeoObserver(ctx);

    // Verify ZERO High/Critical Noindex alarms
    const severeNoindexAlarm = indexabilityFindings.find(f => f.detectionRule === 'NOINDEX_DIRECTIVE_PRESENT');
    assert.equal(severeNoindexAlarm, undefined, 'Search page with noindex MUST NOT emit NOINDEX_DIRECTIVE_PRESENT alert');

    // Verify INFO finding acknowledging expected hygiene
    const infoNoindex = indexabilityFindings.find(f => f.detectionRule === 'NOINDEX_ON_TRANSACTIONAL_ROUTE');
    assert.ok(infoNoindex, 'Must emit informational validation of standard search hygiene');
    assert.equal(infoNoindex?.severity, 'INFO');

    // Verify ZERO missing canonical, missing H1, or thin content alarms on search
    const missingCanon = indexabilityFindings.find(f => f.detectionRule === 'CANONICAL_TAG_MISSING');
    assert.equal(missingCanon, undefined, 'Search page MUST NOT emit missing canonical alarm');

    const missingH1 = technicalFindings.find(f => f.detectionRule === 'H1_HEADING_MISSING_IN_SSR');
    assert.equal(missingH1, undefined, 'Search page MUST NOT emit critical missing H1 alarm');

    const thinContent = technicalFindings.find(f => f.detectionRule === 'THIN_CONTENT_DETECTED');
    assert.equal(thinContent, undefined, 'Search page MUST NOT emit thin content alarm');

    // Verify Priority Decision Queue quarantines search items to P4
    const queue = PriorityDecisionEngine.prioritizeFindings([...indexabilityFindings, ...technicalFindings]);
    for (const item of queue) {
      assert.equal(item.priorityTier, 'P4_INFORMATIONAL', `Search finding ${item.detectionRule} must be quarantined to P4`);
    }
  }
});

test('Phase 1.2 — Transactional & Checkout Endpoints: Zero Commercial Distraction', () => {
  const transactionalUrls = [
    'https://store.example.com/cart',
    'https://store.example.com/checkout',
    'https://store.example.com/my-account/orders',
    'https://store.example.com/account/login',
    'https://store.example.com/wishlist'
  ];

  for (const txUrl of transactionalUrls) {
    const intent = classifyRouteIntent(txUrl);
    assert.equal(intent, 'TRANSACTIONAL_UTILITY', `Route ${txUrl} must be classified as TRANSACTIONAL_UTILITY`);
    assert.ok(isExpectedNoindex(txUrl), `Route ${txUrl} must expect noindex`);

    const checkoutHtml = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Secure Checkout</title>
          <meta name="robots" content="noindex, nofollow">
        </head>
        <body>
          <form id="checkout-form"><input type="text" placeholder="Card number"></form>
        </body>
      </html>
    `;

    const ctx = createMockPageContext(txUrl, checkoutHtml);
    const indexabilityFindings = runIndexabilityObserver(ctx);
    const technicalFindings = runTechnicalSeoObserver(ctx);

    // Verify zero high severity indexation alarms
    const badAlert = indexabilityFindings.find(f => f.severity === 'HIGH' || f.severity === 'CRITICAL');
    assert.equal(badAlert, undefined, `Transactional route ${txUrl} must produce zero HIGH/CRITICAL indexation alerts`);

    const missingH1 = technicalFindings.find(f => f.detectionRule === 'H1_HEADING_MISSING_IN_SSR');
    assert.equal(missingH1, undefined, `Transactional route ${txUrl} must not demand an SSR H1`);

    // Verify quarantine to P4
    const queue = PriorityDecisionEngine.prioritizeFindings([...indexabilityFindings, ...technicalFindings]);
    assert.ok(queue.every(q => q.priorityTier === 'P4_INFORMATIONAL'), 'All checkout findings must be P4');
  }
});

test('Phase 1.3 — Interactive Simulators & Diagnostic Tools: Zero Broken-Page Alarms', () => {
  const toolUrls = [
    'https://sanocea.com/demo.html',
    'https://sanocea.com/calculator.html',
    'https://sanocea.com/simulator',
    'https://app.sanocea.com/portal'
  ];

  for (const toolUrl of toolUrls) {
    const intent = classifyRouteIntent(toolUrl);
    assert.equal(intent, 'UTILITY_SIMULATOR', `Tool route ${toolUrl} must be classified as UTILITY_SIMULATOR`);
    assert.ok(isExpectedNoindex(toolUrl));

    // Simulator HTML (Single Page App container, client-loaded JS, no static H1, 20 words)
    const simulatorHtml = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Interactive Simulator Tool</title>
        </head>
        <body>
          <div id="root">Loading interactive widget...</div>
          <script src="/bundle.js"></script>
        </body>
      </html>
    `;

    const ctx = createMockPageContext(toolUrl, simulatorHtml);
    const technicalFindings = runTechnicalSeoObserver(ctx);
    const indexabilityFindings = runIndexabilityObserver(ctx);

    // No critical H1 alarm
    const missingH1 = technicalFindings.find(f => f.detectionRule === 'H1_HEADING_MISSING_IN_SSR');
    assert.equal(missingH1, undefined, 'Simulator must NOT emit CRITICAL H1_HEADING_MISSING_IN_SSR');

    // No thin content alarm
    const thinContent = technicalFindings.find(f => f.detectionRule === 'THIN_CONTENT_DETECTED');
    assert.equal(thinContent, undefined, 'Simulator must NOT emit THIN_CONTENT_DETECTED');

    // No missing canonical alarm
    const missingCanon = indexabilityFindings.find(f => f.detectionRule === 'CANONICAL_TAG_MISSING');
    assert.equal(missingCanon, undefined, 'Simulator must NOT emit CANONICAL_TAG_MISSING');
  }
});

test('Phase 1.4 — Faceted Navigation Filters: Clean Intent Classification', () => {
  const facetedUrls = [
    'https://store.example.com/collections/all?filter.p.color=blue',
    'https://store.example.com/collections/inverters?sort_by=price-ascending&page=2',
    'https://store.example.com/c/batteries?facet.brand=waaree'
  ];

  for (const facetUrl of facetedUrls) {
    const intent = classifyRouteIntent(facetUrl);
    assert.equal(intent, 'FACETED_FILTER', `Faceted URL ${facetUrl} must be classified as FACETED_FILTER`);
    assert.ok(isExpectedNoindex(facetUrl), 'Faceted filter URL should expect noindex');
  }
});

test('Phase 1.5 — Strict Financial Provenance: No Benchmark Assumptions Disguised as Calculated', () => {
  // Case A: Price Discrepancy without Merchant Sales Telemetry
  const uncredentialedPriceMismatch = estimateCommercialRisk('STRUCTURED_DATA_PRICE_MISMATCH', 'https://store.example.com/products/panel-330w', {
    priceDelta: 450
  });

  assert.equal(uncredentialedPriceMismatch.commercialRisk.confidence, '[REQUIRES_ACCESS]', 'Price discrepancy without telemetry must be [REQUIRES_ACCESS]');
  assert.equal(uncredentialedPriceMismatch.commercialRisk.source, 'requires_merchant_telemetry');
  assert.equal(uncredentialedPriceMismatch.commercialRisk.estimatedMonthlyLossInr, undefined, 'Monthly loss must be undefined when sales telemetry is absent');
  assert.equal(uncredentialedPriceMismatch.commercialRisk.observedDataPoints?.observedPriceDeltaInr, 450);
  assert.ok(uncredentialedPriceMismatch.commercialRisk.calculationFormula.includes('[OBSERVED]'));
  assert.ok(uncredentialedPriceMismatch.commercialRisk.calculationFormula.includes('[REQUIRES_ACCESS]'));

  // Case B: Price Discrepancy WITH Confirmed Merchant Sales Volume Telemetry
  const confirmedVolumePriceMismatch = estimateCommercialRisk('STRUCTURED_DATA_PRICE_MISMATCH', 'https://store.example.com/products/panel-330w', {
    priceDelta: 450,
    monthlyUnitVolume: 300
  });

  assert.equal(confirmedVolumePriceMismatch.commercialRisk.confidence, '[CALCULATED]', 'Price discrepancy with confirmed volume is strictly [CALCULATED]');
  assert.equal(confirmedVolumePriceMismatch.commercialRisk.source, 'storefront_dom');
  assert.equal(confirmedVolumePriceMismatch.commercialRisk.estimatedMonthlyLossInr, 450 * 300); // ₹1,35,000
  assert.equal(confirmedVolumePriceMismatch.commercialRisk.observedDataPoints?.verifiedMonthlyUnitVolume, 300);
  assert.ok(confirmedVolumePriceMismatch.commercialRisk.calculationFormula.includes('300 units/mo'));

  // Case C: Projections Derived from Industry Benchmarks MUST be [ESTIMATED]
  const dilution = estimateCommercialRisk('SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION', 'https://store.example.com/collections/all');
  assert.equal(dilution.commercialRisk.confidence, '[ESTIMATED]', 'Canonical dilution must be [ESTIMATED]');
  assert.equal(dilution.commercialRisk.source, 'industry_benchmark_estimate');
  assert.ok(dilution.commercialRisk.assumptions && dilution.commercialRisk.assumptions.length > 0);

  const titleOverflow = estimateCommercialRisk('TITLE_PIXEL_WIDTH_EXCEEDED', 'https://store.example.com/about');
  assert.equal(titleOverflow.commercialRisk.confidence, '[ESTIMATED]', 'SERP CTR truncation must be [ESTIMATED]');
  assert.equal(titleOverflow.commercialRisk.source, 'industry_benchmark_estimate');

  // Case D: Google Merchant Center Stock Contradiction requires merchant telemetry
  const gmcStock = estimateCommercialRisk('STRUCTURED_DATA_INSTOCK_WHEN_OOS', 'https://store.example.com/products/inverter');
  assert.equal(gmcStock.commercialRisk.confidence, '[REQUIRES_ACCESS]');
  assert.equal(gmcStock.commercialRisk.source, 'requires_merchant_telemetry');
});

test('Phase 1.6 — Executive Decision Queue Integrity with Strict Provenance', () => {
  const findings = [
    // 1. Critical Commercial Finding: Price discrepancy without telemetry
    {
      findingId: 'F-PRICE-01',
      url: 'https://store.example.com/products/solar-inverter-5kw',
      routeIntent: 'PRODUCT_DISPLAY_PAGE' as const,
      detectionRule: 'STRUCTURED_DATA_PRICE_MISMATCH',
      track: 'TRACK_B_ECOMMERCE_INTELLIGENCE' as const,
      category: 'Ecommerce' as const,
      severity: 'HIGH' as const,
      evidenceClass: '[O] Observed' as const,
      observedValue: 'Storefront ₹24,999 vs Schema ₹28,999',
      expectedValue: 'Identical price',
      exactEvidence: { priceFound: 24999, priceExpected: 28999 },
      reproductionMethod: 'curl -sL https://store.example.com/products/solar-inverter-5kw',
      businessImpact: 'Pricing discrepancy threatens buy-box and GMC feed rejection.',
      commercialRisk: estimateCommercialRisk('STRUCTURED_DATA_PRICE_MISMATCH', 'https://store.example.com/products/solar-inverter-5kw', { priceDelta: 4000 }).commercialRisk,
      recommendedRemediation: 'Sync price with schema',
      automaticallyFixable: true,
      requiredAccess: 'Storefront API',
      remediationStatus: 'ACTION_REQUIRED' as const,
      beforeEvidence: 'Price mismatch',
      afterEvidence: null,
      verificationResult: null,
      timestamp: new Date().toISOString()
    },
    // 2. Utility Route Finding: noindex on /cart
    {
      findingId: 'F-CART-01',
      url: 'https://store.example.com/cart',
      routeIntent: 'TRANSACTIONAL_UTILITY' as const,
      detectionRule: 'NOINDEX_ON_TRANSACTIONAL_ROUTE',
      track: 'TRACK_A_CORE_SEO' as const,
      category: 'Indexability' as const,
      severity: 'INFO' as const,
      evidenceClass: '[O] Observed' as const,
      observedValue: 'noindex',
      expectedValue: 'noindex',
      exactEvidence: { rawContext: 'Cart page with noindex' },
      reproductionMethod: 'curl -sI https://store.example.com/cart',
      businessImpact: 'Expected security hygiene',
      recommendedRemediation: 'Retain noindex',
      automaticallyFixable: false,
      requiredAccess: 'None',
      remediationStatus: 'INFORMATIONAL' as const,
      beforeEvidence: 'noindex',
      afterEvidence: null,
      verificationResult: 'Validated Standard Practice',
      timestamp: new Date().toISOString()
    },
    // 3. Search Route Finding: noindex on /?s=battery
    {
      findingId: 'F-SEARCH-01',
      url: 'https://store.example.com/?s=battery',
      routeIntent: 'INTERNAL_SEARCH' as const,
      detectionRule: 'NOINDEX_ON_TRANSACTIONAL_ROUTE',
      track: 'TRACK_A_CORE_SEO' as const,
      category: 'Indexability' as const,
      severity: 'INFO' as const,
      evidenceClass: '[O] Observed' as const,
      observedValue: 'noindex',
      expectedValue: 'noindex',
      exactEvidence: { rawContext: 'Internal search query with noindex' },
      reproductionMethod: 'curl -sI https://store.example.com/?s=battery',
      businessImpact: 'Expected hygiene preventing internal search results from flooding index',
      recommendedRemediation: 'Retain noindex',
      automaticallyFixable: false,
      requiredAccess: 'None',
      remediationStatus: 'INFORMATIONAL' as const,
      beforeEvidence: 'noindex',
      afterEvidence: null,
      verificationResult: 'Validated Standard Practice',
      timestamp: new Date().toISOString()
    }
  ];

  const queue = PriorityDecisionEngine.prioritizeFindings(findings);

  // Assert Top Action is the Commercial Finding on PDP
  assert.equal(queue[0].findingId, 'F-PRICE-01');
  assert.equal(queue[0].routeIntent, 'PRODUCT_DISPLAY_PAGE');
  assert.equal(queue[0].confidence, '[REQUIRES_ACCESS]');
  assert.ok(queue[0].financialImpactSummary.includes('[REQUIRES_ACCESS]'));

  // Assert Utility & Search findings are quarantined to P4
  const cartItem = queue.find(q => q.findingId === 'F-CART-01');
  assert.equal(cartItem?.priorityTier, 'P4_INFORMATIONAL');

  const searchItem = queue.find(q => q.findingId === 'F-SEARCH-01');
  assert.equal(searchItem?.priorityTier, 'P4_INFORMATIONAL');
});
