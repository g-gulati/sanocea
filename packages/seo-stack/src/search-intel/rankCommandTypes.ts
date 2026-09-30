/**
 * SANOCEA SEO Stack — RankCommand Feature Parity Data Contracts
 * 
 * Strict Truth Invariants:
 * 1. [OBSERVED]: Directly captured from an external authoritative API (GSC, SERP provider, Keyword provider, AI citation engine).
 * 2. [CALCULATED]: Exact mathematical derivations with documented arithmetic formulas.
 * 3. [MODELED]: Synthetic or benchmark models clearly segregated from observed metrics.
 * 4. [AWAITING_PROVIDER] / [NOT AVAILABLE]: When external data (such as backlink indices) is not connected, state NOT AVAILABLE rather than manufacturing simulated values.
 */

// ── 0. Fail-closed provider primitive ────────────────────────────────────────

/**
 * Returned by a provider that cannot supply evidence (no credentials, HTTP failure, no data).
 * It is never persisted as an observation: an absent observation means "not observed",
 * and must never be rendered as a zero/false value.
 */
export interface ProviderUnavailable {
  available: false;
  provider: string;
  reason: string;
  timestamp: string;
}

export function isProviderUnavailable(x: unknown): x is ProviderUnavailable {
  return typeof x === 'object' && x !== null && (x as any).available === false;
}

// ── 1. Keyword Intelligence Types ────────────────────────────────────────────

export type KeywordIntent = 'COMMERCIAL' | 'TRANSACTIONAL' | 'INFORMATIONAL' | 'NAVIGATIONAL' | 'UNKNOWN';

export interface KeywordMetricObservation {
  id?: number;
  observationId: string;
  tenantId: string;
  query: string;
  searchVolume: number | null; // null if provider has no data / unobserved
  cpc: number | null;
  competition: number | null; // 0.0 - 1.0 or difficulty score
  /** Heuristic keyword classification derived from query text: [INFERRED], never provider data. */
  intent: KeywordIntent;
  cluster: string;
  geography: string; // e.g. 'IN', 'US'
  language: string; // e.g. 'en'
  provider: string; // e.g. 'DATAFORSEO_LIVE'
  provenance: '[OBSERVED: KEYWORD PROVIDER]' | '[MODELED]' | '[NOT AVAILABLE]';
  timestamp: string; // ISO 8601
  rawJson?: string;
}

export interface KeywordClusterSummary {
  clusterName: string;
  totalSearchVolume: number | null;
  avgDifficulty: number | null;
  keywordsCount: number;
  commercialIntentRatio: number;
  topQueries: KeywordMetricObservation[];
  provenance: string;
}

export interface KeywordIntelligenceReport {
  tenantId: string;
  provider: string;
  totalKeywordsTracked: number;
  observedKeywordsCount: number;
  totalObservedVolume: number | null;
  clusters: KeywordClusterSummary[];
  observations: KeywordMetricObservation[];
  lastObservedAt: string;
  provenance: string;
}

// ── 2. AEO Intelligence Types ────────────────────────────────────────────────

export interface AeoObservation {
  id?: number;
  observationId: string;
  tenantId: string;
  query: string;
  targetDomain: string;
  hasFeaturedSnippet: boolean;
  featuredSnippetOwner: string | null;
  isFeaturedSnippetOwned: boolean;
  featuredSnippetText: string | null;
  hasPeopleAlsoAsk: boolean;
  paaQuestions: string[];
  hasAiOverview: boolean;
  aiOverviewCitations: string[];
  isAiOverviewOwned: boolean;
  provider: string;
  provenance: '[OBSERVED: SERP PROVIDER]';
  timestamp: string;
  rawJson?: string;
}

export interface AeoSummary {
  tenantId: string;
  totalQueriesTracked: number;
  featuredSnippetCaptureCount: number;
  featuredSnippetCaptureRate: number | null; // percentage; null when nothing was observed
  paaOpportunityCount: number;
  aiOverviewCoverageCount: number;
  aiOverviewOwnershipRate: number | null; // percentage of observed AI Overviews; null when none observed
  observations: AeoObservation[];
  /** Queries the provider could not answer (fail-closed). */
  unavailable: ProviderUnavailable[];
  provenance: string;
  lastObservedAt: string | null;
}

// ── 3. GEO Intelligence Types ────────────────────────────────────────────────

export type GeoEngine = 'PERPLEXITY' | 'CHATGPT_SEARCH' | 'GOOGLE_AI_OVERVIEW' | 'CLAUDE_SEARCH';

