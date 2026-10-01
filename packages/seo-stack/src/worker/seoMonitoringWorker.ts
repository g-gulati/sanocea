/**
 * SANOCEA SEO Stack — 24/7 Autonomous SEO Monitoring Worker
 * 
 * 3-Tier Autonomous Operating Model:
 * Tier 1 — Hourly Lightweight Probe (Sitemap delta, critical URL health, robots noindex emergency, title/H1/canonical check)
 * Tier 2 — Daily Search Intelligence (GSC search analytics sync, period delta comparison, P0/P1 threshold evaluation, WhatsApp dispatch)
 * Tier 3 — Bi-Weekly Comprehensive Audit (Full headless crawl, link graph, schema validation, commercial prioritization)
 * 
 * Strict Tenant Boundary:
 * Autonomous worker executes strictly for 'sanocea' (www.sanocea.com).
 * All prospect tenants are barred from autonomous background runs.
 */

import * as fs from 'node:fs';
import { SeoDatabase, MonitoringHeartbeat, DetectedChange } from '../persistence/seoDb.js';
import { TenantMonitoringPolicyManager } from './tenantPolicy.js';
import { AutonomousRemediator } from './autonomousRemediator.js';
import { GscClient } from '../search-intel/gscClient.js';
import { GscAuthManager, ServiceAccountCredentials } from '../search-intel/gscAuth.js';
import { GscSnapshotStore } from '../search-intel/gscSnapshotStore.js';
import { SearchSignalsEngine, SearchSignalsReport, ActionableSeoSignal } from '../search-intel/searchSignalsEngine.js';
import { SerpTrajectory } from '../search-intel/serpTypes.js';
import { SeoAuditPipeline } from '../pipeline/auditPipeline.js';
import { SeoFinding, GscSnapshot } from '../core/types.js';
import { calculateTitlePixelWidth, GOOGLE_SERP_LIMITS } from '../core/pixelWidth.js';
import * as cheerio from 'cheerio';
import { KeywordIntelligenceEngine, createKeywordProviderFromEnv } from '../search-intel/keywordIntelligence.js';
import { KeywordDataProvider } from '../search-intel/keywordIntelligence.js';
import { AeoIntelligenceEngine, AeoSerpProvider, UnconfiguredAeoProvider } from '../search-intel/aeoIntelligence.js';
import { GeoCitationEngine, GeoCitationProvider, UnconfiguredGeoProvider } from '../search-intel/geoCitationEngine.js';
import { CompetitorIntelligenceEngine, CompetitorEngineOptions, DEFAULT_COMPETITOR_ROSTER } from '../search-intel/competitorWorker.js';
import { CompetitorConfig } from '../search-intel/rankCommandTypes.js';
import { GscPropertyService } from '../search-intel/gscProperty.js';
import { AUTONOMY_MODES, POLICY_REF } from '../opportunities/autonomyPolicy.js';
import { OpportunityEngine } from '../opportunities/opportunityEngine.js';
import { AgentRosterManager } from '../agents/agentRoster.js';
import { buildLiveSerpRankMovement, verifiedSerpTrajectories, LiveSerpRankMovement } from '../search-intel/serpRankMovement.js';
import { GscPositionTracker, GscPositionCollectResult, GscPositionTrajectory } from '../search-intel/gscPositionTracker.js';
import { BingWebmasterCollector } from '../search-intel/bingWebmaster.js';
import { CommonCrawlAuthorityCollector } from '../search-intel/commonCrawlGraph.js';
import { ModelVisibilityHarness, ModelHarnessOptions } from '../search-intel/aeoModelHarness.js';
import { JobScheduler, JobDefinition } from '../scheduler/jobScheduler.js';
import { 
  KeywordIntelligenceReport, 
  AeoSummary, 
  GeoSummary, 
  CompetitiveIntelligenceReport, 
  AgentRosterSummary 
} from '../search-intel/rankCommandTypes.js';

export interface SeoWorkerConfig {
  tenantId?: string;
  domain?: string;
  dbPath?: string;
  enableTier1?: boolean;
  enableTier2?: boolean;
  enableTier3?: boolean;
  tier1IntervalMs?: number; // default: 3,600,000 (1 hour)
  tier2IntervalMs?: number; // default: 86,400,000 (24 hours)
  tier3IntervalMs?: number; // default: 1,209,600,000 (14 days)
  criticalUrls?: string[];
  /** HTTP client for tier-1 probes (tests inject a fake; production uses global fetch). */
  probeFetch?: typeof fetch;
  /** Wait before re-checking a failed critical URL; a P0 is only raised if the failure repeats. Default 5000ms. */
  confirmDelayMs?: number;
  /** HTTP client for Google property calls (sites/sitemaps/URL Inspection); tests inject a fake. */
  googleFetch?: typeof fetch;
  gscClient?: GscClient;
  gscPropertyUrl?: string;
  gscServiceAccount?: ServiceAccountCredentials;
  /** Provider wiring for RankCommand intelligence. Production defaults are real-or-fail-closed. */
  rankCommand?: {
    keywordProvider?: KeywordDataProvider;
    aeoProvider?: AeoSerpProvider;
    geoProvider?: GeoCitationProvider;
    competitors?: CompetitorConfig[];
    competitorOptions?: CompetitorEngineOptions;
    trackedQueries?: string[];
    bingApiKey?: string;
    bingFetch?: typeof fetch;
    /** HTTP client for the AI Content Auditor's published-page checks. */
    pageFetch?: typeof fetch;
    authorityFetch?: typeof fetch;
    authorityRelease?: string;
    modelHarness?: ModelHarnessOptions;
  };
  /** Persisted job scheduler. Off by default for library/test use; the daemon turns it on. */
  scheduler?: { enabled?: boolean; tickMs?: number; retryBaseMs?: number };
}

