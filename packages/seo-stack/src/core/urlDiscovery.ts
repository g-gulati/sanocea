/**
 * SANOCEA SEO Stack — High-Performance URL Discovery & Crawl Graph Engine
 * Track A:
 * - Recursive XML sitemap / sitemapindex parsing
 * - Redirect-chain and redirect-loop tracing
 * - Crawl graph builder (inlinks, outlinks, in-degree, out-degree, orphan detection)
 * - Faceted and tracking parameter normalization
 */

import { AiBotDirective, buildAiBotDirectives, parseRobotsGroups } from './aiCrawlerPolicy.js';
import * as zlib from 'zlib';
import * as cheerio from 'cheerio';
import { DiscoveredUrl, CrawlGraphNode, CrawlGraphSummary, RedirectTrace, CrawledPage, OutboundLinkTarget } from './types.js';

/**
 * Decompresses gzip data (magic bytes 0x1f 0x8b) if present
 */
export function decompressIfGzip(data: Buffer | Uint8Array | string): string {
  if (typeof data === 'string') {
    return data;
  }
  const buf = Buffer.isBuffer(data) ? data : Buffer.from(data);
  if (buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b) {
    return zlib.gunzipSync(buf).toString('utf-8');
  }
  return buf.toString('utf-8');
}

export interface UrlNormalizationOptions {
  stripFragment?: boolean;
  stripTrackingParams?: boolean;
  normalizeTrailingSlash?: boolean;
  lowercaseHost?: boolean;
}

export const TRACKING_PARAMS = new Set([
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
  'gclid', 'fbclid', 'msclkid', 'mc_cid', 'mc_eid', '_ga', 'yclid'
]);

export const FACET_PARAMS = new Set([
  'filter', 'filter.v.price.gte', 'filter.v.price.lte', 'filter.v.availability',
  'sort_by', 'sort', 'order', 'color', 'size', 'material'
]);

export type ParameterCategory = 'FACET' | 'TRACKING' | 'FUNCTIONAL' | 'UNKNOWN';

/**
 * Deterministically classifies query parameter purpose
 */
export function classifyQueryParameter(key: string): ParameterCategory {
  const k = key.toLowerCase();
  if (
    k.startsWith('utm_') ||
    ['gclid', 'fbclid', 'msclkid', 'mc_cid', 'mc_eid', '_ga', 'yclid', 'ref', 'source'].includes(k)
  ) {
    return 'TRACKING';
  }
  if (['page', 'p', 'q', 'search', 'query', 's', 'id', 'category_id', 'lang', 'locale', 'view'].includes(k)) {
    return 'FUNCTIONAL';
  }
  if (
    ['filter', 'sort', 'sort_by', 'order', 'orderby', 'color', 'colour', 'size', 'material', 'brand', 'price', 'price_min', 'price_max', 'tag', 'rating', 'availability'].some(
      f => k === f || k.startsWith(f + '.') || k.startsWith(f + '_') || k.startsWith(f + '[')
    )
  ) {
    return 'FACET';
  }
  return 'UNKNOWN';
}

/**
 * Classifies all parameters on a URL and returns clean base URL
 */
export function classifyUrlParameters(rawUrl: string): {
  facetParams: string[];
  trackingParams: string[];
  functionalParams: string[];
  cleanUrl: string;
} {
  try {
    const urlObj = new URL(rawUrl);
    const facetParams: string[] = [];
    const trackingParams: string[] = [];
    const functionalParams: string[] = [];

    for (const key of Array.from(urlObj.searchParams.keys())) {
      const cat = classifyQueryParameter(key);
      if (cat === 'FACET') facetParams.push(key);
      else if (cat === 'TRACKING') trackingParams.push(key);
      else if (cat === 'FUNCTIONAL') functionalParams.push(key);
    }

    const cleanObj = new URL(rawUrl);
    for (const key of [...facetParams, ...trackingParams]) {
      cleanObj.searchParams.delete(key);
    }
    const cleanUrl = cleanObj.searchParams.toString() ? cleanObj.toString() : `${cleanObj.origin}${cleanObj.pathname}`;
    return {
      facetParams,
      trackingParams,
      functionalParams,
      cleanUrl
    };
  } catch {
    return {
      facetParams: [],
      trackingParams: [],
      functionalParams: [],
      cleanUrl: rawUrl
    };
  }
}

/**
 * Normalizes a URL to prevent duplicate crawling and loops
 */
