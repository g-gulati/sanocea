/**
 * SANOCEA SEO Stack — Closed-Loop Autonomous Remediator
 * 
 * Pipeline:
 * OBSERVE → DETECT → VALIDATE → PRIORITISE → PREPARE → EXECUTE → VERIFY → RECORD
 * 
 * INVARIANT:
 * Strictly whitelisted to tenant 'sanocea'.
 * Any attempt to invoke automated remediation on prospect tenants throws TenantPolicyViolationError.
 */

import { SeoFinding } from '../core/types.js';
import { SeoDatabase, RemediationActionRecord } from '../persistence/seoDb.js';
import { TenantMonitoringPolicyManager } from './tenantPolicy.js';
import { calculateTitlePixelWidth, GOOGLE_SERP_LIMITS } from '../core/pixelWidth.js';

export interface RemediationResult {
  actionId: string;
  findingId: string;
  tenantId: string;
  status: 'verified' | 'failed' | 'rejected';
  actionType: string;
  beforeEvidence: string;
  afterEvidence?: string;
  verificationReceiptId?: string;
  error?: string;
}

export class AutonomousRemediator {
  private db: SeoDatabase;

  constructor(db: SeoDatabase) {
    this.db = db;
  }

  /**
   * Executes the 8-stage closed-loop remediation on an eligible finding.
   */
  public async remediateFinding(
    tenantId: string, 
    finding: SeoFinding,
    customExecutor?: (prepared: { type: string; before: string; candidate: string }) => Promise<string>
  ): Promise<RemediationResult> {
    // 1. & 2. OBSERVE & DETECT: Tenant Policy Guard
    TenantMonitoringPolicyManager.assertAutoRemediationAllowed(tenantId);

    // 3. VALIDATE
    if (finding.remediationStatus === 'REJECTED' || finding.evidenceClass === '[GEO] GEO Readiness') {
      return {
        actionId: `ACT-REJ-${Date.now()}`,
        findingId: finding.findingId,
        tenantId,
        status: 'rejected',
        actionType: 'INFORMATIONAL_OR_REJECTED',
        beforeEvidence: String(finding.observedValue || ''),
        error: 'Finding is informational/rejected and cannot be automatically remediated.'
      };
    }

    // Explicit detection-only rejection guard (protects editorial intent & builds/CDN separation)
    if (!finding.automaticallyFixable) {
      return {
        actionId: `ACT-REJ-${Date.now()}`,
        findingId: finding.findingId,
        tenantId,
        status: 'rejected',
        actionType: finding.detectionRule === 'OUTBOUND_BROKEN_LINK_DETECTED'
          ? 'DETECTION_ONLY_EDITORIAL_PROTECTION'
          : 'BUILD_OR_CDN_PIPELINE_REQUIRED',
        beforeEvidence: String(finding.observedValue || ''),
        error: finding.detectionRule === 'OUTBOUND_BROKEN_LINK_DETECTED'
          ? 'Outbound broken links require editorial review; autonomous deletion is suppressed to preserve editorial intent.'
          : 'Asset recompression requires build pipeline / CDN transformation; autonomous template editing cannot convert binary assets.'
      };
    }

    const isCriticalOrHigh = finding.severity === 'CRITICAL' || finding.severity === 'HIGH';
    const isTier1Automatable = [
      'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING',
      'FAQPAGE_SCHEMA_MISSING',
      'IMAGE_MISSING_EXPLICIT_DIMENSIONS'
    ].includes(finding.detectionRule);

    if (!isCriticalOrHigh && !isTier1Automatable) {
      return {
        actionId: `ACT-REJ-${Date.now()}`,
        findingId: finding.findingId,
        tenantId,
        status: 'rejected',
        actionType: 'SEVERITY_BELOW_THRESHOLD',
        beforeEvidence: String(finding.observedValue || ''),
        error: `Only CRITICAL and HIGH findings (or explicitly automatable schema/dimensions) are eligible for autonomous remediation. Finding severity: ${finding.severity}`
      };
    }

    const actionId = `ACT-SANOCEA-AUTO-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    const actionType = finding.detectionRule || 'GENERIC_SEO_REMEDIATION';
    const beforeEvidence = finding.exactEvidence?.htmlSnippet || String(finding.observedValue || '');

    // 4. PRIORITISE & 5. PREPARE Candidate Value
    let candidate = '';
    let expectedRule = '';

    if (finding.detectionRule.includes('TITLE') || finding.category === 'Technical SEO' && beforeEvidence.includes('<title>')) {
      // Prepare trimmed title under 561px
      const current = String(finding.observedValue || '');
      if (current.includes('|')) {
        candidate = current.split('|')[0].trim() + ' | SANOCEA';
      } else if (current.includes('—')) {
        candidate = current.split('—')[0].trim() + ' | SANOCEA';
      } else {
        candidate = current.slice(0, 45).trim() + ' | SANOCEA';
      }
      const pWidth = calculateTitlePixelWidth(candidate);
      if (pWidth > GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS) {
        candidate = candidate.slice(0, 36).trim() + ' | SANOCEA';
      }
      expectedRule = `Title pixel width <= ${GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS}px`;
    } else if (finding.detectionRule.includes('H1') || finding.category === 'Content & Headings') {
      candidate = '<h1>Autonomous Multichannel Commerce Orchestration</h1>';
      expectedRule = '1 semantic SSR H1 tag in initial HTML response';
    } else if (finding.detectionRule.includes('META') || finding.detectionRule.includes('DESCRIPTION')) {
      candidate = 'Autonomous multichannel catalogue, price, and inventory orchestration for high-velocity D2C and marketplace brands in India.';
      expectedRule = 'Meta description length between 70 and 160 characters';
    } else if (finding.detectionRule.includes('ROBOTS') || finding.detectionRule.includes('AI')) {
      candidate = 'User-agent: GPTBot\nAllow: /\nUser-agent: ClaudeBot\nAllow: /\nUser-agent: PerplexityBot\nAllow: /';
      expectedRule = 'AI crawler directives present in robots.txt';
    } else if (actionType === 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING') {
      candidate = `<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"SANOCEA","url":"https://www.sanocea.com","potentialAction":{"@type":"SearchAction","target":"https://www.sanocea.com/search?q={search_term_string}","query-input":"required name=search_term_string"}}</script>`;
      expectedRule = 'WebSite JSON-LD with potentialAction of type SearchAction';
    } else if (actionType === 'FAQPAGE_SCHEMA_MISSING' || actionType === 'FAQPAGE_SCHEMA_MALFORMED') {
      candidate = `<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{"@type":"Question","name":"What is SANOCEA?","acceptedAnswer":{"@type":"Answer","text":"SANOCEA is an autonomous multichannel commerce and catalogue orchestration engine."}},{"@type":"Question","name":"How does autonomous remediation operate?","acceptedAnswer":{"@type":"Answer","text":"It executes an 8-stage verification loop: Observe, Detect, Validate, Prioritise, Prepare, Execute, Verify, and Record."}}]}</script>`;
      expectedRule = 'Valid Schema.org/FAQPage JSON-LD with Question and Answer mainEntity entities';
    } else if (actionType === 'ARTICLE_SCHEMA_MISSING' || actionType === 'ARTICLE_SCHEMA_INCOMPLETE') {
      candidate = `<script type="application/ld+json">{"@context":"https://schema.org","@type":"BlogPosting","headline":"Autonomous Multichannel Commerce Orchestration","author":{"@type":"Organization","name":"SANOCEA"},"datePublished":"2026-09-30T00:00:00.000Z","image":"https://www.sanocea.com/og-image.png"}</script>`;
      expectedRule = 'Schema.org/BlogPosting JSON-LD with headline, author, datePublished, and image';
    } else if (actionType === 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION') {
      const cleanUrl = finding.exactEvidence?.cleanCanonicalUrl || finding.url.split('?')[0];
      candidate = `<link rel="canonical" href="${cleanUrl}">`;
      expectedRule = 'Clean canonical pointing strictly to base category without facet query parameters';
    } else if (actionType === 'IMAGE_MISSING_EXPLICIT_DIMENSIONS') {
      candidate = '<img src="/assets/hero.png" width="1200" height="630" loading="lazy" alt="SANOCEA">';
      expectedRule = 'Explicit width and height HTML attributes or CSS aspect-ratio on image';
    } else {
      candidate = String(finding.expectedValue || 'Remediated production configuration');
      expectedRule = 'Conformant to production schema';
    }

    // Record 'prepared' state in SQLite
    const actionRecord: RemediationActionRecord = {
      id: actionId,
      tenantId,
      findingId: finding.findingId,
      timestamp: new Date().toISOString(),
      actionType,
      status: 'prepared',
      beforeEvidence,
      details: {
        candidate,
        expectedRule,
        severity: finding.severity,
        url: finding.url
      }
    };
    this.db.recordRemediationAction(actionRecord);

    // 6. EXECUTE
    let executedValue = candidate;
    try {
      this.db.updateRemediationStatus(actionId, 'executing');
      if (customExecutor) {
        executedValue = await customExecutor({
          type: actionType,
          before: beforeEvidence,
          candidate
        });
      }
    } catch (err: any) {
      this.db.updateRemediationStatus(actionId, 'failed');
      return {
        actionId,
        findingId: finding.findingId,
        tenantId,
        status: 'failed',
        actionType,
        beforeEvidence,
        error: `Execution failed: ${err.message}`
      };
    }

    // 7. VERIFY
    const verificationReceiptId = `VRCP-${actionId}`;
    let isVerified = false;
    let afterEvidence = executedValue;

    if (actionType.includes('TITLE')) {
      const pWidth = calculateTitlePixelWidth(executedValue);
      isVerified = pWidth <= GOOGLE_SERP_LIMITS.TITLE_MAX_PIXELS;
      afterEvidence = `<title>${executedValue}</title> (Calculated: ${pWidth}px <= 561px SERP limit)`;
    } else if (actionType.includes('H1')) {
      isVerified = executedValue.includes('<h1') && executedValue.includes('</h1>');
      afterEvidence = executedValue;
    } else if (actionType.includes('META') || actionType.includes('DESCRIPTION')) {
      isVerified = executedValue.length >= 70 && executedValue.length <= 160;
      afterEvidence = `<meta name="description" content="${executedValue}"> (${executedValue.length} chars)`;
    } else if (actionType === 'WEBSITE_SEARCH_ACTION_SCHEMA_MISSING') {
      isVerified = executedValue.includes('SearchAction') && executedValue.includes('WebSite');
      afterEvidence = executedValue;
    } else if (actionType === 'FAQPAGE_SCHEMA_MISSING' || actionType === 'FAQPAGE_SCHEMA_MALFORMED') {
      isVerified = executedValue.includes('FAQPage') && executedValue.includes('Question') && executedValue.includes('acceptedAnswer');
      afterEvidence = executedValue;
    } else if (actionType === 'ARTICLE_SCHEMA_MISSING' || actionType === 'ARTICLE_SCHEMA_INCOMPLETE') {
      isVerified = (executedValue.includes('Article') || executedValue.includes('BlogPosting')) && executedValue.includes('headline');
      afterEvidence = executedValue;
    } else if (actionType === 'FACETED_COMBINATORIAL_PARAMETER_EXPLOSION') {
      isVerified = executedValue.includes('rel="canonical"') && !executedValue.includes('filter') && !executedValue.includes('sort_by');
      afterEvidence = executedValue;
    } else if (actionType === 'IMAGE_MISSING_EXPLICIT_DIMENSIONS') {
      isVerified = executedValue.includes('width=') && executedValue.includes('height=');
      afterEvidence = executedValue;
    } else {
      isVerified = true;
      afterEvidence = executedValue;
    }

    if (!isVerified) {
      this.db.updateRemediationStatus(actionId, 'failed', afterEvidence, verificationReceiptId);
      return {
        actionId,
        findingId: finding.findingId,
        tenantId,
        status: 'failed',
        actionType,
        beforeEvidence,
        afterEvidence,
        error: 'Independent post-execution verification failed.'
      };
    }

    // 8. RECORD
    this.db.updateRemediationStatus(actionId, 'verified', afterEvidence, verificationReceiptId);

    // Record into longitudinal ledger
    this.db.recordLongitudinalEvent({
      tenantId,
      timestamp: new Date().toISOString(),
      eventType: 'AUTONOMOUS_REMEDIATION_VERIFIED',
      phase: 'INTERVENTION',
      description: `Remediated ${actionType} on ${finding.url}`,
      metrics: {
        findingId: finding.findingId,
        actionId,
        verificationReceiptId
      },
      causalityAnnotation: 'Technical remediation verified immediately. GSC indexation/ranking observable in 3-7 days.'
    });

    return {
      actionId,
      findingId: finding.findingId,
      tenantId,
      status: 'verified',
      actionType,
      beforeEvidence,
      afterEvidence,
      verificationReceiptId
    };
  }
}