export interface WorkerHealthStatus {
  status: 'healthy' | 'degraded' | 'error';
  uptimeSeconds: number;
  tenantId: string;
  domain: string;
  dbPath: string;
  tier1: {
    lastRun?: string;
    lastStatus?: string;
    totalRuns: number;
  };
  tier2: {
    lastRun?: string;
    lastStatus?: string;
    totalRuns: number;
  };
  tier3: {
    lastRun?: string;
    lastStatus?: string;
    totalRuns: number;
  };
  gsc?: {
    live: boolean;
    propertyUrl: string;
    authMethod: string;
    signalsCount?: number;
  };
  rankCommand?: {
    keywordObservationsCount: number;
    aeoObservationsCount: number;
    geoCitationsCount: number;
    competitorGapsCount: number;
    activeAgentsCount: number; // agents whose latest persisted run COMPLETED (not AWAITING_PROVIDER / ALERT)
    registeredAgentsCount: number;
  };
  scheduler?: { loopRunning: boolean; lastHeartbeatAt: string | null; heartbeatAgeMs: number | null; jobs: Array<{ name: string; nextRunAt: string; lastStatus: string | null; consecutiveFailures: number; overdue: boolean }> };
  activeDeltasCount: number;
  remediationCount: number;
}

export class SeoMonitoringWorker {
  private config: Required<SeoWorkerConfig>;
  private db: SeoDatabase;
  private remediator: AutonomousRemediator;
  private gscSnapshotStore: GscSnapshotStore;
  private keywordEngine: KeywordIntelligenceEngine;
  private aeoEngine: AeoIntelligenceEngine;
  private geoEngine: GeoCitationEngine;
  private competitorEngine: CompetitorIntelligenceEngine;
  private agentRoster: AgentRosterManager;
  private opportunities: OpportunityEngine;
  private googleProperty: GscPropertyService;
  private bing: BingWebmasterCollector;
  private authority: CommonCrawlAuthorityCollector;
  private modelHarness: ModelVisibilityHarness;
  public readonly scheduler: JobScheduler;
  private startTime: number;
  private tier1Timer?: NodeJS.Timeout;
  private tier2Timer?: NodeJS.Timeout;
  private tier3Timer?: NodeJS.Timeout;
  private isRunning: boolean = false;

  private tier1RunCount: number = 0;
  private tier2RunCount: number = 0;
  private tier3RunCount: number = 0;

  // Cached sitemap length for change detection
  private lastSitemapCount: number = 0;
  private isLiveGsc: boolean = false;
  private gscPropertyUrl: string;
  private lastSearchSignals?: SearchSignalsReport;

  constructor(config: SeoWorkerConfig = {}) {
    const tenantId = config.tenantId || 'sanocea';
    
    // Strict Tenant Policy Enforcement
    TenantMonitoringPolicyManager.assertMonitoringAllowed(tenantId);

    // Check service account credentials from config or environment
    let serviceAccount: ServiceAccountCredentials | undefined = config.gscServiceAccount;
    const saPath = process.env.GSC_SERVICE_ACCOUNT_PATH;
    const saRaw = process.env.GSC_SERVICE_ACCOUNT_KEY;

    if (!serviceAccount && saPath && fs.existsSync(saPath)) {
      try {
        serviceAccount = JSON.parse(fs.readFileSync(saPath, 'utf8'));
      } catch (e: any) {
        console.error(`[SEO-WORKER] Failed to read service account from ${saPath}:`, e.message);
      }
    } else if (!serviceAccount && saRaw) {
      try {
        const decoded = saRaw.startsWith('{') ? saRaw : Buffer.from(saRaw, 'base64').toString('utf8');
        serviceAccount = JSON.parse(decoded);
      } catch (e: any) {
        console.error(`[SEO-WORKER] Failed to parse GSC_SERVICE_ACCOUNT_KEY:`, e.message);
      }
    }

    let authMgr: GscAuthManager;
    if (serviceAccount && serviceAccount.client_email && serviceAccount.private_key) {
      authMgr = new GscAuthManager({
        authType: 'SERVICE_ACCOUNT',
        serviceAccount
      });
      this.isLiveGsc = true;
      console.log(`[SEO-WORKER] Live GSC integration initialized for ${serviceAccount.client_email}`);
    } else {
      authMgr = new GscAuthManager({ authType: 'MOCK_FIXTURE' });
    }

    const defaultGscClient = new GscClient(authMgr);
    const domain = config.domain || 'www.sanocea.com';
    this.gscPropertyUrl = config.gscPropertyUrl || process.env.GSC_PROPERTY_URL || `sc-domain:${domain.replace(/^www\./, '')}`;

    this.config = {
      tenantId,
      domain,
      dbPath: config.dbPath || '',
      enableTier1: config.enableTier1 ?? true,
      enableTier2: config.enableTier2 ?? true,
      enableTier3: config.enableTier3 ?? true,
      tier1IntervalMs: config.tier1IntervalMs || 3600000,
      tier2IntervalMs: config.tier2IntervalMs || 86400000,
      tier3IntervalMs: config.tier3IntervalMs || 1209600000,
      googleFetch: config.googleFetch || (((u: any, i: any) => fetch(u, i)) as typeof fetch),
      probeFetch: config.probeFetch || (((u: any, i: any) => fetch(u, i)) as typeof fetch),
      confirmDelayMs: config.confirmDelayMs ?? 5000,
      criticalUrls: config.criticalUrls || [
        'https://www.sanocea.com',
        'https://www.sanocea.com/robots.txt',
        'https://www.sanocea.com/sitemap.xml',
        'https://www.sanocea.com/llms.txt'
      ],
      gscClient: config.gscClient || defaultGscClient,
      gscPropertyUrl: this.gscPropertyUrl,
      gscServiceAccount: serviceAccount || ({} as any),
      rankCommand: config.rankCommand || {},
      scheduler: config.scheduler || {}
    };

    this.db = new SeoDatabase(this.config.dbPath || undefined);
    this.remediator = new AutonomousRemediator(this.db);
    this.opportunities = new OpportunityEngine(this.db);
    this.googleProperty = new GscPropertyService(this.db, { auth: this.config.gscClient?.auth, live: this.isLiveGsc, fetchImpl: config.googleFetch });
    this.gscSnapshotStore = new GscSnapshotStore(this.db, this.config.tenantId);
    const rc = config.rankCommand ?? {};
    if (rc.trackedQueries) this.trackedQueries = rc.trackedQueries;
    this.keywordEngine = new KeywordIntelligenceEngine(rc.keywordProvider ?? createKeywordProviderFromEnv(), this.db);
    this.aeoEngine = new AeoIntelligenceEngine(rc.aeoProvider ?? new UnconfiguredAeoProvider(), this.db);
    this.geoEngine = new GeoCitationEngine(rc.geoProvider ?? new UnconfiguredGeoProvider(), this.db);
    this.competitorEngine = new CompetitorIntelligenceEngine(rc.competitors ?? DEFAULT_COMPETITOR_ROSTER, this.db, rc.competitorOptions);
    this.agentRoster = new AgentRosterManager(this.db, {
      domain: this.config.domain,
      fetchImpl: rc.pageFetch,
      siteUrl: this.gscPropertyUrl,
      queries: this.trackedQueries,
      keywordEngine: this.keywordEngine,
      aeoEngine: this.aeoEngine,
      geoEngine: this.geoEngine,
      competitorEngine: this.competitorEngine
    });
    this.bing = new BingWebmasterCollector(this.db, { apiKey: rc.bingApiKey, fetchImpl: rc.bingFetch });
    this.authority = new CommonCrawlAuthorityCollector(this.db, { fetchImpl: rc.authorityFetch, release: rc.authorityRelease });
    this.modelHarness = new ModelVisibilityHarness(this.db, rc.modelHarness);
    this.scheduler = new JobScheduler(this.db, { tenantId: this.config.tenantId, tickMs: this.config.scheduler.tickMs, retryBaseMs: this.config.scheduler.retryBaseMs });
    for (const job of this.buildScheduledJobs()) this.scheduler.register(job);
    this.agentRoster.setNextRunResolver(() => this.scheduler.getNextRunAt('rankcommand-agents') ?? '');
    this.startTime = Date.now();

    // Register monitor in SQLite
    this.db.registerTenantMonitor({
      tenantId: this.config.tenantId,
      domain: this.config.domain,
      monitoringEnabled: true,
      autoRemediationEnabled: true,
      status: 'ACTIVE',
      config: {
        domain: this.config.domain,
        criticalUrls: this.config.criticalUrls
      }
    });
  }

