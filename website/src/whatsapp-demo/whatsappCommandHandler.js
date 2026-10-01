/**
 * Shared WhatsApp Command & Menu Interaction Handler for SANOCEA Commerce OS.
 * Standardized across all merchant/company environments (The Premium Basket,
 * Ajanta Soya, Golden Bird Jewels, Carzex Automotive, and all future tenants).
 */

import {getSeoAuditData} from './data/seoAuditData.js'

export const WHATSAPP_MENU_TEXT = `SANOCEA Commerce OS
What would you like to do?
1. What needs my attention?
2. Show channel connectivity
3. Show inventory health
4. Show channel GMV breakdown
Reply with 1–4`

export const WHATSAPP_MENU_OPTIONS = [
  { number: 1, key: 'attention', label: '1. What needs my attention?' },
  { number: 2, key: 'connectivity', label: '2. Show channel connectivity' },
  { number: 3, key: 'inventory', label: '3. Show inventory health' },
  { number: 4, key: 'gmv', label: '4. Show channel GMV breakdown' },
]

/**
 * Parses user input to extract a numeric selection (1–4) if present.
 * Supports: "1", "1.", "option 1", "#1", "1️⃣", "one", etc.
 */
export function parseNumericChoice(input) {
  if (input === null || input === undefined) return null
  const trimmed = String(input).trim()

  // Single digit matching: 1, 2, 3, 4, "1.", "#1", "option 1", "(1)", "[1]"
  const match = trimmed.match(/^(?:option\s*|#|\(|\[)?([1-4])(?:\.|\)|\])?$/i)
  if (match) {
    return parseInt(match[1], 10)
  }

  // Emojis
  if (trimmed.includes('1️⃣')) return 1
  if (trimmed.includes('2️⃣')) return 2
  if (trimmed.includes('3️⃣')) return 3
  if (trimmed.includes('4️⃣')) return 4

  // Words
  const lower = trimmed.toLowerCase()
  if (lower === 'one') return 1
  if (lower === 'two') return 2
  if (lower === 'three') return 3
  if (lower === 'four') return 4

  return null
}

/**
 * Checks if the input is explicitly requesting the menu.
 * Handles "menu", "Menu", "MENU", "help", "options", "0", etc.
 */
export function isMenuCommand(input) {
  if (!input) return false
  const lower = String(input).trim().toLowerCase()
  return (
    lower === 'menu' ||
    lower === 'help' ||
    lower === 'options' ||
    lower === '0' ||
    lower === '#menu' ||
    lower === '/menu' ||
    lower === 'start'
  )
}

/**
 * Checks if the input is requesting a full demo reset.
 */
export function isResetCommand(input) {
  if (!input) return false
  const lower = String(input).trim().toLowerCase()
  return (
    lower === 'reset' ||
    lower === 'reset demo' ||
    lower === 'reset simulation' ||
    lower === 'restart' ||
    lower === 'clear'
  )
}

/**
 * Core command processor.
 * Given user input and operational context, returns:
 * {
 *   intent: 'menu' | 'attention' | 'connectivity' | 'inventory' | 'gmv' | 'approval' | 'reset' | 'unknown',
 *   reply: string,
 *   quickActions?: Array<{ id: string, label: string, actionKey?: string, replyText?: string }>,
 *   executionAction?: object,
 *   shouldReset?: boolean
 * }
 */
export function processWhatsAppCommand(input, context = {}) {
  const {
    companyData = {},
    urgentActions = [],
    channelStates = [],
    globalStatus = null,
  } = context

  const raw = String(input || '').trim()
  const lower = raw.toLowerCase()
  const choice = parseNumericChoice(raw)

  // 0. Reset Demo Command ("reset", "reset demo")
  if (isResetCommand(raw)) {
    return {
      intent: 'reset',
      shouldReset: true,
      reply: `⟲ *Demo Environment Reset Complete:*\nAll operational decisions, inventory buffers, telemetry latencies, and WhatsApp history have been restored to initial seeded state for ${companyData.companyName || 'your business'}.\n\nType *menu* to view available commands.`,
      quickActions: [
        { id: 'menu-qa-1', label: '1️⃣ What Needs Attention?', replyText: '1' },
        { id: 'menu-qa-2', label: '2️⃣ Channel Connectivity', replyText: '2' },
        { id: 'menu-qa-3', label: '3️⃣ Inventory Health', replyText: '3' },
        { id: 'menu-qa-4', label: '4️⃣ Channel GMV', replyText: '4' },
      ],
    }
  }

  // 1. Menu Command ("menu", "Menu", "MENU", etc.)
  if (isMenuCommand(raw)) {
    return {
      intent: 'menu',
      reply: WHATSAPP_MENU_TEXT,
      quickActions: [
        { id: 'menu-qa-1', label: '1️⃣ What Needs Attention?', replyText: '1' },
        { id: 'menu-qa-2', label: '2️⃣ Channel Connectivity', replyText: '2' },
        { id: 'menu-qa-3', label: '3️⃣ Inventory Health', replyText: '3' },
        { id: 'menu-qa-4', label: '4️⃣ Channel GMV', replyText: '4' },
      ],
    }
  }

  // 2. Option 1: What needs my attention?
  if (
    choice === 1 ||
    lower.includes('attention') ||
    lower.includes('wrong') ||
    lower.includes('issue') ||
    lower.includes('urgent') ||
    lower.includes('exception')
  ) {
    const pending = (urgentActions || []).filter((a) => !a.resolved)
    if (pending.length === 0) {
      return {
        intent: 'attention',
        reply: `🟢 *All Clear:* All urgent operational exceptions have been resolved for ${companyData.companyName || 'your business'}. Continuous telemetry monitoring active across ${companyData.channels?.length || 4} channels.\n\nType *menu* for more options.`,
        quickActions: [
          { id: 'btn-menu-back', label: '📋 View Menu', replyText: 'menu' },
          { id: 'btn-conn-jump', label: '🌐 Channel Connectivity', replyText: '2' },
        ],
      }
    }

    const text =
      `⚠️ *Operational Exceptions Needing Attention (${pending.length}) — ${companyData.companyName || 'Commerce Operations'}:*\n\n` +
      pending
        .map(
          (p, i) =>
            `${i + 1}️⃣ ${p.evidenceClass ? `*${p.evidenceClass}* · ` : ''}*${p.channel}:* ${p.title}\n→ ${p.recommendation || p.description}`
        )
        .join('\n\n') +
      `\n\nType *menu* for more options.`

    return {
      intent: 'attention',
      reply: text,
      quickActions: pending.map((p) => ({
        id: `qa-${p.id}`,
        label: `⚡ ${p.actionLabel || 'Approve Action'}`,
        actionKey: p.id,
        actionKind: p.actionKind,
      })),
    }
  }

  // 3. Option 2: Show channel connectivity
  if (
    choice === 2 ||
    lower.includes('connect') ||
    lower.includes('channel') ||
    lower.includes('status') ||
    lower.includes('latency') ||
    lower.includes('telemetry')
  ) {
    const channels =
      channelStates && channelStates.length > 0
        ? channelStates
        : (companyData.channels || []).map((ch, idx) => ({
            name: ch.shortName || ch.name,
            connectionStatus: 'Connected',
            healthStatus: 'Healthy',
            latencyMs: 42,
            lastEventSecondsAgo: (idx + 1) * 3,
            incomingEventCount: 120,
          }))

    const listStr = channels
      .map(
        (ch) =>
          `${ch.healthStatus === 'Healthy' ? '🟢' : '🟡'} *${ch.name}:* ${ch.connectionStatus} (${ch.latencyMs}ms · Last event ${ch.lastEventSecondsAgo}s ago · ${ch.incomingEventCount} events today)`
      )
      .join('\n')

    const connectedCount =
      globalStatus?.connectedCount ??
      channels.filter((c) => c.healthStatus === 'Healthy').length
    const totalCount = globalStatus?.totalCount ?? channels.length
    const statusText = globalStatus ? globalStatus.statusText : '● All systems connected'

    return {
      intent: 'connectivity',
      reply: `🌐 *Commerce Channels Connectivity (${connectedCount}/${totalCount} Healthy) — ${companyData.companyName || 'Commerce OS'}:*\n${listStr}\n\n*Status:* ${statusText}\n*Security:* TLS 1.3 Active · Ingress normal · 42ms avg latency\n\nType *menu* for more options.`,
      quickActions: [
        { id: 'btn-menu-back', label: '📋 View Menu', replyText: 'menu' },
        { id: 'btn-gmv-jump', label: '📊 View GMV Breakdown', replyText: '4' },
      ],
    }
  }

  // 4. Option 3: Show inventory health
  if (
    choice === 3 ||
    lower.includes('inventory') ||
    lower.includes('stock') ||
    lower.includes('oos') ||
    lower.includes('reorder') ||
    lower.includes('warehouse')
  ) {
    const items = companyData.inventoryItems || []
    const oos = items.filter((i) => i.status === 'OOS' || i.riskLevel === 'oos')
    const low = items.filter((i) => i.riskLevel === 'critical' || i.riskLevel === 'warning')

    let itemHighlight = ''
    if (oos.length > 0) {
      itemHighlight = `• Fastest Depleting: ${oos[0].name} (${oos[0].channel} · ${oos[0].location || 'OOS'})\n• Reorder Recommendation: Emergency allocation from master fulfillment center.`
    } else if (low.length > 0) {
      itemHighlight = `• Low Stock Notice: ${low[0].name} (${low[0].channel} · ${low[0].currentStock} units left)\n• Run-out Rate: Buffer cover ${low[0].daysOfCover || '<2 days'}`
    } else {
      itemHighlight = `• Stock Health: All active listings maintained above minimum safety stock buffer.`
    }

    return {
      intent: 'inventory',
      reply: `📦 *Inventory Health Status — ${companyData.companyName || 'Commerce OS'}:*
• Current Status: ${companyData.kpis?.inventoryHealth || 'Monitoring active'}
• Revenue Exposure: ${companyData.kpis?.stockoutRisk || '₹0'}
${itemHighlight}
• Master Catalog: ${companyData.kpis?.activeSkus || 'All SKUs'} (${companyData.kpis?.catalogHealth || '100%'} health)

Type *menu* for more options.`,
      quickActions: [
        { id: 'btn-menu-back', label: '📋 View Menu', replyText: 'menu' },
        { id: 'btn-att-jump', label: '⚡ Pending Decisions', replyText: '1' },
      ],
    }
  }

  // 5. Option 4: Show channel GMV breakdown
  if (
    choice === 4 ||
    lower.includes('gmv') ||
    lower.includes('sales') ||
    lower.includes('revenue') ||
    lower.includes('pace') ||
    lower.includes('breakdown')
  ) {
    const channels = companyData.channels || []
    const channelLines =
      channels.length > 0
        ? channels
            .map(
              (ch) =>
                `• *${ch.shortName || ch.name}:* ${ch.gmv} GMV (${ch.orders} orders) · Share: ${ch.share || '—'} · ${ch.statusText || 'Healthy'}`
            )
            .join('\n')
        : '• All channels operational'

    return {
      intent: 'gmv',
      reply: `📈 *Channel Performance Snapshot — ${companyData.companyName || 'Commerce OS'}:*
• Total GMV (MTD): ${companyData.kpis?.revenueMtd || '—'} (${companyData.kpis?.revenueDelta || '0%'})
• Today's Pace: ${companyData.kpis?.revenueToday || '—'}
• Total Orders: ${companyData.kpis?.ordersMtd || '—'}
• Average Order Value: ${companyData.kpis?.aov || '—'}
• On-time Fulfillment SLA: ${companyData.kpis?.ordersSla || '99%'}

*Channel Breakdown:*
${channelLines}

Type *menu* for more options.`,
      quickActions: [
        { id: 'btn-menu-back', label: '📋 View Menu', replyText: 'menu' },
        { id: 'btn-conn-jump', label: '🌐 Channel Connectivity', replyText: '2' },
      ],
    }
  }

  // 6. SEO & Commerce Audit Prioritization Engine intent
  if (
    raw === '5' ||
    raw === '5.' ||
    lower.includes('option 5') ||
    lower.includes('seo') ||
    lower.includes('audit') ||
    lower.includes('priorit') ||
    lower.includes('what to fix') ||
    lower.includes('fix first')
  ) {
    const auditData = getSeoAuditData(companyData.companyId || 'waaree')
    const total = auditData.totalFindingsCount || 214
    const displayLabel = auditData.displayCountLabel || (total >= 200 ? '200+ findings detected' : `${total} findings detected`)
    const summary = auditData.funnel?.whatsappSummary || {
      immediateAttention: 5,
      requiresApproval: 2,
      feedFixable: 1,
      apiRequired: 3,
      backlogDeprioritized: 209,
    }

    const topActions = (auditData.priorityQueue || []).slice(0, 3)
    const actionsList = topActions
      .map((item, idx) => {
        const tierTag = item.priorityTier.split(' — ')[0]
        return `${idx + 1}️⃣ *[${tierTag}] ${item.findingTitle}*\n` +
               `   • *Channel:* ${item.affectedChannel}\n` +
               `   • *Risk:* ${item.businessConsequence}\n` +
               `   • *Action:* ${item.recommendedAction}\n` +
               `   • *Access:* ${item.requiredAccess} | *Approval:* ${item.humanApprovalRequired ? 'Required' : 'Auto'}`
      })
      .join('\n\n')

    const reply =
      `🔍 *SANOCEA SEO & Commerce Audit Engine — ${companyData.companyName || 'Commerce Operations'}:*\n` +
      `Crawl completed across catalog, feeds, and crawl graph.\n\n` +
      `📊 *Full Discovery:* ${displayLabel} (${total} verified).\n\n` +
      `🎯 *Commercial Prioritization Summary:*\n` +
      `• *${summary.immediateAttention} require immediate attention* (P0/P1 Commercial Risk)\n` +
      `• *${summary.requiresApproval} require human approval*\n` +
      `• *${summary.feedFixable} can be corrected via GMC Supplemental Feed*\n` +
      `• *${summary.apiRequired} require Storefront API / Git Repository access*\n` +
      `• *${summary.backlogDeprioritized} long-tail findings deprioritized* to low backlog\n\n` +
      `*What SANOCEA Recommends Fixing First:*\n\n${actionsList}\n\n` +
      `Reply with action number or select an option below:`

    const quickActions = [
      ...topActions.slice(0, 2).map((item) => ({
        id: `qa-${item.id}`,
        label: `⚡ Approve ${item.priorityTier.split(' — ')[0]} Fix`,
        actionKey: item.id,
        actionKind: 'seo_priority_resolution',
      })),
      { id: 'btn-menu-back', label: '📋 View Menu', replyText: 'menu' },
    ]

    return {
      intent: 'seo_audit',
      reply,
      quickActions,
    }
  }

  // 5. Automation Opportunity Map intent
  if (
    lower.includes('automation') ||
    lower.includes('opportunity') ||
    lower.includes('automate') ||
    lower.includes('map') ||
    lower.includes('matrix')
  ) {
    if (companyData.companyId === 'waaree') {
      return {
        intent: 'automation',
        reply: `⚡ *SANOCEA Automation Opportunity Map — Waaree Energies:*
*Operating Model:* Detect → Explain → Prepare Action → Approve → Execute → Audit

1️⃣ *Catalogue & Specs:* Continuous attribute sweep across 75 SKUs; auto-validates wattage, cell-tech (TOPCon vs PERC), and 17 datasheet CDN links.
2️⃣ *Pricing & Parity:* Real-time parity monitor between D2C vs Amazon vs Flipkart; alerts on multi-pack unit dilution (-40%) and third-party buy-box undercuts (MNP Global).
3️⃣ *Inventory & Feeds:* Detects structured data InStock leaks on zero-stock items; suppresses 24h dispatch badges on OOS products.
4️⃣ *Order Operations:* Fulfilment SLA countdown against 48h/72h targets across all 5 channels; flags delayed pick-and-pack batches.
5️⃣ *Marketplace Operations:* SP-API & Flipkart Partner API health scanner; tracks seller-of-record compliance and automated listing suppression recovery.
6️⃣ *Complaints & SLAs:* Normalizes tickets from 5 parallel intake portals into one queue; bridges L&T-SuFin & Moglix orders; enforces 30-day warranty clock.
7️⃣ *Warranty Operations:* Automated 9-item document bundle verification; serial number validation; cross-channel warranty term harmonization.
8️⃣ *Settlement & Reconcile:* Correlates channel orders, fee deductions, and L&T-SuFin deduction schedules (*Requires access to settlement/finance data*).

Type *menu* to return or reply *1* to take action on pending decisions.`,
        quickActions: [
          { id: 'btn-att-jump', label: '⚡ Pending Decisions', replyText: '1' },
          { id: 'btn-menu-back', label: '📋 View Menu', replyText: 'menu' },
        ],
      }
    }

    return {
      intent: 'automation',
      reply: `⚡ *SANOCEA Automation Engine — ${companyData.companyName || 'Commerce Operations'}:*
• Channel Telemetry & Event Ingress (Continuous)
• Automated Anomaly & Drift Detection
• Decision-Gated Action Payloads
• 1-Click Approval via WhatsApp & Command Center
• Closed-Loop Cryptographic Execution Audit

Type *1* to review items requiring immediate decision.`,
      quickActions: [
        { id: 'btn-att-jump', label: '⚡ Pending Decisions', replyText: '1' },
        { id: 'btn-menu-back', label: '📋 View Menu', replyText: 'menu' },
      ],
    }
  }

  // 6. Approval / Execution intents
  if (lower.includes('approve') || lower.includes('yes') || lower.includes('reconnect')) {
    if (globalStatus && !globalStatus.isHealthy) {
      return {
        intent: 'approval',
        executionAction: {
          actionKey: 'act-deg-amazon',
          actionKind: 'reconnect-channel',
          label: 'Reconnect Amazon India',
        },
      }
    }
    const pending = (urgentActions || []).filter((a) => !a.resolved)
    if (pending.length > 0) {
      return {
        intent: 'approval',
        executionAction: {
          actionKey: pending[0].id,
          actionKind: pending[0].actionKind,
          label: pending[0].actionLabel,
        },
      }
    }
  }

  // 7. Fallback: Any unrecognized input displays the explicit numbered menu
  return {
    intent: 'menu',
    reply: WHATSAPP_MENU_TEXT,
    quickActions: [
      { id: 'menu-qa-1', label: '1️⃣ What Needs Attention?', replyText: '1' },
      { id: 'menu-qa-2', label: '2️⃣ Channel Connectivity', replyText: '2' },
      { id: 'menu-qa-3', label: '3️⃣ Inventory Health', replyText: '3' },
      { id: 'menu-qa-4', label: '4️⃣ Channel GMV', replyText: '4' },
    ],
  }
}
