/**
 * SANOCEA SEO Stack — GSC Historical Snapshot Store & Period Delta Comparator
 * 
 * Stores search performance snapshots and computes mathematically exact
 * period-over-period comparisons without loss of precision.
 */

import { 
  GscSnapshot, 
  GscComparisonReport, 
  GscDimensionDelta 
} from '../core/types.js';
import { SeoDatabase } from '../persistence/seoDb.js';

export class GscSnapshotStore {
  private snapshots = new Map<string, GscSnapshot>();
  private db?: SeoDatabase;
  private defaultTenantId: string;

  constructor(db?: SeoDatabase, defaultTenantId: string = 'sanocea') {
    this.db = db;
    this.defaultTenantId = defaultTenantId;
  }

  /**
   * Saves a snapshot to the store (and SQLite database if configured)
   */
  public saveSnapshot(snapshot: GscSnapshot, tenantId?: string): void {
    this.snapshots.set(snapshot.snapshotId, snapshot);
    if (this.db) {
      this.db.saveGscSnapshot(tenantId || this.defaultTenantId, snapshot);
    }
  }

  /**
   * Retrieves a snapshot by ID
   */
  public getSnapshot(snapshotId: string): GscSnapshot | undefined {
    if (this.snapshots.has(snapshotId)) {
      return this.snapshots.get(snapshotId);
    }
    if (this.db) {
      const snap = this.db.getGscSnapshot(snapshotId);
      if (snap) {
        this.snapshots.set(snapshotId, snap);
        return snap;
      }
    }
    return undefined;
  }

  /**
   * Lists all snapshots for a given site URL ordered chronologically
   */
  public getSnapshotsForSite(siteUrl: string): GscSnapshot[] {
    if (this.db) {
      const persisted = this.db.getGscSnapshotsForSite(siteUrl);
      if (persisted.length > 0) {
        for (const s of persisted) {
          this.snapshots.set(s.snapshotId, s);
        }
        return persisted;
      }
    }
    return Array.from(this.snapshots.values())
      .filter(s => s.siteUrl === siteUrl)
      .sort((a, b) => a.dateRange.startDate.localeCompare(b.dateRange.startDate));
  }

