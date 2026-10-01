import React from 'react'

export default function FindingDetailDrawer({finding, isOpen, onClose, onApprove, isApproved, onSwitchToWhatsApp}) {
  if (!isOpen || !finding) return null

  const getEvidenceBadgeClass = (status) => {
    switch (status) {
      case 'REPRODUCED':
        return 'evidence-reproduced'
      case 'PARTIAL':
        return 'evidence-partial'
      case 'SNAPSHOT':
        return 'evidence-snapshot'
      case 'NOT_VERIFIABLE':
        return 'evidence-unverified'
      default:
        return 'evidence-reproduced'
    }
  }

  const getEvidenceLabel = (status) => {
    switch (status) {
      case 'REPRODUCED':
        return '✓ REPRODUCED (Live Crawl Verified)'
      case 'PARTIAL':
        return '⚠ PARTIALLY REPRODUCED (Live Confirmed Subset)'
      case 'SNAPSHOT':
        return '📸 SNAPSHOT (Point-in-Time Live Capture)'
      case 'NOT_VERIFIABLE':
        return '🚫 NOT VERIFIABLE TODAY (Quarantined)'
      default:
        return status || '✓ REPRODUCED'
    }
  }

  // Lifecycle steps in order: Detect -> Validate -> Quantify -> Prioritise -> Prepare -> Approve -> Execute -> Verify
  const lifecycleSteps = [
    { key: 'detect', label: '1. Detect', desc: finding.executionPath?.detect || 'Discovered during continuous crawl & telemetry ingestion.' },
    { key: 'validate', label: '2. Validate', desc: finding.executionPath?.validate || 'Validated against DOM state, route intent and live URL verification.' },
    { key: 'quantify', label: '3. Quantify', desc: finding.executionPath?.quantify || finding.executionPath?.explain || 'Quantified via strict financial provenance.' },
    { key: 'prioritise', label: '4. Prioritise', desc: finding.executionPath?.prioritise || `Ranked by Commercial Impact Index (CII: ${finding.priorityScore}).` },
    { key: 'prepare', label: '5. Prepare', desc: finding.executionPath?.prepare || 'Remediation payload generated and staged.' },
    { key: 'approve', label: '6. Approve', desc: finding.executionPath?.approve || (finding.humanApprovalRequired ? 'Human sign-off required via Dashboard or WhatsApp.' : 'Pre-approved safe autonomous operation.') },
    { key: 'execute', label: '7. Execute', desc: finding.executionPath?.execute || 'Automated dispatch via API, feed override, or PR merge.' },
    { key: 'verify', label: '8. Verify', desc: finding.executionPath?.verify || 'Automated recrawl confirms compliant state and clears alarm.' }
  ]

  const liveTargetUrl = finding.liveEvidenceUrl || finding.exactEvidence?.sourceUrl || finding.url

  return (
    <div className="finding-drawer-backdrop" onClick={onClose}>
      <div className="finding-drawer-card" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <div className="drawer-header">
          <div className="drawer-title-col">
            <div className="drawer-meta-badges">
              <span className={`drawer-tier-badge ${finding.badgeClass || 'p0'}`}>{finding.priorityTier}</span>
              <span className="drawer-score-badge">CII Score: {finding.priorityScore}</span>
              <span className={`drawer-evidence-badge ${getEvidenceBadgeClass(finding.evidenceStatus)}`}>
                {getEvidenceLabel(finding.evidenceStatus)}
              </span>
              <span className="drawer-prov-badge">{finding.provenanceTier}</span>
              <span className="drawer-cat-badge">{finding.category}</span>
            </div>
            
            <h3 className="drawer-title">{finding.findingTitle}</h3>

            <div className="drawer-meta-subrow">
              <span className="meta-tag-item"><strong>SKU / Ref:</strong> <code>{finding.affectedSku || 'N/A'}</code></span>
              <span className="meta-tag-item"><strong>Channel:</strong> {finding.affectedChannel}</span>
              <span className="meta-tag-item"><strong>Remediation Status:</strong> <code className="status-code">{finding.remediationStatus || 'ACTION_REQUIRED'}</code></span>
              <span className="meta-tag-item"><strong>Access Tier:</strong> <code className="access-tier-code">{finding.automationSuitability?.accessTier || finding.minimumAccessRequired}</code></span>
            </div>

            <div className="drawer-url-row">
              <span className="drawer-url-label">Direct Target URL:</span>
              <a href={liveTargetUrl} target="_blank" rel="noopener noreferrer" className="drawer-url-link">
                {liveTargetUrl} ↗
              </a>
              <a href={liveTargetUrl} target="_blank" rel="noopener noreferrer" className="btn-direct-live-evidence">
                🌐 Open Live Source in Browser ↗
              </a>
            </div>

            {finding.evidenceStatusNote && (
              <div className="drawer-evidence-note-box">
                <span className="note-icon">📋</span>
                <span className="note-text"><strong>Live URL Evidence Status:</strong> {finding.evidenceStatusNote}</span>
              </div>
            )}
          </div>
          <button type="button" className="btn-close-drawer" onClick={onClose} aria-label="Close drawer">
            ✕
          </button>
        </div>

        {/* Drawer Scrollable Body */}
        <div className="drawer-body">
          {/* Section 1: What was Observed vs Expected */}
          <div className="drawer-section">
            <h4 className="drawer-section-title">1. Observed Discrepancy vs Expected State</h4>
            <div className="comparison-grid">
              <div className="comparison-box observed">
                <div className="comp-tag">WHAT WAS OBSERVED</div>
                <div className="comp-text">{finding.observed}</div>
              </div>
              <div className="comparison-box expected">
                <div className="comp-tag">EXPECTED COMPLIANT STATE</div>
                <div className="comp-text">{finding.expected}</div>
              </div>
            </div>
          </div>

          {/* Section 2: The Three Different Truths */}
          <div className="drawer-section">
            <div className="section-header-flex">
              <h4 className="drawer-section-title">2. Epistemological Breakdown: The Three Different Truths</h4>
              <span className="epistemic-motto">“Never turn an estimate into an observed business result”</span>
            </div>
            
            <div className="three-truths-drawer-grid">
              <div className="truth-drawer-card observed">
                <div className="truth-badge-pill">[OBSERVED TRUTH]</div>
                <div className="truth-title">Directly Measurable</div>
                <p className="truth-desc">
                  {finding.threeTruths?.observed || finding.observed}
                </p>
                <span className="truth-source">Source: Live Storefront DOM / HTTP Response / GSC API</span>
              </div>

              <div className="truth-drawer-card calculated">
                <div className="truth-badge-pill">[CALCULATED TRUTH]</div>
                <div className="truth-title">Deterministic Math</div>
                <p className="truth-desc">
                  {finding.threeTruths?.calculated || finding.financialDetail || 'Deterministic mathematical consequence.'}
                </p>
                <span className="truth-source">Source: Algorithmic Delta & Boundary Math</span>
              </div>

              <div className="truth-drawer-card access">
                <div className="truth-badge-pill">[REQUIRES CLIENT ACCESS]</div>
                <div className="truth-title">Telemetry Dependent</div>
                <p className="truth-desc">
                  {finding.threeTruths?.requiresAccess || 'Requires client ad spend, conversion or analytics telemetry.'}
                </p>
                <span className="truth-source">Source: Client Analytics & Merchant Center Permissions</span>
              </div>
            </div>
          </div>

          {/* Section 3: Exact Code & DOM Evidence */}
          <div className="drawer-section">
            <div className="section-header-flex">
              <h4 className="drawer-section-title">3. Exact Code & DOM Evidence</h4>
              <a href={liveTargetUrl} target="_blank" rel="noopener noreferrer" className="link-inspect-live">
                Inspect Live DOM at Source ↗
              </a>
            </div>

            <div className="evidence-code-block">
              {finding.exactEvidence?.domSnippet && (
                <div className="code-sub-block">
                  <div className="code-label">Storefront DOM Markup:</div>
                  <pre><code>{finding.exactEvidence.domSnippet}</code></pre>
                </div>
              )}
              {finding.exactEvidence?.schemaSnippet && (
                <div className="code-sub-block mt-2">
                  <div className="code-label">JSON-LD Structured Data:</div>
                  <pre><code>{finding.exactEvidence.schemaSnippet}</code></pre>
                </div>
              )}
              {finding.exactEvidence?.pixelMeasurement && (
                <div className="code-sub-block mt-2">
                  <div className="code-label">SERP Pixel Measurement:</div>
                  <code>{finding.exactEvidence.pixelMeasurement}</code>
                </div>
              )}
              {finding.exactEvidence?.httpStatus && (
                <div className="code-sub-block mt-2">
                  <div className="code-label">HTTP Server Response:</div>
                  <code>{finding.exactEvidence.httpStatus}</code>
                </div>
              )}
            </div>

            {/* GSC Search Telemetry Evidence */}
            {finding.gscEvidence && (
              <div className="gsc-telemetry-box mt-3">
                <div className="gsc-header">
                  <span className="gsc-icon">📊</span>
                  <strong>Google Search Console & Merchant Center Telemetry:</strong>
                </div>
                <ul className="gsc-metrics-list">
                  {finding.gscEvidence.richAppearanceImpressions !== undefined && (
                    <li>Rich Search Appearance Impressions: <strong>{finding.gscEvidence.richAppearanceImpressions}</strong></li>
                  )}
                  {finding.gscEvidence.queryImpressions !== undefined && (
                    <li>Organic Query Impressions: <strong>{finding.gscEvidence.queryImpressions.toLocaleString()}</strong></li>
                  )}
                  {finding.gscEvidence.issue && (
                    <li className="text-warning">GSC Coverage Diagnostic: <strong>{finding.gscEvidence.issue}</strong></li>
                  )}
                  {finding.gscEvidence.mismatchDelta && (
                    <li className="text-danger">Disparity Magnitude: <strong>{finding.gscEvidence.mismatchDelta}</strong></li>
                  )}
                </ul>
              </div>
            )}
          </div>

          {/* Section 4: Business Impact & Strict Financial Provenance */}
          <div className="drawer-section">
            <h4 className="drawer-section-title">4. Commercial Consequence & Provenance Tier</h4>
            <div className="impact-box">
              <p className="impact-text">{finding.businessImpact}</p>
              <div className="provenance-detail-line">
                <span className="prov-pill">{finding.provenanceTier}</span>
                <span className="prov-text">{finding.financialDetail}</span>
              </div>
            </div>
          </div>

          {/* Section 5: Why SANOCEA Prioritizes This First & CII Breakdown */}
          <div className="drawer-section">
            <div className="section-header-flex">
              <h4 className="drawer-section-title">5. Commercial Impact Index (CII) Mathematical Breakdown</h4>
              <span className="cii-badge-score">Score: {finding.priorityScore}</span>
            </div>

            <div className="why-prioritized-box">
              <span className="why-icon">💡</span>
              <p>{finding.whyPrioritized}</p>
            </div>

            {finding.ciiBreakdown && (
              <div className="cii-breakdown-card mt-3">
                <div className="cii-formula-title">Mathematical Formula:</div>
                <code className="cii-formula-snippet">{finding.ciiBreakdown.formula}</code>
                
                <div className="cii-variables-grid mt-2">
                  <div className="cii-var-box">
                    <span className="var-label">{finding.ciiBreakdown.wChannel.label}</span>
                    <span className="var-val">{finding.ciiBreakdown.wChannel.value}</span>
                    <span className="var-reason">{finding.ciiBreakdown.wChannel.reason}</span>
                  </div>
                  <div className="cii-var-box">
                    <span className="var-label">{finding.ciiBreakdown.wRisk.label}</span>
                    <span className="var-val">{finding.ciiBreakdown.wRisk.value}</span>
                    <span className="var-reason">{finding.ciiBreakdown.wRisk.reason}</span>
                  </div>
                  <div className="cii-var-box">
                    <span className="var-label">{finding.ciiBreakdown.wIntent.label}</span>
                    <span className="var-val">{finding.ciiBreakdown.wIntent.value}</span>
                    <span className="var-reason">{finding.ciiBreakdown.wIntent.reason}</span>
                  </div>
                  <div className="cii-var-box">
                    <span className="var-label">{finding.ciiBreakdown.wConfidence.label}</span>
                    <span className="var-val">{finding.ciiBreakdown.wConfidence.value}</span>
                    <span className="var-reason">{finding.ciiBreakdown.wConfidence.reason}</span>
                  </div>
                  <div className="cii-var-box">
                    <span className="var-label">{finding.ciiBreakdown.fAccess.label}</span>
                    <span className="var-val">{finding.ciiBreakdown.fAccess.value}</span>
                    <span className="var-reason">{finding.ciiBreakdown.fAccess.reason}</span>
                  </div>
                </div>

                {finding.ciiBreakdown.challengeDefense && (
                  <div className="cii-defense-note mt-2">
                    <strong>CTO Challenge Defense:</strong> {finding.ciiBreakdown.challengeDefense}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Section 6: Automation Claim & Execution Dossier */}
          <div className="drawer-section">
            <div className="section-header-flex">
              <h4 className="drawer-section-title">6. Automation Feasibility & Execution Route</h4>
              <span className="access-tier-tag">Access Required: {finding.automationSuitability?.accessTier || finding.minimumAccessRequired}</span>
            </div>

            {finding.automationSuitability && (
              <div className="automation-dossier-card mb-3">
                <div className="auto-dossier-grid">
                  <div className="auto-item">
                    <span className="auto-label">Can SANOCEA Execute?</span>
                    <strong className="text-success">✓ Yes — Staged Recipe Ready</strong>
                  </div>
                  <div className="auto-item">
                    <span className="auto-label">Execution Mechanism:</span>
                    <code>{finding.automationSuitability.executionMechanism}</code>
                  </div>
                  <div className="auto-item">
                    <span className="auto-label">Minimum Access Tier:</span>
                    <span className="access-tier-chip">{finding.automationSuitability.accessTier}</span>
                  </div>
                  <div className="auto-item">
                    <span className="auto-label">Human Sign-off:</span>
                    <span>{finding.automationSuitability.approvalRequired ? '👤 Required (WhatsApp or UI)' : '⚡ Pre-Approved Safe'}</span>
                  </div>
                </div>

                {finding.automationSuitability.preparedPayload && (
                  <div className="staged-payload-box mt-2">
                    <div className="payload-label">Prepared Autonomous Payload:</div>
                    <pre><code>{finding.automationSuitability.preparedPayload}</code></pre>
                  </div>
                )}

                <div className="verification-method-box mt-2">
                  <strong>Verification Method:</strong> {finding.automationSuitability.verificationMethod}
                </div>
              </div>
            )}

            <div className="execution-path-steps-8">
              {lifecycleSteps.map((step) => (
                <div key={step.key} className="path-step-8">
                  <div className="path-step-num-8">{step.label}</div>
                  <div className="path-step-desc-8">{step.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Drawer Actions Footer */}
        <div className="drawer-footer">
          <div className="footer-left">
            <button
              type="button"
              className="btn-drawer-whatsapp"
              onClick={() => onSwitchToWhatsApp && onSwitchToWhatsApp(finding.affectedSku || finding.id)}
            >
              💬 Review in WhatsApp
            </button>
            <a href={liveTargetUrl} target="_blank" rel="noopener noreferrer" className="btn-drawer-evidence-link">
              Inspect Live Source ↗
            </a>
          </div>

          <div className="footer-right">
            {isApproved ? (
              <button type="button" className="btn-drawer-approved" disabled>
                ✓ Remediation Dispatched
              </button>
            ) : (
              <button
                type="button"
                className="btn-drawer-approve"
                onClick={() => onApprove && onApprove(finding)}
              >
                <span>⚡ Approve & Fix</span>
              </button>
            )}
            <button type="button" className="btn-drawer-close" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
