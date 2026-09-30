/**
 * SANOCEA SEO Stack — Priority & Decision Engine
 * 
 * Converts raw technical findings into an executive decision queue.
 * Guarantees that technically severe but commercially irrelevant findings
 * CANNOT outrank commercially consequential findings.
 * 
 * Multi-Dimensional Priority Index (PI):
 * PI = ChannelWeight × RiskTypeWeight × RouteIntentWeight × EvidenceWeight
 */

import { SeoFinding, Severity, RouteIntent, AccessTier, FinancialConfidence } from './types.js';

export type PriorityTier = 'P0_IMMEDIATE_ACTION' | 'P1_HIGH_IMPACT' | 'P2_MEDIUM_PRIORITY' | 'P3_LOW_BACKLOG' | 'P4_INFORMATIONAL';

export interface PrioritizedDecision {
  priorityRank: number;
  priorityScore: number;
  priorityTier: PriorityTier;
  findingId: string;
  url: string;
  routeIntent: RouteIntent;
  affectedChannels: string[];
  affectedSkus?: string[];
  detectionRule: string;
  findingSeverity: Severity;
  evidenceStatus: string;
  confidence: FinancialConfidence;
  businessImpactProvenance: string;
  financialImpactSummary: string;
  recommendedAction: string;
  automationOpportunity: {
    recipeType: string;
    primaryMechanism: string;
    fallbackMechanisms: string[];
    requiredAccessTier: AccessTier;
    humanApprovalRequired: boolean;
  };
  verificationMethod: string;
  rationale: string;
}

export interface PriorityScoringFactors {
  channelWeight: number;
  riskTypeWeight: number;
  routeIntentWeight: number;
  evidenceWeight: number;
  accessFrictionDiscount: number;
}

/**
 * Weights for commercial exposure channels
 */
const CHANNEL_WEIGHTS: Record<string, number> = {
  'Google Shopping': 1.0,
  'Performance Max Ads': 1.0,
  'Direct Storefront': 0.9,
  'Google Search Organic': 0.7,
  'Bing Search': 0.5,
  'AI Search Engines': 0.4
};

/**
 * Weights for commercial risk categories
 */
const RISK_TYPE_WEIGHTS: Record<string, number> = {
  'GMC_ACCOUNT_SUSPENSION': 10.0,
  'BUY_BOX_REVENUE_EROSION': 9.0,
  'INDEXATION_PURGE': 7.5,
  'CONVERSION_FRICTION': 6.0,
  'CRAWL_BUDGET_DILUTION': 5.0,
  'SERP_CTR_LEAK': 4.0,
  'COMPLIANCE_PENALTY': 2.0
};

/**
 * Weights for route architectural intent
 */
const ROUTE_INTENT_WEIGHTS: Record<RouteIntent, number> = {
  'PRODUCT_DISPLAY_PAGE': 1.0,
  'COLLECTION_PAGE': 0.85,
  'MARKETING_LANDING_PAGE': 0.75,
  'EDITORIAL_ARTICLE': 0.4,
  'FACETED_FILTER': 0.2,
  'INTERNAL_SEARCH': 0.05,
  'UTILITY_SIMULATOR': 0.05,
  'TRANSACTIONAL_UTILITY': 0.05,
  'SYSTEM_FEED': 0.0
};

/**
 * Weights for evidence certainty and data provenance
 */
const CONFIDENCE_WEIGHTS: Record<FinancialConfidence, number> = {
  '[OBSERVED]': 1.0,
  '[CALCULATED]': 0.95,
  '[REQUIRES_ACCESS]': 0.85, // High commercial risk, but telemetry pending
  '[ESTIMATED]': 0.6
};

/**
 * Computes the multi-factor priority score for a finding
 */
export function calculatePriorityScore(finding: SeoFinding): { score: number; factors: PriorityScoringFactors } {
  // 1. Channel Weight
  const channels = finding.commercialRisk?.affectedChannels || ['Direct Storefront'];
  let maxChannelWeight = 0.5;
  for (const ch of channels) {
    if (CHANNEL_WEIGHTS[ch] && CHANNEL_WEIGHTS[ch] > maxChannelWeight) {
      maxChannelWeight = CHANNEL_WEIGHTS[ch];
    }
  }

  // 2. Risk Type Weight
  const riskType = finding.commercialRisk?.riskType;
  const riskWeight = riskType && RISK_TYPE_WEIGHTS[riskType] ? RISK_TYPE_WEIGHTS[riskType] : 1.5;

  // 3. Route Intent Weight
  const intentWeight = ROUTE_INTENT_WEIGHTS[finding.routeIntent] ?? 0.5;

  // 4. Evidence / Confidence Weight
  const conf = finding.commercialRisk?.confidence || '[ESTIMATED]';
  const evidenceWeight = CONFIDENCE_WEIGHTS[conf] ?? 0.5;

  // 5. Access friction discount
  const accessTier = finding.automationOpportunity?.requiredAccessTier || 'CODE_REPO';
  let accessDiscount = 1.0;
  if (accessTier === 'NO_ACCESS_REQUIRED' || accessTier === 'FEED_ONLY') {
    accessDiscount = 1.05; // Bonus for immediate, friction-free execution
  } else if (accessTier === 'CODE_REPO') {
    accessDiscount = 0.95; // Small penalty for needing pull requests
  }

  const rawScore = maxChannelWeight * riskWeight * intentWeight * evidenceWeight * accessDiscount;
  const normalizedScore = Math.round(rawScore * 10) / 10;

  return {
    score: normalizedScore,
    factors: {
      channelWeight: maxChannelWeight,
      riskTypeWeight: riskWeight,
      routeIntentWeight: intentWeight,
      evidenceWeight,
      accessFrictionDiscount: accessDiscount
    }
  };
}

