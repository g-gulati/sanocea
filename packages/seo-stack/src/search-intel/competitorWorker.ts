/**
 * SANOCEA SEO Stack — Recurring Competitor Intelligence Worker
 *
 * Truth rules:
 * - Sitemap intelligence is real: fetch -> parse -> persist URL set -> diff against the last SUCCESSFUL
 *   snapshot. POLL_OK only when fetch and parse genuinely succeeded; every failure is POLL_FAILED.
 * - First successful poll is a baseline (no "new URL" claims). A sitemap that parses to zero URLs is
 *   DEGRADED and never replaces the baseline (an empty parse must not read as "everything removed").
 * - Competitor ranks come only from an injected CompetitorRankProvider (live SERP data). With none,
 *   gaps are NOT AVAILABLE and are not persisted. Our own rank comes only from the persisted SERP ledger.
 * - Backlink / domain-authority data is NOT AVAILABLE until a backlink provider is connected.
 */

import { createHash, randomUUID } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import * as cheerio from 'cheerio';
import {
  CompetitorConfig,
  CompetitorSitemapObservation,
  CompetitorKeywordGap,
  CompetitiveIntelligenceReport,
  CompetitorBacklinkStatus,
  ProviderUnavailable,
  isProviderUnavailable
} from './rankCommandTypes.js';
import { SeoDatabase } from '../persistence/seoDb.js';

/** Configured competitor set (configuration, not observation). Sitemap URLs are unverified until polled. */
export const DEFAULT_COMPETITOR_ROSTER: CompetitorConfig[] = [
  { competitorId: 'comp-unicommerce', name: 'Unicommerce', domain: 'unicommerce.com', sitemapUrl: 'https://unicommerce.com/sitemap.xml', trackedRoutes: ['/solutions/inventory-management', '/marketplace-integrations', '/features'] },
  { competitorId: 'comp-increff', name: 'Increff', domain: 'increff.com', sitemapUrl: 'https://www.increff.com/sitemap.xml', trackedRoutes: ['/omni-channel-inventory-management', '/wms-fulfillment', '/pricing'] },
  { competitorId: 'comp-vinculum', name: 'Vinculum', domain: 'vinculumgroup.com', sitemapUrl: 'https://www.vinculumgroup.com/sitemap.xml', trackedRoutes: ['/vin-omni', '/vin-mdm', '/order-management'] },
  { competitorId: 'comp-browntape', name: 'Browntape', domain: 'browntape.com', sitemapUrl: 'https://browntape.com/sitemap.xml', trackedRoutes: ['/multi-channel-inventory-management', '/ecommerce-integrations'] }
];

export interface CompetitorRankResult {
  rank: number | null; // null = provider checked and the domain does not rank in scanned depth
  provider: string;
  observedAt: string;
}

/** Live SERP source for competitor positions (e.g. DataForSEO Labs ranked_keywords). Not wired yet. */
export interface CompetitorRankProvider {
  name: string;
  fetchCompetitorRank(tenantId: string, competitorDomain: string, query: string): Promise<CompetitorRankResult | ProviderUnavailable>;
}

export interface CompetitorEngineOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  maxChildSitemaps?: number;
  maxUrls?: number;
  rankProvider?: CompetitorRankProvider;
}

class SitemapError extends Error {
  constructor(message: string, public httpStatus: number | null = null) { super(message); }
}

export class CompetitorIntelligenceEngine {
  private competitors: CompetitorConfig[];
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private readonly maxChildSitemaps: number;
  private readonly maxUrls: number;
  private readonly rankProvider?: CompetitorRankProvider;

  constructor(competitors: CompetitorConfig[], private db?: SeoDatabase, opts: CompetitorEngineOptions = {}) {
    this.competitors = competitors.map(c => ({ ...c }));
    this.fetchImpl = opts.fetchImpl ?? fetch;
    this.timeoutMs = opts.timeoutMs ?? 20000;
    this.maxChildSitemaps = opts.maxChildSitemaps ?? 50;
    this.maxUrls = opts.maxUrls ?? 200000;
    this.rankProvider = opts.rankProvider;
  }

