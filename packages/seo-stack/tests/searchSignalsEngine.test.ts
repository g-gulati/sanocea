import test from 'node:test';
import assert from 'node:assert/strict';
import { SearchSignalsEngine, classifyRouteCategory } from '../src/search-intel/searchSignalsEngine.js';
import { GscSnapshot } from '../src/core/types.js';

const mockLiveSnapshot: GscSnapshot = {
  snapshotId: 'GSC-SNAP-test-live-001',
  siteUrl: 'sc-domain:sanocea.com',
  dateRange: { startDate: '2026-09-02', endDate: '2026-09-30' },
  totalClicks: 11,
  totalImpressions: 28,
  averageCtr: 0.392857,
  averagePosition: 2.42857,
  queryRows: [], // Query strings withheld by Google Search Console under privacy filtering
  pageRows: [
    {
      page: 'https://www.sanocea.com/',
      clicks: 11,
      impressions: 28,
      ctr: 0.392857,
      position: 2.42857
    }
  ],
  deviceRows: [
    { device: 'DESKTOP', clicks: 10, impressions: 26, ctr: 0.3846, position: 2.5 },
    { device: 'MOBILE', clicks: 1, impressions: 2, ctr: 0.5, position: 1.5 }
  ],
  capturedAt: '2026-09-30T08:00:00.000Z'
};

const mockCrawledUrls = [
  'https://www.sanocea.com/',
  'https://www.sanocea.com/solutions/marketplace-reconciliation',
  'https://www.sanocea.com/robots.txt',
  'https://www.sanocea.com/sitemap.xml',
  'https://www.sanocea.com/llms.txt'
];

test('SearchSignalsEngine — Provenance Model & Three-Layer Truth Integrity', () => {
  const report = SearchSignalsEngine.deriveSignals(mockLiveSnapshot, mockCrawledUrls);

  assert.equal(report.signalsCount, 5, 'Must derive exactly 5 actionable signals');
  assert.equal(report.observationWindow, '2026-09-02 to 2026-09-30 (28 days)');
  assert.equal(report.sampleSize.impressions, 28);
  assert.equal(report.sampleSize.clicks, 11);
  assert.equal(report.sampleSize.isSmallSample, true);

  for (const sig of report.signals) {
    // Every signal must have complete provenance fields
    assert.ok(sig.id, 'Signal must have an id');
    assert.ok(sig.title, 'Signal must have a title');
    assert.ok(sig.observationWindow, 'Signal must specify observationWindow');
    assert.ok(sig.sampleSize, 'Signal must specify sampleSize');
    assert.ok(sig.confidence, 'Signal must have an explicit confidence level');
    assert.ok(sig.confidenceRationale, 'Signal must explain confidence rationale');
    assert.ok(sig.observedEvidence, 'Signal must define directly observedEvidence');
    assert.ok(sig.calculatedMetrics, 'Signal must define calculatedMetrics');
    assert.ok(sig.inference, 'Signal must define explicitly labeled inference');
    assert.ok(sig.actionableRemediation, 'Signal must define actionableRemediation');
    assert.ok(['[OBSERVED]', '[CALCULATED]', '[INFERRED]'].includes(sig.provenance), 'Provenance tag must be valid');
  }
});

test('SearchSignalsEngine — Route Classification: Technical vs Commercial Routes', () => {
  // 1. Direct classifier tests
  assert.equal(classifyRouteCategory('https://www.sanocea.com/robots.txt'), 'TECHNICAL_RESOURCE');
  assert.equal(classifyRouteCategory('https://www.sanocea.com/sitemap.xml'), 'TECHNICAL_RESOURCE');
  assert.equal(classifyRouteCategory('https://www.sanocea.com/llms.txt'), 'TECHNICAL_RESOURCE');
  assert.equal(classifyRouteCategory('https://www.sanocea.com/favicon.ico'), 'TECHNICAL_RESOURCE');
  assert.equal(classifyRouteCategory('https://www.sanocea.com/'), 'INDEXABLE_COMMERCIAL_ROUTE');
  assert.equal(classifyRouteCategory('https://www.sanocea.com/solutions/marketplace-reconciliation'), 'INDEXABLE_COMMERCIAL_ROUTE');

  // 2. Footprint signal exclusion of technical resources
  const report = SearchSignalsEngine.deriveSignals(mockLiveSnapshot, mockCrawledUrls);
  const footprintSig = report.signals.find(s => s.type === 'SERP_FOOTPRINT');
  assert.ok(footprintSig, 'Must generate SERP_FOOTPRINT signal');

  // Must not treat robots.txt or sitemap.xml as missing commercial routes
  assert.equal(footprintSig.calculatedMetrics.totalIndexableCommercialRoutes, 2);
  assert.equal(footprintSig.calculatedMetrics.surfacedCommercialRoutesCount, 1);
  assert.equal(footprintSig.calculatedMetrics.unsurfacedCommercialRoutesCount, 1);
  assert.equal(footprintSig.calculatedMetrics.technicalResourcesExcluded, 3);
  assert.ok(footprintSig.summary.includes('Technical resources (/robots.txt, /sitemap.xml, /llms.txt) are excluded'));
});