  public getDatabase(): SeoDatabase {
    return this.db;
  }

  public getRemediator(): AutonomousRemediator {
    return this.remediator;
  }

  /**
   * Tier 1: Hourly Lightweight Monitoring Probe
   * - Sitemap <lastmod> / URL population changes
   * - Critical URL HTTP status health
   * - Emergency robots.txt / sitewide noindex detection
   * - Canonical, Title pixel width, SSR H1 presence on critical URLs
   * - Persists heartbeat and detected deltas
   * - DOES NOT run a full crawl if no changes detected
   */
  public async runTier1(): Promise<{ status: string; changes: DetectedChange[]; heartbeatId: number }> {
    TenantMonitoringPolicyManager.assertMonitoringAllowed(this.config.tenantId);
    const startMs = Date.now();
    const changes: DetectedChange[] = [];
    const timestamp = new Date().toISOString();

    try {
      // 1. Probe robots.txt for emergency sitewide noindex / Disallow: /
      await this.checkRobotsEmergency(changes, timestamp);

      // 2. Probe sitemap for population changes
      await this.checkSitemapChanges(changes, timestamp);

      // 3. Probe critical URLs (HTTP status, title pixel width, SSR H1, canonical)
      await this.checkCriticalUrls(changes, timestamp);

      const durationMs = Date.now() - startMs;
      const status = changes.some(c => c.severity === 'P0') 
        ? 'alert' 
        : changes.some(c => c.severity === 'P1') 
          ? 'degraded' 
          : 'ok';

      // Persist Heartbeat
      const heartbeatId = this.db.recordHeartbeat({
        tenantId: this.config.tenantId,
        domain: this.config.domain,
        timestamp,
        tier: 'tier1',
        status,
        changeCount: changes.length,
        durationMs,
        details: {
          changes: changes.map(c => ({ type: c.changeType, severity: c.severity, url: c.url }))
        }
      });

      this.db.updateTenantMonitorRun(this.config.tenantId, 'tier1', timestamp);
      this.tier1RunCount++;

      return { status, changes, heartbeatId };
    } catch (err: any) {
      const durationMs = Date.now() - startMs;
      const heartbeatId = this.db.recordHeartbeat({
        tenantId: this.config.tenantId,
        domain: this.config.domain,
        timestamp,
        tier: 'tier1',
        status: 'error',
        changeCount: 0,
        durationMs,
        details: { error: err.message }
      });
      return { status: 'error', changes: [], heartbeatId };
    }
  }

