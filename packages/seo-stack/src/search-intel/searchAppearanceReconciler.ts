/**
 * SANOCEA SEO Stack — Search Appearance & Schema Telemetry Reconciler
 * 
 * Bridges Track B Storefront Structured Data Declarations with Real Google Search Console 
 * Search Appearance & Rich Results Telemetry.
 * 
 * Enforces the 3-State Progression Pipeline:
 * [SCHEMA DECLARED] → [ELIGIBLE VIA URL INSPECTION] → [ACTUALLY SURFACED IN SERP]
 * 
 * Epistemological Rule:
 * Never treat declared JSON-LD as proof that Google is showing the rich result.
 * Google's SERP algorithms determine whether to display rich cards even when schema is valid.
 */

import * as cheerio from 'cheerio';
import { 
  GscSnapshot, 
  GscUrlInspectionRecord, 
  CrawledPage, 
  SeoFinding, 
  Severity,
  SearchAppearanceEntityStatus,
  SearchAppearanceProgressionState
} from '../core/types.js';
import { normalizeUrl } from '../core/urlDiscovery.js';
import { classifyRouteIntent } from '../core/routeIntent.js';

export interface SearchAppearanceReconciliationInput {
  crawledPages: Map<string, CrawledPage>;
  gscSnapshot?: GscSnapshot;
  inspectionRecords?: Map<string, GscUrlInspectionRecord>;
}

export interface SearchAppearanceAuditSummary {
  hasStorefrontProductSchema: boolean;
  gscSearchAppearanceActive: boolean;
  merchantListingsImpressions: number;
  productSnippetsImpressions: number;
  richResultsErrorsCount: number;
  statuses: SearchAppearanceEntityStatus[];
  findings: SeoFinding[];
}

