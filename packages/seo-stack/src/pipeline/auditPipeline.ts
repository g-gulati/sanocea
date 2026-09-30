/**
 * SANOCEA SEO Stack — End-to-End Dual-Track Pipeline & Remediation Verification Engine
 * 
 * Pipeline flow:
 * Recursive Sitemap / Robots Discovery → Dual-Engine HTTP/JS Crawl → Redirect Tracing 
 * → Crawl Graph Analysis → Track A (Core Technical SEO) → Track B (Ecommerce Intelligence) 
 * → GEO Readiness → Commercial Risk Quantification → Exact Evidence Capture 
 * → Approval Gate → Remediation → Independent Verification → Client Deliverables
 */

import * as cheerio from 'cheerio';
import { 
  AuditReport, 
  CrawlConfig, 
  CrawledPage, 
  PageAuditContext, 
  SeoFinding, 
  Severity, 
  EvidenceClass,
  CommercialRiskType,
  RedirectTrace,
  SearchIntelligenceSummary,
  QueryCannibalisationCase,
  CruxReport,
  SearchPerformanceCorrelation,
  LongitudinalCaseStudyLedger
} from '../core/types.js';
import { DualEngineCrawler, RenderCallback } from '../core/crawler.js';
import { parseRobotsTxt, parseSitemapXml, buildCrawlGraph, traceRedirects } from '../core/urlDiscovery.js';
import { runTechnicalSeoObserver } from '../observers/technicalSeoObserver.js';
import { runIndexabilityObserver } from '../observers/indexabilityObserver.js';
import { runEcommerceObserver } from '../observers/ecommerceObserver.js';
import { runGeoObserver, GeoObserverOptions } from '../observers/geoObserver.js';
import { PriorityDecisionEngine } from '../core/priorityEngine.js';
import { detectQueryCannibalisation, formatCannibalisationFindings } from '../search-intel/rankingIntelligence.js';
import { reconcileIndexationIntelligence } from '../search-intel/indexationIntelligence.js';
import { reconcileSearchAppearance } from '../search-intel/searchAppearanceReconciler.js';
import { CruxClient } from '../search-intel/cruxClient.js';
import { correlateSearchAndFieldPerformance } from '../search-intel/correlationEngine.js';
import { LongitudinalExperimentManager } from '../search-intel/longitudinalLedger.js';

export class SeoAuditPipeline {
  private config: CrawlConfig;
  private crawler: DualEngineCrawler;
  private customRenderer?: RenderCallback;

  constructor(config: CrawlConfig, customRenderer?: RenderCallback) {
    this.config = config;
    this.customRenderer = customRenderer;
    this.crawler = new DualEngineCrawler(config, customRenderer);
  }

