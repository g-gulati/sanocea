import React, {useState, useEffect, useCallback, useMemo} from 'react'
import {createRoot} from 'react-dom/client'
import './commerceOps.css'
import AppSidebar from './components/AppSidebar.jsx'
import AppHeader from './components/AppHeader.jsx'
import DashboardView from './components/DashboardView.jsx'
import WhatsAppView from './components/WhatsAppView.jsx'
import SeoAuditSection from './components/SeoAuditSection.jsx'
import {getCompanyOperationalData} from './data/companyData.js'
import {
  ALL_DEMO_COMPANIES,
  loadOperationalState,
  saveOperationalState,
  resetCompanyOperationalState,
  resolveOperationalAction,
  reconnectChannelInState,
  degradeChannelInState,
} from './operationalStore.js'

function getInitialCompanyId() {
  try {
    const params = new URLSearchParams(window.location.search)
    const company = params.get('company')
    if (company && getCompanyOperationalData(company)) {
      return company
    }
  } catch {}
  return 'premium-basket'
}

function getInitialTab() {
  try {
    const params = new URLSearchParams(window.location.search)
    const tab = params.get('tab') || params.get('view')
    if (tab === 'whatsapp' || tab === 'whatsapp-ops' || tab === 'chat') return 'whatsapp'
    if (tab === 'seo-audit' || tab === 'audit' || tab === 'seo') return 'seo-audit'
    if (tab === 'dashboard') return 'dashboard'
  } catch {}
  return 'dashboard' // Default to main operations command center
}