  /**
   * Computes a deterministic period-over-period comparison between baseline and comparison snapshots
   */
  public static compareSnapshots(baseline: GscSnapshot, comparison: GscSnapshot): GscComparisonReport {
    if (baseline.siteUrl !== comparison.siteUrl) {
      throw new Error(`Cannot compare snapshots from different sites: ${baseline.siteUrl} vs ${comparison.siteUrl}`);
    }

    const totalClickDelta = comparison.totalClicks - baseline.totalClicks;
    const totalImpressionDelta = comparison.totalImpressions - baseline.totalImpressions;
    const averageCtrDelta = comparison.averageCtr - baseline.averageCtr;
    // Negative position delta means rank improved (e.g. 7.5 to 4.2 is -3.3 rank delta)
    const averagePositionDelta = comparison.averagePosition - baseline.averagePosition;

    // 1. Compute Query Deltas
    const queryMap = new Map<string, { baseline?: any; comparison?: any }>();
    for (const q of baseline.queryRows) {
      if (!q.query) continue;
      if (!queryMap.has(q.query)) queryMap.set(q.query, {});
      queryMap.get(q.query)!.baseline = q;
    }
    for (const q of comparison.queryRows) {
      if (!q.query) continue;
      if (!queryMap.has(q.query)) queryMap.set(q.query, {});
      queryMap.get(q.query)!.comparison = q;
    }

    const queryDeltas: GscDimensionDelta[] = [];
    const winners: GscDimensionDelta[] = [];
    const losers: GscDimensionDelta[] = [];
    const newQueries: GscDimensionDelta[] = [];
    const lostQueries: GscDimensionDelta[] = [];
    const strikeZoneQueries: GscDimensionDelta[] = [];

    for (const [query, data] of queryMap.entries()) {
      const bClicks = data.baseline?.clicks || 0;
      const cClicks = data.comparison?.clicks || 0;
      const bImpr = data.baseline?.impressions || 0;
      const cImpr = data.comparison?.impressions || 0;
      const bCtr = data.baseline?.ctr || 0;
      const cCtr = data.comparison?.ctr || 0;
      const bPos = data.baseline?.position || 0;
      const cPos = data.comparison?.position || 0;

      const clickDelta = cClicks - bClicks;
      const impressionDelta = cImpr - bImpr;
      const ctrDelta = cCtr - bCtr;
      const positionDelta = (bPos > 0 && cPos > 0) ? (cPos - bPos) : 0;

      const deltaObj: GscDimensionDelta = {
        key: query,
        baselineClicks: bClicks,
        comparisonClicks: cClicks,
        clickDelta,
        baselineImpressions: bImpr,
        comparisonImpressions: cImpr,
        impressionDelta,
        baselineCtr: bCtr,
        comparisonCtr: cCtr,
        ctrDelta,
        baselinePosition: bPos,
        comparisonPosition: cPos,
        positionDelta
      };

      queryDeltas.push(deltaObj);

      // New Query: 0 in baseline, active in comparison
      if (bImpr === 0 && cImpr >= 20) {
        newQueries.push(deltaObj);
      }

      // Lost Query: active in baseline, 0 in comparison
      if (bImpr >= 20 && cImpr === 0) {
        lostQueries.push(deltaObj);
      }

      // Rank Winner: rank improved by >= 1.5 positions with significant impressions
      if (bPos > 0 && cPos > 0 && positionDelta <= -1.5 && cImpr >= 50) {
        winners.push(deltaObj);
      }

      // Rank Loser: rank dropped by >= 1.5 positions or clicks dropped by >= 15%
      if (bPos > 0 && cPos > 0 && (positionDelta >= 1.5 || (bClicks >= 10 && clickDelta <= -(bClicks * 0.15)))) {
        losers.push(deltaObj);
      }

      // Strike-Zone Queries: position 4.0 to 10.9 with >= 150 impressions
      if (cPos >= 4.0 && cPos <= 10.9 && cImpr >= 150) {
        strikeZoneQueries.push(deltaObj);
      }
    }

    // Sort winners and strike-zone by opportunity volume
    winners.sort((a, b) => b.comparisonClicks - a.comparisonClicks);
    losers.sort((a, b) => a.clickDelta - b.clickDelta);
    strikeZoneQueries.sort((a, b) => b.comparisonImpressions - a.comparisonImpressions);

    // 2. Compute Page Deltas
    const pageMap = new Map<string, { baseline?: any; comparison?: any }>();
    for (const p of baseline.pageRows) {
      if (!p.page) continue;
      if (!pageMap.has(p.page)) pageMap.set(p.page, {});
      pageMap.get(p.page)!.baseline = p;
    }
    for (const p of comparison.pageRows) {
      if (!p.page) continue;
      if (!pageMap.has(p.page)) pageMap.set(p.page, {});
      pageMap.get(p.page)!.comparison = p;
    }

    const pageDeltas: GscDimensionDelta[] = [];
    for (const [page, data] of pageMap.entries()) {
      const bClicks = data.baseline?.clicks || 0;
      const cClicks = data.comparison?.clicks || 0;
      const bImpr = data.baseline?.impressions || 0;
      const cImpr = data.comparison?.impressions || 0;
      const bCtr = data.baseline?.ctr || 0;
      const cCtr = data.comparison?.ctr || 0;
      const bPos = data.baseline?.position || 0;
      const cPos = data.comparison?.position || 0;

      pageDeltas.push({
        key: page,
        baselineClicks: bClicks,
        comparisonClicks: cClicks,
        clickDelta: cClicks - bClicks,
        baselineImpressions: bImpr,
        comparisonImpressions: cImpr,
        impressionDelta: cImpr - bImpr,
        baselineCtr: bCtr,
        comparisonCtr: cCtr,
        ctrDelta: cCtr - bCtr,
        baselinePosition: bPos,
        comparisonPosition: cPos,
        positionDelta: (bPos > 0 && cPos > 0) ? (cPos - bPos) : 0
      });
    }

    pageDeltas.sort((a, b) => b.comparisonClicks - a.comparisonClicks);

    return {
      siteUrl: baseline.siteUrl,
      baselineRange: baseline.dateRange,
      comparisonRange: comparison.dateRange,
      totalClickDelta,
      totalImpressionDelta,
      averageCtrDelta,
      averagePositionDelta,
      queryDeltas,
      pageDeltas,
      winners,
      losers,
      newQueries,
      lostQueries,
      strikeZoneQueries
    };
  }
}