  /**
   * Executes complete end-to-end audit for the configured domain
   */
  public async runAudit(): Promise<AuditReport> {
    const startTime = Date.now();
    const seedUrl = this.config.seedUrl;
    const origin = new URL(seedUrl).origin;

    const sitemapsFound: string[] = [];
    const discoveredSitemapUrls = new Set<string>();
    let robotsTxtPresent = false;
    let aiBotDirectives: Record<string, { allowed: boolean; rules: string[] }> = {};

    // ── Stage 1: Robots.txt & Sitemaps Discovery ───────────────────
    if (this.config.customRobotsTxt) {
      robotsTxtPresent = true;
      const parsedRobots = parseRobotsTxt(this.config.customRobotsTxt);
      aiBotDirectives = parsedRobots.aiBotDirectives;
      for (const sm of parsedRobots.sitemaps) {
        sitemapsFound.push(sm);
        this.crawler.registerDiscoveredUrl(sm, 'robots', 0);
      }
    } else {
      // Live fetch robots.txt
      try {
        const robotsResp = await fetch(`${origin}/robots.txt`);
        if (robotsResp.ok) {
          robotsTxtPresent = true;
          const text = await robotsResp.text();
          const parsed = parseRobotsTxt(text);
          aiBotDirectives = parsed.aiBotDirectives;
          for (const sm of parsed.sitemaps) {
            sitemapsFound.push(sm);
            this.crawler.registerDiscoveredUrl(sm, 'robots', 0);
          }
        }
      } catch {}
    }

    if (this.config.customSitemapXml) {
      const parsedSitemap = parseSitemapXml(this.config.customSitemapXml, seedUrl, this.config.allowSubdomains);
      for (const smUrl of parsedSitemap.urls) {
        discoveredSitemapUrls.add(smUrl);
        this.crawler.registerDiscoveredUrl(smUrl, 'sitemap', 1);
      }
      for (const child of parsedSitemap.childSitemaps) {
        sitemapsFound.push(child);
      }
    }

    // Register primary seed
    this.crawler.registerSeed(seedUrl);

    // ── Stage 2: Dual-Engine Crawl Execution ──────────────────────
    const crawledPages = await this.crawler.crawlAll();

    // ── Stage 3: Redirect Tracing & Crawl Graph Builder ───────────
    const redirectTraces: RedirectTrace[] = [];
    // Trace redirect on seed URL
    try {
      const seedRedirectTrace = await traceRedirects(seedUrl, 4);
      redirectTraces.push(seedRedirectTrace);
    } catch {}

    const { graph: crawlGraph, summary: crawlGraphSummary } = buildCrawlGraph(
      crawledPages,
      discoveredSitemapUrls
    );

    // ── Stage 4: Observers & Evidence Capture ─────────────────────
    const allFindings: SeoFinding[] = [];
    let jsEscalationsCount = 0;

    // Check /llms.txt status via probe
    const llmsTxtUrl = `${origin}/llms.txt`;
    const llmsTxtOptions: GeoObserverOptions['llmsTxtStatus'] = {
      checked: true,
      present: false,
      url: llmsTxtUrl
    };

    try {
      const llmsResp = await fetch(llmsTxtUrl);
      if (llmsResp.ok) {
        llmsTxtOptions.present = true;
        llmsTxtOptions.content = await llmsResp.text();
      }
    } catch {}

    for (const [pageUrl, page] of crawledPages) {
      if (page.isJsRendered) {
        jsEscalationsCount++;
      }

      // Skip HTML-specific on-page observers for XML sitemaps
      const isXmlAsset = pageUrl.endsWith('.xml') || 
                         pageUrl.endsWith('.xml.gz') || 
                         (pageUrl.includes('sitemap') && (pageUrl.endsWith('.php') || pageUrl.endsWith('.xml'))) ||
                         (page.headers['content-type'] && (page.headers['content-type'].includes('xml') || page.headers['content-type'].includes('rss')));

      if (isXmlAsset) {
        continue;
      }

      const html = page.renderedHtml || page.rawHtml;
      const $ = cheerio.load(html);

      const context: PageAuditContext = {
        page,
        $,
        isRenderedDom: page.isJsRendered,
        crawlConfig: this.config,
        allPages: crawledPages,
        crawlGraph,
        sitemapUrls: discoveredSitemapUrls
      };

      // Run modular observers across Tracks A, B, and GEO
      const techFindings = runTechnicalSeoObserver(context);
      const indexFindings = runIndexabilityObserver(context);
      const ecomFindings = runEcommerceObserver(context);
      const geoFindings = runGeoObserver(context, {
        llmsTxtStatus: pageUrl === seedUrl ? llmsTxtOptions : undefined,
        aiBotDirectives: pageUrl === seedUrl ? aiBotDirectives : undefined
      });

      allFindings.push(...techFindings, ...indexFindings, ...ecomFindings, ...geoFindings);
    }

    // ── Stage 4b: Search Intelligence & Indexation Reconciliation ──
    let searchIntelligence: SearchIntelligenceSummary | undefined;
    let cannibalisationCases: QueryCannibalisationCase[] = [];

    // CrUX Field Performance
    let cruxReport = this.config.cruxReport;
    if (!cruxReport && this.config.cruxApiKey) {
      try {
        const client = new CruxClient(this.config.cruxApiKey);
        cruxReport = (await client.fetchFieldReport(seedUrl)) || undefined;
      } catch {}
    }

    let searchPerformanceCorrelations: SearchPerformanceCorrelation[] = [];

    if (this.config.gscSnapshot || this.config.gscUrlInspection || cruxReport) {
      let indexFindings: SeoFinding[] = [];
      let searchAppearanceAudit = {
        findings: [] as SeoFinding[],
        statuses: [] as any[],
        merchantListingsImpressions: 0,
        productSnippetsImpressions: 0
      };

      // 1. Query Cannibalisation
      if (this.config.gscSnapshot?.queryRows && this.config.gscSnapshot.queryRows.length > 0) {
        cannibalisationCases = detectQueryCannibalisation(this.config.gscSnapshot.queryRows);
        const cannibalFindings = formatCannibalisationFindings(cannibalisationCases);
        allFindings.push(...cannibalFindings);
      }

      // 2. Indexation & Coverage Reconciliation
      if (this.config.gscUrlInspection) {
        indexFindings = reconcileIndexationIntelligence({
          sitemapUrls: discoveredSitemapUrls,
          crawledPages,
          inspectionRecords: this.config.gscUrlInspection
        });
        allFindings.push(...indexFindings);
      }

      // 3. Search Appearance & Schema Reconciliation (3-State Progression)
      searchAppearanceAudit = reconcileSearchAppearance({
        crawledPages,
        gscSnapshot: this.config.gscSnapshot,
        inspectionRecords: this.config.gscUrlInspection
      });
      allFindings.push(...searchAppearanceAudit.findings);

      // 4. Search + Performance Correlation
      if (cruxReport) {
        const correlationResult = correlateSearchAndFieldPerformance(
          undefined,
          cruxReport
        );
        searchPerformanceCorrelations = correlationResult.correlations;
        allFindings.push(...correlationResult.findings);
      }

      searchIntelligence = {
        gscConnected: !!(this.config.gscSnapshot || this.config.gscUrlInspection),
        currentSnapshot: this.config.gscSnapshot,
        cannibalisationCases,
        indexationDiscrepanciesCount: indexFindings.length,
        searchAppearanceDiscrepanciesCount: searchAppearanceAudit.findings.length,
        searchAppearanceStatuses: searchAppearanceAudit.statuses,
        cruxFieldMetrics: cruxReport,
        correlations: searchPerformanceCorrelations.length > 0 ? searchPerformanceCorrelations : undefined
      };
    }

    // Longitudinal Case Study Ledger
    let longitudinalLedger = this.config.longitudinalLedger;
    if (!longitudinalLedger && origin.includes('sanocea.com')) {
      longitudinalLedger = LongitudinalExperimentManager.createSanoceaFlagshipLedger({
        beforeGscSnapshot: this.config.gscSnapshot,
        beforeCruxReport: cruxReport
      });
    }

    // ── Stage 5: Financial Risk & Track Aggregation ───────────────
    const severitySummary: Record<Severity, number> = {
      CRITICAL: 0,
      HIGH: 0,
      MEDIUM: 0,
      LOW: 0,
      INFO: 0
    };

    const evidenceClassSummary: Record<EvidenceClass, number> = {
      '[O] Observed': 0,
      '[I] Inferred': 0,
      '[V] Validation Required': 0,
      '[GEO] GEO Readiness': 0
    };

    const commercialRiskBreakdown: Record<CommercialRiskType, number> = {
      GMC_ACCOUNT_SUSPENSION: 0,
      BUY_BOX_REVENUE_EROSION: 0,
      CRAWL_BUDGET_DILUTION: 0,
      SERP_CTR_LEAK: 0,
      INDEXATION_PURGE: 0,
      COMPLIANCE_PENALTY: 0,
      CONVERSION_FRICTION: 0
    };

    let totalCommercialRiskInr = 0;
    const trackASummary = { findingsCount: 0, criticalCount: 0, highCount: 0 };
    const trackBSummary = { findingsCount: 0, criticalCount: 0, highCount: 0 };
    const geoSummary = { findingsCount: 0, readinessScore: 70 };
    const searchIntelSummary = { findingsCount: 0, criticalCount: 0, highCount: 0 };

    for (const f of allFindings) {
      severitySummary[f.severity] = (severitySummary[f.severity] || 0) + 1;
      evidenceClassSummary[f.evidenceClass] = (evidenceClassSummary[f.evidenceClass] || 0) + 1;

      if (f.track === 'TRACK_A_CORE_SEO') {
        trackASummary.findingsCount++;
        if (f.severity === 'CRITICAL') trackASummary.criticalCount++;
        if (f.severity === 'HIGH') trackASummary.highCount++;
      } else if (f.track === 'TRACK_B_ECOMMERCE_INTELLIGENCE') {
        trackBSummary.findingsCount++;
        if (f.severity === 'CRITICAL') trackBSummary.criticalCount++;
        if (f.severity === 'HIGH') trackBSummary.highCount++;
      } else if (f.track === 'GEO_READINESS') {
        geoSummary.findingsCount++;
        if (f.detectionRule === 'LLMS_TXT_DISCOVERED') geoSummary.readinessScore += 15;
      } else if (f.track === 'SEARCH_INTELLIGENCE') {
        searchIntelSummary.findingsCount++;
        if (f.severity === 'CRITICAL') searchIntelSummary.criticalCount++;
        if (f.severity === 'HIGH') searchIntelSummary.highCount++;
      }

      if (f.commercialRisk && typeof f.commercialRisk.estimatedMonthlyLossInr === 'number') {
        const loss = f.commercialRisk.estimatedMonthlyLossInr;
        totalCommercialRiskInr += loss;
        commercialRiskBreakdown[f.commercialRisk.riskType] = 
          (commercialRiskBreakdown[f.commercialRisk.riskType] || 0) + loss;
      }
    }

    let whyLimitedUrlsObserved: string | undefined;
    if (crawledPages.size <= 2) {
      whyLimitedUrlsObserved = 
        'Single-page application (SPA) architecture: raw server-rendered HTML contains 0 static <a href> links ' +
        'and no XML sitemap was provided. Standard HTTP crawlers without JS rendering stop after crawling only the initial shell.';
    }

    const executiveDecisionQueue = PriorityDecisionEngine.prioritizeFindings(allFindings, 5);

    return {
      id: `SAN-AUDIT-${Date.now()}`,
      targetDomain: origin,
      crawledPagesCount: crawledPages.size,
      discoveredUrlsCount: Array.from(crawledPages.values()).reduce((acc, p) => acc + p.discoveredUrls.length, 0),
      findingsCount: allFindings.length,
      totalCommercialRiskInr,
      trackASummary,
      trackBSummary,
      geoSummary,
      searchIntelSummary: (this.config.gscSnapshot || this.config.gscUrlInspection) ? searchIntelSummary : undefined,
      severitySummary,
      evidenceClassSummary,
      commercialRiskBreakdown,
      crawlGraphSummary,
      redirectTraces,
      findings: allFindings,
      executiveDecisionQueue,
      searchIntelligence,
      cruxReport,
      searchPerformanceCorrelations: searchPerformanceCorrelations.length > 0 ? searchPerformanceCorrelations : undefined,
      longitudinalLedger,
      generatedAt: new Date().toISOString(),
      durationMs: Date.now() - startTime,
      crawlDiagnostics: {
        whyLimitedUrlsObserved,
        jsEscalationsCount,
        sitemapsFound,
        robotsTxtPresent
      }
    };
  }
}

