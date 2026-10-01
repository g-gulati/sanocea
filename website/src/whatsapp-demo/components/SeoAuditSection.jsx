import React, {useState, useMemo, useEffect} from 'react'
import {getSeoAuditData, getHostileQuestionsForTenant} from '../data/seoAuditData.js'
import FindingDetailDrawer from './FindingDetailDrawer.jsx'
import SearchAppearanceProgressionCard from './SearchAppearanceProgressionCard.jsx'
import SanoceaCaseStudyView from './SanoceaCaseStudyView.jsx'

export default function SeoAuditSection({companyData, onBackToDashboard, onSwitchToWhatsApp, onResolveAction}) {
  const auditData = useMemo(() => {
    return getSeoAuditData(companyData?.companyId || 'premium-basket')
  }, [companyData?.companyId])

  const hostileQuestions = useMemo(() => {
    return getHostileQuestionsForTenant(companyData?.companyId || auditData?.companyId)
  }, [companyData?.companyId, auditData?.companyId])

  // Filter state for "All Findings" section
  const [tierFilter, setTierFilter] = useState('ALL')
  const [evidenceFilter, setEvidenceFilter] = useState('ALL')
  const [categoryFilter, setCategoryFilter] = useState('ALL')
  const [channelFilter, setChannelFilter] = useState('ALL')
  const [activeFunnelFilter, setActiveFunnelFilter] = useState('ALL') // 'ALL' | 'VALIDATED' | 'CONSEQUENTIAL'
  const [showMethodologyModal, setShowMethodologyModal] = useState(false)
  const [showHostileModal, setShowHostileModal] = useState(false)
  const [approvedActionIds, setApprovedActionIds] = useState(new Set())

  // Inspect Drawer State
  const [selectedFinding, setSelectedFinding] = useState(null)
  const [isDrawerOpen, setIsDrawerOpen] = useState(false)

  // Sub-view toggle (Prospect Audit vs Flagship SANOCEA Case Study)
  const isSanocea = companyData?.companyId === 'sanocea'
  const [activeViewMode, setActiveViewMode] = useState(() => {
    return isSanocea ? 'SANOCEA_CASE_STUDY' : 'PROSPECT_AUDIT'
  })

  // Reset state on tenant switch
  useEffect(() => {
    setActiveViewMode(companyData?.companyId === 'sanocea' ? 'SANOCEA_CASE_STUDY' : 'PROSPECT_AUDIT')
    setSelectedFinding(null)
    setIsDrawerOpen(false)
    setActiveFunnelFilter('ALL')
    setTierFilter('ALL')
    setEvidenceFilter('ALL')
    setCategoryFilter('ALL')
    setChannelFilter('ALL')
    setShowHostileModal(false)
    setShowMethodologyModal(false)
    setApprovedActionIds(new Set())
  }, [companyData?.companyId])

  // Handle one-click action approval
  const handleApproveAction = (priorityItem) => {
    setApprovedActionIds((prev) => new Set([...prev, priorityItem.id]))
    if (onResolveAction) {
      onResolveAction(priorityItem.id)
    }
  }

  const handleOpenInspect = (item) => {
    setSelectedFinding(item)
    setIsDrawerOpen(true)
  }

  // Handle clicking on Funnel steps to inspect traceable populations
  const handleFunnelStepClick = (stepNumber) => {
    if (stepNumber === 1) {
      setActiveFunnelFilter('ALL')
      setTierFilter('ALL')
      setEvidenceFilter('ALL')
      const el = document.getElementById('seo-all-findings')
      if (el) el.scrollIntoView({behavior: 'smooth'})
    } else if (stepNumber === 2) {
      setActiveFunnelFilter('VALIDATED')
      setEvidenceFilter('ALL')
      const el = document.getElementById('seo-all-findings')
      if (el) el.scrollIntoView({behavior: 'smooth'})
    } else if (stepNumber === 3) {
      setActiveFunnelFilter('CONSEQUENTIAL')
      setTierFilter('ALL')
      const el = document.getElementById('seo-all-findings')
      if (el) el.scrollIntoView({behavior: 'smooth'})
    } else if (stepNumber === 4 || stepNumber === 5) {
      const el = document.getElementById('seo-priority-queue')
      if (el) el.scrollIntoView({behavior: 'smooth'})
    }
  }

  // Filter long-tail findings
  const filteredAllFindings = useMemo(() => {
    return (auditData.allFindings || []).filter((f) => {
      const matchTier = tierFilter === 'ALL' || f.tier === tierFilter
      const matchEvidence =
        evidenceFilter === 'ALL' ||
        f.evidenceStatus === evidenceFilter ||
        (evidenceFilter === 'NOT_VERIFIABLE' && f.isQuarantined) ||
        (f.evidenceClass && f.evidenceClass.includes(evidenceFilter)) ||
        (f.provenance && f.provenance.includes(evidenceFilter))
      const matchCategory = categoryFilter === 'ALL' || f.category === categoryFilter
      const matchChannel = channelFilter === 'ALL' || f.channel === channelFilter

      // Traceable funnel filters
      let matchFunnel = true
      if (activeFunnelFilter === 'VALIDATED') {
        // Exclude unverified or quarantined transient issues
        matchFunnel = !f.isQuarantined
      } else if (activeFunnelFilter === 'CONSEQUENTIAL') {
        // Exclude quarantined and cosmetic P3 items
        matchFunnel = !f.isQuarantined && f.tier !== 'P3'
      }

      return matchTier && matchEvidence && matchCategory && matchChannel && matchFunnel
    })
  }, [auditData.allFindings, tierFilter, evidenceFilter, categoryFilter, channelFilter, activeFunnelFilter])

  const totalFindings = auditData?.totalFindingsCount || auditData?.findingCount || (auditData?.allFindings?.length || 0)
  const displayCount = `${totalFindings} findings detected`

  const funnel = auditData?.funnel || {
    totalDiscovered: totalFindings,
    validatedIssues: auditData?.validatedCount || totalFindings,
    commerciallyConsequential: auditData?.consequentialCount || totalFindings,
    actionableCount: auditData?.priorityActions || (auditData?.priorityQueue?.length || 2),
    steps: [
      { stepNumber: 1, name: '1. Discovery Volume', metric: `${totalFindings} Detected`, badge: 'Raw Discovery Population', subtext: 'Full crawl graph discovered', color: 'blue' },
      { stepNumber: 2, name: '2. Validation Filter', metric: `${auditData?.validatedCount || totalFindings} Validated`, badge: 'De-duplicated & Verified', subtext: 'Verified issues', color: 'cyan' },
      { stepNumber: 3, name: '3. Commercial Consequence', metric: `${auditData?.consequentialCount || totalFindings} Consequential`, badge: 'Revenue Velocity', subtext: 'Commercially actionable', color: 'purple' },
      { stepNumber: 4, name: '4. Algorithmic Ranking', metric: `Top ${auditData?.priorityCount || 2} Priority`, badge: 'CII Score', subtext: 'Prioritized queue', color: 'amber' },
      { stepNumber: 5, name: '5. Executive Actions', metric: `Top ${auditData?.priorityActions || 2} Actions`, badge: 'Action Queue', subtext: 'Immediate remediation actions', color: 'green' }
    ],
    whatsappSummary: {
      immediateAttention: auditData?.priorityActions || 2,
      requiresApproval: 1,
      feedFixable: 0,
      apiRequired: 1,
      backlogDeprioritized: 0
    }
  }

  const severityBreakdown = auditData?.severityBreakdown || { CRITICAL: 2, HIGH: 2, MEDIUM: 2, LOW: 1, INFORMATIONAL: 0 }
  const categoryBreakdown = auditData?.categoryBreakdown || { 'Technical SEO': 2, 'Indexability': 2 }
  const priorityQueue = auditData?.priorityQueue || []

  return (
    <section className="seo-audit-intelligence-section" aria-labelledby="seo-audit-heading">
      {/* ── Top Utility Header Bar ────────────────────────────────────────── */}
      <div className="seo-top-utility-bar">
        {onBackToDashboard && (
          <button
            type="button"
            className="btn-back-to-ops"
            onClick={onBackToDashboard}
            title="Return to the Operations Dashboard"
          >
            ← Back to Operations Dashboard
          </button>
        )}

        <div className="seo-view-mode-selector-inline">
          {isSanocea ? (
            <span className="seo-workspace-status-badge sanocea-badge" style={{
              background: '#0F172A',
              color: '#38BDF8',
              fontWeight: 800,
              fontSize: '12px',
              padding: '6px 14px',
              borderRadius: '6px',
              border: '1px solid #1E293B',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              <span>🔬 SANOCEA Autonomous 24/7 SEO Monitoring & Longitudinal Experiment</span>
            </span>
          ) : (
            <span className="seo-workspace-status-badge prospect-badge" style={{
              background: '#F1F5F9',
              color: '#0F172A',
              fontWeight: 800,
              fontSize: '12px',
              padding: '6px 14px',
              borderRadius: '6px',
              border: '1px solid #CBD5E1',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              <span>🎯 Prospect Commercial Audit — {companyData?.companyName || auditData?.displayName || auditData?.domain}</span>
            </span>
          )}
        </div>

        <div className="seo-active-prospect-tag">
          {isSanocea ? (
            <>Target Domain: <strong>www.sanocea.com (Daemon Active)</strong></>
          ) : (
            <>Target Domain: <strong>{auditData?.domain}</strong></>
          )}
        </div>
      </div>

      {activeViewMode === 'SANOCEA_CASE_STUDY' ? (
        <SanoceaCaseStudyView />
      ) : (
        <>
          {/* ── Prominent Commercial Positioning Banner ─────────────────────────── */}
          <div className="commercial-core-promise-banner">
            <div className="promise-top-line">
              <span className="promise-badge">SANOCEA VALUE PROPOSITION</span>
              <div className="promise-meta-row">
                <span>Target: <strong>{auditData?.domain || 'sanocea.com'}</strong></span>
                <span>•</span>
                <span>Engine: <strong>{auditData?.engineVersion || 'v2.4-enterprise'}</strong></span>
                <span>•</span>
                <button 
                  type="button" 
                  className="btn-hostile-trigger"
                  onClick={() => setShowHostileModal(true)}
                >
                  ⚡ CTO Audit Verification (10 Hard Questions)
                </button>
              </div>
            </div>
            <div className="promise-title">
              “SANOCEA doesn't sell you a list of SEO errors. It identifies the operational issues worth acting on, prepares the intervention, and verifies the result.”
            </div>
          </div>

          {/* ── First Screen Executive Triad: Three Core Answers Immediately ────── */}
          <div className="executive-triad-grid">
            {/* Card 1: What did you find? */}
            <div className="triad-card discovery" onClick={() => handleFunnelStepClick(1)}>
              <span className="triad-question">Question 1: What did you find?</span>
              <div className="triad-metric">{totalFindings} Findings</div>
              <div className="triad-subtext">
                Raw discovery population across {auditData?.pagesAuditedCount || '75+'} PDPs, PLP categories, sitemaps, and root crawl graph.
              </div>
              <span className="triad-action-hint">Click to inspect raw crawl population ➔</span>
            </div>

            {/* Card 2: How many actually matter? */}
            <div className="triad-card consequential" onClick={() => handleFunnelStepClick(3)}>
              <span className="triad-question">Question 2: How many actually matter?</span>
              <div className="triad-metric text-purple">{funnel.commerciallyConsequential} Consequential</div>
              <div className="triad-subtext">
                {totalFindings - funnel.commerciallyConsequential} utility pages, checkout routes, login screens, duplicate parameters & cosmetic noise quarantined.
              </div>
              <span className="triad-action-hint">Click to inspect commercial subset ➔</span>
            </div>

            {/* Card 3: What should we do first? */}
            <div className="triad-card action" onClick={() => handleFunnelStepClick(5)}>
              <span className="triad-question">Question 3: What should we do first?</span>
              <div className="triad-metric text-green">Top {funnel.actionableCount} Actions</div>
              <div className="triad-subtext">
                Ranked by GMC suspension risk, live ad spend velocity, and automated remediability.
              </div>
              <span className="triad-action-hint">Click to jump to action queue ➔</span>
            </div>
          </div>

          {/* ── Section Title & Executive Story ─────────────────────────────────── */}
          <div className="seo-audit-hero-card">
            <div className="seo-hero-badge-row">
              <span className="seo-pulse-dot" />
              <span className="seo-hero-kicker">SANOCEA COMMERCIAL PRIORITIZATION ENGINE</span>
              <span className="seo-engine-tag">Target: {auditData?.domain || 'sanocea.com'}</span>
              <span className="seo-engine-tag">Audited: {auditData?.auditedDate || 'March 2026'}</span>
            </div>

            <h3 id="seo-audit-heading" className="seo-hero-title">
              {displayCount}
            </h3>
            <p className="seo-hero-narrative">
              <strong>We found {totalFindings} findings across your site. We don’t ask you to fix {totalFindings} things.</strong><br />
              SANOCEA identifies what matters commercially and tells you what to fix first.
            </p>

            {/* ── 1. Transition Funnel: Traceable Dynamic 5-Step Pipeline ─────────── */}
            <div className="seo-funnel-card">
              <div className="funnel-header-line">
                <span className="funnel-badge">TRACEABLE FUNNEL (CLICK ANY STEP TO FILTER POPULATION)</span>
                <span className="funnel-motto">
                  “We don’t just find problems. We filter out the noise and tell you what to fix first.”
                </span>
              </div>

              <div className="seo-5-step-funnel">
                {funnel.steps.map((step, idx) => (
                  <React.Fragment key={step.stepNumber}>
                    <div 
                      className={`funnel-step-card ${step.color} clickable-step`}
                      onClick={() => handleFunnelStepClick(step.stepNumber)}
                      title={`Click to inspect the ${step.metric} population`}
                    >
                      <div className="step-badge">{step.badge}</div>
                      <div className="step-metric">{step.metric}</div>
                      <div className="step-name">{step.name}</div>
                      <div className="step-subtext">{step.subtext}</div>
                      <div className="step-inspect-hint">🔍 Inspect Population</div>
                    </div>
                    {idx < funnel.steps.length - 1 && (
                      <div className="funnel-step-arrow">➔</div>
                    )}
                  </React.Fragment>
                ))}
              </div>

              {/* WhatsApp Bridge Banner */}
              <div className="whatsapp-bridge-box">
                <div className="wa-bridge-left">
                  <span className="wa-icon-bubble">💬</span>
                  <div>
                    <strong>Connected WhatsApp Operations Layer Ready:</strong>
                    <p>
                      Found {totalFindings} issues · <strong>{funnel.whatsappSummary.immediateAttention} require immediate attention</strong> · {funnel.whatsappSummary.requiresApproval} require approval · {funnel.whatsappSummary.feedFixable} via GMC feed · {funnel.whatsappSummary.apiRequired} via API · {funnel.whatsappSummary.backlogDeprioritized} quarantined
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-open-wa-dispatch"
                  onClick={() => onSwitchToWhatsApp && onSwitchToWhatsApp('seo')}
                  title="Open the interactive WhatsApp operations flow"
                >
                  <span>⚡ Review via WhatsApp</span>
                </button>
              </div>
            </div>

            {/* ── 2. Full Discovery Breakdown (Severity & Categories) ─────────────── */}
            <div className="seo-discovery-breakdown-grid">
              {/* Severity Breakdown */}
              <div className="discovery-column">
                <div className="discovery-column-title">Discovered Severity Spectrum (Raw Population)</div>
                <div className="discovery-pills-row">
                  <span className="disc-pill critical">
                    <strong>{severityBreakdown.CRITICAL}</strong> Critical
                  </span>
                  <span className="disc-pill high">
                    <strong>{severityBreakdown.HIGH}</strong> High
                  </span>
                  <span className="disc-pill medium">
                    <strong>{severityBreakdown.MEDIUM}</strong> Medium
                  </span>
                  <span className="disc-pill low">
                    <strong>{severityBreakdown.LOW}</strong> Low
                  </span>
                  <span className="disc-pill info">
                    <strong>{severityBreakdown.INFORMATIONAL}</strong> Informational
                  </span>
                </div>
              </div>

              {/* Category Breakdown */}
              <div className="discovery-column">
                <div className="discovery-column-title">Analyzed Technical & Commerce Domains</div>
                <div className="discovery-categories-row">
                  {Object.entries(categoryBreakdown).map(([cat, count]) => (
                    <span key={cat} className="category-count-chip">
                      <span className="cat-name">{cat}</span>
                      <span className="cat-num">{count}</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* ── 2B. The Three Different Truths ───────────────────────────────────── */}
          {auditData.threeTruths && (
            <div className="three-truths-master-card">
              <div className="truths-header-row">
                <div className="truths-header-left">
                  <span className="truths-kicker">EPISTEMOLOGICAL DISCIPLINE</span>
                  <h3 className="truths-main-title">The Three Different Truths</h3>
                </div>
                <div className="truths-motto-badge">
                  “{auditData.threeTruths.governanceMotto}”
                </div>
              </div>

              <div className="three-truths-columns-grid">
                {/* Column 1: Observed */}
                <div className="truth-column observed">
                  <div className="truth-col-header">
                    <span className="truth-pill observed">{auditData.threeTruths.observed.badge}</span>
                    <h4>{auditData.threeTruths.observed.title}</h4>
                  </div>
                  <p className="truth-col-desc">{auditData.threeTruths.observed.description}</p>
                  <div className="truth-examples-list">
                    <div className="truth-list-heading">Observed Live Facts:</div>
                    <ul>
                      {auditData.threeTruths.observed.evidenceItems.map((item, i) => (
                        <li key={i}>✓ {item}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Column 2: Calculated */}
                <div className="truth-column calculated">
                  <div className="truth-col-header">
                    <span className="truth-pill calculated">{auditData.threeTruths.calculated.badge}</span>
                    <h4>{auditData.threeTruths.calculated.title}</h4>
                  </div>
                  <p className="truth-col-desc">{auditData.threeTruths.calculated.description}</p>
                  <div className="truth-examples-list">
                    <div className="truth-list-heading">Deterministic Calculations:</div>
                    <ul>
                      {auditData.threeTruths.calculated.evidenceItems.map((item, i) => (
                        <li key={i}>📐 {item}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Column 3: Requires Access */}
                <div className="truth-column access">
                  <div className="truth-col-header">
                    <span className="truth-pill access">{auditData.threeTruths.requiresAccess.badge}</span>
                    <h4>{auditData.threeTruths.requiresAccess.title}</h4>
                  </div>
                  <p className="truth-col-desc">{auditData.threeTruths.requiresAccess.description}</p>
                  <div className="truth-examples-list">
                    <div className="truth-list-heading">Requires Client Telemetry:</div>
                    <ul>
                      {auditData.threeTruths.requiresAccess.evidenceItems.map((item, i) => (
                        <li key={i}>🔐 {item}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── 2C. Operational Decision Layer Lifecycle ────────────────────────── */}
          {auditData.operationalNarrative && (
            <div className="operational-decision-card">
              <div className="op-card-header">
                <span className="op-kicker">DECISION ENGINE ARCHITECTURE</span>
                <h3 className="op-title">Operational Decision Layer (Detect ➔ Verify)</h3>
                <p className="op-motto">“{auditData.operationalNarrative.motto}”</p>
              </div>

              <div className="op-stages-grid">
                {auditData.operationalNarrative.stages.map((stg, i) => (
                  <div key={stg.name} className="op-stage-node">
                    <div className="op-stage-badge">{stg.label}</div>
                    <div className="op-stage-desc">{stg.desc}</div>
                    {i < auditData.operationalNarrative.stages.length - 1 && (
                      <span className="op-stage-arrow">➔</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── 3. Search Appearance: The 3-State Truth Component ───────────────── */}
          <SearchAppearanceProgressionCard progressionData={auditData.searchAppearanceProgression} />

          {/* ── 4. Prominent Section: What SANOCEA Recommends Fixing First ──────── */}
          <div className="seo-priority-section" id="seo-priority-queue">
            <div className="priority-section-header">
              <div>
                <div className="priority-title-row">
                  <span className="priority-icon-sparkle">🎯</span>
                  <h3 className="priority-title">What SANOCEA Recommends Fixing First</h3>
                  <span className="priority-badge-count">{priorityQueue.length} High-Impact Decisions</span>
                </div>
                <p className="priority-subtitle">
                  We found {totalFindings} things across the site. These are the {priorityQueue.length} issues we address first, ranked by commercial consequence, Google Merchant Center feed standing, and execution feasibility. Click any card to inspect the full technical dossier.
                </p>
              </div>

              <button
                type="button"
                className="btn-methodology-toggle"
                onClick={() => setShowMethodologyModal(true)}
                title="Explain how the Commercial Impact Index calculates priority scores"
              >
                <span>ℹ️ Prioritization Methodology (CII)</span>
              </button>
            </div>

            {/* Priority Cards List */}
            <div className="priority-cards-stack">
              {priorityQueue.map((item) => {
                const isApproved = approvedActionIds.has(item.id)
                const liveUrl = item.liveEvidenceUrl || item.exactEvidence?.sourceUrl || item.url
                return (
                  <div 
                    key={item.id} 
                    className={`priority-card ${item.badgeClass} ${isApproved ? 'approved' : ''}`}
                    onClick={() => handleOpenInspect(item)}
                    style={{cursor: 'pointer'}}
                  >
                    {/* Header Row */}
                    <div className="pcard-header">
                      <div className="pcard-left-tags">
                        <span className={`ptier-badge ${item.badgeClass}`}>{item.priorityTier}</span>
                        <span className="pscore-badge">CII Score: {item.priorityScore}</span>
                        {item.evidenceStatus && (
                          <span className={`pevid-status-badge ${item.evidenceStatus.toLowerCase()}`}>
                            {item.evidenceStatus === 'REPRODUCED' ? '✓ REPRODUCED' : item.evidenceStatus === 'PARTIAL' ? '⚠ PARTIAL' : item.evidenceStatus}
                          </span>
                        )}
                        <span className="pcat-badge">{item.category}</span>
                        <span className="pevid-badge">{item.provenanceTier}</span>
                      </div>

                      <div className="pcard-approval-status">
                        {isApproved ? (
                          <span className="approved-pill">✅ Approved & Synchronized</span>
                        ) : (
                          <span className="requires-signoff">
                            {item.humanApprovalRequired ? '👤 Human Approval Required' : '⚡ Safe Auto-Remediation'}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Finding Title & Direct Evidence Link */}
                    <div className="pcard-title-row">
                      <h4 className="pcard-title">{item.findingTitle}</h4>
                      <div className="pcard-title-actions" onClick={(e) => e.stopPropagation()}>
                        <a 
                          href={liveUrl} 
                          target="_blank" 
                          rel="noopener noreferrer" 
                          className="btn-direct-card-link"
                          title="Open live URL directly in browser"
                        >
                          🌐 Open Live URL ↗
                        </a>
                        <span className="pcard-inspect-hint" onClick={() => handleOpenInspect(item)}>
                          🔍 Inspect Dossier
                        </span>
                      </div>
                    </div>

                    {/* Meta row: SKU, Channel, Access Tier, Execution Method */}
                    <div className="pcard-meta-line">
                      <span><strong>Channel:</strong> {item.affectedChannel}</span>
                      <span><strong>SKU / Ref:</strong> <code>{item.affectedSku || 'N/A'}</code></span>
                      <span><strong>Access Tier:</strong> <code className="access-tier-chip">{item.automationSuitability?.accessTier || item.minimumAccessRequired}</code></span>
                      <span><strong>Execution:</strong> <code>{item.automationSuitability?.executionMechanism || item.executionClassLabel}</code></span>
                      <span><strong>Status:</strong> <code className="status-code">{item.remediationStatus || 'ACTION_REQUIRED'}</code></span>
                    </div>

                    {/* Conflict / Comparison Grid */}
                    <div className="pcard-conflict-grid">
                      <div className="conflict-box">
                        <span className="conflict-label">OBSERVED:</span>
                        <span className="conflict-value">{item.observed}</span>
                      </div>
                      <div className="conflict-box">
                        <span className="conflict-label">EXPECTED:</span>
                        <span className="conflict-value">{item.expected}</span>
                      </div>
                    </div>

                    {/* Business Impact & Provenance */}
                    <div className="pcard-body-grid">
                      <div className="pcard-info-tile consequence">
                        <div className="tile-label">Business Consequence:</div>
                        <div className="tile-text">{item.businessImpact}</div>
                        <div className="provenance-tag-line">
                          <span className="prov-tag">{item.provenanceTier}</span>
                          <span className="prov-text">{item.financialDetail}</span>
                        </div>
                      </div>

                      <div className="pcard-info-tile channel-sku">
                        <div className="tile-label">CII Mathematical Weight Breakdown:</div>
                        {item.ciiBreakdown ? (
                          <div className="cii-inline-vars">
                            <div><code>W_channel: {item.ciiBreakdown.wChannel.value}</code> · {item.ciiBreakdown.wChannel.reason}</div>
                            <div><code>W_risk: {item.ciiBreakdown.wRisk.value}</code> · {item.ciiBreakdown.wRisk.reason}</div>
                            <div><code>W_intent: {item.ciiBreakdown.wIntent.value}</code> · {item.ciiBreakdown.wIntent.reason}</div>
                            <div><code>W_confidence: {item.ciiBreakdown.wConfidence.value}</code> · {item.ciiBreakdown.wConfidence.reason}</div>
                            <div><code>F_access: {item.ciiBreakdown.fAccess.value}</code> · {item.ciiBreakdown.fAccess.reason}</div>
                          </div>
                        ) : (
                          <div className="truth-micro-item">
                            Deterministic formula: W_channel × W_risk × W_intent × W_confidence × F_access
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Why We're Prioritizing It */}
                    <div className="pcard-why-box">
                      <div className="why-header">
                        <span className="why-bulb">💡</span>
                        <strong>Why SANOCEA Prioritizes This First:</strong>
                      </div>
                      <p className="why-content">{item.whyPrioritized}</p>
                    </div>

                    {/* Recommended Action & Automation Route */}
                    <div className="pcard-action-bar" onClick={(e) => e.stopPropagation()}>
                      <div className="action-details-col">
                        <div>
                          <strong>Recommended Action:</strong> {item.recommendedAction || item.recommendedRemediation}
                        </div>
                        <div className="automation-route-line">
                          <span>⚡ Execution Class: <code>{item.executionClassLabel}</code></span>
                          <span className="access-pill">Required Access: {item.automationSuitability?.accessTier || item.minimumAccessRequired}</span>
                        </div>
                      </div>

                      <div className="action-buttons-col">
                        <button
                          type="button"
                          className="btn-inspect-dossier"
                          onClick={() => handleOpenInspect(item)}
                        >
                          🔍 Inspect Evidence
                        </button>
                        {isApproved ? (
                          <button type="button" className="btn-resolved-state" disabled>
                            ✓ Action Dispatched
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn-approve-priority"
                            onClick={() => handleApproveAction(item)}
                          >
                            <span>⚡ Approve & Fix</span>
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn-discuss-wa"
                          onClick={() => onSwitchToWhatsApp && onSwitchToWhatsApp(item.affectedSku || item.id)}
                          title="Inspect and approve this decision inside WhatsApp"
                        >
                          <span>💬 WhatsApp</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* ── 5. Visible Credibility & Algorithmic Guardrails Banner ─────────── */}
          <div className="seo-credibility-guardrail-banner">
            <div className="guardrail-col">
              <span className="guardrail-badge">DATA PROVENANCE TIERS</span>
              <p>
                Every finding carries strict provenance: <code>[OBSERVED]</code> (DOM/HTTP verified) ➔ <code>[CALCULATED]</code> (Exact price/index delta) ➔ <code>[ESTIMATED]</code> (Disclosed benchmark model) ➔ <code>[REQUIRES_ACCESS]</code> (Requires merchant telemetry).
              </p>
            </div>
            <div className="guardrail-col">
              <span className="guardrail-badge">SEARCH INTELLIGENCE BOUNDARY</span>
              <p>
                SANOCEA observes empirical Google Search Console and CrUX outcomes (impressions, clicks, average position, indexing, rich snippet status). We never claim to know Google's proprietary internal ranking algorithm or prove single-variable causation.
              </p>
            </div>
          </div>

          {/* ── 6. Keep Long-Tail Findings Available (All Findings with Filters) ── */}
          <div className="seo-all-findings-section" id="seo-all-findings">
            <div className="all-findings-header">
              <div>
                <h3 className="all-findings-title">
                  <span>All Discovered Findings ({totalFindings})</span>
                </h3>
                <p className="all-findings-subtitle">
                  Examine the full crawl graph without cluttering executive priorities. Filter by Priority Tier, Category, Evidence Status, or Channel.
                </p>
                {activeFunnelFilter !== 'ALL' && (
                  <div className="active-funnel-filter-badge">
                    <span>Active Funnel Filter: <strong>{activeFunnelFilter}</strong></span>
                    <button type="button" onClick={() => setActiveFunnelFilter('ALL')}>✕ Clear Funnel Filter</button>
                  </div>
                )}
              </div>
              <span className="showing-count-tag">
                Showing {filteredAllFindings.length} of {auditData.allFindings?.length || 0} sampled
              </span>
            </div>

            {/* Filter Controls Bar */}
            <div className="all-findings-filter-bar">
              <div className="filter-select-group">
                <label className="filter-group-label">Priority Tier:</label>
                <div className="filter-pill-btns">
                  {['ALL', 'P0', 'P1', 'P2', 'P3'].map((tier) => (
                    <button
                      key={tier}
                      type="button"
                      className={`btn-filter-pill ${tierFilter === tier ? 'active' : ''}`}
                      onClick={() => setTierFilter(tier)}
                    >
                      {tier}
                    </button>
                  ))}
                </div>
              </div>

              <div className="filter-select-group">
                <label className="filter-group-label">Evidence Status:</label>
                <select
                  className="filter-dropdown"
                  value={evidenceFilter}
                  onChange={(e) => setEvidenceFilter(e.target.value)}
                >
                  <option value="ALL">All Evidence States</option>
                  <option value="REPRODUCED">✓ Reproduced Live</option>
                  <option value="PARTIAL">⚠ Partially Confirmed</option>
                  <option value="SNAPSHOT">📸 Point-in-Time Snapshot</option>
                  <option value="NOT_VERIFIABLE">🚫 Quarantined / Unverified</option>
                </select>
              </div>

              <div className="filter-select-group">
                <label className="filter-group-label">Category:</label>
                <select
                  className="filter-dropdown"
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                >
                  <option value="ALL">All Categories</option>
                  <option value="Ecommerce">Ecommerce</option>
                  <option value="Catalogue">Catalogue</option>
                  <option value="Technical SEO">Technical SEO</option>
                  <option value="Structured Data">Structured Data</option>
                </select>
              </div>

              <div className="filter-select-group">
                <label className="filter-group-label">Channel:</label>
                <select
                  className="filter-dropdown"
                  value={channelFilter}
                  onChange={(e) => setChannelFilter(e.target.value)}
                >
                  <option value="ALL">All Channels</option>
                  <option value="Google Shopping">Google Shopping</option>
                  <option value="Direct Storefront">Direct Storefront</option>
                  <option value="Organic Search">Organic Search</option>
                  <option value="Amazon / D2C">Amazon / D2C</option>
                  <option value="Flipkart">Flipkart</option>
                </select>
              </div>
            </div>

            {/* Findings Table */}
            <div className="findings-table-wrap">
              <table className="seo-findings-table">
                <thead>
                  <tr>
                    <th>Tier</th>
                    <th>Evidence Status</th>
                    <th>Severity</th>
                    <th>Category</th>
                    <th>Channel</th>
                    <th>Detection Rule & Summary</th>
                    <th>URL</th>
                    <th>Provenance</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAllFindings.map((finding) => (
                    <tr 
                      key={finding.id} 
                      className={`${finding.tier.toLowerCase()} ${finding.isQuarantined ? 'quarantined-row' : ''}`}
                    >
                      <td>
                        <span className={`table-tier-badge ${finding.tier.toLowerCase()}`}>
                          {finding.tier}
                        </span>
                      </td>
                      <td>
                        {finding.isQuarantined ? (
                          <span className="table-quarantined-tag" title={finding.quarantineReason}>
                            🚫 QUARANTINED
                          </span>
                        ) : (
                          <span className={`table-evidence-tag ${finding.evidenceStatus?.toLowerCase()}`}>
                            {finding.evidenceStatus === 'REPRODUCED' ? '✓ REPRODUCED' : finding.evidenceStatus === 'PARTIAL' ? '⚠ PARTIAL' : finding.evidenceStatus}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`table-sev-badge ${finding.severity.toLowerCase()}`}>
                          {finding.severity}
                        </span>
                      </td>
                      <td>
                        <span className="table-cat-text">{finding.category}</span>
                      </td>
                      <td>
                        <span className="table-channel-text">{finding.channel}</span>
                      </td>
                      <td>
                        <div className="finding-table-rule">{finding.rule}</div>
                        <div className="finding-table-desc">{finding.summary}</div>
                        {finding.isQuarantined && finding.quarantineReason && (
                          <div className="finding-quarantine-note">
                            <em>Note: {finding.quarantineReason}</em>
                          </div>
                        )}
                      </td>
                      <td>
                        <a href={finding.url} target="_blank" rel="noopener noreferrer" className="table-url-link">
                          {finding.url.replace(/^https?:\/\/[^/]+/, '') || '/'}
                        </a>
                      </td>
                      <td>
                        <span className="table-prov-chip">{finding.provenance}</span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-table-inspect"
                          onClick={() => onSwitchToWhatsApp && onSwitchToWhatsApp(finding.rule)}
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ── Slide-out Evidentiary Inspection Drawer ─────────────────────────── */}
      <FindingDetailDrawer
        finding={selectedFinding}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        onApprove={handleApproveAction}
        isApproved={selectedFinding ? approvedActionIds.has(selectedFinding.id) : false}
        onSwitchToWhatsApp={onSwitchToWhatsApp}
      />

      {/* ── Hostile Audit Verification Modal (10 Hard Questions) ────────────── */}
      {showHostileModal && (
        <div className="modal-backdrop" onClick={() => setShowHostileModal(false)}>
          <div className="hostile-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-box">
                <span className="modal-icon">🛡️</span>
                <h3>Hostile Audit Verification: 10 Critical Questions</h3>
              </div>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setShowHostileModal(false)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body hostile-body">
              <p className="modal-lead">
                A skeptical CTO or VP of Ecommerce should challenge every assertion. Here is how SANOCEA defends every claim without hand-waving or black-box scores:
              </p>

              <div className="hostile-questions-list">
                {hostileQuestions.map((qa) => (
                  <div key={qa.qNumber} className="hostile-qa-item">
                    <div className="qa-q-row">
                      <span className="qa-num">Q{qa.qNumber}</span>
                      <strong className="qa-question">{qa.question}</strong>
                    </div>
                    <p className="qa-answer">{qa.answer}</p>
                    <div className="qa-pointers-row">
                      <span className="pointers-label">Proof / Pointers:</span>
                      {qa.evidencePointers.map((p, i) => (
                        <span key={i} className="qa-pointer-chip">✓ {p}</span>
                      ))}
                      {qa.evidenceUrl && (
                        <a 
                          href={qa.evidenceUrl} 
                          target="_blank" 
                          rel="noopener noreferrer" 
                          className="qa-live-link"
                        >
                          Inspect Live URL ↗
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn-modal-close"
                onClick={() => setShowHostileModal(false)}
              >
                Close Hostile Verification
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Methodology Modal (CII Formula) ─────────────────────────────────── */}
      {showMethodologyModal && (
        <div className="modal-backdrop" onClick={() => setShowMethodologyModal(false)}>
          <div className="methodology-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-box">
                <span className="modal-icon">📐</span>
                <h3>SANOCEA Commercial Impact Index (CII) Methodology</h3>
              </div>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setShowMethodologyModal(false)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <p className="modal-lead">
                Traditional SEO crawlers rank findings strictly by raw technical severity (CRITICAL &gt; HIGH &gt; MEDIUM &gt; LOW).
                In enterprise ecommerce, this creates severe credibility failures — screaming about an unindexed login screen while burying a Google Shopping feed suspension risk on an active revenue product.
              </p>

              <div className="formula-callout-box">
                <div className="formula-title">Mathematical Priority Formula:</div>
                <code className="formula-code">
                  Priority Score = W_channel × W_risk × W_intent × W_confidence × F_access
                </code>
              </div>

              <div className="methodology-dimensions-grid">
                <div className="dimension-item">
                  <strong>1. Channel Exposure Weight (W_channel)</strong>
                  <p>Active Google Shopping & P-Max Ads = 1.0; Direct Storefront = 0.9; Organic Search = 0.7; AI Crawlers = 0.4.</p>
                </div>
                <div className="dimension-item">
                  <strong>2. Commercial Risk Weight (W_risk)</strong>
                  <p>GMC Feed Suspension = 10.0; Buy Box Price Discrepancy = 9.0; Search Purge = 7.5; Conversion Friction = 6.0; Cosmetic Hygiene = 1.5.</p>
                </div>
                <div className="dimension-item">
                  <strong>3. Route Intent Weight (W_intent)</strong>
                  <p>Product Display Page (PDP) = 1.0; Category (PLP) = 0.85; Utility (Cart, Login, Account) = 0.05.</p>
                </div>
                <div className="dimension-item">
                  <strong>4. Provenance & Confidence Weight (W_confidence)</strong>
                  <p>[OBSERVED] Direct DOM match = 1.0; [CALCULATED] Exact price delta = 0.95; [REQUIRES_ACCESS] Telemetry dependent = 0.85; [ESTIMATED] = 0.6.</p>
                </div>
                <div className="dimension-item">
                  <strong>5. Execution Friction Factor (F_access)</strong>
                  <p>Feed Only = 1.05; Tag Manager = 1.0; Code Repo / Git PR = 0.95.</p>
                </div>
              </div>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn-modal-close"
                onClick={() => setShowMethodologyModal(false)}
              >
                Close Methodology
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
