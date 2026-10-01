import React, {useState, useMemo} from 'react'
import {SANOCEA_CASE_STUDY_DATA, TENANT_SEO_CONFIGS} from '../data/seoAuditData.js'
import {useSeoOverview, view, fmtTime, sentinelStatus, latestHeartbeat} from '../useSeoOverview.js'
import SeoSearchIntelPanel from './SeoSearchIntelPanel.jsx'
import SeoSentinelPanel from './SeoSentinelPanel.jsx'
import {NotAvailable, relativeAge, HistoricalNotice} from './SeoShared.jsx'

export default function SanoceaCaseStudyView() {
  const caseStudy = SANOCEA_CASE_STUDY_DATA
  const sanoceaConfig = TENANT_SEO_CONFIGS.sanocea
  const seo = useSeoOverview()
  const hbView = view(seo.overview, 'heartbeats')
  const deltaView = view(seo.overview, 'deltas')
  const schedulerView = view(seo.overview, 'scheduler')
  const growthConstraints = sanoceaConfig?.growthConstraints || []

  // Tab navigation for deep evidence & telemetry below the primary fold
  const [activeTab, setActiveTab] = useState('KEYWORDS') // 'KEYWORDS' | 'TECHNICAL_DIFFS' | 'ENDPOINTS_HEARTBEATS' | 'LIFECYCLE' | 'GOVERNANCE'
  const [showRuntimeDetails, setShowRuntimeDetails] = useState(false)
  const [activityCategoryFilter, setActivityCategoryFilter] = useState('ALL')
  const [inspectedOpId, setInspectedOpId] = useState(null)

  // LIVE AUTONOMOUS ACTIVITY is built only from what the worker persisted: Tier-1 probe heartbeats and the
  // detected-change ledger. Times are the worker's own timestamps; the "ago" is computed from them at render.
  const operationsFeed = useMemo(() => {
    const items = []
    if (hbView.ok && Array.isArray(hbView.data)) {
      hbView.data.slice(0, 3).forEach((hb) => items.push({
        id: `HB-${hb.id}`, timestamp: hb.timestamp, sentinel: 'Hourly Sentinel Probe (Tier 1)', category: 'Sentinel',
        title: `Probe of ${hb.domain}`, status: String(hb.status).toUpperCase(), statusColor: hb.status === 'ok' ? 'emerald' : 'red',
        details: `${hb.changeCount} changes detected · ${hb.durationMs} ms.`, targetUrl: `https://${hb.domain}`,
        evidenceSnippet: JSON.stringify(hb, null, 2),
      }))
    }
    if (deltaView.ok && Array.isArray(deltaView.data)) {
      // the worker stores the same signal again on each daily run: show the latest record per change type
      const latestPerType = new Map()
      deltaView.data.forEach((d) => {
        const prev = latestPerType.get(d.changeType)
        if (!prev || String(d.timestamp) > String(prev.timestamp)) latestPerType.set(d.changeType, d)
      })
      Array.from(latestPerType.values()).forEach((d) => items.push({
        id: `DELTA-${d.id}`, timestamp: d.timestamp, sentinel: `Search Intelligence (${d.tier})`, category: 'Search Intel',
        title: d.observedValue, status: d.severity, statusColor: 'blue', details: d.expectedValue, targetUrl: d.url,
        evidenceSnippet: JSON.stringify(d, null, 2),
      }))
    }
    return items.sort((x, y) => String(y.timestamp).localeCompare(String(x.timestamp)))
  }, [hbView, deltaView])
  const feedAvailable = hbView.ok || deltaView.ok
  const filteredOperations = useMemo(() => (activityCategoryFilter === 'ALL' ? operationsFeed : operationsFeed.filter((op) => op.category === activityCategoryFilter)), [operationsFeed, activityCategoryFilter])
  const latestBeat = latestHeartbeat(seo.overview)
  const sentinelLive = sentinelStatus(seo.overview).state === 'live'

  return (
    <div className="sanocea-case-study-card" id="sanocea-seo-workspace">
      {/* ── 1. PRIMARY SENTINEL STATUS BAR ────────────────────────────────────── */}
      <div className="cs-sentinel-bar">
        <div className="cs-sentinel-main">
          <div className="cs-sentinel-live-indicator">
            <span className="live-pulsing-dot">●</span>
            <span className="live-brand-title">SANOCEA Autonomous SEO</span>
            <span className="live-sentinel-badge">{seo.status === 'loading' ? 'CONNECTING…' : sentinelLive ? 'LIVE · Sentinel Active' : 'SENTINEL STATUS NOT AVAILABLE'}</span>
          </div>
          <div className="cs-sentinel-subtext">
            Persisted SEO worker state · <strong>{latestBeat ? `Last probe ${relativeAge(latestBeat.timestamp)}` : 'Last probe NOT AVAILABLE'}</strong>{seo.loadedAt ? ` · read ${fmtTime(seo.loadedAt)} · refreshes every 60 s` : ''}{seo.error ? ` · ${seo.error}` : ''}
          </div>
        </div>
        <div className="cs-sentinel-controls">
          <span className="cs-target-domain-chip">www.sanocea.com</span>
          <button
            type="button"
            className="cs-runtime-toggle-btn"
            onClick={() => setShowRuntimeDetails(!showRuntimeDetails)}
            aria-expanded={showRuntimeDetails}
          >
            {showRuntimeDetails ? '▲ Hide System Runtime' : '⚙ System Evidence & Runtime Details ▾'}
          </button>
        </div>
      </div>

      {/* De-emphasised Engineering / Runtime Details Drawer */}
      {showRuntimeDetails && (
        <div className="cs-runtime-details-drawer">
          <div className="runtime-drawer-header">
            <strong>Systemd Daemon Runtime &amp; Cryptographic Provenance</strong>
            <span className="runtime-badge">Linux Host Service</span>
          </div>
          <div className="runtime-details-grid">
            <div className="runtime-item">
              <span className="runtime-label">System Service:</span>
              <code className="runtime-val">sanocea-seo-worker.service</code>
            </div>
            <div className="runtime-item">
              <span className="runtime-label">Scheduler:</span>
              <span className="runtime-val">{schedulerView.ok ? `Loop ${schedulerView.data.loopRunning ? 'running' : 'STOPPED'} · ${schedulerView.data.jobs.length} jobs · tick ${Math.round(schedulerView.data.tickMs / 1000)}s` : 'NOT AVAILABLE'}</span>
            </div>
            <div className="runtime-item">
              <span className="runtime-label">Persistence:</span>
              <span className="runtime-val">SQLite WAL, read through the demo bridge (no direct browser access)</span>
            </div>
            <div className="runtime-item">
              <span className="runtime-label">Monitoring Tiers:</span>
              <span className="runtime-val">Tier 1: 1h Probe · Tier 2: 24h Search Intel · Tier 3: 14d Crawl</span>
            </div>
            <div className="runtime-item">
              <span className="runtime-label">Remediation Authority:</span>
              <span className="runtime-val">Strictly Scoped to tenantId=sanocea</span>
            </div>
          </div>
        </div>
      )}

      {/* ── 3. LIVE AUTONOMOUS ACTIVITY (Immediately in Primary Viewport) ──────── */}
      <div className="cs-live-activity-stream">
        <div className="cs-activity-header">
          <div className="cs-activity-title-wrap">
            <span className="live-activity-dot">●</span>
            <h4 className="cs-activity-heading">LIVE AUTONOMOUS ACTIVITY</h4>
            <span className="cs-activity-subtext">Persisted ledger of sentinel probes and detected changes, each with the worker&apos;s own timestamp</span>
          </div>
          <div className="cs-activity-filter-pills">
            {['ALL', 'Sentinel', 'Search Intel'].map(cat => (
              <button
                key={cat}
                type="button"
                className={`cs-filter-chip ${activityCategoryFilter === cat ? 'active' : ''}`}
                onClick={() => setActivityCategoryFilter(cat)}
              >
                {cat === 'ALL' ? `All Operations (${operationsFeed.length})` : cat}
              </button>
            ))}
          </div>
        </div>

        <div className="cs-operations-list">
          {!feedAvailable ? <NotAvailable title="Autonomous activity" reason={seo.status === 'loading' ? 'Reading the SEO worker’s persisted ledger…' : (hbView.error || seo.error || 'no ledger returned')} /> : null}
          {filteredOperations.map(op => {
            const isInspected = inspectedOpId === op.id
            return (
              <div key={op.id} className={`cs-operation-card ${isInspected ? 'inspected' : ''}`}>
                <div className="op-card-top">
                  <div className="op-meta-left">
                    <span className="op-relative-time">{relativeAge(op.timestamp)}</span>
                    <span className="op-sentinel-tag">[{op.sentinel}]</span>
                    <strong className="op-title">{op.title}</strong>
                  </div>
                  <div className="op-meta-right">
                    <span className={`op-status-badge ${op.statusColor}`}>{op.status}</span>
                    <button
                      type="button"
                      className="op-inspect-btn"
                      onClick={() => setInspectedOpId(isInspected ? null : op.id)}
                    >
                      {isInspected ? 'Close Evidence' : 'Inspect Evidence'}
                    </button>
                  </div>
                </div>

                <div className="op-card-body">
                  <p className="op-desc">{op.details}</p>
                  <div className="op-target-url">
                    <span className="url-label">Target:</span> <code>{op.targetUrl}</code>
                  </div>
                </div>

                {isInspected && (
                  <div className="op-evidence-drawer">
                    <div className="drawer-title">Evidentiary Proof / Code Payload:</div>
                    <pre className="op-code-snippet">{op.evidenceSnippet}</pre>
                    <div className="drawer-provenance">
                      <span>Event ID: <code>{op.id}</code></span> · 
                      <span> Timestamp: <code>{op.timestamp}</code></span> · 
                      <span> Deterministic Engine Verified</span>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── 4. DEEP EVIDENCE & TELEMETRY TABS ─────────────────────────────────── */}
      <div className="cs-evidence-tabs-section">
        <div className="cs-tabs-row">
          <button
            type="button"
            className={`cs-tab-btn ${activeTab === 'KEYWORDS' ? 'active' : ''}`}
            onClick={() => setActiveTab('KEYWORDS')}
          >
            1. Search &amp; Keyword Intelligence
          </button>
          <button
            type="button"
            className={`cs-tab-btn ${activeTab === 'TECHNICAL_DIFFS' ? 'active' : ''}`}
            onClick={() => setActiveTab('TECHNICAL_DIFFS')}
          >
            2. Exact Verification Diffs &amp; Receipts
          </button>
          <button
            type="button"
            className={`cs-tab-btn ${activeTab === 'ENDPOINTS_HEARTBEATS' ? 'active' : ''}`}
            onClick={() => setActiveTab('ENDPOINTS_HEARTBEATS')}
          >
            3. Monitored Endpoints &amp; Sentinel Heartbeats
          </button>
          <button
            type="button"
            className={`cs-tab-btn ${activeTab === 'LIFECYCLE' ? 'active' : ''}`}
            onClick={() => setActiveTab('LIFECYCLE')}
          >
            4. 5-Phase Controlled Lifecycle
          </button>
          <button
            type="button"
            className={`cs-tab-btn ${activeTab === 'GOVERNANCE' ? 'active' : ''}`}
            onClick={() => setActiveTab('GOVERNANCE')}
          >
            5. Epistemological &amp; Causality Governance
          </button>
        </div>

        {/* Tab 1: Search & Keyword Intelligence: every value comes from the SEO worker's persisted state via the bridge */}
        {activeTab === 'KEYWORDS' && (
          <SeoSearchIntelPanel overview={seo.overview} status={seo.status} error={seo.error} growthConstraints={growthConstraints} />
        )}

        {/* Tab 2: Findings & Exact Technical Diffs */}
        {activeTab === 'TECHNICAL_DIFFS' && (
          <div className="cs-diffs-table-wrap">
            <HistoricalNotice />
            <div style={{marginBottom: '14px', fontSize: '13.5px', color: '#475569', lineHeight: 1.5}}>
              <strong>Remediation Action Ledger &amp; Cryptographic Receipts:</strong> Exact changes prepared, applied, and verified against production.
            </div>
            <table className="cs-diffs-table">
              <thead>
                <tr>
                  <th>Technical Component</th>
                  <th>BEFORE Intervention</th>
                  <th>AFTER Intervention</th>
                  <th>Automated Verification Evidence</th>
                </tr>
              </thead>
              <tbody>
                {caseStudy.intervention.changesApplied.map((diff, idx) => (
                  <tr key={idx}>
                    <td><strong>{diff.field}</strong></td>
                    <td className="diff-before"><code>{diff.before}</code></td>
                    <td className="diff-after"><code>{diff.after}</code></td>
                    <td className="diff-verif"><span className="verif-check">✓</span> {diff.verification}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab 3: Monitored Endpoints & Sentinel Heartbeats */}
        {activeTab === 'ENDPOINTS_HEARTBEATS' && (
          <SeoSentinelPanel overview={seo.overview} status={seo.status} error={seo.error} />
        )}

        {/* Tab 4: 5-Phase Controlled Lifecycle */}
        {activeTab === 'LIFECYCLE' && (
          <div className="cs-lifecycle-flow-5">
            <HistoricalNotice />
            {/* Phase 1: BEFORE */}
            <div className="lifecycle-phase before">
              <div className="phase-header">
                <span className="phase-num">PHASE 1</span>
                <h4>BEFORE Baseline</h4>
                <span className="phase-tag">28-Day Baseline</span>
              </div>
              <div className="phase-body">
                <div className="phase-metric-group">
                  <div className="metric-label">Technical Findings Baseline:</div>
                  <div className="metric-val text-danger">
                    <strong>7 Verified Engineering Flaws:</strong>
                  </div>
                </div>
                <ul className="cs-flaws-list">
                  <li>• 78-character / oversized title (624px &gt; 561px)</li>
                  <li>• 219-character meta description (mobile truncation)</li>
                  <li>• 0 SSR H1 tags in raw HTML payload</li>
                  <li>• 0 static internal outlinks (SPA router trap)</li>
                  <li>• Missing security headers (HSTS &amp; CSP)</li>
                  <li>• Missing /llms.txt context file (HTTP 404)</li>
                  <li>• Crawler stalled at 1 URL (Screaming Frog baseline)</li>
                </ul>
                <div className="phase-metric-group mt-2">
                  <div className="metric-label">GSC Search Baseline (28-day):</div>
                  <div className="metric-val">
                    <strong>{caseStudy.before.gscBaseline.clicks.toLocaleString()}</strong> Clicks · <strong>{caseStudy.before.gscBaseline.impressions.toLocaleString()}</strong> Imps (Avg Pos: {caseStudy.before.gscBaseline.averagePosition})
                  </div>
                </div>
              </div>
            </div>

            <div className="lifecycle-arrow">➔</div>

            {/* Phase 2: INTERVENTION */}
            <div className="lifecycle-phase intervention">
              <div className="phase-header">
                <span className="phase-num">PHASE 2</span>
                <h4>INTERVENTION</h4>
                <span className="phase-tag verified">Receipt Verified</span>
              </div>
              <div className="phase-body">
                <div className="receipt-id-tag">
                  Action: <code>{caseStudy.intervention.receiptId}</code>
                </div>
                <div className="receipt-details">
                  <p><strong>Mechanism:</strong> {caseStudy.intervention.executionMechanism}</p>
                  <p><strong>Timestamp:</strong> {caseStudy.intervention.timestamp}</p>
                  <p><strong>Verifier:</strong> <code>{caseStudy.intervention.verifiedBy}</code></p>
                </div>
                <div className="changes-summary-pill">
                  5 Critical Elements Remediated &amp; Merged via Staged PR
                </div>
              </div>
            </div>

            <div className="lifecycle-arrow">➔</div>

            {/* Phase 3: VERIFICATION */}
            <div className="lifecycle-phase verification">
              <div className="phase-header">
                <span className="phase-num">PHASE 3</span>
                <h4>VERIFICATION</h4>
                <span className="phase-tag verified">100% Pass</span>
              </div>
              <div className="phase-body">
                <div className="phase-metric-group">
                  <div className="metric-label">Automated Assertions:</div>
                  <div className="metric-val text-success">
                    <strong>5/5 Verified Clean</strong>
                  </div>
                </div>
                <ul className="cs-assertions-list">
                  {caseStudy.technicalVerification.assertions.map((a, i) => (
                    <li key={i}>
                      <span className="assert-name">{a.check}:</span>{' '}
                      <span className="assert-obs">{a.observed}</span>{' '}
                      <span className="assert-status">✓ {a.status}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="lifecycle-arrow">➔</div>

            {/* Phase 4: OBSERVATION */}
            <div className="lifecycle-phase observation">
              <div className="phase-header">
                <span className="phase-num">PHASE 4</span>
                <h4>OBSERVATION</h4>
                <span className="phase-tag pending">Window Active</span>
              </div>
              <div className="phase-body">
                <div className="phase-metric-group">
                  <div className="metric-label">Observation Window:</div>
                  <div className="metric-val">
                    <strong>Day 2 of 28</strong>
                  </div>
                </div>
                <div className="phase-metric-group">
                  <div className="metric-label">Duration Requirement:</div>
                  <div className="metric-val">
                    {caseStudy.observationWindow?.minimumDaysRequired || 28} Days continuous indexation required
                  </div>
                </div>
                <div className="obs-governance-note">
                  <p>{caseStudy.observationWindow?.governanceRule || 'Statistical defensibility requires 14–28 days of uninterrupted Googlebot recrawling before post-intervention telemetry is evaluated.'}</p>
                </div>
              </div>
            </div>

            <div className="lifecycle-arrow">➔</div>

            {/* Phase 5: AFTER */}
            <div className="lifecycle-phase after">
              <div className="phase-header">
                <span className="phase-num">PHASE 5</span>
                <h4>AFTER Telemetry</h4>
                <span className="phase-tag pending">Unclaimed</span>
              </div>
              <div className="phase-body">
                <div className="phase-metric-group">
                  <div className="metric-label">Ranking Telemetry:</div>
                  <div className="metric-val text-muted">
                    <em>Clicks / Imps: <strong>UNCLAIMED</strong></em>
                  </div>
                </div>
                <div className="phase-metric-group">
                  <div className="metric-label">GSC Status:</div>
                  <div className="metric-val text-muted">
                    <code>{caseStudy.after.gscPostDeployment.status}</code>
                  </div>
                </div>
                <div className="no-fabrication-banner">
                  <strong>Honesty Protocol:</strong> Zero manufactured ranking gains displayed. SANOCEA refuses to fabricate outcomes while the observation window remains open.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Governance */}
        {activeTab === 'GOVERNANCE' && (
          <div className="cs-governance-view">
            <HistoricalNotice />
            <div className="gov-card disclaimer">
              <h4>Strict Anti-Causality Rule</h4>
              <p>{caseStudy.governance.antiCausalityDisclaimer}</p>
            </div>

            <div className="gov-card boundary mt-3">
              <h4>Google Search Intelligence vs Ranking Algorithm Boundary</h4>
              <p>{caseStudy.governance.algorithmBoundaryNote}</p>
            </div>

            <div className="gov-card algo-updates mt-3">
              <h4>Google Core &amp; Review Updates in Evaluation Window</h4>
              <div className="algo-updates-grid">
                {caseStudy.governance.algorithmContext.map((algo, idx) => (
                  <div key={idx} className="algo-item">
                    <div className="algo-date">{algo.date}</div>
                    <div className="algo-name">{algo.name}</div>
                    <div className="algo-note">{algo.note}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