  /**
   * Tier 2: Daily Search Intelligence & Feed Sync
   * - Ingests GSC Search Analytics (queries & pages)
   * - Compares with persisted baseline snapshot in SQLite
   * - Evaluates ranking/click/impression drops
   * - Persists snapshots & logs longitudinal events
   */
  public async runTier2(customSnapshot?: GscSnapshot): Promise<{
    status: string;
    /** Set when status is 'unavailable': why nothing was captured. */
    reason?: string;
    snapshotId: string;
    winnersCount: number;
    losersCount: number;
    strikeZoneCount: number;
    signalsCount?: number;
    signals?: ActionableSeoSignal[];
  }> {
    TenantMonitoringPolicyManager.assertMonitoringAllowed(this.config.tenantId);
    const startMs = Date.now();
    const timestamp = new Date().toISOString();

    let snapshot: GscSnapshot;
    if (customSnapshot) {
      snapshot = customSnapshot;
    } else if (this.isLiveGsc && this.config.gscClient) {
      const now = new Date();
      const endStr = now.toISOString().split('T')[0];
      const startStr = new Date(now.getTime() - 28 * 86400000).toISOString().split('T')[0];

      try {
        snapshot = await this.config.gscClient.captureSnapshot(this.gscPropertyUrl, {
          startDate: startStr,
          endDate: endStr
        });
        console.log(`[SEO-WORKER] Captured live GSC snapshot ${snapshot.snapshotId} for ${this.gscPropertyUrl}: ${snapshot.totalClicks} clicks, ${snapshot.totalImpressions} impressions, ${snapshot.pageRows.length} pages`);
      } catch (err: any) {
        console.error(`[SEO-WORKER] Live GSC capture failed on ${this.gscPropertyUrl}:`, err.message);
        throw err;
      }
    } else {
      // Not connected to live GSC (no service account) and no snapshot supplied: there is nothing real to capture.
      // A hardcoded "baseline" snapshot used to be persisted here; that fabricated clicks/impressions/queries into
      // the production tables and would have read as an observed GSC snapshot. Nothing is captured or persisted.
      this.db.updateTenantMonitorRun(this.config.tenantId, 'tier2', timestamp);
      return {
        status: 'unavailable',
        reason: 'GSC is not connected in live mode (no service account) and no snapshot was supplied; nothing was captured or persisted.',
        snapshotId: '',
        winnersCount: 0,
        losersCount: 0,
        strikeZoneCount: 0,
        signalsCount: 0,
        signals: []
      };
    }

    // Persist snapshot to SQLite WAL
    this.gscSnapshotStore.saveSnapshot(snapshot, this.config.tenantId);

    // Retrieve historical snapshots to compute period comparison
    const history = this.gscSnapshotStore.getSnapshotsForSite(snapshot.siteUrl);
    let winnersCount = 0;
    let losersCount = 0;
    let strikeZoneCount = 0;

    if (history.length >= 2) {
      const baseline = history[0];
      const current = history[history.length - 1];
      const comparison = GscSnapshotStore.compareSnapshots(baseline, current);

      winnersCount = comparison.winners.length;
      losersCount = comparison.losers.length;
      strikeZoneCount = comparison.strikeZoneQueries.length;

      // Check if losers breached P0/P1 threshold
      if (losersCount > 0) {
        for (const loser of comparison.losers) {
          const change: DetectedChange = {
            tenantId: this.config.tenantId,
            timestamp,
            tier: 'tier2',
            changeType: 'GSC_RANKING_DROP',
            severity: loser.clickDelta <= -50 ? 'P0' : 'P1',
            url: loser.key,
            observedValue: `Pos: ${loser.comparisonPosition}, Clicks: ${loser.comparisonClicks}`,
            expectedValue: `Baseline Pos: ${loser.baselinePosition}, Clicks: ${loser.baselineClicks}`,
            details: loser
          };
          this.db.recordDetectedChange(change);
        }
      }
    }

    // Derive actionable intelligence signals from snapshot
    const signalsReport = SearchSignalsEngine.deriveSignals(snapshot, [
      `https://${this.config.domain}/`,
      `https://${this.config.domain}/solutions/marketplace-reconciliation`,
      `https://${this.config.domain}/robots.txt`,
      `https://${this.config.domain}/sitemap.xml`,
      `https://${this.config.domain}/llms.txt`
    ]);
    this.lastSearchSignals = signalsReport;

    // Record actionable signals into SQLite detected_changes
    for (const signal of signalsReport.signals) {
      if (signal.status === 'ALERT' || signal.status === 'ATTENTION' || signal.status === 'OPPORTUNITY') {
        const change: DetectedChange = {
          tenantId: this.config.tenantId,
          timestamp,
          tier: 'tier2',
          changeType: `GSC_SIGNAL_${signal.type}`,
          severity: signal.severity === 'CRITICAL' ? 'P0' : signal.severity === 'HIGH' ? 'P1' : signal.severity === 'MEDIUM' || signal.severity === 'LOW' ? 'P2' : 'INFO',
          url: snapshot.siteUrl,
          observedValue: signal.title,
          expectedValue: signal.summary,
          details: {
            signalId: signal.id,
            confidence: signal.confidence,
            remediation: signal.actionableRemediation,
            calculatedMetrics: signal.calculatedMetrics
          }
        };
        this.db.recordDetectedChange(change);
      }
    }

    const durationMs = Date.now() - startMs;
    this.db.recordHeartbeat({
      tenantId: this.config.tenantId,
      domain: this.config.domain,
      timestamp,
      tier: 'tier2',
      status: losersCount > 2 ? 'alert' : 'ok',
      changeCount: losersCount + signalsReport.signalsCount,
      durationMs,
      details: {
        snapshotId: snapshot.snapshotId,
        totalClicks: snapshot.totalClicks,
        totalImpressions: snapshot.totalImpressions,
        winnersCount,
        losersCount,
        strikeZoneCount,
        signalsCount: signalsReport.signalsCount,
        signalsSummary: signalsReport.signals.map(s => s.id)
      }
    });

    this.db.updateTenantMonitorRun(this.config.tenantId, 'tier2', timestamp);
    this.tier2RunCount++;

    // GSC position tracking, RankCommand agents and the other intelligence jobs run on the persisted JobScheduler
    // (see buildScheduledJobs), not on this in-memory tier timer.

    return {
      status: 'ok',
      snapshotId: snapshot.snapshotId,
      winnersCount,
      losersCount,
      strikeZoneCount,
      signalsCount: signalsReport.signalsCount,
      signals: signalsReport.signals
    };
  }

  /**
   * Tier 3: Bi-Weekly Comprehensive Audit
   * - Runs full crawler & audit pipeline
   * - Captures full receipt and stores in SQLite
   */
  public async runTier3(): Promise<{
    status: string;
    receiptId: string;
    findingsCount: number;
    p0Count: number;
    p1Count: number;
  }> {
    TenantMonitoringPolicyManager.assertMonitoringAllowed(this.config.tenantId);
    const startMs = Date.now();
    const timestamp = new Date().toISOString();
    const receiptId = `RCP-SEO-AUDIT-${this.config.tenantId}-${Date.now()}`;

    try {
      const pipeline = new SeoAuditPipeline({
        seedUrl: `https://${this.config.domain}`,
        maxPages: 25,
        maxDepth: 3,
        allowSubdomains: false,
        enableJsRendering: false,
        concurrency: 2
      });

      const auditResult = await pipeline.runAudit();
      const findings = auditResult.findings || [];
      const p0Count = findings.filter((f: SeoFinding) => f.severity === 'CRITICAL').length;
      const p1Count = findings.filter((f: SeoFinding) => f.severity === 'HIGH').length;

      // Save receipt in SQLite
      this.db.saveAuditReceipt({
        id: receiptId,
        tenantId: this.config.tenantId,
        domain: this.config.domain,
        timestamp,
        summary: {
          totalPagesAudited: auditResult.crawledPagesCount || 1,
          totalFindings: findings.length,
          p0Count,
          p1Count,
          durationMs: Date.now() - startMs
        },
        findings
      });

      // Automatically trigger closed-loop remediation for safe CRITICAL/HIGH findings on sanocea
      for (const finding of findings) {
        if ((finding.severity === 'CRITICAL' || finding.severity === 'HIGH') && finding.remediationStatus !== 'REJECTED') {
          await this.remediator.remediateFinding(this.config.tenantId, finding);
        }
      }

      this.db.recordHeartbeat({
        tenantId: this.config.tenantId,
        domain: this.config.domain,
        timestamp,
        tier: 'tier3',
        status: p0Count > 0 ? 'alert' : 'ok',
        changeCount: findings.length,
        durationMs: Date.now() - startMs,
        details: { receiptId, p0Count, p1Count }
      });

      this.db.updateTenantMonitorRun(this.config.tenantId, 'tier3', timestamp);
      this.tier3RunCount++;

      return {
        status: 'ok',
        receiptId,
        findingsCount: findings.length,
        p0Count,
        p1Count
      };
    } catch (err: any) {
      this.db.recordHeartbeat({
        tenantId: this.config.tenantId,
        domain: this.config.domain,
        timestamp,
        tier: 'tier3',
        status: 'error',
        changeCount: 0,
        durationMs: Date.now() - startMs,
        details: { error: err.message }
      });
      return {
        status: 'error',
        receiptId,
        findingsCount: 0,
        p0Count: 0,
        p1Count: 0
      };
    }
  }

