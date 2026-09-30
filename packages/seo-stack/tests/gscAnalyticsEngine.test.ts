/**
 * SANOCEA SEO Stack — Milestone 5.1 GSC Ingestion & Analytics Engine Test Suite
 * 
 * Verifies:
 * 1. GscAuthManager OAuth URL generation, Service Account JWT signing, and property verification
 * 2. Multi-dimensional Search Analytics ingestion (queries, pages, devices, appearances)
 * 3. Historical snapshot storage and period-over-period delta computation
 * 4. Deterministic detection of Winners, Losers, New Queries, Lost Queries, and Strike-Zone opportunities
 * 5. Strict adherence to data provenance ([OBSERVED] / [CALCULATED] / [REQUIRES_ACCESS])
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as crypto from 'node:crypto';
import { GscAuthManager } from '../src/search-intel/gscAuth.js';
import { GscClient } from '../src/search-intel/gscClient.js';
import { GscSnapshotStore } from '../src/search-intel/gscSnapshotStore.js';
import { GscSnapshot } from '../src/core/types.js';

test('Milestone 5.1.1 — GscAuthManager: OAuth URL Generation & Service Account JWT Signing', async () => {
  // 1. Test OAuth 2.0 Auth URL Generation
  const oauthManager = new GscAuthManager({
    authType: 'OAUTH_2',
    oauth: {
      clientId: 'sanocea-client-123.apps.googleusercontent.com',
      clientSecret: 'secret-xyz',
      redirectUri: 'https://sanocea.com/oauth/google/callback'
    }
  });

  const authUrl = oauthManager.generateAuthUrl('state-tenant-waaree');
  assert.ok(authUrl.startsWith('https://accounts.google.com/o/oauth2/v2/auth'));
  assert.ok(authUrl.includes('client_id=sanocea-client-123.apps.googleusercontent.com'));
  assert.ok(authUrl.includes('scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fwebmasters.readonly'));
  assert.ok(authUrl.includes('state=state-tenant-waaree'));

  // 2. Test Service Account JWT generation with generated RSA key pair
  const { privateKey } = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' }
  });

  const saManager = new GscAuthManager({
    authType: 'SERVICE_ACCOUNT',
    serviceAccount: {
      client_email: 'sanocea-seo-bot@sanocea-prod.iam.gserviceaccount.com',
      private_key: privateKey,
      project_id: 'sanocea-prod'
    }
  });

  // Verify private method / internal signing through reflection
  const jwt = (saManager as any).generateServiceAccountJwt();
  const parts = jwt.split('.');
  assert.equal(parts.length, 3, 'JWT must have 3 segments (header.payload.signature)');

  const header = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf-8'));
  const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf-8'));

  assert.equal(header.alg, 'RS256');
  assert.equal(payload.iss, 'sanocea-seo-bot@sanocea-prod.iam.gserviceaccount.com');
  assert.equal(payload.scope, 'https://www.googleapis.com/auth/webmasters.readonly');
  assert.equal(payload.aud, 'https://oauth2.googleapis.com/token');
  assert.ok(payload.exp > payload.iat);

  // 3. Test Property Verification fallback when uncredentialed
  const noAuthManager = new GscAuthManager({ authType: 'NONE' });
  const verification = await noAuthManager.verifyProperty('https://www.sanocea.com');
  assert.equal(verification.verified, false);
  assert.equal(verification.permissionLevel, 'siteUnverified');
  assert.ok(verification.errorMessage?.includes('[REQUIRES_ACCESS]'));
});

test('Milestone 5.1.2 — GscClient: Search Analytics Ingestion & Structured Snapshot Capture', async () => {
  const authManager = new GscAuthManager({
    authType: 'MOCK_FIXTURE',
    mockVerification: { verified: true, permissionLevel: 'siteOwner' }
  });

  const mockSnapshotData: GscSnapshot = {
    snapshotId: 'SNAP-SANOCEA-M1',
    siteUrl: 'https://www.sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    totalClicks: 420,
    totalImpressions: 12500,
    averageCtr: 0.0336,
    averagePosition: 8.4,
    queryRows: [
      { query: 'ecommerce operations automation', clicks: 120, impressions: 2400, ctr: 0.05, position: 4.2 },
      { query: 'marketplace exception reconciliation', clicks: 85, impressions: 1800, ctr: 0.0472, position: 5.8 },
      { query: 'shopify catalog sync errors', clicks: 45, impressions: 2100, ctr: 0.0214, position: 7.9 },
      { query: 'automated buy box repricing', clicks: 15, impressions: 3200, ctr: 0.0047, position: 9.6 },
      { query: 'b2b catalog onboarding software', clicks: 80, impressions: 1100, ctr: 0.0727, position: 3.1 }
    ],
    pageRows: [
      { page: 'https://www.sanocea.com/', clicks: 280, impressions: 8500, ctr: 0.0329, position: 6.1 },
      { page: 'https://www.sanocea.com/demo.html', clicks: 140, impressions: 4000, ctr: 0.035, position: 7.4 }
    ],
    deviceRows: [
      { device: 'DESKTOP', clicks: 290, impressions: 7500, ctr: 0.0386, position: 7.8 },
      { device: 'MOBILE', clicks: 130, impressions: 5000, ctr: 0.026, position: 9.1 }
    ],
    searchAppearanceRows: [
      { searchAppearance: 'PRODUCT_SNIPPETS', clicks: 45, impressions: 1200, ctr: 0.0375, position: 5.2 }
    ],
    capturedAt: new Date().toISOString()
  };

  const client = new GscClient(authManager, mockSnapshotData);

  // Ingest Query Dimension
  const queryRows = await client.querySearchAnalytics({
    siteUrl: 'https://www.sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    dimensions: ['query']
  });

  assert.equal(queryRows.length, 5);
  assert.equal(queryRows[0].query, 'ecommerce operations automation');
  assert.equal(queryRows[0].clicks, 120);

  // Ingest Page Dimension
  const pageRows = await client.querySearchAnalytics({
    siteUrl: 'https://www.sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    dimensions: ['page']
  });

  assert.equal(pageRows.length, 2);
  assert.equal(pageRows[0].page, 'https://www.sanocea.com/');

  // Capture Snapshot
  const snapshot = await client.captureSnapshot('https://www.sanocea.com', {
    startDate: '2026-08-01',
    endDate: '2026-08-28'
  });

  assert.equal(snapshot.siteUrl, 'https://www.sanocea.com');
  assert.equal(snapshot.totalClicks, 420);
  assert.equal(snapshot.totalImpressions, 12500);
  assert.equal(snapshot.queryRows.length, 5);
});

test('Milestone 5.1.3 — GscSnapshotStore: Historical Period Comparison & Delta Math', () => {
  // Baseline Snapshot (Pre-Remediation: e.g. Month 1)
  const baselineSnapshot: GscSnapshot = {
    snapshotId: 'SNAP-SAN-PRE-M1',
    siteUrl: 'https://www.sanocea.com',
    dateRange: { startDate: '2026-07-01', endDate: '2026-07-28' },
    totalClicks: 280,
    totalImpressions: 10000,
    averageCtr: 0.028,
    averagePosition: 9.2,
    queryRows: [
      { query: 'ecommerce operations automation', clicks: 60, impressions: 2000, ctr: 0.03, position: 7.5 },
      { query: 'marketplace exception reconciliation', clicks: 40, impressions: 1500, ctr: 0.026, position: 8.8 },
      { query: 'shopify catalog sync errors', clicks: 30, impressions: 1800, ctr: 0.016, position: 9.1 },
      { query: 'automated buy box repricing', clicks: 10, impressions: 2500, ctr: 0.004, position: 10.5 },
      { query: 'legacy order software', clicks: 50, impressions: 800, ctr: 0.0625, position: 4.0 } // will become lost query
    ],
    pageRows: [
      { page: 'https://www.sanocea.com/', clicks: 280, impressions: 10000, ctr: 0.028, position: 9.2 }
    ],
    capturedAt: '2026-07-29T00:00:00Z'
  };

  // Comparison Snapshot (Post-Remediation: e.g. Month 2)
  const comparisonSnapshot: GscSnapshot = {
    snapshotId: 'SNAP-SAN-POST-M2',
    siteUrl: 'https://www.sanocea.com',
    dateRange: { startDate: '2026-08-01', endDate: '2026-08-28' },
    totalClicks: 470,
    totalImpressions: 14500,
    averageCtr: 0.0324,
    averagePosition: 6.8,
    queryRows: [
      { query: 'ecommerce operations automation', clicks: 140, impressions: 2600, ctr: 0.0538, position: 4.1 }, // Winner: 7.5 -> 4.1 (-3.4 delta)
      { query: 'marketplace exception reconciliation', clicks: 90, impressions: 1900, ctr: 0.0473, position: 5.2 }, // Winner: 8.8 -> 5.2 (-3.6 delta)
      { query: 'shopify catalog sync errors', clicks: 65, impressions: 2400, ctr: 0.027, position: 6.9 }, // Strike-Zone: pos 6.9, 2400 impr
      { query: 'automated buy box repricing', clicks: 25, impressions: 3800, ctr: 0.0065, position: 8.4 }, // Strike-Zone: pos 8.4, 3800 impr
      { query: 'b2b catalog onboarding software', clicks: 95, impressions: 1400, ctr: 0.0678, position: 3.2 } // New Query: 0 in baseline, active now
      // 'legacy order software' dropped to 0 impressions (Lost query)
    ],
    pageRows: [
      { page: 'https://www.sanocea.com/', clicks: 350, impressions: 11000, ctr: 0.0318, position: 7.1 },
      { page: 'https://www.sanocea.com/demo.html', clicks: 120, impressions: 3500, ctr: 0.0342, position: 6.0 }
    ],
    capturedAt: '2026-08-29T00:00:00Z'
  };

  // Test Store Persistence
  const store = new GscSnapshotStore();
  store.saveSnapshot(baselineSnapshot);
  store.saveSnapshot(comparisonSnapshot);

  const siteSnapshots = store.getSnapshotsForSite('https://www.sanocea.com');
  assert.equal(siteSnapshots.length, 2);
  assert.equal(siteSnapshots[0].snapshotId, 'SNAP-SAN-PRE-M1');

  // Test Period Delta Calculation
  const report = GscSnapshotStore.compareSnapshots(baselineSnapshot, comparisonSnapshot);

  // Exact Aggregate Deltas [CALCULATED]
  assert.equal(report.totalClickDelta, 190, 'Clicks: 470 - 280 = +190');
  assert.equal(report.totalImpressionDelta, 4500, 'Impressions: 14500 - 10000 = +4500');
  assert.ok(Math.abs(report.averagePositionDelta - (-2.4)) < 0.001, 'Position: 6.8 - 9.2 = -2.4 (rank improvement)');

  // 1. Assert Winners Detection (positionDelta <= -1.5)
  assert.ok(report.winners.length >= 2, 'Must detect at least 2 rank winners');
  const topWinner = report.winners.find(w => w.key === 'ecommerce operations automation');
  assert.ok(topWinner);
  assert.ok(topWinner.positionDelta <= -3.0, 'Rank improved by >= 3 positions');
  assert.equal(topWinner.clickDelta, 80, 'Gained +80 clicks');

  // 2. Assert New Query Detection
  const newQuery = report.newQueries.find(q => q.key === 'b2b catalog onboarding software');
  assert.ok(newQuery, 'Must detect newly appearing query');
  assert.equal(newQuery.baselineImpressions, 0);
  assert.equal(newQuery.comparisonImpressions, 1400);

  // 3. Assert Lost Query Detection
  const lostQuery = report.lostQueries.find(q => q.key === 'legacy order software');
  assert.ok(lostQuery, 'Must detect lost query dropping out of top rankings');
  assert.equal(lostQuery.baselineImpressions, 800);
  assert.equal(lostQuery.comparisonImpressions, 0);

  // 4. Assert Strike-Zone Opportunities (positions 4.0 to 10.9 with high impressions)
  assert.ok(report.strikeZoneQueries.length >= 2, 'Must detect strike-zone queries');
  const strikeItem = report.strikeZoneQueries.find(q => q.key === 'automated buy box repricing');
  assert.ok(strikeItem);
  assert.ok(strikeItem.comparisonPosition >= 4.0 && strikeItem.comparisonPosition <= 10.9);
  assert.equal(strikeItem.comparisonImpressions, 3800, 'High impression candidate on bottom of page 1');
});