export function reconcileSearchAppearance(
  input: SearchAppearanceReconciliationInput
): SearchAppearanceAuditSummary {
  const findings: SeoFinding[] = [];
  const statuses: SearchAppearanceEntityStatus[] = [];
  const now = new Date().toISOString();
  const { crawledPages, gscSnapshot, inspectionRecords = new Map() } = input;

  let hasStorefrontProductSchema = false;
  let merchantListingsImpressions = 0;
  let productSnippetsImpressions = 0;
  let richResultsErrorsCount = 0;

  // 1. Calculate aggregate GSC Search Appearance Impressions
  if (gscSnapshot && gscSnapshot.searchAppearanceRows) {
    for (const row of gscSnapshot.searchAppearanceRows) {
      const appearance = (row.searchAppearance || '').toUpperCase();
      if (appearance === 'MERCHANT_LISTINGS') {
        merchantListingsImpressions += row.impressions;
      } else if (appearance === 'PRODUCT_SNIPPETS') {
        productSnippetsImpressions += row.impressions;
      }
    }
  }

  // 2. Audit storefront pages for declared Product / Offer schema
  const pagesWithProductSchema: string[] = [];
  for (const [url, page] of crawledPages) {
    const html = page.renderedHtml || page.rawHtml;
    if (!html) continue;

    const $ = cheerio.load(html);
    let pageHasProduct = false;

    $('script[type="application/ld+json"]').each((_, el) => {
      try {
        const raw = $(el).html() || '{}';
        const parsed = JSON.parse(raw);
        const entities = Array.isArray(parsed) ? parsed : (parsed['@graph'] ? parsed['@graph'] : [parsed]);
        for (const ent of entities) {
          if (ent['@type'] === 'Product') {
            pageHasProduct = true;
            hasStorefrontProductSchema = true;
          }
        }
      } catch {}
    });

    if (pageHasProduct) {
      pagesWithProductSchema.push(url);
    }
  }

  // 3. Evaluate 3-State Progression for each audited page
  for (const [rawUrl] of crawledPages) {
    const normUrl = normalizeUrl(rawUrl) || rawUrl;
    const isDeclared = pagesWithProductSchema.includes(rawUrl) || pagesWithProductSchema.includes(normUrl);
    if (!isDeclared) continue;

    const inspection = inspectionRecords.get(normUrl) || inspectionRecords.get(rawUrl);
    let progressionState: SearchAppearanceProgressionState = 'DECLARED_ONLY';
    let explanation = 'Product schema declared on storefront DOM; GSC URL inspection telemetry not available to confirm eligibility.';
    let verdict: 'PASS' | 'NEUTRAL' | 'FAIL' | undefined;
    let issues: Array<{ message: string; severity: 'ERROR' | 'WARNING' }> | undefined;

    if (inspection && inspection.richResultsItems && inspection.richResultsItems.length > 0) {
      const productItem = inspection.richResultsItems.find((i: any) => 
        i.name.toLowerCase().includes('merchant') || i.name.toLowerCase().includes('product')
      ) || inspection.richResultsItems[0];

      verdict = productItem.verdict;
      issues = productItem.issues;

      const hasFatalErrors = productItem.issues?.some((i: any) => i.severity === 'ERROR');

      if (productItem.verdict === 'PASS' && !hasFatalErrors) {
        if (merchantListingsImpressions > 0 || productSnippetsImpressions > 0) {
          progressionState = 'SURFACED_IN_SERP';
          explanation = `Verified active in Google SERP: Schema declared → Eligible (PASS) → Actively surfacing rich snippets (${merchantListingsImpressions + productSnippetsImpressions} impressions).`;
        } else {
          progressionState = 'ELIGIBLE_UNSURFACED';
          explanation = 'Eligible for rich snippets in Google inspection, but 0 rich search appearance impressions recorded in current GSC window.';
        }
      } else {
        progressionState = 'DECLARED_ONLY';
        explanation = `Schema declared on storefront, but Google URL inspection failed eligibility: ${productItem.issues?.map((i: any) => i.message).join('; ') || 'Verdict: FAIL'}`;
      }
    } else if (merchantListingsImpressions > 0 || productSnippetsImpressions > 0) {
      progressionState = 'SURFACED_IN_SERP';
      explanation = `Active rich search appearance impressions (${merchantListingsImpressions + productSnippetsImpressions}) recorded in GSC.`;
    }

    statuses.push({
      url: normUrl,
      appearanceType: 'MERCHANT_LISTINGS',
      declaredOnStorefront: true,
      storefrontEntityType: 'Product',
      inspectionVerdict: verdict,
      inspectionIssues: issues,
      gscImpressions: merchantListingsImpressions,
      gscClicks: 0,
      state: progressionState,
      explanation
    });
  }

  // 4. Disqualification Check:
  // Declared schema present, organic traffic non-trivial (>= 100 imps), but 0 rich appearance impressions
  const totalOrganicImpressions = gscSnapshot?.totalImpressions || 0;
  const totalRichShoppingImpressions = merchantListingsImpressions + productSnippetsImpressions;

  if (hasStorefrontProductSchema && totalOrganicImpressions >= 100 && totalRichShoppingImpressions === 0) {
    const sampleUrl = pagesWithProductSchema[0] || gscSnapshot?.siteUrl || 'https://example.com';
    const routeIntent = classifyRouteIntent(sampleUrl);

    findings.push({
      findingId: `SAN-GSC-SEARCH-APP-DISQUALIFIED-${Buffer.from(sampleUrl).toString('base64url').slice(0, 10)}`,
      url: sampleUrl,
      routeIntent,
      detectionRule: 'STRUCTURED_DATA_SEARCH_APPEARANCE_DISQUALIFIED',
      track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
      category: 'Structured Data',
      severity: 'HIGH',
      evidenceClass: '[O] Observed',
      observedValue: `Catalog declares Product/Offer schema on ${pagesWithProductSchema.length} pages, but GSC records 0 Merchant Listings or Product Snippets impressions across ${totalOrganicImpressions} total search impressions`,
      expectedValue: 'Active "MERCHANT_LISTINGS" and "PRODUCT_SNIPPETS" search appearances in Google Search Console for eligible product pages',
      exactEvidence: {
        searchAppearanceType: 'MERCHANT_LISTINGS',
        rawContext: `GSC Search Analytics telemetry reveals 0 impressions for MERCHANT_LISTINGS despite ${pagesWithProductSchema.length} pages containing JSON-LD Product schema. Total search impressions: ${totalOrganicImpressions}.`
      },
      reproductionMethod: "GSC API dimensions=['searchAppearance'], filtered for MERCHANT_LISTINGS and PRODUCT_SNIPPETS",
      businessImpact: 'Declared schema is disqualified or ignored by Google algorithms, causing loss of price badges, star ratings, and Google Shopping organic tab placement.',
      commercialRisk: {
        riskType: 'SERP_CTR_LEAK',
        title: 'Google Shopping & Rich Snippet Disqualification',
        currency: 'INR',
        confidence: '[REQUIRES_ACCESS]',
        source: 'google_search_console',
        severityScore: 4,
        calculationFormula: `Product schema declared on ${pagesWithProductSchema.length} pages but generating 0 rich result impressions [REQUIRES_ACCESS: Exact incremental conversion value requires checkout telemetry]`,
        affectedChannels: ['Google Organic Search', 'Google Shopping Free Listings'],
        observedDataPoints: {
          catalogPagesWithSchema: pagesWithProductSchema.length,
          totalOrganicImpressions,
          merchantListingsImpressions,
          productSnippetsImpressions
        }
      },
      automationOpportunity: {
        automatable: true,
        recipeType: 'SCHEMA_INJECTION',
        primaryMechanism: 'TAG_MANAGER_SCRIPT',
        fallbackMechanisms: ['STOREFRONT_API', 'GIT_PULL_REQUEST'],
        requiredAccessTier: 'TAG_MANAGER_ONLY',
        requiredRole: 'GROWTH',
        description: 'Enrich schema with mandatory Google Merchant attributes: shippingDetails, hasMerchantReturnPolicy, and valid GS1 GTINs.'
      },
      recommendedRemediation: 'Validate Product JSON-LD against Google Rich Results Test. Add missing mandatory attributes: shippingDetails, returnPolicy, and valid GS1 identifiers (GTIN-13/UPC) to unlock rich search appearance.',
      automaticallyFixable: true,
      requiredAccess: 'Schema Template / Product Catalog',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: `0 rich appearance impressions in GSC`,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  }

  // 5. Audit URL Inspection Rich Results records for explicit validation errors
  for (const [rawUrl, inspection] of inspectionRecords.entries()) {
    const normUrl = normalizeUrl(rawUrl) || rawUrl;
    const routeIntent = classifyRouteIntent(normUrl);

    if (inspection.richResultsItems && inspection.richResultsItems.length > 0) {
      for (const item of inspection.richResultsItems) {
        if (item.verdict === 'FAIL' || (item.issues && item.issues.length > 0)) {
          const hasError = item.issues?.some((i: { message: string; severity: 'ERROR' | 'WARNING' }) => i.severity === 'ERROR');
          const severity: Severity = hasError ? 'CRITICAL' : 'MEDIUM';
          if (hasError) richResultsErrorsCount++;

          const issuesSummary = item.issues?.map((i: { message: string; severity: 'ERROR' | 'WARNING' }) => `[${i.severity}] ${i.message}`).join('; ') || 'Rich results verdict: FAIL';

          findings.push({
            findingId: `SAN-GSC-RICH-RESULT-ERROR-${Buffer.from(normUrl).toString('base64url').slice(0, 10)}`,
            url: normUrl,
            routeIntent,
            detectionRule: 'GSC_RICH_RESULT_ELIGIBILITY_ERROR',
            track: 'TRACK_B_ECOMMERCE_INTELLIGENCE',
            category: 'Structured Data',
            severity,
            evidenceClass: '[O] Observed',
            observedValue: `Google Rich Results validation failed for "${item.name}": ${issuesSummary}`,
            expectedValue: `Clean validation verdict PASS with 0 errors or warnings for "${item.name}"`,
            exactEvidence: {
              searchAppearanceType: item.name,
              rawContext: `GSC URL Inspection report for ${normUrl}: ${item.name} status is ${item.verdict}. Issues: ${issuesSummary}`
            },
            reproductionMethod: `GSC URL Inspection API: richResultsItems on ${normUrl}`,
            businessImpact: hasError 
              ? 'Google Search completely invalidates rich snippet rendering for this product.' 
              : 'Google Search suppresses rich enhancements due to non-standard schema implementation.',
            commercialRisk: {
              riskType: 'SERP_CTR_LEAK',
              title: `Rich Result Ineligibility: ${item.name}`,
              currency: 'INR',
              confidence: '[REQUIRES_ACCESS]',
              source: 'google_search_console',
              severityScore: hasError ? 5 : 3,
              calculationFormula: `Rich result item "${item.name}" failed validation in GSC URL Inspection [REQUIRES_ACCESS]`,
              affectedChannels: ['Google Organic Search'],
              observedDataPoints: {
                richResultItem: item.name,
                verdict: item.verdict,
                issuesCount: item.issues?.length || 0
              }
            },
            automationOpportunity: {
              automatable: true,
              recipeType: 'SCHEMA_INJECTION',
              primaryMechanism: 'TAG_MANAGER_SCRIPT',
              fallbackMechanisms: ['STOREFRONT_API', 'GIT_PULL_REQUEST'],
              requiredAccessTier: 'TAG_MANAGER_ONLY',
              requiredRole: 'GROWTH',
              description: 'Fix invalid schema fields reported by Google Search Console URL inspection.'
            },
            recommendedRemediation: `Fix the schema properties reported by Google Search Console: ${issuesSummary}`,
            automaticallyFixable: true,
            requiredAccess: 'Schema Template / Product Catalog',
            remediationStatus: 'ACTION_REQUIRED',
            beforeEvidence: issuesSummary,
            afterEvidence: null,
            verificationResult: null,
            timestamp: now
          });
        }
      }
    }
  }

  const gscSearchAppearanceActive = (merchantListingsImpressions + productSnippetsImpressions) > 0;

  return {
    hasStorefrontProductSchema,
    gscSearchAppearanceActive,
    merchantListingsImpressions,
    productSnippetsImpressions,
    richResultsErrorsCount,
    statuses,
    findings
  };
}
