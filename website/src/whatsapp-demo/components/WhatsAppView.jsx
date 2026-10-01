import React, {useState, useEffect, useRef} from 'react'
import {getChannelLogo} from '../data/companyData.js'
import {processWhatsAppCommand, WHATSAPP_MENU_TEXT} from '../whatsappCommandHandler.js'

export default function WhatsAppView({
  companyData,
  urgentActions,
  onResolveAction,
  onSwitchToDashboard,
  streamEvents,
  onAddStreamEvent,
  channelStates,
  globalStatus,
  onReconnectChannel,
  chatMessages: propChatMessages,
  onUpdateChatMessages,
  onResetDemo,
}) {
  const [selectedFilter, setSelectedFilter] = useState('all') // 'all' | 'inventory' | 'pricing' | 'orders' | 'catalogue'
  const [selectedEventId, setSelectedEventId] = useState(null)
  const [internalChatMessages, setInternalChatMessages] = useState(companyData.initialChatMessages || [])
  const chatMessages = propChatMessages !== undefined ? propChatMessages : internalChatMessages

  const setChatMessages = (updater) => {
    if (onUpdateChatMessages) {
      onUpdateChatMessages(updater)
    } else {
      setInternalChatMessages(updater)
    }
  }

  const [inputText, setInputText] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [streamActive, setStreamActive] = useState(true)
  const chatBottomRef = useRef(null)

  // Scroll chat to bottom when messages update
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({behavior: 'smooth'})
  }, [chatMessages, isTyping])

  // Periodic subtle simulated incoming event
  useEffect(() => {
    if (!streamActive) return
    const interval = setInterval(() => {
      const now = new Date()
      const timeStr = now.toTimeString().split(' ')[0]
      const simulatedCandidates = [
        {
          id: `sim-${Date.now()}`,
          time: timeStr,
          channel: 'Blinkit',
          type: 'Blinkit dark store sync',
          headline: 'Saket Dark Store — replenishment batch reserved',
          detail: '48 units assigned from central warehouse staging dock.',
          badge: 'Inventory',
          badgeColor: '#10b981',
        },
        {
          id: `sim-${Date.now()}`,
          time: timeStr,
          channel: 'Shopify D2C',
          type: 'New order event',
          headline: `Order #PB-${Math.floor(10483 + Math.random() * 50)} — ₹1,890`,
          detail: '2 items · Payment captured via UPI · Routed to Noida FC.',
          badge: 'Order Ingress',
          badgeColor: '#10b981',
        },
        {
          id: `sim-${Date.now()}`,
          time: timeStr,
          channel: 'Swiggy Instamart',
          type: 'Catalog health ping',
          headline: 'Catalog synchronization completed (14 SKUs)',
          detail: 'All inventory quantities matched against POS store buffer.',
          badge: 'Catalogue',
          badgeColor: '#38bdf8',
        },
      ]
      const nextEvent = simulatedCandidates[Math.floor(Math.random() * simulatedCandidates.length)]
      onAddStreamEvent(nextEvent)
    }, 18000)

    return () => clearInterval(interval)
  }, [streamActive, onAddStreamEvent])

  const filteredEvents = streamEvents.filter((ev) => {
    if (selectedFilter === 'all') return true
    const text = `${ev.type} ${ev.badge} ${ev.headline}`.toLowerCase()
    return text.includes(selectedFilter.toLowerCase())
  })

  // Handle WhatsApp interactive button click (approval / trigger)
  // Helper to construct realistic 5-step closed-loop execution plans
  const getExecutionPlan = (action) => {
    const key = action.actionKey || action.id || ''
    if (key === 'act-pb-01' || key === 'act-ajn-03' || key === 'act-crz-02' || action.actionKind === 'approve-transfer') {
      return {
        title: 'Blinkit Emergency Stock Allocation & WMS Transfer',
        channel: 'Blinkit',
        steps: [
          { label: 'Approval requested', detail: 'BBQ Almonds 200g (120 units) allocation requested for Saket & Indirapuram dark stores' },
          { label: 'Approved by operator', detail: 'Operator authorized emergency stock transfer via WhatsApp Operations' },
          { label: 'Stock transfer initiated', detail: 'Dispatched pick & transfer payload to Central Warehouse (Okhla Hub) WMS' },
          { label: 'Blinkit connector acknowledged', detail: 'Blinkit Dark Store Ingress API acknowledged stock allocation in 28ms' },
          { label: 'Exception resolved', detail: '120 units reserved · Dark store availability restored · Dashboard state synced' },
        ],
        auditId: 'SAN-BLK-89421',
        duration: '1.2s',
      }
    }
    if (key === 'act-pb-02' || key === 'act-ajn-01' || key === 'act-gbj-02' || action.actionKind === 'price-guard') {
      return {
        title: 'Amazon SP-API Price Guard Enforcement',
        channel: 'Amazon India',
        steps: [
          { label: 'Approval requested', detail: 'Floor price breach detected on Medjool Stuffed Dates (₹380 actual vs ₹420 floor)' },
          { label: 'Approved by operator', detail: 'Operator authorized ₹420 Buy Box floor enforcement via WhatsApp' },
          { label: 'Pricing rule update initiated', detail: 'Generated SP-API feed payload with canonical floor constraint' },
          { label: 'Amazon connector acknowledged', detail: 'Amazon Selling Partner API confirmed price feed ingestion in 34ms' },
          { label: 'Exception resolved', detail: 'Floor locked to ₹420 · Margin dilution prevented · Rule status ACTIVE' },
        ],
        auditId: 'SAN-AMZ-44109',
        duration: '1.4s',
      }
    }
    if (key === 'act-deg-amazon' || action.actionKind === 'reconnect-channel') {
      return {
        title: 'Amazon India SP-API Connector Reconnection',
        channel: 'Amazon India',
        steps: [
          { label: 'Approval requested', detail: 'Connector latency spike (1,840ms) & timeout detected on SP-API webhook' },
          { label: 'Approved by operator', detail: 'Operator triggered TLS 1.3 channel reconnection handshake' },
          { label: 'Ingress handshake initiated', detail: 'Re-negotiating OAuth credentials & event bus listener endpoint' },
          { label: 'Amazon connector acknowledged', detail: 'Amazon SP-API telemetry ping acknowledged · 42ms response latency' },
          { label: 'Exception resolved', detail: '4 of 4 channels operational · Ingress normal · Telemetry healthy' },
        ],
        auditId: 'SAN-REC-10293',
        duration: '1.1s',
      }
    }
    if (key === 'act-waa-01' || action.actionKind === 'correct-availability-feed') {
      return {
        title: 'Availability Feed Override — SANOCEA Simulation',
        channel: 'shop.waaree.com (BigCommerce) · Simulation Sandbox',
        isSimulation: true,
        steps: [
          { label: 'Automation prepared', detail: '[O] Observed: JSON-LD hardcodes InStock on 8 zero-stock SKUs including 3kW Hybrid Inverter & 50kW Three-Phase' },
          { label: 'Approved by operator', detail: 'Operator authorized availability feed override & 24h dispatch badge suppression via SANOCEA Command Center' },
          { label: 'Simulation payload executed', detail: 'SANOCEA state store updated · OutOfStock status corrected on 8 OOS SKUs · Replenishment alert staged' },
          { label: 'Simulation verified', detail: 'SANOCEA demo state synchronized · Production execution requires BigCommerce V3 API write scopes' },
          { label: 'Immutable audit logged', detail: 'Audit receipt #SAN-WAA-84021 written with operator ID, timestamp & action payload snapshot' },
        ],
        auditId: 'SAN-WAA-84021',
        duration: '1.3s (simulation)',
      }
    }
    if (key === 'act-waa-02' || action.actionKind === 'lock-specs') {
      return {
        title: 'Master Specification Lock — SANOCEA Simulation',
        channel: 'shop.waaree.com & Amazon · Simulation Sandbox',
        isSimulation: true,
        steps: [
          { label: 'Automation prepared', detail: '[O] Observed: 700W TOPCon alt-text incorrectly claims Mono PERC on 12+ listings; 0/17 working datasheet links' },
          { label: 'Approved by operator', detail: 'Operator authorized canonical N-Type TOPCon attribute lock & PDF CDN redirect' },
          { label: 'Simulation payload executed', detail: 'SANOCEA state store updated · Conflicting Mono PERC tags cleared · Correct 600W+ datasheet link staged' },
          { label: 'Simulation verified', detail: 'SANOCEA demo state synchronized · Production execution requires BigCommerce catalog & feed write scopes' },
          { label: 'Immutable audit logged', detail: 'Audit receipt #SAN-WAA-84022 written with operator ID, timestamp & action payload snapshot' },
        ],
        auditId: 'SAN-WAA-84022',
        duration: '1.4s (simulation)',
      }
    }
    if (key === 'act-waa-03' || action.actionKind === 'align-pricing') {
      return {
        title: 'Price Parity Alignment — SANOCEA Simulation',
        channel: 'shop.waaree.com & Amazon · Simulation Sandbox',
        isSimulation: true,
        steps: [
          { label: 'Automation prepared', detail: '[O] Observed: 590Wp D2C ₹11,099 vs Amazon ₹11,599 (+4.5%); 540Wp pack-of-2 at ₹9,099/unit (−40% dilution)' },
          { label: 'Approved by operator', detail: 'Operator authorized D2C price parity alignment and Amazon pack floor constraint' },
          { label: 'Simulation payload executed', detail: 'SANOCEA state store updated · D2C single unit aligned to ₹11,099 parity · Pack margin floor staged' },
          { label: 'Simulation verified', detail: 'SANOCEA demo state synchronized · Production execution requires Amazon SP-API & BigCommerce pricing scopes' },
          { label: 'Immutable audit logged', detail: 'Audit receipt #SAN-WAA-84023 written with operator ID, timestamp & action payload snapshot' },
        ],
        auditId: 'SAN-WAA-84023',
        duration: '1.2s (simulation)',
      }
    }
    if (key === 'act-waa-04' || action.actionKind === 'unify-complaints') {
      return {
        title: 'Complaint Unification — SANOCEA Simulation',
        channel: 'Customer Service & Intake Portals · Simulation Sandbox',
        isSimulation: true,
        steps: [
          { label: 'Automation prepared', detail: '[O] Observed: L&T-SuFin & Moglix omitted from ecom helpdesk; conflicting warranty terms (12/27 yr vs 12/30 yr vs 15 yr)' },
          { label: 'Approved by operator', detail: 'Operator authorized unified ingestion routing and standardized 12/30 yr warranty terms' },
          { label: 'Simulation payload executed', detail: 'SANOCEA state store updated · L&T-SuFin & Moglix order schemas linked · Warranty terms standardized' },
          { label: 'Simulation verified', detail: 'SANOCEA demo state synchronized · Production execution requires support portal webhook/API access' },
          { label: 'Immutable audit logged', detail: 'Audit receipt #SAN-WAA-84024 written with operator ID, timestamp & action payload snapshot' },
        ],
        auditId: 'SAN-WAA-84024',
        duration: '1.3s (simulation)',
      }
    }
    return {
      title: action.label || action.title || 'Commerce Operations Automation',
      channel: action.channel || 'Commerce Channels',
      steps: [
        { label: 'Approval requested', detail: `Operational action requested: ${action.label || action.title || 'Action'}` },
        { label: 'Approved by operator', detail: 'Operator authorized action execution via WhatsApp Operations' },
        { label: 'Action payload initiated', detail: 'Dispatched operational command to SANOCEA Operations Engine' },
        { label: 'Connector acknowledged', detail: 'Channel connectors acknowledged receipt and updated state in 31ms' },
        { label: 'Exception resolved', detail: 'State synchronized across all connected channels · Audit trail logged' },
      ],
      auditId: `SAN-ACT-${Math.floor(10000 + Math.random() * 90000)}`,
      duration: '1.3s',
    }
  }

  // Trigger dynamic 5-step closed-loop execution
  const runClosedLoopExecution = (action) => {
    const plan = getExecutionPlan(action)
    const botMsgId = `exec-${Date.now()}`
    const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})

    const execMsg = {
      id: botMsgId,
      from: 'sanocea',
      time: timeStr,
      isExecutionLoop: true,
      executionPlan: plan,
      currentStep: 1,
      isCompleted: false,
    }

    setChatMessages((prev) => [...prev, execMsg])

    // Animate through all 5 steps over ~1.4 seconds
    setTimeout(() => {
      setChatMessages((prev) =>
        prev.map((m) => (m.id === botMsgId ? {...m, currentStep: 2} : m))
      )
    }, 320)

    setTimeout(() => {
      setChatMessages((prev) =>
        prev.map((m) => (m.id === botMsgId ? {...m, currentStep: 3} : m))
      )
    }, 680)

    setTimeout(() => {
      setChatMessages((prev) =>
        prev.map((m) => (m.id === botMsgId ? {...m, currentStep: 4} : m))
      )
    }, 1040)

    setTimeout(() => {
      setChatMessages((prev) =>
        prev.map((m) => (m.id === botMsgId ? {...m, currentStep: 5, isCompleted: true} : m))
      )

      // Synchronize with dashboard resolution state
      if (action.actionKey === 'act-deg-amazon' || action.actionKind === 'reconnect-channel') {
        if (onReconnectChannel) onReconnectChannel('amazon')
      } else if (action.actionKey) {
        onResolveAction(action.actionKey)
      } else if (action.id) {
        onResolveAction(action.id)
      }
    }, 1400)
  }

  // Handle WhatsApp interactive button click (approval / trigger)
  const handleQuickAction = (action) => {
    // 1. Add user reply bubble
    const userMsg = {
      id: `usr-${Date.now()}`,
      from: 'user',
      time: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
      text: action.replyText || action.label,
    }
    setChatMessages((prev) => [...prev, userMsg])

    // 2. If it has an actionKey or is an execution command, run the closed-loop stepper
    if (action.actionKey || action.actionKind) {
      setTimeout(() => {
        runClosedLoopExecution(action)
      }, 250)
      return
    }

    // 3. Process action command through shared WhatsApp command handler
    const query = action.replyText || action.label
    const result = processWhatsAppCommand(query, {
      companyData,
      urgentActions,
      channelStates,
      globalStatus,
    })

    if (result.shouldReset) {
      if (onResetDemo) {
        onResetDemo({ fromWhatsApp: true, replyText: result.reply })
        return
      }
    }

    if (result.executionAction) {
      setTimeout(() => {
        runClosedLoopExecution(result.executionAction)
      }, 250)
      return
    }

    setIsTyping(true)
    setTimeout(() => {
      setIsTyping(false)
      setChatMessages((prev) => [
        ...prev,
        {
          id: `bot-${Date.now()}`,
          from: 'sanocea',
          time: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
          text: result.reply,
          quickActions: result.quickActions,
        },
      ])
    }, 450)
  }

  // Handle free-form chat message from input
  const handleSendMessage = (e, overrideText) => {
    if (e && e.preventDefault) e.preventDefault()
    const query = (overrideText || inputText).trim()
    if (!query) return

    setInputText('')

    const userMsg = {
      id: `usr-${Date.now()}`,
      from: 'user',
      time: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
      text: query,
    }
    setChatMessages((prev) => [...prev, userMsg])

    // Process via shared WhatsApp command handler (standardized site-wide)
    const result = processWhatsAppCommand(query, {
      companyData,
      urgentActions,
      channelStates,
      globalStatus,
    })

    if (result.shouldReset) {
      if (onResetDemo) {
        onResetDemo({ fromWhatsApp: true, replyText: result.reply })
        return
      }
    }

    // If command triggers an operational approval / reconnection execution:
    if (result.executionAction) {
      setTimeout(() => {
        runClosedLoopExecution(result.executionAction)
      }, 300)
      return
    }

    setIsTyping(true)
    setTimeout(() => {
      setIsTyping(false)
      setChatMessages((prev) => [
        ...prev,
        {
          id: `bot-${Date.now()}`,
          from: 'sanocea',
          time: new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
          text: result.reply,
          quickActions: result.quickActions,
        },
      ])
    }, 450)
  }

  return (
    <div className="whatsapp-view-section">
      {/* ── Prominent Connection State Banner (Requirement) ──────────────────── */}
      <div className="wa-connection-banner">
        <div className="wa-conn-left">
          <div className="wa-brand-badge-wrap" title="SANOCEA Operational Ingress">
            <img src="/sanocea-wordmark-navy.png" alt="SANOCEA" className="wa-brand-badge-img" />
          </div>
          <div className="wa-status-dot-pulse" title="Live bidirectional connector heartbeat" />
          <div>
            <h2 className="wa-conn-title">WhatsApp Connected</h2>
            <p className="wa-conn-subtitle">
              <span style={{fontWeight: 800, color: 'var(--green-success)'}}>🟢 Connected · Receiving operational events</span>
              <span>·</span>
              <span style={{fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)'}}>
                {globalStatus ? `${globalStatus.connectedCount}/${globalStatus.totalCount} Channels Live · Latency: 42 ms · TLS 1.3 Active` : 'Latency: 42 ms · TLS 1.3 Active'}
              </span>
            </p>
          </div>
        </div>

        <div className="wa-security-ingress-badge" title="SANOCEA Ingress Security">
          <span className="ingress-dot">●</span>
          <span>TLS 1.3 Active · 42ms Latency · Real-Time Commerce Connectors</span>
        </div>
      </div>

      {/* If a channel is degraded, show immediate alert in WhatsApp view as well */}
      {globalStatus && !globalStatus.isHealthy && (
        <div style={{
          background: 'var(--amber-bg)',
          border: '1px solid var(--amber-border)',
          borderRadius: 14,
          padding: '14px 22px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          color: '#92400E',
          fontSize: 15,
          fontWeight: 600,
        }}>
          <div style={{display: 'flex', alignItems: 'center', gap: 12}}>
            <span style={{color: 'var(--amber-warning)', fontSize: 18}}>⚠️</span>
            {getChannelLogo(globalStatus.degradedChannel?.id, globalStatus.degradedChannel?.name) && (
              <img
                src={getChannelLogo(globalStatus.degradedChannel?.id, globalStatus.degradedChannel?.name)}
                alt=""
                className="channel-mini-logo"
                style={{width: 26, height: 26}}
              />
            )}
            <span><strong>Channel Telemetry Alert:</strong> {globalStatus.degradedChannel?.name} SP-API latency spike ({globalStatus.degradedChannel?.latencyMs} ms). Last event {globalStatus.degradedChannel?.lastEventSecondsAgo}s ago.</span>
          </div>
          <button
            type="button"
            className="btn-sim-restore"
            style={{padding: '8px 16px', fontSize: 13.5, fontWeight: 700}}
            onClick={() => onReconnectChannel(globalStatus.degradedChannel?.id)}
          >
            Reconnect Now
          </button>
        </div>
      )}

      {/* ── Two-Column Operational Workspace ─────────────────────────────────── */}
      <div className="wa-ops-split">
        {/* Left: Real-Time Operational Event Stream */}
        <div className="wa-stream-pane">
          <div className="stream-head">
            <div className="stream-title-wrap">
              <h3 className="stream-title">Live Operational Event Stream</h3>
              <div className="live-indicator">
                <span className="live-pulse-dot" />
                <span>RECEIVING LIVE</span>
              </div>
            </div>

            <button
              type="button"
              className="btn-ghost-action"
              style={{fontSize: 13, fontWeight: 700, padding: '6px 14px'}}
              onClick={() => setStreamActive(!streamActive)}
              title="Pause or resume real-time event telemetry stream"
            >
              {streamActive ? '⏸ Pause Stream' : '▶ Resume Stream'}
            </button>
          </div>

          {/* Filter Chips */}
          <div className="stream-filter-row">
            {['all', 'inventory', 'pricing', 'orders', 'catalogue'].map((cat) => (
              <button
                key={cat}
                type="button"
                className={`stream-filter-chip ${selectedFilter === cat ? 'active' : ''}`}
                onClick={() => setSelectedFilter(cat)}
              >
                {cat === 'all' ? 'All Events' : cat === 'inventory' ? 'Inventory (OOS)' : cat.charAt(0).toUpperCase() + cat.slice(1)}
              </button>
            ))}
          </div>

          {/* Chronological Event Feed */}
          <div className="stream-feed-list">
            {filteredEvents.map((ev) => (
              <div
                key={ev.id}
                className={`stream-event-item ${selectedEventId === ev.id ? 'highlighted' : ''}`}
                onClick={() => setSelectedEventId(ev.id === selectedEventId ? null : ev.id)}
              >
                <div className="event-top-line">
                  <span className="event-time">{ev.time}</span>
                  <span className="event-channel-badge">
                    {getChannelLogo(null, ev.channel) && (
                      <img
                        src={getChannelLogo(null, ev.channel)}
                        alt=""
                        className="channel-mini-logo"
                        style={{width: 18, height: 18, padding: 1}}
                      />
                    )}
                    <span>{ev.channel}</span>
                  </span>
                </div>

                <div className="event-headline">{ev.headline}</div>
                <div className="event-detail">{ev.detail}</div>

                <div className="event-action-row">
                  <span
                    className="event-badge-tag"
                    style={{
                      background: '#F0F9FF',
                      color: 'var(--teal-primary)',
                      border: '1px solid var(--teal-border)',
                      fontSize: 12.5,
                      fontWeight: 800,
                    }}
                  >
                    {ev.badge}
                  </span>

                  <div style={{display: 'flex', gap: 8}}>
                    <button
                      type="button"
                      className="btn-ghost-action"
                      style={{fontSize: 13, fontWeight: 700, padding: '6px 14px'}}
                      onClick={(e) => {
                        e.stopPropagation()
                        onSwitchToDashboard(ev.headline)
                      }}
                    >
                      Inspect in Dashboard ↗
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: WhatsApp Business Assistant Chat Terminal */}
        <div className="wa-chat-pane">
          <div className="chat-header">
            <div className="chat-partner">
              <div className="chat-avatar-brand" title="SANOCEA Operations Intelligence">
                <img src="/sanocea-wordmark-navy.png" alt="SANOCEA" className="chat-avatar-logo" />
              </div>
              <div className="chat-info">
                <h4>
                  <span>SANOCEA Operations Bot</span>
                  <span className="verified-icon" title="Verified WhatsApp Business Account">✓</span>
                </h4>
                <p className="chat-subline">
                  🟢 Online · Connected to {companyData.companyName}
                </p>
              </div>
            </div>

            <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
              <button
                type="button"
                style={{
                  background: 'rgba(255, 255, 255, 0.18)',
                  border: '1px solid rgba(255, 255, 255, 0.35)',
                  color: '#FFFFFF',
                  borderRadius: 8,
                  padding: '8px 14px',
                  fontSize: 13.5,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                onClick={() => handleSendMessage({preventDefault: () => {}, target: {}}, 'menu')}
              >
                📋 Operations Menu
              </button>
              <button
                type="button"
                style={{
                  background: 'rgba(255, 255, 255, 0.18)',
                  border: '1px solid rgba(255, 255, 255, 0.35)',
                  color: '#FFFFFF',
                  borderRadius: 8,
                  padding: '8px 14px',
                  fontSize: 13.5,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                onClick={() => handleSendMessage({preventDefault: () => {}, target: {}}, '1')}
              >
                ⚡ Attention Briefing
              </button>
            </div>
          </div>

          <div className="chat-messages-area">
            <div className="chat-disclaimer-bubble">
              🔒 Encrypted Operations Channel · Events ingested from Blinkit, Shopify, Swiggy & Amazon
            </div>

            {chatMessages.map((msg) => (
              <div key={msg.id} className={`msg-row ${msg.from === 'user' ? 'out' : 'in'} ${msg.isExecutionLoop ? 'exec-loop-row' : ''}`}>
                <div className={`msg-bubble ${msg.isExecutionLoop ? 'exec-bubble' : ''}`}>
                  {msg.isExecutionLoop ? (
                    <div className="closed-loop-card">
                      <div className="cl-header">
                        <div className="cl-title-wrap">
                          <div className="cl-tag-row">
                            <span className="cl-tag">{msg.executionPlan.isSimulation ? 'SANOCEA SIMULATION SANDBOX' : 'CLOSED-LOOP AUTOMATION'}</span>
                            <span className="cl-channel-badge">{msg.executionPlan.channel}</span>
                          </div>
                          <h4 className="cl-title">{msg.executionPlan.title}</h4>
                        </div>
                        <span className={`cl-status-pill ${msg.isCompleted ? 'completed' : 'running'}`}>
                          {msg.isCompleted ? (msg.executionPlan.isSimulation ? '✓ SIMULATION COMPLETE' : '✓ EXECUTED') : '⚡ EXECUTING...'}
                        </span>
                      </div>

                      {msg.executionPlan.isSimulation && (
                        <div style={{
                          background: '#FFF7ED',
                          border: '1px solid #FED7AA',
                          borderRadius: 6,
                          padding: '6px 10px',
                          fontSize: 12,
                          color: '#92400E',
                          display: 'flex',
                          gap: 6,
                          alignItems: 'flex-start',
                          marginBottom: 12,
                        }}>
                          <span>🛡️</span>
                          <span>SANOCEA Simulation Sandbox — State updated in demo only. Live production execution requires API credentials & connector validation.</span>
                        </div>
                      )}

                      <div className="cl-stepper">
                        {msg.executionPlan.steps.map((st, idx) => {
                          const stepNum = idx + 1
                          const isDone = msg.currentStep > stepNum || msg.isCompleted
                          const isActive = msg.currentStep === stepNum && !msg.isCompleted
                          const isPending = msg.currentStep < stepNum

                          return (
                            <div
                              key={idx}
                              className={`cl-step ${isDone ? 'done' : ''} ${isActive ? 'active' : ''} ${isPending ? 'pending' : ''}`}
                            >
                              <div className="cl-step-indicator">
                                <div className="cl-step-circle">
                                  {isDone ? '✓' : (isActive ? '●' : stepNum)}
                                </div>
                                {idx < msg.executionPlan.steps.length - 1 && (
                                  <div className={`cl-step-line ${isDone ? 'done' : ''}`} />
                                )}
                              </div>
                              <div className="cl-step-content">
                                <div className="cl-step-label">{st.label}</div>
                                <div className="cl-step-detail">{st.detail}</div>
                              </div>
                            </div>
                          )
                        })}
                      </div>

                      {msg.isCompleted && (
                        <div className="cl-audit-footer">
                          <div className="cl-audit-row">
                            <span className="cl-audit-id">IMMUTABLE AUDIT RECEIPT: {msg.executionPlan.auditId}</span>
                            <span className="cl-audit-meta">{msg.executionPlan.duration} · {msg.executionPlan.isSimulation ? 'Demonstration state' : `Synced across ${msg.executionPlan.channel}`} & Dashboard</span>
                          </div>
                          <div className="cl-audit-status">
                            <span className="cl-audit-check">✓</span>
                            {msg.executionPlan.isSimulation
                              ? 'Simulation verified in SANOCEA demo state · Audit receipt written'
                              : 'Exception resolved and verified in SANOCEA Operations Engine'
                            }
                          </div>
                        </div>
                      )}

                      <span className="msg-time" style={{marginTop: 10}}>{msg.time}</span>
                    </div>
                  ) : (
                    <>
                      {msg.text}
                      <span className="msg-time">{msg.time}</span>

                      {/* Interactive Buttons on Bot Messages */}
                      {msg.quickActions && (
                        <div className="msg-quick-actions">
                          {msg.quickActions.map((qa) => (
                            <button
                              key={qa.id}
                              type="button"
                              className="wa-interactive-btn"
                              onClick={() => handleQuickAction(qa)}
                            >
                              <span>{qa.label}</span>
                              <span style={{fontSize: 14, opacity: 0.9}}>➔</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}

            {isTyping && (
              <div className="msg-row in">
                <div className="msg-bubble" style={{color: '#667781', fontStyle: 'italic', fontSize: 14.5}}>
                  Sanocea Operations Bot is analyzing telemetry...
                </div>
              </div>
            )}

            <div ref={chatBottomRef} />
          </div>

          {/* Interactive Chat Composer */}
          <form className="chat-composer" onSubmit={handleSendMessage}>
            <input
              type="text"
              className="chat-input"
              placeholder="Ask Sanocea or approve actions (e.g. 'What needs attention?', 'Approve stock transfer')..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
            />
            <button type="submit" className="chat-send-btn" title="Send message to Sanocea Bot">
              ➔
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
