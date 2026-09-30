/**
 * SANOCEA SEO Stack — Core Data Contracts & Interfaces
 * Phase 3: Commercial Client-Audit & Dual-Track Intelligence Engine
 * Hardened with Route Intent Filtering & Financial Provenance Tiers
 */

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export type EvidenceClass = 
  | '[O] Observed' 
  | '[I] Inferred' 
  | '[V] Validation Required' 
  | '[GEO] GEO Readiness';

export type FinancialConfidence = 
  | '[OBSERVED]'          // Directly derived from visible price/stock on page
  | '[CALCULATED]'        // Mathematical delta of two observed numbers (e.g. Price Delta = ₹200)
  | '[ESTIMATED]'         // Model projection based on stated traffic/conversion benchmarks
  | '[REQUIRES_ACCESS]';  // Requires GSC, GMC, Shopify Admin, or ERP sales telemetry

export type FinancialSource = 
  | 'storefront_dom'
  | 'schema_json_ld'
  | 'http_header'
  | 'marketplace_snapshot'
  | 'industry_benchmark_estimate'
  | 'requires_merchant_telemetry'
  | 'google_search_console'
  | 'crux_field_telemetry';

export type FindingStatus = 
  | 'ACTION_REQUIRED' 
  | 'PENDING_APPROVAL' 
  | 'APPROVED' 
  | 'REMEDIATED' 
  | 'VERIFIED' 
  | 'REJECTED' 
  | 'INFORMATIONAL';

export type FindingTrack = 
  | 'TRACK_A_CORE_SEO' 
  | 'TRACK_B_ECOMMERCE_INTELLIGENCE' 
  | 'GEO_READINESS'
  | 'SEARCH_INTELLIGENCE';

export type RouteIntent = 
  | 'MARKETING_LANDING_PAGE'
  | 'PRODUCT_DISPLAY_PAGE'
  | 'COLLECTION_PAGE'
  | 'EDITORIAL_ARTICLE'
  | 'TRANSACTIONAL_UTILITY'
  | 'INTERNAL_SEARCH'
  | 'UTILITY_SIMULATOR'
  | 'FACETED_FILTER'
  | 'SYSTEM_FEED';

export type CommercialRiskType = 
  | 'GMC_ACCOUNT_SUSPENSION' 
  | 'BUY_BOX_REVENUE_EROSION' 
  | 'CRAWL_BUDGET_DILUTION' 
  | 'SERP_CTR_LEAK' 
  | 'INDEXATION_PURGE' 
  | 'COMPLIANCE_PENALTY'
  | 'CONVERSION_FRICTION';

export interface CommercialRisk {
  riskType: CommercialRiskType;
  title: string;
  estimatedMonthlyLossInr?: number;
  currency: 'INR' | 'USD';
  confidence: FinancialConfidence;
  source: FinancialSource;
  affectedSkus?: string[];
  affectedChannels?: string[];
  severityScore: 1 | 2 | 3 | 4 | 5;
  calculationFormula: string;
  assumptions?: string[];
  observedDataPoints?: Record<string, string | number>;
}

export type AutomationRecipeType = 
  | 'DIRECT_DOM_PATCH' 
  | 'SHOPIFY_LIQUID' 
  | 'SERVER_HEADER' 
  | 'ROBOTS_TXT' 
  | 'FEED_MAP' 
  | 'SCHEMA_INJECTION' 
  | 'CANONICAL_RULE';

export type ExecutionMechanism = 
  | 'STOREFRONT_API' 
  | 'SUPPLEMENTAL_FEED' 
  | 'TAG_MANAGER_SCRIPT' 
  | 'GIT_PULL_REQUEST' 
  | 'WHATSAPP_APPROVAL';

export type AccessTier = 
  | 'NO_ACCESS_REQUIRED' 
  | 'FEED_ONLY' 
  | 'TAG_MANAGER_ONLY' 
  | 'ADMIN_OAUTH' 
  | 'CODE_REPO';

