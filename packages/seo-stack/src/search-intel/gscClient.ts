/**
 * SANOCEA SEO Stack — Google Search Console Analytics Ingestion Client
 * 
 * Ingests multi-dimensional Search Analytics data:
 * - Queries, Landing Pages, Devices, Countries, Search Appearances, Dates
 * - Clicks, Impressions, CTR, Average Position
 * - Generates structured GscSnapshot objects for historical tracking
 */

import { GscAuthManager } from './gscAuth.js';
import { 
  GscPerformanceRow, 
  GscSnapshot, 
  GscDateRange, 
  GscDimension 
} from '../core/types.js';

export interface GscQueryOptions {
  siteUrl: string;
  dateRange: GscDateRange;
  dimensions?: GscDimension[];
  dimensionFilterGroups?: Array<{
    filters: Array<{
      dimension: GscDimension;
      operator: 'contains' | 'equals' | 'notContains' | 'notEquals';
      expression: string;
    }>;
  }>;
  rowLimit?: number;
  startRow?: number;
}

export class GscClient {
  private authManager: GscAuthManager;
  private mockSnapshot?: GscSnapshot;

  constructor(authManager: GscAuthManager, mockSnapshot?: GscSnapshot) {
    this.authManager = authManager;
    this.mockSnapshot = mockSnapshot;
  }

  /** True when this client serves fixture data instead of the live GSC API. Fixture rows are never observations. */
  public get isFixtureMode(): boolean {
    return Boolean(this.mockSnapshot);
  }

  /**
   * Sets or overrides mock snapshot data for offline audits and test pipelines
   */
  public setMockSnapshot(snapshot: GscSnapshot): void {
    this.mockSnapshot = snapshot;
  }

  /**
   * Executes a raw searchAnalytics.query request against the GSC API
   */
  public async querySearchAnalytics(options: GscQueryOptions): Promise<GscPerformanceRow[]> {
    if (this.mockSnapshot) {
      // In fixture mode, return filtered mock rows based on requested dimensions
      const requestedDims = options.dimensions || ['query'];
      if (requestedDims.includes('page') && !requestedDims.includes('query')) {
        return this.mockSnapshot.pageRows;
      }
      return this.mockSnapshot.queryRows;
    }

    const token = await this.authManager.getAccessToken();
    if (!token) {
      throw new Error('GSC access token unavailable [REQUIRES_ACCESS]');
    }

    const encodedSiteUrl = encodeURIComponent(options.siteUrl);
    const url = `https://www.googleapis.com/webmasters/v3/sites/${encodedSiteUrl}/searchAnalytics/query`;

    const requestBody: any = {
      startDate: options.dateRange.startDate,
      endDate: options.dateRange.endDate,
      dimensions: options.dimensions || ['query'],
      rowLimit: options.rowLimit || 1000,
      startRow: options.startRow || 0
    };

    if (options.dimensionFilterGroups && options.dimensionFilterGroups.length > 0) {
      requestBody.dimensionFilterGroups = options.dimensionFilterGroups;
    }

    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`GSC API searchAnalytics.query failed (HTTP ${resp.status}): ${errText}`);
    }

    const data = await resp.json() as any;
    const rawRows = data.rows || [];

    const dimensions = options.dimensions || ['query'];
    return rawRows.map((r: any) => {
      const keys = r.keys || [];
      const row: GscPerformanceRow = {
        clicks: r.clicks || 0,
        impressions: r.impressions || 0,
        ctr: r.ctr || 0,
        position: r.position || 0
      };

      dimensions.forEach((dim, idx) => {
        if (dim === 'query') row.query = keys[idx];
        if (dim === 'page') row.page = keys[idx];
        if (dim === 'device') row.device = keys[idx];
        if (dim === 'country') row.country = keys[idx];
        if (dim === 'searchAppearance') row.searchAppearance = keys[idx];
        if (dim === 'date') row.date = keys[idx];
      });

      return row;
    });
  }

  /**
   * Captures a comprehensive multi-dimensional GSC snapshot for a target domain and date range
   */
  public async captureSnapshot(siteUrl: string, dateRange: GscDateRange): Promise<GscSnapshot> {
    if (this.mockSnapshot) {
      return {
        ...this.mockSnapshot,
        siteUrl,
        dateRange,
        capturedAt: new Date().toISOString()
      };
    }

    // 1. Query top Queries
    const queryRows = await this.querySearchAnalytics({
      siteUrl,
      dateRange,
      dimensions: ['query'],
      rowLimit: 5000
    });

    // 2. Query top Landing Pages
    const pageRows = await this.querySearchAnalytics({
      siteUrl,
      dateRange,
      dimensions: ['page'],
      rowLimit: 2500
    });

    // 3. Query Device Breakdown
    const deviceRows = await this.querySearchAnalytics({
      siteUrl,
      dateRange,
      dimensions: ['device']
    });

    // 4. Query Search Appearance Breakdown (Merchant Listings, Product Snippets)
    let searchAppearanceRows: GscPerformanceRow[] = [];
    try {
      searchAppearanceRows = await this.querySearchAnalytics({
        siteUrl,
        dateRange,
        dimensions: ['searchAppearance']
      });
    } catch {
      // searchAppearance may return empty if property has no rich results
      searchAppearanceRows = [];
    }

    // Compute aggregate metrics with mathematical integrity
    let totalClicks = 0;
    let totalImpressions = 0;
    let weightedPositionSum = 0;

    // Google Search Console anonymizes queries below privacy thresholds; fall back to pageRows if queryRows is empty
    const sourceRows = queryRows.length > 0 ? queryRows : pageRows;
    for (const r of sourceRows) {
      totalClicks += r.clicks;
      totalImpressions += r.impressions;
      weightedPositionSum += (r.position * r.impressions);
    }

    const averageCtr = totalImpressions > 0 ? (totalClicks / totalImpressions) : 0;
    const averagePosition = totalImpressions > 0 ? (weightedPositionSum / totalImpressions) : 0;

    const snapshotId = `GSC-SNAP-${Buffer.from(siteUrl).toString('base64url').slice(0, 8)}-${dateRange.startDate}_${dateRange.endDate}`;

    return {
      snapshotId,
      siteUrl,
      dateRange,
      totalClicks,
      totalImpressions,
      averageCtr,
      averagePosition,
      queryRows,
      pageRows,
      deviceRows,
      searchAppearanceRows,
      capturedAt: new Date().toISOString()
    };
  }
}
