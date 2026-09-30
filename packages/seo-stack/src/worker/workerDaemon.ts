/**
 * SANOCEA SEO Stack — Production Autonomous Worker Daemon
 * 
 * Runs continuously under systemd as 'sanocea-seo-worker.service'.
 * Provides:
 * - 24/7 background scheduler (Tier 1 Hourly, Tier 2 Daily, Tier 3 Bi-weekly)
 * - HTTP Health & Metrics Endpoint on port 8089 (GET /health)
 * - Persistent SQLite WAL state
 * - Graceful SIGTERM/SIGINT shutdown handling
 */

import http from 'node:http';
import { SeoMonitoringWorker } from './seoMonitoringWorker.js';

const PORT = parseInt(process.env.SEO_WORKER_PORT || '8089', 10);
const DOMAIN = process.env.SEO_MONITORED_DOMAIN || 'www.sanocea.com';
const TENANT_ID = process.env.SEO_TENANT_ID || 'sanocea';
const DB_PATH = process.env.SEO_DB_PATH || undefined;

const GSC_PROPERTY = process.env.GSC_PROPERTY_URL || `sc-domain:${DOMAIN.replace(/^www\./, '')}`;

console.log(`[SEO-WORKER] Initializing 24/7 Autonomous SEO Monitor for tenant: ${TENANT_ID} (${DOMAIN}, GSC: ${GSC_PROPERTY})`);

const worker = new SeoMonitoringWorker({
  tenantId: TENANT_ID,
  domain: DOMAIN,
  dbPath: DB_PATH,
  gscPropertyUrl: GSC_PROPERTY,
  enableTier1: true,
  enableTier2: true,
  enableTier3: true,
  tier1IntervalMs: parseInt(process.env.TIER1_INTERVAL_MS || '3600000', 10), // 1 hour
  tier2IntervalMs: parseInt(process.env.TIER2_INTERVAL_MS || '86400000', 10), // 24 hours
  tier3IntervalMs: parseInt(process.env.TIER3_INTERVAL_MS || '1209600000', 10), // 14 days
  scheduler: { enabled: true }, // persisted job scheduler: agents, GSC positions, Bing, authority graph, model visibility
});

// Start scheduler
worker.start();
console.log(`[SEO-WORKER] Background monitoring tiers started (T1: 1h, T2: 24h, T3: 14d)`);

// Start internal HTTP health server
const server = http.createServer(async (req, res) => {
  if (req.url === '/health' || req.url === '/status') {
    const health = worker.getHealth();
    res.writeHead(health.status === 'error' ? 503 : 200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(health, null, 2));
    return;
  }

  if (req.url === '/heartbeats') {
    const db = worker.getDatabase();
    const heartbeats = db.getRecentHeartbeats(TENANT_ID, 20);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(heartbeats, null, 2));
    return;
  }

  if (req.url === '/deltas') {
    const db = worker.getDatabase();
    const changes = db.getDetectedChanges(TENANT_ID, 50);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(changes, null, 2));
    return;
  }

  if (req.url === '/sync-gsc' || req.url === '/run-tier2') {
    try {
      const result = await worker.runTier2();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ message: 'Live GSC Tier 2 sync executed successfully', result }, null, 2));
    } catch (err: any) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }, null, 2));
    }
    return;
  }

  if (req.url === '/gsc-snapshots') {
    const db = worker.getDatabase();
    const snapshots = db.getGscSnapshotsForTenant(TENANT_ID);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(snapshots, null, 2));
    return;
  }

  if (req.url === '/search-signals') {
    const signals = worker.getSearchSignals();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(signals || { signalsCount: 0, signals: [] }, null, 2));
    return;
  }

  if (req.url === '/serp-trajectories') {
    const trajectories = worker.getSerpTrajectories();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(trajectories, null, 2));
    return;
  }

  if (req.url === '/rank-movement') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(worker.getRankMovement(), null, 2));
    return;
  }

  if (req.url === '/scheduler') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(worker.getSchedulerStatus(), null, 2));
    return;
  }

  if (req.url === '/authority') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(worker.getAuthority(), null, 2));
    return;
  }

  if (req.url === '/bing') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(worker.getBingReport(), null, 2));
    return;
  }

  if (req.url === '/model-visibility') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(worker.getModelVisibility(), null, 2));
    return;
  }

  if (req.url === '/agent-roster') {
    const roster = await worker.getAgentRoster();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(roster, null, 2));
    return;
  }

  if (req.url === '/keyword-intel') {
    const report = await worker.getKeywordReport();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(report, null, 2));
    return;
  }

  if (req.url === '/aeo-intel') {
    const report = await worker.getAeoReport();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(report, null, 2));
    return;
  }

  if (req.url === '/geo-intel') {
    const report = await worker.getGeoReport();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(report, null, 2));
    return;
  }

  if (req.url === '/competitive-intel') {
    const report = await worker.getCompetitorReport();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(report, null, 2));
    return;
  }

  if (req.url === '/sync-rankcommand') {
    try {
      const result = await worker.runRankCommandIntelligence();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ message: 'RankCommand intelligence sync executed successfully', result }, null, 2));
    } catch (err: any) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }, null, 2));
    }
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ 
    error: 'Not Found', 
    endpoints: [
      '/health', 
      '/heartbeats', 
      '/deltas', 
      '/sync-gsc', 
      '/gsc-snapshots', 
      '/search-signals', 
      '/serp-trajectories',
      '/rank-movement',
      '/scheduler',
      '/authority',
      '/bing',
      '/model-visibility',
      '/agent-roster',
      '/keyword-intel',
      '/aeo-intel',
      '/geo-intel',
      '/competitive-intel',
      '/sync-rankcommand'
    ] 
  }));
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[SEO-WORKER] Health endpoint listening on http://127.0.0.1:${PORT}/health`);
});

// Graceful shutdown
const shutdown = (signal: string) => {
  console.log(`[SEO-WORKER] Received ${signal}. Shutting down worker gracefully...`);
  server.close(() => {
    worker.stop();
    console.log(`[SEO-WORKER] Worker stopped and database connection closed.`);
    process.exit(0);
  });
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
