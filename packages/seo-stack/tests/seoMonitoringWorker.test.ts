import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { 
  SeoDatabase, 
  TenantMonitoringPolicyManager, 
  TenantPolicyViolationError,
  AutonomousRemediator,
  SeoMonitoringWorker,
  SeoFinding,
  GscSnapshot
} from '../src/index.js';

test('Milestone 6.1 — SQLite WAL Persistence Layer survives process restarts', () => {
  const tmpDir = path.resolve(process.cwd(), 'data/test_db_' + Date.now());
  const dbPath = path.join(tmpDir, 'test_seo.sqlite');

  try {
    // Process 1: write data
    const db1 = new SeoDatabase(dbPath);
    const hbId = db1.recordHeartbeat({
      tenantId: 'sanocea',
      domain: 'www.sanocea.com',
      timestamp: '2026-09-30T10:00:00.000Z',
      tier: 'tier1',
      status: 'ok',
      changeCount: 0,
      durationMs: 45,
      details: { probe: 'clean' }
    });
    assert.ok(hbId > 0, 'Heartbeat ID should be positive integer');

    const sampleSnapshot: GscSnapshot = {
      snapshotId: 'SNAP-SANOCEA-2026-09-30',
      siteUrl: 'https://www.sanocea.com/',
      dateRange: { startDate: '2026-09-01', endDate: '2026-09-28' },
      capturedAt: '2026-09-30T10:00:00.000Z',
      totalClicks: 1420,
      totalImpressions: 51800,
      averageCtr: 0.0274,
      averagePosition: 13.9,
      queryRows: [
        { query: 'multichannel ecommerce orchestration', clicks: 420, impressions: 8400, ctr: 0.05, position: 3.4 }
      ],
      pageRows: [
        { page: 'https://www.sanocea.com/', clicks: 950, impressions: 38000, ctr: 0.025, position: 12.1 }
      ]
    };
    db1.saveGscSnapshot('sanocea', sampleSnapshot);

    db1.recordDetectedChange({
      tenantId: 'sanocea',
      timestamp: '2026-09-30T10:00:00.000Z',
      tier: 'tier1',
      changeType: 'TITLE_PIXEL_OVERFLOW',
      severity: 'P1',
      url: 'https://www.sanocea.com',
      observedValue: '624px',
      expectedValue: '<= 561px'
    });

    db1.close();

    // Process 2: re-open existing SQLite file (simulating process restart)
    const db2 = new SeoDatabase(dbPath);
    const restoredHb = db2.getLatestHeartbeat('sanocea');
    assert.ok(restoredHb, 'Heartbeat should persist across database reconnect');
    assert.equal(restoredHb?.status, 'ok');
    assert.equal(restoredHb?.durationMs, 45);

    const restoredSnap = db2.getGscSnapshot('SNAP-SANOCEA-2026-09-30');
    assert.ok(restoredSnap, 'GSC snapshot must persist in SQLite WAL across process restart');
    assert.equal(restoredSnap?.totalClicks, 1420);
    assert.equal(restoredSnap?.queryRows[0].query, 'multichannel ecommerce orchestration');

    const changes = db2.getDetectedChanges('sanocea', 10);
    assert.equal(changes.length, 1);
    assert.equal(changes[0].changeType, 'TITLE_PIXEL_OVERFLOW');

    db2.close();
  } finally {
    if (fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  }
});

test('Milestone 6.2 — Tenant Policy Guard: SANOCEA.com strictly whitelisted; all prospects barred from background execution', () => {
  // 1. SANOCEA Whitelist
  assert.equal(TenantMonitoringPolicyManager.isMonitoringAllowed('sanocea'), true);
  assert.equal(TenantMonitoringPolicyManager.isAutoRemediationAllowed('sanocea'), true);
  assert.doesNotThrow(() => TenantMonitoringPolicyManager.assertMonitoringAllowed('sanocea'));
  assert.doesNotThrow(() => TenantMonitoringPolicyManager.assertAutoRemediationAllowed('sanocea'));

  // 2. Prospect Tenants strictly barred
  const prospectTenants = ['waaree', 'carzex', 'premium-basket', 'ajanta-soya', 'golden-bird-jewels'];
  for (const tenant of prospectTenants) {
    assert.equal(TenantMonitoringPolicyManager.isMonitoringAllowed(tenant), false, `${tenant} must not be allowed autonomous monitoring`);
    assert.equal(TenantMonitoringPolicyManager.isAutoRemediationAllowed(tenant), false, `${tenant} must not be allowed auto remediation`);

    assert.throws(
      () => TenantMonitoringPolicyManager.assertMonitoringAllowed(tenant),
      TenantPolicyViolationError,
      `Attempting monitoring for ${tenant} must throw TenantPolicyViolationError`
    );

    assert.throws(
      () => TenantMonitoringPolicyManager.assertAutoRemediationAllowed(tenant),
      TenantPolicyViolationError,
      `Attempting auto-remediation for ${tenant} must throw TenantPolicyViolationError`
    );
  }

  // 3. Worker instantiation guard
  assert.throws(
    () => new SeoMonitoringWorker({ tenantId: 'waaree', domain: 'shop.waaree.com' }),
    TenantPolicyViolationError,
    'Worker instantiation for prospect tenant must throw TenantPolicyViolationError'
  );
});

test('Milestone 6.3 — Closed-Loop Autonomous Remediator: 8-stage verification pipeline on SANOCEA', async () => {
  const db = new SeoDatabase(':memory:');
  const remediator = new AutonomousRemediator(db);

  const titleFinding: SeoFinding = {
    findingId: 'FND-SANOCEA-TITLE-001',
    url: 'https://www.sanocea.com',
    routeIntent: 'MARKETING_LANDING_PAGE',
    detectionRule: 'SERP_TITLE_OVERFLOW',
    track: 'TRACK_A_CORE_SEO',
    category: 'Technical SEO',
    severity: 'HIGH',
    evidenceClass: '[O] Observed',
    observedValue: 'SANOCEA — Autonomous Multichannel Catalogue, Price & Inventory Orchestration Engine (624px)',
    expectedValue: 'SANOCEA | Autonomous Ecommerce Orchestration (<= 561px)',
    exactEvidence: {
      htmlSnippet: '<title>SANOCEA — Autonomous Multichannel Catalogue, Price & Inventory Orchestration Engine</title>',
      pixelWidth: 624
    },
    reproductionMethod: 'curl -s https://www.sanocea.com | grep -i "<title>"',
    businessImpact: 'Title truncation in desktop Google SERP reduces brand salience',
    recommendedRemediation: 'Trim title under 561px',
    automaticallyFixable: true,
    requiredAccess: 'SOURCE_CODE_WRITE',
    remediationStatus: 'PENDING_APPROVAL',
    beforeEvidence: '<title>SANOCEA — Autonomous Multichannel Catalogue, Price & Inventory Orchestration Engine</title>',
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  // Attempt auto-remediation on Waaree must be blocked
  await assert.rejects(
    async () => remediator.remediateFinding('waaree', titleFinding),
    TenantPolicyViolationError
  );

  // Auto-remediation on sanocea succeeds through all 8 stages
  const result = await remediator.remediateFinding('sanocea', titleFinding, async ({ candidate }) => {
    // Simulated build/deployment patch
    return candidate;
  });

  assert.equal(result.status, 'verified');
  assert.ok(result.verificationReceiptId?.startsWith('VRCP-ACT-SANOCEA-AUTO-'));
  assert.ok(result.afterEvidence?.includes('<= 561px SERP limit'));

  // Verify SQLite state
  const actions = db.getRemediationActions('sanocea');
  assert.equal(actions.length, 1);
  assert.equal(actions[0].status, 'verified');

  const ledger = db.getLongitudinalLedger('sanocea');
  assert.equal(ledger.length, 1);
  assert.equal(ledger[0].eventType, 'AUTONOMOUS_REMEDIATION_VERIFIED');

  db.close();
});

test('Milestone 6.4 — SeoMonitoringWorker: 3-Tier Execution & Observability Heartbeat', async () => {
  const dbPath = path.resolve(process.cwd(), 'data/test_worker_' + Date.now() + '.sqlite');
  
  try {
    const worker = new SeoMonitoringWorker({
      tenantId: 'sanocea',
      domain: 'www.sanocea.com',
      dbPath,
      enableTier1: false,
      enableTier2: false,
      enableTier3: false
    });

    // 1. Run Tier 1 Lightweight Probe
    const t1Result = await worker.runTier1();
    assert.ok(t1Result.heartbeatId > 0);
    assert.ok(['ok', 'degraded', 'alert'].includes(t1Result.status));

    // 2. Run Tier 2 Daily Search Intelligence
    const snap1: GscSnapshot = {
      snapshotId: 'SNAP-BASE-001',
      siteUrl: 'https://www.sanocea.com/',
      dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
      capturedAt: '2026-08-29T00:00:00.000Z',
      totalClicks: 1200,
      totalImpressions: 40000,
      averageCtr: 0.03,
      averagePosition: 12.0,
      queryRows: [
        { query: 'ecommerce catalog orchestration', clicks: 300, impressions: 6000, ctr: 0.05, position: 5.0 },
        { query: 'price erosion control', clicks: 100, impressions: 2000, ctr: 0.05, position: 8.0 }
      ],
      pageRows: [
        { page: 'https://www.sanocea.com/', clicks: 1200, impressions: 40000, ctr: 0.03, position: 12.0 }
      ]
    };

    const snap2: GscSnapshot = {
      snapshotId: 'SNAP-CURR-002',
      siteUrl: 'https://www.sanocea.com/',
      dateRange: { startDate: '2026-08-29', endDate: '2026-09-26' },
      capturedAt: '2026-09-27T00:00:00.000Z',
      totalClicks: 1450,
      totalImpressions: 48000,
      averageCtr: 0.0302,
      averagePosition: 10.4,
      queryRows: [
        { query: 'ecommerce catalog orchestration', clicks: 420, impressions: 8400, ctr: 0.05, position: 3.2 },
        { query: 'price erosion control', clicks: 80, impressions: 1600, ctr: 0.05, position: 9.8 }
      ],
      pageRows: [
        { page: 'https://www.sanocea.com/', clicks: 1450, impressions: 48000, ctr: 0.0302, position: 10.4 }
      ]
    };

    // Save baseline snapshot
    await worker.runTier2(snap1);
    // Run comparison snapshot
    const t2Result = await worker.runTier2(snap2);
    assert.equal(t2Result.status, 'ok');
    assert.ok(t2Result.winnersCount >= 1, 'Rank winner should be detected');

    // 3. Inspect Observable Health Status
    const health = worker.getHealth();
    assert.ok(health.uptimeSeconds >= 0);
    assert.equal(health.tenantId, 'sanocea');
    assert.equal(health.tier1.totalRuns, 1);
    assert.equal(health.tier2.totalRuns, 2);

    worker.stop();
  } finally {
    if (fs.existsSync(dbPath)) fs.unlinkSync(dbPath);
    if (fs.existsSync(`${dbPath}-wal`)) fs.unlinkSync(`${dbPath}-wal`);
    if (fs.existsSync(`${dbPath}-shm`)) fs.unlinkSync(`${dbPath}-shm`);
  }
});