export function normalizeUrl(rawUrl: string, baseUrl?: string, options: UrlNormalizationOptions = {}): string | null {
  const {
    stripFragment = true,
    stripTrackingParams = true,
    normalizeTrailingSlash = true,
    lowercaseHost = true
  } = options;

  try {
    const parsed = baseUrl ? new URL(rawUrl, baseUrl) : new URL(rawUrl);

    // Only allow HTTP/HTTPS
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return null;
    }

    if (lowercaseHost) {
      parsed.hostname = parsed.hostname.toLowerCase();
    }

    if (stripFragment) {
      parsed.hash = '';
    }

    if (stripTrackingParams && parsed.search) {
      const keys = Array.from(parsed.searchParams.keys());
      for (const k of keys) {
        if (TRACKING_PARAMS.has(k.toLowerCase())) {
          parsed.searchParams.delete(k);
        }
      }
    }

    // Normalize trailing slash for path (except root / or files with extension)
    let path = parsed.pathname;
    if (normalizeTrailingSlash && path.length > 1 && !path.includes('.')) {
      if (path.endsWith('/')) {
        path = path.slice(0, -1);
      }
    }
    parsed.pathname = path;

    return parsed.toString();
  } catch {
    return null;
  }
}

/**
 * Checks whether targetUrl belongs to the allowed domain / scope
 */
export function isUrlInScope(targetUrl: string, seedUrl: string, allowSubdomains = false): boolean {
  try {
    const targetParsed = new URL(targetUrl);
    const seedParsed = new URL(seedUrl);

    if (targetParsed.hostname === seedParsed.hostname) {
      return true;
    }

    if (allowSubdomains) {
      const getBaseDomain = (host: string) => {
        const parts = host.split('.');
        if (parts.length >= 2) {
          return parts.slice(-2).join('.');
        }
        return host;
      };

      return getBaseDomain(targetParsed.hostname) === getBaseDomain(seedParsed.hostname);
    }

    return false;
  } catch {
    return false;
  }
}

/**
 * Extracts all internal and external links from a page's DOM
 */
export function extractPageLinks(html: string, currentUrl: string, seedUrl: string, allowSubdomains = false): DiscoveredUrl[] {
  const $ = cheerio.load(html);
  const discoveredMap = new Map<string, DiscoveredUrl>();

  // 1. Standard <a href="...">
  $('a[href]').each((_, el) => {
    const rawHref = $(el).attr('href')?.trim();
    if (!rawHref || rawHref.startsWith('mailto:') || rawHref.startsWith('tel:') || rawHref.startsWith('javascript:')) {
      return;
    }

    const normalized = normalizeUrl(rawHref, currentUrl);
    if (!normalized) return;

    if (isUrlInScope(normalized, seedUrl, allowSubdomains)) {
      if (!discoveredMap.has(normalized)) {
        discoveredMap.set(normalized, {
          url: normalized,
          source: 'internal_link',
          foundOnUrl: currentUrl,
          depth: 1
        });
      }
    }
  });

  // 2. Canonical tag <link rel="canonical" href="...">
  const canonicalHref = $('link[rel="canonical"]').attr('href')?.trim();
  if (canonicalHref) {
    const normalized = normalizeUrl(canonicalHref, currentUrl);
    if (normalized && isUrlInScope(normalized, seedUrl, allowSubdomains)) {
      if (!discoveredMap.has(normalized)) {
        discoveredMap.set(normalized, {
          url: normalized,
          source: 'canonical',
          foundOnUrl: currentUrl,
          depth: 1
        });
      }
    }
  }

  // 3. JavaScript / Data attribute links: data-url, data-href
  $('[data-url], [data-href]').each((_, el) => {
    const rawVal = $(el).attr('data-url') || $(el).attr('data-href');
    if (rawVal) {
      const normalized = normalizeUrl(rawVal, currentUrl);
      if (normalized && isUrlInScope(normalized, seedUrl, allowSubdomains)) {
        if (!discoveredMap.has(normalized)) {
          discoveredMap.set(normalized, {
            url: normalized,
            source: 'js_render',
            foundOnUrl: currentUrl,
            depth: 1
          });
        }
      }
    }
  });

  return Array.from(discoveredMap.values());
}

/**
 * Extracts all external outbound <a href> links for status verification and probing
 */
export function extractOutboundLinks(
  html: string,
  currentUrl: string,
  seedUrl: string,
  allowSubdomains = false
): OutboundLinkTarget[] {
  const $ = cheerio.load(html);
  const outlinksMap = new Map<string, OutboundLinkTarget>();

  $('a[href]').each((_, el) => {
    const rawHref = $(el).attr('href')?.trim();
    if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('mailto:') || rawHref.startsWith('tel:') || rawHref.startsWith('javascript:')) {
      return;
    }

    try {
      const parsed = new URL(rawHref, currentUrl);
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        return;
      }
      const targetUrl = parsed.toString();
      if (!isUrlInScope(targetUrl, seedUrl, allowSubdomains)) {
        if (!outlinksMap.has(targetUrl)) {
          const anchorText = $(el).text().trim() || $(el).attr('aria-label') || $(el).attr('title') || 'External Link';
          outlinksMap.set(targetUrl, {
            url: targetUrl,
            anchorText,
            sourceUrl: currentUrl
          });
        }
      }
    } catch {}
  });

  return Array.from(outlinksMap.values());
}

