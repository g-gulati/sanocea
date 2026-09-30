/**
 * SANOCEA SEO Stack — LIVE SERP RANK MOVEMENT (separate capability from GSC average position)
 *
 * Exact keyword positions from a SERP data source: Start Rank -> Previous Rank -> Current Rank, daily and net delta.
 *
 * Truth rules:
 * - This is NOT GSC average position, and nothing here is ever derived from it. GSC has its own series and panel.
 * - Only observations written by a provider listed in VERIFIED_SERP_PROVIDERS are ever displayed. That set is
 *   EMPTY today: no compliant zero-cost source supplies exact per-query positions (Google's Custom Search JSON API is
 *   closed to new customers; scraping google.com breaches its terms; paid SERP APIs are excluded by policy). A row in
 *   `serp_rank_observations` from any other provider name (a seed script, a test fixture, a typo) is counted as
 *   "ignored" and never shown as a rank. Provider names are not trusted evidence; the allowlist is.
 * - Adding a provider means adding an adapter AND verifying it live AND then adding its name here in the same change.
 * - With no verified provider (or no observation from one) the capability is NOT_AVAILABLE with the exact dependency.
 * - Ranks >100 stay `null` (">100"); they are never converted into an invented number.
 */

import { SeoDatabase } from '../persistence/seoDb.js';
import { SerpObservation, SerpTrajectory } from './serpTypes.js';
import { SerpTrajectoryEngine } from './serpTrajectoryEngine.js';

export const LIVE_SERP_CAPABILITY = 'LIVE SERP RANK MOVEMENT' as const;
export const LIVE_SERP_PROVENANCE = '[OBSERVED: SERP PROVIDER]' as const;

/** Providers with a verified-live adapter in this codebase. Intentionally empty. */
export const VERIFIED_SERP_PROVIDERS: ReadonlySet<string> = new Set<string>();

export const LIVE_SERP_DEPENDENCY =
  'Requires a SERP data source that returns exact organic positions per query, device and location. No compliant zero-cost source exists ' +
  '(Google Custom Search JSON API is closed to new customers; scraping google.com breaches its terms; paid SERP APIs are excluded by policy). ' +
  'This capability becomes available only when a verified provider adapter is added.';

export interface LiveSerpRankRow {
  query: string;
  startRank: number | null;
  previousRank: number | null;
  currentRank: number | null;
  startRankFormatted: string;
  previousRankFormatted: string;
  currentRankFormatted: string;
  dailyDelta: number | null;
  dailyDeltaFormatted: string;
  netDelta: number | null;
  netDeltaFormatted: string;
  firstObservedAt: string;
  lastCheckedAt: string;
  observationCount: number;
  provider: string;
  methodology: string;
  provenance: typeof LIVE_SERP_PROVENANCE;
}

export interface LiveSerpRankMovement {
  capability: typeof LIVE_SERP_CAPABILITY;
  status: 'OBSERVED' | 'NOT_AVAILABLE';
  provenance: typeof LIVE_SERP_PROVENANCE | '[NOT AVAILABLE]';
  verifiedProviders: string[];
  rows: LiveSerpRankRow[];
  /** Stored rows from providers that are not verified. They are never displayed as ranks. */
  ignoredRowCount: number;
  reason: string | null;
  dependency: string | null;
}

export function verifiedSerpObservations(db: SeoDatabase, tenantId: string, verified: ReadonlySet<string> = VERIFIED_SERP_PROVIDERS): { rows: SerpObservation[]; ignored: number } {
  const all = db.getSerpObservations(tenantId);
  const rows = all.filter(o => verified.has(o.provider));
  return { rows, ignored: all.length - rows.length };
}

function groupKey(o: SerpObservation): string {
  return [o.query, o.device, o.geography, o.language, o.provider, o.serpType].join('\u0001');
}

/** Trajectories computed only from verified-provider observations, one per (query, device, geo, language, provider). */
export function verifiedSerpTrajectories(db: SeoDatabase, tenantId: string, verified: ReadonlySet<string> = VERIFIED_SERP_PROVIDERS): SerpTrajectory[] {
  const groups = new Map<string, SerpObservation[]>();
  for (const o of verifiedSerpObservations(db, tenantId, verified).rows) {
    const list = groups.get(groupKey(o)) ?? [];
    list.push(o);
    groups.set(groupKey(o), list);
  }
  return [...groups.values()]
    .map(list => SerpTrajectoryEngine.computeTrajectory(list.sort((a, b) => a.timestamp.localeCompare(b.timestamp))))
    .filter((t): t is SerpTrajectory => t !== null);
}

export function buildLiveSerpRankMovement(db: SeoDatabase, tenantId: string, verified: ReadonlySet<string> = VERIFIED_SERP_PROVIDERS): LiveSerpRankMovement {
  const { ignored } = verifiedSerpObservations(db, tenantId, verified);
  const trajectories = verifiedSerpTrajectories(db, tenantId, verified);
  const rows: LiveSerpRankRow[] = trajectories.map(t => ({
    query: t.query,
    startRank: t.baselineRank,
    previousRank: t.previousRank,
    currentRank: t.currentRank,
    startRankFormatted: t.startRankFormatted,
    previousRankFormatted: t.previousRankFormatted,
    currentRankFormatted: t.currentRankFormatted,
    dailyDelta: t.dailyDelta,
    dailyDeltaFormatted: t.dailyDeltaFormatted,
    netDelta: t.cumulativeDelta,
    netDeltaFormatted: t.cumulativeDeltaFormatted,
    firstObservedAt: t.baselineObservation.timestamp,
    lastCheckedAt: t.currentObservation.timestamp,
    observationCount: t.observationCount,
    provider: t.provider,
    methodology: `${t.provider} organic SERP position · device ${t.device} · geography ${t.geography} · language ${t.language}`,
    provenance: LIVE_SERP_PROVENANCE
  }));

  if (rows.length === 0) {
    return {
      capability: LIVE_SERP_CAPABILITY, status: 'NOT_AVAILABLE', provenance: '[NOT AVAILABLE]',
      verifiedProviders: [...verified], rows: [], ignoredRowCount: ignored,
      reason: verified.size === 0
        ? 'No verified SERP provider is connected, so no exact keyword position has been observed.'
        : 'A verified SERP provider is connected but has produced no observation for this tenant yet.',
      dependency: LIVE_SERP_DEPENDENCY
    };
  }
  return { capability: LIVE_SERP_CAPABILITY, status: 'OBSERVED', provenance: LIVE_SERP_PROVENANCE, verifiedProviders: [...verified], rows, ignoredRowCount: ignored, reason: null, dependency: null };
}
