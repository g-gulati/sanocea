/**
 * Authoritative Operational State Store for SANOCEA Commerce OS.
 * Provides unified, bidirectional synchronization across:
 * - Dashboard (Decision Center, KPI Ribbon, Channel Matrix, Inventory Table, Exceptions Log)
 * - WhatsApp Ops (Live Stream, Bot Conversation, Quick Actions, Closed-Loop Steppers)
 * - LocalStorage persistence across page reloads
 * - Company-isolated tenant stores
 * - Site-wide demo state reset
 */

import {getCompanyOperationalData} from './data/companyData.js'

export const STORAGE_PREFIX = 'sanocea_ops_state_v2_'

export const ALL_DEMO_COMPANIES = [
  {id: 'sanocea', name: 'SANOCEA.com (Autonomous 24/7 Monitored)'},
  {id: 'premium-basket', name: 'The Premium Basket'},
  {id: 'waaree', name: 'Waaree Energies (Solar Ecommerce)'},
  {id: 'ajanta-soya', name: 'Ajanta Soya (Anchal)'},
  {id: 'golden-bird-jewels', name: 'Golden Bird Jewels'},
  {id: 'carzex', name: 'Carzex Automotive'},
]

export function initializeChannelStates(channels) {
  return (channels || []).map((ch, idx) => ({
    id: ch.id,
    name: ch.shortName || ch.name,
    fullName: ch.name,
    shortName: ch.shortName || ch.name,
    badge: ch.badge || 'Connector',
    connectionStatus: 'Connected',
    healthStatus: 'Healthy',
    lastEventSecondsAgo: [4, 8, 12, 3][idx % 4] || (idx + 1) * 3,
    lastSyncSecondsAgo: [2, 5, 8, 2][idx % 4] || (idx + 1) * 2,
    latencyMs: [42, 61, 84, 31][idx % 4] || 45,
    incomingEventCount: [142, 96, 68, 184][idx % 4] || 100,
    color: ch.color || '#00e5ff',
  }))
}

/**
 * Creates a clean, unmutated initial operational state for a company.
 */
export function getFreshInitialState(companyId) {
  const template = getCompanyOperationalData(companyId)

  // Deep clone each sub-structure to guarantee zero cross-contamination
  const rawUrgentActions = JSON.parse(JSON.stringify(template.urgentActions || []))
  const rawStreamEvents = JSON.parse(JSON.stringify(template.liveEvents || []))
  const rawInventory = JSON.parse(JSON.stringify(template.inventoryItems || []))
  const rawExceptions = JSON.parse(JSON.stringify(template.exceptionsLog || []))
  const rawKpis = JSON.parse(JSON.stringify(template.kpis || {}))
  const rawChannels = JSON.parse(JSON.stringify(template.channels || []))
  const rawChatMessages = JSON.parse(JSON.stringify(template.initialChatMessages || []))
  const rawAuditedDiscrepancies = JSON.parse(JSON.stringify(template.auditedDiscrepancies || []))
  const rawAutomationMap = JSON.parse(JSON.stringify(template.automationOpportunityMap || []))
  const rawCoverageMatrix = JSON.parse(JSON.stringify(template.automationCoverageMatrix || []))
  const rawValidationReqs = JSON.parse(JSON.stringify(template.validationRequirements || []))
  const rawEvidencePack = template.evidencePack ? JSON.parse(JSON.stringify(template.evidencePack)) : null

  const channelStates = initializeChannelStates(rawChannels)

  return {
    version: 2,
    companyId: template.companyId || companyId,
    companyName: template.companyName,
    legalName: template.legalName,
    industry: template.industry,
    currencySymbol: template.currencySymbol || '₹',
    channels: rawChannels,
    channelStates,
    urgentActions: rawUrgentActions,
    streamEvents: rawStreamEvents,
    inventoryItems: rawInventory,
    exceptionsLog: rawExceptions,
    kpis: rawKpis,
    chatMessages: rawChatMessages,
    auditedDiscrepancies: rawAuditedDiscrepancies,
    automationOpportunityMap: rawAutomationMap,
    automationCoverageMatrix: rawCoverageMatrix,
    validationRequirements: rawValidationReqs,
    evidencePack: rawEvidencePack,
    lastResetAt: new Date().toISOString(),
  }
}

/**
 * Loads operational state from localStorage or falls back to pristine template.
 */
export function loadOperationalState(companyId) {
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      const stored = window.localStorage.getItem(STORAGE_PREFIX + companyId)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (parsed && Array.isArray(parsed.urgentActions) && parsed.version === 2) {
          return parsed
        }
      }
    } catch (e) {
      console.warn('Failed to load operational state from localStorage:', e)
    }
  }
  return getFreshInitialState(companyId)
}

/**
 * Saves operational state to localStorage.
 */
export function saveOperationalState(companyId, state) {
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      window.localStorage.setItem(STORAGE_PREFIX + companyId, JSON.stringify(state))
    } catch (e) {
      console.warn('Failed to save operational state to localStorage:', e)
    }
  }
}

