import React, {useState} from 'react'
import ChannelConnectivity from './ChannelConnectivity.jsx'
import WaareeIntelligenceSection from './WaareeIntelligenceSection.jsx'
import {getChannelLogo} from '../data/companyData.js'
import {TENANT_SEO_CONFIGS} from '../data/seoAuditData.js'
import {useSeoOverview, gscNumbers, sentinelStatus, latestHeartbeat, fmtTime} from '../useSeoOverview.js'
import {Chip, NotAvailable, OpportunityModelUnavailable, RankMovementAndSerp, GrowthConstraintsEditorial, MonitoredEndpoints, HeartbeatsTable, relativeAge} from './SeoShared.jsx'

export default function DashboardView({
  companyData,
  urgentActions,
  onResolveAction,
  onSwitchToWhatsApp,
  channelStates,
  globalStatus,
  onSimulateDegrade,
  onReconnectChannel,
  activeTableTab: propActiveTableTab,
  onChangeTableTab,
}) {
  const [internalTableTab, setInternalTableTab] = useState('inventory') // 'inventory' | 'exceptions'
  const activeTableTab = propActiveTableTab !== undefined ? propActiveTableTab : internalTableTab
  const setActiveTableTab = (tab) => {
    setInternalTableTab(tab)
    if (onChangeTableTab) onChangeTableTab(tab)
  }
  const [inventoryFilter, setInventoryFilter] = useState('all') // 'all' | 'oos' | 'low' | 'healthy'

  const isSanocea = companyData?.companyId === 'sanocea'
  // The same SEO data contract the SEO & Commerce Audit tab uses (one store, one fetch). Only the Sanocea tenant subscribes.
  const seo = useSeoOverview(isSanocea)
  const gsc = gscNumbers(seo.overview)
  const sentinel = sentinelStatus(seo.overview)
  const lastBeat = latestHeartbeat(seo.overview)
  const NA = 'NOT AVAILABLE'
  const kpis = companyData?.kpis || {}
  const channels = companyData?.channels || []
  const inventoryItems = companyData?.inventoryItems || []
  const exceptionsLog = companyData?.exceptionsLog || []
  const sanoceaSeo = TENANT_SEO_CONFIGS?.sanocea
  const growthConstraints = sanoceaSeo?.growthConstraints || []
  // Strict governance: SANOCEA Dashboard must contain zero SEO remediation cards
  const safeUrgentActions = (urgentActions || []).filter((action) => {
    if (!action) return false
    if (isSanocea && (action.category === 'SEO' || action.actionKind === 'approve-seo-fix' || action.ref?.startsWith('SAN-SEO') || action.channelId === 'google')) {
      return false
    }
    return true
  })

  const filteredInventory = inventoryItems.filter((item) => {
    if (!item) return false
    if (inventoryFilter === 'all') return true
    if (inventoryFilter === 'oos') return item.riskLevel === 'oos'
    if (inventoryFilter === 'low') return item.riskLevel === 'critical' || item.riskLevel === 'warning'
    if (inventoryFilter === 'healthy') return item.riskLevel === 'healthy'
    return true
  })

  return (
    <div className="dashboard-view-container">
      {/* ── Section 1: Prominent LIVE Channel Connectivity Section (Executive Level) ── */}
      {channelStates && globalStatus && (
        <div id="channels">
          <ChannelConnectivity
            channels={channelStates}
            globalStatus={globalStatus}
            onSimulateDegrade={onSimulateDegrade}
            onReconnectChannel={onReconnectChannel}
          />
        </div>
      )}

      {/* ── Section 2: Actions Requiring Immediate Attention (Decision Center) ── */}
      <section className="decision-center" id="decisions" aria-labelledby="decision-center-title">
        <div className="section-head-row">
          <div>
            <div className="section-title" id="decision-center-title">
              <span>⚡ Actions Requiring Attention</span>
              <span className="action-count-tag">
                {safeUrgentActions.filter((a) => a && !a.resolved).length} Pending Decision
              </span>
            </div>
            <div className="section-subtitle">
              Operations Intelligence Layer · Decision-Gated Automations
            </div>
          </div>
        </div>

        {safeUrgentActions.length === 0 ? (
          <div
            className="zero-actions-state"
            style={{
              background: '#F8FAFC',
              border: '1px solid #E2E8F0',
              borderRadius: '12px',
              padding: '24px 28px',
              display: 'flex',
              alignItems: 'center',
              gap: '18px',
              marginTop: '12px',
            }}
          >
            <span style={{fontSize: 32}}>🛡️</span>
            <div>
              <div style={{fontWeight: 800, fontSize: 16, color: '#0F172A'}}>
                {isSanocea
                  ? 'Autonomous Sentinels Active · 0 Decisions Pending'
                  : 'All Systems Operational · 0 Pending Decisions'}
              </div>
              <div style={{fontSize: 13.5, color: '#64748B', marginTop: 4, lineHeight: 1.5}}>
                {isSanocea
                  ? 'Tier 1/2/3 background worker is running continuously. SEO remediation & audit findings are strictly isolated to the SEO & Commerce Audit command view.'
                  : 'Operations Intelligence Layer is monitoring all active sales connectors with zero unhandled exceptions.'}
              </div>
            </div>
          </div>
        ) : (
          <div className="decision-grid">
            {safeUrgentActions.map((action) => (
              <div
                key={action.id}
                className={`decision-card ${action.severity} ${action.resolved ? 'resolved' : ''}`}
            >
              <div>
                <div className="decision-top">
                  <div className="decision-meta">
                    <span className="channel-tag">
                      {getChannelLogo(action.channelId, action.channel) && (
                        <img
                          src={getChannelLogo(action.channelId, action.channel)}
                          alt=""
                          className="channel-mini-logo"
                        />
                      )}
                      <span>{action.channel}</span>
                    </span>
                    <span className="category-tag">{action.category}</span>
                    {action.evidenceClass && (
                      <span
                        className="class-badge observed"
                        style={{
                          fontSize: '11px',
                          fontWeight: 800,
                          padding: '2px 7px',
                          borderRadius: '4px',
                          background: '#ECFDF5',
                          color: '#047857',
                          border: '1px solid #A7F3D0',
                        }}
                      >
                        {action.evidenceClass}
                      </span>
                    )}
                  </div>
                  <span className={`severity-pill ${action.severity}`}>
                    {action.resolved ? 'RESOLVED' : action.severity}
                  </span>
                </div>

                <h3 className="decision-title">{action.title}</h3>
                <p className="decision-desc">{action.description}</p>

                {action.resolved ? (
                  <div className="decision-resolution-receipt">
                    <div className="closed-loop-chain-label">
                      <span>CLOSED-LOOP EXECUTION RECEIPT</span>
                      <span className="audit-id">IMMUTABLE AUDIT #{action.resolutionAuditId || `SAN-${action.id.toUpperCase()}-VERIFIED`}</span>
                    </div>
                    <div className="resolution-loop-chain">
                      <div className="receipt-step completed">
                        <span className="step-icon">✓</span>
                        <span className="step-label">Approval prepared</span>
                      </div>
                      <span className="receipt-arrow">➔</span>
                      <div className="receipt-step completed">
                        <span className="step-icon">✓</span>
                        <span className="step-label">Approved by operator</span>
                      </div>
                      <span className="receipt-arrow">➔</span>
                      <div className="receipt-step completed">
                        <span className="step-icon">✓</span>
                        <span className="step-label">{companyData.companyId === 'waaree' ? 'Simulation sandbox synced' : `${action.channel} connector synced`}</span>
                      </div>
                      <span className="receipt-arrow">➔</span>
                      <div className="receipt-step completed">
                        <span className="step-icon">✓</span>
                        <span className="step-label">Immutable audit verified</span>
                      </div>
                    </div>
                    <div className="resolution-detail-text">
                      <span className="resolution-check">✓</span>
                      <span>{action.resolutionText}</span>
                    </div>
                  </div>
                ) : (
                  <div className="decision-rec-box">
                    <strong>Recommendation:</strong> {action.recommendation}
                    {action.simulationNotice && (
                      <div style={{fontSize: 12, color: 'var(--text-muted)', marginTop: 8, fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: 6}}>
                        <span>🛡️</span>
                        <span>{action.simulationNotice}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="decision-actions">
                {!action.resolved ? (
                  <>
                    <button
                      type="button"
                      className="btn-primary-action"
                      onClick={() => onResolveAction(action.id)}
                    >
                      <span>⚡</span>
                      <span>{action.actionLabel}</span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost-action"
                      onClick={() => onSwitchToWhatsApp(action.ref)}
                      title="Inspect event in connected WhatsApp stream"
                    >
                      <span>Open in WhatsApp ↗</span>
                    </button>
                  </>
                ) : (
                  <div className="receipt-audit-badge">
                    <span className="receipt-pulse-dot">●</span>
                    <span>Immutable audit receipt verified · Closed-loop synced across {companyData.companyId === 'waaree' ? 'simulation state' : `${action.channel} connector`} & WhatsApp</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>

      {/* ── Section 3: Executive Operational KPI Ribbon / SANOCEA Autonomous Summary ── */}
      {isSanocea ? (
        <section aria-label="Autonomous SEO & Search Operations Summary" className="sanocea-ops-summary">
          <div className="section-head-row">
            <div>
              <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
                <h2 className="section-title" style={{margin: 0}}>Autonomous SEO & Search Operations Overview</h2>
                <span
                  style={{
                    background: '#0F172A',
                    color: '#38BDF8',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 700,
                    padding: '3px 8px',
                    borderRadius: 4,
                  }}
                >
                  {seo.status === 'loading' ? 'CONNECTING…' : sentinel.state === 'live' ? '24/7 SENTINEL ACTIVE' : 'SENTINEL STATUS NOT AVAILABLE'}
                </span>
              </div>
              <div className="section-subtitle">
                Continuous closed-loop monitoring, search intelligence, and telemetry verification for SANOCEA.com
              </div>
            </div>
          </div>

          {/* Live SEO KPI cards: both read the shared persisted-worker store */}
          <div className="kpi-grid">
            {/* Search Intelligence (GSC Telemetry): live from the persisted worker state */}
            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Search Intelligence (GSC)</span>
                <Chip label={gsc ? '[OBSERVED]' : '[NOT AVAILABLE]'} />
              </div>
              <div className="kpi-value">
                {gsc ? gsc.clicks.toLocaleString() : NA}{' '}
                <span style={{fontSize: 16, fontWeight: 600, color: 'var(--text-secondary)'}}>GSC Clicks</span>
              </div>
              <div className="kpi-subtext">
                <span>{gsc ? gsc.impressions.toLocaleString() : NA} Impr [OBSERVED]</span> · {gsc ? `${(gsc.ctr * 100).toFixed(2)}%` : NA} CTR [CALCULATED]
              </div>
              <div style={{fontSize: 13, color: 'var(--text-muted)', marginTop: 8}}>
                Average Position: <strong>{gsc ? gsc.position.toFixed(2) : NA}</strong>{gsc ? ` · ${gsc.queryRows} query rows disclosed (privacy anonymized)` : ''}
              </div>
              <div style={{fontSize: 11.5, color: 'var(--text-muted)', marginTop: 6, fontFamily: 'var(--font-mono)'}}>snapshot captured {gsc ? fmtTime(gsc.capturedAt) : 'no timestamp reported'}</div>
            </div>

            {/* Monitoring Sentinel Worker: live from the persisted scheduler and heartbeat state */}
            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">24/7 Sentinel Worker</span>
                <Chip label={seo.status === 'loading' ? 'CONNECTING…' : sentinel.state === 'live' ? '[OBSERVED] Scheduler running' : '[NOT AVAILABLE]'} />
              </div>
              <div className="kpi-value">{sentinel.state === 'unavailable' ? NA : `${sentinel.jobs.length} jobs scheduled`}</div>
              <div className="kpi-subtext">Hourly probe: {lastBeat ? `${String(lastBeat.status).toUpperCase()} · ${lastBeat.changeCount} changes · ${relativeAge(lastBeat.timestamp)}` : NA}</div>
              <div style={{fontSize: 13, color: 'var(--text-muted)', marginTop: 8}}>
                Persistence: SQLite WAL
              </div>
              <div style={{fontSize: 11.5, color: 'var(--text-muted)', marginTop: 6, fontFamily: 'var(--font-mono)'}}>last scheduler heartbeat {sentinel.tickAt ? fmtTime(sentinel.tickAt) : 'no timestamp reported'}</div>
            </div>

          </div>
        </section>
      ) : (
        <section aria-label="Business Overview & Operational Health Metrics">
          <div className="section-head-row">
            <div>
              <h2 className="section-title">Business Overview</h2>
              <div className="section-subtitle">
                Commerce performance & operational health across all active sales channels
              </div>
            </div>
          </div>

          <div className="kpi-grid">
            {/* GMV / Revenue */}
            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Gross Merchandise Value (GMV)</span>
                <span className="kpi-delta up">{kpis.revenueDelta}</span>
              </div>
              <div className="kpi-value">{kpis.revenueMtd}</div>
              <div className="kpi-subtext">
                <span>{kpis.revenueToday}</span> · MTD Run-rate
              </div>
              {/* Channel split bar */}
              <div style={{display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 14, background: '#E5E7EB'}}>
                <div style={{width: '44%', background: 'var(--teal-primary)'}} title="Quick Commerce 44%" />
                <div style={{width: '34%', background: 'var(--green-success)'}} title="D2C 34%" />
                <div style={{width: '22%', background: '#6366F1'}} title="Marketplaces 22%" />
              </div>
            </div>

            {/* Orders & AOV */}
            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Orders & Basket AOV</span>
                <span className="kpi-delta up">{kpis.aovDelta}</span>
              </div>
              <div className="kpi-value">{kpis.ordersMtd} <span style={{fontSize: 16, fontWeight: 600, color: 'var(--text-secondary)'}}>orders</span></div>
              <div className="kpi-subtext">
                <span>Avg AOV: <strong>{kpis.aov}</strong></span> · {kpis.ordersSla}
              </div>
              <div style={{fontSize: 13, color: 'var(--text-muted)', marginTop: 8}}>
                {kpis.ordersToday} processed today
              </div>
            </div>

            {/* Active Products & Catalog Health */}
            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Catalog & Active SKUs</span>
                <span className="kpi-status-pill optimal">
                  {kpis.catalogHealth} Health
                </span>
              </div>
              <div className="kpi-value">{kpis.activeSkus}</div>
              <div className="kpi-subtext">
                {kpis.channelListings}
              </div>
              <div style={{fontSize: 13, color: 'var(--text-muted)', marginTop: 8}}>
                Cross-channel schema audit active
              </div>
            </div>

            {/* Inventory Health & Stockout Risk */}
            <div className="kpi-card" style={{borderLeft: '5px solid var(--red-critical)'}}>
              <div className="kpi-header">
                <span className="kpi-title">Inventory Health</span>
                <span className="kpi-status-pill danger">Stockout Risk</span>
              </div>
              <div className="kpi-value" style={{color: 'var(--red-critical)'}}>{kpis.inventoryHealth}</div>
              <div className="kpi-subtext" style={{color: 'var(--red-critical)', fontWeight: 700}}>
                {kpis.stockoutRisk}
              </div>
              <div style={{fontSize: 13, color: 'var(--text-muted)', marginTop: 8}}>
                Fast-depleting in quick-commerce hubs
              </div>
            </div>

            {/* Pending Approvals */}
            <div className="kpi-card" style={{borderLeft: '5px solid var(--amber-warning)'}}>
              <div className="kpi-header">
                <span className="kpi-title">Pending Approvals</span>
                <span className="kpi-status-pill warning">Decisions</span>
              </div>
              <div className="kpi-value" style={{color: 'var(--amber-warning)'}}>
                {safeUrgentActions.filter((a) => a && !a.resolved).length} Pending
              </div>
              <div className="kpi-subtext">
                {kpis.pendingApprovalsLabel}
              </div>
              <div style={{fontSize: 13, color: 'var(--teal-primary)', fontWeight: 700, marginTop: 8, cursor: 'pointer'}} onClick={() => onSwitchToWhatsApp()}>
                Actionable via WhatsApp or above ↗
              </div>
            </div>

            {/* Catalogue Exceptions */}
            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Active Exceptions</span>
                <span className="kpi-status-pill warning">Exceptions</span>
              </div>
              <div className="kpi-value">{kpis.catalogueExceptionsCount} Flagged</div>
              <div className="kpi-subtext">
                {kpis.catalogueExceptionsLabel}
              </div>
              <div style={{fontSize: 13, color: 'var(--text-muted)', marginTop: 8}}>
                Automated guard rules active
              </div>
            </div>
          </div>
        </section>
      )}



      {/* ── Perspective Sections for Waaree Prospect Environment ── */}
      {companyData?.companyId === 'waaree' && (
        <WaareeIntelligenceSection
          companyData={companyData}
          onSwitchToWhatsApp={onSwitchToWhatsApp}
        />
      )}

      {/* ── Section 4: Operations Trend Graph + Multi-Channel Matrix ─────────── */}
      <section className="middle-grid">
        {isSanocea ? (
          <div className="panel-card" style={{display: 'flex', flexDirection: 'column', gap: 0}}>
            {/* ── LAYER 1: OBSERVED GSC SEARCH TELEMETRY ── */}
            <div style={{padding: '20px 24px', borderBottom: '2px solid #E2E8F0', background: '#FAFCFF'}}>
              <div style={{display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 16}}>
                <div>
                  <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4}}>
                    <span style={{fontSize: 11, fontWeight: 800, letterSpacing: '0.06em', background: '#0284C7', color: '#FFFFFF', padding: '3px 8px', borderRadius: 4}}>
                      LAYER 1 · OBSERVED
                    </span>
                    <h3 style={{fontSize: 16, fontWeight: 800, color: '#0F172A', margin: 0}}>
                      📡 Google Search Console — Verified Live Telemetry
                    </h3>
                  </div>
                  <span style={{fontSize: 12.5, color: '#64748B'}}>
                    {gsc ? <>Persisted GSC snapshot of <code>{gsc.siteUrl}</code> · window {gsc.startDate} → {gsc.endDate} · captured {fmtTime(gsc.capturedAt)}</> : 'Persisted GSC snapshot NOT AVAILABLE'}
                  </span>
                </div>
                <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
                  <span style={{fontSize: 12, padding: '4px 10px', background: '#ECFDF5', color: '#047857', border: '1px solid #A7F3D0', borderRadius: 6, fontWeight: 700}}>
                    {gsc ? '● Persisted by the SEO worker' : '○ Not available'}
                  </span>
                </div>
              </div>

              {/* 4-Stat Live Metrics Grid */}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12, marginBottom: 14}}>
                <div style={{background: '#FFFFFF', border: '1px solid #BAE6FD', borderRadius: 8, padding: '10px 14px'}}>
                  <div style={{fontSize: 11, fontWeight: 700, color: '#0284C7', textTransform: 'uppercase', letterSpacing: '0.05em'}}>Clicks [OBSERVED]</div>
                  <div style={{fontSize: 22, fontWeight: 800, color: '#0F172A', marginTop: 2}}>{gsc ? gsc.clicks.toLocaleString() : NA}</div>
                  <div style={{fontSize: 11, color: '#64748B', marginTop: 2}}>{gsc ? gsc.provenance : ''}</div>
                </div>
                <div style={{background: '#FFFFFF', border: '1px solid #BAE6FD', borderRadius: 8, padding: '10px 14px'}}>
                  <div style={{fontSize: 11, fontWeight: 700, color: '#0284C7', textTransform: 'uppercase', letterSpacing: '0.05em'}}>Impressions [OBSERVED]</div>
                  <div style={{fontSize: 22, fontWeight: 800, color: '#0F172A', marginTop: 2}}>{gsc ? gsc.impressions.toLocaleString() : NA}</div>
                  <div style={{fontSize: 11, color: '#64748B', marginTop: 2}}>{gsc ? `${gsc.startDate} → ${gsc.endDate}` : ''}</div>
                </div>
                <div style={{background: '#FFFFFF', border: '1px solid #DDD6FE', borderRadius: 8, padding: '10px 14px'}}>
                  <div style={{fontSize: 11, fontWeight: 700, color: '#7C3AED', textTransform: 'uppercase', letterSpacing: '0.05em'}}>CTR [CALCULATED]</div>
                  <div style={{fontSize: 22, fontWeight: 800, color: '#0F172A', marginTop: 2}}>{gsc ? `${(gsc.ctr * 100).toFixed(2)}%` : NA}</div>
                  <div style={{fontSize: 11, color: '#64748B', marginTop: 2}}>clicks ÷ impressions</div>
                </div>
                <div style={{background: '#FFFFFF', border: '1px solid #BAE6FD', borderRadius: 8, padding: '10px 14px'}}>
                  <div style={{fontSize: 11, fontWeight: 700, color: '#0284C7', textTransform: 'uppercase', letterSpacing: '0.05em'}}>Avg Position [OBSERVED]</div>
                  <div style={{fontSize: 22, fontWeight: 800, color: '#0F172A', marginTop: 2}}>{gsc ? gsc.position.toFixed(2) : NA}</div>
                  <div style={{fontSize: 11, color: '#64748B', marginTop: 2}}>impression-weighted</div>
                </div>
              </div>

              {/* Privacy Threshold Notice Box */}
              <div style={{background: '#F1F5F9', border: '1px solid #CBD5E1', borderRadius: 8, padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 12}}>
                <span style={{fontSize: 18, marginTop: 1}}>🔒</span>
                <div>
                  <div style={{fontSize: 13, fontWeight: 700, color: '#1E293B', marginBottom: 2}}>
                    GSC Query Anonymization Active — Query-Level Attribution Unavailable [OBSERVED FACT]
                  </div>
                  <div style={{fontSize: 12, color: '#475569', lineHeight: 1.5}}>
                    {gsc ? <>Google Search Console returned <strong>{gsc.queryRows} query dimension rows</strong> for this window across {gsc.impressions} aggregate impressions and {gsc.clicks} clicks. Under Google&apos;s privacy filtering threshold, individual search queries are withheld. Query-level intent attribution cannot be established from observed search data.</> : 'Query-level state NOT AVAILABLE: no persisted GSC snapshot was returned.'}
                  </div>
                </div>
              </div>
            </div>

            {/* ── LAYER 2: SEO OPPORTUNITY MODEL: no persisted source exists, so nothing is modeled ── */}
            <div style={{padding: '20px 24px', background: '#FFFFFF'}}>
              <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap'}}>
                <span style={{fontSize: 11, fontWeight: 800, letterSpacing: '0.06em', background: '#7C3AED', color: '#FFFFFF', padding: '3px 8px', borderRadius: 4}}>
                  LAYER 2 · MODELED
                </span>
                <h3 style={{fontSize: 16, fontWeight: 800, color: '#581C87', margin: 0}}>
                  🎯 SEO Opportunity Model — Not GSC Observed
                </h3>
              </div>
              <OpportunityModelUnavailable />
            </div>

            {/* ── LAYER 3: RANK MOVEMENT (GSC) + EXACT KEYWORD SERP LEDGER ── */}
            <div style={{padding: '20px 24px', borderTop: '2px solid #E2E8F0', background: '#F8FAFC'}}>
              {seo.overview ? <RankMovementAndSerp overview={seo.overview} /> : <NotAvailable title="Rank movement and SERP ledger" reason={seo.status === 'loading' ? 'Reading the SEO worker’s persisted state…' : (seo.error || 'SEO worker unavailable')} />}
            </div>

            {/* ── FOUR CURRENT GROWTH CONSTRAINTS: editorial, not worker telemetry ── */}
            <div style={{padding: '20px 24px', borderTop: '2px solid #E2E8F0', background: '#FFFFFF'}}>
              <GrowthConstraintsEditorial items={growthConstraints} />
            </div>
          </div>
        ) : (
          /* Operations Intelligence Trend Chart */
          <div className="panel-card">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  <span>📈 Operations Decision & Revenue Protection</span>
                </h3>
                <span className="panel-subtext">
                  Quantified GMV protected vs. operational exceptions resolved over the past 14 days
                </span>
              </div>
              <span className="kpi-delta up" style={{fontSize: 13.5, padding: '4px 10px'}}>
                ₹2.4L GMV Protected
              </span>
            </div>

            <div className="chart-container">
              {/* Responsive SVG Chart with Light SaaS Theme */}
              <svg className="chart-svg" viewBox="0 0 600 180" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="gmvGradientLight" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#00838F" stopOpacity="0.2" />
                    <stop offset="100%" stopColor="#00838F" stopOpacity="0.0" />
                  </linearGradient>
                  <linearGradient id="riskGradientLight" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#DC2626" stopOpacity="0.15" />
                    <stop offset="100%" stopColor="#DC2626" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Gridlines */}
                <line x1="0" y1="30" x2="600" y2="30" stroke="#F3F4F6" strokeDasharray="4 4" />
                <line x1="0" y1="75" x2="600" y2="75" stroke="#F3F4F6" strokeDasharray="4 4" />
                <line x1="0" y1="120" x2="600" y2="120" stroke="#F3F4F6" strokeDasharray="4 4" />
                <line x1="0" y1="165" x2="600" y2="165" stroke="#E5E7EB" />

                {/* Area 1: GMV Protected Area */}
                <path
                  d="M 0 140 Q 80 120, 150 95 T 300 80 T 450 45 T 600 25 L 600 165 L 0 165 Z"
                  fill="url(#gmvGradientLight)"
                />
                {/* Line 1: GMV Protected */}
                <path
                  d="M 0 140 Q 80 120, 150 95 T 300 80 T 450 45 T 600 25"
                  fill="none"
                  stroke="#00838F"
                  strokeWidth="2.5"
                />

                {/* Line 2: Stockout & Pricing Loss Prevented */}
                <path
                  d="M 0 65 Q 80 85, 150 110 T 300 135 T 450 150 T 600 158"
                  fill="none"
                  stroke="#DC2626"
                  strokeWidth="2"
                  strokeDasharray="5 3"
                />

                {/* Key event dots */}
                <circle cx="150" cy="95" r="5" fill="#00838F" stroke="#FFFFFF" strokeWidth="2" />
                <circle cx="300" cy="80" r="5" fill="#00838F" stroke="#FFFFFF" strokeWidth="2" />
                <circle cx="450" cy="45" r="6" fill="#D97706" stroke="#FFFFFF" strokeWidth="2" />
                <circle cx="600" cy="25" r="6" fill="#15803D" stroke="#FFFFFF" strokeWidth="2" />
              </svg>

              <div className="chart-legend">
                <div className="legend-item">
                  <span className="legend-dot" style={{background: '#00838F'}} />
                  <span>Protected Realized GMV</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{background: '#DC2626'}} />
                  <span>Stockout / Pricing Leakage (Mitigated)</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{background: '#D97706'}} />
                  <span>Sanocea Guard Interventions</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Marketplace & Channel Performance Matrix */}
        <div className="panel-card">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">
                <span>🌐 Channel Performance</span>
              </h3>
              <span className="panel-subtext">
                Live sync latency & operational exceptions per connector
              </span>
            </div>
            <span style={{fontFamily: 'var(--font-mono)', fontSize: 13.5, fontWeight: 800, color: 'var(--green-success)'}}>
              {channels.filter(c => c.status === 'healthy').length}/{channels.length} CONNECTED
            </span>
          </div>

          <div className="channel-list">
            {channels.map((ch) => (
              <div key={ch.id} className="channel-row">
                <div className="channel-left">
                  {getChannelLogo(ch.id, ch.name) ? (
                    <img
                      src={getChannelLogo(ch.id, ch.name)}
                      alt={ch.name}
                      className="channel-matrix-logo"
                    />
                  ) : (
                    <div
                      className="lcc-icon-badge"
                      style={{
                        background: '#F3F4F6',
                        color: 'var(--teal-primary)',
                        border: '1px solid var(--border-subtle)',
                        width: 44,
                        height: 44,
                        fontSize: 15,
                      }}
                    >
                      {ch.shortName.slice(0, 2).toUpperCase()}
                    </div>
                  )}
                  <div className="channel-info">
                    <h4>{ch.name}</h4>
                    <div className="channel-status-line">
                      <span style={{color: ch.status === 'healthy' ? 'var(--green-success)' : 'var(--amber-warning)', fontWeight: 700}}>
                        ● {ch.statusText}
                      </span>
                      <span>·</span>
                      <span style={{fontFamily: 'var(--font-mono)', fontWeight: 600}}>Sync: {ch.syncLatency}</span>
                    </div>
                  </div>
                </div>

                <div className="channel-right">
                  <div className="channel-gmv">{ch.gmv}</div>
                  <div className="channel-orders">
                    {isSanocea ? `${ch.orders.toLocaleString()} events (${ch.share})` : `${ch.orders} orders (${ch.share})`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Section 5: Operational Tables ── */}
      {isSanocea ? (
        <section className="table-section" id="tables">
          <div className="table-tabs-nav">
            <button
              type="button"
              className={`table-tab-btn ${activeTableTab === 'inventory' ? 'active' : ''}`}
              onClick={() => setActiveTableTab('inventory')}
            >
              <span>🌐 Monitored Production Endpoints (Crawl Telemetry)</span>
            </button>
            <button
              type="button"
              className={`table-tab-btn ${activeTableTab === 'exceptions' ? 'active' : ''}`}
              onClick={() => setActiveTableTab('exceptions')}
            >
              <span>🛡️ Autonomous Sentinel Heartbeats & Delta Log</span>
            </button>
          </div>

          {/* Both tabs read the same persisted worker state as the SEO & Commerce Audit tab: the monitored set with its
              aggregate probe outcome, and the heartbeat ledger. No hard-coded rows or relative times. */}
          <div className="ops-table-wrap" style={{padding: 16}}>
            {!seo.overview
              ? <NotAvailable title="Sentinel state" reason={seo.status === 'loading' ? 'Reading the SEO worker’s persisted state…' : (seo.error || 'SEO worker unavailable')} />
              : activeTableTab === 'inventory'
                ? <MonitoredEndpoints overview={seo.overview} />
                : <HeartbeatsTable overview={seo.overview} />}
          </div>
        </section>
      ) : (
        <section className="table-section" id="tables">
          <div className="table-tabs-nav">
            <button
              type="button"
              className={`table-tab-btn ${activeTableTab === 'inventory' ? 'active' : ''}`}
              onClick={() => setActiveTableTab('inventory')}
            >
              <span>📦 Inventory Health & Stockout Risk</span>
            </button>
            <button
              type="button"
              className={`table-tab-btn ${activeTableTab === 'exceptions' ? 'active' : ''}`}
              onClick={() => setActiveTableTab('exceptions')}
            >
              <span>⚠️ Operational Exceptions & Audit Log</span>
            </button>

            {activeTableTab === 'inventory' && (
              <div style={{marginLeft: 'auto', display: 'flex', gap: 8}}>
                {['all', 'oos', 'low', 'healthy'].map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={`stream-filter-chip ${inventoryFilter === f ? 'active' : ''}`}
                    onClick={() => setInventoryFilter(f)}
                  >
                    {f === 'all' ? 'All SKUs' : f.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
          </div>

          {activeTableTab === 'inventory' ? (
            <div className="ops-table-wrap">
              <table className="ops-table">
                <thead>
                  <tr>
                    <th>Master SKU</th>
                    <th>Product Title</th>
                    <th>Channel & Node</th>
                    <th>Stock / Safety</th>
                    <th>Daily Velocity</th>
                    <th>Days of Cover</th>
                    <th>Revenue at Risk</th>
                    <th>Operational Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredInventory.map((item, idx) => (
                    <tr key={item.sku + idx}>
                      <td>
                        <span className="sku-code">{item.sku}</span>
                      </td>
                      <td style={{fontWeight: 800, color: 'var(--text-main)', fontSize: 15.5}}>{item.name}</td>
                      <td>
                        <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
                          {getChannelLogo(null, item.channel) && (
                            <img
                              src={getChannelLogo(null, item.channel)}
                              alt=""
                              className="channel-mini-logo"
                            />
                          )}
                          <span style={{color: 'var(--text-main)', fontWeight: 700}}>{item.channel}</span>
                        </div>
                        <div style={{fontSize: 13, color: 'var(--text-secondary)', marginTop: 2}}>{item.location}</div>
                      </td>
                      <td>
                        <strong style={{color: item.currentStock === 0 ? 'var(--red-critical)' : 'var(--text-main)', fontSize: 16}}>
                          {item.currentStock}
                        </strong>{' '}
                        <span style={{color: 'var(--text-muted)'}}>/ {item.safetyStock} min</span>
                      </td>
                      <td style={{fontFamily: 'var(--font-mono)', fontWeight: 600}}>{item.velocity}</td>
                      <td style={{fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: 15, color: String(item.daysOfCover || '').startsWith('0') ? 'var(--red-critical)' : 'var(--text-main)'}}>
                        {item.daysOfCover}
                      </td>
                      <td style={{fontFamily: 'var(--font-mono)', fontWeight: 700, color: item.riskLevel === 'oos' ? 'var(--red-critical)' : 'var(--text-secondary)'}}>
                        {item.revenueAtRisk}
                      </td>
                      <td>
                        <span className={`status-badge ${item.riskLevel}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-table-action"
                          onClick={() => onSwitchToWhatsApp()}
                          title="Manage via connected WhatsApp workflow"
                        >
                          {item.currentStock === 0 ? '⚡ Transfer' : 'Reorder'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="ops-table-wrap">
              <table className="ops-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Channel</th>
                    <th>Category</th>
                    <th>Severity</th>
                    <th>Master Ref</th>
                    <th>Operational Finding</th>
                    <th>Business Impact</th>
                    <th>Status</th>
                    <th>Resolve</th>
                  </tr>
                </thead>
                <tbody>
                  {exceptionsLog.map((exp) => (
                    <tr key={exp.id}>
                      <td style={{fontFamily: 'var(--font-mono)', color: 'var(--teal-primary)', fontWeight: 700}}>{exp.timestamp}</td>
                      <td style={{fontWeight: 700}}>
                        <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
                          {getChannelLogo(null, exp.channel) && (
                            <img
                              src={getChannelLogo(null, exp.channel)}
                              alt=""
                              className="channel-mini-logo"
                            />
                          )}
                          <span>{exp.channel}</span>
                        </div>
                      </td>
                      <td>
                        <span className="category-tag">{exp.category}</span>
                      </td>
                      <td>
                        <span className={`severity-pill ${exp.severity}`}>
                          {exp.severity}
                        </span>
                      </td>
                      <td>
                        <span className="sku-code">{exp.sku}</span>
                      </td>
                      <td style={{color: 'var(--text-main)', maxWidth: 300, fontWeight: 600, lineHeight: 1.45}}>{exp.description}</td>
                      <td style={{fontSize: 14, color: 'var(--text-secondary)'}}>{exp.impact}</td>
                      <td>
                        <span className={`status-badge ${exp.status === 'RESOLVED' ? 'optimal' : exp.status === 'ACTION_REQUIRED' ? 'critical' : 'warning'}`}>
                          {exp.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-table-action"
                          onClick={() => onSwitchToWhatsApp(exp.sku)}
                        >
                          {exp.actionLabel || 'Inspect'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
