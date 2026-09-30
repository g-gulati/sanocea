/**
 * SANOCEA SEO Stack — GSC Position Movement Tracker (Start → Previous → Current → Delta)
 *
 * The zero-cost, ToS-compliant rank signal: Google Search Console `date`, `page × date` and `query × date` rows for OUR
 * OWN property, fetched through the official API with the service account. No scraping, no paid provider.
 * Query-level rows are frequently EMPTY for small sites (GSC anonymizes low-volume queries); that level is then
 * reported NOT AVAILABLE rather than approximated from page or site data.
 *
 * Truth rules:
 * - Only rows returned by the live GSC API are stored. Fixture-mode clients are refused; API failures store nothing.
 * - "Position" is GSC's impression-weighted AVERAGE position for that query on that date. It is not a point-in-time
 *   SERP rank, so it lives in its own table/series and is labelled [OBSERVED: GSC AVERAGE POSITION], never merged
 *   with SERP-provider ranks.
 * - A date with no impressions has NO observation. It is never interpolated and never read as ">100".
 * - History starts at the first date GSC returned data for. Older dates fetched retroactively are real GSC data, and
 *   every row carries fetched_at so the retrieval time is never disguised as the observation time.
 * - Deltas use the sign convention "positive = moved up" (lower position number). Low-impression points are flagged.
 */

import { GscClient } from './gscClient.js';
import { SeoDatabase } from '../persistence/seoDb.js';
import { ProviderUnavailable } from './rankCommandTypes.js';

export const GSC_POSITION_PROVENANCE = '[OBSERVED: GSC AVERAGE POSITION]' as const;
export const LOW_SAMPLE_IMPRESSIONS = 5;

export interface GscPositionPoint { date: string; position: number; impressions: number; clicks: number; }

export type GscDimensionLevel = 'SITE' | 'PAGE' | 'QUERY';

export interface GscPositionTrajectory {
  tenantId: string;
  siteUrl: string;
  dimension: GscDimensionLevel;
  /** SITE: the property URL; PAGE: the page URL; QUERY: the query text. */
  key: string;
  observationDays: number;
  /** Every observed date (ascending). Dates without impressions are absent: they are gaps, not zeros. */
  points: GscPositionPoint[];
  start: GscPositionPoint;
  previous: GscPositionPoint | null;
  current: GscPositionPoint;
  /** previous.position - current.position; positive = improved. null when there is no previous observed date. */
  movementSincePrevious: number | null;
  /** start.position - current.position; positive = improved. null when start === current (first observation only). */
  movementSinceStart: number | null;
  /** Calendar days between previous and current observed dates (>1 means the days between had no impressions). */
  gapDaysSincePrevious: number | null;
  lowSample: boolean;
  startFormatted: string;
  previousFormatted: string;
  currentFormatted: string;
  movementFormatted: string;
  provenance: string;
  lastFetchedAt: string;
}

export interface GscPositionCollectResult {
  status: 'OBSERVED' | 'NOT_AVAILABLE';
  rowsStored: number;
  window: { startDate: string; endDate: string } | null;
  levels: Record<GscDimensionLevel, { rowsStored: number; keys: number; note: string | null }>;
  unavailable?: ProviderUnavailable;
}

const fmt = (p: GscPositionPoint) => `${p.position.toFixed(1)} (${p.impressions} impr, ${p.date})`;
const dayDiff = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
const isoDay = (d: Date) => d.toISOString().split('T')[0];

const LEVELS: Array<{ level: GscDimensionLevel; dims: Array<'query' | 'page' | 'date'> }> = [
  { level: 'SITE', dims: ['date'] },
  { level: 'PAGE', dims: ['page', 'date'] },
  { level: 'QUERY', dims: ['query', 'date'] }
];

export class GscPositionTracker {
  constructor(private db: SeoDatabase, private client: GscClient) {}

