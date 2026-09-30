/**
 * SANOCEA SEO Stack — Dual-Engine Crawler with JS Escalation Trigger
 * Stage 1: Fast HTTP Crawl (Node 20 fetch + Cheerio)
 * Stage 2: JS/Playwright Escalation when Single-Page App or dynamic DOM is detected
 * Hardened for Scale: Bounded concurrency worker pool, streaming memory management,
 * and comprehensive crawl statistics.
 */

import * as cheerio from 'cheerio';
import { CrawlConfig, CrawledPage, DiscoveredUrl, CrawlStats, OutboundLinkTarget } from './types.js';
import { extractPageLinks, extractOutboundLinks, normalizeUrl } from './urlDiscovery.js';
import { BrowserPool } from './browserPool.js';

export interface JsEscalationResult {
  needsEscalation: boolean;
  reasons: string[];
}

/**
 * Heuristics to detect if an HTML response requires JavaScript rendering
 */
export function evaluateJsEscalationNeed(html: string): JsEscalationResult {
  const $ = cheerio.load(html);
  const reasons: string[] = [];

  // Check 1: Empty root/app container (Vite/React/Next/Vue client-side mount)
  const root = $('#root, #app, #__next');
  if (root.length > 0 && root.children().length === 0) {
    reasons.push('Empty client-side mount container (#root/#app/#__next)');
  }

  // Check 2: Raw HTML contains 0 <h1> tags but contains client-side script bundles
  const h1Count = $('h1').length;
  const scriptModules = $('script[type="module"], script[src*="vite"], script[src*="main"]').length;
  if (h1Count === 0 && scriptModules > 0) {
    reasons.push('Missing SSR <h1> while modern JS module bundle is present');
  }

  // Check 3: Zero internal links found in raw HTML body
  const internalLinks = $('a[href]').length;
  if (internalLinks === 0) {
    reasons.push('Zero internal <a> links present in raw server-rendered HTML');
  }

  // Check 4: Minimal body text length while scripts are loaded (< 100 words)
  const bodyText = $('body').text().replace(/\s+/g, ' ').trim();
  const wordCount = bodyText.split(' ').filter(Boolean).length;
  if (wordCount < 40 && scriptModules > 0) {
    reasons.push(`Low SSR text word count (${wordCount} words) with client bundle present`);
  }

  return {
    needsEscalation: reasons.length > 0,
    reasons
  };
}

/**
 * Probes an external target URL using lightweight HEAD (falling back to GET)
 */
export async function probeOutboundUrl(
  url: string,
  timeoutMs = 3000
): Promise<{ status: number; ok: boolean; error?: string }> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let res: Response;
    try {
      res = await fetch(url, {
        method: 'HEAD',
        signal: controller.signal,
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; SanoceaOutboundChecker/1.0; +https://www.sanocea.com/bot)'
        }
      });
      // 405 Method Not Allowed or 501 Not Implemented on HEAD -> retry with GET
      if (res.status === 405 || res.status === 501) {
        res = await fetch(url, {
          method: 'GET',
          signal: controller.signal,
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; SanoceaOutboundChecker/1.0; +https://www.sanocea.com/bot)'
          }
        });
      }
    } finally {
      clearTimeout(timer);
    }

    const ok = res.status >= 200 && res.status < 400;
    return {
      status: res.status,
      ok,
      error: ok ? undefined : `HTTP ${res.status}`
    };
  } catch (err: any) {
    const isTimeout = err.name === 'AbortError' || err.message?.includes('timeout') || err.message?.includes('aborted');
    return {
      status: 0,
      ok: false,
      error: isTimeout ? 'Connection Timeout (ETIMEDOUT)' : (err.code || err.message || 'Unreachable Destination')
    };
  }
}

/**
 * Concurrently probes multiple outbound links with bounded concurrency
 */
