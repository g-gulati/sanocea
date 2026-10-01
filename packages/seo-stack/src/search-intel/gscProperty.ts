/**
 * SANOCEA SEO Stack — Google Search Console property state: connection, sitemaps, URL Inspection
 *
 * Extends the existing service-account integration (gscAuth.ts / gscClient.ts); it adds no credential and no
 * scope. Everything here is READ-ONLY against Google (sites.get, sitemaps.list, urlInspection.index.inspect, all
 * covered by the existing `webmasters.readonly` scope). Sitemap SUBMISSION is deliberately not implemented: it needs
 * the write scope and an explicit authorization decision, and lives in a separate change.
 *
 * Truth rules
 * - Connection state is what the last check observed, with its time; it is never assumed. NOT_CONNECTED means no
 *   live credential is configured (fixture/none), not a failure.
 * - URL Inspection values are stored exactly as Google returned them. Nothing is inferred from them here.
 * - Quota: URL Inspection is capped per run and a URL is not re-inspected within `minIntervalMs`.
 */

import { SeoDatabase } from '../persistence/seoDb.js';

export type ConnectionState = 'NOT_CONNECTED' | 'CONNECTING' | 'CONNECTED' | 'TOKEN_EXPIRED' | 'ERROR';
export const GSC_PROVIDER = 'GOOGLE_SEARCH_CONSOLE' as const;
export const GSC_SCOPE = 'https://www.googleapis.com/auth/webmasters.readonly';

/** The slice of GscAuthManager this module needs; lets tests supply a fake without credentials. */
export interface GscAuthLike {
  getAccessToken(): Promise<string | null>;
  verifyProperty(siteUrl: string): Promise<{ verified: boolean; permissionLevel: string; authMethod: string; errorMessage?: string }>;
}

export interface ConnectionRecord {
  provider: typeof GSC_PROVIDER; property: string; state: ConnectionState; authMethod: string;
  permissionLevel: string | null; scopes: string; lastCheckedAt: string; lastSuccessAt: string | null; lastError: string | null;
}
export interface SitemapRecord {
  path: string; type: string | null; isPending: boolean | null; isSitemapsIndex: boolean | null;
  lastSubmitted: string | null; lastDownloaded: string | null; warnings: number | null; errors: number | null; fetchedAt: string;
}
export interface InspectionRecord {
  url: string; inspectedAt: string; verdict: string | null; coverageState: string | null; indexingState: string | null;
  robotsTxtState: string | null; pageFetchState: string | null; lastCrawlTime: string | null;
  googleCanonical: string | null; userCanonical: string | null; crawledAs: string | null;
}

export class GscPropertyService {
  constructor(private db: SeoDatabase, private opts: { auth?: GscAuthLike; live: boolean; fetchImpl?: typeof fetch; timeoutMs?: number }) {}

  private get doFetch(): typeof fetch { return this.opts.fetchImpl ?? fetch; }

  public async refreshConnection(tenantId: string, siteUrl: string, now = new Date().toISOString()): Promise<ConnectionRecord> {
    const prev = this.getConnection(tenantId, siteUrl);
    let state: ConnectionState; let authMethod = 'NONE'; let permission: string | null = null; let error: string | null = null;
    if (!this.opts.live || !this.opts.auth) {
      state = 'NOT_CONNECTED'; error = 'No live Google credential is configured for this tenant';
    } else {
      const v = await this.opts.auth.verifyProperty(siteUrl);
      authMethod = v.authMethod;
      if (v.verified) { state = 'CONNECTED'; permission = v.permissionLevel; }
      else {
        permission = null; error = v.errorMessage ?? 'Property could not be verified';
        state = /HTTP 401|invalid_grant|token (expired|revoked)/i.test(error) ? 'TOKEN_EXPIRED' : 'ERROR';
      }
    }
    const rec: ConnectionRecord = { provider: GSC_PROVIDER, property: siteUrl, state, authMethod, permissionLevel: permission, scopes: GSC_SCOPE,
      lastCheckedAt: now, lastSuccessAt: state === 'CONNECTED' ? now : prev?.lastSuccessAt ?? null, lastError: error };
    this.db.handle.prepare(`INSERT INTO search_connections (tenant_id, provider, property, state, auth_method, permission_level, scopes, last_checked_at, last_success_at, last_error)
      VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id, provider, property) DO UPDATE SET state=excluded.state, auth_method=excluded.auth_method,
      permission_level=excluded.permission_level, scopes=excluded.scopes, last_checked_at=excluded.last_checked_at, last_success_at=excluded.last_success_at, last_error=excluded.last_error`)
      .run(tenantId, GSC_PROVIDER, siteUrl, state, authMethod, permission, GSC_SCOPE, now, rec.lastSuccessAt, error);
    return rec;
  }