  /**
   * Health & Observability Endpoint
   */
  public getHealth(): WorkerHealthStatus {
    const latestTier1 = this.db.getLatestHeartbeat(this.config.tenantId);
    const recentDeltas = this.db.getDetectedChanges(this.config.tenantId, 100);
    const remediations = this.db.getRemediationActions(this.config.tenantId);

    const monitor = this.db.getTenantMonitor(this.config.tenantId);

    return {
      status: latestTier1?.status === 'alert' ? 'degraded' : latestTier1?.status === 'error' ? 'error' : 'healthy',
      uptimeSeconds: Math.floor((Date.now() - this.startTime) / 1000),
      tenantId: this.config.tenantId,
      domain: this.config.domain,
      dbPath: this.db.getPath(),
      tier1: {
        lastRun: monitor?.lastTier1Run,
        lastStatus: latestTier1?.status,
        totalRuns: this.tier1RunCount
      },
      tier2: {
        lastRun: monitor?.lastTier2Run,
        lastStatus: 'ok',
        totalRuns: this.tier2RunCount
      },
      tier3: {
        lastRun: monitor?.lastTier3Run,
        lastStatus: 'ok',
        totalRuns: this.tier3RunCount
      },
      gsc: {
        live: this.isLiveGsc,
        propertyUrl: this.gscPropertyUrl,
        authMethod: this.isLiveGsc ? 'SERVICE_ACCOUNT' : 'MOCK_FIXTURE',
        signalsCount: this.getSearchSignals()?.signalsCount || 0
      },
      rankCommand: {
        keywordObservationsCount: this.db.getLatestKeywordObservations(this.config.tenantId).length,
        aeoObservationsCount: this.db.getLatestAeoObservations(this.config.tenantId).length,
        geoCitationsCount: this.db.getGeoCitationsForTenant(this.config.tenantId).length,
        competitorGapsCount: this.db.getCompetitorKeywordGaps(this.config.tenantId).length,
        activeAgentsCount: this.agentRoster.getRosterSummary(this.config.tenantId).activeAgentsCount,
        registeredAgentsCount: this.agentRoster.getAllAgents().length
      },
      scheduler: (() => { const st = this.scheduler.status(); return { loopRunning: st.loopRunning, lastHeartbeatAt: st.lastHeartbeat?.tickAt ?? null, heartbeatAgeMs: st.lastHeartbeat?.ageMs ?? null,
        jobs: st.jobs.map(j => ({ name: j.name, nextRunAt: j.nextRunAt, lastStatus: j.lastStatus, consecutiveFailures: j.consecutiveFailures, overdue: j.overdue })) }; })(),
      activeDeltasCount: recentDeltas.length,
      remediationCount: remediations.length
    };
  }

  private trackedQueries: string[] = [
    'ecommerce operations automation',
    'marketplace exception management',
    'ecommerce inventory drift automation',
    'marketplace multi-channel reconciliation',
    'automated catalog onboarding ecommerce',
    'shopify to amazon inventory sync india',
    'sanocea autonomous commerce'
  ];

  /**
   * Executes all RankCommand parity subsystems:
   * 1. Keyword Intelligence Provider
   * 2. AEO SERP Feature Engine
   * 3. GEO Citation Engine
   * 4. Competitor Intelligence Engine
   * 5. Autonomous Agent Roster
   */
  public async runRankCommandIntelligence(): Promise<{
    keywords: KeywordIntelligenceReport;
    aeo: AeoSummary;
    geo: GeoSummary;
    competitors: CompetitiveIntelligenceReport;
    agents: AgentRosterSummary;
  }> {
    const tenantId = this.config.tenantId;
    // The agents are the executors: each one calls its engine exactly once and persists an execution record.
    // Reports below are then read from persisted state, so a sync never double-bills a provider.
    await this.agentRoster.executeAll(tenantId);
    this.opportunities.refresh(tenantId);
    return {
      keywords: this.keywordEngine.latestReport(tenantId, this.trackedQueries),
      aeo: this.aeoEngine.latestSummary(tenantId, this.trackedQueries),
      geo: this.geoEngine.latestSummary(tenantId, this.trackedQueries),
      competitors: this.competitorEngine.latestReport(tenantId),
      agents: this.agentRoster.getRosterSummary(tenantId)
    };
  }