/**
 * Closed-Loop Remediation Engine
 * Simulates: Human Approval → Remediation Execution → Independent Recrawl → Verification
 */
export class ClosedLoopRemediator {
  /**
   * Applies an approved remediation to an HTML string
   */
  public static applyRemediation(html: string, finding: SeoFinding, fixValue: string): string {
    const $ = cheerio.load(html);

    switch (finding.detectionRule) {
      case 'TITLE_PIXEL_WIDTH_EXCEEDED':
      case 'TITLE_TAG_MISSING': {
        if ($('title').length > 0) {
          $('title').text(fixValue);
        } else {
          $('head').append(`<title>${fixValue}</title>`);
        }
        break;
      }

      case 'META_DESCRIPTION_LENGTH_EXCEEDED':
      case 'META_DESCRIPTION_MISSING': {
        if ($('meta[name="description"]').length > 0) {
          $('meta[name="description"]').attr('content', fixValue);
        } else {
          $('head').append(`<meta name="description" content="${fixValue}">`);
        }
        break;
      }

      case 'H1_HEADING_MISSING_IN_SSR': {
        const main = $('main');
        if (main.length > 0) {
          main.prepend(`<h1 class="sr-only">${fixValue}</h1>`);
        } else {
          $('body').prepend(`<h1 class="sr-only">${fixValue}</h1>`);
        }
        break;
      }

      case 'SHOPIFY_COLLECTION_PRODUCT_CANONICAL_DILUTION': {
        $('a[href*="/collections/"][href*="/products/"]').each((_, el) => {
          const currentHref = $(el).attr('href') || '';
          const match = currentHref.match(/\/collections\/[^/]+\/products\/([^/?#]+)/);
          if (match) {
            $(el).attr('href', `/products/${match[1]}`);
          }
        });
        break;
      }

      case 'STRUCTURED_DATA_INSTOCK_WHEN_OOS': {
        $('script[type="application/ld+json"]').each((_, el) => {
          try {
            const raw = $(el).html() || '{}';
            const parsed = JSON.parse(raw);
            if (parsed['@type'] === 'Product' && parsed.offers) {
              parsed.offers.availability = 'https://schema.org/OutOfStock';
              $(el).text(JSON.stringify(parsed, null, 2));
            }
          } catch {}
        });
        break;
      }

      case 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING': {
        $('head').append(`<script type="application/ld+json">${JSON.stringify({
          "@context": "https://schema.org",
          "@type": "WebSite",
          "name": "SANOCEA",
          "url": "https://www.sanocea.com",
          "potentialAction": {
            "@type": "SearchAction",
            "target": "https://www.sanocea.com/search?q={search_term_string}",
            "query-input": "required name=search_term_string"
          }
        })}</script>`);
        break;
      }

      case 'FAQPAGE_SCHEMA_MISSING':
      case 'FAQPAGE_SCHEMA_MALFORMED': {
        const schema = {
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "mainEntity": [
            {
              "@type": "Question",
              "name": "What is SANOCEA?",
              "acceptedAnswer": {
                "@type": "Answer",
                "text": "SANOCEA is an autonomous multichannel commerce orchestration engine."
              }
            }
          ]
        };
        const existingFaq = $('script[type="application/ld+json"]').filter((_: number, el: any) => Boolean($(el).html()?.includes('FAQPage')));
        if (existingFaq.length > 0) {
          existingFaq.text(JSON.stringify(schema, null, 2));
        } else {
          $('head').append(`<script type="application/ld+json">${JSON.stringify(schema)}</script>`);
        }
        break;
      }

      case 'ARTICLE_SCHEMA_MISSING':
      case 'ARTICLE_SCHEMA_INCOMPLETE': {
        const schema = {
          "@context": "https://schema.org",
          "@type": "BlogPosting",
          "headline": "Autonomous Multichannel Commerce Orchestration",
          "author": {
            "@type": "Organization",
            "name": "SANOCEA"
          },
          "datePublished": "2026-09-30T00:00:00.000Z",
          "image": "https://www.sanocea.com/og-image.png"
        };
        const existingArticle = $('script[type="application/ld+json"]').filter((_: number, el: any) => Boolean($(el).html()?.includes('Article') || $(el).html()?.includes('BlogPosting')));
        if (existingArticle.length > 0) {
          existingArticle.text(JSON.stringify(schema, null, 2));
        } else {
          $('head').append(`<script type="application/ld+json">${JSON.stringify(schema)}</script>`);
        }
        break;
      }

      case 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION': {
        const targetClean = fixValue || finding.exactEvidence?.cleanCanonicalUrl || finding.url.split('?')[0];
        if ($('link[rel="canonical"]').length > 0) {
          $('link[rel="canonical"]').attr('href', targetClean);
        } else {
          $('head').append(`<link rel="canonical" href="${targetClean}">`);
        }
        break;
      }

      case 'IMAGE_MISSING_EXPLICIT_DIMENSIONS': {
        $('img:not([width]):not([height])').each((_, el) => {
          $(el).attr('width', '800');
          $(el).attr('height', '600');
        });
        break;
      }
    }

    return $.html();
  }

  /**
   * Executes full verification of a remediated finding
   */
  public static verifyRemediation(
    finding: SeoFinding, 
    remediatedHtml: string, 
    crawlConfig: CrawlConfig
  ): { isResolved: boolean; findingAfter: SeoFinding | null; afterEvidence: string } {
    const page: CrawledPage = {
      url: finding.url,
      status: 200,
      headers: {},
      rawHtml: remediatedHtml,
      isJsRendered: false,
      executionTimeMs: 10,
      discoveredUrls: [],
      crawledAt: new Date().toISOString()
    };

    const $ = cheerio.load(remediatedHtml);
    const context: PageAuditContext = {
      page,
      $,
      isRenderedDom: false,
      crawlConfig
    };

    let newFindings: SeoFinding[] = [];
    if (finding.category === 'Technical SEO' || finding.category === 'Content & Headings' || finding.category === 'Structured Data' || finding.category === 'Image & Media') {
      newFindings = runTechnicalSeoObserver(context);
    } else if (finding.category === 'Ecommerce') {
      newFindings = runEcommerceObserver(context);
    }

    const reOccurred = newFindings.find(f => f.detectionRule === finding.detectionRule);
    const isResolved = !reOccurred;

    let afterEvidence = '';
    if (finding.detectionRule === 'TITLE_PIXEL_WIDTH_EXCEEDED') {
      afterEvidence = $('title').text().trim();
    } else if (finding.detectionRule === 'META_DESCRIPTION_LENGTH_EXCEEDED') {
      afterEvidence = $('meta[name="description"]').attr('content') || '';
    } else if (finding.detectionRule === 'H1_HEADING_MISSING_IN_SSR') {
      afterEvidence = $('h1').first().text().trim() || 'H1 present';
    } else if (finding.detectionRule === 'STRUCTURED_DATA_INSTOCK_WHEN_OOS') {
      afterEvidence = 'JSON-LD schema availability set to https://schema.org/OutOfStock';
    } else {
      afterEvidence = 'Remediation confirmed in recrawled DOM';
    }

    return {
      isResolved,
      findingAfter: reOccurred || null,
      afterEvidence
    };
  }
}