/**
 * Parses XML sitemap text (handles standard <urlset> and <sitemapindex>)
 */
export function parseSitemapXml(xmlContent: string, seedUrl: string, allowSubdomains = false): { urls: string[]; childSitemaps: string[] } {
  const urls: string[] = [];
  const childSitemaps: string[] = [];

  // Match <loc> tags
  const locRegex = /<loc>\s*(https?:\/\/[^<\s]+)\s*<\/loc>/gi;
  let match: RegExpExecArray | null;

  while ((match = locRegex.exec(xmlContent)) !== null) {
    const rawUrl = match[1].trim();
    const normalized = normalizeUrl(rawUrl);
    if (!normalized) continue;

    if (rawUrl.endsWith('.xml') || rawUrl.endsWith('.xml.gz') || rawUrl.includes('/sitemap')) {
      // If it looks like a child sitemap
      if (!childSitemaps.includes(normalized)) {
        childSitemaps.push(normalized);
      }
    } else if (isUrlInScope(normalized, seedUrl, allowSubdomains)) {
      if (!urls.includes(normalized)) {
        urls.push(normalized);
      }
    }
  }

  return { urls, childSitemaps };
}

/**
 * Recursively parses sitemaps including <sitemapindex> up to maxDepth
 */
export async function parseSitemapXmlRecursive(
  initialSitemapUrl: string,
  seedUrl: string,
  fetchFn: (url: string) => Promise<string | Buffer>,
  maxSitemapDepth = 3,
  allowSubdomains = false
): Promise<{ allUrls: string[]; sitemapsParsed: string[] }> {
  const allUrls = new Set<string>();
  const sitemapsParsed = new Set<string>();
  const queue: { url: string; depth: number }[] = [{ url: initialSitemapUrl, depth: 0 }];

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) break;
    if (sitemapsParsed.has(current.url) || current.depth > maxSitemapDepth) continue;

    try {
      sitemapsParsed.add(current.url);
      const raw = await fetchFn(current.url);
      const xml = decompressIfGzip(raw);
      const { urls, childSitemaps } = parseSitemapXml(xml, seedUrl, allowSubdomains);

      for (const u of urls) {
        allUrls.add(u);
      }

      for (const child of childSitemaps) {
        if (!sitemapsParsed.has(child)) {
          queue.push({ url: child, depth: current.depth + 1 });
        }
      }
    } catch {
      // Continue on fetch error
    }
  }

  return {
    allUrls: Array.from(allUrls),
    sitemapsParsed: Array.from(sitemapsParsed)
  };
}

/**
 * Traces HTTP redirects for a given URL and flags redirect chains or loops
 */
export async function traceRedirects(
  startUrl: string,
  maxHops = 5,
  fetchFn?: (url: string) => Promise<{ status: number; location?: string }>
): Promise<RedirectTrace> {
  const hops: { url: string; status: number }[] = [];
  const visited = new Set<string>();
  let current = startUrl;
  let isLoop = false;

  for (let i = 0; i < maxHops; i++) {
    if (visited.has(current)) {
      isLoop = true;
      hops.push({ url: current, status: 301 });
      break;
    }
    visited.add(current);

    if (fetchFn) {
      try {
        const res = await fetchFn(current);
        hops.push({ url: current, status: res.status });
        if ([301, 302, 303, 307, 308].includes(res.status) && res.location) {
          const next = normalizeUrl(res.location, current);
          if (next) {
            current = next;
            continue;
          }
        }
      } catch {
        break;
      }
    } else {
      // Live fetch with redirect: 'manual'
      try {
        const res = await fetch(current, {
          method: 'GET',
          redirect: 'manual',
          headers: { 'User-Agent': 'Mozilla/5.0 (compatible; SanoceaSeoBot/1.0)' }
        });
        hops.push({ url: current, status: res.status });
        if ([301, 302, 303, 307, 308].includes(res.status)) {
          const loc = res.headers.get('location');
          if (loc) {
            const next = normalizeUrl(loc, current);
            if (next) {
              current = next;
              continue;
            }
          }
        }
      } catch {
        break;
      }
    }
    break;
  }

  return {
    initialUrl: startUrl,
    finalUrl: current,
    hops,
    isLoop,
    hopCount: Math.max(0, hops.length - 1)
  };
}

