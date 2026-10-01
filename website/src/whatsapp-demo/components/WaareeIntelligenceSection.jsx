import React, {useState, useMemo} from 'react'

export default function WaareeIntelligenceSection({companyData, onSwitchToWhatsApp}) {
  const [activePerspective, setActivePerspective] = useState('audit') // 'audit' | 'automation' | 'validation'
  const [evidenceFilter, setEvidenceFilter] = useState('all') // 'all' | '[O]' | '[I]' | '[V]'
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [selectedDiscrepancy, setSelectedDiscrepancy] = useState(null)

  const discrepancies = companyData.auditedDiscrepancies || []
  const automationMap = companyData.automationOpportunityMap || []
  const coverageMatrix = companyData.automationCoverageMatrix || []
  const validationRequirements = companyData.validationRequirements || []

  // Filtered discrepancies
  const filteredDiscrepancies = useMemo(() => {
    return discrepancies.filter((d) => {
      const matchEvidence = evidenceFilter === 'all' || d.class === evidenceFilter
      const matchCategory =
        categoryFilter === 'all' ||
        d.category.toLowerCase().includes(categoryFilter.toLowerCase())
      return matchEvidence && matchCategory
    })
  }, [discrepancies, evidenceFilter, categoryFilter])

  // Count summaries
  const observedCount = discrepancies.filter((d) => d.class === '[O]').length
  const inferredCount = discrepancies.filter((d) => d.class === '[I]').length
  const validationCount = discrepancies.filter((d) => d.class === '[V]').length

  return (
    <section className="waaree-intelligence-wrapper" aria-label="Waaree Operations Intelligence">
      {/* ── Operating Loop Narrative Banner (Requirement) ────────────────── */}
      <div className="waaree-loop-banner">
        <div className="loop-banner-header">
          <div className="loop-brand-tag">
            <span className="loop-dot">●</span>
            <span>SANOCEA OPERATING LOOP · WAAREE ENERGIES</span>
          </div>
          <h2 className="loop-title">How SANOCEA Operates Across Waaree's Multi-Channel Estate</h2>
          <p className="loop-subtitle">
            Watching the operational layer across shop.waaree.com, Amazon, Flipkart, L&T-SuFin, Moglix, and 5 complaint portals — detecting discrepancies, preparing actions, and closing the loop with human sign-off.
          </p>
        </div>

        <div className="loop-flow-diagram">
          <div className="loop-step-card">
            <div className="step-num">01</div>
            <div className="step-icon">📡</div>
            <div className="step-label">Continuous Watch</div>
            <div className="step-detail">Monitors feeds, stock, prices, datasheets, and tickets across 5 commerce channels.</div>
          </div>
          <div className="loop-arrow">➔</div>

          <div className="loop-step-card highlight">
            <div className="step-num">02</div>
            <div className="step-icon">🔍</div>
            <div className="step-label">Deterministic Detect</div>
            <div className="step-detail">Catches structured data leaks, -40% pack dilution, and conflicting cell specs.</div>
          </div>
          <div className="loop-arrow">➔</div>

          <div className="loop-step-card">
            <div className="step-num">03</div>
            <div className="step-icon">💡</div>
            <div className="step-label">Explain Impact</div>
            <div className="step-detail">Translates technical discrepancies into commercial risk: GMV at risk, cancellations, disputes.</div>
          </div>
          <div className="loop-arrow">➔</div>

          <div className="loop-step-card">
            <div className="step-num">04</div>
            <div className="step-icon">⚡</div>
            <div className="step-label">Prepare Action</div>
            <div className="step-detail">Generates ready-to-dispatch payloads: feed overrides, price floor locks, spec alignments.</div>
          </div>
          <div className="loop-arrow">➔</div>

          <div className="loop-step-card approval">
            <div className="step-num">05</div>
            <div className="step-icon">👤</div>
            <div className="step-label">Human Approves</div>
            <div className="step-detail">Operator approves with 1 click via WhatsApp or Command Center. No unverified actions.</div>
          </div>
          <div className="loop-arrow">➔</div>

          <div className="loop-step-card audit">
            <div className="step-num">06</div>
            <div className="step-icon">📜</div>
            <div className="step-label">Execute & Audit</div>
            <div className="step-detail">Connector executes update in simulation sandbox; logs immutable audit receipt with timestamp, operator ID, and action payload.</div>
          </div>
        </div>
      </div>

      {/* ── Perspective Selector Tabs (Three Distinct Pillars) ───────────── */}
      <div className="perspective-tabs-container">
        <div className="perspective-tabs" role="tablist">
          <button
            type="button"
            className={`perspective-tab-btn ${activePerspective === 'audit' ? 'active' : ''}`}
            onClick={() => setActivePerspective('audit')}
            role="tab"
            aria-selected={activePerspective === 'audit'}
          >
            <span className="tab-pill-icon">🔍</span>
            <span className="tab-pill-text">A · What SANOCEA Found</span>
            <span className="tab-pill-count">{discrepancies.length} Audited Findings</span>
          </button>

          <button
            type="button"
            className={`perspective-tab-btn ${activePerspective === 'automation' ? 'active' : ''}`}
            onClick={() => setActivePerspective('automation')}
            role="tab"
            aria-selected={activePerspective === 'automation'}
          >
            <span className="tab-pill-icon">⚡</span>
            <span className="tab-pill-text">B · What SANOCEA Can Automate</span>
            <span className="tab-pill-count">10 Core Workflows</span>
          </button>

          <button
            type="button"
            className={`perspective-tab-btn ${activePerspective === 'validation' ? 'active' : ''}`}
            onClick={() => setActivePerspective('validation')}
            role="tab"
            aria-selected={activePerspective === 'validation'}
          >
            <span className="tab-pill-icon">📋</span>
            <span className="tab-pill-text">C · What Needs Waaree Validation</span>
            <span className="tab-pill-count">7 Technical Discoveries</span>
          </button>
        </div>
      </div>

      {activePerspective === 'audit' && (
        <div className="perspective-view-body" role="tabpanel">
          <div className="perspective-header-row">
            <div>
              <h3 className="perspective-title">Audited Operational Discrepancies</h3>
              <p className="perspective-subtitle">
                Independent public findings verified on 2026-09-29 across shop.waaree.com, Amazon India, Flipkart, and support portals. Evidence classification preserved from live URL evidence pack.
              </p>
            </div>

            {/* Evidence Pack + Filter Pills */}
            <div style={{display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-end'}}>
              {/* Evidence Pack CTA */}
              {companyData.evidencePack && (
                <div className="evidence-pack-cta">
                  <div className="evidence-pack-icon">📎</div>
                  <div className="evidence-pack-text">
                    <span className="evidence-pack-label">Evidence Pack</span>
                    <span className="evidence-pack-sub">{companyData.evidencePack.subtitle}</span>
                  </div>
                  <div className="evidence-pack-stats">
                    <span className="ep-stat reproduced">{companyData.evidencePack.reproducedCount} Reproduced</span>
                    <span className="ep-stat partial">{companyData.evidencePack.partialCount} Partial</span>
                    <span className="ep-stat snapshot">{companyData.evidencePack.liveSnapshotCount} Snapshot</span>
                    <span className="ep-stat unverifiable">{companyData.evidencePack.notVerifiableCount} Not Verifiable</span>
                  </div>
                  <a
                    href={companyData.evidencePack.sitemapUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-pack-sitemap-link"
                    title="View full Waaree product sitemap"
                  >
                    75 Products ↗
                  </a>
                </div>
              )}

              {/* Evidence Class Filter Pills */}
              <div className="evidence-filter-group">
                <span className="filter-label">Evidence Class:</span>
                <button
                  type="button"
                  className={`filter-btn ${evidenceFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setEvidenceFilter('all')}
                >
                  All ({discrepancies.length})
                </button>
                <button
                  type="button"
                  className={`filter-btn observed ${evidenceFilter === '[O]' ? 'active' : ''}`}
                  onClick={() => setEvidenceFilter('[O]')}
                  title="Directly evidenced on verified public pages"
                >
                  [O] Observed ({observedCount})
                </button>
                <button
                  type="button"
                  className={`filter-btn inferred ${evidenceFilter === '[I]' ? 'active' : ''}`}
                  onClick={() => setEvidenceFilter('[I]')}
                  title="Strong logical operational inferences"
                >
                  [I] Inferred ({inferredCount})
                </button>
                <button
                  type="button"
                  className={`filter-btn validation ${evidenceFilter === '[V]' ? 'active' : ''}`}
                  onClick={() => setEvidenceFilter('[V]')}
                  title="Requires confirmation from Waaree team"
                >
                  [V] Needs Validation ({validationCount})
                </button>
              </div>
            </div>
          </div>

          {/* Integrity Notice */}
          {companyData.evidencePack && (
            <div className="evidence-integrity-notice">
              <span className="integrity-icon">🛡️</span>
              <div className="integrity-body">
                <strong>Evidence Pack Integrity Corrections</strong>
                <ul className="integrity-list">
                  {companyData.evidencePack.keyIntegrityCorrections.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Category Filter Buttons */}
          <div className="category-filter-strip">
            {['all', 'Catalogue', 'Pricing', 'Inventory', 'Warranty', 'Datasheet', 'Complaints'].map((cat) => (
              <button
                key={cat}
                type="button"
                className={`category-pill-btn ${categoryFilter === cat ? 'active' : ''}`}
                onClick={() => setCategoryFilter(cat)}
              >
                {cat === 'all' ? 'All Categories' : cat}
              </button>
            ))}
          </div>

          {/* Discrepancies Grid */}
          <div className="discrepancies-grid">
            {filteredDiscrepancies.map((item) => {
              const isNotVerifiable = item.evidenceStatus === 'NOT_VERIFIABLE'
              const isNotReproduced = item.evidenceStatus === 'NOT_REPRODUCED'
              const isSnapshot = item.evidenceStatus === 'LIVE_URL_SNAPSHOT'
              const isInferred = item.evidenceStatus === 'INFERRED'
              const isPartial = item.evidenceStatus === 'REPRODUCED_PARTIAL'
              const isLarger = item.evidenceStatus === 'REPRODUCED_LARGER'
              const isReproduced = item.evidenceStatus === 'REPRODUCED'

              const evidenceStatusLabel = {
                'REPRODUCED': '✓ Reproduced',
                'REPRODUCED_LARGER': '✓ Reproduced (scope expanded)',
                'REPRODUCED_PARTIAL': '⚠ Partial — see note',
                'LIVE_URL_SNAPSHOT': '📷 Snapshot — verify on day',
                'NOT_REPRODUCED': '✗ Not reproduced',
                'NOT_VERIFIABLE': '✗ URL dead — not verifiable',
                'INFERRED': '◆ Inferred',
                'ABSENCE_CONFIRMED': '✓ Absence confirmed',
              }[item.evidenceStatus] || item.evidenceStatus

              return (
                <div
                  key={item.id}
                  className={`discrepancy-card ${item.class === '[O]' ? 'observed' : item.class === '[I]' ? 'inferred' : 'validation'} ${isNotVerifiable || isNotReproduced ? 'dimmed-unverified' : ''}`}
                >
                  <div className="disc-card-top">
                    <div className="disc-id-badge">
                      <span className="disc-ref">#{item.ref}</span>
                      <span className="disc-cat">{item.category}</span>
                    </div>
                    <div className="disc-tag-group">
                      <span className={`class-badge ${item.class === '[O]' ? 'observed' : item.class === '[I]' ? 'inferred' : 'validation'}`}>
                        {item.class === '[O]' ? '● [O] Observed' : item.class === '[I]' ? '◆ [I] Inferred' : '▲ [V] To Validate'}
                      </span>
                      <span className="channel-badge">{item.channel}</span>
                    </div>
                  </div>

                  <h4 className="disc-title">{item.title}</h4>

                  {/* Evidence Status Badge */}
                  <div className={`evidence-status-row ${item.evidenceStatus?.toLowerCase().replace(/_/g, '-')}`}>
                    <span className={`evidence-status-badge ${isReproduced || isLarger ? 'green' : isPartial || isSnapshot ? 'amber' : isNotVerifiable || isNotReproduced ? 'red' : 'blue'}`}>
                      {evidenceStatusLabel}
                    </span>
                    {item.evidenceUrl && (
                      <div className="evidence-action-links">
                        <a
                          href={item.evidenceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="view-evidence-link"
                          title={`Open live evidence: ${item.evidenceUrl}`}
                        >
                          View Evidence ↗
                        </a>
                        {item.evidenceUrl2 && (
                          <a
                            href={item.evidenceUrl2}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="view-evidence-link secondary"
                            title={`Open secondary evidence: ${item.evidenceUrl2}`}
                          >
                            View Source 2 ↗
                          </a>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Integrity note for non-reproduced / snapshot / partial */}
                  {item.evidenceNote && (isNotVerifiable || isNotReproduced || isPartial || isSnapshot) && (
                    <div className={`evidence-integrity-chip ${isNotVerifiable || isNotReproduced ? 'error' : 'warn'}`}>
                      {isNotVerifiable || isNotReproduced ? '⚠' : 'ℹ'} {item.evidenceNote}
                    </div>
                  )}

                  <div className="disc-section">
                    <span className="disc-label">WHAT WAS OBSERVED:</span>
                    <p className="disc-text">{item.observedDetail}</p>
                  </div>

                  <div className="disc-section impact">
                    <span className="disc-label">BUSINESS IMPACT:</span>
                    <p className="disc-text">{item.businessImpact}</p>
                  </div>

                  <div className="disc-section action">
                    <span className="disc-label">WHAT SANOCEA DOES:</span>
                    <p className="disc-text">{item.recommendedAction}</p>
                  </div>

                  <div className="disc-footer">
                    <span className="disc-source" title={item.sourceEvidence}>
                      🔗 <strong>Source:</strong> {item.sourceEvidence}
                    </span>
                    <span className="disc-status-tag">{item.status || 'ACTION_REQUIRED'}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── PERSPECTIVE B: Automation Opportunity Map (What We Can Automate) ─ */}
      {activePerspective === 'automation' && (
        <div className="perspective-view-body" role="tabpanel">
          <div className="perspective-header-row">
            <div>
              <h3 className="perspective-title">The Complete Automation Opportunity Map</h3>
              <p className="perspective-subtitle">
                Beyond the specific discrepancies found: a comprehensive map of what SANOCEA can automate across Waaree's multi-channel operations.
              </p>
            </div>
            <div className="governance-badge">
              <span>🛡️ 100% Decision-Gated · Human Approvals Preserved</span>
            </div>
          </div>

          {/* 10 Automation Opportunity Cards */}
          <div className="automation-cards-grid">
            {automationMap.map((opp, idx) => (
              <div key={opp.areaId} className="automation-opp-card">
                <div className="opp-header">
                  <div>
                    <h4 className="opp-title">{opp.areaName}</h4>
                    <span className="opp-scope">{opp.scope}</span>
                  </div>
                  <span className={`opp-status-pill ${opp.statusTag.includes('Finance') ? 'finance' : opp.statusTag.includes('Deploy') ? 'ready' : 'discovery'}`}>
                    {opp.statusTag}
                  </span>
                </div>

                <div className="opp-flow-box">
                  <div className="opp-flow-row">
                    <span className="flow-lbl current">Current Process:</span>
                    <span className="flow-val">{opp.currentProcess}</span>
                  </div>
                  <div className="opp-flow-row">
                    <span className="flow-lbl manual">Manual Overhead:</span>
                    <span className="flow-val">{opp.manualWork}</span>
                  </div>
                  <div className="opp-flow-row highlight">
                    <span className="flow-lbl sanocea">SANOCEA Automation:</span>
                    <span className="flow-val">{opp.sanoceaAutomation}</span>
                  </div>
                  <div className="opp-flow-row approval">
                    <span className="flow-lbl human">Human Sign-off:</span>
                    <span className="flow-val">{opp.humanApprovalRequired}</span>
                  </div>
                </div>

                <div className="opp-footer">
                  <span className="opp-result-label">Expected Outcome:</span>
                  <span className="opp-result-val">✓ {opp.expectedOutcome}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Automation Coverage Matrix Table */}
          <div className="coverage-matrix-section">
            <h4 className="matrix-title">Automation Coverage & Governance Matrix</h4>
            <p className="matrix-subtitle">
              Clear boundaries between autonomous background monitoring and mandatory human governance gates.
            </p>

            <div className="table-responsive">
              <table className="coverage-matrix-table">
                <thead>
                  <tr>
                    <th>Operational Function</th>
                    <th>Continuous Monitoring</th>
                    <th>Discrepancy Detection</th>
                    <th>Action Recommendation</th>
                    <th>Automated Execution</th>
                    <th>Human Approval Required</th>
                  </tr>
                </thead>
                <tbody>
                  {coverageMatrix.map((row, idx) => (
                    <tr key={idx}>
                      <td className="font-semibold">{row.function}</td>
                      <td><span className="badge-auto">{row.monitor}</span></td>
                      <td><span className="badge-auto">{row.detect}</span></td>
                      <td><span className="badge-auto">{row.recommend}</span></td>
                      <td><span className="badge-cond">{row.execute}</span></td>
                      <td><span className={row.approval.includes('Human') ? 'badge-human' : 'badge-neutral'}>{row.approval}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── PERSPECTIVE C: Discovery Scope (What Needs Waaree Validation) ──── */}
      {activePerspective === 'validation' && (
        <div className="perspective-view-body" role="tabpanel">
          <div className="perspective-header-row">
            <div>
              <h3 className="perspective-title">Technical Discovery & Validation Scope</h3>
              <p className="perspective-subtitle">
                Intellectual honesty baseline: clear demarcation of internal systems and files requiring Waaree validation during technical onboarding.
              </p>
            </div>
            <div className="honesty-badge">
              <span>🔒 Zero Unverified Claims · Complementary to Unicommerce</span>
            </div>
          </div>

          <div className="validation-grid">
            {validationRequirements.map((req, idx) => (
              <div key={idx} className="validation-item-card">
                <div className="val-top">
                  <span className="val-num">0{idx + 1}</span>
                  <h4 className="val-system-name">{req.system}</h4>
                </div>
                <div className="val-purpose">
                  <strong>Role:</strong> {req.purpose}
                </div>
                <div className="val-discovery">
                  <strong>Discovery Requirement:</strong> {req.discoveryNeed}
                </div>
                <div className="val-status">
                  <span className="status-label">Current Audit State:</span>
                  <span className="status-val">{req.currentStatus}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Discovery Call Questions Quick Reference */}
          <div className="discovery-questions-box">
            <h4 className="disc-q-title">Key Discovery Questions for Akshay & Waaree Team</h4>
            <div className="disc-q-grid">
              <div className="disc-q-item">
                <span className="q-num">Q1</span>
                <p>You listed Unicommerce COM-OMS and Central Order Management. Are these two systems, or one system with two names?</p>
              </div>
              <div className="disc-q-item">
                <span className="q-num">Q2</span>
                <p>We verified five customer-facing complaint intake portals. Do these feed one unified queue today, or do they sit in separate databases?</p>
              </div>
              <div className="disc-q-item">
                <span className="q-num">Q3</span>
                <p>Where does product master data live — BigCommerce, Unicommerce, SAP S/4HANA, or the Dealer Management System (DMS)?</p>
              </div>
              <div className="disc-q-item">
                <span className="q-num">Q4</span>
                <p>Your warranty documentation specifies a 30-day written defect notice window. What system currently tracks that countdown clock?</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