  // GET-path readers: persisted state only. They never call a provider or fetch a sitemap.
  private buildScheduledJobs(): JobDefinition[] {
    const DAY = 86400000;
    const tenantId = this.config.tenantId;
    const ownDomain = this.config.domain.replace(/^www\./, '');
    const authorityDomains = [ownDomain, ...this.competitorEngine.getCompetitors().map(c => c.domain)];
    return [
      {
        name: 'rankcommand-agents', intervalMs: DAY,
        run: async () => {
          const runs = await this.agentRoster.executeAll(tenantId);
          const counts: Record<string, number> = {};
          for (const r of runs) counts[r.status] = (counts[r.status] ?? 0) + 1;
          const opp = this.opportunities.refresh(tenantId);
          return { status: 'OK', summary: `ran ${runs.length} agents: ${Object.entries(counts).map(([k, v]) => `${k}=${v}`).join(', ')}; opportunities +${opp.created} new, ${opp.updated} re-seen`, output: { ...counts, opportunitiesCreated: opp.created } };
        }
      },
      {
        name: 'gsc-position', intervalMs: DAY,
        run: async () => {
          // Connection state is recorded on every run (including NOT_CONNECTED); sitemaps and URL Inspection only when CONNECTED.
          const prop = await this.runGoogleProperty().catch((e: any) => `property check failed: ${String(e?.message ?? e).slice(0, 120)}`);
          if (!this.isLiveGsc) return { status: 'UNAVAILABLE', summary: `GSC is not connected in live mode (no service account); ${prop}` };
          const r = await this.runGscPositionTracking();
          if (r.status !== 'OBSERVED') throw new Error(r.unavailable?.reason ?? 'GSC position collection failed');
          return { status: 'OK', summary: `${prop}; stored ${r.rowsStored} rows (site=${r.levels.SITE.rowsStored}, page=${r.levels.PAGE.rowsStored}, query=${r.levels.QUERY.rowsStored})`, output: r.levels };
        }
      },
      {
        name: 'bing-webmaster', intervalMs: DAY,
        run: async () => {
          if (!this.bing.configured) return { status: 'UNAVAILABLE', summary: 'BING_WEBMASTER_API_KEY is not configured' };
          const r = await this.bing.collect(tenantId, `https://${this.config.domain}/`);
          if (r.status !== 'OBSERVED') throw new Error(r.unavailable?.reason ?? 'Bing collection failed');
          return { status: 'OK', summary: `stored ${r.positionRowsStored} position rows, ${r.linkRowsStored} link rows`, output: r.notes };
        }
      },
      {
        name: 'authority-graph', intervalMs: 30 * DAY,
        run: async () => {
          const r = await this.authority.collect(tenantId, authorityDomains);
          if (r.status !== 'OBSERVED') throw new Error(r.unavailable?.reason ?? 'authority collection failed');
          return { status: 'OK', summary: `release ${r.releaseId}: ${r.results.filter(x => x.inGraph).length}/${r.results.length} domains in graph${r.fromCache ? ' (cached)' : ''}` };
        }
      },
      {
        name: 'model-visibility', intervalMs: 7 * DAY,
        run: async () => {
          if (!this.modelHarness.configured) return { status: 'UNAVAILABLE', summary: 'SEO_LLM_MODEL is not configured (no model selected)' };
          const r = await this.modelHarness.run(tenantId, this.trackedQueries, ['Sanocea', ownDomain]);
          if (r.observations.length === 0) throw new Error(r.unavailable[0]?.reason ?? 'no model responses');
          return { status: 'OK', summary: `${r.observations.length} samples from ${r.model}; mentions ${r.mentionRatePercent}% (model-specific)` };
        }
      }
    ];
  }

  /** LIVE SERP RANK MOVEMENT: separate capability from GSC average position. Persisted-only. */
  public getLiveSerpRankMovement(): LiveSerpRankMovement {
    return buildLiveSerpRankMovement(this.db, this.config.tenantId);
  }

  /**
   * Persisted-only: totals of the latest stored GSC snapshot. `live` says whether THIS worker is connected to the live
   * GSC API; a snapshot stored while running on fixtures must never be presented as live-verified data.
   */
  public getGscSummary() {
    const snaps = this.db.getGscSnapshotsForTenant(this.config.tenantId).sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
    const s = snaps[snaps.length - 1];
    if (!s) return { provenance: '[NOT AVAILABLE]', live: this.isLiveGsc, siteUrl: this.gscPropertyUrl, snapshot: null };
    return {
      provenance: '[OBSERVED: PERSISTED GSC SNAPSHOT]', live: this.isLiveGsc, siteUrl: this.gscPropertyUrl,
      snapshot: { snapshotId: s.snapshotId, siteUrl: s.siteUrl, startDate: s.dateRange.startDate, endDate: s.dateRange.endDate, capturedAt: s.capturedAt,
        totalClicks: s.totalClicks, totalImpressions: s.totalImpressions, averageCtr: s.averageCtr, averagePosition: s.averagePosition, queryRowCount: s.queryRows.length, pageRowCount: s.pageRows.length }
    };
  }

  public getSchedulerStatus() { return this.scheduler.status(); }

  /** Persisted-only. Common Crawl Domain Reference Graph values per tracked domain, with release + methodology. */
  public getAuthority() {
    const rows = this.authority.latest(this.config.tenantId);
    return { provenance: rows.length ? '[OBSERVED: COMMON CRAWL DOMAIN REFERENCE GRAPH]' : '[NOT AVAILABLE]', rows };
  }

  /** Persisted-only. Bing Webmaster (own property) query positions + inbound link counts. */
  public getBingReport() {
    const site = `https://${this.config.domain}/`;
    const t = this.bing.trajectories(this.config.tenantId, site);
    return {
      configured: this.bing.configured,
      queryPositions: { provenance: t.length ? '[OBSERVED: BING WEBMASTER AVERAGE POSITION]' : '[NOT AVAILABLE]', trajectories: t },
      linkCounts: this.bing.linkCounts(this.config.tenantId, site)
    };
  }

  /** Persisted-only. Model-specific AI visibility observations. */
  public getModelVisibility() { return this.modelHarness.summary(this.config.tenantId); }

  /** Records connection state; when CONNECTED also persists the sitemap list and inspects the audited URLs (capped). Read-only against Google. */
  public async runGoogleProperty(): Promise<string> {
    const tenantId = this.config.tenantId; const site = this.gscPropertyUrl;
    const conn = await this.googleProperty.refreshConnection(tenantId, site);
    if (conn.state !== 'CONNECTED') return `connection ${conn.state}`;
    const sm = await this.googleProperty.collectSitemaps(tenantId, site);
    const auditor = this.db.getLatestAgentRoster(tenantId).find(a => a.agentId === 'agent-ai-content-auditor');
    const pages: string[] = Array.isArray((auditor?.details as any)?.pages) ? (auditor!.details as any).pages.map((p: any) => p.url) : [`https://${this.config.domain}/`];
    const insp = await this.googleProperty.inspectUrls(tenantId, site, pages);
    this.opportunities.refresh(tenantId);
    return `connection CONNECTED; sitemaps ${sm.status === 'OBSERVED' ? sm.count : 'unavailable'}; inspected ${insp.inspected}, skipped ${insp.skipped}, failed ${insp.failed.length}`;
  }

