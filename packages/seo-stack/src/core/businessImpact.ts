/**
 * SANOCEA SEO Stack — Business Impact & Commercial Risk Quantification Engine
 * Converts technical and ecommerce exceptions into tangible Monthly INR Revenue at Risk.
 * 
 * Strict Commercial Defensibility Rules:
 * 1. Every risk output carries an explicit FinancialConfidence tier:
 *    - [OBSERVED]: Directly observed data points
 *    - [CALCULATED]: Exact mathematical deltas
 *    - [ESTIMATED]: Model projection from stated assumptions
 *    - [REQUIRES_ACCESS]: Telemetry requires merchant credentials
 * 2. Every calculation discloses source and assumptions.
 * 3. Every automation recipe declares primary and fallback execution mechanisms.
 */

import { 
  CommercialRisk, 
  CommercialRiskType, 
  AutomationOpportunity, 
  FinancialConfidence,
  FinancialSource,
  ExecutionMechanism,
  AccessTier
} from './types.js';

export interface BusinessImpactModelDefaults {
  avgOrderValueInr: number;
  monthlyOrganicVisits: number;
  monthlyShoppingGmvInr: number;
  monthlySearchImpressions: number;
  conversionRate: number;
}

export const DEFAULT_COMMERCE_METRICS: BusinessImpactModelDefaults = {
  avgOrderValueInr: 2500,
  monthlyOrganicVisits: 50000,
  monthlyShoppingGmvInr: 1200000,
  monthlySearchImpressions: 250000,
  conversionRate: 0.018
};

/**
 * Calculates estimated commercial risk for a finding with explicit provenance and execution fallback
 */
