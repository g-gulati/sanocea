/**
 * SANOCEA SEO Stack — Search + Field Performance Correlation Engine
 * 
 * Correlates GSC search telemetry movement with CrUX real-user Core Web Vitals.
 * 
 * Epistemological & Causality Discipline:
 * 1. "Google Search Intelligence" observes outcomes (clicks, impressions, positions, indexing).
 *    It CANNOT observe Google's internal ranking signals or algorithmic weights.
 * 2. Never claim that poor Core Web Vitals CAUSED a ranking drop merely because both exist.
 * 3. Preserve the explicit disclaimer on every correlated finding:
 *    "Correlation observed: Poor field metric co-occurs with rank drop. Causality is NOT asserted."
 */

import { 
  CruxReport, 
  GscComparisonReport, 
  SearchPerformanceCorrelation, 
  SeoFinding,
  Severity
} from '../core/types.js';
import { classifyRouteIntent } from '../core/routeIntent.js';

export function correlateSearchAndFieldPerformance(
  comparisonReport?: GscComparisonReport,
  cruxReport?: CruxReport
): { correlations: SearchPerformanceCorrelation[]; findings: SeoFinding[] } {
  const correlations: SearchPerformanceCorrelation[] = [];
  const findings: SeoFinding[] = [];
  const now = new Date().toISOString();

  if (!comparisonReport || !cruxReport) {
    return { correlations, findings };
  }

  // Identify poor CrUX metrics on Mobile (phone) and Desktop
  const poorMobileMetrics: Array<{ metric: 'LCP' | 'INP' | 'CLS'; p75Value: number; threshold: number; rating: string }> = [];
  if (cruxReport.mobile) {
    if (cruxReport.mobile.lcp.rating === 'POOR') {
      poorMobileMetrics.push({ metric: 'LCP', p75Value: cruxReport.mobile.lcp.p75, threshold: 4000, rating: 'POOR' });
    }
    if (cruxReport.mobile.inp.rating === 'POOR') {
      poorMobileMetrics.push({ metric: 'INP', p75Value: cruxReport.mobile.inp.p75, threshold: 500, rating: 'POOR' });
    }
    if (cruxReport.mobile.cls.rating === 'POOR') {
      poorMobileMetrics.push({ metric: 'CLS', p75Value: cruxReport.mobile.cls.p75, threshold: 0.25, rating: 'POOR' });
    }
  }

  // Cross-reference with ranking losers from GSC comparison report
  if (poorMobileMetrics.length > 0 && comparisonReport.losers && comparisonReport.losers.length > 0) {
    for (const loser of comparisonReport.losers.slice(0, 5)) {
      const positionDrop = loser.positionDelta; // positive number indicates rank drop (e.g. 5.1 -> 8.2 is +3.1)
      if (positionDrop >= 2.0) {
        const metricsSnippet = poorMobileMetrics.map(m => `Mobile ${m.metric} (${m.p75Value}${m.metric === 'CLS' ? '' : 'ms'})`).join(', ');
        
        const correlationObservation = 
          `Co-occurrence: Query/Page "${loser.key}" dropped ${positionDrop.toFixed(1)} positions ` +
          `(from ${loser.baselinePosition.toFixed(1)} to ${loser.comparisonPosition.toFixed(1)}) while domain field performance exhibits ${metricsSnippet}.`;

        const causalityStatement = 
          `IMPORTANT CAUSALITY DISCLAIMER: Co-occurrence of poor Core Web Vitals and rank drop is an observed correlation, NOT proven causation. ` +
          `Google Search evaluates hundreds of concurrent signals (query intent, content relevance, competitor movements, link graphs, algorithmic updates). ` +
          `Improving page speed is necessary for conversion rate and user experience, but cannot be guaranteed to independently restore lost rankings.`;

        correlations.push({
          url: cruxReport.url,
          query: loser.key,
          rankingMovement: positionDrop,
          rankingPosition: loser.comparisonPosition,
          cruxDevice: 'PHONE',
          poorMetrics: poorMobileMetrics,
          correlationObservation,
          causalityStatement,
          supportedByFieldData: true
        });

        const routeIntent = classifyRouteIntent(cruxReport.url);
        findings.push({
          findingId: `SAN-CORRELATION-CWV-RANK-${Buffer.from(loser.key).toString('base64url').slice(0, 10)}`,
          url: cruxReport.url,
          routeIntent,
          detectionRule: 'CORRELATION_POOR_FIELD_PERFORMANCE_AND_RANK_DROP',
          track: 'SEARCH_INTELLIGENCE',
          category: 'Search Performance',
          severity: 'MEDIUM' as Severity,
          evidenceClass: '[O] Observed',
          observedValue: `Rank drop of +${positionDrop.toFixed(1)} positions co-occurring with ${metricsSnippet}`,
          expectedValue: 'Stable or improving rankings with Good field performance (Mobile LCP ≤ 2.5s, INP ≤ 200ms, CLS ≤ 0.1)',
          exactEvidence: {
            rawContext: `${correlationObservation}\n\n${causalityStatement}`
          },
          reproductionMethod: 'Cross-reference GSC period-over-period loser delta with CrUX 28-day p75 field records',
          businessImpact: 'Degraded mobile performance damages mobile conversion rates and user retention, and co-occurs with organic search rank slippage.',
          commercialRisk: {
            riskType: 'CONVERSION_FRICTION',
            title: 'Mobile CWV Deficit Co-Occurring with Ranking Movement',
            currency: 'INR',
            confidence: '[REQUIRES_ACCESS]',
            source: 'crux_field_telemetry',
            severityScore: 3,
            calculationFormula: `Correlated CWV deficit on ${cruxReport.url} [REQUIRES_ACCESS: Causality cannot be assumed; revenue attribution requires conversion telemetry]`,
            affectedChannels: ['Google Organic Search', 'Mobile Direct Traffic'],
            observedDataPoints: {
              target: loser.key,
              positionDrop,
              poorMetricsSummary: metricsSnippet,
              poorMetricsCount: poorMobileMetrics.length
            }
          },
          recommendedRemediation: 'Optimize critical rendering path (defer non-critical JavaScript, optimize hero images, eliminate render-blocking fonts) to bring field LCP below 2.5s and INP below 200ms.',
          automaticallyFixable: false,
          requiredAccess: 'Frontend Engineering / Build Pipeline',
          remediationStatus: 'ACTION_REQUIRED',
          beforeEvidence: metricsSnippet,
          afterEvidence: null,
          verificationResult: null,
          timestamp: now
        });
      }
    }
  }

  return { correlations, findings };
}