  /** Fetches [today-lookback, today-endLagDays] (GSC data lags ~2-3 days) and upserts real rows for each level. */
  public async collect(tenantId: string, siteUrl: string, opts: { lookbackDays?: number; endLagDays?: number; rowLimit?: number; maxPages?: number } = {}): Promise<GscPositionCollectResult> {
    const lookback = opts.lookbackDays ?? 90;
    const lag = opts.endLagDays ?? 3;
    const rowLimit = opts.rowLimit ?? 25000;
    const maxPages = opts.maxPages ?? 10;
    const now = Date.now();
    const window = { startDate: isoDay(new Date(now - lookback * 86400000)), endDate: isoDay(new Date(now - lag * 86400000)) };
    const empty = () => ({ SITE: { rowsStored: 0, keys: 0, note: null }, PAGE: { rowsStored: 0, keys: 0, note: null }, QUERY: { rowsStored: 0, keys: 0, note: null } }) as GscPositionCollectResult['levels'];
    const unavailable = (reason: string): GscPositionCollectResult => ({ status: 'NOT_AVAILABLE', rowsStored: 0, window: null, levels: empty(),
      unavailable: { available: false, provider: 'GSC_API', reason, timestamp: new Date().toISOString() } });

    if (this.client.isFixtureMode) return unavailable('GSC client is in fixture mode; fixture rows are not observations');

    const fetchedAt = new Date().toISOString();
    const levels = empty();
    let total = 0;
    try {
      for (const { level, dims } of LEVELS) {
        const rows: Parameters<SeoDatabase['upsertGscPositionObservations']>[0] = [];
        for (let page = 0; page < maxPages; page++) {
          const batch = await this.client.querySearchAnalytics({ siteUrl, dateRange: window, dimensions: dims, rowLimit, startRow: page * rowLimit });
          for (const r of batch) {
            const key = level === 'SITE' ? siteUrl : level === 'PAGE' ? r.page : r.query;
            // A row with zero impressions carries no position: it is a gap, not an observation.
            if (!key || !r.date || !Number.isFinite(r.position) || r.position <= 0 || !(r.impressions > 0)) continue;
            rows.push({ tenantId, siteUrl, dimension: level, key, observedDate: r.date, position: r.position, impressions: r.impressions, clicks: r.clicks, ctr: r.ctr, fetchedAt });
          }
          if (batch.length < rowLimit) break;
        }
        this.db.upsertGscPositionObservations(rows);
        levels[level] = { rowsStored: rows.length, keys: new Set(rows.map(r => r.key)).size,
          note: rows.length === 0 && level === 'QUERY' ? 'GSC returned no query-level rows (queries below its privacy threshold are anonymized and omitted); per-query position is NOT AVAILABLE' : rows.length === 0 ? 'GSC returned no rows with impressions in this window' : null };
        total += rows.length;
      }
    } catch (err: any) {
      return unavailable(err?.message ?? String(err));
    }
    return { status: total > 0 ? 'OBSERVED' : 'NOT_AVAILABLE', rowsStored: total, window, levels,
      ...(total === 0 ? { unavailable: { available: false as const, provider: 'GSC_API', reason: 'GSC returned no rows with impressions in this window', timestamp: fetchedAt } } : {}) };
  }

  public static computeTrajectory(tenantId: string, siteUrl: string, dimension: GscDimensionLevel, key: string,
    obs: Array<{ observedDate: string; position: number; impressions: number; clicks: number; fetchedAt: string }>,
    provenance: string = GSC_POSITION_PROVENANCE): GscPositionTrajectory | null {
    if (obs.length === 0) return null;
    const pts = [...obs].sort((a, b) => a.observedDate.localeCompare(b.observedDate));
    const toPt = (o: typeof pts[number]): GscPositionPoint => ({ date: o.observedDate, position: o.position, impressions: o.impressions, clicks: o.clicks });
    const start = toPt(pts[0]);
    const current = toPt(pts[pts.length - 1]);
    const previous = pts.length > 1 ? toPt(pts[pts.length - 2]) : null;
    const round = (n: number) => Math.round(n * 100) / 100;

    const movementSincePrevious = previous ? round(previous.position - current.position) : null;
    const movementSinceStart = pts.length > 1 ? round(start.position - current.position) : null;
    let movementFormatted = 'N/A — first observation';
    if (movementSinceStart !== null) {
      const s = movementSinceStart;
      movementFormatted = s > 0 ? `▲ +${s} positions since start` : s < 0 ? `▼ ${s} positions since start` : '0 (unchanged since start)';
    }
    return {
      tenantId, siteUrl, dimension, key, observationDays: pts.length, points: pts.map(toPt), start, previous, current,
      movementSincePrevious, movementSinceStart,
      gapDaysSincePrevious: previous ? dayDiff(previous.date, current.date) : null,
      lowSample: current.impressions < LOW_SAMPLE_IMPRESSIONS || start.impressions < LOW_SAMPLE_IMPRESSIONS,
      startFormatted: pts.length > 1 ? fmt(start) : `${fmt(start)} — first observation`,
      previousFormatted: previous ? fmt(previous) : 'N/A — no earlier observation',
      currentFormatted: fmt(current),
      movementFormatted,
      provenance,
      lastFetchedAt: pts.map(p => p.fetchedAt).sort().pop()!
    };
  }

  /** Persisted-only read. Never calls GSC. */
  public trajectories(tenantId: string, siteUrl: string, dimension: GscDimensionLevel): GscPositionTrajectory[] {
    const byKey = new Map<string, ReturnType<SeoDatabase['getGscPositionObservations']>>();
    for (const o of this.db.getGscPositionObservations(tenantId, siteUrl, dimension)) {
      const list = byKey.get(o.key) ?? [];
      list.push(o);
      byKey.set(o.key, list);
    }
    return [...byKey.entries()]
      .map(([k, list]) => GscPositionTracker.computeTrajectory(tenantId, siteUrl, dimension, k, list)!)
      .sort((a, b) => b.current.impressions - a.current.impressions);
  }
}
