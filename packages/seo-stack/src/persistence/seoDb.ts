/**
 * SANOCEA SEO Stack — High-Performance SQLite WAL Persistence Layer
 * 
 * Persists:
 * - GSC Search Analytics snapshots & query/page tables
 * - Tier 1/2/3 Monitoring Heartbeats
 * - Detected Deltas & Threshold Breaches
 * - Audit Receipts & Longitudinal Case Study Ledgers
 * - Remediation Actions & Verified Post-Execution Evidence
 * 
 * Operates in WAL (Write-Ahead Logging) mode with deterministic ACID guarantees.
 * Process restarts do not erase monitoring history or baseline progression.
 */

import Database from 'better-sqlite3';
import path from 'node:path';
import fs from 'node:fs';
import { 
  GscSnapshot, 
  GscPerformanceRow, 
  SeoFinding 
} from '../core/types.js';
import { SerpObservation, SerpTrajectory } from '../search-intel/serpTypes.js';
import { SerpTrajectoryEngine } from '../search-intel/serpTrajectoryEngine.js';
import { 
  KeywordMetricObservation, 
  AeoObservation, 
  GeoCitationObservation, 
  CompetitorSitemapObservation, 
  CompetitorKeywordGap, 
  AgentTaskExecution 
} from '../search-intel/rankCommandTypes.js';

export interface MonitoringHeartbeat {
  id?: number;
  tenantId: string;
  domain: string;
  timestamp: string;
  tier: 'tier1' | 'tier2' | 'tier3';
  status: 'ok' | 'degraded' | 'alert' | 'error';
  changeCount: number;
  durationMs: number;
  details?: Record<string, any>;
}

export interface DetectedChange {
  id?: number;
  tenantId: string;
  timestamp: string;
  tier: 'tier1' | 'tier2' | 'tier3';
  changeType: string;
  severity: 'P0' | 'P1' | 'P2' | 'INFO';
  url?: string;
  observedValue?: string;
  expectedValue?: string;
  details?: Record<string, any>;
}

export interface PersistedAuditReceipt {
  id: string;
  tenantId: string;
  domain: string;
  timestamp: string;
  summary: Record<string, any>;
  findings: SeoFinding[];
  verification?: Record<string, any>;
}

export interface RemediationActionRecord {
  id: string;
  tenantId: string;
  findingId: string;
  timestamp: string;
  actionType: string;
  status: 'prepared' | 'executing' | 'verified' | 'failed' | 'rolled_back';
  beforeEvidence?: string;
  afterEvidence?: string;
  verificationReceiptId?: string;
  details?: Record<string, any>;
}

export interface LongitudinalLedgerEntry {
  id?: number;
  tenantId: string;
  timestamp: string;
  eventType: string;
  phase?: string;
  description: string;
  metrics?: Record<string, any>;
  causalityAnnotation?: string;
}

export interface TenantMonitorRecord {
  tenantId: string;
  domain: string;
  monitoringEnabled: boolean;
  autoRemediationEnabled: boolean;
  lastTier1Run?: string;
  lastTier2Run?: string;
  lastTier3Run?: string;
  status: string;
  config?: Record<string, any>;
}

export class SeoDatabase {
  private db: Database.Database;
  private readonly dbPath: string;

  constructor(customPath?: string) {
    if (customPath === ':memory:') {
      this.dbPath = ':memory:';
      this.db = new Database(':memory:');
    } else {
      const defaultPath = path.resolve(process.cwd(), 'data/seo_monitoring.sqlite');
      this.dbPath = customPath || process.env.SEO_DB_PATH || defaultPath;
      const dir = path.dirname(this.dbPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      this.db = new Database(this.dbPath);
    }

    // Configure SQLite for high-concurrency low-latency production operation
    if (this.dbPath !== ':memory:') {
      this.db.pragma('journal_mode = WAL');
      this.db.pragma('synchronous = NORMAL');
    }
    this.db.pragma('foreign_keys = ON');

    this.initSchema();
  }

  /** Narrow handle for modules that own their own tables (opportunities). Tenant scoping is the caller's duty. */
  public get handle(): Database.Database {
    return this.db;
  }

  public getPath(): string {
    return this.dbPath;
  }

  private initSchema(): void {
    this.dropLegacyGscPositionTable();
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS monitoring_heartbeats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        tier TEXT NOT NULL,
        status TEXT NOT NULL,
        change_count INTEGER DEFAULT 0,
        duration_ms INTEGER DEFAULT 0,
        details_json TEXT
      );

      CREATE TABLE IF NOT EXISTS gsc_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        site_url TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        total_clicks INTEGER NOT NULL,
        total_impressions INTEGER NOT NULL,
        average_ctr REAL NOT NULL,
        average_position REAL NOT NULL,
        query_count INTEGER NOT NULL,
        page_count INTEGER NOT NULL,
        raw_json TEXT
      );

      CREATE TABLE IF NOT EXISTS gsc_queries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        query TEXT NOT NULL,
        clicks INTEGER NOT NULL,
        impressions INTEGER NOT NULL,
        ctr REAL NOT NULL,
        position REAL NOT NULL,
        FOREIGN KEY (snapshot_id) REFERENCES gsc_snapshots(snapshot_id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS gsc_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        page TEXT NOT NULL,
        clicks INTEGER NOT NULL,
        impressions INTEGER NOT NULL,
        ctr REAL NOT NULL,
        position REAL NOT NULL,
        FOREIGN KEY (snapshot_id) REFERENCES gsc_snapshots(snapshot_id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS detected_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        tier TEXT NOT NULL,
        change_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        url TEXT,
        observed_value TEXT,
        expected_value TEXT,
        details_json TEXT
      );

      CREATE TABLE IF NOT EXISTS audit_receipts (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        summary_json TEXT NOT NULL,
        findings_json TEXT NOT NULL,
        verification_json TEXT
      );

      CREATE TABLE IF NOT EXISTS remediation_actions (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        finding_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        action_type TEXT NOT NULL,
        status TEXT NOT NULL,
        before_evidence TEXT,
        after_evidence TEXT,
        verification_receipt_id TEXT,
        details_json TEXT
      );

      CREATE TABLE IF NOT EXISTS longitudinal_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        phase TEXT,
        description TEXT NOT NULL,
        metrics_json TEXT,
        causality_annotation TEXT
      );

      CREATE TABLE IF NOT EXISTS tenant_monitors (
        tenant_id TEXT PRIMARY KEY,
        domain TEXT NOT NULL,
        monitoring_enabled INTEGER NOT NULL DEFAULT 0,
        auto_remediation_enabled INTEGER NOT NULL DEFAULT 0,
        last_tier1_run TEXT,
        last_tier2_run TEXT,
        last_tier3_run TEXT,
        status TEXT DEFAULT 'ACTIVE',
        config_json TEXT
      );