/**
 * Clears localStorage for a company and returns fresh state.
 */
export function resetCompanyOperationalState(companyId) {
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      window.localStorage.removeItem(STORAGE_PREFIX + companyId)
    } catch (e) {}
  }
  return getFreshInitialState(companyId)
}

/**
 * Resets all demo companies across the site.
 */
export function resetAllOperationalStates() {
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      ALL_DEMO_COMPANIES.forEach((c) => {
        window.localStorage.removeItem(STORAGE_PREFIX + c.id)
      })
    } catch (e) {}
  }
}

/**
 * Authoritative Action Resolution Transition.
 * Synchronizes:
 * 1. urgentActions -> marked resolved: true
 * 2. exceptionsLog -> marked RESOLVED
 * 3. inventoryItems -> replenished stock & health restored
 * 4. kpis -> pending count decremented, stockout risk reduced
 * 5. streamEvents -> resolution audit event prepended
 * 6. chatMessages -> button state updated and confirmation appended
 */
export function resolveOperationalAction(currentState, actionIdOrKey, options = {}) {
  // Deep clone current state to keep transitions pure and deterministic
  const state = JSON.parse(JSON.stringify(currentState))

  const targetIndex = state.urgentActions.findIndex(
    (a) =>
      a.id === actionIdOrKey ||
      a.ref === actionIdOrKey ||
      a.sku === actionIdOrKey ||
      (a.actionKind && a.actionKind === actionIdOrKey)
  )

  if (targetIndex === -1) {
    return state
  }

  const action = state.urgentActions[targetIndex]
  if (action.resolved) {
    return state // Already resolved
  }

  // 1. Mark urgent action resolved
  action.resolved = true
  action.resolvedAt = new Date().toISOString()
  action.resolutionAuditId =
    action.resolutionAuditId || `SAN-AUD-${Math.floor(10000 + Math.random() * 90000)}`

  // 2. Synchronize exceptions log
  if (state.exceptionsLog && state.exceptionsLog.length > 0) {
    state.exceptionsLog = state.exceptionsLog.map((exp) => {
      if (
        (action.sku && exp.sku && exp.sku.includes(action.sku)) ||
        (action.channel && exp.channel === action.channel) ||
        (action.category && exp.category === action.category)
      ) {
        return {
          ...exp,
          status: 'RESOLVED',
          impact: 'Exception resolved by operator approval. Telemetry synced.',
        }
      }
      return exp
    })
  }

  // 3. Synchronize inventory items (e.g. stock transfer for BBQ Almonds)
  if (state.inventoryItems && state.inventoryItems.length > 0) {
    state.inventoryItems = state.inventoryItems.map((item) => {
      const matchSku = action.sku && item.sku && (item.sku === action.sku || item.sku.includes(action.sku))
      const matchName = action.title && item.name && action.title.toLowerCase().includes(item.name.toLowerCase().slice(0, 10))

      if (
        matchSku ||
        matchName ||
        (action.actionKind === 'approve-transfer' && item.riskLevel === 'oos') ||
        (action.actionKind === 'correct-availability-feed' && item.status === 'OOS')
      ) {
        const addedUnits = action.units || (action.actionKind === 'correct-availability-feed' ? 0 : 120)
        return {
          ...item,
          currentStock: (item.currentStock || 0) + addedUnits,
          status: 'OPTIMAL',
          riskLevel: 'healthy',
          daysOfCover: action.actionKind === 'correct-availability-feed' ? 'Feed Corrected' : '14.0 days',
          revenueAtRisk: '₹0',
        }
      }
      return item
    })
  }

  // 4. Synchronize KPIs
  const remainingPending = state.urgentActions.filter((a) => !a.resolved).length
  const oosCount = (state.inventoryItems || []).filter(
    (i) => i.status === 'OOS' || i.riskLevel === 'oos'
  ).length
  const lowCount = (state.inventoryItems || []).filter(
    (i) => i.riskLevel === 'critical' || i.riskLevel === 'warning'
  ).length

  if (state.kpis) {
    state.kpis.pendingApprovalsCount = remainingPending
    state.kpis.pendingApprovalsLabel =
      remainingPending === 0
        ? 'All operational approvals completed'
        : `${remainingPending} pending approval`
    state.kpis.inventoryHealth = `${oosCount} OOS · ${lowCount} Low Stock`
    state.kpis.stockoutRisk = oosCount === 0 ? '₹0 GMV at risk' : '₹28,000 GMV at risk'
  }

  // 5. Prepend event to Live Operational Stream
  const nowStr = new Date().toTimeString().split(' ')[0]
  const resolutionEvent = {
    id: `ev-res-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    time: nowStr,
    channel: action.channel,
    type: 'Operator approval executed',
    headline: `✓ ${action.actionLabel} completed`,
    detail: `${action.resolutionText || 'Operational action dispatched.'} Audit #${action.resolutionAuditId} verified.`,
    badge: 'Resolved',
    badgeColor: '#10b981',
  }
  state.streamEvents = [resolutionEvent, ...(state.streamEvents || []).slice(0, 24)]

  // 6. Synchronize WhatsApp Chat Conversation
  // (a) Update buttons inside existing messages to show executed checkmark
  if (state.chatMessages && state.chatMessages.length > 0) {
    state.chatMessages = state.chatMessages.map((msg) => {
      if (msg.quickActions && msg.quickActions.length > 0) {
        const updatedQa = msg.quickActions.map((qa) => {
          if (qa.actionKey === action.id || qa.id === action.id) {
            return {
              ...qa,
              label: `✓ ${action.actionLabel} (Executed)`,
              disabled: true,
              executed: true,
            }
          }
          return qa
        })
        return {...msg, quickActions: updatedQa}
      }
      return msg
    })
  }

  // (b) If resolved from Dashboard, append a sync confirmation into WhatsApp chat
  if (options.source === 'dashboard') {
    const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
    const syncMsg = {
      id: `dash-sync-${Date.now()}`,
      from: 'sanocea',
      time: timeStr,
      text: `⚡ *Operations Command Center Sync:*
Operator executed: *${action.actionLabel}* (${action.channel})
• Action Status: *RESOLVED & CONNECTOR ACKNOWLEDGED*
• Execution Receipt: ${action.resolutionText || 'Dispatched payload.'}
• Audit Log: *#${action.resolutionAuditId}*
• Remaining pending decisions: *${remainingPending}*`,
    }
    state.chatMessages = [...(state.chatMessages || []), syncMsg]
  }

  return state
}