export async function probeOutboundLinks(
  outboundLinks: OutboundLinkTarget[],
  options: { maxConcurrency?: number; timeoutMs?: number } = {}
): Promise<OutboundLinkTarget[]> {
  const concurrency = Math.max(1, Math.min(options.maxConcurrency ?? 5, 10));
  const timeoutMs = options.timeoutMs ?? 3000;
  const results: OutboundLinkTarget[] = [];
  const queue = [...outboundLinks];

  const worker = async () => {
    while (queue.length > 0) {
      const link = queue.shift();
      if (!link) break;

      const probeResult = await probeOutboundUrl(link.url, timeoutMs);
      results.push({
        ...link,
        status: probeResult.status,
        error: probeResult.error,
        isDead: !probeResult.ok
      });
    }
  };

  const workers = Array.from({ length: Math.min(concurrency, outboundLinks.length) }, () => worker());
  await Promise.all(workers);

  return results;
}

export type RenderCallback = (url: string, rawHtml: string) => Promise<string>;

export class DualEngineCrawler {
  private config: CrawlConfig;
  private visitedUrls = new Set<string>();
  private queuedUrls = new Set<string>();
  private queue: DiscoveredUrl[] = [];
  private crawledPages = new Map<string, CrawledPage>();
  private customRenderer?: RenderCallback;
  private stats: CrawlStats = {
    discoveredUrlsCount: 0,
    crawledUrlsCount: 0,
    skippedUrlsCount: 0,
    failedUrlsCount: 0,
    jsEscalatedUrlsCount: 0,
    deduplicatedUrlsCount: 0,
    peakHeapUsedMb: 0
  };

  constructor(config: CrawlConfig, customRenderer?: RenderCallback) {
    this.config = config;
    this.customRenderer = customRenderer;
    this.updateHeapMetric();
  }

  private updateHeapMetric(): void {
    const heapMb = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
    if (heapMb > this.stats.peakHeapUsedMb) {
      this.stats.peakHeapUsedMb = heapMb;
    }
  }

  public getCrawlStats(): CrawlStats {
    this.updateHeapMetric();
    return { ...this.stats };
  }

  public registerSeed(url: string): void {
    const normalized = normalizeUrl(url);
    if (normalized && !this.visitedUrls.has(normalized) && !this.queuedUrls.has(normalized)) {
      this.queuedUrls.add(normalized);
      this.stats.discoveredUrlsCount++;
      this.queue.push({
        url: normalized,
        source: 'seed',
        depth: 0
      });
    }
  }

  public registerDiscoveredUrl(url: string, source: DiscoveredUrl['source'], depth = 1): void {
    const normalized = normalizeUrl(url);
    if (!normalized) return;

    this.stats.discoveredUrlsCount++;

    if (this.visitedUrls.has(normalized) || this.queuedUrls.has(normalized)) {
      this.stats.deduplicatedUrlsCount++;
      return;
    }

    if (depth > this.config.maxDepth) {
      this.stats.skippedUrlsCount++;
      return;
    }

    this.queuedUrls.add(normalized);
    this.queue.push({
      url: normalized,
      source,
      depth
    });
  }

  /**
   * Crawls a single page via fast HTTP with JS escalation detection
   */
  public async crawlSingle(url: string): Promise<CrawledPage> {
    const startTime = Date.now();
    let status = 0;
    const headers: Record<string, string> = {};
    let rawHtml = '';
    let renderedHtml: string | undefined;
    let isJsRendered = false;

    try {
      const resp = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; SanoceaSeoBot/1.0; +https://www.sanocea.com/bot)',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        },
        redirect: 'follow'
      });

      status = resp.status;
      resp.headers.forEach((val, key) => {
        headers[key.toLowerCase()] = val;
      });

      rawHtml = await resp.text();