test('SearchSignalsEngine — Small Sample Size Handling & Demographic Intent Caveat', () => {
  const report = SearchSignalsEngine.deriveSignals(mockLiveSnapshot, mockCrawledUrls);
  const deviceSig = report.signals.find(s => s.type === 'DEVICE_INTENT');
  assert.ok(deviceSig, 'Must generate DEVICE_INTENT signal');

  // Small sample must downgrade confidence to LOW
  assert.equal(deviceSig.confidence, 'LOW', 'n=28 impressions must downgrade confidence to LOW');
  assert.ok(deviceSig.confidenceRationale.includes('statistically preliminary'));
  assert.ok(deviceSig.calculatedMetrics.desktopShare > 0.90);

  // Must NOT claim definitive proof of enterprise B2B procurement behavior
  assert.ok(
    !deviceSig.summary.includes('confirming high-intent enterprise commercial search behavior'),
    'Must not state that 28 impressions proves enterprise B2B behavior'
  );
  assert.ok(deviceSig.inference.includes('cannot be presented as proof of enterprise B2B procurement behavior'));
  assert.equal(deviceSig.provenance, '[CALCULATED]');
});

test('SearchSignalsEngine — Unavailable Query Dimensions & Benchmark Provenance', () => {
  const report = SearchSignalsEngine.deriveSignals(mockLiveSnapshot, mockCrawledUrls);

  // 1. Privacy Threshold signal
  const privacySig = report.signals.find(s => s.type === 'PRIVACY_THRESHOLD');
  assert.ok(privacySig, 'Must generate PRIVACY_THRESHOLD signal');
  assert.equal(privacySig.provenance, '[OBSERVED]');
  // Must NOT assert arbitrary <10 cutoff as established fact
  assert.ok(
    !privacySig.summary.includes('<10'),
    'Privacy explanation must not assert unverified numeric threshold'
  );
  assert.ok(privacySig.inference.includes('does not publish a verified numeric impression cutoff'));

  // 2. CTR Benchmark signal
  const ctrSig = report.signals.find(s => s.type === 'CTR_BENCHMARK');
  assert.ok(ctrSig, 'Must generate CTR_BENCHMARK signal');
  assert.equal(ctrSig.provenance, '[CALCULATED]');
  assert.equal(ctrSig.confidence, 'MEDIUM');

  // Must include documented external benchmark with complete audit provenance
  assert.ok(ctrSig.externalBenchmark, 'Must include external benchmark');
  assert.equal(ctrSig.externalBenchmark.source, 'Advanced Web Ranking (AWR) CTR Model (Desktop Organic)');
  assert.equal(ctrSig.externalBenchmark.expectedValue, '15.0%');
  assert.ok(ctrSig.externalBenchmark.population, 'Benchmark must define population');
  assert.equal(ctrSig.externalBenchmark.device, 'Desktop');
  assert.ok(ctrSig.externalBenchmark.geography, 'Benchmark must define geography');
  assert.ok(ctrSig.externalBenchmark.dateVersion, 'Benchmark must define dateVersion');
  assert.ok(ctrSig.externalBenchmark.methodology, 'Benchmark must define methodology');

  // Must NOT claim confirmed brand dominance while query rows are withheld
  assert.ok(
    !ctrSig.summary.includes('confirming strong direct brand equity'),
    'Must not assert confirmation of brand intent when query rows are withheld'
  );
  assert.ok(
    !ctrSig.inference.includes('typically indicates navigational search intent'),
    'Must not characterize CTR differential as evidence of navigational search intent while query rows are unavailable'
  );
  assert.ok(
    ctrSig.summary.includes('materially above the configured Advanced Web Ranking (AWR) desktop organic benchmark'),
    'Summary must state observed CTR is materially above configured benchmark'
  );
  assert.ok(
    ctrSig.summary.toLowerCase().includes('query intent cannot currently be attributed'),
    'Summary must state query intent cannot currently be attributed'
  );
  assert.ok(
    ctrSig.inference.toLowerCase().includes('query intent cannot currently be attributed'),
    'Inference must state query intent cannot currently be attributed'
  );
  assert.ok(
    ctrSig.actionableRemediation.includes('conservative operational measure') ||
    ctrSig.actionableRemediation.includes('conservative safeguard'),
    'Remediation must characterize brand-token preservation as a conservative operational measure/safeguard'
  );
  assert.ok(
    ctrSig.actionableRemediation.includes('not as proof of brand traffic'),
    'Remediation must clarify action is not proof of brand traffic'
  );
});

test('SearchSignalsEngine — Early Incubation as SANOCEA Operational Inference', () => {
  const report = SearchSignalsEngine.deriveSignals(mockLiveSnapshot, mockCrawledUrls);
  const velocitySig = report.signals.find(s => s.type === 'SEARCH_VELOCITY');
  assert.ok(velocitySig, 'Must generate SEARCH_VELOCITY signal');

  // Provenance must be explicitly [INFERRED]
  assert.equal(velocitySig.provenance, '[INFERRED]');
  assert.equal(velocitySig.confidence, 'MEDIUM');
  assert.ok(velocitySig.summary.includes('operational inference, not a status supplied by Google'));
  assert.ok(velocitySig.inference.includes('SANOCEA infers that this property is in an early indexation phase'));
});