      CREATE TABLE IF NOT EXISTS serp_rank_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        query TEXT NOT NULL,
        observed_url TEXT,
        target_domain TEXT NOT NULL,
        rank INTEGER,
        serp_type TEXT NOT NULL DEFAULT 'ORGANIC',
        device TEXT NOT NULL DEFAULT 'DESKTOP',
        geography TEXT NOT NULL DEFAULT 'IN',
        language TEXT NOT NULL DEFAULT 'en',
        provider TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        raw_response_json TEXT
      );

      CREATE TABLE IF NOT EXISTS keyword_intelligence_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        query TEXT NOT NULL,
        search_volume INTEGER,
        cpc REAL,
        competition REAL,
        intent TEXT NOT NULL,
        cluster TEXT NOT NULL,
        geography TEXT NOT NULL,
        language TEXT NOT NULL,
        provider TEXT NOT NULL,
        provenance TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        raw_json TEXT
      );

      CREATE TABLE IF NOT EXISTS aeo_serp_feature_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        query TEXT NOT NULL,
        target_domain TEXT NOT NULL,
        has_featured_snippet INTEGER NOT NULL,
        featured_snippet_owner TEXT,
        is_featured_snippet_owned INTEGER NOT NULL,
        featured_snippet_text TEXT,
        has_people_also_ask INTEGER NOT NULL,
        paa_questions_json TEXT,
        has_ai_overview INTEGER NOT NULL,
        ai_overview_citations_json TEXT,
        is_ai_overview_owned INTEGER NOT NULL,
        provider TEXT NOT NULL,
        provenance TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        raw_json TEXT
      );

      CREATE TABLE IF NOT EXISTS geo_citation_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        query TEXT NOT NULL,
        engine TEXT NOT NULL,
        is_cited INTEGER NOT NULL,
        cited_url TEXT,
        snippet_text TEXT,
        citation_rank INTEGER,
        target_domain TEXT NOT NULL,
        provider TEXT NOT NULL,
        provenance TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        raw_json TEXT
      );

      CREATE TABLE IF NOT EXISTS competitor_sitemap_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        competitor_id TEXT NOT NULL,
        competitor_domain TEXT NOT NULL,
        sitemap_url TEXT NOT NULL,
        total_urls INTEGER NOT NULL,
        newly_discovered_urls_json TEXT,
        status TEXT NOT NULL,
        polled_at TEXT NOT NULL,
        raw_json TEXT
      );

      CREATE TABLE IF NOT EXISTS gsc_position_observations (
        tenant_id TEXT NOT NULL,
        site_url TEXT NOT NULL,
        dimension TEXT NOT NULL,
        key TEXT NOT NULL,
        observed_date TEXT NOT NULL,
        position REAL NOT NULL,
        impressions INTEGER NOT NULL,
        clicks INTEGER NOT NULL,
        ctr REAL NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, site_url, dimension, key, observed_date)
      );

      CREATE TABLE IF NOT EXISTS domain_authority_observations (
        tenant_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        release_id TEXT NOT NULL,
        source TEXT NOT NULL,
        in_graph INTEGER NOT NULL,
        harmonic_pos INTEGER,
        harmonic_val REAL,
        pagerank_pos INTEGER,
        pagerank_val REAL,
        n_hosts INTEGER,
        source_url TEXT NOT NULL,
        source_last_modified TEXT,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, domain, release_id)
      );

      CREATE TABLE IF NOT EXISTS bing_position_observations (
        tenant_id TEXT NOT NULL,
        site_url TEXT NOT NULL,
        key TEXT NOT NULL,
        observed_date TEXT NOT NULL,
        position REAL NOT NULL,
        impressions INTEGER NOT NULL,
        clicks INTEGER NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, site_url, key, observed_date)
      );

      CREATE TABLE IF NOT EXISTS bing_link_counts (
        tenant_id TEXT NOT NULL,
        site_url TEXT NOT NULL,
        page_url TEXT NOT NULL,
        inbound_links INTEGER NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, site_url, page_url, fetched_at)
      );

      CREATE TABLE IF NOT EXISTS ga4_landing_observations (
        tenant_id TEXT NOT NULL,
        property_id TEXT NOT NULL,
        observed_date TEXT NOT NULL,
        channel_group TEXT NOT NULL,
        landing_page TEXT NOT NULL,
        sessions INTEGER NOT NULL,
        users INTEGER NOT NULL,
        engaged_sessions INTEGER NOT NULL,
        engagement_seconds REAL NOT NULL,
        key_events REAL NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, property_id, observed_date, channel_group, landing_page)
      );

      CREATE TABLE IF NOT EXISTS ga4_event_inventory (
        tenant_id TEXT NOT NULL,
        property_id TEXT NOT NULL,
        event_name TEXT NOT NULL,
        is_key_event INTEGER NOT NULL,
        event_count INTEGER NOT NULL,
        key_event_count REAL NOT NULL,
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, property_id, event_name)
      );

      CREATE TABLE IF NOT EXISTS llm_model_observations (
        observation_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        prompt TEXT NOT NULL,
        sample_index INTEGER NOT NULL,
        model TEXT NOT NULL,
        endpoint_host TEXT NOT NULL,
        temperature REAL NOT NULL,
        response_text TEXT NOT NULL,
        response_sha256 TEXT NOT NULL,
        brand_mentioned INTEGER NOT NULL,
        matched_terms_json TEXT NOT NULL,
        urls_in_response_json TEXT NOT NULL,
        observed_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS scheduled_jobs (
        tenant_id TEXT NOT NULL,
        job_name TEXT NOT NULL,
        interval_ms INTEGER NOT NULL,
        next_run_at TEXT NOT NULL,
        last_run_at TEXT,
        last_status TEXT,
        last_error TEXT,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        lease_owner TEXT,
        lease_expires_at TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        registered_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, job_name)
      );

      CREATE TABLE IF NOT EXISTS job_runs (
        run_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        job_name TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        error TEXT,
        duration_ms INTEGER,
        output_json TEXT
      );

      CREATE TABLE IF NOT EXISTS scheduler_heartbeats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner TEXT NOT NULL,
        tick_at TEXT NOT NULL,
        due_jobs INTEGER NOT NULL,
        ran_jobs INTEGER NOT NULL
      );

      CREATE TABLE IF NOT EXISTS competitor_sitemap_snapshots (
        tenant_id TEXT NOT NULL,
        competitor_id TEXT NOT NULL,
        sitemap_url TEXT NOT NULL,
        observation_id TEXT NOT NULL,
        url_set_json TEXT NOT NULL,
        url_count INTEGER NOT NULL,
        content_sha256 TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, competitor_id, sitemap_url)
      );

      CREATE TABLE IF NOT EXISTS competitor_keyword_gaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        competitor_id TEXT NOT NULL,
        competitor_domain TEXT NOT NULL,
        query TEXT NOT NULL,
        competitor_rank INTEGER,
        sanocea_rank INTEGER,
        gap_status TEXT NOT NULL,
        provenance TEXT NOT NULL,
        last_compared_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS agent_task_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL,
        current_task TEXT NOT NULL,
        output_summary TEXT NOT NULL,
        provenance TEXT NOT NULL,
        executed_at TEXT NOT NULL,
        next_scheduled_at TEXT NOT NULL,
        details_json TEXT
      );

      CREATE TABLE IF NOT EXISTS seo_opportunities (
        opportunity_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        type TEXT NOT NULL,
        target TEXT NOT NULL,
        dedupe_key TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence TEXT NOT NULL,
        source TEXT NOT NULL,
        reason TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        objective TEXT NOT NULL,
        detected_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        resulting_action TEXT,
        resulting_measurement TEXT,
        UNIQUE (tenant_id, dedupe_key)
      );

      CREATE TABLE IF NOT EXISTS seo_opportunity_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        opportunity_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        at TEXT NOT NULL,
        actor TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT NOT NULL,
        note TEXT NOT NULL,
        FOREIGN KEY (opportunity_id) REFERENCES seo_opportunities(opportunity_id)
      );

      CREATE TABLE IF NOT EXISTS search_connections (
        tenant_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        property TEXT NOT NULL,
        state TEXT NOT NULL,
        auth_method TEXT NOT NULL,
        permission_level TEXT,
        scopes TEXT,
        last_checked_at TEXT NOT NULL,
        last_success_at TEXT,
        last_error TEXT,
        PRIMARY KEY (tenant_id, provider, property)
      );

      CREATE TABLE IF NOT EXISTS gsc_sitemaps (
        tenant_id TEXT NOT NULL,
        site_url TEXT NOT NULL,
        path TEXT NOT NULL,
        type TEXT,
        is_pending INTEGER,
        is_sitemaps_index INTEGER,
        last_submitted TEXT,
        last_downloaded TEXT,
        warnings INTEGER,
        errors INTEGER,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, site_url, path)
      );

      CREATE TABLE IF NOT EXISTS gsc_url_inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        site_url TEXT NOT NULL,
        url TEXT NOT NULL,
        inspected_at TEXT NOT NULL,
        verdict TEXT,
        coverage_state TEXT,
        indexing_state TEXT,
        robots_txt_state TEXT,
        page_fetch_state TEXT,
        last_crawl_time TEXT,
        google_canonical TEXT,
        user_canonical TEXT,
        crawled_as TEXT
      );

      CREATE INDEX IF NOT EXISTS idx_url_insp ON gsc_url_inspections(tenant_id, site_url, url, id);
      CREATE TABLE IF NOT EXISTS tenant_autonomy (
        tenant_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_by TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS seo_approvals (
        approval_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        opportunity_id TEXT NOT NULL,
        approval_actor_type TEXT NOT NULL CHECK (approval_actor_type IN ('HUMAN','AUTONOMOUS_AGENT')),
        actor TEXT NOT NULL,
        approval_policy TEXT NOT NULL,
        approval_reason TEXT NOT NULL,
        approved_at TEXT NOT NULL,
        approved_action TEXT NOT NULL,
        action_class TEXT NOT NULL,
        target TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        gates_json TEXT NOT NULL,
        qa_results_json TEXT,
        rollback_json TEXT,
        FOREIGN KEY (opportunity_id) REFERENCES seo_opportunities(opportunity_id)
      );

      CREATE INDEX IF NOT EXISTS idx_approvals_opp ON seo_approvals(tenant_id, opportunity_id);
      CREATE INDEX IF NOT EXISTS idx_opps_tenant ON seo_opportunities(tenant_id, status);
      CREATE INDEX IF NOT EXISTS idx_opp_events ON seo_opportunity_events(tenant_id, opportunity_id);
      CREATE INDEX IF NOT EXISTS idx_heartbeats_tenant ON monitoring_heartbeats(tenant_id, timestamp);
      CREATE INDEX IF NOT EXISTS idx_gsc_snapshots_tenant ON gsc_snapshots(tenant_id, start_date);
      CREATE INDEX IF NOT EXISTS idx_detected_changes_tenant ON detected_changes(tenant_id, timestamp);
      CREATE INDEX IF NOT EXISTS idx_remediation_tenant ON remediation_actions(tenant_id, status);
      CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON longitudinal_ledger(tenant_id, timestamp);
      CREATE INDEX IF NOT EXISTS idx_serp_obs_tenant_query ON serp_rank_observations(tenant_id, query, timestamp);
      CREATE INDEX IF NOT EXISTS idx_keyword_obs_tenant ON keyword_intelligence_observations(tenant_id, query);
      CREATE INDEX IF NOT EXISTS idx_aeo_obs_tenant ON aeo_serp_feature_observations(tenant_id, query);
      CREATE INDEX IF NOT EXISTS idx_geo_obs_tenant ON geo_citation_observations(tenant_id, query);
      CREATE INDEX IF NOT EXISTS idx_comp_sitemap_tenant ON competitor_sitemap_observations(tenant_id, competitor_id);
      CREATE INDEX IF NOT EXISTS idx_comp_gaps_tenant ON competitor_keyword_gaps(tenant_id, competitor_id);
      CREATE INDEX IF NOT EXISTS idx_agent_tasks_tenant ON agent_task_executions(tenant_id, agent_id);
    `);
    this.migrateRankCommandColumns();
    for (const col of ['diagnosis_json', 'action_plan_json']) {
      const have = (this.db.prepare(`PRAGMA table_info(seo_opportunities)`).all() as any[]).some(c => c.name === col);
      if (!have) this.db.exec(`ALTER TABLE seo_opportunities ADD COLUMN ${col} TEXT`);
    }
  }

  private dropLegacyGscPositionTable(): void {
    const cols = this.db.prepare(`PRAGMA table_info(gsc_position_observations)`).all() as any[];
    if (cols.length > 0 && !cols.some(c => c.name === 'dimension')) {
      const n = (this.db.prepare(`SELECT COUNT(*) AS n FROM gsc_position_observations`).get() as any).n;
      if (n === 0) this.db.exec(`DROP TABLE gsc_position_observations`);
      else throw new Error('gsc_position_observations has legacy shape with rows; manual migration required');
    }
  }

  private ensureColumn(table: string, column: string, ddl: string): void {
    const cols = this.db.prepare(`PRAGMA table_info(${table})`).all() as any[];
    if (!cols.some(c => c.name === column)) {
      this.db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${ddl}`);
    }
  }

  /** Additive, idempotent migrations for databases created before these columns existed. */
  private migrateRankCommandColumns(): void {
    this.ensureColumn('competitor_sitemap_observations', 'removed_urls_json', 'TEXT');
    this.ensureColumn('competitor_sitemap_observations', 'http_status', 'INTEGER');
    this.ensureColumn('competitor_sitemap_observations', 'diffed_against_previous', 'INTEGER NOT NULL DEFAULT 0');
    this.ensureColumn('competitor_sitemap_observations', 'error', 'TEXT');
    this.ensureColumn('competitor_sitemap_observations', 'provenance', "TEXT NOT NULL DEFAULT '[NOT AVAILABLE]'");
  }

  // ── Heartbeats ─────────────────────────────────────────────────────────────

  public recordHeartbeat(hb: MonitoringHeartbeat): number {
    const stmt = this.db.prepare(`
      INSERT INTO monitoring_heartbeats (
        tenant_id, domain, timestamp, tier, status, change_count, duration_ms, details_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const info = stmt.run(
      hb.tenantId,
      hb.domain,
      hb.timestamp,
      hb.tier,
      hb.status,
      hb.changeCount || 0,
      hb.durationMs || 0,
      hb.details ? JSON.stringify(hb.details) : null
    );
    return Number(info.lastInsertRowid);
  }

  public getLatestHeartbeat(tenantId: string): MonitoringHeartbeat | undefined {
    const row = this.db.prepare(`
      SELECT * FROM monitoring_heartbeats
      WHERE tenant_id = ?
      ORDER BY id DESC LIMIT 1
    `).get(tenantId) as any;

    if (!row) return undefined;
    return {
      id: row.id,
      tenantId: row.tenant_id,
      domain: row.domain,
      timestamp: row.timestamp,
      tier: row.tier,
      status: row.status,
      changeCount: row.change_count,
      durationMs: row.duration_ms,
      details: row.details_json ? JSON.parse(row.details_json) : undefined
    };
  }

  public getRecentHeartbeats(tenantId: string, limit: number = 20): MonitoringHeartbeat[] {
    const rows = this.db.prepare(`
      SELECT * FROM monitoring_heartbeats
      WHERE tenant_id = ?
      ORDER BY id DESC LIMIT ?
    `).all(tenantId, limit) as any[];

    return rows.map(row => ({
      id: row.id,
      tenantId: row.tenant_id,
      domain: row.domain,
      timestamp: row.timestamp,
      tier: row.tier,
      status: row.status,
      changeCount: row.change_count,
      durationMs: row.duration_ms,
      details: row.details_json ? JSON.parse(row.details_json) : undefined
    }));
  }

  // ── GSC Snapshots ──────────────────────────────────────────────────────────

  public saveGscSnapshot(tenantId: string, snapshot: GscSnapshot): void {
    const insertSnapshot = this.db.prepare(`
      INSERT OR REPLACE INTO gsc_snapshots (
        snapshot_id, tenant_id, site_url, start_date, end_date, captured_at,
        total_clicks, total_impressions, average_ctr, average_position,
        query_count, page_count, raw_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const insertQuery = this.db.prepare(`
      INSERT INTO gsc_queries (
        snapshot_id, tenant_id, query, clicks, impressions, ctr, position
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `);

    const insertPage = this.db.prepare(`
      INSERT INTO gsc_pages (
        snapshot_id, tenant_id, page, clicks, impressions, ctr, position
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `);

    const deleteOldQueries = this.db.prepare(`DELETE FROM gsc_queries WHERE snapshot_id = ?`);
    const deleteOldPages = this.db.prepare(`DELETE FROM gsc_pages WHERE snapshot_id = ?`);

    const transaction = this.db.transaction(() => {
      insertSnapshot.run(
        snapshot.snapshotId,
        tenantId,
        snapshot.siteUrl,
        snapshot.dateRange.startDate,
        snapshot.dateRange.endDate,
        snapshot.capturedAt,
        snapshot.totalClicks,
        snapshot.totalImpressions,
        snapshot.averageCtr,
        snapshot.averagePosition,
        snapshot.queryRows.length,
        snapshot.pageRows.length,
        JSON.stringify(snapshot)
      );

      deleteOldQueries.run(snapshot.snapshotId);
      deleteOldPages.run(snapshot.snapshotId);

      for (const q of snapshot.queryRows) {
        if (!q.query) continue;
        insertQuery.run(
          snapshot.snapshotId,
          tenantId,
          q.query,
          q.clicks,
          q.impressions,
          q.ctr,
          q.position
        );
      }

      for (const p of snapshot.pageRows) {
        if (!p.page) continue;
        insertPage.run(
          snapshot.snapshotId,
          tenantId,
          p.page,
          p.clicks,
          p.impressions,
          p.ctr,
          p.position
        );
      }
    });

    transaction();
  }

  public getGscSnapshot(snapshotId: string): GscSnapshot | undefined {
    const row = this.db.prepare(`
      SELECT raw_json FROM gsc_snapshots WHERE snapshot_id = ?
    `).get(snapshotId) as any;

    if (!row || !row.raw_json) return undefined;
    return JSON.parse(row.raw_json);
  }

  public getGscSnapshotsForTenant(tenantId: string): GscSnapshot[] {
    const rows = this.db.prepare(`
      SELECT raw_json FROM gsc_snapshots 
      WHERE tenant_id = ? 
      ORDER BY start_date ASC
    `).all(tenantId) as any[];

    return rows.map(r => JSON.parse(r.raw_json));
  }

  public getGscSnapshotsForSite(siteUrl: string): GscSnapshot[] {
    const rows = this.db.prepare(`
      SELECT raw_json FROM gsc_snapshots 
      WHERE site_url = ? 
      ORDER BY start_date ASC
    `).all(siteUrl) as any[];

    return rows.map(r => JSON.parse(r.raw_json));
  }

  // ── Detected Changes ───────────────────────────────────────────────────────

  public recordDetectedChange(change: DetectedChange): number {
    const stmt = this.db.prepare(`
      INSERT INTO detected_changes (
        tenant_id, timestamp, tier, change_type, severity, url, observed_value, expected_value, details_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const info = stmt.run(
      change.tenantId,
      change.timestamp,
      change.tier,
      change.changeType,
      change.severity,
      change.url || null,
      change.observedValue || null,
      change.expectedValue || null,
      change.details ? JSON.stringify(change.details) : null
    );
    return Number(info.lastInsertRowid);
  }

  public getDetectedChanges(tenantId: string, limit: number = 50): DetectedChange[] {
    const rows = this.db.prepare(`
      SELECT * FROM detected_changes
      WHERE tenant_id = ?
      ORDER BY id DESC LIMIT ?
    `).all(tenantId, limit) as any[];

    return rows.map(r => ({
      id: r.id,
      tenantId: r.tenant_id,
      timestamp: r.timestamp,
      tier: r.tier,
      changeType: r.change_type,
      severity: r.severity,
      url: r.url || undefined,
      observedValue: r.observed_value || undefined,
      expectedValue: r.expected_value || undefined,
      details: r.details_json ? JSON.parse(r.details_json) : undefined
    }));
  }

  // ── Audit Receipts ─────────────────────────────────────────────────────────

  public saveAuditReceipt(receipt: PersistedAuditReceipt): void {
    const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO audit_receipts (
        id, tenant_id, domain, timestamp, summary_json, findings_json, verification_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      receipt.id,
      receipt.tenantId,
      receipt.domain,
      receipt.timestamp,
      JSON.stringify(receipt.summary),
      JSON.stringify(receipt.findings),
      receipt.verification ? JSON.stringify(receipt.verification) : null
    );
  }

  public getAuditReceipt(receiptId: string): PersistedAuditReceipt | undefined {
    const row = this.db.prepare(`
      SELECT * FROM audit_receipts WHERE id = ?
    `).get(receiptId) as any;

    if (!row) return undefined;
    return {
      id: row.id,
      tenantId: row.tenant_id,
      domain: row.domain,
      timestamp: row.timestamp,
      summary: JSON.parse(row.summary_json),
      findings: JSON.parse(row.findings_json),
      verification: row.verification_json ? JSON.parse(row.verification_json) : undefined
    };
  }

  public getLatestAuditReceipt(tenantId: string): PersistedAuditReceipt | undefined {
    const row = this.db.prepare(`
      SELECT * FROM audit_receipts WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 1
    `).get(tenantId) as any;

    if (!row) return undefined;
    return {
      id: row.id,
      tenantId: row.tenant_id,
      domain: row.domain,
      timestamp: row.timestamp,
      summary: JSON.parse(row.summary_json),
      findings: JSON.parse(row.findings_json),
      verification: row.verification_json ? JSON.parse(row.verification_json) : undefined
    };
  }

  // ── Remediation Actions ────────────────────────────────────────────────────

  public recordRemediationAction(action: RemediationActionRecord): void {
    const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO remediation_actions (
        id, tenant_id, finding_id, timestamp, action_type, status,
        before_evidence, after_evidence, verification_receipt_id, details_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      action.id,
      action.tenantId,
      action.findingId,
      action.timestamp,
      action.actionType,
      action.status,
      action.beforeEvidence || null,
      action.afterEvidence || null,
      action.verificationReceiptId || null,
      action.details ? JSON.stringify(action.details) : null
    );
  }

  public updateRemediationStatus(
    actionId: string, 
    status: RemediationActionRecord['status'], 
    afterEvidence?: string,
    verificationReceiptId?: string
  ): void {
    const stmt = this.db.prepare(`
      UPDATE remediation_actions
      SET status = ?, after_evidence = COALESCE(?, after_evidence), verification_receipt_id = COALESCE(?, verification_receipt_id)
      WHERE id = ?
    `);
    stmt.run(status, afterEvidence || null, verificationReceiptId || null, actionId);
  }

  public getRemediationActions(tenantId: string): RemediationActionRecord[] {
    const rows = this.db.prepare(`
      SELECT * FROM remediation_actions WHERE tenant_id = ? ORDER BY timestamp DESC
    `).all(tenantId) as any[];

    return rows.map(r => ({
      id: r.id,
      tenantId: r.tenant_id,
      findingId: r.finding_id,
      timestamp: r.timestamp,
      actionType: r.action_type,
      status: r.status,
      beforeEvidence: r.before_evidence || undefined,
      afterEvidence: r.after_evidence || undefined,
      verificationReceiptId: r.verification_receipt_id || undefined,
      details: r.details_json ? JSON.parse(r.details_json) : undefined
    }));
  }

  // ── Longitudinal Ledger ────────────────────────────────────────────────────

  public recordLongitudinalEvent(event: LongitudinalLedgerEntry): number {
    const stmt = this.db.prepare(`
      INSERT INTO longitudinal_ledger (
        tenant_id, timestamp, event_type, phase, description, metrics_json, causality_annotation
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    const info = stmt.run(
      event.tenantId,
      event.timestamp,
      event.eventType,
      event.phase || null,
      event.description,
      event.metrics ? JSON.stringify(event.metrics) : null,
      event.causalityAnnotation || null
    );
    return Number(info.lastInsertRowid);
  }

  public getLongitudinalLedger(tenantId: string): LongitudinalLedgerEntry[] {
    const rows = this.db.prepare(`
      SELECT * FROM longitudinal_ledger WHERE tenant_id = ? ORDER BY id ASC
    `).all(tenantId) as any[];

    return rows.map(r => ({
      id: r.id,
      tenantId: r.tenant_id,
      timestamp: r.timestamp,
      eventType: r.event_type,
      phase: r.phase || undefined,
      description: r.description,
      metrics: r.metrics_json ? JSON.parse(r.metrics_json) : undefined,
      causalityAnnotation: r.causality_annotation || undefined
    }));
  }

  // ── Tenant Monitors Configuration ──────────────────────────────────────────

  public registerTenantMonitor(monitor: TenantMonitorRecord): void {
    const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO tenant_monitors (
        tenant_id, domain, monitoring_enabled, auto_remediation_enabled,
        last_tier1_run, last_tier2_run, last_tier3_run, status, config_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      monitor.tenantId,
      monitor.domain,
      monitor.monitoringEnabled ? 1 : 0,
      monitor.autoRemediationEnabled ? 1 : 0,
      monitor.lastTier1Run || null,
      monitor.lastTier2Run || null,
      monitor.lastTier3Run || null,
      monitor.status || 'ACTIVE',
      monitor.config ? JSON.stringify(monitor.config) : null
    );
  }

  public getTenantMonitor(tenantId: string): TenantMonitorRecord | undefined {
    const row = this.db.prepare(`
      SELECT * FROM tenant_monitors WHERE tenant_id = ?
    `).get(tenantId) as any;

    if (!row) return undefined;
    return {
      tenantId: row.tenant_id,
      domain: row.domain,
      monitoringEnabled: Boolean(row.monitoring_enabled),
      autoRemediationEnabled: Boolean(row.auto_remediation_enabled),
      lastTier1Run: row.last_tier1_run || undefined,
      lastTier2Run: row.last_tier2_run || undefined,
      lastTier3Run: row.last_tier3_run || undefined,
      status: row.status,
      config: row.config_json ? JSON.parse(row.config_json) : undefined
    };
  }

  public updateTenantMonitorRun(
    tenantId: string, 
    tier: 'tier1' | 'tier2' | 'tier3', 
    timestamp: string
  ): void {
    const col = tier === 'tier1' ? 'last_tier1_run' : tier === 'tier2' ? 'last_tier2_run' : 'last_tier3_run';
    const stmt = this.db.prepare(`
      UPDATE tenant_monitors SET ${col} = ? WHERE tenant_id = ?
    `);
    stmt.run(timestamp, tenantId);
  }

  // ── SERP Rank Observations & Trajectories ───────────────────────────────────

  public recordSerpObservation(obs: SerpObservation): void {
    const stmt = this.db.prepare(`
      INSERT INTO serp_rank_observations (
        observation_id, tenant_id, query, observed_url, target_domain,
        rank, serp_type, device, geography, language, provider, timestamp, raw_response_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(observation_id) DO UPDATE SET
        rank = excluded.rank,
        observed_url = excluded.observed_url,
        timestamp = excluded.timestamp
    `);
    stmt.run(
      obs.observationId,
      obs.tenantId,
      obs.query,
      obs.observedUrl || null,
      obs.targetDomain,
      obs.rank,
      obs.serpType || 'ORGANIC',
      obs.device || 'DESKTOP',
      obs.geography || 'IN',
      obs.language || 'en',
      obs.provider,
      obs.timestamp,
      obs.rawResponseJson || null
    );
  }

  public getSerpObservations(tenantId: string, query?: string): SerpObservation[] {
    if (query) {
      const stmt = this.db.prepare(`
        SELECT * FROM serp_rank_observations 
        WHERE tenant_id = ? AND query = ?
        ORDER BY timestamp ASC
      `);
      const rows = stmt.all(tenantId, query) as any[];
      return rows.map(r => this.mapSerpRow(r));
    } else {
      const stmt = this.db.prepare(`
        SELECT * FROM serp_rank_observations 
        WHERE tenant_id = ?
        ORDER BY timestamp ASC
      `);
      const rows = stmt.all(tenantId) as any[];
      return rows.map(r => this.mapSerpRow(r));
    }
  }

  public getSerpTrajectory(tenantId: string, query: string): SerpTrajectory | null {
    const observations = this.getSerpObservations(tenantId, query);
    return SerpTrajectoryEngine.computeTrajectory(observations);
  }

  public getAllSerpTrajectories(tenantId: string): SerpTrajectory[] {
    const stmt = this.db.prepare(`
      SELECT DISTINCT query FROM serp_rank_observations WHERE tenant_id = ?
    `);
    const queryRows = stmt.all(tenantId) as { query: string }[];
    const trajectories: SerpTrajectory[] = [];
    for (const { query } of queryRows) {
      const traj = this.getSerpTrajectory(tenantId, query);
      if (traj) {
        trajectories.push(traj);
      }
    }
    return trajectories;
  }

  private mapSerpRow(r: any): SerpObservation {
    return {
      id: r.id,
      observationId: r.observation_id,
      tenantId: r.tenant_id,
      query: r.query,
      observedUrl: r.observed_url,
      targetDomain: r.target_domain,
      rank: r.rank !== null ? Number(r.rank) : null,
      serpType: r.serp_type,
      device: r.device,
      geography: r.geography,
      language: r.language,
      provider: r.provider,
      timestamp: r.timestamp,
      rawResponseJson: r.raw_response_json
    };
  }

  // ── Domain authority (Common Crawl Domain Reference Graph) ─────────────────

  public upsertDomainAuthority(o: { tenantId: string; domain: string; releaseId: string; source: string; inGraph: boolean;
    harmonicPos: number | null; harmonicVal: number | null; pagerankPos: number | null; pagerankVal: number | null; nHosts: number | null;
    sourceUrl: string; sourceLastModified: string | null; fetchedAt: string }): void {
    this.db.prepare(`
      INSERT INTO domain_authority_observations (tenant_id, domain, release_id, source, in_graph, harmonic_pos, harmonic_val, pagerank_pos, pagerank_val, n_hosts, source_url, source_last_modified, fetched_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(tenant_id, domain, release_id) DO UPDATE SET in_graph = excluded.in_graph, harmonic_pos = excluded.harmonic_pos,
        harmonic_val = excluded.harmonic_val, pagerank_pos = excluded.pagerank_pos, pagerank_val = excluded.pagerank_val,
        n_hosts = excluded.n_hosts, fetched_at = excluded.fetched_at
    `).run(o.tenantId, o.domain, o.releaseId, o.source, o.inGraph ? 1 : 0, o.harmonicPos, o.harmonicVal, o.pagerankPos, o.pagerankVal, o.nHosts, o.sourceUrl, o.sourceLastModified, o.fetchedAt);
  }

  public getDomainAuthority(tenantId: string, releaseId?: string): Array<{ domain: string; releaseId: string; source: string; inGraph: boolean;
    harmonicPos: number | null; harmonicVal: number | null; pagerankPos: number | null; pagerankVal: number | null; nHosts: number | null;
    sourceUrl: string; sourceLastModified: string | null; fetchedAt: string }> {
    const rows = (releaseId
      ? this.db.prepare(`SELECT * FROM domain_authority_observations WHERE tenant_id = ? AND release_id = ? ORDER BY domain`).all(tenantId, releaseId)
      : this.db.prepare(`SELECT * FROM domain_authority_observations WHERE tenant_id = ? ORDER BY release_id DESC, domain`).all(tenantId)) as any[];
    return rows.map(r => ({ domain: r.domain, releaseId: r.release_id, source: r.source, inGraph: Boolean(r.in_graph), harmonicPos: r.harmonic_pos, harmonicVal: r.harmonic_val,
      pagerankPos: r.pagerank_pos, pagerankVal: r.pagerank_val, nHosts: r.n_hosts, sourceUrl: r.source_url, sourceLastModified: r.source_last_modified, fetchedAt: r.fetched_at }));
  }

  // ── Bing Webmaster observations (own property only) ────────────────────────

  public upsertBingPositionObservations(rows: Array<{ tenantId: string; siteUrl: string; key: string; observedDate: string; position: number; impressions: number; clicks: number; fetchedAt: string }>): void {
    const stmt = this.db.prepare(`
      INSERT INTO bing_position_observations (tenant_id, site_url, key, observed_date, position, impressions, clicks, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(tenant_id, site_url, key, observed_date) DO UPDATE SET position = excluded.position, impressions = excluded.impressions, clicks = excluded.clicks, fetched_at = excluded.fetched_at`);
    this.db.transaction(() => { for (const r of rows) stmt.run(r.tenantId, r.siteUrl, r.key, r.observedDate, r.position, r.impressions, r.clicks, r.fetchedAt); })();
  }

  public getBingPositionObservations(tenantId: string, siteUrl: string): Array<{ key: string; observedDate: string; position: number; impressions: number; clicks: number; fetchedAt: string }> {
    return (this.db.prepare(`SELECT * FROM bing_position_observations WHERE tenant_id = ? AND site_url = ? ORDER BY key, observed_date`).all(tenantId, siteUrl) as any[])
      .map(r => ({ key: r.key, observedDate: r.observed_date, position: r.position, impressions: r.impressions, clicks: r.clicks, fetchedAt: r.fetched_at }));
  }

  public recordBingLinkCounts(rows: Array<{ tenantId: string; siteUrl: string; pageUrl: string; inboundLinks: number; fetchedAt: string }>): void {
    const stmt = this.db.prepare(`INSERT OR REPLACE INTO bing_link_counts (tenant_id, site_url, page_url, inbound_links, fetched_at) VALUES (?, ?, ?, ?, ?)`);
    this.db.transaction(() => { for (const r of rows) stmt.run(r.tenantId, r.siteUrl, r.pageUrl, r.inboundLinks, r.fetchedAt); })();
  }

  public getLatestBingLinkCounts(tenantId: string, siteUrl: string): Array<{ pageUrl: string; inboundLinks: number; fetchedAt: string }> {
    const latest = (this.db.prepare(`SELECT MAX(fetched_at) AS f FROM bing_link_counts WHERE tenant_id = ? AND site_url = ?`).get(tenantId, siteUrl) as any)?.f;
    if (!latest) return [];
    return (this.db.prepare(`SELECT * FROM bing_link_counts WHERE tenant_id = ? AND site_url = ? AND fetched_at = ? ORDER BY inbound_links DESC`).all(tenantId, siteUrl, latest) as any[])
      .map(r => ({ pageUrl: r.page_url, inboundLinks: r.inbound_links, fetchedAt: r.fetched_at }));
  }

  // ── GA4 observations (own property, read-only Data API) ────────────────────

  public upsertGa4LandingObservations(rows: Array<{ tenantId: string; propertyId: string; observedDate: string; channelGroup: string; landingPage: string; sessions: number; users: number; engagedSessions: number; engagementSeconds: number; keyEvents: number; fetchedAt: string }>): void {
    const stmt = this.db.prepare(`
      INSERT INTO ga4_landing_observations (tenant_id, property_id, observed_date, channel_group, landing_page, sessions, users, engaged_sessions, engagement_seconds, key_events, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(tenant_id, property_id, observed_date, channel_group, landing_page) DO UPDATE SET sessions = excluded.sessions, users = excluded.users, engaged_sessions = excluded.engaged_sessions, engagement_seconds = excluded.engagement_seconds, key_events = excluded.key_events, fetched_at = excluded.fetched_at`);
    this.db.transaction(() => { for (const r of rows) stmt.run(r.tenantId, r.propertyId, r.observedDate, r.channelGroup, r.landingPage, r.sessions, r.users, r.engagedSessions, r.engagementSeconds, r.keyEvents, r.fetchedAt); })();
  }

  public getGa4LandingObservations(tenantId: string, propertyId: string): Array<{ observedDate: string; channelGroup: string; landingPage: string; sessions: number; users: number; engagedSessions: number; engagementSeconds: number; keyEvents: number; fetchedAt: string }> {
    return (this.db.prepare(`SELECT * FROM ga4_landing_observations WHERE tenant_id = ? AND property_id = ? ORDER BY observed_date, channel_group, landing_page`).all(tenantId, propertyId) as any[])
      .map(r => ({ observedDate: r.observed_date, channelGroup: r.channel_group, landingPage: r.landing_page, sessions: r.sessions, users: r.users, engagedSessions: r.engaged_sessions, engagementSeconds: r.engagement_seconds, keyEvents: r.key_events, fetchedAt: r.fetched_at }));
  }

  /** Per-landing-page totals from the most recently fetched GA4 property of this tenant (path as GA4 reports it). */
  public getGa4LandingTotals(tenantId: string): Array<{ landingPage: string; sessions: number; engagedSessions: number; organicSessions: number; windowStart: string; windowEnd: string; fetchedAt: string }> {
    const pid = (this.db.prepare(`SELECT property_id FROM ga4_landing_observations WHERE tenant_id = ? ORDER BY fetched_at DESC LIMIT 1`).get(tenantId) as any)?.property_id;
    if (!pid) return [];
    return (this.db.prepare(`SELECT landing_page, SUM(sessions) AS s, SUM(engaged_sessions) AS e, SUM(CASE WHEN channel_group = 'Organic Search' THEN sessions ELSE 0 END) AS o, MIN(observed_date) AS ws, MAX(observed_date) AS we, MAX(fetched_at) AS f
      FROM ga4_landing_observations WHERE tenant_id = ? AND property_id = ? GROUP BY landing_page ORDER BY s DESC`).all(tenantId, pid) as any[])
      .map(r => ({ landingPage: r.landing_page, sessions: r.s, engagedSessions: r.e, organicSessions: r.o, windowStart: r.ws, windowEnd: r.we, fetchedAt: r.f }));
  }

  public replaceGa4EventInventory(tenantId: string, propertyId: string, rows: Array<{ eventName: string; isKeyEvent: boolean; eventCount: number; keyEventCount: number; windowStart: string; windowEnd: string; fetchedAt: string }>): void {
    const stmt = this.db.prepare(`INSERT INTO ga4_event_inventory (tenant_id, property_id, event_name, is_key_event, event_count, key_event_count, window_start, window_end, fetched_at) VALUES (?,?,?,?,?,?,?,?,?)`);
    this.db.transaction(() => {
      this.db.prepare(`DELETE FROM ga4_event_inventory WHERE tenant_id = ? AND property_id = ?`).run(tenantId, propertyId);
      for (const r of rows) stmt.run(tenantId, propertyId, r.eventName, r.isKeyEvent ? 1 : 0, r.eventCount, r.keyEventCount, r.windowStart, r.windowEnd, r.fetchedAt);
    })();
  }

  public getGa4EventInventory(tenantId: string, propertyId: string): Array<{ eventName: string; isKeyEvent: boolean; eventCount: number; keyEventCount: number; windowStart: string; windowEnd: string; fetchedAt: string }> {
    return (this.db.prepare(`SELECT * FROM ga4_event_inventory WHERE tenant_id = ? AND property_id = ? ORDER BY event_count DESC`).all(tenantId, propertyId) as any[])
      .map(r => ({ eventName: r.event_name, isKeyEvent: Boolean(r.is_key_event), eventCount: r.event_count, keyEventCount: r.key_event_count, windowStart: r.window_start, windowEnd: r.window_end, fetchedAt: r.fetched_at }));
  }

  // ── Local/open model observations (model-specific) ─────────────────────────

  public recordLlmModelObservation(o: { observationId: string; tenantId: string; prompt: string; sampleIndex: number; model: string; endpointHost: string;
    temperature: number; responseText: string; responseSha256: string; brandMentioned: boolean; matchedTerms: string[]; urlsInResponse: string[]; observedAt: string }): void {
    this.db.prepare(`
      INSERT INTO llm_model_observations (observation_id, tenant_id, prompt, sample_index, model, endpoint_host, temperature, response_text, response_sha256, brand_mentioned, matched_terms_json, urls_in_response_json, observed_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(o.observationId, o.tenantId, o.prompt, o.sampleIndex, o.model, o.endpointHost, o.temperature, o.responseText, o.responseSha256, o.brandMentioned ? 1 : 0, JSON.stringify(o.matchedTerms), JSON.stringify(o.urlsInResponse), o.observedAt);
  }

  public getLlmModelObservations(tenantId: string): Array<{ observationId: string; prompt: string; sampleIndex: number; model: string; endpointHost: string; temperature: number;
    responseText: string; brandMentioned: boolean; matchedTerms: string[]; urlsInResponse: string[]; observedAt: string }> {
    return (this.db.prepare(`SELECT * FROM llm_model_observations WHERE tenant_id = ? ORDER BY observed_at DESC`).all(tenantId) as any[]).map(r => ({
      observationId: r.observation_id, prompt: r.prompt, sampleIndex: r.sample_index, model: r.model, endpointHost: r.endpoint_host, temperature: r.temperature,
      responseText: r.response_text, brandMentioned: Boolean(r.brand_mentioned), matchedTerms: JSON.parse(r.matched_terms_json), urlsInResponse: JSON.parse(r.urls_in_response_json), observedAt: r.observed_at }));
  }

  // ── Scheduler persistence ──────────────────────────────────────────────────

  /** Raw handle for the scheduler's transactional lease logic. */
  public get raw(): Database.Database { return this.db; }

  // ── GSC Average-Position Observations (isolated from SERP-provider ranks) ──


  public upsertGscPositionObservations(rows: Array<{ tenantId: string; siteUrl: string; dimension: 'SITE' | 'PAGE' | 'QUERY'; key: string;
    observedDate: string; position: number; impressions: number; clicks: number; ctr: number; fetchedAt: string }>): number {
    const stmt = this.db.prepare(`
      INSERT INTO gsc_position_observations (tenant_id, site_url, dimension, key, observed_date, position, impressions, clicks, ctr, fetched_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(tenant_id, site_url, dimension, key, observed_date) DO UPDATE SET
        position = excluded.position, impressions = excluded.impressions, clicks = excluded.clicks,
        ctr = excluded.ctr, fetched_at = excluded.fetched_at
    `);
    const tx = this.db.transaction(() => { for (const r of rows) stmt.run(r.tenantId, r.siteUrl, r.dimension, r.key, r.observedDate, r.position, r.impressions, r.clicks, r.ctr, r.fetchedAt); });
    tx();
    return rows.length;
  }

  public getGscPositionObservations(tenantId: string, siteUrl: string, dimension?: 'SITE' | 'PAGE' | 'QUERY'): Array<{ dimension: 'SITE' | 'PAGE' | 'QUERY'; key: string;
    observedDate: string; position: number; impressions: number; clicks: number; ctr: number; fetchedAt: string }> {
    const rows = (dimension
      ? this.db.prepare(`SELECT * FROM gsc_position_observations WHERE tenant_id = ? AND site_url = ? AND dimension = ? ORDER BY key, observed_date ASC`).all(tenantId, siteUrl, dimension)
      : this.db.prepare(`SELECT * FROM gsc_position_observations WHERE tenant_id = ? AND site_url = ? ORDER BY dimension, key, observed_date ASC`).all(tenantId, siteUrl)) as any[];
    return rows.map(r => ({ dimension: r.dimension, key: r.key, observedDate: r.observed_date, position: r.position, impressions: r.impressions, clicks: r.clicks, ctr: r.ctr, fetchedAt: r.fetched_at }));
  }

  // ── Keyword Intelligence Observations ──────────────────────────────────────

  public recordKeywordObservation(obs: KeywordMetricObservation): number {
    const stmt = this.db.prepare(`
      INSERT INTO keyword_intelligence_observations (
        observation_id, tenant_id, query, search_volume, cpc, competition,
        intent, cluster, geography, language, provider, provenance, timestamp, raw_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const info = stmt.run(
      obs.observationId,
      obs.tenantId,
      obs.query,
      obs.searchVolume !== null ? obs.searchVolume : null,
      obs.cpc !== null ? obs.cpc : null,
      obs.competition !== null ? obs.competition : null,
      obs.intent,
      obs.cluster,
      obs.geography,
      obs.language,
      obs.provider,
      obs.provenance,
      obs.timestamp,
      obs.rawJson || null
    );
    return Number(info.lastInsertRowid);
  }

  public getLatestKeywordObservations(tenantId: string): KeywordMetricObservation[] {
    const stmt = this.db.prepare(`
      SELECT * FROM keyword_intelligence_observations
      WHERE tenant_id = ?
      GROUP BY query
      HAVING id = MAX(id)
      ORDER BY id ASC
    `);
    const rows = stmt.all(tenantId) as any[];
    return rows.map(r => ({
      id: r.id,
      observationId: r.observation_id,
      tenantId: r.tenant_id,
      query: r.query,
      searchVolume: r.search_volume !== null ? Number(r.search_volume) : null,
      cpc: r.cpc !== null ? Number(r.cpc) : null,
      competition: r.competition !== null ? Number(r.competition) : null,
      intent: r.intent,
      cluster: r.cluster,
      geography: r.geography,
      language: r.language,
      provider: r.provider,
      provenance: r.provenance,
      timestamp: r.timestamp,
      rawJson: r.raw_json
    }));
  }

  // ── AEO Intelligence Observations ──────────────────────────────────────────

  public recordAeoObservation(obs: AeoObservation): number {
    const stmt = this.db.prepare(`
      INSERT INTO aeo_serp_feature_observations (
        observation_id, tenant_id, query, target_domain,
        has_featured_snippet, featured_snippet_owner, is_featured_snippet_owned, featured_snippet_text,
        has_people_also_ask, paa_questions_json,
        has_ai_overview, ai_overview_citations_json, is_ai_overview_owned,
        provider, provenance, timestamp, raw_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const info = stmt.run(
      obs.observationId,
      obs.tenantId,
      obs.query,
      obs.targetDomain,
      obs.hasFeaturedSnippet ? 1 : 0,
      obs.featuredSnippetOwner || null,
      obs.isFeaturedSnippetOwned ? 1 : 0,
      obs.featuredSnippetText || null,
      obs.hasPeopleAlsoAsk ? 1 : 0,
      JSON.stringify(obs.paaQuestions || []),
      obs.hasAiOverview ? 1 : 0,
      JSON.stringify(obs.aiOverviewCitations || []),
      obs.isAiOverviewOwned ? 1 : 0,
      obs.provider,
      obs.provenance,
      obs.timestamp,
      obs.rawJson || null
    );
    return Number(info.lastInsertRowid);
  }

  public getLatestAeoObservations(tenantId: string): AeoObservation[] {
    const stmt = this.db.prepare(`
      SELECT * FROM aeo_serp_feature_observations
      WHERE tenant_id = ?
      GROUP BY query
      HAVING id = MAX(id)
      ORDER BY id ASC
    `);
    const rows = stmt.all(tenantId) as any[];
    return rows.map(r => ({
      id: r.id,
      observationId: r.observation_id,
      tenantId: r.tenant_id,
      query: r.query,
      targetDomain: r.target_domain,
      hasFeaturedSnippet: Boolean(r.has_featured_snippet),
      featuredSnippetOwner: r.featured_snippet_owner,
      isFeaturedSnippetOwned: Boolean(r.is_featured_snippet_owned),
      featuredSnippetText: r.featured_snippet_text,
      hasPeopleAlsoAsk: Boolean(r.has_people_also_ask),
      paaQuestions: r.paa_questions_json ? JSON.parse(r.paa_questions_json) : [],
      hasAiOverview: Boolean(r.has_ai_overview),
      aiOverviewCitations: r.ai_overview_citations_json ? JSON.parse(r.ai_overview_citations_json) : [],
      isAiOverviewOwned: Boolean(r.is_ai_overview_owned),
      provider: r.provider,
      provenance: r.provenance,
      timestamp: r.timestamp,
      rawJson: r.raw_json
    }));
  }

  // ── GEO Citation Observations ──────────────────────────────────────────────

  public recordGeoCitation(obs: GeoCitationObservation): number {
    const stmt = this.db.prepare(`
      INSERT INTO geo_citation_observations (
        observation_id, tenant_id, query, engine, is_cited, cited_url,
        snippet_text, citation_rank, target_domain, provider, provenance, timestamp, raw_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const info = stmt.run(
      obs.observationId,
      obs.tenantId,
      obs.query,
      obs.engine,
      obs.isCited ? 1 : 0,
      obs.citedUrl || null,
      obs.snippetText || null,
      obs.citationRank !== null ? obs.citationRank : null,
      obs.targetDomain,
      obs.provider,
      obs.provenance,
      obs.timestamp,
      obs.rawJson || null
    );
    return Number(info.lastInsertRowid);
  }

  public getGeoCitationsForTenant(tenantId: string): GeoCitationObservation[] {
    const stmt = this.db.prepare(`
      SELECT * FROM geo_citation_observations
      WHERE tenant_id = ?
      ORDER BY id DESC
    `);
    const rows = stmt.all(tenantId) as any[];
    return rows.map(r => ({
      id: r.id,
      observationId: r.observation_id,
      tenantId: r.tenant_id,
      query: r.query,
      engine: r.engine,
      isCited: Boolean(r.is_cited),
      citedUrl: r.cited_url,
      snippetText: r.snippet_text,
      citationRank: r.citation_rank !== null ? Number(r.citation_rank) : null,
      targetDomain: r.target_domain,
      provider: r.provider,
      provenance: r.provenance,
      timestamp: r.timestamp,
      rawJson: r.raw_json
    }));
  }

  // ── Competitor Intelligence ────────────────────────────────────────────────

  public recordCompetitorSitemapObservation(obs: CompetitorSitemapObservation): number {
    const info = this.db.prepare(`
      INSERT INTO competitor_sitemap_observations (
        observation_id, tenant_id, competitor_id, competitor_domain, sitemap_url,
        total_urls, newly_discovered_urls_json, removed_urls_json, status, http_status,
        diffed_against_previous, error, provenance, polled_at, raw_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      obs.observationId,
      obs.tenantId,
      obs.competitorId,
      obs.competitorDomain,
      obs.sitemapUrl,
      obs.totalUrls,
      JSON.stringify(obs.newlyDiscoveredUrls || []),
      JSON.stringify(obs.removedUrls || []),
      obs.status,
      obs.httpStatus,
      obs.diffedAgainstPrevious ? 1 : 0,
      obs.error,
      obs.provenance,
      obs.polledAt,
      obs.rawJson || null
    );
    return Number(info.lastInsertRowid);
  }

  private mapSitemapRow(r: any): CompetitorSitemapObservation {
    return {
      id: r.id,
      observationId: r.observation_id,
      tenantId: r.tenant_id,
      competitorId: r.competitor_id,
      competitorDomain: r.competitor_domain,
      sitemapUrl: r.sitemap_url,
      totalUrls: r.total_urls,
      newlyDiscoveredUrls: r.newly_discovered_urls_json ? JSON.parse(r.newly_discovered_urls_json) : [],
      removedUrls: r.removed_urls_json ? JSON.parse(r.removed_urls_json) : [],
      status: r.status,
      httpStatus: r.http_status ?? null,
      diffedAgainstPrevious: Boolean(r.diffed_against_previous),
      error: r.error ?? null,
      provenance: r.provenance,
      polledAt: r.polled_at,
      rawJson: r.raw_json
    };
  }

  public getLatestCompetitorSitemapObservations(tenantId: string): CompetitorSitemapObservation[] {
    const rows = this.db.prepare(`
      SELECT * FROM competitor_sitemap_observations
      WHERE tenant_id = ?
      GROUP BY competitor_id
      HAVING id = MAX(id)
      ORDER BY id ASC
    `).all(tenantId) as any[];
    return rows.map(r => this.mapSitemapRow(r));
  }

  public getCompetitorSitemapHistory(tenantId: string, competitorId: string, limit = 50): CompetitorSitemapObservation[] {
    const rows = this.db.prepare(`
      SELECT * FROM competitor_sitemap_observations
      WHERE tenant_id = ? AND competitor_id = ?
      ORDER BY id DESC LIMIT ?
    `).all(tenantId, competitorId, limit) as any[];
    return rows.map(r => this.mapSitemapRow(r));
  }

  /** Last SUCCESSFUL sitemap URL set: the baseline the next poll is diffed against. */
  public getCompetitorSitemapSnapshot(tenantId: string, competitorId: string, sitemapUrl: string):
    { urls: string[]; capturedAt: string; observationId: string; contentSha256: string } | undefined {
    const r = this.db.prepare(`
      SELECT * FROM competitor_sitemap_snapshots
      WHERE tenant_id = ? AND competitor_id = ? AND sitemap_url = ?
    `).get(tenantId, competitorId, sitemapUrl) as any;
    if (!r) return undefined;
    return { urls: JSON.parse(r.url_set_json), capturedAt: r.captured_at, observationId: r.observation_id, contentSha256: r.content_sha256 };
  }

  public saveCompetitorSitemapSnapshot(tenantId: string, competitorId: string, sitemapUrl: string,
    snap: { urls: string[]; observationId: string; contentSha256: string; capturedAt: string }): void {
    this.db.prepare(`
      INSERT INTO competitor_sitemap_snapshots (
        tenant_id, competitor_id, sitemap_url, observation_id, url_set_json, url_count, content_sha256, captured_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(tenant_id, competitor_id, sitemap_url) DO UPDATE SET
        observation_id = excluded.observation_id,
        url_set_json = excluded.url_set_json,
        url_count = excluded.url_count,
        content_sha256 = excluded.content_sha256,
        captured_at = excluded.captured_at
    `).run(tenantId, competitorId, sitemapUrl, snap.observationId, JSON.stringify(snap.urls), snap.urls.length, snap.contentSha256, snap.capturedAt);
  }

  public recordCompetitorKeywordGaps(tenantId: string, gaps: CompetitorKeywordGap[]): void {
    const stmt = this.db.prepare(`
      INSERT INTO competitor_keyword_gaps (
        tenant_id, competitor_id, competitor_domain, query,
        competitor_rank, sanocea_rank, gap_status, provenance, last_compared_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    // Replace only the (competitor, query) pairs re-observed now; other observed gaps are kept.
    const deleteOld = this.db.prepare(`
      DELETE FROM competitor_keyword_gaps WHERE tenant_id = ? AND competitor_id = ? AND query = ?
    `);

    const tx = this.db.transaction(() => {
      for (const g of gaps) {
        deleteOld.run(tenantId, g.competitorId, g.query);
        stmt.run(
          tenantId,
          g.competitorId,
          g.competitorDomain,
          g.query,
          g.competitorRank !== null ? g.competitorRank : null,
          g.sanoceaRank !== null ? g.sanoceaRank : null,
          g.gapStatus,
          g.provenance,
          g.lastComparedAt
        );
      }
    });
    tx();
  }

  public getCompetitorKeywordGaps(tenantId: string): CompetitorKeywordGap[] {
    const stmt = this.db.prepare(`
      SELECT * FROM competitor_keyword_gaps
      WHERE tenant_id = ?
      ORDER BY id ASC
    `);
    const rows = stmt.all(tenantId) as any[];
    return rows.map(r => ({
      id: r.id,
      tenantId: r.tenant_id,
      competitorId: r.competitor_id,
      competitorDomain: r.competitor_domain,
      query: r.query,
      competitorRank: r.competitor_rank !== null ? Number(r.competitor_rank) : null,
      sanoceaRank: r.sanocea_rank !== null ? Number(r.sanocea_rank) : null,
      gapStatus: r.gap_status,
      provenance: r.provenance,
      lastComparedAt: r.last_compared_at
    }));
  }

  // ── Agent Task Executions ──────────────────────────────────────────────────

  public recordAgentTaskExecution(task: AgentTaskExecution): number {
    const stmt = this.db.prepare(`
      INSERT INTO agent_task_executions (
        task_id, tenant_id, agent_id, agent_name, role, status,
        current_task, output_summary, provenance, executed_at, next_scheduled_at, details_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const info = stmt.run(
      task.taskId,
      task.tenantId,
      task.agentId,
      task.agentName,
      task.role,
      task.status,
      task.currentTask,
      task.outputSummary,
      task.provenance,
      task.executedAt,
      task.nextScheduledAt,
      task.details ? JSON.stringify(task.details) : null
    );
    return Number(info.lastInsertRowid);
  }

  public getLatestAgentRoster(tenantId: string): AgentTaskExecution[] {
    const stmt = this.db.prepare(`
      SELECT * FROM agent_task_executions
      WHERE tenant_id = ?
      GROUP BY agent_id
      HAVING id = MAX(id)
      ORDER BY agent_id ASC
    `);
    const rows = stmt.all(tenantId) as any[];
    return rows.map(r => ({
      id: r.id,
      taskId: r.task_id,
      tenantId: r.tenant_id,
      agentId: r.agent_id,
      agentName: r.agent_name,
      role: r.role,
      status: r.status,
      currentTask: r.current_task,
      outputSummary: r.output_summary,
      provenance: r.provenance,
      executedAt: r.executed_at,
      nextScheduledAt: r.next_scheduled_at,
      details: r.details_json ? JSON.parse(r.details_json) : undefined
    }));
  }

  public close(): void {
    this.db.close();
  }
}

