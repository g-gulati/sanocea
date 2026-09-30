/**
 * SANOCEA SEO Stack — Phase 3 Crawler Scale & Memory Benchmark
 * 
 * Tests:
 * 1. Compressed .xml.gz sitemap ingestion & recursive index expansion
 * 2. Bounded concurrency worker pool
 * 3. 5,000+ URL ecommerce corpus scale test
 * 4. Controlled memory usage (< 200MB heap) with streaming/discarded body discipline
 * 5. Full crawl accounting: discovered, crawled, skipped, failed, JS-escalated, deduplicated
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as zlib from 'node:zlib';
import * as http from 'node:http';
import { parseSitemapXmlRecursive, decompressIfGzip } from '../src/core/urlDiscovery.js';
import { DualEngineCrawler } from '../src/core/crawler.js';

test('Phase 3.1 — Compressed .xml.gz Sitemap Support & Recursive Parsing', async () => {
  // 1. Generate 500 child product URLs
  const childUrls: string[] = [];
  for (let i = 1; i <= 500; i++) {
    childUrls.push(`https://shop.example.com/products/solar-panel-${i}`);
  }

  const childXml = `<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      ${childUrls.map(u => `<url><loc>${u}</loc><changefreq>weekly</changefreq></url>`).join('\n')}
    </urlset>
  `;

  // Compress child sitemap into gzip binary buffer
  const gzippedBuffer = zlib.gzipSync(Buffer.from(childXml, 'utf-8'));

  // Parent sitemapindex pointing to the .xml.gz child sitemap
  const indexXml = `<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap>
        <loc>https://shop.example.com/sitemaps/products.xml.gz</loc>
      </sitemap>
    </sitemapindex>
  `;

  // Mock fetchFn returning string for index and Buffer for .xml.gz
  const mockFetch = async (url: string): Promise<string | Buffer> => {
    if (url.endsWith('.xml.gz')) {
      return gzippedBuffer;
    }
    return indexXml;
  };

  const result = await parseSitemapXmlRecursive(
    'https://shop.example.com/sitemap.xml',
    'https://shop.example.com/',
    mockFetch
  );

  assert.equal(result.sitemapsParsed.length, 2, 'Must parse both parent index and child .xml.gz');
  assert.equal(result.allUrls.length, 500, 'Must discover all 500 URLs inside the gzipped sitemap');
  assert.ok(result.allUrls.includes('https://shop.example.com/products/solar-panel-1'));
  assert.ok(result.allUrls.includes('https://shop.example.com/products/solar-panel-500'));
});

test('Phase 3.2 — 5,000+ URL Ecommerce Scale & Controlled Memory Footprint (<200MB)', async () => {
  // Build a representative 5,000+ URL synthetic catalog
  // - 4,000 PDPs
  // - 500 Collections
  // - 300 Duplicate parameter variants
  // - 200 Out-of-depth URLs
  const TOTAL_URLS = 5000;

  const catalogUrls: string[] = [];
  for (let i = 1; i <= 4000; i++) {
    catalogUrls.push(`http://127.0.0.1:9999/products/item-${i}`);
  }
  for (let i = 1; i <= 500; i++) {
    catalogUrls.push(`http://127.0.0.1:9999/collections/category-${i}`);
  }
  for (let i = 1; i <= 300; i++) {
    // Duplicate URLs with tracking or variant query parameters
    catalogUrls.push(`http://127.0.0.1:9999/products/item-${i}?utm_source=google&gclid=test`);
  }
  for (let i = 1; i <= 200; i++) {
    catalogUrls.push(`http://127.0.0.1:9999/deep/nested/page-${i}`);
  }

  assert.equal(catalogUrls.length, TOTAL_URLS, 'Corpus must contain 5,000 URLs');

  // Initialize DualEngineCrawler in streaming/bounded scale mode
  const crawler = new DualEngineCrawler({
    seedUrl: 'http://127.0.0.1:9999/',
    maxPages: 100, // Crawl a bounded batch of 100 pages while ingesting the full 5,000 URL pool
    maxDepth: 1,
    allowSubdomains: false,
    enableJsRendering: false,
    concurrency: 8,
    interRequestDelayMs: 0,
    retainRawHtml: false // Memory discipline: Discard full raw response bodies after extraction
  });

  // Register all 5,000 URLs into the discovery queue
  crawler.registerSeed('http://127.0.0.1:9999/');
  for (let i = 0; i < catalogUrls.length; i++) {
    const isDeep = catalogUrls[i].includes('/deep/');
    crawler.registerDiscoveredUrl(catalogUrls[i], 'internal_link', isDeep ? 3 : 1);
  }

  // Spin up an in-memory fast mock HTTP server responding to crawler batch
  const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(`
      <!DOCTYPE html>
      <html>
        <head><title>Product ${req.url}</title></head>
        <body>
          <h1>Product Listing</h1>
          <p>Standard ecommerce catalogue description with semantic tags.</p>
        </body>
      </html>
    `);
  });

  await new Promise<void>((resolve) => server.listen(9999, '127.0.0.1', () => resolve()));

  try {
    const initialHeapMb = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);

    // Execute bounded crawl across the 5,000 URL pool
    const crawledMap = await crawler.crawlAll();
    const stats = crawler.getCrawlStats();

    const finalHeapMb = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);

    // Verify Crawl Accounting
    assert.ok(stats.discoveredUrlsCount >= 5000, `Must discover 5,000+ URLs (observed: ${stats.discoveredUrlsCount})`);
    assert.ok(stats.deduplicatedUrlsCount >= 300, `Must identify and deduplicate parameter URLs (observed: ${stats.deduplicatedUrlsCount})`);
    assert.ok(stats.skippedUrlsCount >= 200, `Must skip out-of-depth URLs (observed: ${stats.skippedUrlsCount})`);
    assert.equal(crawledMap.size, 100, 'Must respect maxPages ceiling with bounded concurrency');
    assert.equal(stats.crawledUrlsCount, 100, 'Must record exactly 100 completed page crawls');

    // Verify Memory Discipline: Peak Heap must remain < 200 MB
    assert.ok(stats.peakHeapUsedMb < 200, `Peak heap usage (${stats.peakHeapUsedMb} MB) must remain < 200 MB`);
    assert.ok(finalHeapMb < 200, `Final heap usage (${finalHeapMb} MB) must remain < 200 MB`);

    // Verify that crawled pages in memory do NOT retain bulky rawHtml strings
    for (const page of crawledMap.values()) {
      assert.equal(page.rawHtml, '', 'Raw HTML must be discarded for streaming memory discipline');
    }
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
    await crawler.close();
  }
});
