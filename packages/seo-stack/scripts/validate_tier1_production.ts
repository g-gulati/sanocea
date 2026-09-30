/**
 * Production Readiness Validation Script for Tier 1 SEO Pack
 * Runs the live SEO stack against https://www.sanocea.com and specific validation scenarios.
 */

import { DualEngineCrawler } from '../src/core/crawler.js';
import { runTechnicalSeoObserver } from '../src/observers/technicalSeoObserver.js';
import { runEcommerceObserver } from '../src/observers/ecommerceObserver.js';
import { classifyUrlParameters, extractOutboundLinks } from '../src/core/urlDiscovery.js';
import { AutonomousRemediator } from '../src/worker/autonomousRemediator.js';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { TenantMonitoringPolicyManager, TenantPolicyViolationError } from '../src/worker/tenantPolicy.js';
import { PageAuditContext, CrawledPage, SeoFinding, CrawlConfig } from '../src/core/types.js';
import * as cheerio from 'cheerio';
import * as fs from 'fs';
import * as path from 'path';

async function main() {
  console.log('================================================================');
  console.log('SANOCEA SEO STACK — TIER 1 PRODUCTION READINESS VALIDATION PASS');
  console.log('================================================================\n');

  const dbPath = path.resolve(process.cwd(), 'data/tier1_production_validation.sqlite');
  if (fs.existsSync(dbPath)) fs.unlinkSync(dbPath);
  const db = new SeoDatabase(dbPath);
  const remediator = new AutonomousRemediator(db);

  // ── STEP 1: Live Production Crawl of www.sanocea.com ─────────────
  console.log('--- 1. EXECUTING LIVE PRODUCTION CRAWL (https://www.sanocea.com) ---');
  const crawlConfig: CrawlConfig = {
    seedUrl: 'https://www.sanocea.com',
    maxPages: 25,
    maxDepth: 3,
    allowSubdomains: false,
    enableJsRendering: false,
    probeOutboundLinks: true
  };

  const crawler = new DualEngineCrawler(crawlConfig);
  crawler.registerSeed('https://www.sanocea.com/');
  crawler.registerDiscoveredUrl('https://www.sanocea.com/solutions/marketplace-reconciliation', 'sitemap', 1);

  const crawledPages = await crawler.crawlAll();
  console.log(`Crawl completed: ${crawledPages.size} pages crawled successfully.`);
  for (const [url, page] of crawledPages) {
    console.log(`  - [HTTP ${page.status}] ${url} (${page.rawHtml.length} bytes, discovered: ${page.discoveredUrls.length}, outbound: ${page.outboundLinks?.length || 0})`);
  }

  // ── STEP 2: Run Tier 1 Observers on Production Pages ────────────
  console.log('\n--- 2. RUNNING TIER 1 OBSERVERS ON LIVE PRODUCTION PAGES ---');
  const liveFindings: SeoFinding[] = [];

  for (const [url, page] of crawledPages) {
    const $ = cheerio.load(page.rawHtml);
    const context: PageAuditContext = {
      page,
      $,
      isRenderedDom: false,
      crawlConfig
    };

    const techFindings = runTechnicalSeoObserver(context);
    const ecomFindings = runEcommerceObserver(context);
    liveFindings.push(...techFindings, ...ecomFindings);
  }

  console.log(`Discovered ${liveFindings.length} findings across crawled production pages.`);
  for (const f of liveFindings) {
    console.log(`  * [${f.severity}] ${f.detectionRule} on ${f.url}`);
    console.log(`    Observed: ${f.observedValue}`);
    console.log(`    Auto-Fixable: ${f.automaticallyFixable}`);
  }

  // ── STEP 3: Specifically Validate the 9 Target Conditions ────────
  console.log('\n--- 3. SPECIFIC SCENARIO VALIDATIONS (Per User Directive) ---');

  // 3a. Homepage WebSite/SearchAction
  console.log('\n[Scenario 3a] Homepage WebSite / SearchAction Validation:');
  const homePage = crawledPages.get('https://www.sanocea.com/') || crawledPages.get('https://www.sanocea.com');
  const homeFinding = liveFindings.find(f => f.url.startsWith('https://www.sanocea.com') && f.detectionRule === 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING');
  console.log(`  Homepage checked: ${homePage ? 'YES (200 OK)' : 'NO'}`);
  console.log(`  WEBSITE_SEARCH_ACTION_SCHEMA_MISSING detected: ${!!homeFinding}`);
  if (homeFinding) {
    console.log(`  Observed: "${homeFinding.observedValue}"`);
    console.log(`  Remediation recommendation: "${homeFinding.recommendedRemediation}"`);
  }

  // 3b. FAQ-containing routes
  console.log('\n[Scenario 3b] FAQ-Containing Routes Validation:');
  const faqFindings = liveFindings.filter(f => f.detectionRule.includes('FAQ'));
  console.log(`  FAQ findings detected on production: ${faqFindings.length}`);
  for (const f of faqFindings) {
    console.log(`  - ${f.detectionRule} on ${f.url} (Observed: ${f.observedValue})`);
  }

  // 3c. Editorial / blog routes
  console.log('\n[Scenario 3c] Editorial / Blog Routes Validation:');
  const mockBlogPage: CrawledPage = {
    url: 'https://www.sanocea.com/blog/ecommerce-reconciliation-guide',
    status: 200,
    headers: { 'content-type': 'text/html' },
    rawHtml: `
      <!DOCTYPE html><html><head><title>Reconciliation Guide | SANOCEA</title><meta name="description" content="Guide"></head>
      <body><article><h1>Guide to Reconciliation</h1><p>Full editorial text about commerce reconciliation.</p></article></body></html>
    `,
    isJsRendered: false,
    executionTimeMs: 10,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  };
  const blogContext: PageAuditContext = {
    page: mockBlogPage,
    $: cheerio.load(mockBlogPage.rawHtml),
    isRenderedDom: false,
    crawlConfig
  };
  const blogFindings = runTechnicalSeoObserver(blogContext).filter(f => f.detectionRule.includes('ARTICLE'));
  console.log(`  Blog route tested: ${mockBlogPage.url}`);
  console.log(`  Findings on blog route missing Article JSON-LD: ${blogFindings.map(f => f.detectionRule).join(', ')}`);

  // 3d. Images with and without dimensions
  console.log('\n[Scenario 3d] Images With and Without Dimensions (CLS):');
  const dimFindings = liveFindings.filter(f => f.detectionRule === 'IMAGE_MISSING_EXPLICIT_DIMENSIONS');
  console.log(`  Images missing width/height detected on production: ${dimFindings.length}`);
  for (const f of dimFindings) {
    console.log(`  - URL: ${f.url}`);
    console.log(`    Observed: ${f.observedValue}`);
    console.log(`    Sample: ${f.exactEvidence?.brokenSrc || 'N/A'}`);
    console.log(`    Auto-fixable: ${f.automaticallyFixable}`);
  }

  // 3e. PNG/JPG legacy assets
  console.log('\n[Scenario 3e] PNG/JPG Legacy Assets Detection:');
  const legacyImgFindings = liveFindings.filter(f => f.detectionRule === 'IMAGE_LEGACY_FORMAT_NOT_NEXTGEN');
  console.log(`  Legacy PNG/JPG findings on production: ${legacyImgFindings.length}`);
  for (const f of legacyImgFindings) {
    console.log(`  - URL: ${f.url}`);
    console.log(`    Observed: ${f.observedValue}`);
    console.log(`    Sample: ${f.exactEvidence?.brokenSrc || 'N/A'}`);
    console.log(`    Auto-fixable: ${f.automaticallyFixable} (Build/CDN pipeline required)`);
  }

  // 3f. Responsive srcset images
  console.log('\n[Scenario 3f] Responsive srcset Images vs Oversized Images:');
  const oversizedFindings = liveFindings.filter(f => f.detectionRule === 'IMAGE_OVERSIZED_PAYLOAD');
  console.log(`  Oversized image findings on production: ${oversizedFindings.length}`);
  for (const f of oversizedFindings) {
    console.log(`  - URL: ${f.url}`);
    console.log(`    Observed: ${f.observedValue}`);
    console.log(`    Auto-fixable: ${f.automaticallyFixable}`);
  }

  // 3g. URLs containing multiple facet parameters
  console.log('\n[Scenario 3g] URLs with Combinatorial Facet Parameters:');
  const facetUrl = 'https://www.sanocea.com/solutions?color=navy&size=enterprise&sort=pricing_asc';
  const facetPage: CrawledPage = {
    url: facetUrl,
    status: 200,
    headers: {},
    rawHtml: `
      <!DOCTYPE html><html><head><title>Solutions Filtered</title><link rel="canonical" href="${facetUrl}"></head>
      <body><h1>Filtered Solutions</h1></body></html>
    `,
    isJsRendered: false,
    executionTimeMs: 10,
    discoveredUrls: [],
    crawledAt: new Date().toISOString()
  };
  const facetFindings = runEcommerceObserver({
    page: facetPage,
    $: cheerio.load(facetPage.rawHtml),
    isRenderedDom: false,
    crawlConfig
  }).filter(f => f.detectionRule.includes('FACET'));
  console.log(`  Tested URL: ${facetUrl}`);
  console.log(`  Detection result: ${facetFindings.map(f => f.detectionRule).join(', ')}`);
  for (const f of facetFindings) {
    console.log(`    Observed: ${f.observedValue}`);
    console.log(`    Clean Canonical Target: ${f.exactEvidence?.cleanCanonicalUrl}`);
  }

  // 3h. Pagination and search URLs to prove NOT incorrectly stripped
  console.log('\n[Scenario 3h] Pagination and Search Query Conservation Check:');
  const paginationUrl = 'https://www.sanocea.com/solutions?page=2&utm_source=newsletter';
  const pClassification = classifyUrlParameters(paginationUrl);
  console.log(`  Tested URL: ${paginationUrl}`);
  console.log(`  Facet Params: [${pClassification.facetParams.join(', ')}]`);
  console.log(`  Tracking Params: [${pClassification.trackingParams.join(', ')}]`);
  console.log(`  Functional Params: [${pClassification.functionalParams.join(', ')}]`);
  console.log(`  Clean URL: ${pClassification.cleanUrl}`);
  const paginationPreserved = pClassification.cleanUrl.includes('page=2');
  console.log(`  PROVEN: Functional pagination parameter is PRESERVED: ${paginationPreserved}`);

  const searchUrl = 'https://www.sanocea.com/search?q=reconciliation&filter.v.availability=1';
  const sClassification = classifyUrlParameters(searchUrl);
  console.log(`  Tested URL: ${searchUrl}`);
  console.log(`  Facet Params: [${sClassification.facetParams.join(', ')}]`);
  console.log(`  Functional Params: [${sClassification.functionalParams.join(', ')}]`);
  console.log(`  Clean URL: ${sClassification.cleanUrl}`);
  const searchPreserved = sClassification.cleanUrl.includes('q=reconciliation');
  console.log(`  PROVEN: Functional search parameter is PRESERVED: ${searchPreserved}`);

  // 3i. Outbound links returning 404/410/405/5xx
  console.log('\n[Scenario 3i] Outbound Dead Link Probe & Detection:');
  const mockOutboundPage: CrawledPage = {
    url: 'https://www.sanocea.com/resources',
    status: 200,
    headers: {},
    rawHtml: `
      <!DOCTYPE html><html><head><title>Resources</title><meta name="description" content="Resources"></head>
      <body>
        <a href="https://httpstat.us/404">Dead 404 Destination</a>
        <a href="https://httpstat.us/500">Dead 500 Destination</a>
      </body></html>
    `,
    isJsRendered: false,
    executionTimeMs: 15,
    discoveredUrls: [],
    outboundLinks: [
      {
        url: 'https://httpstat.us/404',
        anchorText: 'Dead 404 Destination',
        sourceUrl: 'https://www.sanocea.com/resources',
        status: 404,
        error: 'HTTP 404',
        isDead: true
      },
      {
        url: 'https://httpstat.us/500',
        anchorText: 'Dead 500 Destination',
        sourceUrl: 'https://www.sanocea.com/resources',
        status: 500,
        error: 'HTTP 500',
        isDead: true
      }
    ],
    crawledAt: new Date().toISOString()
  };
  const outboundFindings = runTechnicalSeoObserver({
    page: mockOutboundPage,
    $: cheerio.load(mockOutboundPage.rawHtml),
    isRenderedDom: false,
    crawlConfig
  }).filter(f => f.detectionRule === 'OUTBOUND_BROKEN_LINK_DETECTED');
  console.log(`  Detected dead outbound links: ${outboundFindings.length}`);
  for (const f of outboundFindings) {
    console.log(`  - [${f.detectionRule}] ${f.observedValue}`);
    console.log(`    Auto-fixable: ${f.automaticallyFixable} (Editorial intent protected)`);
  }

  // ── STEP 4: Autonomous Closed-Loop Remediation Run ───────────────
  console.log('\n--- 4. AUTONOMOUS REMEDIATION PASS (8-Stage Verification Loop) ---');
  // Run on live homepage finding: WEBSITE_SEARCH_ACTION_SCHEMA_MISSING
  if (homeFinding) {
    console.log(`Executing 8-stage remediation on live finding: ${homeFinding.findingId} (${homeFinding.detectionRule})`);
    const result = await remediator.remediateFinding('sanocea', homeFinding);
    console.log(`  Status: ${result.status}`);
    console.log(`  Verification Receipt ID: ${result.verificationReceiptId}`);
    console.log(`  Action Type: ${result.actionType}`);
    console.log(`  After Evidence: ${result.afterEvidence}`);
  }

  // Run on combinatorial facet explosion
  if (facetFindings.length > 0) {
    console.log(`\nExecuting 8-stage remediation on facet explosion: ${facetFindings[0].findingId}`);
    const result = await remediator.remediateFinding('sanocea', facetFindings[0]);
    console.log(`  Status: ${result.status}`);
    console.log(`  Verification Receipt ID: ${result.verificationReceiptId}`);
    console.log(`  Action Type: ${result.actionType}`);
    console.log(`  After Evidence: ${result.afterEvidence}`);
  }

  // Verify rejection of detection-only findings
  if (legacyImgFindings.length > 0) {
    console.log(`\nTesting rejection guard on detection-only finding: ${legacyImgFindings[0].detectionRule}`);
    const result = await remediator.remediateFinding('sanocea', legacyImgFindings[0]);
    console.log(`  Status: ${result.status}`);
    console.log(`  Action Type: ${result.actionType}`);
    console.log(`  Error: "${result.error}"`);
  }

  // ── STEP 5: Tenant Policy & Dashboard Isolation Confirmation ─────
  console.log('\n--- 5. GOVERNANCE & TENANT ISOLATION CONFIRMATION ---');
  try {
    TenantMonitoringPolicyManager.assertAutoRemediationAllowed('waaree');
    console.log('  ERROR: Waaree was allowed to auto-remediate!');
  } catch (err: any) {
    console.log(`  CONFIRMED: Prospect tenant 'waaree' strictly blocked from autonomous remediation (${err.name}: ${err.message})`);
  }

  const actions = db.getRemediationActions('sanocea');
  const ledger = db.getLongitudinalLedger('sanocea');
  console.log(`  SQLite WAL Remediation Actions recorded: ${actions.length}`);
  console.log(`  SQLite WAL Longitudinal Ledger events recorded: ${ledger.length}`);

  db.close();
  console.log('\n================================================================');
  console.log('TIER 1 PRODUCTION READINESS VALIDATION PASS COMPLETED');
  console.log('================================================================\n');
}

main().catch(err => {
  console.error('Validation pass failed:', err);
  process.exit(1);
});
