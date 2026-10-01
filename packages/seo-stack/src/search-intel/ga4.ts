/**
 * SANOCEA SEO Stack — Google Analytics 4 connector (own property only, read-only, official Data + Admin APIs)
 *
 * Reuses the Search Console service account (GscAuthManager) with the analytics.readonly scope: no second credential.
 * Collects, for OUR OWN property: sessions / users / engaged sessions / engagement time / key events by date x default
 * channel group x landing page, and an inventory of the events the property actually records plus which are configured
 * as key events.
 *
 * Truth rules:
 * - Only rows the live API returned are stored. No property id, no credential, HTTP/API failure or an unrecognised
 *   response shape => ProviderUnavailable and nothing is stored.
 * - GA4 is first-party BEHAVIOUR data: it says what visitors did after arriving. It is never mixed with GSC (Google search
 *   impressions/position) or crawler facts, and carries its own provenance label.
 * - A key event that is configured but has a zero count is reported as "configured, not observed". A conversion signal is
 *   claimed only for key events with a non-zero observed count.
 * - GA4 may apply thresholding / sampling to a report; the API's own metadata is not re-interpreted here.
 */

import { SeoDatabase } from '../persistence/seoDb.js';
import { GscAuthManager, ANALYTICS_READONLY_SCOPE } from './gscAuth.js';
import { ProviderUnavailable } from './rankCommandTypes.js';

export const GA4_PROVENANCE = '[OBSERVED: GOOGLE ANALYTICS 4 DATA API]' as const;
const DATA = 'https://analyticsdata.googleapis.com/v1beta';
const ADMIN = 'https://analyticsadmin.googleapis.com/v1beta';
const PAGE = 10000;

export interface Ga4CollectResult {
  status: 'OBSERVED' | 'NOT_AVAILABLE';
  landingRowsStored: number;
  eventsStored: number;
  keyEventsConfigured: number;
  unavailable?: ProviderUnavailable;
  notes: string[];
}

const ymd = (v: string): string | null => (/^\d{8}$/.test(v) ? `${v.slice(0, 4)}-${v.slice(4, 6)}-${v.slice(6, 8)}` : null);
const num = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : NaN; };

export class Ga4Collector {
  constructor(private db: SeoDatabase, private opts: { auth?: GscAuthManager; propertyId?: string; fetchImpl?: typeof fetch; windowDays?: number } = {}) {}