export interface AutomationOpportunity {
  automatable: boolean;
  recipeType: AutomationRecipeType;
  primaryMechanism: ExecutionMechanism;
  fallbackMechanisms: ExecutionMechanism[];
  requiredAccessTier: AccessTier;
  requiredRole: 'ENGINEERING' | 'MERCHANDISING' | 'GROWTH' | 'OPERATIONS';
  description: string;
  proposedCodeSnippet?: string;
}

export interface ExactEvidence {
  htmlSnippet?: string;
  domSelector?: string;
  pixelWidth?: number;
  charLength?: number;
  headerValue?: string;
  rawContext?: string;
  attributeValue?: string;
  priceFound?: string | number;
  priceExpected?: string | number;
  stockFound?: string;
  stockExpected?: string;
  redirectHops?: string[];
  orphanDiscoveredVia?: string;
  brokenSrc?: string;
  thinWordCount?: number;
  skippedHeading?: string;
  genericAnchorText?: string;
  inDegree?: number;
  outDegree?: number;
  competingUrls?: Array<{ url: string; clicks: number; impressions: number; position: number; share: number }>;
  gscCoverageState?: string;
  googleCanonical?: string;
  userCanonical?: string;
  searchAppearanceType?: string;
  lastCrawlTime?: string;
  // Tier 1 SEO Pack Evidence Fields
  imageDimensions?: { width?: string | number; height?: string | number };
  imageFormat?: string;
  imagePayloadBytes?: number;
  facetParams?: string[];
  cleanCanonicalUrl?: string;
  brokenOutboundUrl?: string;
  outboundStatusCode?: number;
  outboundError?: string;
  schemaType?: string;
  missingSchemaProperties?: string[];
}

export interface OutboundLinkTarget {
  url: string;
  anchorText: string;
  sourceUrl: string;
  status?: number;
  error?: string;
  isDead?: boolean;
}

export interface SeoFinding {
  findingId: string;
  url: string;
  routeIntent: RouteIntent;
  detectionRule: string;
  track: FindingTrack;
  category: 
    | 'Technical SEO' 
    | 'Indexability' 
    | 'Content & Headings' 
    | 'Security Headers' 
    | 'Ecommerce' 
    | 'GEO / AI Readiness' 
    | 'Internal Linking'
    | 'Image & Media'
    | 'Performance'
    | 'Search Performance'
    | 'Indexation & Coverage'
    | 'Structured Data'
    | 'Core Web Vitals';
  severity: Severity;
  evidenceClass: EvidenceClass;
  observedValue: string | number | null;
  expectedValue: string | number | null;
  exactEvidence: ExactEvidence;
  reproductionMethod: string;
  businessImpact: string;
  commercialRisk?: CommercialRisk;
  recommendedRemediation: string;
  automationOpportunity?: AutomationOpportunity;
  automaticallyFixable: boolean;
  requiredAccess: string;
  remediationStatus: FindingStatus;
  beforeEvidence: string | null;
  afterEvidence: string | null;
  verificationResult: string | null;
  timestamp: string;
}

export interface DiscoveredUrl {
  url: string;
  source: 'sitemap' | 'robots' | 'internal_link' | 'canonical' | 'js_render' | 'seed';
  foundOnUrl?: string;
  depth: number;
}

export interface CrawledPage {
  url: string;
  status: number;
  headers: Record<string, string>;
  rawHtml: string;
  renderedHtml?: string;
  isJsRendered: boolean;
  executionTimeMs: number;
  discoveredUrls: DiscoveredUrl[];
  outboundLinks?: OutboundLinkTarget[];
  crawledAt: string;
}

export interface CrawlGraphNode {
  url: string;
  inLinks: string[];
  outLinks: string[];
  inDegree: number;
  outDegree: number;
  depth: number;
  isOrphan: boolean;
  status: number;
  title?: string;
  h1?: string;
  wordCount?: number;
}

export interface CrawlGraphSummary {
  totalNodes: number;
  totalEdges: number;
  orphanPages: string[];
  deepestPages: { url: string; depth: number }[];
  highestInDegreePages: { url: string; inDegree: number }[];
}

export interface RedirectTrace {
  initialUrl: string;
  finalUrl: string;
  hops: { url: string; status: number }[];
  isLoop: boolean;
  hopCount: number;
}

