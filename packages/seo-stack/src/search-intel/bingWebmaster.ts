/**
 * SANOCEA SEO Stack — Bing Webmaster Tools connector (own verified property only, free API key)
 *
 * Provides, for OUR OWN site: per-query average impression position + impressions + clicks per returned date bucket
 * (Bing does not hide low-volume queries the way GSC's anonymization does, so this can fill the query-level gap), and
 * inbound link counts per page. Requires only BING_WEBMASTER_API_KEY (generated in Bing Webmaster Tools; no payment).
 *
 * Truth rules:
 * - No key, HTTP failure, API error object, or an unrecognised response shape => ProviderUnavailable, nothing stored.
 * - Positions are Bing's own average positions [OBSERVED: BING WEBMASTER AVERAGE POSITION]; a separate series from GSC
 *   and from any SERP-provider rank. Bing's date granularity is stored exactly as returned.
 * - Link counts are Bing's inbound-link counts for pages of OUR site: own-site data only, never competitors.
 * - STATUS: run against the live API for sanocea.com (2026-10-01). Verified live: GetUserSites, GetUrlInfo and the
 *   envelope of every listed endpoint. Bing had no query/page/crawl/link/sitemap data yet for this newly verified site, so
 *   row-level shapes for those are NOT yet verified: they are stored raw (never reinterpreted), and rows we cannot parse
 *   are counted and disclosed rather than dropped silently.
 * - NOT AVAILABLE BY DESIGN: Bing's "AI Performance" (Copilot citations) report has no API; it is a dashboard CSV export.
 * - The API key travels in the query string (Bing's design); it is stripped from every error message we produce.
 */

import { SeoDatabase } from '../persistence/seoDb.js';
import { ProviderUnavailable } from './rankCommandTypes.js';
import { GscPositionTracker, GscPositionTrajectory } from './gscPositionTracker.js';

export const BING_POSITION_PROVENANCE = '[OBSERVED: BING WEBMASTER AVERAGE POSITION]' as const;
export const BING_CRAWL_PROVENANCE = '[OBSERVED: BING WEBMASTER CRAWL & INDEX DATA]' as const;
export const BING_LINKS_PROVENANCE = '[OBSERVED: BING WEBMASTER LINK COUNTS]' as const;
const BASE = 'https://ssl.bing.com/webmaster/api.svc/json';

/** Parses ASP.NET JSON dates: "/Date(1699920000000)/" or "/Date(1699920000000-0700)/". */
export function parseAspNetDate(v: unknown): string | null {
  const m = typeof v === 'string' ? /\/Date\((-?\d+)(?:[+-]\d{4})?\)\// .exec(v) : null;
  return m ? new Date(Number(m[1])).toISOString().split('T')[0] : null;
}

export interface BingCollectResult {
  status: 'OBSERVED' | 'NOT_AVAILABLE';
  positionRowsStored: number;
  linkRowsStored: number;
  /** Rows stored per extra endpoint (page stats, crawl stats, crawl issues, sitemaps, URL info). */
  extra: Record<string, number>;
  unavailable?: ProviderUnavailable;
  notes: string[];
}

export class BingWebmasterCollector {
  constructor(private db: SeoDatabase, private opts: { apiKey?: string; fetchImpl?: typeof fetch; timeoutMs?: number } = {}) {}

  public get configured(): boolean { return Boolean(this.key); }

  private get key(): string | undefined { return this.opts.apiKey ?? process.env.BING_WEBMASTER_API_KEY; }

