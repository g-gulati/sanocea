/**
 * SANOCEA SEO Stack — Google Merchant Center Feed Reconciler
 * 
 * Compares ingested Google Merchant Center catalog records against live storefront DOM
 * to detect deterministic discrepancies with strict evidentiary provenance.
 */

import * as cheerio from 'cheerio';
import { GmcFeedProduct } from './feedIngester.js';
import { CrawledPage, SeoFinding } from '../core/types.js';
import { normalizeUrl } from '../core/urlDiscovery.js';

export interface StorefrontProductSnapshot {
  url: string;
  domPrice?: number;
  schemaPrice?: number;
  effectivePrice?: number;
  domStockState?: 'in_stock' | 'out_of_stock';
  schemaStockState?: 'in_stock' | 'out_of_stock';
  effectiveStockState?: 'in_stock' | 'out_of_stock';
  brand?: string;
  gtin?: string;
}

/**
 * Extracts product commerce attributes from a crawled HTML page
 */
export function extractStorefrontProductSnapshot(page: CrawledPage): StorefrontProductSnapshot {
  const $ = cheerio.load(page.renderedHtml || page.rawHtml);
  const snapshot: StorefrontProductSnapshot = { url: page.url };

  // 1. Extract JSON-LD Offer Price and Stock
  $('script[type="application/ld+json"]').each((_, el) => {
    try {
      const data = JSON.parse($(el).text());
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        if (item['@type'] === 'Product' || item.offers) {
          if (item.brand?.name) snapshot.brand = item.brand.name;
          if (item.gtin13 || item.gtin || item.sku) snapshot.gtin = item.gtin13 || item.gtin || item.sku;

          const offers = Array.isArray(item.offers) ? item.offers[0] : item.offers;
          if (offers) {
            if (offers.price !== undefined) {
              snapshot.schemaPrice = parseFloat(offers.price);
            }
            if (offers.availability) {
              snapshot.schemaStockState = offers.availability.includes('InStock') ? 'in_stock' : 'out_of_stock';
            }
          }
        }
      }
    } catch {
      // Ignore JSON parse errors in script tags
    }
  });

  // 2. Extract Visible DOM Price
  const priceSelectors = [
    '[data-price]', '.price', '.product-price', '.current-price', '.regular-price',
    'span.price-item', '.special-price', '.sale-price', '.price__current'
  ];
  for (const sel of priceSelectors) {
    const text = $(sel).first().text().trim();
    if (text) {
      const match = text.replace(/,/g, '').match(/(?:₹|INR|Rs\.?|\$)\s*([\d.]+)/i) || text.replace(/,/g, '').match(/([\d.]+)/);
      if (match && parseFloat(match[1]) > 0) {
        snapshot.domPrice = parseFloat(match[1]);
        break;
      }
    }
  }

  // 3. Extract Visible DOM Stock
  const bodyText = $('body').text().toLowerCase();
  const oosSignals = ['out of stock', 'sold out', 'currently unavailable', 'notify me when available'];
  const hasOos = oosSignals.some(s => {
    const btnText = $('button:disabled, .out-of-stock, .badge--sold-out, [data-sold-out]').text().toLowerCase();
    return btnText.includes(s) || bodyText.includes(s);
  });

  snapshot.domStockState = hasOos ? 'out_of_stock' : 'in_stock';
  snapshot.effectivePrice = snapshot.domPrice ?? snapshot.schemaPrice;
  snapshot.effectiveStockState = snapshot.domStockState;

  return snapshot;
}

/**
 * Reconciles a list of GMC feed products against crawled pages
 */
