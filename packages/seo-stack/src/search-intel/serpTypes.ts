/**
 * SANOCEA SEO Stack — SERP Rank Observation & Trajectory Types
 * 
 * Strict Truth Rules:
 * 1. Never fabricate historical observations.
 * 2. If monitoring begins today, Start Rank = first actual observation.
 * 3. If no previous observation exists, Previous Rank = "N/A — no observation".
 * 4. >100 must remain >100; never convert into an invented numeric rank.
 * 5. Observations must carry source/provenance ([OBSERVED: SERP Provider]).
 * 6. SERP-provider rank is strictly isolated from GSC aggregate telemetry.
 */

export type SerpType = 'ORGANIC' | 'FEATURED_SNIPPET' | 'AI_OVERVIEW' | 'KNOWLEDGE_PANEL';
export type DeviceType = 'DESKTOP' | 'MOBILE';

export interface SerpObservation {
  id?: number;
  observationId: string;
  tenantId: string;
  query: string;
  observedUrl: string | null;
  targetDomain: string;
  rank: number | null; // null represents unranked / >100
  serpType: SerpType;
  device: DeviceType;
  geography: string; // e.g. 'IN', 'US'
  language: string; // e.g. 'en'
  provider: string; // e.g. 'DATA_FOR_SEO', 'SERP_API', 'MOCK_COMPLIANT_PROVIDER'
  timestamp: string; // ISO 8601
  rawResponseJson?: string;
}

export interface SerpTrajectory {
  query: string;
  targetDomain: string;
  device: DeviceType;
  geography: string;
  language: string;
  provider: string;
  observationCount: number;

  baselineObservation: SerpObservation;
  previousObservation: SerpObservation | null;
  currentObservation: SerpObservation;

  baselineRank: number | null;
  previousRank: number | null;
  currentRank: number | null;

  dailyDelta: number | null;
  cumulativeDelta: number | null;

  startRankFormatted: string;
  previousRankFormatted: string;
  currentRankFormatted: string;
  dailyDeltaFormatted: string;
  cumulativeDeltaFormatted: string;

  lastObservedAt: string;
  provenance: string;
}

export interface SerpProviderAdapter {
  name: string;
  fetchRank(query: string, targetDomain: string, options?: {
    device?: DeviceType;
    geography?: string;
    language?: string;
  }): Promise<{
    rank: number | null;
    observedUrl: string | null;
    serpType: SerpType;
    rawJson?: string;
  }>;
}