/**
 * Builds a comprehensive crawl graph across crawled pages and detects orphans
 */
export function buildCrawlGraph(
  crawledPages: Map<string, CrawledPage>,
  sitemapUrls: Set<string> = new Set()
): { graph: Map<string, CrawlGraphNode>; summary: CrawlGraphSummary } {
  const graph = new Map<string, CrawlGraphNode>();

  // Initialize nodes for all crawled pages
  for (const [url, page] of crawledPages) {
    const $ = cheerio.load(page.renderedHtml || page.rawHtml);
    const bodyText = $('body').text().replace(/\s+/g, ' ').trim();
    const wordCount = bodyText.split(' ').filter(Boolean).length;

    graph.set(url, {
      url,
      inLinks: [],
      outLinks: [],
      inDegree: 0,
      outDegree: 0,
      depth: 0,
      isOrphan: false,
      status: page.status,
      title: $('title').first().text().trim() || undefined,
      h1: $('h1').first().text().trim() || undefined,
      wordCount
    });
  }

  // Also initialize nodes for sitemap URLs not yet crawled
  for (const sUrl of sitemapUrls) {
    if (!graph.has(sUrl)) {
      graph.set(sUrl, {
        url: sUrl,
        inLinks: [],
        outLinks: [],
        inDegree: 0,
        outDegree: 0,
        depth: 99,
        isOrphan: true, // Initially orphan until proven linked
        status: 0
      });
    }
  }

  // Populate edges from crawled page links
  let totalEdges = 0;
  for (const [sourceUrl, page] of crawledPages) {
    const sourceNode = graph.get(sourceUrl);
    if (!sourceNode) continue;

    for (const discovered of page.discoveredUrls) {
      if (discovered.source === 'internal_link') {
        const targetUrl = discovered.url;
        if (!sourceNode.outLinks.includes(targetUrl)) {
          sourceNode.outLinks.push(targetUrl);
          totalEdges++;
        }

        const targetNode = graph.get(targetUrl);
        if (targetNode) {
          if (!targetNode.inLinks.includes(sourceUrl)) {
            targetNode.inLinks.push(sourceUrl);
          }
        }
      }
    }
  }

  // Compute inDegree, outDegree, and orphan flags
  const orphanPages: string[] = [];
  const deepestPages: { url: string; depth: number }[] = [];
  const highestInDegreePages: { url: string; inDegree: number }[] = [];

  for (const [url, node] of graph) {
    node.inDegree = node.inLinks.length;
    node.outDegree = node.outLinks.length;

    // Orphan check: If inDegree is 0 and it's not the seed/homepage, it is an orphan
    const parsed = new URL(url);
    const isRoot = parsed.pathname === '/' || parsed.pathname === '';

    if (node.inDegree === 0 && !isRoot) {
      node.isOrphan = true;
      orphanPages.push(url);
    }

    highestInDegreePages.push({ url, inDegree: node.inDegree });
  }

  highestInDegreePages.sort((a, b) => b.inDegree - a.inDegree);

  const summary: CrawlGraphSummary = {
    totalNodes: graph.size,
    totalEdges,
    orphanPages,
    deepestPages,
    highestInDegreePages: highestInDegreePages.slice(0, 10)
  };

  return { graph, summary };
}

/**
 * Parses robots.txt to discover declared sitemaps, per-agent disallow rules and AI bot directives.
 * Group semantics follow RFC 9309 (see aiCrawlerPolicy.ts): rules apply to every user-agent of their group.
 */
export function parseRobotsTxt(robotsContent: string): {
  sitemaps: string[];
  disallowRules: Record<string, string[]>;
  aiBotDirectives: Record<string, AiBotDirective>;
} {
  const sitemaps: string[] = [];
  for (const rawLine of robotsContent.split(/\r?\n/)) {
    const line = rawLine.split('#')[0].trim();
    const colonIdx = line.indexOf(':');
    if (colonIdx === -1 || line.slice(0, colonIdx).trim().toLowerCase() !== 'sitemap') continue;
    const normalized = normalizeUrl(line.slice(colonIdx + 1).trim());
    if (normalized && !sitemaps.includes(normalized)) sitemaps.push(normalized);
  }

  const disallowRules: Record<string, string[]> = {};
  for (const group of parseRobotsGroups(robotsContent)) {
    for (const agent of group.agents) {
      disallowRules[agent] = disallowRules[agent] ?? [];
      for (const rule of group.rules) if (rule.type === 'disallow') disallowRules[agent].push(rule.path);
    }
  }

  return { sitemaps, disallowRules, aiBotDirectives: buildAiBotDirectives(robotsContent) };
}