export interface GeoCitationObservation {
  id?: number;
  observationId: string;
  tenantId: string;
  query: string;
  engine: GeoEngine;
  isCited: boolean;
  citedUrl: string | null;
  snippetText: string | null;
  citationRank: number | null;
  targetDomain: string;
  provider: string;
  provenance: '[OBSERVED: AI CITATION ENGINE]';
  timestamp: string;
  rawJson?: string;
}

export interface GeoSummary {
  tenantId: string;
  totalTrackedQueries: number;
  totalCitationsObserved: number;
  citationRatePercent: number | null; // null when nothing was observed
  citationsByEngine: Record<string, number>;
  topCitedPages: Array<{ url: string; count: number }>;
  observations: GeoCitationObservation[];
  /** Query/engine pairs the provider could not answer (fail-closed). */
  unavailable: ProviderUnavailable[];
  provenance: string;
  lastPolledAt: string | null;
}

// ── 4. Competitive Intelligence Types ────────────────────────────────────────

export interface CompetitorConfig {
  competitorId: string;
  name: string;
  domain: string;
  sitemapUrl?: string;
  trackedRoutes: string[];
}

export interface CompetitorSitemapObservation {
  id?: number;
  observationId: string;
  tenantId: string;
  competitorId: string;
  competitorDomain: string;
  sitemapUrl: string;
  totalUrls: number;
  newlyDiscoveredUrls: string[];
  removedUrls: string[];
  /** POLL_OK: fetched + parsed + non-empty. DEGRADED: fetched + parsed but zero URLs (baseline kept, no diff).
   *  POLL_FAILED: HTTP, timeout, network or malformed-XML failure. */
  status: 'POLL_OK' | 'DEGRADED' | 'POLL_FAILED';
  httpStatus: number | null;
  /** True when a previous successful snapshot existed to diff against. */
  diffedAgainstPrevious: boolean;
  error: string | null;
  provenance: '[OBSERVED: SITEMAP FETCH]' | '[NOT AVAILABLE]';
  polledAt: string;
  rawJson?: string;
}

export type CompetitorGapStatus = 'SANOCEA_AHEAD' | 'COMPETITOR_AHEAD' | 'BOTH_UNRANKED' | 'GAP_OPPORTUNITY' | 'NOT_AVAILABLE';

export interface CompetitorKeywordGap {
  id?: number;
  tenantId: string;
  competitorId: string;
  competitorDomain: string;
  query: string;
  competitorRank: number | null;
  sanoceaRank: number | null; // from the persisted SERP trajectory ledger only; never defaulted
  gapStatus: CompetitorGapStatus;
  provenance: '[OBSERVED: SERP PROVIDER]' | '[NOT AVAILABLE]';
  lastComparedAt: string;
}

export interface CompetitorBacklinkStatus {
  status: 'NOT AVAILABLE';
  reason: string;
  providerRequired: string;
}

export interface CompetitiveIntelligenceReport {
  tenantId: string;
  competitors: CompetitorConfig[];
  sitemapObservations: CompetitorSitemapObservation[];
  keywordGaps: CompetitorKeywordGap[];
  keywordGapsStatus: 'OBSERVED' | 'NOT_AVAILABLE';
  keywordGapsUnavailableReason: string | null;
  backlinkStatus: CompetitorBacklinkStatus;
  lastUpdated: string;
  provenance: string;
}

// ── 5. Autonomous Agent Roster Types ─────────────────────────────────────────

export type AgentRole = 
  | 'SEO_STRATEGIST'
  | 'KEYWORD_RESEARCHER'
  | 'CONTENT_OPTIMIZER'
  | 'TECHNICAL_SEO'
  | 'AEO_SPECIALIST'
  | 'GEO_SPECIALIST'
  | 'LINK_BUILDING_MANAGER'
  | 'ANALYTICS_MANAGER'
  | 'COMPETITIVE_INTELLIGENCE'
  | 'AI_CONTENT_AUDITOR';

export type AgentStatus = 'IDLE' | 'EXECUTING' | 'COMPLETED' | 'AWAITING_PROVIDER' | 'ALERT';

export interface AgentTaskExecution {
  id?: number;
  taskId: string;
  tenantId: string;
  agentId: string;
  agentName: string;
  role: AgentRole;
  status: AgentStatus;
  currentTask: string;
  outputSummary: string;
  provenance: '[OBSERVED]' | '[CALCULATED]' | '[MODELED]' | '[AWAITING_PROVIDER]' | string;
  executedAt: string;
  /** Empty string until a persisted scheduler exists: no schedule is claimed that nothing will execute. */
  nextScheduledAt: string;
  details?: Record<string, any>;
}

export interface AgentRosterSummary {
  tenantId: string;
  activeAgentsCount: number;
  totalAgentsCount: number;
  roster: AgentTaskExecution[];
  lastSynchronizedAt: string;
  provenance: string;
}
