import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { SerpTrajectoryEngine } from '../src/search-intel/serpTrajectoryEngine.js';
import { SerpObservation } from '../src/search-intel/serpTypes.js';

const TEST_DB_PATH = path.join(process.cwd(), 'tests', 'fixtures', 'test_serp_monitoring.sqlite');

test('SERP Trajectory Engine — Truth Rules: First Observation (Zero Fabricated History)', () => {
  const obs1: SerpObservation = {
    observationId: 'SERP-OBS-001',
    tenantId: 'sanocea',
    query: 'ecommerce operations automation',
    observedUrl: 'https://www.sanocea.com/',
    targetDomain: 'sanocea.com',
    rank: 42,
    serpType: 'ORGANIC',
    device: 'DESKTOP',
    geography: 'IN',
    language: 'en',
    provider: 'DATA_FOR_SEO',
    timestamp: '2026-09-30T08:00:00Z'
  };

  const traj = SerpTrajectoryEngine.computeTrajectory([obs1]);
  assert.ok(traj, 'Must compute trajectory for single observation');

  // Truth Rule 1: Never fabricate "Yesterday" or "Start Rank"
  assert.equal(traj.observationCount, 1);
  assert.equal(traj.currentRank, 42);
  assert.equal(traj.currentRankFormatted, '#42');
  assert.equal(traj.startRankFormatted, '#42 — first observation', 'Start rank must explicitly state first observation');
  assert.equal(traj.previousRankFormatted, 'N/A — no observation', 'Previous rank must be N/A when no prior observation exists');
  assert.equal(traj.dailyDeltaFormatted, 'N/A — first observation', 'Daily delta must be N/A on initial observation');
  assert.equal(traj.cumulativeDeltaFormatted, 'Baseline Established');
  assert.equal(traj.provenance, '[OBSERVED: DATA_FOR_SEO]');
});

test('SERP Trajectory Engine — Trajectory Progression & Position Delta Math', () => {
  const obs1: SerpObservation = {
    observationId: 'SERP-OBS-001',
    tenantId: 'sanocea',
    query: 'ecommerce operations automation',
    observedUrl: 'https://www.sanocea.com/',
    targetDomain: 'sanocea.com',
    rank: 48,
    serpType: 'ORGANIC',
    device: 'DESKTOP',
    geography: 'IN',
    language: 'en',
    provider: 'DATA_FOR_SEO',
    timestamp: '2026-09-28T08:00:00Z'
  };

  const obs2: SerpObservation = {
    observationId: 'SERP-OBS-002',
    tenantId: 'sanocea',
    query: 'ecommerce operations automation',
    observedUrl: 'https://www.sanocea.com/',
    targetDomain: 'sanocea.com',
    rank: 42, // Gained 6 positions
    serpType: 'ORGANIC',
    device: 'DESKTOP',
    geography: 'IN',
    language: 'en',
    provider: 'DATA_FOR_SEO',
    timestamp: '2026-09-29T08:00:00Z'
  };

  const obs3: SerpObservation = {
    observationId: 'SERP-OBS-003',
    tenantId: 'sanocea',
    query: 'ecommerce operations automation',
    observedUrl: 'https://www.sanocea.com/',
    targetDomain: 'sanocea.com',
    rank: 37, // Gained 5 positions today, net +11 from baseline
    serpType: 'ORGANIC',
    device: 'DESKTOP',
    geography: 'IN',
    language: 'en',
    provider: 'DATA_FOR_SEO',
    timestamp: '2026-09-30T08:00:00Z'
  };

  const traj = SerpTrajectoryEngine.computeTrajectory([obs1, obs2, obs3]);
  assert.ok(traj);

  assert.equal(traj.observationCount, 3);
  assert.equal(traj.baselineRank, 48);
  assert.equal(traj.previousRank, 42);
  assert.equal(traj.currentRank, 37);

  assert.equal(traj.startRankFormatted, '#48');
  assert.equal(traj.previousRankFormatted, '#42');
  assert.equal(traj.currentRankFormatted, '#37');
  assert.equal(traj.dailyDeltaFormatted, '▲ +5 today');
  assert.equal(traj.cumulativeDeltaFormatted, '▲ +11 pos');
});

