/**
 * SANOCEA SEO Stack — GEO (Generative Engine Optimization) Citation Engine
 *
 * Truth rules:
 * - A citation (or a confirmed non-citation) exists only when a real provider/API answered for that
 *   query + engine. Position/rank is recorded only if the provider returned one.
 * - With no provider configured, or on any failure, the pair is reported as ProviderUnavailable and
 *   NOTHING is persisted. "Not checked" is never stored as "not cited".
 * - No mock provider lives in this module; test doubles live under tests/.
 *
 * A production adapter (LLM-answer / AI-visibility API) is deliberately not wired yet: until one is
 * implemented and verified against the live API this capability is fail-closed (RED).
 */

import { GeoCitationObservation, GeoSummary, GeoEngine, ProviderUnavailable, isProviderUnavailable } from './rankCommandTypes.js';
import { SeoDatabase } from '../persistence/seoDb.js';

export interface GeoCitationProvider {
  name: string;
  checkQueryCitations(tenantId: string, query: string, targetDomain: string, engine: GeoEngine): Promise<GeoCitationObservation | ProviderUnavailable>;
}

/** Default production provider until a real citation source is connected. Always fails closed. */
export class UnconfiguredGeoProvider implements GeoCitationProvider {
  public readonly name = 'UNCONFIGURED_GEO_PROVIDER';
  constructor(private reason = 'No AI-citation provider is connected (requires DataForSEO AI Optimization or direct LLM search API credentials)') {}
  public async checkQueryCitations(): Promise<ProviderUnavailable> {
    return { available: false, provider: this.name, reason: this.reason, timestamp: new Date().toISOString() };
  }
}

export const DEFAULT_GEO_ENGINES: GeoEngine[] = ['PERPLEXITY', 'CHATGPT_SEARCH', 'GOOGLE_AI_OVERVIEW'];

export class GeoCitationEngine {
  constructor(private provider: GeoCitationProvider, private db?: SeoDatabase) {}

  public setProvider(provider: GeoCitationProvider): void {
    this.provider = provider;
  }

  public async pollCitations(tenantId: string, queries: string[], targetDomain: string, engines: GeoEngine[] = DEFAULT_GEO_ENGINES): Promise<GeoSummary> {
    const observations: GeoCitationObservation[] = [];
    const unavailable: ProviderUnavailable[] = [];

    for (const q of queries) {
      for (const eng of engines) {
        let result: GeoCitationObservation | ProviderUnavailable;
        try {
          result = await this.provider.checkQueryCitations(tenantId, q, targetDomain, eng);
        } catch (err: any) {
          result = { available: false, provider: this.provider.name, reason: err?.message ?? String(err), timestamp: new Date().toISOString() };
        }
        if (isProviderUnavailable(result)) {
          unavailable.push(result);
          continue;
        }
        result.tenantId = tenantId;
        observations.push(result);
        this.db?.recordGeoCitation(result);
      }
    }
    return GeoCitationEngine.buildSummary(tenantId, queries.length, engines, observations, unavailable);
  }

  /** Summary from persisted observations only (no provider call). Latest observation per query+engine. */
  public latestSummary(tenantId: string, queries: string[], engines: GeoEngine[] = DEFAULT_GEO_ENGINES): GeoSummary {
    const set = new Set(queries.map(q => q.toLowerCase()));
    const seen = new Set<string>();
    const rows: GeoCitationObservation[] = [];
    for (const o of this.db ? this.db.getGeoCitationsForTenant(tenantId) : []) { // newest first
      const key = `${o.query.toLowerCase()}|${o.engine}`;
      if (set.has(o.query.toLowerCase()) && engines.includes(o.engine) && !seen.has(key)) {
        seen.add(key);
        rows.push(o);
      }
    }
    const missing = queries.length * engines.length - rows.length;
    const unavailable: ProviderUnavailable[] = missing > 0
      ? [{ available: false, provider: this.provider.name, reason: `${missing} query/engine pairs have no persisted observation`, timestamp: new Date().toISOString() }]
      : [];
    return GeoCitationEngine.buildSummary(tenantId, queries.length, engines, rows, unavailable);
  }

  private static buildSummary(tenantId: string, queryCount: number, engines: GeoEngine[], obs: GeoCitationObservation[], unavailable: ProviderUnavailable[]): GeoSummary {
    const cited = obs.filter(o => o.isCited);
    const citationsByEngine: Record<string, number> = {};
    for (const e of engines) citationsByEngine[e] = obs.filter(o => o.engine === e && o.isCited).length;

    const pageCounts = new Map<string, number>();
    for (const o of cited) if (o.citedUrl) pageCounts.set(o.citedUrl, (pageCounts.get(o.citedUrl) ?? 0) + 1);

    const stamps = obs.map(o => o.timestamp).sort();
    return {
      tenantId,
      totalTrackedQueries: queryCount,
      totalCitationsObserved: cited.length,
      citationRatePercent: obs.length > 0 ? Math.round((cited.length / obs.length) * 1000) / 10 : null,
      citationsByEngine,
      topCitedPages: [...pageCounts.entries()].map(([url, count]) => ({ url, count })).sort((a, b) => b.count - a.count),
      observations: obs,
      unavailable,
      provenance: obs.length > 0 ? '[CALCULATED: GEO CITATION OBSERVATIONS]' : '[NOT AVAILABLE]',
      lastPolledAt: stamps.length ? stamps[stamps.length - 1] : null
    };
  }
}
