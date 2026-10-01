/**
 * SANOCEA SEO Stack — Tier 1 SEO Pack Test Suite
 * Covers the 4 core Tier 1 deliverables:
 * 1. Extended structured data (WebSite + SearchAction, FAQPage, Article / BlogPosting)
 * 2. Image intelligence (Missing width/height CLS check, legacy PNG/JPG alert, oversized asset alert)
 * 3. Faceted navigation & combinatorial parameter explosion (Param classifier, combinatorial detection, clean canonical validation)
 * 4. Outbound broken-link detection (External link extraction, probe detection for 404/5xx, detection-only governance)
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import * as cheerio from 'cheerio';

import { runTechnicalSeoObserver } from '../src/observers/technicalSeoObserver.js';
import { runEcommerceObserver } from '../src/observers/ecommerceObserver.js';
import { 
  classifyQueryParameter, 
  classifyUrlParameters, 
  extractOutboundLinks 
} from '../src/core/urlDiscovery.js';
import { probeOutboundUrl, probeOutboundLinks } from '../src/core/crawler.js';
import { AutonomousRemediator } from '../src/worker/autonomousRemediator.js';
import { ClosedLoopRemediator } from '../src/pipeline/auditPipeline.js';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { CrawledPage, PageAuditContext, CrawlConfig } from '../src/core/types.js';

const DEFAULT_CONFIG: CrawlConfig = {
  seedUrl: 'https://www.sanocea.com',
  maxPages: 10,
  maxDepth: 3,
  allowSubdomains: false,
  enableJsRendering: false
};

function createMockPage(url: string, html: string, extra?: Partial<CrawledPage>): CrawledPage {
  return {
    url,
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8' },
    rawHtml: html,
    isJsRendered: false,
    executionTimeMs: 15,
    discoveredUrls: [],
    crawledAt: new Date().toISOString(),
    ...extra
  };
}

function createContext(page: CrawledPage): PageAuditContext {
  const $ = cheerio.load(page.rawHtml);
  return {
    page,
    $,
    isRenderedDom: false,
    crawlConfig: DEFAULT_CONFIG
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. EXTENDED STRUCTURED DATA
// ─────────────────────────────────────────────────────────────────────────────

test('1.1 Extended Structured Data — WebSite + SearchAction missing on homepage', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>SANOCEA | Multichannel Commerce</title>
        <meta name="description" content="Autonomous multichannel commerce orchestration.">
        <!-- Missing WebSite + SearchAction JSON-LD -->
      </head>
      <body>
        <h1>SANOCEA Orchestration</h1>
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const websiteFinding = findings.find(f => f.detectionRule === 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING');
  assert.ok(websiteFinding, 'Homepage without WebSite SearchAction must trigger WEBSITE_SEARCH_ACTION_SCHEMA_MISSING');
  assert.equal(websiteFinding?.category, 'Structured Data');
  // Google retired the sitelinks search box (Nov 2024): informational only, no invented loss, no auto-fix.
  assert.equal(websiteFinding?.severity, 'INFO');
  assert.equal(websiteFinding?.automaticallyFixable, false);
  assert.equal(websiteFinding?.commercialRisk, undefined);
});

test('1.2 Extended Structured Data — WebSite + SearchAction satisfied when properly declared', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>SANOCEA | Multichannel Commerce</title>
        <meta name="description" content="Autonomous multichannel commerce orchestration.">
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "WebSite",
          "name": "SANOCEA",
          "url": "https://www.sanocea.com",
          "potentialAction": {
            "@type": "SearchAction",
            "target": "https://www.sanocea.com/search?q={search_term_string}",
            "query-input": "required name=search_term_string"
          }
        }
        </script>
      </head>
      <body>
        <h1>SANOCEA Orchestration</h1>
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const websiteFinding = findings.find(f => f.detectionRule === 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING');
  assert.equal(websiteFinding, undefined, 'Properly declared WebSite SearchAction must not trigger finding');
});

test('1.3 Extended Structured Data — FAQPage missing on route with FAQ markup', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Platform FAQs | SANOCEA</title>
        <meta name="description" content="Frequently asked questions about SANOCEA multichannel automation.">
      </head>
      <body>
        <h1>Frequently Asked Questions</h1>
        <div class="faq-section">
          <div class="faq-item">
            <h3>What channels does SANOCEA support?</h3>
            <p>SANOCEA supports Shopify, Amazon, Flipkart, Blinkit, and custom ERPs.</p>
          </div>
          <div class="faq-item">
            <h3>How fast is inventory synchronization?</h3>
            <p>Synchronization occurs in sub-second latency across all connected channels.</p>
          </div>
        </div>
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/faqs', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const faqFinding = findings.find(f => f.detectionRule === 'FAQPAGE_SCHEMA_MISSING');
  assert.ok(faqFinding, 'Page with visible FAQs but no JSON-LD must trigger FAQPAGE_SCHEMA_MISSING');
  assert.equal(faqFinding?.category, 'Structured Data');
  // Google no longer shows FAQ rich results: informational only, no invented loss, no auto-fix.
  assert.equal(faqFinding?.severity, 'INFO');
  assert.equal(faqFinding?.automaticallyFixable, false);
  assert.equal(faqFinding?.commercialRisk, undefined);
  assert.doesNotMatch(faqFinding!.businessImpact, /lowering organic CTR/);
});

test('1.4 Extended Structured Data — FAQPage malformed entity detection (empty answer/question)', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Platform FAQs | SANOCEA</title>
        <meta name="description" content="Frequently asked questions about SANOCEA.">
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "mainEntity": [
            {
              "@type": "Question",
              "name": "",
              "acceptedAnswer": {
                "@type": "Answer",
                "text": ""
              }
            }
          ]
        }
        </script>
      </head>
      <body>
        <h1>FAQs</h1>
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/faqs', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const malformedFinding = findings.find(f => f.detectionRule === 'FAQPAGE_SCHEMA_MALFORMED');
  assert.ok(malformedFinding, 'FAQPage with empty Question name and Answer text must trigger FAQPAGE_SCHEMA_MALFORMED');
  assert.equal(malformedFinding?.severity, 'INFO');
  assert.equal(malformedFinding?.commercialRisk, undefined);
});

test('1.5 Extended Structured Data — Article / BlogPosting missing on editorial route', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>How to Eliminate Marketplace Mismatches | SANOCEA</title>
        <meta name="description" content="Technical guide to eradicating marketplace feed discrepancies.">
      </head>
      <body>
        <article>
          <h1>How to Eliminate Marketplace Mismatches</h1>
          <p>Marketplace mismatches between Shopify and Amazon cause severe revenue loss and account health degradation. In high-velocity retail environments, inventory synchronization latency must be held under 500 milliseconds across all active sales nodes.</p>
        </article>
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/blog/marketplace-mismatches', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const articleFinding = findings.find(f => f.detectionRule === 'ARTICLE_SCHEMA_MISSING');
  assert.ok(articleFinding, 'Editorial route without Article/BlogPosting schema must trigger ARTICLE_SCHEMA_MISSING');
  assert.equal(articleFinding?.category, 'Structured Data');
  assert.equal(articleFinding?.severity, 'HIGH');
});

test('1.6 Extended Structured Data — Article schema incomplete property detection', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Marketplace Reconciliation | SANOCEA</title>
        <meta name="description" content="Reconciliation guide.">
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "BlogPosting",
          "headline": "Marketplace Reconciliation"
        }
        </script>
      </head>
      <body>
        <article>
          <h1>Marketplace Reconciliation</h1>
          <p>Long editorial copy detailing architectural patterns for order reconciliation across multiple channels.</p>
        </article>
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/blog/reconciliation', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const incompleteFinding = findings.find(f => f.detectionRule === 'ARTICLE_SCHEMA_INCOMPLETE');
  assert.ok(incompleteFinding, 'Article missing author/date/image must trigger ARTICLE_SCHEMA_INCOMPLETE');
  assert.ok(incompleteFinding?.exactEvidence.missingSchemaProperties?.includes('author'));
  assert.ok(incompleteFinding?.exactEvidence.missingSchemaProperties?.includes('datePublished'));
  assert.ok(incompleteFinding?.exactEvidence.missingSchemaProperties?.includes('image'));
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. IMAGE INTELLIGENCE
// ─────────────────────────────────────────────────────────────────────────────

test('2.1 Image Intelligence — Missing width/height dimensions (CLS Prevention)', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head><title>Test Page | SANOCEA</title><meta name="description" content="Test meta description."></head>
      <body>
        <h1>Test Page</h1>
        <img src="/hero.webp" alt="SANOCEA Dashboard"> <!-- Missing width and height -->
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/overview', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const dimFinding = findings.find(f => f.detectionRule === 'IMAGE_MISSING_EXPLICIT_DIMENSIONS');
  assert.ok(dimFinding, 'Image missing width and height must trigger IMAGE_MISSING_EXPLICIT_DIMENSIONS');
  assert.equal(dimFinding?.category, 'Image & Media');
  assert.equal(dimFinding?.severity, 'MEDIUM');
  assert.equal(dimFinding?.automaticallyFixable, true, 'Dimension injection is safely fixable in HTML templates');
});

test('2.2 Image Intelligence — Legacy PNG/JPG format detection where NextGen is required', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head><title>Test Page | SANOCEA</title><meta name="description" content="Test description."></head>
      <body>
        <h1>Test Page</h1>
        <img src="/assets/hero-banner.jpg" width="1200" height="600" alt="Hero Banner">
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/overview', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const legacyFinding = findings.find(f => f.detectionRule === 'IMAGE_LEGACY_FORMAT_NOT_NEXTGEN');
  assert.ok(legacyFinding, 'Raster JPG without WebP/AVIF must trigger IMAGE_LEGACY_FORMAT_NOT_NEXTGEN');
  assert.equal(legacyFinding?.category, 'Image & Media');
  assert.equal(legacyFinding?.severity, 'LOW');
  assert.equal(legacyFinding?.automaticallyFixable, false, 'Raster binary format conversion requires build/CDN processing');
  assert.ok(legacyFinding?.recommendedRemediation.includes('CDN'), 'Remediation must explicitly specify build pipeline or CDN transformation');
});

test('2.3 Image Intelligence — Oversized image detection (>150KB or display width >= 1600 without srcset)', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head><title>Test Page | SANOCEA</title><meta name="description" content="Test description."></head>
      <body>
        <h1>Test Page</h1>
        <!-- Oversized width 2400px without responsive srcset -->
        <img src="/assets/huge-banner.webp" width="2400" height="1200" alt="Huge Banner">
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/overview', html);
  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const oversizedFinding = findings.find(f => f.detectionRule === 'IMAGE_OVERSIZED_PAYLOAD');
  assert.ok(oversizedFinding, 'Image with width >= 1600px without srcset must trigger IMAGE_OVERSIZED_PAYLOAD');
  assert.equal(oversizedFinding?.severity, 'MEDIUM');
  assert.equal(oversizedFinding?.automaticallyFixable, false, 'Requires responsive asset generation via build/CDN');
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. FACETED NAVIGATION & PARAMETER EXPLOSION
// ─────────────────────────────────────────────────────────────────────────────

test('3.1 Parameter Classifier — Accurately segments Facet, Tracking, and Functional parameters', () => {
  // Facet parameters
  assert.equal(classifyQueryParameter('filter'), 'FACET');
  assert.equal(classifyQueryParameter('filter.v.price.gte'), 'FACET');
  assert.equal(classifyQueryParameter('sort_by'), 'FACET');
  assert.equal(classifyQueryParameter('order'), 'FACET');
  assert.equal(classifyQueryParameter('color'), 'FACET');
  assert.equal(classifyQueryParameter('price_min'), 'FACET');

  // Tracking parameters
  assert.equal(classifyQueryParameter('utm_source'), 'TRACKING');
  assert.equal(classifyQueryParameter('utm_campaign'), 'TRACKING');
  assert.equal(classifyQueryParameter('gclid'), 'TRACKING');
  assert.equal(classifyQueryParameter('fbclid'), 'TRACKING');

  // Functional parameters (Must NOT be stripped blindly)
  assert.equal(classifyQueryParameter('page'), 'FUNCTIONAL');
  assert.equal(classifyQueryParameter('p'), 'FUNCTIONAL');
  assert.equal(classifyQueryParameter('q'), 'FUNCTIONAL');
  assert.equal(classifyQueryParameter('search'), 'FUNCTIONAL');

  // Unknown
  assert.equal(classifyQueryParameter('xyz_custom_flag'), 'UNKNOWN');
});

test('3.2 Parameter Classifier — classifyUrlParameters isolates clean category URL while retaining functional query', () => {
  const dirtyUrl = 'https://shop.example.com/collections/solar-panels?color=black&brand=waaree&sort_by=price_asc&utm_source=google&page=3';
  const { facetParams, trackingParams, functionalParams, cleanUrl } = classifyUrlParameters(dirtyUrl);

  assert.deepEqual(facetParams.sort(), ['brand', 'color', 'sort_by'].sort());
  assert.deepEqual(trackingParams, ['utm_source']);
  assert.deepEqual(functionalParams, ['page']);
  // Clean URL retains pagination functional param while stripping facets and tracking
  assert.equal(cleanUrl, 'https://shop.example.com/collections/solar-panels?page=3');
});

test('3.3 Faceted Navigation — Combinatorial parameter explosion detected on self-canonicalizing faceted URL', () => {
  const url = 'https://shop.example.com/collections/electronics?color=black&size=large&sort_by=popularity';
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Electronics Filtered | Shop</title>
        <!-- Self-referencing canonical with facet parameters -->
        <link rel="canonical" href="${url}">
      </head>
      <body>
        <h1>Filtered Electronics</h1>
      </body>
    </html>
  `;
  const page = createMockPage(url, html);
  const context = createContext(page);
  const findings = runEcommerceObserver(context);

  const comboFinding = findings.find(f => f.detectionRule === 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION');
  assert.ok(comboFinding, 'Faceted URL with multiple parameters and self-referential canonical must trigger FACETED_COMBINATORIAL_PARAMETER_EXPLOSION');
  assert.equal(comboFinding?.severity, 'HIGH');
  assert.equal(comboFinding?.track, 'TRACK_B_ECOMMERCE_INTELLIGENCE');
  assert.equal(comboFinding?.automaticallyFixable, true);
  assert.equal(comboFinding?.exactEvidence.cleanCanonicalUrl, 'https://shop.example.com/collections/electronics');
});

test('3.4 Faceted Navigation — Clean canonical or noindex suppresses combinatorial finding', () => {
  // Case A: Page has clean canonical to parent collection root
  const cleanCanonUrl = 'https://shop.example.com/collections/electronics?color=black&size=large';
  const htmlCleanCanon = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Filtered Electronics</title>
        <link rel="canonical" href="https://shop.example.com/collections/electronics">
      </head>
      <body><h1>Electronics</h1></body>
    </html>
  `;
  const pageA = createMockPage(cleanCanonUrl, htmlCleanCanon);
  const findingsA = runEcommerceObserver(createContext(pageA));
  assert.equal(
    findingsA.find(f => f.detectionRule === 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION'), 
    undefined, 
    'Faceted URL with clean canonical must not trigger explosion finding'
  );

  // Case B: Page has noindex directive
  const htmlNoindex = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Filtered Electronics</title>
        <meta name="robots" content="noindex, follow">
      </head>
      <body><h1>Electronics</h1></body>
    </html>
  `;
  const pageB = createMockPage(cleanCanonUrl, htmlNoindex);
  const findingsB = runEcommerceObserver(createContext(pageB));
  assert.equal(
    findingsB.find(f => f.detectionRule === 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION'), 
    undefined, 
    'Faceted URL with noindex directive must not trigger explosion finding'
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. OUTBOUND BROKEN-LINK DETECTION
// ─────────────────────────────────────────────────────────────────────────────

test('4.1 Outbound Links — extractOutboundLinks captures external destinations only', () => {
  const currentUrl = 'https://www.sanocea.com/about';
  const html = `
    <!DOCTYPE html>
    <html>
      <body>
        <a href="/pricing">Internal Link</a>
        <a href="https://www.sanocea.com/contact">Internal Absolute Link</a>
        <a href="https://external-partner-site.com/resource">External Partner</a>
        <a href="https://dead-vendor-domain.org/spec.pdf" aria-label="Vendor Specs">Vendor Specification</a>
      </body>
    </html>
  `;
  const outlinks = extractOutboundLinks(html, currentUrl, 'https://www.sanocea.com');
  assert.equal(outlinks.length, 2);
  assert.equal(outlinks[0].url, 'https://external-partner-site.com/resource');
  assert.equal(outlinks[0].anchorText, 'External Partner');
  assert.equal(outlinks[1].url, 'https://dead-vendor-domain.org/spec.pdf');
  assert.equal(outlinks[1].anchorText, 'Vendor Specification');
});

test('4.2 Outbound Links — Probed dead link triggers OUTBOUND_BROKEN_LINK_DETECTED (Detection-Only)', () => {
  const html = `
    <!DOCTYPE html>
    <html>
      <head><title>Resources | SANOCEA</title><meta name="description" content="Resources."></head>
      <body>
        <h1>Resources</h1>
        <a href="https://vendor-partner-dead-link.com/api">Dead Vendor Link</a>
      </body>
    </html>
  `;
  const page = createMockPage('https://www.sanocea.com/resources', html, {
    outboundLinks: [
      {
        url: 'https://vendor-partner-dead-link.com/api',
        anchorText: 'Dead Vendor Link',
        sourceUrl: 'https://www.sanocea.com/resources',
        status: 404,
        error: 'HTTP 404',
        isDead: true
      }
    ]
  });

  const context = createContext(page);
  const findings = runTechnicalSeoObserver(context);

  const brokenLinkFinding = findings.find(f => f.detectionRule === 'OUTBOUND_BROKEN_LINK_DETECTED');
  assert.ok(brokenLinkFinding, 'Dead outbound link must trigger OUTBOUND_BROKEN_LINK_DETECTED');
  assert.equal(brokenLinkFinding?.severity, 'MEDIUM');
  assert.equal(brokenLinkFinding?.automaticallyFixable, false, 'External links must NOT be deleted autonomously to protect editorial intent');
  assert.ok(brokenLinkFinding?.recommendedRemediation.includes('Autonomous deletion is suppressed'));
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. AUTONOMOUS REMEDIATION & VERIFICATION PIPELINE
// ─────────────────────────────────────────────────────────────────────────────

test('5.1 AutonomousRemediator — Refuses to auto-add WebSite SearchAction: the sitelinks search box is retired', async () => {
  const db = new SeoDatabase(':memory:');
  const remediator = new AutonomousRemediator(db);

  const finding = {
    findingId: 'FND-SAN-WEBSITE-SEARCH-01',
    url: 'https://www.sanocea.com',
    routeIntent: 'MARKETING_LANDING_PAGE' as const,
    detectionRule: 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING',
    track: 'TRACK_A_CORE_SEO' as const,
    category: 'Structured Data' as const,
    severity: 'MEDIUM' as const,
    evidenceClass: '[O] Observed' as const,
    observedValue: 'Missing WebSite SearchAction schema',
    expectedValue: 'WebSite schema with SearchAction',
    exactEvidence: { schemaType: 'WebSite' },
    reproductionMethod: 'curl -s https://www.sanocea.com | grep SearchAction',
    businessImpact: 'Disqualifies domain from Google Sitelinks Searchbox',
    recommendedRemediation: 'Inject WebSite schema with SearchAction',
    automaticallyFixable: true,
    requiredAccess: 'HTML template source code',
    remediationStatus: 'ACTION_REQUIRED' as const,
    beforeEvidence: 'Missing WebSite schema',
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const result = await remediator.remediateFinding('sanocea', finding);
  assert.equal(result.status, 'rejected');
  assert.equal(result.actionType, 'RETIRED_GOOGLE_FEATURE_NO_ACTION');
  assert.match(result.error ?? '', /retired/);
  assert.equal(db.getRemediationActions('sanocea').filter(a => a.status === 'verified').length, 0, 'nothing may be applied');
});

test('5.2 AutonomousRemediator — Successfully strips combinatorial facet bloat to clean canonical with WAL receipt', async () => {
  const db = new SeoDatabase(':memory:');
  const remediator = new AutonomousRemediator(db);

  const finding = {
    findingId: 'FND-SAN-FACET-COMBO-01',
    url: 'https://www.sanocea.com/solutions?filter=multichannel&sort_by=rank',
    routeIntent: 'FACETED_FILTER' as const,
    detectionRule: 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION',
    track: 'TRACK_B_ECOMMERCE_INTELLIGENCE' as const,
    category: 'Ecommerce' as const,
    severity: 'HIGH' as const,
    evidenceClass: '[O] Observed' as const,
    observedValue: 'Combinatorial faceted parameters without clean canonical',
    expectedValue: 'Clean canonical pointing to https://www.sanocea.com/solutions',
    exactEvidence: { cleanCanonicalUrl: 'https://www.sanocea.com/solutions' },
    reproductionMethod: 'curl -sI https://www.sanocea.com/solutions?filter=multichannel&sort_by=rank',
    businessImpact: 'Wastes crawl budget',
    recommendedRemediation: 'Point canonical to clean base URL',
    automaticallyFixable: true,
    requiredAccess: 'Template code',
    remediationStatus: 'ACTION_REQUIRED' as const,
    beforeEvidence: 'https://www.sanocea.com/solutions?filter=multichannel&sort_by=rank',
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const result = await remediator.remediateFinding('sanocea', finding);
  assert.equal(result.status, 'verified');
  assert.ok(result.verificationReceiptId?.startsWith('VRCP-ACT-SANOCEA-AUTO-'));
  assert.ok(result.afterEvidence?.includes('rel="canonical"'));
  assert.ok(!result.afterEvidence?.includes('filter='));
  db.close();
});

test('5.3 AutonomousRemediator — Rejects detection-only findings (Build/CDN requirement & Editorial protection)', async () => {
  const db = new SeoDatabase(':memory:');
  const remediator = new AutonomousRemediator(db);

  // A. Broken outbound link (Editorial protection)
  const outboundFinding = {
    findingId: 'FND-OUTBOUND-01',
    url: 'https://www.sanocea.com/partners',
    routeIntent: 'MARKETING_LANDING_PAGE' as const,
    detectionRule: 'OUTBOUND_BROKEN_LINK_DETECTED',
    track: 'TRACK_A_CORE_SEO' as const,
    category: 'Internal Linking' as const,
    severity: 'MEDIUM' as const,
    evidenceClass: '[O] Observed' as const,
    observedValue: 'Outbound link returned 404',
    expectedValue: '200 OK',
    exactEvidence: {},
    reproductionMethod: 'curl -sI https://dead-domain.com',
    businessImpact: 'Broken external user journey',
    recommendedRemediation: 'Manual review required',
    automaticallyFixable: false, // Detection-only
    requiredAccess: 'Editorial CMS',
    remediationStatus: 'ACTION_REQUIRED' as const,
    beforeEvidence: 'Dead link',
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const outboundResult = await remediator.remediateFinding('sanocea', outboundFinding);
  assert.equal(outboundResult.status, 'rejected');
  assert.equal(outboundResult.actionType, 'DETECTION_ONLY_EDITORIAL_PROTECTION');

  // B. Legacy image format (Build/CDN requirement)
  const legacyImgFinding = {
    findingId: 'FND-LEGACY-IMG-01',
    url: 'https://www.sanocea.com/hero',
    routeIntent: 'MARKETING_LANDING_PAGE' as const,
    detectionRule: 'IMAGE_LEGACY_FORMAT_NOT_NEXTGEN',
    track: 'TRACK_A_CORE_SEO' as const,
    category: 'Image & Media' as const,
    severity: 'LOW' as const,
    evidenceClass: '[O] Observed' as const,
    observedValue: 'PNG format',
    expectedValue: 'WebP/AVIF',
    exactEvidence: {},
    reproductionMethod: 'curl -sI /hero.png',
    businessImpact: 'LCP latency',
    recommendedRemediation: 'Convert to WebP via CDN',
    automaticallyFixable: false, // Detection-only
    requiredAccess: 'CDN pipeline',
    remediationStatus: 'ACTION_REQUIRED' as const,
    beforeEvidence: 'PNG',
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  const legacyResult = await remediator.remediateFinding('sanocea', legacyImgFinding);
  assert.equal(legacyResult.status, 'rejected');
  assert.equal(legacyResult.actionType, 'BUILD_OR_CDN_PIPELINE_REQUIRED');

  db.close();
});

test('5.4 ClosedLoopRemediator — End-to-end DOM patch and independent verification for FAQPage', () => {
  const initialHtml = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Pricing FAQs | SANOCEA</title>
        <meta name="description" content="Pricing FAQs.">
      </head>
      <body>
        <h1>Frequently Asked Questions</h1>
        <div class="faq">
          <p class="question">What is SANOCEA?</p>
          <p class="answer">Autonomous multichannel commerce engine.</p>
        </div>
      </body>
    </html>
  `;

  const finding = {
    findingId: 'FND-SAN-FAQ-01',
    url: 'https://www.sanocea.com/faqs',
    routeIntent: 'MARKETING_LANDING_PAGE' as const,
    detectionRule: 'FAQPAGE_SCHEMA_MISSING',
    track: 'TRACK_A_CORE_SEO' as const,
    category: 'Structured Data' as const,
    severity: 'MEDIUM' as const,
    evidenceClass: '[O] Observed' as const,
    observedValue: 'Missing FAQPage schema',
    expectedValue: 'Schema.org/FAQPage JSON-LD',
    exactEvidence: { schemaType: 'FAQPage' },
    reproductionMethod: 'curl -s https://www.sanocea.com/faqs',
    businessImpact: 'SERP rich snippet loss',
    recommendedRemediation: 'Inject FAQPage JSON-LD',
    automaticallyFixable: true,
    requiredAccess: 'Template code',
    remediationStatus: 'ACTION_REQUIRED' as const,
    beforeEvidence: 'Missing schema',
    afterEvidence: null,
    verificationResult: null,
    timestamp: new Date().toISOString()
  };

  // 1. Apply remediation
  const patchedHtml = ClosedLoopRemediator.applyRemediation(initialHtml, finding, '');
  assert.ok(patchedHtml.includes('FAQPage'));
  assert.ok(patchedHtml.includes('Question'));

  // 2. Independently recrawl & verify
  const verification = ClosedLoopRemediator.verifyRemediation(finding, patchedHtml, DEFAULT_CONFIG);
  assert.equal(verification.isResolved, true, 'FAQPage finding must be fully resolved in recrawled DOM');
  assert.equal(verification.findingAfter, null);
});