  /** Persisted-only. */
  public getGoogleSearchState() {
    return this.googleProperty.getState(this.config.tenantId, this.gscPropertyUrl);
  }

  public async runGscPositionTracking(): Promise<GscPositionCollectResult> {
    return new GscPositionTracker(this.db, this.config.gscClient).collect(this.config.tenantId, this.gscPropertyUrl);
  }

  /** Persisted-only: start -> previous -> current -> movement from real GSC rows, per level. */
  public getRankMovement() {
    const tracker = new GscPositionTracker(this.db, this.config.gscClient);
    const level = (l: 'SITE' | 'PAGE' | 'QUERY') => {
      const t = tracker.trajectories(this.config.tenantId, this.gscPropertyUrl, l);
      return {
        provenance: t.length ? '[OBSERVED: GSC AVERAGE POSITION]' : '[NOT AVAILABLE]',
        note: t.length ? null : l === 'QUERY'
          ? 'No query-level positions: GSC anonymizes and omits low-volume queries. Not approximated from page or site data.'
          : 'No GSC rows with impressions have been stored for this level yet.',
        trajectories: t
      };
    };
    return {
      siteUrl: this.gscPropertyUrl,
      definition: 'GSC impression-weighted average position for our own property, per date. Not a point-in-time SERP rank; dates without impressions have no observation.',
      site: level('SITE'), pages: level('PAGE'), queries: level('QUERY')
    };
  }

  public async getKeywordReport(): Promise<KeywordIntelligenceReport> {
    return this.keywordEngine.latestReport(this.config.tenantId, this.trackedQueries);
  }

  public async getAeoReport(): Promise<AeoSummary> {
    return this.aeoEngine.latestSummary(this.config.tenantId, this.trackedQueries);
  }

  public async getGeoReport(): Promise<GeoSummary> {
    return this.geoEngine.latestSummary(this.config.tenantId, this.trackedQueries);
  }

  public async getCompetitorReport(): Promise<CompetitiveIntelligenceReport> {
    return this.competitorEngine.latestReport(this.config.tenantId);
  }

  /** Control-plane mutations (authorised by the daemon before calling). */
  public transitionOpportunity(opportunityId: string, to: any, actor: string, note: string) {
    return this.opportunities.transition(this.config.tenantId, opportunityId, to, actor, note);
  }
  public authorizeOpportunity(opportunityId: string) { return this.opportunities.authorize(this.config.tenantId, opportunityId); }
  public setAutonomyMode(mode: string, actor: string) { return this.opportunities.setAutonomyMode(this.config.tenantId, mode, actor); }
  public getAutonomy() { return { tenantId: this.config.tenantId, mode: this.opportunities.getAutonomyMode(this.config.tenantId), policy: POLICY_REF, modes: AUTONOMY_MODES }; }
  public linkOpportunityResult(opportunityId: string, ref: string, actor: string) {
    return this.opportunities.linkResult(this.config.tenantId, opportunityId, ref, actor);
  }

  /** Persisted opportunities only; reading never fetches or refreshes. */
  public getOpportunities() {
    return this.opportunities.list(this.config.tenantId);
  }

  public async getAgentRoster(): Promise<AgentRosterSummary> {
    return this.agentRoster.getRosterSummary(this.config.tenantId);
  }

  /**
   * Retrieves the latest actionable Search Signals Report
   */
  public getSearchSignals(): SearchSignalsReport | undefined {
    if (this.lastSearchSignals) return this.lastSearchSignals;
    const snapshots = this.gscSnapshotStore.getSnapshotsForSite(this.gscPropertyUrl);
    if (snapshots.length > 0) {
      this.lastSearchSignals = SearchSignalsEngine.deriveSignals(snapshots[snapshots.length - 1], [
        `https://${this.config.domain}/`,
        `https://${this.config.domain}/solutions/marketplace-reconciliation`,
        `https://${this.config.domain}/robots.txt`,
        `https://${this.config.domain}/sitemap.xml`,
        `https://${this.config.domain}/llms.txt`
      ]);
      return this.lastSearchSignals;
    }
    return undefined;
  }

  /**
   * Retrieves all computed SERP rank trajectories from the SQLite observation ledger.
   */
  /** Only trajectories from verified SERP providers; unverified stored rows are never presented as ranks. */
  public getSerpTrajectories(): SerpTrajectory[] {
    return verifiedSerpTrajectories(this.db, this.config.tenantId);
  }

  /**
   * Starts autonomous timers
   */
  public start(): void {
    if (this.isRunning) return;
    this.isRunning = true;
    if (this.config.scheduler.enabled) this.scheduler.start();

    // Run immediate Tier 1 probe
    this.runTier1().catch(console.error);

    // Schedule intervals
    if (this.config.enableTier1) {
      this.tier1Timer = setInterval(() => {
        this.runTier1().catch(console.error);
      }, this.config.tier1IntervalMs);
      this.tier1Timer.unref();
    }

    if (this.config.enableTier2) {
      this.tier2Timer = setInterval(() => {
        this.runTier2().catch(console.error);
      }, this.config.tier2IntervalMs);
      this.tier2Timer.unref();
    }

    if (this.config.enableTier3) {
      this.tier3Timer = setInterval(() => {
        this.runTier3().catch(console.error);
      }, this.config.tier3IntervalMs);
      this.tier3Timer.unref();
    }
  }

  /**
   * Stops autonomous timers and closes SQLite connection
   */
  public stop(): void {
    this.isRunning = false;
    this.scheduler.stop();
    if (this.tier1Timer) clearInterval(this.tier1Timer);
    if (this.tier2Timer) clearInterval(this.tier2Timer);
    if (this.tier3Timer) clearInterval(this.tier3Timer);
    this.db.close();
  }