      // Check if JS rendering escalation is required
      const escalation = evaluateJsEscalationNeed(rawHtml);
      if (escalation.needsEscalation && this.config.enableJsRendering) {
        this.stats.jsEscalatedUrlsCount++;
        if (this.customRenderer) {
          renderedHtml = await this.customRenderer(url, rawHtml);
          isJsRendered = true;
        } else {
          try {
            const browserPool = BrowserPool.getInstance();
            const renderResult = await browserPool.renderUrl(url);
            renderedHtml = renderResult.renderedHtml;
            isJsRendered = true;
          } catch {
            renderedHtml = undefined;
          }
        }
      }

      if (status >= 400) {
        this.stats.failedUrlsCount++;
      } else {
        this.stats.crawledUrlsCount++;
      }
    } catch (err: any) {
      status = 500;
      rawHtml = `<html><body>Crawler error: ${err.message}</body></html>`;
      this.stats.failedUrlsCount++;
    }

    const durationMs = Date.now() - startTime;
    const htmlToAnalyze = renderedHtml || rawHtml;
    const links = extractPageLinks(htmlToAnalyze, url, this.config.seedUrl, this.config.allowSubdomains);
    let outboundLinks = extractOutboundLinks(htmlToAnalyze, url, this.config.seedUrl, this.config.allowSubdomains);

    if (this.config.probeOutboundLinks && outboundLinks.length > 0) {
      try {
        outboundLinks = await probeOutboundLinks(outboundLinks);
      } catch {}
    }

    // Memory discipline: For scale crawls, discard heavy raw response bodies if retainRawHtml is false
    const shouldRetain = this.config.retainRawHtml ?? true;
    const storedRawHtml = shouldRetain ? rawHtml : '';
    const storedRenderedHtml = shouldRetain ? renderedHtml : undefined;

    const crawledPage: CrawledPage = {
      url,
      status,
      headers,
      rawHtml: storedRawHtml,
      renderedHtml: storedRenderedHtml,
      isJsRendered,
      executionTimeMs: durationMs,
      discoveredUrls: links,
      outboundLinks,
      crawledAt: new Date().toISOString()
    };

    this.visitedUrls.add(url);
    this.crawledPages.set(url, crawledPage);
    this.updateHeapMetric();

    return crawledPage;
  }

  /**
   * Executes bounded concurrent crawl across discovered URLs with streaming queue
   */
  public async crawlAll(): Promise<Map<string, CrawledPage>> {
    const concurrency = Math.max(1, Math.min(this.config.concurrency || 5, 20));
    const delayMs = this.config.interRequestDelayMs ?? 20;
    let inFlight = 0;

    const worker = async () => {
      while (this.queue.length > 0) {
        if (this.crawledPages.size + inFlight >= this.config.maxPages) {
          break;
        }

        const item = this.queue.shift();
        if (!item) break;

        const normalized = normalizeUrl(item.url);
        if (!normalized || this.visitedUrls.has(normalized)) {
          this.stats.deduplicatedUrlsCount++;
          continue;
        }

        if (item.depth > this.config.maxDepth) {
          this.stats.skippedUrlsCount++;
          continue;
        }

        this.visitedUrls.add(normalized);
        inFlight++;

        try {
          if (this.crawledPages.size < this.config.maxPages) {
            const page = await this.crawlSingle(normalized);

            // Queue newly discovered links
            for (const link of page.discoveredUrls) {
              this.registerDiscoveredUrl(link.url, link.source, item.depth + 1);
            }
          }
        } finally {
          inFlight--;
        }

        if (delayMs > 0) {
          await new Promise(r => setTimeout(r, delayMs));
        }
      }
    };

    // Spawn bounded concurrent worker pool
    const workers: Promise<void>[] = [];
    for (let i = 0; i < concurrency; i++) {
      workers.push(worker());
    }

    await Promise.all(workers);
    this.updateHeapMetric();

    return this.crawledPages;
  }

  public async close(): Promise<void> {
    await BrowserPool.getInstance().close();
  }
}