  public getCompetitors(): CompetitorConfig[] {
    return this.competitors.map(c => ({ ...c }));
  }

  public addCompetitor(comp: CompetitorConfig): void {
    this.competitors.push({ ...comp });
  }

  // ── Sitemap fetch / parse ──────────────────────────────────────────────────

  private async fetchXml(url: string): Promise<{ xml: string; status: number }> {
    let res: Response;
    try {
      res = await this.fetchImpl(url, {
        headers: { 'User-Agent': 'SanoceaSeoBot/1.0 (+https://www.sanocea.com)', Accept: 'application/xml,text/xml,*/*' },
        redirect: 'follow',
        signal: AbortSignal.timeout(this.timeoutMs)
      });
    } catch (err: any) {
      if (err?.name === 'TimeoutError' || err?.name === 'AbortError') throw new SitemapError(`timeout after ${this.timeoutMs}ms fetching ${url}`);
      throw new SitemapError(`network error fetching ${url}: ${err?.cause?.code ?? err?.message ?? err}`);
    }
    if (!res.ok) throw new SitemapError(`HTTP ${res.status} fetching ${url}`, res.status);
    let buf = Buffer.from(await res.arrayBuffer());
    if (buf.length > 2 && buf[0] === 0x1f && buf[1] === 0x8b) {
      try { buf = gunzipSync(buf); } catch { throw new SitemapError(`corrupt gzip sitemap ${url}`, res.status); }
    }
    return { xml: buf.toString('utf8'), status: res.status };
  }

