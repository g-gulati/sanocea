import React from 'react'

export default function AppSidebar({
  currentTab,
  onSelectTab,
  selectedCompanyId,
  onSelectCompany,
  companies,
  pendingApprovalsCount,
  liveEventCount,
  globalStatus,
  onNavigateModule,
  onScrollToSection,
  onResetDemo,
  mobileOpen = false,
  onCloseMobile,
}) {
  const currentCompany = companies.find((c) => c.id === selectedCompanyId) || companies[0]

  const handleModuleClick = (moduleName) => {
    if (onNavigateModule) {
      onNavigateModule(moduleName)
    } else {
      if (moduleName === 'seo-audit') {
        if (onSelectTab) onSelectTab('seo-audit')
        return
      }
      if (currentTab !== 'dashboard') onSelectTab('dashboard')
      const targetId = moduleName === 'channels' ? 'channels' : moduleName === 'decisions' ? 'decisions' : 'tables'
      if (onScrollToSection) onScrollToSection(targetId)
    }
  }

  return (
    <>
      {mobileOpen && (
        <div
          className="sanocea-sidebar-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}
      <aside className={`sanocea-sidebar ${mobileOpen ? 'mobile-open' : ''}`} aria-label="Application Sidebar Navigation">
        {/* ── Brand Header ────────────────────────────────────────────────────── */}
        <div className="sidebar-brand">
          <a href="/demo.html" className="sidebar-logo-link" title="SANOCEA Commerce Command Center">
            <img src="/sanocea-wordmark-navy.png" alt="SANOCEA" className="sidebar-logo" />
            <span className="sidebar-brand-badge">OPERATIONS OS</span>
          </a>
          {onCloseMobile && (
            <button
              type="button"
              className="sidebar-close-mobile-btn"
              onClick={onCloseMobile}
              aria-label="Close sidebar"
            >
              ✕
            </button>
          )}
        </div>

      {/* ── Primary View Switcher Section ──────────────────────────────────── */}
      <div className="sidebar-nav-group">
        <div className="sidebar-group-title">COMMAND VIEWS</div>
        <nav className="sidebar-menu">
          <button
            type="button"
            className={`sidebar-nav-item ${currentTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => onSelectTab('dashboard')}
          >
            <span className="sidebar-item-icon">📊</span>
            <span className="sidebar-item-label">Dashboard</span>
            {pendingApprovalsCount > 0 && (
              <span className="sidebar-badge warning" title="Pending operational decisions">
                {pendingApprovalsCount}
              </span>
            )}
          </button>

          <button
            type="button"
            className={`sidebar-nav-item ${currentTab === 'whatsapp' ? 'active' : ''}`}
            onClick={() => onSelectTab('whatsapp')}
          >
            <span className="sidebar-item-icon">💬</span>
            <span className="sidebar-item-label">WhatsApp Ops</span>
            <span className="sidebar-badge teal" title="Incoming operational event stream">
              {liveEventCount} Live
            </span>
          </button>

          <button
            type="button"
            className={`sidebar-nav-item ${currentTab === 'seo-audit' ? 'active' : ''}`}
            onClick={() => onSelectTab('seo-audit')}
          >
            <span className="sidebar-item-icon">🎯</span>
            <span className="sidebar-item-label">SEO & Commerce Audit</span>
            <span className="sidebar-badge red" title="High-priority commercial revenue protections">
              P0 Focus
            </span>
          </button>
        </nav>
      </div>

      {/* ── Operational Modules / Quick Jumps ──────────────────────────────── */}
      <div className="sidebar-nav-group">
        <div className="sidebar-group-title">COMMERCE MODULES</div>
        <nav className="sidebar-menu">
          <button
            type="button"
            className="sidebar-nav-item secondary"
            onClick={() => handleModuleClick('channels')}
          >
            <span className="sidebar-item-icon">🌐</span>
            <span className="sidebar-item-label">Connected Channels</span>
            <span className={`sidebar-mini-status ${globalStatus && !globalStatus.isHealthy ? 'amber' : 'green'}`}>
              ● {globalStatus ? `${globalStatus.connectedCount}/${globalStatus.totalCount} Live` : '4/4 Live'}
            </span>
          </button>

          <button
            type="button"
            className="sidebar-nav-item secondary"
            onClick={() => handleModuleClick('decisions')}
          >
            <span className="sidebar-item-icon">⚡</span>
            <span className="sidebar-item-label">Decision Center</span>
            {pendingApprovalsCount > 0 && (
              <span className="sidebar-badge red">{pendingApprovalsCount} Urgent</span>
            )}
          </button>

          <button
            type="button"
            className="sidebar-nav-item secondary"
            onClick={() => handleModuleClick('inventory')}
          >
            <span className="sidebar-item-icon">📦</span>
            <span className="sidebar-item-label">Inventory Health</span>
          </button>

          <button
            type="button"
            className="sidebar-nav-item secondary"
            onClick={() => handleModuleClick('exceptions')}
          >
            <span className="sidebar-item-icon">⚠️</span>
            <span className="sidebar-item-label">Exceptions & Audit</span>
          </button>
        </nav>
      </div>

      {/* ── Sidebar Footer: Tenant Switcher & Engine Status ─────────────────── */}
      <div className="sidebar-footer">
        <div className="sidebar-tenant-card">
          <div className="tenant-card-header">
            <span className="tenant-label">CONNECTED MERCHANT</span>
            <span className="tenant-status-dot" />
          </div>
          <div className="tenant-select-wrapper">
            <select
              className="sidebar-tenant-select"
              value={selectedCompanyId}
              onChange={(e) => onSelectCompany(e.target.value)}
              title="Switch demo prospect"
            >
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <span className="tenant-chevron">▾</span>
          </div>
        </div>

        {onResetDemo && (
          <button
            type="button"
            className="sidebar-reset-btn"
            onClick={onResetDemo}
            title="Reset simulation state across all commerce modules"
          >
            <span className="sidebar-reset-icon">⟲</span>
            <span>Reset Simulation State</span>
          </button>
        )}

        <div className="sidebar-engine-pill">
          <span className="engine-pulse-dot" />
          <span className="engine-text">Engine: Live Ingress · 42ms</span>
        </div>
      </div>
    </aside>
  </>
  )
}
