import React, {useState} from 'react'

export default function AppHeader({
  currentTab,
  onSelectTab,
  selectedCompanyId,
  onSelectCompany,
  companies,
  pendingApprovalsCount,
  liveEventCount,
  globalStatus,
  timeframe,
  onChangeTimeframe,
  onSyncTelemetry,
  onResetDemo,
  syncing,
  onToggleMobileSidebar,
}) {
  const [searchQuery, setSearchQuery] = useState('')

  return (
    <header className="sanocea-topbar">
      {/* ── Left Area: Mobile Toggle & Segmented View Switcher ────────────────── */}
      <div className="topbar-left">
        {onToggleMobileSidebar && (
          <button
            type="button"
            className="mobile-sidebar-toggle"
            onClick={onToggleMobileSidebar}
            title="Toggle navigation sidebar"
          >
            ☰
          </button>
        )}

        <div className="topbar-breadcrumb">
          <a href="/demo.html" className="topbar-brand-link" title="SANOCEA Commerce Command Center">
            <img src="/sanocea-wordmark-navy.png" alt="SANOCEA" className="topbar-brand-logo" />
          </a>
          <span className="crumb-slash">/</span>
          <span className="crumb-current">
            {currentTab === 'dashboard'
              ? 'Commerce Command Center'
              : currentTab === 'seo-audit'
              ? 'SEO & Search Intelligence'
              : 'WhatsApp Operations'}
          </span>
        </div>

        {/* Primary View Switcher in Top Bar */}
        <div className="topbar-view-switcher" aria-label="Primary View Navigation">
          <button
            type="button"
            className={`topbar-view-btn ${currentTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => onSelectTab('dashboard')}
          >
            <span className="view-btn-icon">📊</span>
            <span>Dashboard</span>
            {pendingApprovalsCount > 0 && (
              <span className="view-badge warning">
                {pendingApprovalsCount} Action
              </span>
            )}
          </button>

          <button
            type="button"
            className={`topbar-view-btn ${currentTab === 'whatsapp' ? 'active' : ''}`}
            onClick={() => onSelectTab('whatsapp')}
          >
            <span className="view-btn-icon">💬</span>
            <span>WhatsApp Ops</span>
            <span className="view-badge teal">
              {liveEventCount} Live
            </span>
          </button>

          <button
            type="button"
            className={`topbar-view-btn ${currentTab === 'seo-audit' ? 'active' : ''}`}
            onClick={() => onSelectTab('seo-audit')}
          >
            <span className="view-btn-icon">🎯</span>
            <span>SEO & Audit</span>
            <span className="view-badge red">
              P0 Focus
            </span>
          </button>
        </div>
      </div>

      {/* ── Center: Omnibar Search Input ───────────────────────────────────── */}
      <div className="topbar-search-wrap">
        <span className="search-icon">🔍</span>
        <input
          type="text"
          className="topbar-search-input"
          placeholder="Search SKUs, dark stores, orders, exceptions..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <span className="search-hotkey">⌘K</span>
      </div>

      {/* ── Right: Timeframe, Sync, Notifications & Operator Profile ───────── */}
      <div className="topbar-right">
        {/* Timeframe Selector */}
        <div className="topbar-timeframe">
          {['Today', '7D', '30D', 'MTD'].map((tf) => (
            <button
              key={tf}
              type="button"
              className={`timeframe-btn ${timeframe === tf ? 'active' : ''}`}
              onClick={() => onChangeTimeframe(tf)}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Reset Demo Button */}
        {onResetDemo && (
          <button
            type="button"
            className="btn-reset-demo"
            onClick={onResetDemo}
            title="Reset simulation state to fresh initial baseline"
          >
            <span className="reset-icon">⟲</span>
            <span>Reset Demo</span>
          </button>
        )}

        {/* Sync Telemetry Button */}
        <button
          type="button"
          className="btn-sync-telemetry"
          onClick={onSyncTelemetry}
          title="Poll real-time connectors for state updates"
        >
          <span
            style={{
              display: 'inline-block',
              transform: syncing ? 'rotate(360deg)' : 'none',
              transition: 'transform 0.6s linear',
            }}
          >
            ⟳
          </span>
          <span>{syncing ? 'Syncing...' : 'Sync Telemetry'}</span>
        </button>

        {/* Live Indicator Pill (derived from unified globalStatus) */}
        <div
          className={`topbar-live-tag ${globalStatus && !globalStatus.isHealthy ? 'warning' : ''}`}
          title={globalStatus?.statusText || 'Connected to 4 Commerce Channels'}
        >
          <span className={globalStatus && !globalStatus.isHealthy ? 'live-dot-amber' : 'live-dot-green'} />
          <span>
            {globalStatus
              ? `${globalStatus.connectedCount}/${globalStatus.totalCount} Channels Live`
              : '4/4 Channels Live'}
          </span>
        </div>

        {/* Operator Profile Avatar */}
        <div className="topbar-profile" title="Operations Director">
          <div className="profile-avatar">MG</div>
        </div>
      </div>
    </header>
  )
}
