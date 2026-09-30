/**
 * SANOCEA SEO Stack — Keyword Intelligence & Provider Adapter Engine
 *
 * Truth rules:
 * - Volume / CPC / competition exist only when DataForSEO returned them ([OBSERVED: KEYWORD PROVIDER]).
 * - Missing credentials, HTTP/API failures and empty results fail closed to null metrics + [NOT AVAILABLE].
 * - `intent` and `cluster` are text heuristics ([INFERRED]), not provider data.
 * - Only OBSERVED rows are persisted, so a failed poll never overwrites the last real observation.
 * - No mock provider exists in this module; test doubles live under tests/.
 */

import { randomUUID } from 'node:crypto';
import {
  KeywordMetricObservation,
  KeywordClusterSummary,
  KeywordIntelligenceReport,
  KeywordIntent
} from './rankCommandTypes.js';
import { SeoDatabase } from '../persistence/seoDb.js';

export interface KeywordProviderOptions {
  geography?: string;
  language?: string;
}

export interface KeywordDataProvider {
  name: string;
  fetchKeywordMetrics(tenantId: string, queries: string[], options?: KeywordProviderOptions): Promise<KeywordMetricObservation[]>;
}

export interface DataForSeoAdapterOptions {
  login?: string;
  password?: string;
  baseUrl?: string;
  timeoutMs?: number;
  /** Injectable for HTTP-level fakes in tests. Defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

const DFS_LOCATIONS: Record<string, string> = { IN: 'India', US: 'United States', GB: 'United Kingdom', AE: 'United Arab Emirates' };
const DFS_LANGUAGES: Record<string, string> = { en: 'English', hi: 'Hindi' };

export class DataForSeoKeywordAdapter implements KeywordDataProvider {
  public readonly name = 'DATAFORSEO_LIVE';
  private readonly login?: string;
  private readonly password?: string;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: DataForSeoAdapterOptions = {}) {
    this.login = opts.login ?? process.env.DATAFORSEO_LOGIN;
    this.password = opts.password ?? process.env.DATAFORSEO_PASSWORD;
    this.baseUrl = opts.baseUrl ?? 'https://api.dataforseo.com';
    this.timeoutMs = opts.timeoutMs ?? 20000;
    this.fetchImpl = opts.fetchImpl ?? fetch;
  }

  public get isConfigured(): boolean {
    return Boolean(this.login && this.password);
  }

  private unavailable(tenantId: string, queries: string[], geo: string, lang: string, reason: string): KeywordMetricObservation[] {
    const timestamp = new Date().toISOString();
    return queries.map(q => ({
      observationId: `kwd-dfseo-na-${randomUUID()}`,
      tenantId,
      query: q,
      searchVolume: null,
      cpc: null,
      competition: null,
      intent: KeywordIntelligenceEngine.classifyIntent(q),
      cluster: KeywordIntelligenceEngine.assignCluster(q),
      geography: geo,
      language: lang,
      provider: this.name,
      provenance: '[NOT AVAILABLE]' as const,
      timestamp,
      rawJson: JSON.stringify({ error: reason })
    }));
  }

  public async fetchKeywordMetrics(tenantId: string, queries: string[], options?: KeywordProviderOptions): Promise<KeywordMetricObservation[]> {
    const geo = options?.geography || 'IN';
    const lang = options?.language || 'en';
    if (queries.length === 0) return [];

    if (!this.isConfigured) {
      return this.unavailable(tenantId, queries, geo, lang, 'DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not configured');
    }

    try {
      const auth = 'Basic ' + Buffer.from(`${this.login}:${this.password}`).toString('base64');
      const res = await this.fetchImpl(`${this.baseUrl}/v3/keywords_data/google_ads/search_volume/live`, {
        method: 'POST',
        headers: { Authorization: auth, 'Content-Type': 'application/json' },
        body: JSON.stringify([{
          location_name: DFS_LOCATIONS[geo] ?? geo,
          language_name: DFS_LANGUAGES[lang] ?? lang,
          keywords: queries
        }]),
        signal: AbortSignal.timeout(this.timeoutMs)
      });
      if (!res.ok) throw new Error(`DataForSEO HTTP ${res.status}`);

      const json = await res.json() as any;
      const task = json?.tasks?.[0];
      // DataForSEO reports task-level failures inside a 200 response; 20000 = Ok.
      if (json?.status_code !== 20000 || !task || task.status_code !== 20000) {
        throw new Error(`DataForSEO task error ${task?.status_code ?? json?.status_code}: ${task?.status_message ?? json?.status_message ?? 'unknown'}`);
      }
      const results: any[] = Array.isArray(task.result) ? task.result : [];
      const timestamp = new Date().toISOString();

      return queries.map(q => {
        const item = results.find(r => typeof r?.keyword === 'string' && r.keyword.toLowerCase() === q.toLowerCase());
        const volume = finiteOrNull(item?.search_volume);
        const cpc = finiteOrNull(item?.cpc);
        // Google Ads endpoint: `competition` is a LOW/MEDIUM/HIGH label, `competition_index` is 0-100.
        const idx = finiteOrNull(item?.competition_index);
        const competition = idx !== null ? idx / 100 : finiteOrNull(item?.competition);
        const observed = volume !== null;
        return {
          observationId: `kwd-dfseo-${randomUUID()}`,
          tenantId,
          query: q,
          searchVolume: volume,
          cpc,
          competition,
          intent: KeywordIntelligenceEngine.classifyIntent(q),
          cluster: KeywordIntelligenceEngine.assignCluster(q),
          geography: geo,
          language: lang,
          provider: this.name,
          provenance: observed ? '[OBSERVED: KEYWORD PROVIDER]' as const : '[NOT AVAILABLE]' as const,
          timestamp,
          rawJson: item ? JSON.stringify(item) : JSON.stringify({ error: 'provider returned no data for keyword' })
        };
      });
    } catch (err: any) {
      const reason = err?.name === 'TimeoutError' ? `timeout after ${this.timeoutMs}ms` : (err?.message ?? String(err));
      return this.unavailable(tenantId, queries, geo, lang, reason);
    }
  }
}

function finiteOrNull(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Zero-cost default: absolute volume / CPC / difficulty cannot be obtained without paid data, so report that. */
export class UnconfiguredKeywordProvider implements KeywordDataProvider {
  public readonly name = 'UNCONFIGURED_KEYWORD_PROVIDER';
  constructor(private reason = 'No keyword-volume source is connected: absolute search volume / CPC / difficulty are not available from any zero-cost compliant source') {}
  public async fetchKeywordMetrics(tenantId: string, queries: string[], options?: KeywordProviderOptions): Promise<KeywordMetricObservation[]> {
    const timestamp = new Date().toISOString();
    return queries.map(q => ({
      observationId: `kwd-na-${randomUUID()}`, tenantId, query: q, searchVolume: null, cpc: null, competition: null,
      intent: KeywordIntelligenceEngine.classifyIntent(q), cluster: KeywordIntelligenceEngine.assignCluster(q),
      geography: options?.geography || 'IN', language: options?.language || 'en', provider: this.name,
      provenance: '[NOT AVAILABLE]' as const, timestamp, rawJson: JSON.stringify({ error: this.reason })
    }));
  }
}

/**
 * Production provider selection. Paid providers are never selected implicitly: the DataForSEO adapter is used only
 * when SEO_KEYWORD_PROVIDER=dataforseo is set explicitly (it is not part of the zero-cost path).
 */
export function createKeywordProviderFromEnv(env: NodeJS.ProcessEnv = process.env): KeywordDataProvider {
  return env.SEO_KEYWORD_PROVIDER === 'dataforseo' ? new DataForSeoKeywordAdapter() : new UnconfiguredKeywordProvider();
}

export class KeywordIntelligenceEngine {
  constructor(private provider: KeywordDataProvider, private db?: SeoDatabase) {}

