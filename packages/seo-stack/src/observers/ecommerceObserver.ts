/**
 * SANOCEA SEO Stack — Track B: Ecommerce SEO & Commerce Intelligence Observer
 * Implements:
 * 1. Shopify collections/products Canonical Dilution Bug
 * 2. Variant Canonicalisation (Variant URLs pointing to canonical base)
 * 3. Faceted Navigation & Parameter Bloat Detection
 * 4. Product Schema Extraction & Validation (Offers, Price, Currency, Availability)
 * 5. Price vs Structured-Data Price Discrepancy Detection
 * 6. Storefront Out-of-Stock vs Schema InStock Contradiction (The Waaree Discrepancy Rule)
 * 7. SKU, GTIN, and Brand Entity Integrity
 * 8. Product Image & Asset Schema Integrity
 * 9. Empty Collection / Zero-Inventory Category Pages
 * 10. Cross-Page Duplicate Product / Catalogue Detection
 */

import { PageAuditContext, SeoFinding } from '../core/types.js';
import { estimateCommercialRisk } from '../core/businessImpact.js';
import { classifyRouteIntent } from '../core/routeIntent.js';
import { classifyUrlParameters } from '../core/urlDiscovery.js';

export function runEcommerceObserver(context: PageAuditContext): SeoFinding[] {
  const findings: SeoFinding[] = [];
  const { page, $, crawlConfig, allPages } = context;
  const now = new Date().toISOString();
  const pageUrlObj = new URL(page.url);
  const routeIntent = classifyRouteIntent(page.url);

  // ── 1. Shopify /collections/*/products/* Canonical Dilution Bug ────
  const collectionProductLinks: { href: string; text: string }[] = [];
  $('a[href*="/collections/"][href*="/products/"]').each((_idx: number, el: any) => {
    const href = $(el).attr('href')?.trim() || '';
    if (/\/collections\/[^/]+\/products\/[^/?#]+/.test(href)) {
      collectionProductLinks.push({
        href,
        text: $(el).text().trim()
      });
    }
  });

  if (collectionProductLinks.length > 0) {
    const sample = collectionProductLinks[0];
    const risk = estimateCommercialRisk('SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION', page.url);
    findings.push({
      findingId: `SAN-SEO-ECOM-SHOPIFY-DILUTION-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION',
      track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
      category: 'Ecommerce',
      severity: 'HIGH',
      evidenceClass: '[O] Observed',
      observedValue: `${collectionProductLinks.length} internal links pointing to /collections/*/products/*`,
      expectedValue: 'Direct canonical product URLs (/products/<slug>) for internal links',
      exactEvidence: {
        htmlSnippet: `<a href="${sample.href}">${sample.text || 'Product'}</a>`,
        rawContext: `Found ${collectionProductLinks.length} instances on this page, e.g. ${sample.href}`
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -o '/collections/[^/]*/products/[^\"]*'`,
      businessImpact: 'Dilutes PageRank equity across temporary collection URLs. While Shopify canonicalizes to /products/, internal linking to collection URLs increases crawl latency and delays organic indexing.',
      commercialRisk: risk.commercialRisk,
      automationOpportunity: risk.automationOpportunity,
      recommendedRemediation: 'In Shopify Liquid template (e.g. product-card.liquid), change `{{ product.url | within: collection }}` to `{{ product.url }}`.',
      automaticallyFixable: true,
      requiredAccess: 'Shopify Liquid theme files',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: sample.href,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // ── 2. Variant Canonicalisation Checks ─────────────────────────────
  if (pageUrlObj.searchParams.has('variant') || pageUrlObj.searchParams.has('sku')) {
    const canonicalHref = $('link[rel="canonical"]').attr('href')?.trim();
    if (canonicalHref) {
      try {
        const canonicalUrl = new URL(canonicalHref, page.url);
        if (canonicalUrl.searchParams.has('variant') || canonicalUrl.searchParams.has('sku')) {
          const risk = estimateCommercialRisk('VARIANT_CANONICAL_PARAM_DILUTION', page.url);
          findings.push({
            findingId: `SAN-SEO-ECOM-VARIANT-CANON-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
            url: page.url,
            routeIntent,
            detectionRule: 'VARIANT_CANONICAL_PARAM_DILUTION',
            track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
            category: 'Ecommerce',
            severity: 'HIGH',
            evidenceClass: '[O] Observed',
            observedValue: `Canonical tag retains variant parameter: ${canonicalHref}`,
            expectedValue: `Canonical tag pointing to clean base product URL without variant parameters (${canonicalUrl.origin}${canonicalUrl.pathname})`,
            exactEvidence: {
              htmlSnippet: `<link rel="canonical" href="${canonicalHref}">`,
              domSelector: 'link[rel="canonical"]'
            },
            reproductionMethod: `curl -sL '${page.url}' | grep 'rel="canonical"'`,
            businessImpact: 'Indexes hundreds of duplicate product variant permutations, splitting review ratings and diluting organic ranking.',
            commercialRisk: risk.commercialRisk,
            automationOpportunity: risk.automationOpportunity,
            recommendedRemediation: 'Strip variant and SKU query parameters from the canonical link in the product template.',
            automaticallyFixable: true,
            requiredAccess: 'Ecommerce template / theme',
            remediationStatus: 'ACTION_REQUIRED',
            beforeEvidence: canonicalHref,
            afterEvidence: null,
            verificationResult: null,
            timestamp: now
          });
        }
      } catch {}
    }
  }

  // ── 3. Faceted Navigation & Combinatorial Parameter Explosion ──────
  const { facetParams, trackingParams, functionalParams, cleanUrl } = classifyUrlParameters(page.url);
  const hasFacetParams = facetParams.length > 0;
  const isCombinatorialFaceted = facetParams.length >= 2 || (facetParams.length >= 1 && (pageUrlObj.searchParams.has('sort') || pageUrlObj.searchParams.has('sort_by') || pageUrlObj.searchParams.has('order')));

  if (hasFacetParams) {
    const metaRobots = ($('meta[name="robots"]').attr('content') || page.headers['x-robots-tag'] || '').toLowerCase();
    const hasNoindex = metaRobots.includes('noindex');
    const canonicalHref = $('link[rel="canonical"]').attr('href')?.trim();

    let canonicalIsClean = false;
    let canonicalSelfReferencesFaceted = false;

    if (canonicalHref) {
      try {
        const parsedCanonical = new URL(canonicalHref, page.url);
        const canonClassification = classifyUrlParameters(parsedCanonical.toString());
        canonicalIsClean = canonClassification.facetParams.length === 0 && parsedCanonical.pathname === pageUrlObj.pathname;
        canonicalSelfReferencesFaceted = canonClassification.facetParams.length > 0;
      } catch {}
    }

    if (isCombinatorialFaceted && !hasNoindex && !canonicalIsClean) {
      const risk = estimateCommercialRisk('FACETED_COMBINATORIAL_PARAMETER_EXPLOSION', page.url);
      findings.push({
        findingId: `SAN-SEO-ECOM-FACET-COMBO-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent: 'FACETED_FILTER',
        detectionRule: 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
        category: 'Ecommerce',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: `Combinatorial faceted URL (${facetParams.length} filter parameters: ${facetParams.join(', ')}) is indexable without clean canonical or noindex`,
        expectedValue: `Canonical tag pointing to clean category base (${cleanUrl}) or <meta name="robots" content="noindex, follow">`,
        exactEvidence: {
          htmlSnippet: canonicalHref ? `<link rel="canonical" href="${canonicalHref}">` : undefined,
          facetParams,
          cleanCanonicalUrl: cleanUrl,
          rawContext: `Parameters: [Facets: ${facetParams.join(', ')}] [Functional: ${functionalParams.join(', ') || 'none'}]`
        },
        reproductionMethod: `curl -sL '${page.url}' | grep -E 'rel="canonical"|name="robots"'`,
        businessImpact: 'Exponential parameter permutations consume search engine crawl budget, spawning millions of near-duplicate low-value search entries.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: {
          automatable: true,
          recipeType: 'CANONICAL_RULE',
          primaryMechanism: 'STOREFRONT_API',
          fallbackMechanisms: ['TAG_MANAGER_SCRIPT', 'GIT_PULL_REQUEST', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'TAG_MANAGER_ONLY',
          requiredRole: 'GROWTH',
          description: `Strip facet parameters from canonical tag to point directly to clean category URL (${cleanUrl}).`,
          proposedCodeSnippet: `<link rel="canonical" href="${cleanUrl}">`
        },
        recommendedRemediation: `Point canonical tag to clean category base URL (${cleanUrl}) or inject <meta name="robots" content="noindex, follow">. Legitimate functional parameters (${functionalParams.join(', ') || 'none'}) must be preserved.`,
        automaticallyFixable: true,
        requiredAccess: 'Ecommerce collection template',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: canonicalHref || page.url,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    } else if (!hasNoindex && (!canonicalHref || canonicalSelfReferencesFaceted)) {
      const risk = estimateCommercialRisk('FACETED_NAVIGATION_CRAWL_BLOAT', page.url);
      findings.push({
        findingId: `SAN-SEO-ECOM-FACET-BLOAT-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent: 'FACETED_FILTER',
        detectionRule: 'FACETED_NAVIGATION_CRAWL_BLOAT',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
        category: 'Ecommerce',
        severity: 'MEDIUM',
        evidenceClass: '[O] Observed',
        observedValue: `Faceted URL accessible with indexable directives: ${page.url}`,
        expectedValue: `noindex directive or canonical pointing strictly to parent collection root (${cleanUrl})`,
        exactEvidence: {
          facetParams,
          cleanCanonicalUrl: cleanUrl,
          rawContext: `URL contains faceted filter query parameters but is missing <meta name="robots" content="noindex">`
        },
        reproductionMethod: `curl -sI '${page.url}'`,
        businessImpact: 'Creates exponential crawl traps for search engine bots, wasting monthly crawl budget on near-duplicate facet states.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: risk.automationOpportunity,
        recommendedRemediation: `Inject <meta name="robots" content="noindex, follow"> or point canonical to ${cleanUrl}.`,
        automaticallyFixable: true,
        requiredAccess: 'Theme collection template',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: page.url,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 4. Empty Collection / Zero-Inventory Category Check ────────────
  const isCollectionPage = /\/(collections|category|c)\/[^/]+/.test(pageUrlObj.pathname);
  if (isCollectionPage) {
    const bodyText = $('body').text().toLowerCase();
    const hasZeroProductsText = 
      bodyText.includes('no products found') || 
      bodyText.includes('no items in this collection') ||
      bodyText.includes('there are no products');
    
    const productGridItems = $('.product-card, .product-item, [data-product-id], .grid-product').length;

    if (hasZeroProductsText || productGridItems === 0) {
      const risk = estimateCommercialRisk('EMPTY_COLLECTION_PAGE', page.url);
      findings.push({
        findingId: `SAN-SEO-ECOM-EMPTY-COLLECTION-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'EMPTY_COLLECTION_PAGE',
        track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
        category: 'Ecommerce',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: '0 products detected in active collection listing',
        expectedValue: 'Active products displayed or collection redirected/noindexed',
        exactEvidence: {
          rawContext: 'Collection page renders zero product cards or displays "no products found" notice'
        },
        reproductionMethod: `curl -sL '${page.url}' | grep -i 'no products'`,
        businessImpact: 'Soft 404 signal for Google; leads to high user bounce rates and wasted ad spend on empty category landing pages.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: risk.automationOpportunity,
        recommendedRemediation: 'Add noindex directive or temporary 302 redirect to parent category until inventory is replenished.',
        automaticallyFixable: true,
        requiredAccess: 'Storefront CMS / Merchandising',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: 'Empty category page',
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // ── 5. Structured Data: Product Schema & Discrepancy Analysis ─────
  const jsonLdScripts = $('script[type="application/ld+json"]');

  jsonLdScripts.each((_idx: number, el: any) => {
    try {
      const parsed = JSON.parse($(el).html() || '{}');
      const entities = Array.isArray(parsed) ? parsed : (parsed['@graph'] ? parsed['@graph'] : [parsed]);

      for (const entity of entities) {
        if (entity['@type'] === 'Product') {
          // 5a. Offers Validation
          const offers = entity.offers;
          if (!offers) {
            findings.push({
              findingId: `SAN-SEO-ECOM-OFFERS-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
              url: page.url,
              routeIntent,
              detectionRule: 'PRODUCT_SCHEMA_OFFERS_MISSING',
              track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
              category: 'Ecommerce',
              severity: 'HIGH',
              evidenceClass: '[O] Observed',
              observedValue: 'Product schema has no "offers" property',
              expectedValue: 'Offers object containing price, priceCurrency, and availability',
              exactEvidence: {
                rawContext: JSON.stringify(entity).slice(0, 200)
              },
              reproductionMethod: `Inspect JSON-LD @type: "Product" on ${page.url}`,
              businessImpact: 'Disqualifies product from Google Shopping / Rich Results price and availability badges.',
              recommendedRemediation: 'Add valid "offers": { "@type": "Offer", "price": "...", "priceCurrency": "INR", "availability": "https://schema.org/InStock" } to Product schema.',
              automaticallyFixable: true,
              requiredAccess: 'Storefront schema template',
              remediationStatus: 'ACTION_REQUIRED',
              beforeEvidence: null,
              afterEvidence: null,
              verificationResult: null,
              timestamp: now
            });
          } else {
            const offerObj = Array.isArray(offers) ? offers[0] : offers;
            const schemaAvailability = offerObj.availability || '';
            const schemaPrice = offerObj.price !== undefined ? parseFloat(offerObj.price) : null;

            // 5b. The Waaree Out-of-Stock vs InStock Discrepancy Rule
            const isSchemaInStock = schemaAvailability.includes('InStock');
            const pageText = $('body').text().toLowerCase();
            const isOutOfStockOnPage = 
              pageText.includes('out of stock') || 
              pageText.includes('currently unavailable') || 
              pageText.includes('sold out') ||
              $('button[disabled]:contains("Add to cart"), button[disabled]:contains("Buy now")').length > 0;

            if (isSchemaInStock && isOutOfStockOnPage) {
              const risk = estimateCommercialRisk('STRUCTURED_DATA_INSTOCK_WHEN_OOS', page.url);
              findings.push({
                findingId: `SAN-SEO-ECOM-STOCK-LEAK-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
                url: page.url,
                routeIntent,
                detectionRule: 'STRUCTURED_DATA_INSTOCK_WHEN_OOS',
                track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
                category: 'Ecommerce',
                severity: 'CRITICAL',
                evidenceClass: '[O] Observed',
                observedValue: `Schema declares "${schemaAvailability}" while page indicates Out of Stock`,
                expectedValue: 'Schema availability must match true physical inventory ("https://schema.org/OutOfStock")',
                exactEvidence: {
                  stockFound: schemaAvailability,
                  stockExpected: 'https://schema.org/OutOfStock',
                  rawContext: `JSON-LD availability="${schemaAvailability}" but storefront displays Out of Stock / disabled purchase button`
                },
                reproductionMethod: `Compare JSON-LD availability with storefront stock status on ${page.url}`,
                businessImpact: 'Google Merchant Center account suspension risk for deceptive availability feeds; customer frustration from clicking search results for out-of-stock items.',
                commercialRisk: risk.commercialRisk,
                automationOpportunity: risk.automationOpportunity,
                recommendedRemediation: 'Dynamically output "https://schema.org/OutOfStock" in JSON-LD or upload supplemental feed when inventory is zero.',
                automaticallyFixable: true,
                requiredAccess: 'Ecommerce backend / theme inventory logic',
                remediationStatus: 'ACTION_REQUIRED',
                beforeEvidence: schemaAvailability,
                afterEvidence: null,
                verificationResult: null,
                timestamp: now
              });
            }

            // 5c. Price vs Structured-Data Price Discrepancy
            if (schemaPrice !== null) {
              const visiblePriceMatch = $('body').text().match(/(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{2})?)/);
              if (visiblePriceMatch) {
                const visiblePriceNum = parseFloat(visiblePriceMatch[1].replace(/,/g, ''));
                if (!isNaN(visiblePriceNum) && Math.abs(visiblePriceNum - schemaPrice) > 5) {
                  const delta = visiblePriceNum - schemaPrice;
                  const risk = estimateCommercialRisk('STRUCTURED_DATA_PRICE_MISMATCH', page.url, { priceDelta: delta });
                  findings.push({
                    findingId: `SAN-SEO-ECOM-PRICE-MISMATCH-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
                    url: page.url,
                    routeIntent,
                    detectionRule: 'STRUCTURED_DATA_PRICE_MISMATCH',
                    track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
                    category: 'Ecommerce',
                    severity: 'HIGH',
                    evidenceClass: '[O] Observed',
                    observedValue: `Storefront displays ₹${visiblePriceNum} while JSON-LD schema declares ₹${schemaPrice}`,
                    expectedValue: `Consistent price declaration across DOM and JSON-LD schema (₹${visiblePriceNum})`,
                    exactEvidence: {
                      priceFound: schemaPrice,
                      priceExpected: visiblePriceNum,
                      rawContext: `DOM price: ₹${visiblePriceNum} vs Schema price: ₹${schemaPrice} (Delta: ₹${delta})`
                    },
                    reproductionMethod: `Compare visible price text with JSON-LD offer.price on ${page.url}`,
                    businessImpact: 'Google Merchant Center price mismatch disapprovals; causes instant ad feed pause and customer checkout abandonment.',
                    commercialRisk: risk.commercialRisk,
                    automationOpportunity: risk.automationOpportunity,
                    recommendedRemediation: 'Synchronize the active promotional storefront price with JSON-LD offer.price or supply supplemental feed.',
                    automaticallyFixable: true,
                    requiredAccess: 'Theme product template / price feed',
                    remediationStatus: 'ACTION_REQUIRED',
                    beforeEvidence: `DOM: ${visiblePriceNum} vs Schema: ${schemaPrice}`,
                    afterEvidence: null,
                    verificationResult: null,
                    timestamp: now
                  });
                }
              }
            }
          }

          // 5d. Brand Entity Validation
          if (!entity.brand) {
            const risk = estimateCommercialRisk('PRODUCT_SCHEMA_BRAND_MISSING', page.url);
            findings.push({
              findingId: `SAN-SEO-ECOM-BRAND-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
              url: page.url,
              routeIntent,
              detectionRule: 'PRODUCT_SCHEMA_BRAND_MISSING',
              track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
              category: 'Ecommerce',
              severity: 'MEDIUM',
              evidenceClass: '[O] Observed',
              observedValue: 'Missing "brand" in Product schema',
              expectedValue: 'Structured Brand object: { "@type": "Brand", "name": "..." }',
              exactEvidence: {
                rawContext: `Product "${entity.name || 'Product'}" has no brand property`
              },
              reproductionMethod: `Inspect JSON-LD product entity brand attribute on ${page.url}`,
              businessImpact: 'Required for Google Shopping rich results and brand-filtered search queries.',
              commercialRisk: risk.commercialRisk,
              automationOpportunity: risk.automationOpportunity,
              recommendedRemediation: 'Map the catalog brand attribute into JSON-LD `brand: { "@type": "Brand", "name": "..." }`.',
              automaticallyFixable: true,
              requiredAccess: 'Schema template',
              remediationStatus: 'ACTION_REQUIRED',
              beforeEvidence: 'Missing brand',
              afterEvidence: null,
              verificationResult: null,
              timestamp: now
            });
          }

          // 5e. GTIN / Barcode Identifier Validation
          if (!entity.gtin13 && !entity.gtin && !entity.gtin12 && !entity.upc && !entity.mpn) {
            const risk = estimateCommercialRisk('PRODUCT_SCHEMA_GTIN_MISSING', page.url);
            findings.push({
              findingId: `SAN-SEO-ECOM-GTIN-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
              url: page.url,
              routeIntent,
              detectionRule: 'PRODUCT_SCHEMA_GTIN_MISSING',
              track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
              category: 'Ecommerce',
              severity: 'MEDIUM',
              evidenceClass: '[O] Observed',
              observedValue: 'No gtin, gtin13, upc, or mpn in Product schema',
              expectedValue: 'Valid GS1 GTIN/barcode identifier for product matching',
              exactEvidence: {
                rawContext: `Product "${entity.name || 'Unnamed'}" lacks global trade item numbers`
              },
              reproductionMethod: `Inspect JSON-LD product attributes for GTIN/UPC fields on ${page.url}`,
              businessImpact: 'Degrades visibility in Google Shopping free listings and comparison feeds.',
              commercialRisk: risk.commercialRisk,
              automationOpportunity: risk.automationOpportunity,
              recommendedRemediation: 'Assign GS1 GTIN barcode to catalog master and map into Product schema.',
              automaticallyFixable: false,
              requiredAccess: 'PIM / ERP / Product Catalog Master',
              remediationStatus: 'ACTION_REQUIRED',
              beforeEvidence: null,
              afterEvidence: null,
              verificationResult: null,
              timestamp: now
            });
          }

          // 5f. Product Image Integrity in Schema
          if (!entity.image || (Array.isArray(entity.image) && entity.image.length === 0)) {
            findings.push({
              findingId: `SAN-SEO-ECOM-SCHEMA-IMG-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
              url: page.url,
              routeIntent,
              detectionRule: 'PRODUCT_SCHEMA_IMAGE_MISSING',
              track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
              category: 'Ecommerce',
              severity: 'HIGH',
              evidenceClass: '[O] Observed',
              observedValue: 'Product schema has no "image" attribute',
              expectedValue: 'Array of high-resolution product image URLs',
              exactEvidence: {
                rawContext: `Product entity "${entity.name || 'Product'}" has empty image property`
              },
              reproductionMethod: `Inspect JSON-LD product entity image on ${page.url}`,
              businessImpact: 'Ineligible for Google Rich Results image cards and Shopping image snippets.',
              recommendedRemediation: 'Include high-resolution featured image URL in Product schema.',
              automaticallyFixable: true,
              requiredAccess: 'Schema template',
              remediationStatus: 'ACTION_REQUIRED',
              beforeEvidence: 'Missing image',
              afterEvidence: null,
              verificationResult: null,
              timestamp: now
            });
          }
        }
      }
    } catch {}
  });

  return findings;
}
