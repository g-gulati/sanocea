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
 * - STATUS: implemented against Microsoft's documented JSON endpoints and tested with HTTP fakes. It has NOT been run
 *   against the live API (no key on this host), so response-shape assumptions are unverified and fail closed.
 * - The API key travels in the query string (Bing's design); it is stripped from every error message we produce.
 */

import { SeoDatabase } from '../persistence/seoDb.js';
import { ProviderUnavailable } from './rankCommandTypes.js';
import { GscPositionTracker, GscPositionTrajectory } from './gscPositionTracker.js';

export const BING_POSITION_PROVENANCE = '[OBSERVED: BING WEBMASTER AVERAGE POSITION]' as const;
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
  unavailable?: ProviderUnavailable;
  notes: string[];
}

export class BingWebmasterCollector {
  constructor(private db: SeoDatabase, private opts: { apiKey?: string; fetchImpl?: typeof fetch; timeoutMs?: number } = {}) {}

  public get configured(): boolean { return Boolean(this.key); }

  private get key(): string | undefined { return this.opts.apiKey ?? process.env.BING_WEBMASTER_API_KEY; }

  private async call(method: string, siteUrl: string, key: string): Promise<any> {
    const url = `${BASE}/${method}?apikey=${encodeURIComponent(key)}&siteUrl=${encodeURIComponent(siteUrl)}`;
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

  public async collect(tenantId: string, siteUrl: string): Promise<BingCollectResult> {
    const key = this.key;
    const na = (reason: string, notes: string[] = []): BingCollectResult => ({ status: 'NOT_AVAILABLE', positionRowsStored: 0, linkRowsStored: 0, notes,
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

    if (positionRows + linkRows === 0 && errors.length === 2) return na(errors.join('; '));
    if (errors.length) notes.push(...errors.map(e => `partial: ${e}`));
    return { status: positionRows + linkRows > 0 ? 'OBSERVED' : 'NOT_AVAILABLE', positionRowsStored: positionRows, linkRowsStored: linkRows, notes,
      ...(positionRows + linkRows === 0 ? { unavailable: { available: false as const, provider: 'BING_WEBMASTER_API', reason: notes.join('; ') || 'no rows', timestamp: fetchedAt } } : {}) };
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
}