  private async call(method: string, siteUrl: string, key: string, withSite = true, extra: Record<string, string> = {}): Promise<any> {
    const url = `${BASE}/${method}?apikey=${encodeURIComponent(key)}${withSite ? `&siteUrl=${encodeURIComponent(siteUrl)}` : ''}${Object.entries(extra).map(([k, v]) => `&${k}=${encodeURIComponent(v)}`).join('')}`;
    let res: Response;
    try {
      res = await (this.opts.fetchImpl ?? fetch)(url, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(this.opts.timeoutMs ?? 30000) });
    } catch (err: any) {
      throw new Error(err?.name === 'TimeoutError' ? `${method}: timeout` : `${method}: network error ${err?.cause?.code ?? ''}`.trim());
    }
    if (!res.ok) throw new Error(`${method}: HTTP ${res.status}`);
    let json: any;
    try { json = await res.json(); } catch { throw new Error(`${method}: response was not JSON`); }
    if (json && typeof json === 'object' && ('ErrorCode' in json || 'Message' in json) && !('d' in json)) throw new Error(`${method}: API error ${json.ErrorCode ?? ''} ${String(json.Message ?? '').replace(key, '***')}`.trim());
    return json;
  }

  /** Finds the verified Bing property that matches our domain (www or apex) so the host spelling is never assumed. */
  public async resolveSite(domain: string): Promise<{ siteUrl: string | null; sites: string[] }> {
    const key = this.key;
    if (!key) return { siteUrl: null, sites: [] };
    const bare = domain.replace(/^www\./, '').toLowerCase();
    const j = await this.call('GetUserSites', '', key, false);
    if (!Array.isArray(j?.d)) throw new Error('GetUserSites: unexpected response shape (no "d" array)');
    const sites = j.d.filter((x: any) => x?.IsVerified === true && typeof x?.Url === 'string').map((x: any) => x.Url as string);
    const match = sites.filter((u: string) => { try { return new URL(u).hostname.replace(/^www\./, '').toLowerCase() === bare; } catch { return false; } });
    return { siteUrl: match.find((u: string) => !new URL(u).hostname.startsWith('www.')) ?? match[0] ?? null, sites };
  }

  public async collect(tenantId: string, siteUrl: string, urls: string[] = []): Promise<BingCollectResult> {
    const key = this.key;
    const na = (reason: string, notes: string[] = []): BingCollectResult => ({ status: 'NOT_AVAILABLE', positionRowsStored: 0, linkRowsStored: 0, extra: {}, notes,
      unavailable: { available: false, provider: 'BING_WEBMASTER_API', reason, timestamp: new Date().toISOString() } });
    if (!key) return na('BING_WEBMASTER_API_KEY is not configured');

    const fetchedAt = new Date().toISOString();
    const notes: string[] = [];
    let positionRows = 0;
    let linkRows = 0;
    const errors: string[] = [];

    try {
      const qs = await this.call('GetQueryStats', siteUrl, key);
      if (!Array.isArray(qs?.d)) throw new Error('GetQueryStats: unexpected response shape (no "d" array)');
      const rows = [];
      for (const r of qs.d) {
        const date = parseAspNetDate(r?.Date);
        const position = typeof r?.AvgImpressionPosition === 'number' ? r.AvgImpressionPosition : NaN;
        if (!date || typeof r?.Query !== 'string' || !Number.isFinite(position) || position <= 0 || !(r?.Impressions > 0)) continue; // no impressions/position = gap
        rows.push({ tenantId, siteUrl, key: r.Query, observedDate: date, position, impressions: r.Impressions, clicks: Number(r.Clicks) || 0, fetchedAt });
      }
      this.db.upsertBingPositionObservations(rows);
      positionRows = rows.length;
      if (rows.length === 0) notes.push('Bing returned no query rows with impressions and a position');
    } catch (e: any) { errors.push(String(e.message).replace(key, '***')); }

    try {
      const lc = await this.call('GetLinkCounts', siteUrl, key);
      const list = lc?.d?.Links ?? lc?.d?.Details;
      if (!Array.isArray(list)) throw new Error('GetLinkCounts: unexpected response shape (no Links/Details array)');
      const rows = list.filter((l: any) => typeof l?.Url === 'string' && Number.isFinite(l?.Count)).map((l: any) => ({ tenantId, siteUrl, pageUrl: l.Url, inboundLinks: l.Count, fetchedAt }));
      this.db.recordBingLinkCounts(rows);
      linkRows = rows.length;
    } catch (e: any) { errors.push(String(e.message).replace(key, '***')); }

    // Additional official endpoints. Each is stored as returned; an endpoint that answers with a recognised (even empty) list counts as answered.
    const extra: Record<string, number> = {};
    let answered = 2 - errors.length; // the two core endpoints above: answered unless they errored
    const snapshot = async (kind: string, method: string, keyOf: (r: any) => string | null, replace: boolean, params: Record<string, string> = {}) => {
      try {
        const j = await this.call(method, siteUrl, key, true, params);
        if (!Array.isArray(j?.d)) throw new Error(`${method}: unexpected response shape (no "d" array)`);
        const rows = j.d.map((r: any) => ({ key: keyOf(r), payload: r })).filter((r: any): r is { key: string; payload: any } => typeof r.key === 'string' && r.key.length > 0);
        if (rows.length < j.d.length) notes.push(`${method}: ${j.d.length - rows.length} of ${j.d.length} rows had no usable key and were not stored`);
        this.db.storeBingRaw(tenantId, siteUrl, kind, rows, fetchedAt, replace);
        extra[kind] = rows.length; answered++;
      } catch (e: any) { errors.push(String(e.message).replace(key, '***')); }
    };
    const dateKey = (r: any) => parseAspNetDate(r?.Date);
    await snapshot('PAGE_STATS', 'GetPageStats', r => (typeof r?.Query === 'string' && dateKey(r) ? `${r.Query}|${dateKey(r)}` : null), false);
    await snapshot('CRAWL_STATS', 'GetCrawlStats', dateKey, false);
    await snapshot('CRAWL_ISSUE', 'GetCrawlIssues', r => (typeof r?.Url === 'string' ? r.Url : null), true);
    await snapshot('FEED', 'GetFeeds', r => (typeof r?.Url === 'string' ? r.Url : null), true);

    // Index details (discovery / last-crawled) for the site root and the URLs we know about; capped.
    const infoRows: Array<{ key: string; payload: any }> = [];
    for (const u of [...new Set([siteUrl, ...urls])].slice(0, 50)) {
      try {
        const j = await this.call('GetUrlInfo', siteUrl, key, true, { url: u });
        if (j?.d && typeof j.d === 'object' && typeof j.d.Url === 'string') infoRows.push({ key: j.d.Url, payload: j.d });
        else throw new Error('GetUrlInfo: unexpected response shape');
      } catch (e: any) { errors.push(String(e.message).replace(key, '***')); break; }
    }
    if (infoRows.length) { this.db.storeBingRaw(tenantId, siteUrl, 'URL_INFO', infoRows, fetchedAt, true); extra.URL_INFO = infoRows.length; answered++; }

    if (answered <= 0) return na(errors.join('; ') || 'no endpoint returned a recognised response', notes);
    if (errors.length) notes.push(...errors.map(e => `partial: ${e}`));
    const stored = positionRows + linkRows + Object.values(extra).reduce((a, b) => a + b, 0);
    if (stored === 0) notes.push('Bing answered but holds no data for this property yet');
    return { status: 'OBSERVED', positionRowsStored: positionRows, linkRowsStored: linkRows, extra, notes };
  }

  /** Persisted-only. */
  public trajectories(tenantId: string, siteUrl: string): GscPositionTrajectory[] {
    const by = new Map<string, ReturnType<SeoDatabase['getBingPositionObservations']>>();
    for (const o of this.db.getBingPositionObservations(tenantId, siteUrl)) { const l = by.get(o.key) ?? []; l.push(o); by.set(o.key, l); }
    return [...by.entries()].map(([k, l]) => GscPositionTracker.computeTrajectory(tenantId, siteUrl, 'QUERY', k, l, BING_POSITION_PROVENANCE)!)
      .sort((a, b) => b.current.impressions - a.current.impressions);
  }

  public linkCounts(tenantId: string, siteUrl: string) {
    const rows = this.db.getLatestBingLinkCounts(tenantId, siteUrl);
    return { provenance: rows.length ? BING_LINKS_PROVENANCE : '[NOT AVAILABLE]', scope: 'inbound links to pages of our own site only', rows };
  }

  /** Persisted-only crawl/index/sitemap evidence. */
  public crawlReport(tenantId: string, siteUrl: string) {
    const get = (k: string) => this.db.getBingRaw(tenantId, siteUrl, k);
    const [pages, crawl, issues, feeds, info] = ['PAGE_STATS', 'CRAWL_STATS', 'CRAWL_ISSUE', 'FEED', 'URL_INFO'].map(get);
    const any = pages.length + crawl.length + issues.length + feeds.length + info.length;
    return {
      provenance: any ? BING_CRAWL_PROVENANCE : '[NOT AVAILABLE]',
      note: any ? 'Rows are shown as Bing returned them.' : 'Bing has returned no page, crawl, issue, sitemap or URL data for this property yet.',
      aiPerformance: { available: false, reason: 'Bing AI Performance (Copilot citations) has no API; it is only a Bing Webmaster Tools dashboard report with CSV export.' },
      pageStats: pages.map(r => r.payload), crawlStats: crawl.map(r => r.payload), crawlIssues: issues.map(r => r.payload), sitemaps: feeds.map(r => r.payload),
      urlInfo: info.map(r => ({ ...r.payload, DiscoveryDate: parseAspNetDate(r.payload.DiscoveryDate), LastCrawledDate: parseAspNetDate(r.payload.LastCrawledDate) }))
    };
  }
}
