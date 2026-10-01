/**
 * SANOCEA SEO Stack — Published-page audit (what a crawler that does not run JavaScript sees)
 *
 * Fetches the tenant's own robots.txt and a bounded set of sitemap pages with plain HTTP and reports only what it
 * observed: readable words in the delivered HTML, <h1> count, JSON-LD @types (including retired Google rich results),
 * and effective AI-crawler access. It produces NO score. A 0-100 "AI citability" number would need weights and
 * thresholds with no validated source, so none is invented; the raw observations are reported instead.
 *
 * Idea provenance: claude-seo / geo-seo-claude / marketingskills ai-seo all stress that AI and search crawlers often
 * read only server-delivered HTML. Independent implementation; no code copied.
 */

import * as cheerio from 'cheerio';
import { AiCrawlerAccess, resolveAiCrawlerAccess } from './aiCrawlerPolicy.js';
import { findRetiredSchemaTypes } from './retiredRichResults.js';
import { staticVisibleText, staticBodyWordCount, countWords } from './staticText.js';

export const THIN_STATIC_WORD_THRESHOLD = 100; // same threshold as the THIN_CONTENT_DETECTED rule

export interface PublishedPageObservation {
  url: string;
  status: number;
  staticWords: number;
  /** All body words in the delivered HTML including header/nav/footer (staticWords excludes those). */
  bodyWords: number;
  finalUrl: string;
  redirected: boolean;
  title: string;
  h1Text: string;
  h1Count: number;
  jsonLdTypes: string[];
  retiredSchemaTypes: string[];
}

export interface PublishedPageAudit {
  checkedAt: string;
  robots: { status: 'fetched' | 'missing' | 'failed'; crawlers: AiCrawlerAccess[] };
  pages: PublishedPageObservation[];
  failures: Array<{ url: string; error: string }>;
  sitemapStatus: 'fetched' | 'missing' | 'failed';
}

export interface PublishedPageAuditOptions {
  fetchImpl?: typeof fetch;
  maxPages?: number;
  timeoutMs?: number;
}

function typesOf(parsed: any, into: Set<string>): void {
  const items = Array.isArray(parsed) ? parsed : parsed?.['@graph'] ? parsed['@graph'] : [parsed];
  for (const ent of items) {
    if (!ent || typeof ent !== 'object') continue;
    const t = ent['@type'];
    for (const name of Array.isArray(t) ? t : t ? [t] : []) if (typeof name === 'string') into.add(name);
  }
}

export async function auditPublishedPages(domain: string, opts: PublishedPageAuditOptions = {}): Promise<PublishedPageAudit> {
  const doFetch = opts.fetchImpl ?? fetch;
  const timeout = opts.timeoutMs ?? 6000;
  const maxPages = opts.maxPages ?? 8;
  const origin = `https://${domain}`;
  const get = (url: string) => doFetch(url, { method: 'GET', signal: AbortSignal.timeout(timeout), redirect: 'follow' });

  const audit: PublishedPageAudit = {
    checkedAt: new Date().toISOString(),
    robots: { status: 'failed', crawlers: [] },
    pages: [], failures: [], sitemapStatus: 'failed'
  };

  try {
    const res = await get(`${origin}/robots.txt`);
    if (res.ok) {
      audit.robots = { status: 'fetched', crawlers: resolveAiCrawlerAccess(await res.text()) };
    } else if (res.status === 404) {
      audit.robots = { status: 'missing', crawlers: [] };
    }
  } catch { /* stays 'failed' */ }

  const urls: string[] = [`${origin}/`];
  try {
    const res = await get(`${origin}/sitemap.xml`);
    if (res.ok) {
      audit.sitemapStatus = 'fetched';
      const xml = await res.text();
      for (const m of xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)) {
        try {
          const u = new URL(m[1]);
          const norm = `${u.origin}${u.pathname}`;
          if (u.hostname === domain && !urls.includes(norm) && !urls.includes(norm + '/') && !/\.xml(\.gz)?$/i.test(u.pathname)) urls.push(norm);
        } catch { /* ignore malformed loc */ }
      }
    } else if (res.status === 404) {
      audit.sitemapStatus = 'missing';
    }
  } catch { /* stays 'failed' */ }

  for (const url of urls.slice(0, maxPages)) {
    try {
      const res = await get(url);
      if (!res.ok) { audit.failures.push({ url, error: `HTTP ${res.status}` }); continue; }
      const $ = cheerio.load(await res.text());
      const types = new Set<string>();
      $('script[type="application/ld+json"]').each((_: number, el: any) => {
        try { typesOf(JSON.parse($(el).html() || '{}'), types); } catch { /* invalid JSON-LD is ignored here */ }
      });
      audit.pages.push({
        url, status: res.status,
        staticWords: countWords(staticVisibleText($)),
        bodyWords: staticBodyWordCount($),
        finalUrl: res.url || url,
        redirected: Boolean(res.redirected),
        title: $('title').first().text().trim().slice(0, 200),
        h1Text: $('h1').first().text().trim().slice(0, 200),
        h1Count: $('h1').length,
        jsonLdTypes: [...types].sort(),
        retiredSchemaTypes: findRetiredSchemaTypes(types).map(r => r.type)
      });
    } catch (err: any) {
      audit.failures.push({ url, error: err?.name === 'TimeoutError' ? `timeout after ${timeout}ms` : String(err?.message ?? err) });
    }
  }
  return audit;
}