function SanoceaOperationsApp() {
  const [currentTab, setCurrentTab] = useState(getInitialTab)
  const [companyId, setCompanyId] = useState(getInitialCompanyId)
  const [activeTableTab, setActiveTableTab] = useState('inventory') // 'inventory' | 'exceptions'
  const [timeframe, setTimeframe] = useState('MTD')
  const [syncing, setSyncing] = useState(false)
  const [toastMessage, setToastMessage] = useState(null)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  // Single authoritative operational state loaded from localStorage or pristine initial baseline
  const [opsState, setOpsState] = useState(() => loadOperationalState(companyId))

  // When companyId changes, load that company's isolated operational state
  useEffect(() => {
    setOpsState(loadOperationalState(companyId))
  }, [companyId])

  // Real-time live seconds ticker for Channel Connectivity (genuinely live!)
  useEffect(() => {
    const ticker = setInterval(() => {
      setOpsState((prev) => ({
        ...prev,
        channelStates: (prev.channelStates || []).map((ch) => ({
          ...ch,
          lastEventSecondsAgo: (ch.lastEventSecondsAgo || 0) + 1,
          lastSyncSecondsAgo: (ch.lastSyncSecondsAgo || 0) + 1,
        })),
      }))
    }, 1000)
    return () => clearInterval(ticker)
  }, [])

  // Sync URL query params without reloading
  useEffect(() => {
    try {
      const url = new URL(window.location.href)
      url.searchParams.set('company', companyId)
      url.searchParams.set('tab', currentTab)
      window.history.replaceState({}, '', url.toString())
    } catch {}
  }, [companyId, currentTab])

  // Toast auto-clear
  useEffect(() => {
    if (!toastMessage) return
    const timer = setTimeout(() => setToastMessage(null), 3800)
    return () => clearTimeout(timer)
  }, [toastMessage])

  // Derive dynamic companyData containing live operational updates across inventory, exceptions, kpis
  const companyData = useMemo(() => {
    const base = getCompanyOperationalData(companyId)
    return {
      ...base,
      urgentActions: opsState.urgentActions,
      liveEvents: opsState.streamEvents,
      inventoryItems: opsState.inventoryItems,
      exceptionsLog: opsState.exceptionsLog,
      kpis: opsState.kpis,
      channels: opsState.channels,
      initialChatMessages: opsState.chatMessages,
    }
  }, [companyId, opsState])

  // Compute Global Connectivity Status derived from live channel states
  const globalStatus = useMemo(() => {
    const channelStates = opsState.channelStates || []
    const totalCount = channelStates.length
    const connectedCount = channelStates.filter(
      (c) => c.connectionStatus === 'Connected' && c.healthStatus === 'Healthy'
    ).length
    const degradedChannel = channelStates.find(
      (c) => c.healthStatus !== 'Healthy' || c.connectionStatus !== 'Connected'
    )

    return {
      connectedCount,
      totalCount,
      isHealthy: !degradedChannel,
      degradedChannel,
      statusText: !degradedChannel
        ? '● All systems connected'
        : `● ${connectedCount} / ${totalCount} channels connected · ${degradedChannel.name} connection degraded`,
    }
  }, [opsState.channelStates])

  // Update chat messages from WhatsApp conversation and persist
  const handleUpdateChatMessages = useCallback((updater) => {
    setOpsState((prev) => {
      const current = prev.chatMessages || []
      const nextMessages = typeof updater === 'function' ? updater(current) : updater
      const updated = {
        ...prev,
        chatMessages: nextMessages,
      }
      saveOperationalState(companyId, updated)
      return updated
    })
  }, [companyId])

  // Reset simulation state across entire application
  const handleResetDemo = useCallback((options = {}) => {
    const fresh = resetCompanyOperationalState(companyId)
    if (options.fromWhatsApp && options.replyText) {
      const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
      fresh.chatMessages = [
        ...fresh.chatMessages,
        {
          id: `usr-reset-${Date.now()}`,
          from: 'user',
          time: timeStr,
          text: 'reset',
        },
        {
          id: `bot-reset-${Date.now()}`,
          from: 'sanocea',
          time: timeStr,
          text: options.replyText,
          quickActions: [
            { id: 'menu-qa-1', label: '1️⃣ What Needs Attention?', replyText: '1' },
            { id: 'menu-qa-2', label: '2️⃣ Channel Connectivity', replyText: '2' },
            { id: 'menu-qa-3', label: '3️⃣ Inventory Health', replyText: '3' },
            { id: 'menu-qa-4', label: '4️⃣ Channel GMV', replyText: '4' },
          ],
        },
      ]
    }
    saveOperationalState(companyId, fresh)
    setOpsState(fresh)
    setToastMessage(`⟲ Demo Reset: Operational state restored for ${fresh.companyName}.`)
  }, [companyId])

  // Reconnect a degraded channel
  const handleReconnectChannel = useCallback((channelId = 'amazon') => {
    setOpsState((prev) => {
      const updated = reconnectChannelInState(prev, channelId)
      saveOperationalState(companyId, updated)
      return updated
    })
    setToastMessage(`🟢 Telemetry Restored: All channel connectors reporting Healthy.`)
  }, [companyId])

  // Simulate Channel Degradation (e.g. Amazon SP-API latency spike)
  const handleSimulateDegrade = useCallback(() => {
    setOpsState((prev) => {
      const updated = degradeChannelInState(prev, 'amazon')
      saveOperationalState(companyId, updated)
      return updated
    })
    setToastMessage(`⚠️ Telemetry Alert: Amazon India connection degraded · Generated Action Required exception!`)
  }, [companyId])

  // Resolve action handler (called from either Dashboard or WhatsApp)
  const handleResolveAction = useCallback((actionIdOrKey, options = {}) => {
    if (actionIdOrKey === 'act-deg-amazon' || actionIdOrKey === 'SYS-CONN-01') {
      handleReconnectChannel('amazon')
      return
    }

    let resolvedLabel = 'Operational action'

    setOpsState((prev) => {
      const target = (prev.urgentActions || []).find(
        (a) => a.id === actionIdOrKey || a.ref === actionIdOrKey || a.sku === actionIdOrKey
      )
      if (target) {
        resolvedLabel = target.actionLabel
      }
      const updated = resolveOperationalAction(prev, actionIdOrKey, options)
      saveOperationalState(companyId, updated)
      return updated
    })

    setToastMessage(`⚡ Operations Engine: ${resolvedLabel} executed & synchronized!`)
  }, [companyId, handleReconnectChannel])

  // Add event to live stream
  const handleAddStreamEvent = useCallback((newEvent) => {
    setOpsState((prev) => {
      const updatedEvents = [newEvent, ...(prev.streamEvents || []).slice(0, 23)]
      let updatedChannels = prev.channelStates || []
      if (newEvent.channel) {
        updatedChannels = updatedChannels.map((ch) => {
          if (
            ch.name.toLowerCase().includes(newEvent.channel.toLowerCase()) ||
            newEvent.channel.toLowerCase().includes(ch.id)
          ) {
            return {
              ...ch,
              lastEventSecondsAgo: 1,
              lastSyncSecondsAgo: 1,
              incomingEventCount: (ch.incomingEventCount || 0) + 1,
            }
          }
          return ch
        })
      }
      const next = {
        ...prev,
        streamEvents: updatedEvents,
        channelStates: updatedChannels,
      }
      return next
    })
  }, [])

  // Sync Telemetry button handler
  const handleSyncTelemetry = () => {
    setSyncing(true)
    setTimeout(() => {
      setSyncing(false)
      const nowStr = new Date().toTimeString().split(' ')[0]
      const syncEvent = {
        id: `sync-${Date.now()}`,
        time: nowStr,
        channel: 'Operations Engine',
        type: 'Telemetry health check',
        headline: 'Connector health verified (4/4 channels active)',
        detail: 'Blinkit, Shopify, Swiggy, and Amazon polling latencies verified within <1.5s tolerance.',
        badge: 'System Sync',
        badgeColor: '#00e5ff',
      }
      setOpsState((prev) => {
        const next = {
          ...prev,
          streamEvents: [syncEvent, ...(prev.streamEvents || []).slice(0, 23)],
          channelStates: (prev.channelStates || []).map((ch) => ({
            ...ch,
            lastSyncSecondsAgo: 1,
          })),
        }
        saveOperationalState(companyId, next)
        return next
      })
      setToastMessage('⟳ Telemetry sync complete: All channel connectors reporting normal.')
    }, 600)
  }

  // Module quick jumps from sidebar
  const handleNavigateModule = useCallback((moduleName) => {
    setMobileSidebarOpen(false)
    if (currentTab !== 'dashboard') {
      setCurrentTab('dashboard')
    }

    if (moduleName === 'inventory') {
      setActiveTableTab('inventory')
    } else if (moduleName === 'exceptions') {
      setActiveTableTab('exceptions')
    }

    setTimeout(() => {
      const targetId = moduleName === 'channels' ? 'channels' : moduleName === 'decisions' ? 'decisions' : 'tables'
      const target = document.getElementById(targetId)
      if (target) {
        target.scrollIntoView({behavior: 'smooth', block: 'start'})
      }
    }, 120)
  }, [currentTab])

  const pendingApprovalsCount = (opsState.urgentActions || []).filter((a) => !a.resolved).length
  const liveEventCount = (opsState.streamEvents || []).length

  return (
    <div className="sanocea-app-shell">
      {/* ── Left Navigation Sidebar (Authentic Behance / Nexino Admin Shell) ── */}
      <AppSidebar
        currentTab={currentTab}
        onSelectTab={(tab) => {
          setCurrentTab(tab)
          setMobileSidebarOpen(false)
        }}
        selectedCompanyId={companyId}
        onSelectCompany={setCompanyId}
        companies={ALL_DEMO_COMPANIES}
        pendingApprovalsCount={pendingApprovalsCount}
        liveEventCount={liveEventCount}
        globalStatus={globalStatus}
        onNavigateModule={handleNavigateModule}
        onResetDemo={() => handleResetDemo()}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        onScrollToSection={(sectionId) => {
          setMobileSidebarOpen(false)
          const target = document.getElementById(sectionId)
          if (target) {
            target.scrollIntoView({behavior: 'smooth', block: 'start'})
          }
        }}
      />

      {/* ── Main Content Column ────────────────────────────────────────────── */}
      <div className="sanocea-main-wrapper">
        {/* ── Topbar (Search, Tab Switcher, Timeframe, Sync, Reset, Profile) ───── */}
        <AppHeader
          currentTab={currentTab}
          onSelectTab={setCurrentTab}
          selectedCompanyId={companyId}
          onSelectCompany={setCompanyId}
          companies={ALL_DEMO_COMPANIES}
          pendingApprovalsCount={pendingApprovalsCount}
          liveEventCount={liveEventCount}
          globalStatus={globalStatus}
          timeframe={timeframe}
          onChangeTimeframe={setTimeframe}
          onSyncTelemetry={handleSyncTelemetry}
          onResetDemo={() => handleResetDemo()}
          syncing={syncing}
          onToggleMobileSidebar={() => setMobileSidebarOpen((prev) => !prev)}
        />

        {/* ── Toast Synchronization Banner ──────────────────────────────────── */}
        {toastMessage && (
          <div
            style={{
              position: 'fixed',
              bottom: 24,
              right: 24,
              background: '#FFFFFF',
              color: '#17191C',
              border: '1px solid #E7E9ED',
              borderRadius: 12,
              padding: '14px 24px',
              fontSize: 15,
              fontWeight: 600,
              boxShadow: '0 12px 32px -4px rgba(16, 24, 40, 0.12), 0 4px 12px -2px rgba(16, 24, 40, 0.06)',
              zIndex: 999,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <span style={{color: 'var(--teal-primary)', fontSize: 16}}>●</span>
            <span>{toastMessage}</span>
          </div>
        )}

        {/* ── Main Application Content ───────────────────────────────────────── */}
        <main className="app-main">
          {currentTab === 'dashboard' ? (
            <DashboardView
              companyData={companyData}
              urgentActions={opsState.urgentActions || []}
              onResolveAction={(actionId) => handleResolveAction(actionId, { source: 'dashboard' })}
              onSwitchToWhatsApp={() => setCurrentTab('whatsapp')}
              channelStates={opsState.channelStates || []}
              globalStatus={globalStatus}
              onSimulateDegrade={handleSimulateDegrade}
              onReconnectChannel={handleReconnectChannel}
              activeTableTab={activeTableTab}
              onChangeTableTab={setActiveTableTab}
            />
          ) : currentTab === 'seo-audit' ? (
            <div style={{padding: '0 4px'}}>
              <SeoAuditSection
                key={companyData?.companyId || 'company'}
                companyData={companyData}
                onBackToDashboard={() => setCurrentTab('dashboard')}
                onSwitchToWhatsApp={(contextKey) => {
                  setCurrentTab('whatsapp')
                }}
                onResolveAction={(actionId) => handleResolveAction(actionId, { source: 'seo-audit' })}
              />
            </div>
          ) : (
            <WhatsAppView
              companyData={companyData}
              urgentActions={opsState.urgentActions || []}
              onResolveAction={(actionId) => handleResolveAction(actionId, { source: 'whatsapp' })}
              onSwitchToDashboard={() => setCurrentTab('dashboard')}
              streamEvents={opsState.streamEvents || []}
              onAddStreamEvent={handleAddStreamEvent}
              channelStates={opsState.channelStates || []}
              globalStatus={globalStatus}
              onReconnectChannel={handleReconnectChannel}
              chatMessages={opsState.chatMessages || []}
              onUpdateChatMessages={handleUpdateChatMessages}
              onResetDemo={handleResetDemo}
            />
          )}
        </main>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <SanoceaOperationsApp />
  </React.StrictMode>
)
