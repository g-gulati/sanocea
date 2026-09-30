/**
 * SANOCEA SEO Stack — SERP Trajectory Calculation Engine
 * 
 * Computes deterministic rank trajectories from an ordered series of SERP observations.
 * 
 * Truth Guarantees:
 * - 0 synthetic historical entries.
 * - If single observation: Start Rank = first observation, Previous Rank = "N/A — no observation", Delta = "Baseline Established".
 * - >100 is strictly preserved and never coerced into an integer.
 * - Positions compute delta as (previous - current) where positive is improvement.
 */

import { SerpObservation, SerpTrajectory } from './serpTypes.js';

export class SerpTrajectoryEngine {
  /**
   * Computes trajectory from a list of observations for a specific query.
   * Observations MUST be sorted in ascending chronological order (oldest first).
   */
  public static computeTrajectory(observations: SerpObservation[]): SerpTrajectory | null {
    if (!observations || observations.length === 0) {
      return null;
    }

    const baselineObservation = observations[0];
    const currentObservation = observations[observations.length - 1];
    const previousObservation = observations.length > 1 ? observations[observations.length - 2] : null;

    const baselineRank = baselineObservation.rank;
    const currentRank = currentObservation.rank;
    const previousRank = previousObservation ? previousObservation.rank : null;

    // Daily Delta Calculation (Previous -> Current)
    let dailyDelta: number | null = null;
    let dailyDeltaFormatted = 'N/A — no observation';

    if (previousObservation === null) {
      dailyDeltaFormatted = 'N/A — first observation';
    } else if (previousRank === null && currentRank === null) {
      dailyDeltaFormatted = 'Unchanged (>100)';
    } else if (previousRank === null && currentRank !== null) {
      dailyDeltaFormatted = `▲ Entered SERP (#${currentRank})`;
      dailyDelta = 100 - currentRank;
    } else if (previousRank !== null && currentRank === null) {
      dailyDeltaFormatted = '▼ Dropped >100';
      dailyDelta = -(100 - previousRank);
    } else if (previousRank !== null && currentRank !== null) {
      const diff = previousRank - currentRank; // e.g. 48 - 42 = +6 positions gained
      dailyDelta = diff;
      if (diff > 0) {
        dailyDeltaFormatted = `▲ +${diff} today`;
      } else if (diff < 0) {
        dailyDeltaFormatted = `▼ ${diff} today`;
      } else {
        dailyDeltaFormatted = '0 (Unchanged)';
      }
    }

    // Cumulative Delta Calculation (Baseline -> Current)
    let cumulativeDelta: number | null = null;
    let cumulativeDeltaFormatted = 'Baseline Established';

    if (observations.length === 1) {
      cumulativeDeltaFormatted = 'Baseline Established';
    } else if (baselineRank === null && currentRank === null) {
      cumulativeDeltaFormatted = 'Unranked (>100)';
    } else if (baselineRank === null && currentRank !== null) {
      cumulativeDeltaFormatted = `▲ Net Entered (#${currentRank})`;
      cumulativeDelta = 100 - currentRank;
    } else if (baselineRank !== null && currentRank === null) {
      cumulativeDeltaFormatted = '▼ Dropped >100';
      cumulativeDelta = -(100 - baselineRank);
    } else if (baselineRank !== null && currentRank !== null) {
      const netDiff = baselineRank - currentRank;
      cumulativeDelta = netDiff;
      if (netDiff > 0) {
        cumulativeDeltaFormatted = `▲ +${netDiff} pos`;
      } else if (netDiff < 0) {
        cumulativeDeltaFormatted = `▼ ${netDiff} pos`;
      } else {
        cumulativeDeltaFormatted = '0 (Flat)';
      }
    }

    // Formatted Rank Strings
    const currentRankFormatted = currentRank !== null ? `#${currentRank}` : '>100';
    
    let startRankFormatted: string;
    if (observations.length === 1) {
      startRankFormatted = currentRank !== null ? `#${currentRank} — first observation` : '>100 — first observation';
    } else {
      startRankFormatted = baselineRank !== null ? `#${baselineRank}` : '>100';
    }

    const previousRankFormatted = previousObservation === null
      ? 'N/A — no observation'
      : (previousRank !== null ? `#${previousRank}` : '>100');

    return {
      query: currentObservation.query,
      targetDomain: currentObservation.targetDomain,
      device: currentObservation.device,
      geography: currentObservation.geography,
      language: currentObservation.language,
      provider: currentObservation.provider,
      observationCount: observations.length,

      baselineObservation,
      previousObservation,
      currentObservation,

      baselineRank,
      previousRank,
      currentRank,

      dailyDelta,
      cumulativeDelta,

      startRankFormatted,
      previousRankFormatted,
      currentRankFormatted,
      dailyDeltaFormatted,
      cumulativeDeltaFormatted,

      lastObservedAt: currentObservation.timestamp,
      provenance: `[OBSERVED: ${currentObservation.provider}]`
    };
  }
}