export interface CrawlStats {
  discoveredUrlsCount: number;
  crawledUrlsCount: number;
  skippedUrlsCount: number;
  failedUrlsCount: number;
  jsEscalatedUrlsCount: number;
  deduplicatedUrlsCount: number;
  peakHeapUsedMb: number;
}

export interface CrawlConfig {
  seedUrl: string;
  maxPages: number;
  maxDepth: number;
  allowSubdomains: boolean;
  enableJsRendering: boolean;
  concurrency?: number;
  interRequestDelayMs?: number;
  retainRawHtml?: boolean;
  customRobotsTxt?: string;
  customSitemapXml?: string;
  marketplaceSnapshot?: Record<string, any>;
  gscSnapshot?: GscSnapshot;
  gscUrlInspection?: Map<string, GscUrlInspectionRecord>;
  cruxApiKey?: string;
  cruxReport?: CruxReport;
  longitudinalLedger?: LongitudinalCaseStudyLedger;
  probeOutboundLinks?: boolean;
}

export interface PageAuditContext {
  page: CrawledPage;
  $: any; // Cheerio instance
  isRenderedDom: boolean;
  crawlConfig: CrawlConfig;
  allPages?: Map<string, CrawledPage>;
  crawlGraph?: Map<string, CrawlGraphNode>;
  redirectTraces?: Map<string, RedirectTrace>;
  sitemapUrls?: Set<string>;
  gscSnapshot?: GscSnapshot;
  gscUrlInspection?: Map<string, GscUrlInspectionRecord>;
}

export interface AuditReport {
  id: string;
  targetDomain: string;
  crawledPagesCount: number;
  discoveredUrlsCount: number;
  findingsCount: number;
  totalCommercialRiskInr: number;
  trackASummary: {
    findingsCount: number;
    criticalCount: number;
    highCount: number;
  };
  trackBSummary: {
    findingsCount: number;
    criticalCount: number;
    highCount: number;
  };
  geoSummary: {
    findingsCount: number;
    readinessScore: number;
  };
  searchIntelSummary?: {
    findingsCount: number;
    criticalCount: number;
    highCount: number;
  };
  severitySummary: Record<Severity, number>;
  evidenceClassSummary: Record<EvidenceClass, number>;
  commercialRiskBreakdown: Record<CommercialRiskType, number>;
  crawlGraphSummary: CrawlGraphSummary;
  redirectTraces: RedirectTrace[];
  findings: SeoFinding[];
  executiveDecisionQueue?: any[];
  generatedAt: string;
  durationMs: number;
  crawlDiagnostics: {
    whyLimitedUrlsObserved?: string;
    jsEscalationsCount: number;
    sitemapsFound: string[];
    robotsTxtPresent: boolean;
  };
  searchIntelligence?: SearchIntelligenceSummary;
  cruxReport?: CruxReport;
  searchPerformanceCorrelations?: SearchPerformanceCorrelation[];
  longitudinalLedger?: LongitudinalCaseStudyLedger;
}

export type GscDimension = 'query' | 'page' | 'device' | 'country' | 'searchAppearance' | 'date';

