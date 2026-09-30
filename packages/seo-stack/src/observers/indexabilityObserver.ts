/**
 * SANOCEA SEO Stack — Track A: Indexability & Canonical Integrity Observer
 * Hardened with Route Intent Classification
 */

import { PageAuditContext, SeoFinding } from '../core/types.js';
import { estimateCommercialRisk } from '../core/businessImpact.js';
import { classifyRouteIntent, isExpectedNoindex, isUtilityOrNonIndexableIntent } from '../core/routeIntent.js';

export function runIndexabilityObserver(context: PageAuditContext): SeoFinding[] {
  const findings: SeoFinding[] = [];
  const { page, $ } = context;
  const now = new Date().toISOString();
  const routeIntent = classifyRouteIntent(page.url);

  // 1. Meta Robots & X-Robots-Tag Inspection
  const metaRobots = $('meta[name="robots"], meta[name="googlebot"]').attr('content')?.toLowerCase() || '';
  const xRobots = page.headers['x-robots-tag']?.toLowerCase() || '';

  const hasNoindex = metaRobots.includes('noindex') || xRobots.includes('noindex');

  if (hasNoindex) {
    if (isExpectedNoindex(page.url) || isUtilityOrNonIndexableIntent(routeIntent)) {
      // Normal, expected behavior on cart/account/checkout/search/simulators/filters
      findings.push({
        findingId: `SAN-SEO-IDX-NOINDEX-UTILITY-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'NOINDEX_ON_TRANSACTIONAL_ROUTE',
        track: 'TRACK_A_CORE_SEO',
        category: 'Indexability',
        severity: 'INFO',
        evidenceClass: '[O] Observed',
        observedValue: metaRobots.includes('noindex') ? `meta[name=robots]: ${metaRobots}` : `X-Robots-Tag: ${xRobots}`,
        expectedValue: 'noindex directive standard for customer utility routes',
        exactEvidence: {
          rawContext: `Customer utility endpoint (${routeIntent}) is correctly guarded with noindex`
        },
        reproductionMethod: `curl -sL '${page.url}' | grep -i 'robots'`,
        businessImpact: 'Expected security hygiene: prevents private customer account and transactional routes from leaking into search index.',
        recommendedRemediation: 'Retain noindex directive on this utility route.',
        automaticallyFixable: false,
        requiredAccess: 'None',
        remediationStatus: 'INFORMATIONAL',
        beforeEvidence: metaRobots || xRobots,
        afterEvidence: null,
        verificationResult: 'Validated Standard Practice',
        timestamp: now
      });
    } else {
      // Serious issue on a public marketing, collection, or product page
      const risk = estimateCommercialRisk('INDEXATION_PURGE', page.url);
      findings.push({
        findingId: `SAN-SEO-IDX-NOINDEX-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'NOINDEX_DIRECTIVE_PRESENT',
        track: 'TRACK_A_CORE_SEO',
        category: 'Indexability',
        severity: 'HIGH',
        evidenceClass: '[O] Observed',
        observedValue: metaRobots.includes('noindex') ? `meta[name=robots]: ${metaRobots}` : `X-Robots-Tag: ${xRobots}`,
        expectedValue: 'index, follow for public landing pages',
        exactEvidence: {
          rawContext: metaRobots || xRobots
        },
        reproductionMethod: `curl -sL '${page.url}' | grep -i 'robots'`,
        businessImpact: 'Instructs search engines to purge or exclude the public commercial page from the search index.',
        commercialRisk: risk.commercialRisk,
        automationOpportunity: risk.automationOpportunity,
        recommendedRemediation: 'Remove noindex directive from this public commercial page.',
        automaticallyFixable: true,
        requiredAccess: 'HTML / HTTP server config',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: metaRobots || xRobots,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  // 2. Canonical Tag Validation
  const canonicalLinks = $('link[rel="canonical"]');
  if (canonicalLinks.length === 0 && !isUtilityOrNonIndexableIntent(routeIntent)) {
    findings.push({
      findingId: `SAN-SEO-CANON-MISSING-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'CANONICAL_TAG_MISSING',
      track: 'TRACK_A_CORE_SEO',
      category: 'Indexability',
      severity: 'MEDIUM',
      evidenceClass: '[O] Observed',
      observedValue: '0 <link rel="canonical"> tags found',
      expectedValue: `Canonical tag pointing to authoritative URL (e.g. ${page.url})`,
      exactEvidence: {
        domSelector: 'head'
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -i 'rel="canonical"'`,
      businessImpact: 'Risk of content duplication if page is accessed with trailing slashes, uppercase, or tracking parameters.',
      commercialRisk: {
        riskType: 'CRAWL_BUDGET_DILUTION',
        title: 'Missing Canonical Duplicate Risk',
        estimatedMonthlyLossInr: 12000,
        currency: 'INR',
        confidence: '[ESTIMATED]',
        source: 'industry_benchmark_estimate',
        severityScore: 2,
        calculationFormula: 'Estimated duplicate crawling crawl-budget waste: ₹12,000/mo'
      },
      recommendedRemediation: `Add <link rel="canonical" href="${page.url}"> to <head>.`,
      automaticallyFixable: true,
      requiredAccess: 'HTML template source code',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: null,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  } else if (canonicalLinks.length > 1) {
    findings.push({
      findingId: `SAN-SEO-CANON-MULTIPLE-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
      url: page.url,
      routeIntent,
      detectionRule: 'MULTIPLE_CANONICAL_TAGS',
      track: 'TRACK_A_CORE_SEO',
      category: 'Indexability',
      severity: 'HIGH',
      evidenceClass: '[O] Observed',
      observedValue: `${canonicalLinks.length} canonical tags found`,
      expectedValue: 'Exactly 1 canonical tag',
      exactEvidence: {
        htmlSnippet: canonicalLinks.map((_idx: number, el: any) => $(el).prop('outerHTML')).get().join(' | ')
      },
      reproductionMethod: `curl -sL '${page.url}' | grep -i 'rel="canonical"'`,
      businessImpact: 'Conflicting canonical tags cause search engines to ignore all canonical directives.',
      commercialRisk: {
        riskType: 'CRAWL_BUDGET_DILUTION',
        title: 'Conflicting Canonical Directives',
        estimatedMonthlyLossInr: 25000,
        currency: 'INR',
        confidence: '[ESTIMATED]',
        source: 'industry_benchmark_estimate',
        severityScore: 3,
        calculationFormula: 'Ignored canonicalization duplicate index penalty: ₹25,000/mo'
      },
      recommendedRemediation: 'Remove duplicate canonical tags to leave a single authoritative declaration.',
      automaticallyFixable: true,
      requiredAccess: 'HTML template source code',
      remediationStatus: 'ACTION_REQUIRED',
      beforeEvidence: null,
      afterEvidence: null,
      verificationResult: null,
      timestamp: now
    });
  } else if (canonicalLinks.length === 1) {
    const canonicalHref = canonicalLinks.first().attr('href')?.trim() || '';
    if (canonicalHref && !canonicalHref.startsWith('http://') && !canonicalHref.startsWith('https://')) {
      findings.push({
        findingId: `SAN-SEO-CANON-RELATIVE-${Buffer.from(page.url).toString('base64').slice(0, 8)}`,
        url: page.url,
        routeIntent,
        detectionRule: 'CANONICAL_URL_RELATIVE',
        track: 'TRACK_A_CORE_SEO',
        category: 'Indexability',
        severity: 'MEDIUM',
        evidenceClass: '[O] Observed',
        observedValue: canonicalHref,
        expectedValue: 'Absolute HTTPS canonical URL',
        exactEvidence: {
          htmlSnippet: `<link rel="canonical" href="${canonicalHref}">`,
          domSelector: 'link[rel="canonical"]'
        },
        reproductionMethod: `curl -sL '${page.url}' | grep 'rel="canonical"'`,
        businessImpact: 'Relative canonicals can resolve ambiguously across subdomains, protocols, and mirror domains.',
        recommendedRemediation: 'Supply an absolute HTTPS URL in the canonical tag.',
        automaticallyFixable: true,
        requiredAccess: 'HTML template source code',
        remediationStatus: 'ACTION_REQUIRED',
        beforeEvidence: canonicalHref,
        afterEvidence: null,
        verificationResult: null,
        timestamp: now
      });
    }
  }

  return findings;
}