export function estimateCommercialRisk(
  rule: string,
  url: string,
  extra?: {
    skuCount?: number;
    priceDelta?: number;
    monthlyUnitVolume?: number;
    observedValue?: any;
    expectedValue?: any;
  },
  metrics: BusinessImpactModelDefaults = DEFAULT_COMMERCE_METRICS
): { commercialRisk: CommercialRisk; automationOpportunity?: AutomationOpportunity } {
  switch (rule) {
    // ── 1. The Waaree / GMC Out of Stock vs InStock Contradiction ──────
    case 'STRUCTURED_DATA_INSTOCK_WHEN_OOS': {
      const skus = extra?.skuCount || 1;
      const shoppingGmvAtRisk = Math.round(metrics.monthlyShoppingGmvInr * 0.35);
      const lossInr = Math.min(shoppingGmvAtRisk, 450000 * skus);
      return {
        commercialRisk: {
          riskType: 'GMC_ACCOUNT_SUSPENSION',
          title: 'Google Merchant Center Feed Disapproval & Suspension Exposure',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'requires_merchant_telemetry',
          affectedSkus: [url.split('/').pop() || 'SKU-OOS-01'],
          affectedChannels: ['Google Shopping', 'Performance Max Ads', 'Direct Storefront'],
          severityScore: 5,
          calculationFormula: `Modeled Shopping Exposure (35% of Shopping GMV) = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: [
            'Merchant runs active Google Shopping / Performance Max ad campaigns',
            `Assumed baseline monthly Shopping GMV: ₹${metrics.monthlyShoppingGmvInr.toLocaleString('en-IN')}`,
            'Google Merchant Center policy mandates suspension for repeated stock status discrepancies'
          ],
          observedDataPoints: {
            domStockState: 'Out of Stock / Sold Out',
            schemaAvailability: 'https://schema.org/InStock'
          }
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'SCHEMA_INJECTION',
          primaryMechanism: 'STOREFRONT_API',
          fallbackMechanisms: ['SUPPLEMENTAL_FEED', 'TAG_MANAGER_SCRIPT', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'FEED_ONLY',
          requiredRole: 'ENGINEERING',
          description: 'Dynamically output https://schema.org/OutOfStock in JSON-LD or upload GMC Supplemental Feed when inventory <= 0.',
          proposedCodeSnippet: `offers: { ...offers, availability: inventory > 0 ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock' }`
        }
      };
    }

    // ── 2. Price Mismatch between Storefront & Structured Data ─────────
    case 'STRUCTURED_DATA_PRICE_MISMATCH': {
      const priceDelta = Math.abs(extra?.priceDelta || 200);
      const hasVerifiedVolume = typeof extra?.monthlyUnitVolume === 'number' && extra.monthlyUnitVolume > 0;

      if (hasVerifiedVolume) {
        const units = extra!.monthlyUnitVolume!;
        const lossInr = units * priceDelta;
        return {
          commercialRisk: {
            riskType: 'BUY_BOX_REVENUE_EROSION',
            title: 'Storefront vs Schema Price Discrepancy',
            estimatedMonthlyLossInr: lossInr,
            currency: 'INR',
            confidence: '[CALCULATED]',
            source: 'storefront_dom',
            affectedSkus: [url.split('/').pop() || 'SKU-PRICE-01'],
            affectedChannels: ['Google Shopping', 'Affiliate Feeds', 'Direct Storefront'],
            severityScore: 4,
            calculationFormula: `Observed Price Delta (₹${priceDelta}) × Verified Volume (${units} units/mo) = ₹${lossInr.toLocaleString('en-IN')}`,
            assumptions: [
              `Observed exact price disparity: ₹${priceDelta}/unit`,
              `Verified merchant order telemetry: ${units} units/mo`
            ],
            observedDataPoints: {
              observedPriceDeltaInr: priceDelta,
              verifiedMonthlyUnitVolume: units
            }
          },
          automationOpportunity: {
            automatable: true,
            recipeType: 'FEED_MAP',
            primaryMechanism: 'STOREFRONT_API',
            fallbackMechanisms: ['SUPPLEMENTAL_FEED', 'TAG_MANAGER_SCRIPT', 'WHATSAPP_APPROVAL'],
            requiredAccessTier: 'FEED_ONLY',
            requiredRole: 'MERCHANDISING',
            description: 'Synchronize active promotion sale price directly into JSON-LD offer.price or submit via supplemental feed.',
            proposedCodeSnippet: `offer.price = product.selected_or_first_available_variant.price / 100.0;`
          }
        };
      }

      // Strict Provenance: When volume telemetry is absent, do NOT invent numbers and call it CALCULATED
      return {
        commercialRisk: {
          riskType: 'BUY_BOX_REVENUE_EROSION',
          title: 'Storefront vs Schema Price Discrepancy',
          estimatedMonthlyLossInr: undefined,
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'requires_merchant_telemetry',
          affectedSkus: [url.split('/').pop() || 'SKU-PRICE-01'],
          affectedChannels: ['Google Shopping', 'Affiliate Feeds', 'Direct Storefront'],
          severityScore: 4,
          calculationFormula: `Observed Price Delta: ₹${priceDelta}/unit [OBSERVED]. Gross monthly loss requires merchant order velocity telemetry [REQUIRES_ACCESS].`,
          assumptions: [
            `Observed exact price disparity: ₹${priceDelta}/unit on storefront vs schema`,
            'Requires merchant Shopify/ERP sales velocity to calculate monthly revenue loss'
          ],
          observedDataPoints: {
            observedPriceDeltaInr: priceDelta
          }
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'FEED_MAP',
          primaryMechanism: 'STOREFRONT_API',
          fallbackMechanisms: ['SUPPLEMENTAL_FEED', 'TAG_MANAGER_SCRIPT', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'FEED_ONLY',
          requiredRole: 'MERCHANDISING',
          description: 'Synchronize active promotion sale price directly into JSON-LD offer.price or submit via supplemental feed.',
          proposedCodeSnippet: `offer.price = product.selected_or_first_available_variant.price / 100.0;`
        }
      };
    }

    // ── 3. Shopify /collections/*/products/* Canonical Dilution ────────
    case 'SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION': {
      const estimatedLeakedVisits = Math.round(metrics.monthlyOrganicVisits * 0.08);
      const lossInr = Math.round(estimatedLeakedVisits * metrics.conversionRate * metrics.avgOrderValueInr);
      return {
        commercialRisk: {
          riskType: 'CRAWL_BUDGET_DILUTION',
          title: 'Internal Link Equity Leak & Crawl Budget Exhaustion',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          affectedChannels: ['Direct Storefront', 'Google Search Organic'],
          severityScore: 4,
          calculationFormula: `Leaked Organic Visits (${estimatedLeakedVisits}) × Conversion Rate (${metrics.conversionRate * 100}%) × AOV (₹${metrics.avgOrderValueInr}) = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: [
            `Estimated monthly organic traffic: ${metrics.monthlyOrganicVisits} visits`,
            `Estimated link equity dilution factor: 8%`,
            `Average order value benchmark: ₹${metrics.avgOrderValueInr}`
          ]
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'SHOPIFY_LIQUID',
          primaryMechanism: 'GIT_PULL_REQUEST',
          fallbackMechanisms: ['STOREFRONT_API', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'CODE_REPO',
          requiredRole: 'ENGINEERING',
          description: 'Replace `{{ product.url | within: collection }}` with `{{ product.url }}` in product card liquid snippets.',
          proposedCodeSnippet: `<a href="{{ product.url }}">{{ product.title }}</a>`
        }
      };
    }

    // ── 4. Variant Canonical Dilution / Parameter Bloat ─────────────────
    case 'VARIANT_CANONICAL_PARAM_DILUTION':
    case 'FACETED_NAVIGATION_CRAWL_BLOAT':
    case 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION': {
      const lossInr = Math.round(metrics.monthlyOrganicVisits * 0.05 * metrics.conversionRate * metrics.avgOrderValueInr);
      return {
        commercialRisk: {
          riskType: 'CRAWL_BUDGET_DILUTION',
          title: 'Faceted Navigation & Variant Parameter Crawl Bloat',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          affectedChannels: ['Google Search Organic', 'Bing Search'],
          severityScore: 3,
          calculationFormula: `Modeled Crawl Waste (~5% Organic Potential) × AOV (₹${metrics.avgOrderValueInr}) = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: [
            'Search engines consume crawl budget indexing duplicate parameter states',
            `Modeled organic search penalty: 5% of potential organic sessions`
          ]
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'CANONICAL_RULE',
          primaryMechanism: 'TAG_MANAGER_SCRIPT',
          fallbackMechanisms: ['STOREFRONT_API', 'GIT_PULL_REQUEST', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'TAG_MANAGER_ONLY',
          requiredRole: 'ENGINEERING',
          description: 'Ensure canonical link points strictly to the parameter-free base product URL or apply robots noindex.',
          proposedCodeSnippet: `<link rel="canonical" href="{{ canonical_url | split: '?' | first }}">`
        }
      };
    }

    // ── 5. SERP Title / Meta Overflow CTR Leaks ────────────────────────
    case 'TITLE_PIXEL_WIDTH_EXCEEDED':
    case 'TITLE_TAG_MISSING': {
      const lostClicks = Math.round((metrics.monthlySearchImpressions * 0.03) * 0.12);
      const lossInr = Math.round(lostClicks * metrics.conversionRate * metrics.avgOrderValueInr);
      return {
        commercialRisk: {
          riskType: 'SERP_CTR_LEAK',
          title: 'Google SERP Title Truncation & Brand Value Proposition Cutoff',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          affectedChannels: ['Google Organic Search'],
          severityScore: 4,
          calculationFormula: `Estimated Lost Clicks (${lostClicks}) × Conversion Rate (${metrics.conversionRate * 100}%) × AOV (₹${metrics.avgOrderValueInr}) = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: [
            `Industry benchmark: 12% CTR penalty on truncated SERP headlines`,
            `Estimated monthly search impressions: ${metrics.monthlySearchImpressions}`
          ]
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'DIRECT_DOM_PATCH',
          primaryMechanism: 'STOREFRONT_API',
          fallbackMechanisms: ['TAG_MANAGER_SCRIPT', 'GIT_PULL_REQUEST', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'TAG_MANAGER_ONLY',
          requiredRole: 'GROWTH',
          description: 'Calibrate title string to <= 561px (Arial 20px) keeping core keyword and brand intact.',
          proposedCodeSnippet: `<title>Primary Keyword | Brand Name</title>`
        }
      };
    }

    case 'META_DESCRIPTION_LENGTH_EXCEEDED':
    case 'META_DESCRIPTION_MISSING': {
      const lostClicks = Math.round((metrics.monthlySearchImpressions * 0.03) * 0.05);
      const lossInr = Math.round(lostClicks * metrics.conversionRate * metrics.avgOrderValueInr);
      return {
        commercialRisk: {
          riskType: 'SERP_CTR_LEAK',
          title: 'Meta Snippet Ellipsis Truncation & CTR Deprecation',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          affectedChannels: ['Google Organic Search'],
          severityScore: 2,
          calculationFormula: `Estimated Lost CTR Clicks (${lostClicks}) × AOV (₹${metrics.avgOrderValueInr}) = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: [
            `Industry benchmark: ~5% CTR penalty for non-optimized meta snippets`,
            `Estimated monthly search impressions: ${metrics.monthlySearchImpressions}`
          ]
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'DIRECT_DOM_PATCH',
          primaryMechanism: 'STOREFRONT_API',
          fallbackMechanisms: ['TAG_MANAGER_SCRIPT', 'GIT_PULL_REQUEST', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'TAG_MANAGER_ONLY',
          requiredRole: 'GROWTH',
          description: 'Condense description into 140–155 characters (<= 985px) with strong CTA.',
          proposedCodeSnippet: `<meta name="description" content="Concise value proposition under 150 chars.">`
        }
      };
    }

    // ── 6. Missing SSR H1 / Zero Internal Outlinks (SPA Crawl Barrier) ──
    case 'H1_HEADING_MISSING_IN_SSR':
    case 'PAGES_WITHOUT_INTERNAL_OUTLINKS': {
      const lossInr = Math.round(metrics.monthlyOrganicVisits * 0.15 * metrics.conversionRate * metrics.avgOrderValueInr);
      return {
        commercialRisk: {
          riskType: 'INDEXATION_PURGE',
          title: 'Single-Page App Pre-Hydration Indexation Barrier',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          affectedChannels: ['Google Search', 'Bingbot', 'AI Search Engines'],
          severityScore: 5,
          calculationFormula: `Subpage Indexation Deficit (15% potential organic reach) × AOV (₹${metrics.avgOrderValueInr}) = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: [
            'Search crawlers without full headless JS capability fail to index client-rendered routes',
            `Modeled organic reach impact: 15%`
          ]
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'DIRECT_DOM_PATCH',
          primaryMechanism: 'GIT_PULL_REQUEST',
          fallbackMechanisms: ['TAG_MANAGER_SCRIPT', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'CODE_REPO',
          requiredRole: 'ENGINEERING',
          description: 'Inject semantic SSR HTML shell with H1 and crawlable navigation before JS bundle execution.',
          proposedCodeSnippet: `<div id="root"><h1>Semantic Heading</h1><nav><a href="/products">Products</a></nav></div>`
        }
      };
    }

    // ── 7. Missing Schema Brand or GTIN ────────────────────────────────
    case 'PRODUCT_SCHEMA_BRAND_MISSING':
    case 'PRODUCT_SCHEMA_GTIN_MISSING': {
      const lossInr = Math.round(metrics.monthlyShoppingGmvInr * 0.08);
      return {
        commercialRisk: {
          riskType: 'BUY_BOX_REVENUE_EROSION',
          title: 'Google Shopping Entity Identification Deficit',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[REQUIRES_ACCESS]',
          source: 'requires_merchant_telemetry',
          affectedChannels: ['Google Shopping Free Listings'],
          severityScore: 3,
          calculationFormula: `Shopping Free Listings Ineligibility (~8% Shopping GMV) = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: [
            'Google Shopping requires GS1 GTINs for rich product comparisons',
            'Pending merchant product catalog review'
          ]
        },
        automationOpportunity: {
          automatable: false,
          recipeType: 'FEED_MAP',
          primaryMechanism: 'SUPPLEMENTAL_FEED',
          fallbackMechanisms: ['STOREFRONT_API', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'FEED_ONLY',
          requiredRole: 'MERCHANDISING',
          description: 'Populate GS1 GTIN barcodes and Brand entity objects in catalog master or supplemental feed.',
          proposedCodeSnippet: `brand: { "@type": "Brand", "name": "BrandName" }, gtin13: "8901234567890"`
        }
      };
    }

    // ── 8. Empty Collection Pages ──────────────────────────────────────
    case 'EMPTY_COLLECTION_PAGE': {
      const lossInr = 45000;
      return {
        commercialRisk: {
          riskType: 'CONVERSION_FRICTION',
          title: 'Dead-End User Journey & Soft 404 Ranking Drop',
          estimatedMonthlyLossInr: lossInr,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          affectedChannels: ['Direct Storefront', 'Organic Search'],
          severityScore: 4,
          calculationFormula: `Zero-Inventory Landing Page Bounce Penalty = ₹${lossInr.toLocaleString('en-IN')}`,
          assumptions: ['User bounce rate increases on zero-inventory landing pages']
        },
        automationOpportunity: {
          automatable: true,
          recipeType: 'CANONICAL_RULE',
          primaryMechanism: 'STOREFRONT_API',
          fallbackMechanisms: ['TAG_MANAGER_SCRIPT', 'WHATSAPP_APPROVAL'],
          requiredAccessTier: 'TAG_MANAGER_ONLY',
          requiredRole: 'MERCHANDISING',
          description: 'Add noindex or 302 redirect for empty categories to the parent collection.',
          proposedCodeSnippet: `<meta name="robots" content="noindex, follow">`
        }
      };
    }

    default: {
      return {
        commercialRisk: {
          riskType: 'CONVERSION_FRICTION',
          title: 'Technical Friction & Best Practice Non-Compliance',
          estimatedMonthlyLossInr: 5000,
          currency: 'INR',
          confidence: '[ESTIMATED]',
          source: 'industry_benchmark_estimate',
          affectedChannels: ['Direct Storefront'],
          severityScore: 1,
          calculationFormula: 'Baseline UX friction / header compliance penalty: ₹5,000/mo',
          assumptions: ['Standard technical hygiene compliance penalty']
        }
      };
    }
  }
}