export interface GscPerformanceRow {
  query?: string;
  page?: string;
  device?: 'DESKTOP' | 'MOBILE' | 'TABLET';
  country?: string;
  searchAppearance?: string;
  date?: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GscDateRange {
  startDate: string; // YYYY-MM-DD
  endDate: string;   // YYYY-MM-DD
}

export interface GscSnapshot {
  snapshotId: string;
  siteUrl: string;
  dateRange: GscDateRange;
  totalClicks: number;
  totalImpressions: number;
  averageCtr: number;
  averagePosition: number;
  queryRows: GscPerformanceRow[];
  pageRows: GscPerformanceRow[];
  deviceRows?: GscPerformanceRow[];
  countryRows?: GscPerformanceRow[];
  searchAppearanceRows?: GscPerformanceRow[];
  capturedAt: string;
}

export interface GscDimensionDelta {
  key: string;
  baselineClicks: number;
  comparisonClicks: number;
  clickDelta: number;
  baselineImpressions: number;
  comparisonImpressions: number;
  impressionDelta: number;
  baselineCtr: number;
  comparisonCtr: number;
  ctrDelta: number;
  baselinePosition: number;
  comparisonPosition: number;
  positionDelta: number; // negative number indicates rank improvement (e.g. 8.2 -> 5.1 is -3.1)
}

export interface GscComparisonReport {
  siteUrl: string;
  baselineRange: GscDateRange;
  comparisonRange: GscDateRange;
  totalClickDelta: number;
  totalImpressionDelta: number;
  averageCtrDelta: number;
  averagePositionDelta: number;
  queryDeltas: GscDimensionDelta[];
  pageDeltas: GscDimensionDelta[];
  winners: GscDimensionDelta[];
  losers: GscDimensionDelta[];
  newQueries: GscDimensionDelta[];
  lostQueries: GscDimensionDelta[];
  strikeZoneQueries: GscDimensionDelta[];
}

export interface GscPropertyVerification {
  siteUrl: string;
  verified: boolean;
  permissionLevel: 'siteOwner' | 'siteFullUser' | 'siteRestrictedUser' | 'siteUnverified';
  authMethod: 'SERVICE_ACCOUNT' | 'OAUTH_2' | 'MOCK_FIXTURE' | 'NONE';
  errorMessage?: string;
}

export interface SearchIntelligenceSummary {
  gscConnected: boolean;
  verification?: GscPropertyVerification;
  currentSnapshot?: GscSnapshot;
  comparisonReport?: GscComparisonReport;
  cannibalisationCases?: QueryCannibalisationCase[];
  indexationDiscrepanciesCount?: number;
  searchAppearanceDiscrepanciesCount?: number;
  searchAppearanceStatuses?: SearchAppearanceEntityStatus[];
  cruxFieldMetrics?: CruxReport;
  correlations?: SearchPerformanceCorrelation[];
}

export interface GscUrlInspectionRecord {
  url: string;
  verdict: 'PASS' | 'NEUTRAL' | 'FAIL';
  coverageState: 
    | 'INDEXED' 
    | 'CRAWLED_NOT_INDEXED' 
    | 'DISCOVERED_NOT_INDEXED' 
    | 'SOFT_404' 
    | 'BLOCKED_BY_ROBOTS' 
    | 'EXCLUDED_BY_NOINDEX'
    | 'REDIRECTED';
  indexingStatus: string;
  userCanonical?: string;
  googleCanonical?: string;
  lastCrawlTime?: string;
  crawledAs?: 'MOBILE' | 'DESKTOP';
  pageFetchState?: 'SUCCESSFUL' | 'SOFT_404' | 'ACCESS_DENIED' | 'NOT_FOUND';
  robotsTxtState?: 'ALLOWED' | 'DISALLOWED';
  richResultsItems?: Array<{
    name: string;
    verdict: 'PASS' | 'NEUTRAL' | 'FAIL';
    issues?: Array<{ message: string; severity: 'ERROR' | 'WARNING' }>;
  }>;
}

export interface CompetingUrlMetrics {
  url: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
  impressionShare: number; // 0.0 to 1.0
}

export interface QueryCannibalisationCase {
  query: string;
  totalImpressions: number;
  totalClicks: number;
  competingUrls: CompetingUrlMetrics[];
  dominantUrl: string;
  dominantShare: number;
  severity: Severity;
  intentMismatch: boolean;
  recommendedRemediation: string;
}

export type SearchAppearanceProgressionState = 
  | 'DECLARED_ONLY'        // Declared on page, but not verified as eligible in GSC inspection
  | 'ELIGIBLE_UNSURFACED'  // Passes GSC rich results inspection, but 0 impressions recorded in GSC
  | 'SURFACED_IN_SERP';    // Actively generating impressions in GSC search appearance rows

export interface SearchAppearanceEntityStatus {
  url: string;
  appearanceType: 'MERCHANT_LISTINGS' | 'PRODUCT_SNIPPETS' | 'REVIEW_SNIPPET' | string;
  declaredOnStorefront: boolean;
  storefrontEntityType?: string;
  inspectionVerdict?: 'PASS' | 'NEUTRAL' | 'FAIL';
  inspectionIssues?: Array<{ message: string; severity: 'ERROR' | 'WARNING' }>;
  gscImpressions: number;
  gscClicks: number;
  state: SearchAppearanceProgressionState;
  explanation: string;
}

export interface CruxMetric {
  p75: number;
  unit: 'ms' | 's' | 'unitless';
  rating: 'GOOD' | 'NEEDS_IMPROVEMENT' | 'POOR';
  histogram?: Array<{ start: number; end?: number; density: number }>;
}

export interface CruxDeviceMetrics {
  device: 'PHONE' | 'DESKTOP' | 'ALL';
  lcp: CruxMetric; // Largest Contentful Paint (ms)
  inp: CruxMetric; // Interaction to Next Paint (ms)
  cls: CruxMetric; // Cumulative Layout Shift (unitless)
  fcp?: CruxMetric;
  ttfb?: CruxMetric;
}

export interface CruxReport {
  url: string;
  scope: 'URL' | 'ORIGIN';
  collectionPeriod: { firstDate: string; lastDate: string };
  mobile?: CruxDeviceMetrics;
  desktop?: CruxDeviceMetrics;
  overallFormFactor?: CruxDeviceMetrics;
  telemetrySource: 'crux_api' | 'mock_fixture';
  fetchedAt: string;
}

export interface SearchPerformanceCorrelation {
  url: string;
  query?: string;
  rankingMovement?: number;
  rankingPosition?: number;
  cruxDevice: 'PHONE' | 'DESKTOP';
  poorMetrics: Array<{ metric: 'LCP' | 'INP' | 'CLS'; p75Value: number; threshold: number; rating: string }>;
  correlationObservation: string;
  causalityStatement: string; // Anti-causality disclaimer strictly preserved
  supportedByFieldData: boolean;
}

export interface AlgorithmUpdateContext {
  date: string; // YYYY-MM-DD
  name: string; // e.g. "March 2026 Core Update"
  affectedCategories: string[];
  notes: string;
}

export interface LongitudinalCaseStudyLedger {
  siteUrl: string;
  experimentTitle: string;
  hypothesis: string;
  