  // ── Helper Probe Methods ───────────────────────────────────────────────────

  private probe(url: string, timeoutMs: number): Promise<Response> {
    return this.config.probeFetch(url, { method: 'GET', signal: AbortSignal.timeout(timeoutMs) });
  }

  private async checkRobotsEmergency(changes: DetectedChange[], timestamp: string): Promise<void> {
    const robotsUrl = `https://${this.config.domain}/robots.txt`;
    try {
      const res = await fetch(robotsUrl, { method: 'GET', signal: AbortSignal.timeout(5000) });
      if (res.ok) {
        const text = await res.text();
        // Check for catastrophic sitewide Disallow: /
        if (/User-agent:\s*\*\s*\nDisallow:\s*\/\s*$/m.test(text)) {
          const change: DetectedChange = {
            tenantId: this.config.tenantId,
            timestamp,
            tier: 'tier1',
            changeType: 'EMERGENCY_NOINDEX_ROBOTS',
            severity: 'P0',
            url: robotsUrl,
            observedValue: 'User-agent: * Disallow: /',
            expectedValue: 'Permissive indexing policy for production routes'
          };
          changes.push(change);
          this.db.recordDetectedChange(change);
        }
      }
    } catch {
      // Network failure on external fetch, skip or mark degraded
    }
  }

  private async checkSitemapChanges(changes: DetectedChange[], timestamp: string): Promise<void> {
    const sitemapUrl = `https://${this.config.domain}/sitemap.xml`;
    try {
      const res = await fetch(sitemapUrl, { method: 'GET', signal: AbortSignal.timeout(5000) });
      if (res.ok) {
        const text = await res.text();
        const urls = text.match(/<loc>(.*?)<\/loc>/g) || [];
        if (this.lastSitemapCount > 0 && Math.abs(urls.length - this.lastSitemapCount) > 5) {
          const change: DetectedChange = {
            tenantId: this.config.tenantId,
            timestamp,
            tier: 'tier1',
            changeType: 'SITEMAP_POPULATION_SHIFT',
            severity: 'P1',
            url: sitemapUrl,
            observedValue: `${urls.length} URLs in sitemap`,
            expectedValue: `Previous count: ${this.lastSitemapCount} URLs`
          };
          changes.push(change);
          this.db.recordDetectedChange(change);
        }
        this.lastSitemapCount = urls.length;
      }
    } catch {
      // skip
    }
  }

  private async checkCriticalUrls(changes: DetectedChange[], timestamp: string): Promise<void> {
    const rootUrl = `https://${this.config.domain}`;
    try {
      let res = await this.probe(rootUrl, 6000);
      if (!res.ok) {
        // Confirm before alerting: an hourly monitor must not raise a P0 for one failed request. Only a failure that
        // repeats on a fresh request is recorded as P0; a recovery is still recorded (P2) so the blip stays visible.
        const firstStatus = res.status;
        await new Promise(resolve => setTimeout(resolve, this.config.confirmDelayMs));
        let second: Response | null = null;
        try { second = await this.probe(rootUrl, 6000); } catch { second = null; }
        if (!second || !second.ok) {
          const change: DetectedChange = {
            tenantId: this.config.tenantId,
            timestamp,
            tier: 'tier1',
            changeType: second ? 'CRITICAL_URL_HTTP_STATUS' : 'CRITICAL_URL_UNCONFIRMED',
            severity: second ? 'P0' : 'P2',
            url: rootUrl,
            observedValue: second
              ? `HTTP Status: ${second.status} (confirmed: HTTP ${firstStatus} on the first check, same on the re-check ${this.config.confirmDelayMs}ms later)`
              : `HTTP Status: ${firstStatus} on the first check; the re-check could not complete, so this is unconfirmed`,
            expectedValue: 'HTTP 200 OK'
          };
          changes.push(change);
          this.db.recordDetectedChange(change);
          return;
        }
        const change: DetectedChange = {
          tenantId: this.config.tenantId,
          timestamp,
          tier: 'tier1',
          changeType: 'CRITICAL_URL_TRANSIENT_FAILURE',
          severity: 'P2',
          url: rootUrl,
          observedValue: `HTTP ${firstStatus} on the first check, HTTP ${second.status} on the re-check ${this.config.confirmDelayMs}ms later`,
          expectedValue: 'HTTP 200 OK on both checks'
        };
        changes.push(change);
        this.db.recordDetectedChange(change);
        res = second;
      }

      const html = await res.text();
      const $ = cheerio.load(html);

      // 1. Meta robots noindex check
      const robotsMeta = $('meta[name="robots"]').attr('content') || '';
      if (robotsMeta.toLowerCase().includes('noindex')) {
        const change: DetectedChange = {
          tenantId: this.config.tenantId,
          timestamp,
          tier: 'tier1',
          changeType: 'EMERGENCY_NOINDEX_TAG',
          severity: 'P0',
          url: rootUrl,
          observedValue: `<meta name="robots" content="${robotsMeta}">`,
          expectedValue: 'Indexable production metadata'
        };
        changes.push(change);
        this.db.recordDetectedChange(change);
      }

      // 2. Title pixel width check
      const title = $('title').text().trim();
      if (title) {
        const pWidth = calculateTitlePixelWidth(title);
        if (pWidth > GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS) {
          const change: DetectedChange = {
            tenantId: this.config.tenantId,
            timestamp,
            tier: 'tier1',
            changeType: 'TITLE_PIXEL_OVERFLOW',
            severity: 'P1',
            url: rootUrl,
            observedValue: `${pWidth}px ("${title}")`,
            expectedValue: `<= ${GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS}px boundary`
          };
          changes.push(change);
          this.db.recordDetectedChange(change);
        }
      }

      // 3. SSR H1 presence check
      const h1Count = $('h1').length;
      if (h1Count === 0) {
        const change: DetectedChange = {
          tenantId: this.config.tenantId,
          timestamp,
          tier: 'tier1',
          changeType: 'SSR_H1_MISSING',
          severity: 'P1',
          url: rootUrl,
          observedValue: '0 <h1> tags in raw HTML payload',
          expectedValue: '1 semantic topic heading in SSR shell'
        };
        changes.push(change);
        this.db.recordDetectedChange(change);
      }
    } catch {
      // skip
    }
  }
}