/**
 * Assigns Priority Tier based on normalized priority score
 */
export function mapScoreToTier(score: number): PriorityTier {
  if (score >= 7.0) return 'P0_IMMEDIATE_ACTION';
  if (score >= 4.0) return 'P1_HIGH_IMPACT';
  if (score >= 2.0) return 'P2_MEDIUM_PRIORITY';
  if (score >= 0.5) return 'P3_LOW_BACKLOG';
  return 'P4_INFORMATIONAL';
}

/**
 * Priority and Decision Engine
 * Prioritizes findings and outputs an executive action queue
 */
export class PriorityDecisionEngine {
  /**
   * Sorts and filters findings into a structured decision queue
   */
  public static prioritizeFindings(findings: SeoFinding[], maxActions = 5): PrioritizedDecision[] {
    const scoredList = findings.map(f => {
      const { score, factors } = calculatePriorityScore(f);
      let tier = mapScoreToTier(score);

      // Credibility Protection: Quarantine utility, internal search, simulator, and system routes
      const isUtilityRoute = 
        f.routeIntent === 'TRANSACTIONAL_UTILITY' || 
        f.routeIntent === 'INTERNAL_SEARCH' || 
        f.routeIntent === 'UTILITY_SIMULATOR' || 
        f.routeIntent === 'SYSTEM_FEED';

      if (isUtilityRoute && f.severity !== 'CRITICAL') {
        tier = 'P4_INFORMATIONAL';
      }

      // Human approval is required for all changes affecting live pricing, feeds, or code templates
      const humanApprovalRequired = 
        f.category === 'Ecommerce' || 
        f.category === 'Indexability' || 
        f.severity === 'CRITICAL';

      // Rationale explains why this item was ranked here
      let rationale = '';
      if (tier === 'P0_IMMEDIATE_ACTION') {
        rationale = `Critical commerce exception on active revenue channel (${factors.channelWeight * 100}% channel exposure). Threatens live feed eligibility or direct conversion.`;
      } else if (tier === 'P1_HIGH_IMPACT') {
        rationale = `High-consequence SEO or catalog defect on primary marketing/product route with proven evidence.`;
      } else if (tier === 'P2_MEDIUM_PRIORITY') {
        rationale = `Important technical or SERP snippet optimization; moderate ranking or crawl efficiency impact.`;
      } else {
        rationale = `Low commercial risk or utility route hygiene item; deprioritized to prevent executive distraction.`;
      }

      // Financial impact summary with strict provenance
      let financialImpactSummary = 'Non-monetized technical hygiene';
      if (f.commercialRisk) {
        if (f.commercialRisk.confidence === '[REQUIRES_ACCESS]') {
          if (typeof f.commercialRisk.estimatedMonthlyLossInr === 'number' && f.commercialRisk.estimatedMonthlyLossInr > 0) {
            financialImpactSummary = `Commercial exposure modeled at ₹${f.commercialRisk.estimatedMonthlyLossInr.toLocaleString('en-IN')}/mo [REQUIRES_ACCESS: Exact loss subject to merchant ad spend / GMV telemetry]`;
          } else {
            financialImpactSummary = `${f.commercialRisk.calculationFormula || 'Discrepancy verified in DOM/feed [REQUIRES_ACCESS: Monthly revenue loss requires merchant sales telemetry]'}`;
          }
        } else if (f.commercialRisk.confidence === '[CALCULATED]') {
          financialImpactSummary = `Calculated loss: ₹${(f.commercialRisk.estimatedMonthlyLossInr ?? 0).toLocaleString('en-IN')}/mo based on verified sales velocity`;
        } else if (f.commercialRisk.confidence === '[ESTIMATED]') {
          financialImpactSummary = `~₹${(f.commercialRisk.estimatedMonthlyLossInr ?? 0).toLocaleString('en-IN')}/mo [ESTIMATED: Benchmark model]`;
        } else if (f.commercialRisk.confidence === '[OBSERVED]') {
          financialImpactSummary = `Observed data point: ${f.commercialRisk.calculationFormula}`;
        }
      }

      const decision: PrioritizedDecision = {
        priorityRank: 0,
        priorityScore: score,
        priorityTier: tier,
        findingId: f.findingId,
        url: f.url,
        routeIntent: f.routeIntent,
        affectedChannels: f.commercialRisk?.affectedChannels || ['Direct Storefront'],
        affectedSkus: f.commercialRisk?.affectedSkus,
        detectionRule: f.detectionRule,
        findingSeverity: f.severity,
        evidenceStatus: f.evidenceClass,
        confidence: f.commercialRisk?.confidence || '[ESTIMATED]',
        businessImpactProvenance: f.commercialRisk?.source || 'industry_benchmark_estimate',
        financialImpactSummary,
        recommendedAction: f.recommendedRemediation,
        automationOpportunity: {
          recipeType: f.automationOpportunity?.recipeType || 'MANUAL_EDIT',
          primaryMechanism: f.automationOpportunity?.primaryMechanism || 'GIT_PULL_REQUEST',
          fallbackMechanisms: f.automationOpportunity?.fallbackMechanisms || ['WHATSAPP_APPROVAL'],
          requiredAccessTier: f.automationOpportunity?.requiredAccessTier || 'CODE_REPO',
          humanApprovalRequired
        },
        verificationMethod: `Independent recrawl & DOM assertion: ${f.reproductionMethod}`,
        rationale
      };

      return decision;
    });

    // Sort descending by score
    scoredList.sort((a, b) => b.priorityScore - a.priorityScore);

    // Assign sequential ranks
    scoredList.forEach((item, index) => {
      item.priorityRank = index + 1;
    });

    return scoredList.slice(0, maxActions);
  }
}