  // Phase 1: BEFORE
  before: {
    period: GscDateRange;
    technicalFindingsSummary: { totalCount: number; criticalCount: number; highCount: number };
    sampleTechnicalFindings: SeoFinding[];
    gscMetrics: { totalClicks: number; totalImpressions: number; averageCtr: number; averagePosition: number };
    cruxMetrics?: { mobileLcpP75?: number; desktopLcpP75?: number; mobileClsP75?: number };
    searchAppearanceMetrics?: { merchantListingsImpressions: number; productSnippetsImpressions: number };
  };

  // Phase 2: INTERVENTION
  intervention: {
    timestamp: string; // ISO
    remediationReceipt: {
      actionId: string;
      rule: string;
      description: string;
      appliedMechanism: string;
      beforeEvidence: string;
      afterEvidence: string;
      verifiedAt: string;
      verifier: string;
    };
  };

  // Phase 3: AFTER (Controlled Observation Window)
  after?: {
    period: GscDateRange;
    technicalState: { resolvedFindingsCount: number; verifiedClean: boolean };
    gscMetrics: { totalClicks: number; totalImpressions: number; averageCtr: number; averagePosition: number };
    cruxMetrics?: { mobileLcpP75?: number; desktopLcpP75?: number; mobileClsP75?: number };
    searchAppearanceMetrics?: { merchantListingsImpressions: number; productSnippetsImpressions: number };
    deltas: {
      clickDelta: number;
      impressionDelta: number;
      ctrDelta: number;
      positionDelta: number;
    };
  };

  // Rigor & Governance
  algorithmUpdatesInWindow: AlgorithmUpdateContext[];
  causalityAssessment: {
    isCausalityAsserted: boolean;
    confidence: '[OBSERVED]' | '[CALCULATED]' | '[REQUIRES_ACCESS]';
    nonCausalityRationale: string;
  };
}

