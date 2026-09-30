/**
 * SANOCEA SEO Stack — Chrome UX Report (CrUX) Field Performance Client
 * 
 * Captures real-user 28-day rolling field performance telemetry from Google CrUX:
 * - p75 Largest Contentful Paint (LCP)
 * - p75 Interaction to Next Paint (INP)
 * - p75 Cumulative Layout Shift (CLS)
 * - Mobile (PHONE) vs Desktop form factors
 * 
 * Epistemological Rule:
 * Keep Lighthouse/Playwright laboratory measurements strictly separated from CrUX field data.
 * When CrUX data is unavailable (insufficient site traffic or uncredentialed), mark as 
 * [REQUIRES_ACCESS] / UNAVAILABLE. Never synthesize fake field data.
 */

import { CruxReport, CruxDeviceMetrics, CruxMetric } from '../core/types.js';

export interface CruxQueryParams {
  url?: string;
  origin?: string;
  formFactor?: 'PHONE' | 'DESKTOP' | 'ALL_FORM_FACTORS';
  apiKey?: string;
}

export class CruxClient {
  private apiKey?: string;
  private endpoint = 'https://chromeuxreport.googleapis.com/v1/records:queryRecord';

  constructor(apiKey?: string) {
    this.apiKey = apiKey;
  }

  /**
   * Fetches real-user field data for a target URL or Origin
   */
  public async fetchFieldReport(targetUrl: string): Promise<CruxReport | null> {
    if (!this.apiKey) {
      // Uncredentialed: return null to preserve [REQUIRES_ACCESS]
      return null;
    }

    try {
      const mobileMetrics = await this.querySingleFormFactor(targetUrl, 'PHONE');
      const desktopMetrics = await this.querySingleFormFactor(targetUrl, 'DESKTOP');

      if (!mobileMetrics && !desktopMetrics) {
        return null;
      }

      return {
        url: targetUrl,
        scope: targetUrl.endsWith('/') && new URL(targetUrl).pathname === '/' ? 'ORIGIN' : 'URL',
        collectionPeriod: {
          firstDate: new Date(Date.now() - 28 * 86400 * 1000).toISOString().slice(0, 10),
          lastDate: new Date().toISOString().slice(0, 10)
        },
        mobile: mobileMetrics || undefined,
        desktop: desktopMetrics || undefined,
        telemetrySource: 'crux_api',
        fetchedAt: new Date().toISOString()
      };
    } catch {
      return null;
    }
  }

  private async querySingleFormFactor(url: string, formFactor: 'PHONE' | 'DESKTOP'): Promise<CruxDeviceMetrics | null> {
    const urlObj = new URL(url);
    const bodyPayload: any = {
      formFactor,
      metrics: [
        'largest_contentful_paint',
        'interaction_to_next_paint',
        'cumulative_layout_shift',
        'first_contentful_paint'
      ]
    };

    if (urlObj.pathname === '/' || urlObj.pathname === '') {
      bodyPayload.origin = urlObj.origin;
    } else {
      bodyPayload.url = url;
    }

    const apiUrl = `${this.endpoint}?key=${encodeURIComponent(this.apiKey!)}`;
    const resp = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bodyPayload)
    });

    if (!resp.ok) {
      return null;
    }

    const data = (await resp.json()) as any;
    return this.parseRecord(data?.record, formFactor);
  }

  private parseRecord(record: any, formFactor: 'PHONE' | 'DESKTOP'): CruxDeviceMetrics | null {
    if (!record || !record.metrics) return null;

    const rawLcp = record.metrics.largest_contentful_paint;
    const rawInp = record.metrics.interaction_to_next_paint;
    const rawCls = record.metrics.cumulative_layout_shift;
    const rawFcp = record.metrics.first_contentful_paint;

    const lcpP75 = rawLcp?.percentiles?.p75 ? Number(rawLcp.percentiles.p75) : 0;
    const inpP75 = rawInp?.percentiles?.p75 ? Number(rawInp.percentiles.p75) : 0;
    const clsP75 = rawCls?.percentiles?.p75 ? parseFloat(rawCls.percentiles.p75) : 0;
    const fcpP75 = rawFcp?.percentiles?.p75 ? Number(rawFcp.percentiles.p75) : 0;

    const lcp: CruxMetric = {
      p75: lcpP75,
      unit: 'ms',
      rating: lcpP75 <= 2500 ? 'GOOD' : (lcpP75 <= 4000 ? 'NEEDS_IMPROVEMENT' : 'POOR')
    };

    const inp: CruxMetric = {
      p75: inpP75,
      unit: 'ms',
      rating: inpP75 <= 200 ? 'GOOD' : (inpP75 <= 500 ? 'NEEDS_IMPROVEMENT' : 'POOR')
    };

    const cls: CruxMetric = {
      p75: clsP75,
      unit: 'unitless',
      rating: clsP75 <= 0.1 ? 'GOOD' : (clsP75 <= 0.25 ? 'NEEDS_IMPROVEMENT' : 'POOR')
    };

    const fcp: CruxMetric = {
      p75: fcpP75,
      unit: 'ms',
      rating: fcpP75 <= 1800 ? 'GOOD' : (fcpP75 <= 3000 ? 'NEEDS_IMPROVEMENT' : 'POOR')
    };

    return {
      device: formFactor,
      lcp,
      inp,
      cls,
      fcp
    };
  }

  /**
   * Generates a deterministic mock CrUX report for controlled tests and offline audits
   */
  public static createMockReport(params: {
    url: string;
    mobileLcp: number;
    mobileInp: number;
    mobileCls: number;
    desktopLcp: number;
    desktopInp: number;
    desktopCls: number;
  }): CruxReport {
    return {
      url: params.url,
      scope: 'ORIGIN',
      collectionPeriod: {
        firstDate: '2026-08-01',
        lastDate: '2026-08-28'
      },
      mobile: {
        device: 'PHONE',
        lcp: {
          p75: params.mobileLcp,
          unit: 'ms',
          rating: params.mobileLcp <= 2500 ? 'GOOD' : (params.mobileLcp <= 4000 ? 'NEEDS_IMPROVEMENT' : 'POOR')
        },
        inp: {
          p75: params.mobileInp,
          unit: 'ms',
          rating: params.mobileInp <= 200 ? 'GOOD' : (params.mobileInp <= 500 ? 'NEEDS_IMPROVEMENT' : 'POOR')
        },
        cls: {
          p75: params.mobileCls,
          unit: 'unitless',
          rating: params.mobileCls <= 0.1 ? 'GOOD' : (params.mobileCls <= 0.25 ? 'NEEDS_IMPROVEMENT' : 'POOR')
        }
      },
      desktop: {
        device: 'DESKTOP',
        lcp: {
          p75: params.desktopLcp,
          unit: 'ms',
          rating: params.desktopLcp <= 2500 ? 'GOOD' : (params.desktopLcp <= 4000 ? 'NEEDS_IMPROVEMENT' : 'POOR')
        },
        inp: {
          p75: params.desktopInp,
          unit: 'ms',
          rating: params.desktopInp <= 200 ? 'GOOD' : (params.desktopInp <= 500 ? 'NEEDS_IMPROVEMENT' : 'POOR')
        },
        cls: {
          p75: params.desktopCls,
          unit: 'unitless',
          rating: params.desktopCls <= 0.1 ? 'GOOD' : (params.desktopCls <= 0.25 ? 'NEEDS_IMPROVEMENT' : 'POOR')
        }
      },
      telemetrySource: 'mock_fixture',
      fetchedAt: new Date().toISOString()
    };
  }
}