/**
 * Reconnect a degraded channel (e.g. Amazon SP-API latency spike).
 */
export function reconnectChannelInState(currentState, channelId = 'amazon') {
  const state = JSON.parse(JSON.stringify(currentState))

  state.channelStates = (state.channelStates || []).map((ch) => {
    if (ch.id === channelId || ch.shortName.toLowerCase().includes(channelId)) {
      return {
        ...ch,
        connectionStatus: 'Connected',
        healthStatus: 'Healthy',
        latencyMs: 48,
        lastEventSecondsAgo: 2,
        lastSyncSecondsAgo: 1,
      }
    }
    return ch
  })

  // Resolve any degradation urgent action
  state.urgentActions = (state.urgentActions || []).map((act) => {
    if (act.actionKind === 'reconnect-channel' || act.id.startsWith('act-deg-')) {
      return {...act, resolved: true}
    }
    return act
  })

  // Prepend recovery event
  const nowStr = new Date().toTimeString().split(' ')[0]
  const recEvent = {
    id: `ev-rec-${Date.now()}`,
    time: nowStr,
    channel: 'Operations Engine',
    type: 'Connector restored',
    headline: 'Connector re-established · Latency normalized to 48ms',
    detail: 'SP-API token handshake re-verified. Ingress normal across all channels.',
    badge: 'Restored',
    badgeColor: '#10b981',
  }
  state.streamEvents = [recEvent, ...(state.streamEvents || []).slice(0, 24)]

  return state
}

/**
 * Simulate degradation on a channel.
 */
export function degradeChannelInState(currentState, channelId = 'amazon') {
  const state = JSON.parse(JSON.stringify(currentState))
  const targetChannel =
    state.channelStates.find((c) => c.id === channelId) || state.channelStates[0]

  if (!targetChannel) return state

  state.channelStates = state.channelStates.map((ch) => {
    if (ch.id === targetChannel.id) {
      return {
        ...ch,
        connectionStatus: 'Degraded',
        healthStatus: 'Degraded',
        latencyMs: 1840,
        lastEventSecondsAgo: 222,
      }
    }
    return ch
  })

  const degradeAction = {
    id: `act-deg-${targetChannel.id}`,
    ref: 'SYS-CONN-01',
    channel: targetChannel.name,
    channelId: targetChannel.id,
    category: 'Connectivity',
    severity: 'critical',
    title: `${targetChannel.name} connection degraded · Last event 3m 42s ago`,
    description: `${targetChannel.fullName || targetChannel.name} webhook reporting 1,840ms latency. Action required to prevent catalog sync halt.`,
    recommendation: `Restart ${targetChannel.name} connector worker and re-verify SP-API token handshake.`,
    actionLabel: `Reconnect ${targetChannel.name}`,
    actionKind: 'reconnect-channel',
    resolved: false,
    resolutionText: `${targetChannel.name} connector re-established. Latency normalized to 48ms.`,
  }

  state.urgentActions = [degradeAction, ...state.urgentActions.filter((a) => a.id !== degradeAction.id)]

  const nowStr = new Date().toTimeString().split(' ')[0]
  const degradeEvent = {
    id: `ev-deg-${Date.now()}`,
    time: nowStr,
    channel: targetChannel.name,
    type: 'Latency anomaly detected',
    headline: `⚠️ ${targetChannel.name} response timeout (1,840 ms)`,
    detail: 'Connector worker entered degraded retry queue.',
    badge: 'Latency Alert',
    badgeColor: '#f59e0b',
  }
  state.streamEvents = [degradeEvent, ...(state.streamEvents || []).slice(0, 24)]

  return state
}