export function reconcileGmcFeed(
  feedProducts: GmcFeedProduct[],
  crawledPages: Map<string, CrawledPage>
): SeoFinding[] {
  const findings: SeoFinding[] = [];
  const now = new Date().toISOString();

  // Index crawled pages by normalized URL
  const pageMap = new Map<string, CrawledPage>();
  for (const [url, page] of crawledPages.entries()) {
    const norm = normalizeUrl(url);
    if (norm) pageMap.set(norm, page);
  }

  for (const feedItem of feedProducts) {
    const normLink = normalizeUrl(feedItem.link);
    if (!normLink) continue;

    const page = pageMap.get(normLink);
    if (!page) {
      // If page was not crawled in this scope, skip
      continue;
    }

    if (page.status === 404 || page.status >= 500) {
      findings.push({
        findingId: `SAN-GMC-FEED-DEAD-LINK-${feedItem.id}`,
        url: feedItem.link,
        routeIntent: 'PRODUCT_DISPLAY_PAGE',
        detectionRule: 'GMC_FEED_URL_BROKEN',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
        category: 'Ecommerce',
        severity: 'CRITICAL',
        evidenceClass: '[O] Observed',
        observedValue: `HTTP Status ${page.status} on storefront`,
        expectedValue: 'HTTP 200 OK for live Google Shopping feed destination',
        exactEvidence: {
          rawContext: `GMC Feed SKU ${feedItem.id} links to dead endpoint (${page.status})`
        },
        reproductionMethod: `curl -sI '${feedItem.link}'`,
        businessImpact: 'Google Merchant Center will disapprove product and penalize account for broken landing page destinations.',
        commercialRisk: {
          riskType: 'GMC_ACCOUNT_SUSPENSION',
          title: 'Google Merchant Center Broken Landing Page Disapproval',
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'requires_merchant_telemetry',
          severityScore: 5,
          calculationFormula: `Product ${feedItem.id} disapproved in Google Shopping [REQUIRES_ACCESS]`,
          affectedSkus: [feedItem.id],
          affectedChannels: ['Google Shopping', 'Performance Max Ads']
        },
        recommendedRemediation: 'Update GMC feed URL to live canonical product page or restore page status 200.',
        automaticallyFixable: true,
        requiredAccess: 'Feed & Merchant Center',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: `HTTP ${page.status}`,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
      continue;
    }

    const snapshot = extractStorefrontProductSnapshot(page);

    // ── Check 1: Price Mismatch (Feed Price vs Storefront Price) ────────
    const effectiveStorefrontPrice = snapshot.effectivePrice;
    const feedPrice = feedItem.salePrice ?? feedItem.price;

    if (effectiveStorefrontPrice !== undefined && feedPrice > 0) {
      const priceDelta = Math.abs(effectiveStorefrontPrice - feedPrice);
      if (priceDelta >= 1) { // Difference >= ₹1
        findings.push({
          findingId: `SAN-GMC-PRICE-MISMATCH-${feedItem.id}`,
          url: feedItem.link,
          routeIntent: 'PRODUCT_DISPLAY_PAGE',
          detectionRule: 'GMC_FEED_PRICE_MISMATCH',
          track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
          category: 'Ecommerce',
          severity: 'CRITICAL',
          evidenceClass: '[O] Observed',
          observedValue: `Storefront: ₹${effectiveStorefrontPrice.toLocaleString('en-IN')} vs GMC Feed: ₹${feedPrice.toLocaleString('en-IN')}`,
          expectedValue: `Storefront price must match Google Merchant Center feed price exactly (₹${effectiveStorefrontPrice})`,
          exactEvidence: {
            priceFound: effectiveStorefrontPrice,
            priceExpected: feedPrice
          },
          reproductionMethod: `Compare storefront price on ${feedItem.link} (₹${effectiveStorefrontPrice}) with GMC Feed entry (₹${feedPrice})`,
          businessImpact: 'Google Merchant Center automatically flags and disapproves products where checkout/storefront price does not match submitted feed price.',
          commercialRisk: {
            riskType: 'BUY_BOX_REVENUE_EROSION',
            title: 'GMC Feed vs Storefront Price Mismatch Disapproval',
            currency: 'INR',
            confidence: '[REQUIRES_ACCESS]',
            source: 'requires_merchant_telemetry',
            severityScore: 5,
            calculationFormula: `Observed Price Delta: ₹${priceDelta}/unit [OBSERVED]. Gross monthly loss requires merchant order velocity telemetry [REQUIRES_ACCESS].`,
            affectedSkus: [feedItem.id],
            affectedChannels: ['Google Shopping', 'Performance Max Ads'],
            observedDataPoints: {
              storefrontPrice: effectiveStorefrontPrice,
              feedPrice: feedPrice,
              priceDelta: priceDelta
            }
          },
          recommendedRemediation: 'Synchronize Google Merchant Center supplemental feed or update storefront promotional price before feed generation.',
          automaticallyFixable: true,
          requiredAccess: 'GMC Feed / Storefront API',
          remediationStatus: 'ACTION_REQUIRED',
          beforeEvidence: `Storefront: ₹${effectiveStorefrontPrice} | Feed: ₹${feedPrice}`,
          afterEvidence: null,
          verificationResult: null,
          timestamp: now
        });
      }
    }

    // ── Check 2: Availability Contradiction (Feed InStock vs Storefront OutOfStock) ─
    if (feedItem.availability === 'in_stock' && snapshot.effectiveStockState === 'out_of_stock') {
      findings.push({
        findingId: `SAN-GMC-AVAIL-CONTRADICTION-${feedItem.id}`,
        url: feedItem.link,
        routeIntent: 'PRODUCT_DISPLAY_PAGE',
        detectionRule: 'GMC_FEED_AVAILABILITY_CONTRADICTION',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
        category: 'Ecommerce',
        severity: 'CRITICAL',
        evidenceClass: '[O] Observed',
        observedValue: 'Storefront: Out of Stock | GMC Feed: in_stock',
        expectedValue: 'Feed availability must reflect Out of Stock when inventory <= 0',
        exactEvidence: {
          stockFound: 'out_of_stock',
          stockExpected: 'in_stock'
        },
        reproductionMethod: `Inspect stock on ${feedItem.link} vs GMC Feed entry for ${feedItem.id}`,
        businessImpact: 'Primary trigger for immediate Google Merchant Center account-level suspension due to policy violation (advertising unavailable products).',
        commercialRisk: {
          riskType: 'GMC_ACCOUNT_SUSPENSION',
          title: 'Google Merchant Center Stock Status Contradiction Suspension Risk',
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'requires_merchant_telemetry',
          severityScore: 5,
          calculationFormula: `SKU ${feedItem.id} advertised as in_stock while storefront is Out of Stock [REQUIRES_ACCESS: Account suspension risk]`,
          affectedSkus: [feedItem.id],
          affectedChannels: ['Google Shopping', 'Performance Max Ads']
        },
        recommendedRemediation: 'Submit supplemental feed setting availability to out_of_stock immediately when stock drops to 0.',
        automaticallyFixable: true,
        requiredAccess: 'Feed / Shopify Inventory',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'Feed in_stock vs Storefront Out of Stock',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }

    // ── Check 3: Missing GTIN on Feed Product ─────────────────────────
    if (!feedItem.gtin && !snapshot.gtin) {
      findings.push({
        findingId: `SAN-GMC-GTIN-MISSING-${feedItem.id}`,
        url: feedItem.link,
        routeIntent: 'PRODUCT_DISPLAY_PAGE',
        detectionRule: 'GMC_FEED_GTIN_MISSING',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
        category: 'Ecommerce',
        severity: 'MEDIUM',
        evidenceClass: '[O] Observed',
        observedValue: 'Missing GTIN (Global Trade Item Number)',
        expectedValue: 'Valid GS1 GTIN barcode (gtin13/UPC/EAN) in feed',
        exactEvidence: {
          rawContext: `Product ${feedItem.id} (${feedItem.title}) does not have a GTIN declared in feed or structured data`
        },
        reproductionMethod: `Inspect <g:gtin> in feed for ${feedItem.id}`,
        businessImpact: 'Products without valid GTINs are deprioritized by Google Shopping algorithms and ineligible for rich 1-box comparison units.',
        recommendedRemediation: 'Add manufacturer GS1 barcode (UPC/EAN/GTIN) to the product catalog and feed.',
        automaticallyFixable: false,
        requiredAccess: 'Catalog Master / ERP',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'Missing GTIN',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  return findings;
}