  public get propertyId(): string | undefined { return (this.opts.propertyId ?? process.env.GA4_PROPERTY_ID)?.replace(/^properties\//, '').trim() || undefined; }
  public get configured(): boolean { return Boolean(this.propertyId && this.opts.auth); }

  private async call(url: string, token: string, body?: unknown): Promise<any> {
    const name = url.replace(/^https:\/\/[^/]+\/v1beta\/properties\/\d+/, '');
    const res = await (this.opts.fetchImpl ?? fetch)(url, {
      method: body ? 'POST' : 'GET', signal: AbortSignal.timeout(30000),
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined
    }).catch((e: any) => { throw new Error(`${name}: ${e?.name === 'TimeoutError' ? 'timeout' : 'network error'}`); });
    if (!res.ok) {
      let reason = '';
      try { reason = String(((await res.json()) as any)?.error?.status ?? ''); } catch { /* not JSON */ }
      throw new Error(`${name}: HTTP ${res.status}${reason ? ` ${reason}` : ''}`);
    }
    try { return await res.json(); } catch { throw new Error(`${name}: response was not JSON`); }
  }

  public async collect(tenantId: string, now = new Date()): Promise<Ga4CollectResult> {
    const fetchedAt = now.toISOString();
    const na = (reason: string, notes: string[] = []): Ga4CollectResult => ({ status: 'NOT_AVAILABLE', landingRowsStored: 0, eventsStored: 0, keyEventsConfigured: 0, notes,
      unavailable: { available: false, provider: 'GOOGLE_ANALYTICS_4', reason, timestamp: fetchedAt } });
    const pid = this.propertyId;
    if (!pid) return na('GA4_PROPERTY_ID is not configured');
    if (!this.opts.auth) return na('no Google service account is configured');
    let token: string | null;
    try { token = await this.opts.auth.getServiceAccountTokenForScope(ANALYTICS_READONLY_SCOPE); } catch (e: any) { return na(String(e.message)); }
    if (!token) return na('no Google service account is configured');

    const days = this.opts.windowDays ?? 90;
    const dateRanges = [{ startDate: `${days}daysAgo`, endDate: 'yesterday' }];
    const notes: string[] = [];
    const errors: string[] = [];
    let landingRows = 0, eventRows = 0, keyCount = 0;

    try {
      const rows: Parameters<SeoDatabase['upsertGa4LandingObservations']>[0] = [];
      for (let offset = 0; ; offset += PAGE) {
        const j = await this.call(`${DATA}/properties/${pid}:runReport`, token, {
          dateRanges, limit: PAGE, offset,
          dimensions: [{ name: 'date' }, { name: 'sessionDefaultChannelGroup' }, { name: 'landingPage' }],
          metrics: ['sessions', 'totalUsers', 'engagedSessions', 'userEngagementDuration', 'keyEvents'].map(name => ({ name }))
        });
        if (!Array.isArray(j?.dimensionHeaders) || !Array.isArray(j?.metricHeaders)) throw new Error('runReport: unexpected response shape');
        for (const r of j.rows ?? []) {
          const d = r.dimensionValues?.map((x: any) => x?.value), m = r.metricValues?.map((x: any) => num(x?.value));
          const date = ymd(d?.[0] ?? '');
          if (!date || typeof d?.[1] !== 'string' || typeof d?.[2] !== 'string' || !m || m.length !== 5 || m.some(Number.isNaN)) continue;
          rows.push({ tenantId, propertyId: pid, observedDate: date, channelGroup: d[1], landingPage: d[2], sessions: m[0], users: m[1], engagedSessions: m[2], engagementSeconds: m[3], keyEvents: m[4], fetchedAt });
        }
        if (offset + PAGE >= (num(j.rowCount) || 0)) break;
      }
      this.db.upsertGa4LandingObservations(rows);
      landingRows = rows.length;
      if (!rows.length) notes.push('GA4 returned no landing-page rows for the window');
    } catch (e: any) { errors.push(String(e.message)); }

    try {
      const [ev, ke] = await Promise.all([
        this.call(`${DATA}/properties/${pid}:runReport`, token, { dateRanges, dimensions: [{ name: 'eventName' }], metrics: [{ name: 'eventCount' }, { name: 'keyEvents' }], limit: 1000 }),
        this.call(`${ADMIN}/properties/${pid}/keyEvents`, token)
      ]);
      if (!Array.isArray(ev?.dimensionHeaders)) throw new Error('events: unexpected response shape');
      const configured = new Set<string>((ke?.keyEvents ?? []).map((k: any) => k?.eventName).filter((n: any) => typeof n === 'string'));
      const seen = new Map<string, { c: number; k: number }>();
      for (const r of ev.rows ?? []) {
        const n = r.dimensionValues?.[0]?.value, c = num(r.metricValues?.[0]?.value), k = num(r.metricValues?.[1]?.value);
        if (typeof n === 'string' && Number.isFinite(c) && Number.isFinite(k)) seen.set(n, { c, k });
      }
      const [ws, we] = [new Date(now.getTime() - days * 86400000).toISOString().slice(0, 10), new Date(now.getTime() - 86400000).toISOString().slice(0, 10)];
      const names = new Set([...seen.keys(), ...configured]);
      const inv = [...names].map(eventName => ({ eventName, isKeyEvent: configured.has(eventName), eventCount: seen.get(eventName)?.c ?? 0, keyEventCount: seen.get(eventName)?.k ?? 0, windowStart: ws, windowEnd: we, fetchedAt }));
      this.db.replaceGa4EventInventory(tenantId, pid, inv);
      eventRows = inv.length; keyCount = configured.size;
    } catch (e: any) { errors.push(String(e.message)); }

    if (landingRows + eventRows === 0) return na(errors.join('; ') || 'no rows', notes);
    notes.push(...errors.map(e => `partial: ${e}`));
    return { status: 'OBSERVED', landingRowsStored: landingRows, eventsStored: eventRows, keyEventsConfigured: keyCount, notes };
  }

  /** Persisted-only report. Every number is a stored GA4 observation; nothing is computed from other providers. */
  public report(tenantId: string) {
    const pid = this.propertyId;
    if (!pid) return { configured: false, provenance: '[NOT AVAILABLE]', reason: 'GA4_PROPERTY_ID is not configured' };
    const rows = this.db.getGa4LandingObservations(tenantId, pid);
    const events = this.db.getGa4EventInventory(tenantId, pid);
    if (!rows.length && !events.length) return { configured: this.configured, provenance: '[NOT AVAILABLE]', reason: 'no GA4 observations have been collected yet' };
    const byChannel = new Map<string, { sessions: number; users: number; engagedSessions: number; engagementSeconds: number }>();
    for (const r of rows) { const a = byChannel.get(r.channelGroup) ?? { sessions: 0, users: 0, engagedSessions: 0, engagementSeconds: 0 }; a.sessions += r.sessions; a.users += r.users; a.engagedSessions += r.engagedSessions; a.engagementSeconds += r.engagementSeconds; byChannel.set(r.channelGroup, a); }
    const keyEvents = events.filter(e => e.isKeyEvent);
    return {
      configured: this.configured, provenance: GA4_PROVENANCE, propertyId: pid,
      window: rows.length ? { from: rows[0].observedDate, to: rows[rows.length - 1].observedDate } : null,
      fetchedAt: rows[0]?.fetchedAt ?? events[0]?.fetchedAt ?? null,
      caveat: 'GA4 users are summed per day-and-channel row, so users across days may overlap; sessions are additive.',
      byChannel: [...byChannel.entries()].map(([channel, v]) => ({ channel, ...v, engagementRate: v.sessions ? v.engagedSessions / v.sessions : null })).sort((a, b) => b.sessions - a.sessions),
      organicSearchLandingPages: this.landingPages(tenantId, 'Organic Search'),
      conversionSignal: {
        keyEventsConfigured: keyEvents.map(e => e.eventName),
        keyEventsObserved: keyEvents.filter(e => e.keyEventCount > 0 || e.eventCount > 0).map(e => ({ eventName: e.eventName, count: e.eventCount })),
        statement: keyEvents.some(e => e.eventCount > 0) ? 'At least one configured key event was observed.' : keyEvents.length ? 'Key events are configured in GA4 but none was observed in the window; no conversion signal exists yet.' : 'No key events are configured in GA4.'
      },
      events: events.map(e => ({ eventName: e.eventName, count: e.eventCount, keyEvent: e.isKeyEvent }))
    };
  }

  /** Sessions/engagement per landing page for one channel group, from stored observations. */
  public landingPages(tenantId: string, channelGroup?: string) {
    const pid = this.propertyId;
    if (!pid) return [];
    const by = new Map<string, { sessions: number; engagedSessions: number; engagementSeconds: number; keyEvents: number }>();
    for (const r of this.db.getGa4LandingObservations(tenantId, pid)) {
      if (channelGroup && r.channelGroup !== channelGroup) continue;
      const a = by.get(r.landingPage) ?? { sessions: 0, engagedSessions: 0, engagementSeconds: 0, keyEvents: 0 };
      a.sessions += r.sessions; a.engagedSessions += r.engagedSessions; a.engagementSeconds += r.engagementSeconds; a.keyEvents += r.keyEvents; by.set(r.landingPage, a);
    }
    return [...by.entries()].map(([landingPage, v]) => ({ landingPage, ...v })).sort((a, b) => b.sessions - a.sessions);
  }
}
