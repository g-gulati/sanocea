/**
 * SANOCEA SEO Stack — Priority & Decision Engine Test Suite
 * 
 * Verifies that:
 * 1. Multi-factor scoring successfully prevents technical severity from outranking commercial consequence.
 * 2. Active revenue channels (Google Shopping) outrank secondary crawl hygiene.
 * 3. Route intent weights suppress utility routes.
 * 4. Provenance tiers ([OBSERVED], [CALCULATED], [REQUIRES_ACCESS]) are strictly preserved without arbitrary numbers.
 * 5. Action queue outputs exact executive decision contracts.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoFinding } from '../src/core/types.js';
import { calculatePriorityScore, PriorityDecisionEngine, mapScoreToTier } from '../src/core/priorityEngine.js';

test('1. Commercial Exception Outranks Technically Severe Non-Commercial Flaw', () => {
  // Finding A: "CRITICAL" technical finding on an un-monetized tool page
  const technicalFinding: SeoFinding = {
    findingId: 'F-TECH-H1',
    url: 'https://example.com/demo.html',
    routeIntent: 'MARKETING_LANDING_PAGE',
    detectionRule: 'H1_HEADING_MISSING_IN_SSR',
    track: 'TRACK_A_CORE_SEO',
    category: 'Content & Headings',
    severity: 'CRITICAL', // High technical severity!
    evidenceClass: '[O] Observed',
    observedValue: '0 <h1> tags',
    expectedValue: '1 <h1>',
    exactEvidence: {},
    reproductionMethod: 'curl test',
    businessImpact: 'Delayed JS indexing',
    commercialRisk: {
      riskType: 'INDEXATION_PURGE',
      title: 'SPA Pre-Hydration Deficit',
      estimatedMonthlyLossInr: 150000,
      currency: 'INR',
      confidence: '[ESTIMATED]',
      source: 'industry_benchmark_estimate',
      affectedChannels: ['Google Search Organic'],
      severityScore: 5,
      calculationFormula: 'Benchmark projection'
    },
    recommendedRemediation: 'Add SSR H1',
    automaticallyFixable: true,
    requiredAccess: 'Code template',
    remediationStatus: 'ACTION_REQUIRED',
    beforeEvidence: null,
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  // Finding B: "HIGH" severity commercial price mismatch on a live product in Google Shopping
  const commercialFinding: SeoFinding = {
    findingId: 'F-ECOM-PRICE',
    url: 'https://example.com/products/solar-inverter-5kw',
    routeIntent: 'PRODUCT_DISPLAY_PAGE',
    detectionRule: 'STRUCTURED_DATA_PRICE_MISMATCH',
    track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
    category: 'Ecommerce',
    severity: 'HIGH', // Technically labeled 'HIGH', not 'CRITICAL'
    evidenceClass: '[O] Observed',
    observedValue: 'DOM: ₹17,499 vs Schema: ₹14,999',
    expectedValue: 'DOM price matches Schema price',
    exactEvidence: { priceFound: 14999, priceExpected: 17499 },
    reproductionMethod: 'curl test',
    businessImpact: 'Google Merchant Center price mismatch disapproval and ad feed pause',
    commercialRisk: {
      riskType: 'BUY_BOX_REVENUE_EROSION',
      title: 'Storefront vs Schema Price Discrepancy',
      estimatedMonthlyLossInr: 300000,
      currency: 'INR',
      confidence: '[CALCULATED]',
      source: 'schema_json_ld',
      affectedChannels: ['Google Shopping', 'Performance Max Ads', 'Direct Storefront'],
      severityScore: 4,
      calculationFormula: 'Observed Delta ₹2,500 × 120 units'
    },
    automationOpportunity: {
      automatable: true,
      recipeType: 'FEED_MAP',
      primaryMechanism: 'SUPPLEMENTAL_FEED',
      fallbackMechanisms: ['STOREFRONT_API'],
      requiredAccessTier: 'FEED_ONLY',
      requiredRole: 'MERCHANDISING',
      description: 'Upload GMC supplemental price feed'
    },
    recommendedRemediation: 'Sync offer.price with promotional price',
    automaticallyFixable: true,
    requiredAccess: 'Feed access',
    remediationStatus: 'ACTION_REQUIRED',
    beforeEvidence: null,
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const scoreTech = calculatePriorityScore(technicalFinding);
  const scoreEcom = calculatePriorityScore(commercialFinding);

  // Commercial price mismatch on PDP MUST outrank missing H1, despite H1 being technically 'CRITICAL'
  assert.ok(
    scoreEcom.score > scoreTech.score,
    `Commercial finding score (${scoreEcom.score}) must exceed technical finding score (${scoreTech.score})`
  );

  const prioritized = PriorityDecisionEngine.prioritizeFindings([technicalFinding, commercialFinding], 2);
  assert.equal(prioritized[0].findingId, 'F-ECOM-PRICE', 'Commercial finding must be Rank #1 in Executive Queue');
  assert.equal(prioritized[1].findingId, 'F-TECH-H1', 'Technical finding must be Rank #2');
});

test('2. Route Intent Suppression: Utility Route False Priority Quarantined', () => {
  // A missing H1 or noindex on /my-account must be assigned P3 or P4, never P0 or P1
  const utilityFinding: SeoFinding = {
    findingId: 'F-UTIL-NOINDEX',
    url: 'https://example.com/my-account',
    routeIntent: 'TRANSACTIONAL_UTILITY',
    detectionRule: 'NOINDEX_ON_TRANSACTIONAL_ROUTE',
    track: 'TRACK_A_CORE_SEO',
    category: 'Indexability',
    severity: 'INFO',
    evidenceClass: '[O] Observed',
    observedValue: 'noindex, follow',
    expectedValue: 'noindex',
    exactEvidence: {},
    reproductionMethod: 'curl test',
    businessImpact: 'Expected security hygiene',
    recommendedRemediation: 'Retain noindex',
    automaticallyFixable: false,
    requiredAccess: 'None',
    remediationStatus: 'INFORMATIONAL',
    beforeEvidence: null,
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const { score } = calculatePriorityScore(utilityFinding);
  const tier = mapScoreToTier(score);

  assert.ok(score < 2.0, `Utility route score (${score}) must be very low`);
  assert.ok(tier === 'P3_LOW_BACKLOG' || tier === 'P4_INFORMATIONAL');
});

test('3. Provenance Integrity: Telemetry-Dependent Loss Marked [REQUIRES_ACCESS]', () => {
  const oosFinding: SeoFinding = {
    findingId: 'F-WAAREE-OOS',
    url: 'https://shop.waaree.com/products/hybrid-inverter',
    routeIntent: 'PRODUCT_DISPLAY_PAGE',
    detectionRule: 'STRUCTURED_DATA_INSTOCK_WHEN_OOS',
    track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
    category: 'Ecommerce',
    severity: 'CRITICAL',
    evidenceClass: '[O] Observed',
    observedValue: 'Schema InStock vs Storefront Sold Out',
    expectedValue: 'Schema OutOfStock',
    exactEvidence: { stockFound: 'InStock', stockExpected: 'OutOfStock' },
    reproductionMethod: 'curl test',
    businessImpact: 'GMC account suspension risk for deceptive availability',
    commercialRisk: {
      riskType: 'GMC_ACCOUNT_SUSPENSION',
      title: 'Google Merchant Center Suspension Exposure',
      estimatedMonthlyLossInr: 450000,
      currency: 'INR',
      confidence: '[REQUIRES_ACCESS]',
      source: 'requires_merchant_telemetry',
      affectedChannels: ['Google Shopping', 'Performance Max Ads'],
      severityScore: 5,
      calculationFormula: 'Modeled Shopping Exposure = ₹450,000'
    },
    automationOpportunity: {
      automatable: true,
      recipeType: 'SCHEMA_INJECTION',
      primaryMechanism: 'STOREFRONT_API',
      fallbackMechanisms: ['SUPPLEMENTAL_FEED', 'WHATSAPP_APPROVAL'],
      requiredAccessTier: 'FEED_ONLY',
      requiredRole: 'ENGINEERING',
      description: 'Upload GMC supplemental feed'
    },
    recommendedRemediation: 'Output OutOfStock',
    automaticallyFixable: true,
    requiredAccess: 'Feed access',
    remediationStatus: 'ACTION_REQUIRED',
    beforeEvidence: null,
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const queue = PriorityDecisionEngine.prioritizeFindings([oosFinding], 1);
  const decision = queue[0];

  assert.equal(decision.priorityTier, 'P0_IMMEDIATE_ACTION');
  assert.equal(decision.confidence, '[REQUIRES_ACCESS]');
  assert.ok(decision.financialImpactSummary.includes('[REQUIRES_ACCESS: Exact loss subject to merchant ad spend / GMV telemetry]'));
  assert.equal(decision.automationOpportunity.humanApprovalRequired, true, 'Ecommerce catalog updates require human confirmation');
  assert.equal(decision.automationOpportunity.requiredAccessTier, 'FEED_ONLY');
});