test('SERP Trajectory Engine — Unranked (>100) Strict Value Preservation', () => {
  const obsUnranked1: SerpObservation = {
    observationId: 'SERP-OBS-UNR-01',
    tenantId: 'sanocea',
    query: 'marketplace exception management',
    observedUrl: null,
    targetDomain: 'sanocea.com',
    rank: null, // >100 unranked
    serpType: 'ORGANIC',
    device: 'DESKTOP',
    geography: 'IN',
    language: 'en',
    provider: 'SERP_API',
    timestamp: '2026-09-29T08:00:00Z'
  };

  const obsEntered2: SerpObservation = {
    observationId: 'SERP-OBS-UNR-02',
    tenantId: 'sanocea',
    query: 'marketplace exception management',
    observedUrl: 'https://www.sanocea.com/solutions',
    targetDomain: 'sanocea.com',
    rank: 57,
    serpType: 'ORGANIC',
    device: 'DESKTOP',
    geography: 'IN',
    language: 'en',
    provider: 'SERP_API',
    timestamp: '2026-09-30T08:00:00Z'
  };

  const traj = SerpTrajectoryEngine.computeTrajectory([obsUnranked1, obsEntered2]);
  assert.ok(traj);

  // Truth Rule 4: >100 must remain >100; never convert into an invented numeric rank
  assert.equal(traj.startRankFormatted, '>100');
  assert.equal(traj.previousRankFormatted, '>100');
  assert.equal(traj.currentRankFormatted, '#57');
  assert.equal(traj.dailyDeltaFormatted, '▲ Entered SERP (#57)');
  assert.equal(traj.cumulativeDeltaFormatted, '▲ Net Entered (#57)');
});

test('SERP Persistence Layer — SQLite WAL Storage & Tenant Isolation', () => {
  if (fs.existsSync(TEST_DB_PATH)) fs.unlinkSync(TEST_DB_PATH);
  const db = new SeoDatabase(TEST_DB_PATH);

  try {
    const obsA: SerpObservation = {
      observationId: 'OBS-SANO-01',
      tenantId: 'sanocea',
      query: 'ecommerce operations automation',
      observedUrl: 'https://www.sanocea.com/',
      targetDomain: 'sanocea.com',
      rank: 42,
      serpType: 'ORGANIC',
      device: 'DESKTOP',
      geography: 'IN',
      language: 'en',
      provider: 'DATA_FOR_SEO',
      timestamp: '2026-09-30T08:00:00Z'
    };

    const obsB: SerpObservation = {
      observationId: 'OBS-SANO-02',
      tenantId: 'sanocea',
      query: 'ecommerce operations automation',
      observedUrl: 'https://www.sanocea.com/',
      targetDomain: 'sanocea.com',
      rank: 39,
      serpType: 'ORGANIC',
      device: 'DESKTOP',
      geography: 'IN',
      language: 'en',
      provider: 'DATA_FOR_SEO',
      timestamp: '2026-09-30T12:00:00Z'
    };

    const obsProspect: SerpObservation = {
      observationId: 'OBS-PROSPECT-01',
      tenantId: 'waaree',
      query: 'solar panel online purchase',
      observedUrl: 'https://shop.waaree.com/',
      targetDomain: 'shop.waaree.com',
      rank: 8,
      serpType: 'ORGANIC',
      device: 'DESKTOP',
      geography: 'IN',
      language: 'en',
      provider: 'DATA_FOR_SEO',
      timestamp: '2026-09-30T08:00:00Z'
    };

    db.recordSerpObservation(obsA);
    db.recordSerpObservation(obsB);
    db.recordSerpObservation(obsProspect);

    // 1. Retrieve sanocea trajectory
    const sanoceaTraj = db.getSerpTrajectory('sanocea', 'ecommerce operations automation');
    assert.ok(sanoceaTraj, 'Must return trajectory for sanocea');
    assert.equal(sanoceaTraj.observationCount, 2);
    assert.equal(sanoceaTraj.baselineRank, 42);
    assert.equal(sanoceaTraj.previousRank, 42);
    assert.equal(sanoceaTraj.currentRank, 39);
    assert.equal(sanoceaTraj.dailyDeltaFormatted, '▲ +3 today');

    // 2. Tenant isolation: sanocea must not see waaree's observations
    const allSanocea = db.getAllSerpTrajectories('sanocea');
    assert.equal(allSanocea.length, 1);
    assert.equal(allSanocea[0].query, 'ecommerce operations automation');

    const allWaaree = db.getAllSerpTrajectories('waaree');
    assert.equal(allWaaree.length, 1);
    assert.equal(allWaaree[0].query, 'solar panel online purchase');
  } finally {
    db.close();
    if (fs.existsSync(TEST_DB_PATH)) fs.unlinkSync(TEST_DB_PATH);
  }
});