  public setProvider(provider: KeywordDataProvider): void {
    this.provider = provider;
  }

  /** [INFERRED] text heuristic. Ordered rules; first match wins. */
  public static classifyIntent(query: string): KeywordIntent {
    const q = query.toLowerCase();
    if (q.includes('sanocea') || q.includes('login') || /\bapp\b/.test(q)) return 'NAVIGATIONAL';
    if (q.includes('buy') || q.includes('price') || q.includes('sync') || q.includes('reconciliation') || q.includes('tool') || q.includes('software')) return 'TRANSACTIONAL';
    if (q.includes('automation') || q.includes('management') || q.includes('platform') || q.includes('enterprise') || q.includes('best')) return 'COMMERCIAL';
    if (q.includes('what is') || q.includes('how to') || q.includes('guide') || q.includes('definition')) return 'INFORMATIONAL';
    return 'UNKNOWN';
  }

  public static assignCluster(query: string): string {
    const q = query.toLowerCase();
    if (q.includes('drift') || q.includes('inventory') || q.includes('stock')) return 'Inventory & Stock Drift';
    if (q.includes('reconciliation') || q.includes('marketplace') || q.includes('settlement')) return 'Marketplace Exception & Reconciliation';
    if (q.includes('catalog') || q.includes('onboarding') || q.includes('enrichment')) return 'Catalog Onboarding & Enrichment';
    if (q.includes('automation') || q.includes('operations')) return 'eCommerce Operations Automation';
    return 'General eCommerce Strategy';
  }

