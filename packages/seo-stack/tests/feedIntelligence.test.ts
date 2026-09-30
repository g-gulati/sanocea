/**
 * SANOCEA SEO Stack — Phase 4 Commerce Intelligence Test Suite
 * 
 * Verifies:
 * 1. Google Merchant Center TSV feed ingestion
 * 2. Google Merchant Center XML (RSS 2.0) feed ingestion
 * 3. Deterministic storefront-vs-feed reconciliation
 * 4. Evidentiary provenance ([OBSERVED] / [CALCULATED] / [REQUIRES_ACCESS]) on feed discrepancies
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseGmcTsvFeed, parseGmcXmlFeed, parseGmcFeed, parseGmcPrice } from '../src/commerce/feedIngester.js';
import { reconcileGmcFeed, extractStorefrontProductSnapshot } from '../src/commerce/feedReconciler.js';
import { CrawledPage } from '../src/core/types.js';

test('Phase 4.1 — GMC Feed Ingestion: TSV and XML Parsers', () => {
  // Test Price Parsing
  assert.deepEqual(parseGmcPrice('2499.00 INR'), { price: 2499, currency: 'INR' });
  assert.deepEqual(parseGmcPrice('₹18,499.50'), { price: 18499.5, currency: 'INR' });
  assert.deepEqual(parseGmcPrice('USD 49.99'), { price: 49.99, currency: 'USD' });

  // 1. TSV Google Merchant Center Feed
  const sampleTsv = [
    'id\ttitle\tdescription\tlink\timage_link\tavailability\tprice\tsale_price\tbrand\tgtin',
    'WAA-INV-5KW\tWaaree 5kW Solar Inverter\tHigh efficiency solar inverter\thttps://shop.waaree.com/products/inverter-5kw\thttps://cdn.example.com/inv.jpg\tin_stock\t28999.00 INR\t24999.00 INR\tWaaree\t8901234567890',
    'WAA-BAT-100AH\tWaaree 100Ah Lithium Battery\tLithium solar storage\thttps://shop.waaree.com/products/battery-100ah\thttps://cdn.example.com/bat.jpg\tout_of_stock\t45000.00 INR\t\tWaaree\t8909876543210'
  ].join('\n');

  const tsvProducts = parseGmcTsvFeed(sampleTsv);
  assert.equal(tsvProducts.length, 2);
  assert.equal(tsvProducts[0].id, 'WAA-INV-5KW');
  assert.equal(tsvProducts[0].salePrice, 24999);
  assert.equal(tsvProducts[0].price, 28999);
  assert.equal(tsvProducts[0].availability, 'in_stock');
  assert.equal(tsvProducts[1].availability, 'out_of_stock');
  assert.equal(tsvProducts[1].price, 45000);

  // 2. XML Google RSS 2.0 Feed
  const sampleXml = `<?xml version="1.0"?>
    <rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">
      <channel>
        <title>Waaree Store Product Feed</title>
        <link>https://shop.waaree.com</link>
        <item>
          <g:id>WAA-PANEL-330W</g:id>
          <g:title>Waaree 330W Polycrystalline Solar Panel</g:title>
          <g:link>https://shop.waaree.com/products/panel-330w</g:link>
          <g:price>10500.00 INR</g:price>
          <g:availability>in_stock</g:availability>
          <g:brand>Waaree</g:brand>
          <g:gtin>8904567890123</g:gtin>
        </item>
      </channel>
    </rss>
  `;

  const xmlProducts = parseGmcXmlFeed(sampleXml);
  assert.equal(xmlProducts.length, 1);
  assert.equal(xmlProducts[0].id, 'WAA-PANEL-330W');
  assert.equal(xmlProducts[0].price, 10500);
  assert.equal(xmlProducts[0].availability, 'in_stock');
  assert.equal(xmlProducts[0].brand, 'Waaree');

  // Auto-detect Feed Format
  assert.equal(parseGmcFeed(sampleTsv).length, 2);
  assert.equal(parseGmcFeed(sampleXml).length, 1);
});

test('Phase 4.2 — Feed vs Storefront DOM Reconciler: Deterministic Discrepancy Detection', () => {
  // Feed declared products
  const feedProducts = [
    // Product 1: Feed says ₹24,999 sale price, but live storefront is ₹28,999 (Price Mismatch!)
    {
      id: 'SKU-INV-01',
      title: 'Solar Inverter 5kW',
      link: 'https://shop.waaree.com/products/inverter-5kw',
      price: 32000,
      salePrice: 24999,
      currency: 'INR',
      availability: 'in_stock' as const,
      brand: 'Waaree',
      gtin: '8901234567890'
    },
    // Product 2: Feed says in_stock, but live storefront DOM shows Sold Out (Account Suspension Risk!)
    {
      id: 'SKU-BAT-02',
      title: 'Lithium Battery 48V',
      link: 'https://shop.waaree.com/products/battery-48v',
      price: 65000,
      currency: 'INR',
      availability: 'in_stock' as const,
      brand: 'Waaree',
      gtin: '8901234567891'
    },
    // Product 3: Feed URL 404s on storefront
    {
      id: 'SKU-DISC-03',
      title: 'Discontinued Cable',
      link: 'https://shop.waaree.com/products/cable-solar-10m',
      price: 1200,
      currency: 'INR',
      availability: 'in_stock' as const,
      brand: 'Waaree'
    }
  ];

  // Mock crawled storefront pages
  const crawledPages = new Map<string, CrawledPage>();

  // Page 1: Storefront price is ₹28,999 (contradicting feed sale price ₹24,999)
  crawledPages.set('https://shop.waaree.com/products/inverter-5kw', {
    url: 'https://shop.waaree.com/products/inverter-5kw',
    status: 200,
    headers: { 'content-type': 'text/html' },
    rawHtml: `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Solar Inverter 5kW</title>
          <script type="application/ld+json">
            {
              "@type": "Product",
              "name": "Solar Inverter 5kW",
              "offers": {
                "@type": "Offer",
                "price": "28999.00",
                "priceCurrency": "INR",
                "availability": "https://schema.org/InStock"
              }
            }
          </script>
        </head>
        <body>
          <h1 class="product-title">Solar Inverter 5kW</h1>
          <span class="price">₹28,999</span>
          <button class="add-to-cart">Add to Cart</button>
        </body>
      </html>
    `,
    isJsRendered: false,
    executionTimeMs: 50,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  });

  // Page 2: Storefront DOM shows Sold Out button
  crawledPages.set('https://shop.waaree.com/products/battery-48v', {
    url: 'https://shop.waaree.com/products/battery-48v',
    status: 200,
    headers: { 'content-type': 'text/html' },
    rawHtml: `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Lithium Battery 48V</title>
        </head>
        <body>
          <h1>Lithium Battery 48V</h1>
          <span class="price">₹65,000</span>
          <button disabled class="out-of-stock">Sold Out</button>
        </body>
      </html>
    `,
    isJsRendered: false,
    executionTimeMs: 40,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  });

  // Page 3: Dead 404 endpoint
  crawledPages.set('https://shop.waaree.com/products/cable-solar-10m', {
    url: 'https://shop.waaree.com/products/cable-solar-10m',
    status: 404,
    headers: { 'content-type': 'text/html' },
    rawHtml: '<html><body>404 Not Found</body></html>',
    isJsRendered: false,
    executionTimeMs: 30,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  });

  // Run Feed Reconciliation
  const findings = reconcileGmcFeed(feedProducts, crawledPages);

  // 1. Assert Price Mismatch Finding
  const priceFinding = findings.find(f => f.detectionRule === 'GMC_FEED_PRICE_MISMATCH');
  assert.ok(priceFinding, 'Must detect GMC_FEED_PRICE_MISMATCH');
  assert.equal(priceFinding.severity, 'CRITICAL');
  assert.equal(priceFinding.evidenceClass, '[O] Observed');
  assert.equal(priceFinding.exactEvidence.priceFound, 28999);
  assert.equal(priceFinding.exactEvidence.priceExpected, 24999);
  assert.equal(priceFinding.commercialRisk?.confidence, '[REQUIRES_ACCESS]');
  assert.equal(priceFinding.commercialRisk?.observedDataPoints?.priceDelta, 4000);

  // 2. Assert Availability Contradiction Finding
  const availFinding = findings.find(f => f.detectionRule === 'GMC_FEED_AVAILABILITY_CONTRADICTION');
  assert.ok(availFinding, 'Must detect GMC_FEED_AVAILABILITY_CONTRADICTION');
  assert.equal(availFinding.severity, 'CRITICAL');
  assert.equal(availFinding.commercialRisk?.riskType, 'GMC_ACCOUNT_SUSPENSION');
  assert.equal(availFinding.exactEvidence.stockFound, 'out_of_stock');
  assert.equal(availFinding.exactEvidence.stockExpected, 'in_stock');

  // 3. Assert Dead Landing Page URL Finding
  const deadUrlFinding = findings.find(f => f.detectionRule === 'GMC_FEED_URL_BROKEN');
  assert.ok(deadUrlFinding, 'Must detect GMC_FEED_URL_BROKEN on HTTP 404');
  assert.equal(deadUrlFinding.severity, 'CRITICAL');
});
