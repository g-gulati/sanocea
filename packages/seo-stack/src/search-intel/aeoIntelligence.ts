/**
 * SANOCEA SEO Stack — AEO (Answer Engine Optimization) Intelligence Engine
 *
 * Truth rules:
 * - Featured Snippet / PAA / AI Overview state exists only when a SERP provider returned it.
 * - Ownership is derived strictly from provider-returned evidence (owner / cited domains); never inferred.
 * - With no provider configured, or on any provider failure, the query is reported as ProviderUnavailable
 *   and NOTHING is persisted. Absent != false.
 * - No mock provider lives in this module; test doubles live under tests/.
 *
 * A production SERP adapter is deliberately not wired: no compliant zero-cost source exists. Until one is
 * implemented and verified against the live API this capability is fail-closed (RED).
 */

import { AeoObservation, AeoSummary, ProviderUnavailable, isProviderUnavailable } from './rankCommandTypes.js';
import { SeoDatabase } from '../persistence/seoDb.js';

export interface AeoSerpProvider {
  name: string;
  fetchSerpFeatures(tenantId: string, query: string, targetDomain: string): Promise<AeoObservation | ProviderUnavailable>;
}

/** Default production provider until a real SERP adapter is connected. Always fails closed. */
export class UnconfiguredAeoProvider implements AeoSerpProvider {
  public readonly name = 'UNCONFIGURED_SERP_PROVIDER';
  constructor(private reason = 'No SERP provider adapter is connected for featured snippet / PAA / AI Overview data') {}
  public async fetchSerpFeatures(): Promise<ProviderUnavailable> {
    return { available: false, provider: this.name, reason: this.reason, timestamp: new Date().toISOString() };
  }
}

export function domainMatches(candidate: string | null | undefined, targetDomain: string): boolean {
  if (!candidate) return false;
  const clean = (d: string) => d.toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0];
  const target = clean(targetDomain);
  const c = clean(candidate);
  return c === target || c.endsWith('.' + target);
}

export class AeoIntelligenceEngine {
  constructor(private provider: AeoSerpProvider, private db?: SeoDatabase) {}

  public setProvider(provider: AeoSerpProvider): void {
    this.provider = provider;
  }

  public async trackQueries(tenantId: string, queries: string[], targetDomain: string): Promise<AeoSummary> {
    const observations: AeoObservation[] = [];
    const unavailable: ProviderUnavailable[] = [];

    for (const q of queries) {
      let result: AeoObservation | ProviderUnavailable;
      try {
        result = await this.provider.fetchSerpFeatures(tenantId, q, targetDomain);
      } catch (err: any) {
        result = { available: false, provider: this.provider.name, reason: err?.message ?? String(err), timestamp: new Date().toISOString() };
      }
      if (isProviderUnavailable(result)) {
        unavailable.push(result);
        continue;
      }
      result.tenantId = tenantId;
      observations.push(result);
      this.db?.recordAeoObservation(result);
    }
    return AeoIntelligenceEngine.buildSummary(tenantId, observations, unavailable);
  }

  /** Summary from persisted observations only (no provider call). */
  public latestSummary(tenantId: string, queries: string[]): AeoSummary {
    const set = new Set(queries.map(q => q.toLowerCase()));
    const rows = (this.db ? this.db.getLatestAeoObservations(tenantId) : []).filter(o => set.has(o.query.toLowerCase()));
    const missing = queries.length - rows.length;
    const unavailable: ProviderUnavailable[] = missing > 0
      ? [{ available: false, provider: this.provider.name, reason: `${missing} tracked queries have no persisted observation`, timestamp: new Date().toISOString() }]
      : [];
    return AeoIntelligenceEngine.buildSummary(tenantId, rows, unavailable);
  }

  private static buildSummary(tenantId: string, obs: AeoObservation[], unavailable: ProviderUnavailable[]): AeoSummary {
    const n = obs.length;
    const snippetOwned = obs.filter(o => o.isFeaturedSnippetOwned).length;
    const aiOverviews = obs.filter(o => o.hasAiOverview).length;
    const aiOwned = obs.filter(o => o.isAiOverviewOwned).length;
    const stamps = obs.map(o => o.timestamp).sort();
    return {
      tenantId,
      totalQueriesTracked: n + unavailable.length,
      featuredSnippetCaptureCount: snippetOwned,
      featuredSnippetCaptureRate: n > 0 ? Math.round((snippetOwned / n) * 1000) / 10 : null,
      paaOpportunityCount: obs.filter(o => o.hasPeopleAlsoAsk && o.paaQuestions.length > 0).length,
      aiOverviewCoverageCount: aiOverviews,
      aiOverviewOwnershipRate: aiOverviews > 0 ? Math.round((aiOwned / aiOverviews) * 1000) / 10 : null,
      observations: obs,
      unavailable,
      provenance: n > 0 ? '[CALCULATED: SERP OBSERVATIONS]' : '[NOT AVAILABLE]',
      lastObservedAt: stamps.length ? stamps[stamps.length - 1] : null
    };
  }
}