  /** Strict-enough sitemap parse: root must be urlset|sitemapindex and properly closed. */
  private parseSitemap(xml: string, url: string): { kind: 'urlset' | 'index'; locs: string[] } {
    const text = xml.replace(/^﻿/, '').trim();
    const rootMatch = /<(urlset|sitemapindex)[\s>]/i.exec(text);
    if (!rootMatch) throw new SitemapError(`malformed sitemap XML (no urlset/sitemapindex root): ${url}`);
    const root = rootMatch[1].toLowerCase();
    // The root must be closed; only whitespace, XML comments and processing instructions may follow it
    // (Yoast, RankMath etc. append "<!-- XML Sitemap generated by ... -->").
    if (!new RegExp(`</${root}\\s*>(?:\\s|<!--[\\s\\S]*?-->|<\\?[\\s\\S]*?\\?>)*$`, 'i').test(text)) throw new SitemapError(`malformed sitemap XML (root <${root}> not closed / truncated): ${url}`);

    const $ = cheerio.load(text, { xmlMode: true });
    const selector = root === 'urlset' ? 'urlset > url > loc' : 'sitemapindex > sitemap > loc';
    const locs: string[] = [];
    $(selector).each((_, el) => {
      const v = $(el).text().trim();
      if (/^https?:\/\//i.test(v)) locs.push(v);
    });
    return { kind: root === 'urlset' ? 'urlset' : 'index', locs };
  }

  private async collectUrls(sitemapUrl: string, competitorDomain: string): Promise<{ urls: string[]; httpStatus: number }> {
    const root = await this.fetchXml(sitemapUrl);
    const parsed = this.parseSitemap(root.xml, sitemapUrl);
    if (parsed.kind === 'urlset') return { urls: [...new Set(parsed.locs)].sort(), httpStatus: root.status };

    if (parsed.locs.length > this.maxChildSitemaps) throw new SitemapError(`sitemap index lists ${parsed.locs.length} children (> ${this.maxChildSitemaps} limit)`, root.status);
    const all = new Set<string>();
    for (const child of parsed.locs) {
      const host = new URL(child).hostname.toLowerCase();
      const base = competitorDomain.toLowerCase().replace(/^www\./, '');
      if (host !== base && !host.endsWith('.' + base)) throw new SitemapError(`child sitemap host ${host} is outside ${competitorDomain}`, root.status);
      const { xml } = await this.fetchXml(child);
      const c = this.parseSitemap(xml, child);
      if (c.kind !== 'urlset') throw new SitemapError(`nested sitemap index not supported: ${child}`, root.status);
      for (const u of c.locs) all.add(u);
      if (all.size > this.maxUrls) throw new SitemapError(`sitemap exceeds ${this.maxUrls} URLs`, root.status);
    }
    return { urls: [...all].sort(), httpStatus: root.status };
  }

  private async pollOne(tenantId: string, comp: CompetitorConfig): Promise<CompetitorSitemapObservation> {
    const sitemapUrl = comp.sitemapUrl || `https://${comp.domain}/sitemap.xml`;
    const polledAt = new Date().toISOString();
    const observationId = `comp-poll-${comp.competitorId}-${randomUUID()}`;
    const base = { observationId, tenantId, competitorId: comp.competitorId, competitorDomain: comp.domain, sitemapUrl, polledAt };

    try {
      const { urls, httpStatus } = await this.collectUrls(sitemapUrl, comp.domain);

      if (urls.length === 0) {
        return { ...base, totalUrls: 0, newlyDiscoveredUrls: [], removedUrls: [], status: 'DEGRADED', httpStatus, diffedAgainstPrevious: false,
          error: 'sitemap parsed but contains zero URLs; previous baseline retained', provenance: '[OBSERVED: SITEMAP FETCH]' };
      }

      const prev = this.db?.getCompetitorSitemapSnapshot(tenantId, comp.competitorId, sitemapUrl);
      let added: string[] = [];
      let removed: string[] = [];
      if (prev) {
        const prevSet = new Set(prev.urls);
        const curSet = new Set(urls);
        added = urls.filter(u => !prevSet.has(u));
        removed = prev.urls.filter(u => !curSet.has(u));
      }
      const sha = createHash('sha256').update(urls.join('\n')).digest('hex');
      this.db?.saveCompetitorSitemapSnapshot(tenantId, comp.competitorId, sitemapUrl, { urls, observationId, contentSha256: sha, capturedAt: polledAt });

      return { ...base, totalUrls: urls.length, newlyDiscoveredUrls: added, removedUrls: removed, status: 'POLL_OK', httpStatus,
        diffedAgainstPrevious: Boolean(prev), error: null, provenance: '[OBSERVED: SITEMAP FETCH]',
        rawJson: JSON.stringify({ contentSha256: sha, baselineObservationId: prev?.observationId ?? null, baselineCapturedAt: prev?.capturedAt ?? null }) };
    } catch (err: any) {
      const httpStatus = err instanceof SitemapError ? err.httpStatus : null;
      return { ...base, totalUrls: 0, newlyDiscoveredUrls: [], removedUrls: [], status: 'POLL_FAILED', httpStatus, diffedAgainstPrevious: false,
        error: err?.message ?? String(err), provenance: '[NOT AVAILABLE]' };
    }
  }

  /** Polls every configured competitor. One competitor failing never aborts the rest. */
  public async pollCompetitorSitemaps(tenantId: string): Promise<CompetitorSitemapObservation[]> {
    const out: CompetitorSitemapObservation[] = [];
    for (const comp of this.competitors) {
      const obs = await this.pollOne(tenantId, comp);
      this.db?.recordCompetitorSitemapObservation(obs);
      out.push(obs);
    }
    return out;
  }

  // ── Keyword coverage ───────────────────────────────────────────────────────

  public async compareKeywordCoverage(tenantId: string, queries: string[]): Promise<{ gaps: CompetitorKeywordGap[]; unavailable: ProviderUnavailable[] }> {
    const gaps: CompetitorKeywordGap[] = [];
    const unavailable: ProviderUnavailable[] = [];

    if (!this.rankProvider) {
      unavailable.push({ available: false, provider: 'UNCONFIGURED_COMPETITOR_RANK_PROVIDER', timestamp: new Date().toISOString(),
        reason: 'No live SERP provider is connected for competitor rankings (requires DataForSEO Labs / SERP credentials)' });
      return { gaps, unavailable };
    }

    const ownRank = new Map<string, number | null>();
    for (const t of this.db ? this.db.getAllSerpTrajectories(tenantId) : []) ownRank.set(t.query.toLowerCase().trim(), t.currentRank);

    for (const comp of this.competitors) {
      for (const q of queries) {
        const key = q.toLowerCase().trim();
        let res: CompetitorRankResult | ProviderUnavailable;
        try {
          res = await this.rankProvider.fetchCompetitorRank(tenantId, comp.domain, q);
        } catch (err: any) {
          res = { available: false, provider: this.rankProvider.name, reason: err?.message ?? String(err), timestamp: new Date().toISOString() };
        }
        if (isProviderUnavailable(res)) { unavailable.push(res); continue; }

        const mine = ownRank.has(key) ? ownRank.get(key)! : null;
        let gapStatus: CompetitorKeywordGap['gapStatus'] = 'BOTH_UNRANKED';
        if (mine !== null && res.rank !== null) gapStatus = mine < res.rank ? 'SANOCEA_AHEAD' : 'COMPETITOR_AHEAD';
        else if (mine !== null) gapStatus = 'SANOCEA_AHEAD';
        else if (res.rank !== null) gapStatus = 'GAP_OPPORTUNITY';

        gaps.push({ tenantId, competitorId: comp.competitorId, competitorDomain: comp.domain, query: q, competitorRank: res.rank,
          sanoceaRank: mine, gapStatus, provenance: '[OBSERVED: SERP PROVIDER]', lastComparedAt: res.observedAt });
      }
    }
    if (gaps.length > 0) this.db?.recordCompetitorKeywordGaps(tenantId, gaps);
    return { gaps, unavailable };
  }

  public getBacklinkStatus(): CompetitorBacklinkStatus {
    return {
      status: 'NOT AVAILABLE',
      reason: 'Requires a backlink index API (DataForSEO Backlinks, Ahrefs or Moz). SANOCEA does not fabricate third-party domain authority or backlink counts.',
      providerRequired: 'DataForSEO Backlinks / Ahrefs / Moz API'
    };
  }

  public async generateReport(tenantId: string, queries: string[]): Promise<CompetitiveIntelligenceReport> {
    const sitemaps = await this.pollCompetitorSitemaps(tenantId);
    const { gaps, unavailable } = await this.compareKeywordCoverage(tenantId, queries);
    return this.assemble(tenantId, sitemaps, gaps, unavailable);
  }

  /** Report from persisted state only (no network). */
  public latestReport(tenantId: string): CompetitiveIntelligenceReport {
    const gaps = this.db ? this.db.getCompetitorKeywordGaps(tenantId) : [];
    return this.assemble(tenantId, this.db ? this.db.getLatestCompetitorSitemapObservations(tenantId) : [], gaps,
      gaps.length === 0 && !this.rankProvider ? [{ available: false, provider: 'UNCONFIGURED_COMPETITOR_RANK_PROVIDER', timestamp: new Date().toISOString(), reason: 'No live SERP provider is connected for competitor rankings' }] : []);
  }

  private assemble(tenantId: string, sitemaps: CompetitorSitemapObservation[], gaps: CompetitorKeywordGap[], unavailable: ProviderUnavailable[]): CompetitiveIntelligenceReport {
    return {
      tenantId,
      competitors: this.getCompetitors(),
      sitemapObservations: sitemaps,
      keywordGaps: gaps,
      keywordGapsStatus: gaps.length > 0 ? 'OBSERVED' : 'NOT_AVAILABLE',
      keywordGapsUnavailableReason: gaps.length > 0 ? null : (unavailable[0]?.reason ?? 'no gap observations persisted'),
      backlinkStatus: this.getBacklinkStatus(),
      lastUpdated: new Date().toISOString(),
      provenance: sitemaps.some(s => s.status === 'POLL_OK') ? '[OBSERVED: SITEMAP FETCH]' : '[NOT AVAILABLE]'
    };
  }
}