  public getConnection(tenantId: string, siteUrl: string): ConnectionRecord | undefined {
    const r = this.db.handle.prepare(`SELECT * FROM search_connections WHERE tenant_id = ? AND provider = ? AND property = ?`).get(tenantId, GSC_PROVIDER, siteUrl) as any;
    return r ? { provider: GSC_PROVIDER, property: r.property, state: r.state, authMethod: r.auth_method, permissionLevel: r.permission_level, scopes: r.scopes,
      lastCheckedAt: r.last_checked_at, lastSuccessAt: r.last_success_at, lastError: r.last_error } : undefined;
  }

  /** sitemaps.list. Replaces the stored set for this property (a sitemap Google no longer lists is removed). */
  public async collectSitemaps(tenantId: string, siteUrl: string, now = new Date().toISOString()): Promise<{ status: 'OBSERVED' | 'NOT_AVAILABLE'; count: number; reason?: string }> {
    const token = await this.opts.auth?.getAccessToken();
    if (!token) return { status: 'NOT_AVAILABLE', count: 0, reason: 'No access token' };
    let res: Response;
    try {
      res = await this.doFetch(`https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(siteUrl)}/sitemaps`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(this.opts.timeoutMs ?? 20000) });
    } catch (e: any) { return { status: 'NOT_AVAILABLE', count: 0, reason: `network error: ${e?.name ?? 'unknown'}` }; }
    if (!res.ok) return { status: 'NOT_AVAILABLE', count: 0, reason: `Google API HTTP ${res.status}` };
    let body: any;
    try { body = await res.json(); } catch { return { status: 'NOT_AVAILABLE', count: 0, reason: 'response was not JSON' }; }
    if (body && typeof body === 'object' && body.sitemap !== undefined && !Array.isArray(body.sitemap)) return { status: 'NOT_AVAILABLE', count: 0, reason: 'unexpected response shape' };
    const list: any[] = body?.sitemap ?? []; // an absent key means "no sitemaps submitted", which is a real observation
    const num = (v: any) => (v === undefined || v === null ? null : Number(v));
    const tx = this.db.handle.transaction(() => {
      this.db.handle.prepare(`DELETE FROM gsc_sitemaps WHERE tenant_id = ? AND site_url = ?`).run(tenantId, siteUrl);
      const ins = this.db.handle.prepare(`INSERT INTO gsc_sitemaps (tenant_id, site_url, path, type, is_pending, is_sitemaps_index, last_submitted, last_downloaded, warnings, errors, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)`);
      for (const s of list) ins.run(tenantId, siteUrl, String(s.path), s.type ?? null, s.isPending === undefined ? null : Number(Boolean(s.isPending)), s.isSitemapsIndex === undefined ? null : Number(Boolean(s.isSitemapsIndex)), s.lastSubmitted ?? null, s.lastDownloaded ?? null, num(s.warnings), num(s.errors), now);
    });
    tx();
    return { status: 'OBSERVED', count: list.length };
  }

  public getSitemaps(tenantId: string, siteUrl: string): SitemapRecord[] {
    return (this.db.handle.prepare(`SELECT * FROM gsc_sitemaps WHERE tenant_id = ? AND site_url = ? ORDER BY path`).all(tenantId, siteUrl) as any[]).map(r => ({
      path: r.path, type: r.type, isPending: r.is_pending === null ? null : Boolean(r.is_pending), isSitemapsIndex: r.is_sitemaps_index === null ? null : Boolean(r.is_sitemaps_index),
      lastSubmitted: r.last_submitted, lastDownloaded: r.last_downloaded, warnings: r.warnings, errors: r.errors, fetchedAt: r.fetched_at }));
  }

  /** urlInspection.index.inspect for up to `max` URLs, skipping any inspected within `minIntervalMs`. Stops on quota (429). */
  public async inspectUrls(tenantId: string, siteUrl: string, urls: string[], opts: { max?: number; minIntervalMs?: number; now?: string } = {}): Promise<{ inspected: number; skipped: number; failed: Array<{ url: string; reason: string }>; stoppedOnQuota: boolean }> {
    const max = opts.max ?? 10; const minInterval = opts.minIntervalMs ?? 20 * 3600_000; const now = opts.now ?? new Date().toISOString();
    const out = { inspected: 0, skipped: 0, failed: [] as Array<{ url: string; reason: string }>, stoppedOnQuota: false };
    const token = await this.opts.auth?.getAccessToken();
    if (!token) { out.failed.push({ url: '*', reason: 'No access token' }); return out; }
    for (const url of [...new Set(urls)]) {
      if (out.inspected >= max) { out.skipped++; continue; }
      const last = this.latestInspection(tenantId, siteUrl, url);
      if (last && Date.parse(now) - Date.parse(last.inspectedAt) < minInterval) { out.skipped++; continue; }
      let res: Response;
      try {
        res = await this.doFetch('https://searchconsole.googleapis.com/v1/urlInspection/index:inspect', {
          method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ inspectionUrl: url, siteUrl, languageCode: 'en-US' }), signal: AbortSignal.timeout(this.opts.timeoutMs ?? 30000) });
      } catch (e: any) { out.failed.push({ url, reason: `network error: ${e?.name ?? 'unknown'}` }); continue; }
      if (res.status === 429) { out.stoppedOnQuota = true; out.failed.push({ url, reason: 'Google quota reached (HTTP 429)' }); break; }
      if (!res.ok) { out.failed.push({ url, reason: `Google API HTTP ${res.status}` }); continue; }
      let body: any;
      try { body = await res.json(); } catch { out.failed.push({ url, reason: 'response was not JSON' }); continue; }
      const idx = body?.inspectionResult?.indexStatusResult;
      if (!idx || typeof idx !== 'object') { out.failed.push({ url, reason: 'no indexStatusResult in response' }); continue; }
      this.db.handle.prepare(`INSERT INTO gsc_url_inspections (tenant_id, site_url, url, inspected_at, verdict, coverage_state, indexing_state, robots_txt_state, page_fetch_state, last_crawl_time, google_canonical, user_canonical, crawled_as)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(tenantId, siteUrl, url, now, idx.verdict ?? null, idx.coverageState ?? null, idx.indexingState ?? null, idx.robotsTxtState ?? null, idx.pageFetchState ?? null,
        idx.lastCrawlTime ?? null, idx.googleCanonical ?? null, idx.userCanonical ?? null, idx.crawledAs ?? null);
      out.inspected++;
    }
    return out;
  }

  private rowToInspection(r: any): InspectionRecord {
    return { url: r.url, inspectedAt: r.inspected_at, verdict: r.verdict, coverageState: r.coverage_state, indexingState: r.indexing_state, robotsTxtState: r.robots_txt_state,
      pageFetchState: r.page_fetch_state, lastCrawlTime: r.last_crawl_time, googleCanonical: r.google_canonical, userCanonical: r.user_canonical, crawledAs: r.crawled_as };
  }

  public latestInspection(tenantId: string, siteUrl: string, url: string): InspectionRecord | undefined {
    const r = this.db.handle.prepare(`SELECT * FROM gsc_url_inspections WHERE tenant_id = ? AND site_url = ? AND url = ? ORDER BY id DESC LIMIT 1`).get(tenantId, siteUrl, url);
    return r ? this.rowToInspection(r) : undefined;
  }

  public latestInspections(tenantId: string, siteUrl: string): InspectionRecord[] {
    return (this.db.handle.prepare(`SELECT * FROM gsc_url_inspections WHERE tenant_id = ? AND site_url = ? AND id IN (SELECT MAX(id) FROM gsc_url_inspections WHERE tenant_id = ? AND site_url = ? GROUP BY url) ORDER BY url`).all(tenantId, siteUrl, tenantId, siteUrl) as any[]).map(r => this.rowToInspection(r));
  }

  /** Persisted-only view for the API. Never calls Google. */
  public getState(tenantId: string, siteUrl: string) {
    const connection = this.getConnection(tenantId, siteUrl) ?? null;
    return {
      provider: GSC_PROVIDER, property: siteUrl,
      provenance: connection ? '[OBSERVED: GOOGLE SEARCH CONSOLE API]' : '[NOT AVAILABLE]',
      connection, sitemaps: this.getSitemaps(tenantId, siteUrl), inspections: this.latestInspections(tenantId, siteUrl),
      writeCapabilities: { sitemapSubmission: 'NOT ENABLED: requires the write scope and explicit authorization' }
    };
  }
}