  public async evaluateKeywords(tenantId: string, queries: string[]): Promise<KeywordIntelligenceReport> {
    const observations = await this.provider.fetchKeywordMetrics(tenantId, queries);
    for (const obs of observations) {
      // Tenant identity is the execution context's, whatever the provider stamped.
      obs.tenantId = tenantId;
      if (this.db && obs.provenance === '[OBSERVED: KEYWORD PROVIDER]') this.db.recordKeywordObservation(obs);
    }
    return KeywordIntelligenceEngine.buildReport(tenantId, this.provider.name, queries.length, observations);
  }

  /** Report from persisted observations only (no provider call, no cost). */
  public latestReport(tenantId: string, queries: string[]): KeywordIntelligenceReport {
    const persisted = this.db ? this.db.getLatestKeywordObservations(tenantId) : [];
    const set = new Set(queries.map(q => q.toLowerCase()));
    const rows = persisted.filter(o => set.has(o.query.toLowerCase()));
    return KeywordIntelligenceEngine.buildReport(tenantId, this.provider.name, queries.length, rows);
  }

  private static buildReport(tenantId: string, provider: string, tracked: number, observations: KeywordMetricObservation[]): KeywordIntelligenceReport {
    const clusterMap = new Map<string, KeywordMetricObservation[]>();
    for (const obs of observations) {
      const list = clusterMap.get(obs.cluster) ?? [];
      list.push(obs);
      clusterMap.set(obs.cluster, list);
    }

    const clusters: KeywordClusterSummary[] = [...clusterMap.entries()].map(([clusterName, items]) => {
      const observed = items.filter(i => i.searchVolume !== null);
      const diffs = items.filter(i => i.competition !== null).map(i => (i.competition as number) * 100);
      const commercial = items.filter(i => i.intent === 'COMMERCIAL' || i.intent === 'TRANSACTIONAL').length;
      return {
        clusterName,
        totalSearchVolume: observed.length ? observed.reduce((a, i) => a + (i.searchVolume as number), 0) : null,
        avgDifficulty: diffs.length ? Math.round(diffs.reduce((a, b) => a + b, 0) / diffs.length) : null,
        keywordsCount: items.length,
        commercialIntentRatio: Math.round((commercial / items.length) * 100) / 100, // [INFERRED] intent basis
        topQueries: items,
        provenance: observed.length ? '[OBSERVED: KEYWORD PROVIDER]' : '[NOT AVAILABLE]'
      };
    });

    const observed = observations.filter(o => o.searchVolume !== null);
    const stamps = observations.map(o => o.timestamp).sort();
    return {
      tenantId,
      provider,
      totalKeywordsTracked: tracked,
      observedKeywordsCount: observed.length,
      totalObservedVolume: observed.length ? observed.reduce((s, o) => s + (o.searchVolume as number), 0) : null,
      clusters,
      observations,
      lastObservedAt: stamps.length ? stamps[stamps.length - 1] : '',
      provenance: observed.length ? '[OBSERVED: KEYWORD PROVIDER]' : '[NOT AVAILABLE]'
    };
  }
}
