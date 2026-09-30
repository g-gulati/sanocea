/**
 * SANOCEA SEO Stack — Milestone 5.3 Search Appearance, CrUX Field & Longitudinal Ledger Test Suite
 * 
 * Verifies:
 * 1. 3-State Search Appearance progression: [DECLARED_ONLY] → [ELIGIBLE_UNSURFACED] → [SURFACED_IN_SERP]
 * 2. CrUX Field Performance (Mobile vs Desktop, p75 LCP/INP/CLS, Field vs Lab separation)
 * 3. Search + Performance Correlation with strict anti-causality discipline
 * 4. SANOCEA.com Flagship Longitudinal Experiment Ledger (BEFORE → INTERVENTION → AFTER)
 * 5. Full pipeline integration with GSC, CrUX, and Longitudinal Ledger
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 
  reconcileSearchAppearance 
} from '../src/search-intel/searchAppearanceReconciler.js';
import { 
  CruxClient 
} from '../src/search-intel/cruxClient.js';
import { 
  correlateSearchAndFieldPerformance 
} from '../src/search-intel/correlationEngine.js';
import { 
  LongitudinalExperimentManager,
  GOOGLE_ALGORITHM_UPDATES_2026
} from '../src/search-intel/longitudinalLedger.js';
import { SeoAuditPipeline } from '../src/pipeline/auditPipeline.js';
import { 
  GscSnapshot, 
  GscUrlInspectionRecord, 
  CrawledPage,
  GscComparisonReport
} from '../src/core/types.js';

test('Milestone 5.3.1 — Search Appearance Intelligence: 3-State Progression (Declared -> Eligible -> Surfaced)', () => {
  const crawledPages = new Map<string, CrawledPage>();
  const targetUrl = 'https://sanocea.com/products/hybrid-inverter';

  crawledPages.set(targetUrl, {
    url: targetUrl,
    status: 200,
    headers: {},
    rawHtml: `
      <html>
        <head>
          <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "Product",
              "name": "Hybrid Inverter 5kW",
              "offers": {
                "@type": "Offer",
                "price": "42000",
                "priceCurrency": "INR",
                "availability": "https://schema.org/InStock"
              }
            }
          </script>
        </head>
        <body><h1>Hybrid Inverter</h1></body>
      </html>
    `,
    isJsRendered: false,
    executionTimeMs: 12,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  });

  // State 1: DECLARED_ONLY (Inspection fails eligibility or has fatal errors)
  const failedInspection = new Map<string, GscUrlInspectionRecord>();
  failedInspection.set(targetUrl, {
    url: targetUrl,
    verdict: 'FAIL',
    coverageState: 'INDEXED',
    indexingStatus: 'INDEXED',
    richResultsItems: [
      {
        name: 'Merchant listings',
        verdict: 'FAIL',
        issues: [{ message: 'Missing field "shippingDetails"', severity: 'ERROR' }]
      }
    ]
  });

  const auditDeclaredOnly = reconcileSearchAppearance({
    crawledPages,
    inspectionRecords: failedInspection
  });

  assert.equal(auditDeclaredOnly.statuses.length, 1);
  assert.equal(auditDeclaredOnly.statuses[0].state, 'DECLARED_ONLY');
  assert.ok(auditDeclaredOnly.statuses[0].explanation.includes('failed eligibility'));

  // State 2: ELIGIBLE_UNSURFACED (Inspection PASS with 0 errors, but GSC search appearance reports 0 impressions)
  const passedInspection = new Map<string, GscUrlInspectionRecord>();
  passedInspection.set(targetUrl, {
    url: targetUrl,
    verdict: 'PASS',
    coverageState: 'INDEXED',
    indexingStatus: 'INDEXED',
    richResultsItems: [
      {
        name: 'Merchant listings',
        verdict: 'PASS',
        issues: []
      }
    ]
  });

  const unsurfacedSnapshot: GscSnapshot = {
    snapshotId: 'snap-unsurfaced',
    siteUrl: 'https://sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    totalClicks: 100,
    totalImpressions: 2500,
    averageCtr: 0.04,
    averagePosition: 6.5,
    queryRows: [],
    pageRows: [],
    searchAppearanceRows: [
      // Zero merchant listings impressions
      { searchAppearance: 'TRANSLATED_RESULT', clicks: 2, impressions: 30, ctr: 0.067, position: 5.0 }
    ],
    capturedAt: new Date().toISOString()
  };

  const auditEligibleUnsurfaced = reconcileSearchAppearance({
    crawledPages,
    gscSnapshot: unsurfacedSnapshot,
    inspectionRecords: passedInspection
  });

  assert.equal(auditEligibleUnsurfaced.statuses.length, 1);
  assert.equal(auditEligibleUnsurfaced.statuses[0].state, 'ELIGIBLE_UNSURFACED');
  assert.ok(auditEligibleUnsurfaced.statuses[0].explanation.includes('Eligible for rich snippets in Google inspection'));

  // State 3: SURFACED_IN_SERP (Actively generating impressions in GSC search appearance)
  const surfacedSnapshot: GscSnapshot = {
    ...unsurfacedSnapshot,
    searchAppearanceRows: [
      { searchAppearance: 'MERCHANT_LISTINGS', clicks: 42, impressions: 850, ctr: 0.049, position: 3.8 },
      { searchAppearance: 'PRODUCT_SNIPPETS', clicks: 18, impressions: 420, ctr: 0.043, position: 4.2 }
    ]
  };

  const auditSurfaced = reconcileSearchAppearance({
    crawledPages,
    gscSnapshot: surfacedSnapshot,
    inspectionRecords: passedInspection
  });

  assert.equal(auditSurfaced.statuses.length, 1);
  assert.equal(auditSurfaced.statuses[0].state, 'SURFACED_IN_SERP');
  assert.equal(auditSurfaced.gscSearchAppearanceActive, true);
  assert.equal(auditSurfaced.merchantListingsImpressions, 850);
});

test('Milestone 5.3.2 — CrUX Field Performance: Mobile vs Desktop & Laboratory Separation', async () => {
  // Test A: Uncredentialed client returns null (strictly [REQUIRES_ACCESS] / unavailable)
  const uncredentialedClient = new CruxClient();
  const nullReport = await uncredentialedClient.fetchFieldReport('https://sanocea.com');
  assert.equal(nullReport, null, 'Uncredentialed CrUX fetch must return null without estimating');

  // Test B: Mock CrUX field report with Mobile and Desktop separation
  const mockReport = CruxClient.createMockReport({
    url: 'https://sanocea.com',
    mobileLcp: 4200,
    mobileInp: 280,
    mobileCls: 0.18,
    desktopLcp: 1800,
    desktopInp: 120,
    desktopCls: 0.03
  });

  assert.ok(mockReport.mobile);
  assert.ok(mockReport.desktop);

  // Verify Mobile ratings
  assert.equal(mockReport.mobile.lcp.p75, 4200);
  assert.equal(mockReport.mobile.lcp.rating, 'POOR');
  assert.equal(mockReport.mobile.inp.rating, 'NEEDS_IMPROVEMENT');
  assert.equal(mockReport.mobile.cls.rating, 'NEEDS_IMPROVEMENT');

  // Verify Desktop ratings (Fast on desktop, slow on mobile)
  assert.equal(mockReport.desktop.lcp.p75, 1800);
  assert.equal(mockReport.desktop.lcp.rating, 'GOOD');
  assert.equal(mockReport.desktop.inp.rating, 'GOOD');
  assert.equal(mockReport.desktop.cls.rating, 'GOOD');

  // Telemetry provenance tag
  assert.equal(mockReport.telemetrySource, 'mock_fixture');
});

test('Milestone 5.3.3 — Search + Field Performance Correlation & Anti-Causality Governance', () => {
  const cruxReport = CruxClient.createMockReport({
    url: 'https://sanocea.com/products/hybrid-inverter',
    mobileLcp: 4600, // POOR
    mobileInp: 550,  // POOR
    mobileCls: 0.12,
    desktopLcp: 2100,
    desktopInp: 150,
    desktopCls: 0.02
  });

  const comparisonReport: GscComparisonReport = {
    siteUrl: 'https://sanocea.com',
    baselineRange: { startDate: '2026-07-01', endDate: '2026-07-28' },
    comparisonRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    totalClickDelta: -45,
    totalImpressionDelta: -1200,
    averageCtrDelta: -0.005,
    averagePositionDelta: 2.8,
    queryDeltas: [],
    pageDeltas: [],
    winners: [],
    losers: [
      {
        key: 'hybrid solar inverter 5kw price',
        baselineClicks: 120,
        comparisonClicks: 65,
        clickDelta: -55,
        baselineImpressions: 2200,
        comparisonImpressions: 1400,
        impressionDelta: -800,
        baselineCtr: 0.0545,
        comparisonCtr: 0.0464,
        ctrDelta: -0.0081,
        baselinePosition: 4.2,
        comparisonPosition: 7.8,
        positionDelta: 3.6 // Dropped 3.6 positions
      }
    ],
    newQueries: [],
    lostQueries: [],
    strikeZoneQueries: []
  };

  const { correlations, findings } = correlateSearchAndFieldPerformance(comparisonReport, cruxReport);

  assert.equal(correlations.length, 1);
  assert.equal(correlations[0].query, 'hybrid solar inverter 5kw price');
  assert.equal(correlations[0].rankingMovement, 3.6);
  assert.ok(correlations[0].causalityStatement.includes('NOT proven causation'));
  assert.ok(correlations[0].causalityStatement.includes('IMPORTANT CAUSALITY DISCLAIMER'));

  assert.equal(findings.length, 1);
  assert.equal(findings[0].detectionRule, 'CORRELATION_POOR_FIELD_PERFORMANCE_AND_RANK_DROP');
  assert.equal(findings[0].commercialRisk?.confidence, '[REQUIRES_ACCESS]');
});

test('Milestone 5.3.4 — SANOCEA.com Flagship Longitudinal Case Study Ledger', () => {
  // Scenario A: Post-deployment observation window has NOT elapsed yet
  const pendingLedger = LongitudinalExperimentManager.createSanoceaFlagshipLedger();

  assert.equal(pendingLedger.siteUrl, 'https://www.sanocea.com');
  assert.ok(pendingLedger.before);
  assert.equal(pendingLedger.before.technicalFindingsSummary.totalCount, 14);
  assert.ok(pendingLedger.intervention);
  assert.equal(pendingLedger.intervention.remediationReceipt.actionId, 'ACT-SANOCEA-SEO-001');

  // Verify NO manufactured improvement when post-deployment data is absent
  assert.equal(pendingLedger.after, undefined, 'Must not manufacture post-deployment after data when observation window is open');
  assert.equal(pendingLedger.causalityAssessment.isCausalityAsserted, false);
  assert.equal(pendingLedger.causalityAssessment.confidence, '[REQUIRES_ACCESS]');
  assert.ok(pendingLedger.algorithmUpdatesInWindow.length >= 3);

  // Scenario B: Post-deployment window completed with real GSC snapshot
  const postDeploymentGsc: GscSnapshot = {
    snapshotId: 'snap-sanocea-after',
    siteUrl: 'https://www.sanocea.com',
    dateRange: { startDate: '2026-09-01', endDate: '2026-09-28' },
    totalClicks: 1580,
    totalImpressions: 52400,
    averageCtr: 0.0301,
    averagePosition: 11.4,
    queryRows: [],
    pageRows: [],
    capturedAt: new Date().toISOString()
  };

  const completedLedger = LongitudinalExperimentManager.createSanoceaFlagshipLedger({
    afterGscSnapshot: postDeploymentGsc
  });

  assert.ok(completedLedger.after);
  assert.equal(completedLedger.after.technicalState.verifiedClean, true);
  assert.equal(completedLedger.after.deltas.clickDelta, 340); // 1580 - 1240 = +340 clicks
  assert.equal(completedLedger.after.deltas.impressionDelta, 7200); // 52400 - 45200 = +7200 imps
  assert.equal(completedLedger.causalityAssessment.isCausalityAsserted, false, 'Never claim absolute single-variable causality');
  assert.equal(completedLedger.causalityAssessment.confidence, '[CALCULATED]');
});

test('Milestone 5.3.5 — Full Pipeline Integration with CrUX & Longitudinal Ledger', async () => {
  const seedHtml = `
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <title>SANOCEA Test Storefront</title>
        <meta name="description" content="Official test store for high efficiency solar products and vehicle accessories.">
        <link rel="canonical" href="https://www.sanocea.com/products/inverter">
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "SANOCEA Solar Inverter 5kW",
            "offers": {
              "@type": "Offer",
              "price": "38000",
              "priceCurrency": "INR",
              "availability": "https://schema.org/InStock"
            }
          }
        </script>
      </head>
      <body>
        <main>
          <h1>SANOCEA Solar Inverter</h1>
        </main>
      </body>
    </html>
  `;

  const cruxReport = CruxClient.createMockReport({
    url: 'https://www.sanocea.com',
    mobileLcp: 3600,
    mobileInp: 220,
    mobileCls: 0.08,
    desktopLcp: 1700,
    desktopInp: 110,
    desktopCls: 0.02
  });

  const gscSnapshot: GscSnapshot = {
    snapshotId: 'snap-pipe-53',
    siteUrl: 'https://www.sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    totalClicks: 350,
    totalImpressions: 8200,
    averageCtr: 0.0427,
    averagePosition: 8.4,
    queryRows: [],
    pageRows: [],
    searchAppearanceRows: [
      { searchAppearance: 'MERCHANT_LISTINGS', clicks: 80, impressions: 1400, ctr: 0.057, position: 4.2 }
    ],
    capturedAt: new Date().toISOString()
  };

  const pipeline = new SeoAuditPipeline({
    seedUrl: 'https://www.sanocea.com',
    maxPages: 1,
    maxDepth: 0,
    allowSubdomains: false,
    enableJsRendering: false,
    customRobotsTxt: 'User-agent: *\nAllow: /',
    gscSnapshot,
    cruxReport
  });

  (pipeline as any).crawler.crawlAll = async () => {
    const map = new Map();
    map.set('https://www.sanocea.com', {
      url: 'https://www.sanocea.com',
      status: 200,
      headers: {},
      rawHtml: seedHtml,
      isJsRendered: false,
      executionTimeMs: 15,
      discoveredUrls: [],
      crawledAt: new Date().toISOString()
    });
    return map;
  };

  const report = await pipeline.runAudit();

  // 1. Verify CrUX field report is attached to AuditReport
  assert.ok(report.cruxReport);
  assert.equal(report.cruxReport.mobile?.lcp.p75, 3600);

  // 2. Verify Search Intelligence carries Search Appearance statuses and CrUX metrics
  assert.ok(report.searchIntelligence);
  assert.ok(report.searchIntelligence.searchAppearanceStatuses);
  assert.equal(report.searchIntelligence.searchAppearanceStatuses.length, 1);
  assert.equal(report.searchIntelligence.searchAppearanceStatuses[0].state, 'SURFACED_IN_SERP');
  assert.equal(report.searchIntelligence.cruxFieldMetrics?.mobile?.lcp.p75, 3600);

  // 3. Verify SANOCEA.com Longitudinal Ledger is attached automatically for sanocea.com domain
  assert.ok(report.longitudinalLedger);
  assert.equal(report.longitudinalLedger.siteUrl, 'https://www.sanocea.com');
  assert.equal(report.longitudinalLedger.intervention.remediationReceipt.actionId, 'ACT-SANOCEA-SEO-001');
});
