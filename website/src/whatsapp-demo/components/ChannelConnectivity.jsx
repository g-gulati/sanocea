import React from 'react'
import {getChannelLogo} from '../data/companyData.js'

export default function ChannelConnectivity({
  channels,
  globalStatus,
  onSimulateDegrade,
  onReconnectChannel,
}) {
  const formatSeconds = (sec) => {
    if (sec < 3) return 'Just now'
    if (sec < 60) return `${sec} sec ago`
    const mins = Math.floor(sec / 60)
    const remSec = sec % 60
    return `${mins}m ${remSec}s ago`
  }

  // Calculate live telemetry metrics across all channels
  const minLastEvent = Math.min(...channels.map((c) => c.lastEventSecondsAgo || 18))
  const avgLatency = Math.round(
    channels.reduce((acc, c) => acc + (c.latencyMs || 42), 0) / (channels.length || 1)
  )

  const getChannelDisplayName = (channel) => {
    if (channel.shortName) return channel.shortName
    const lower = (channel.name || '').toLowerCase()
    if (lower.includes('production web')) return 'Production Web'
    if (lower.includes('ai discovery') || lower.includes('ai crawler')) return 'AI Crawlers'
    if (lower.includes('google search') || lower.includes('google serp')) return 'Google SERP'
    if (lower.includes('amazon')) return 'Amazon IN'
    if (lower.includes('swiggy') || lower.includes('instamart')) return 'Instamart'
    if (lower.includes('shopify')) return 'Shopify D2C'
    if (lower.includes('blinkit')) return 'Blinkit'
    return channel.name
  }

  return (
    <section className="commerce-channels-section" aria-label="Commerce Channels Connectivity">
      {/* ── Top Header: COMMERCE CHANNELS · 4 of 4 channels operational ────── */}
      <div className="channels-section-banner">
        <div className="channels-banner-left">
          <div className="channels-title-row">
            <h2 className="channels-section-heading">COMMERCE CHANNELS</h2>
            <div className={`channels-live-pill ${globalStatus.isHealthy ? 'healthy' : 'degraded'}`}>
              <span className={`channels-live-dot ${globalStatus.isHealthy ? 'green' : 'amber'}`} />
              <span className="channels-live-text">
                {globalStatus.isHealthy
                  ? `${channels.length} of ${channels.length} channels operational`
                  : `${globalStatus.connectedCount} of ${globalStatus.totalCount} channels operational`}
              </span>
            </div>
          </div>
          <p className="channels-section-desc">
            <span className="telemetry-live-highlight">
              ● LIVE TELEMETRY · Last event {formatSeconds(minLastEvent)} · Avg latency {avgLatency} ms
            </span>
          </p>
        </div>

        <div className="channels-banner-right">
          <div className="telemetry-live-badge-prominent">
            <span className="telemetry-pulse-dot" />
            <div className="telemetry-live-text-wrap">
              <span className="telemetry-live-tag">LIVE INGRESS</span>
              <span className="telemetry-live-sub">Operational telemetry streaming</span>
            </div>
          </div>

          {onSimulateDegrade && (
            <button
              type="button"
              className="btn-channel-sim"
              onClick={globalStatus.isHealthy ? onSimulateDegrade : () => onReconnectChannel(globalStatus.degradedChannel?.id)}
              title={globalStatus.isHealthy ? 'Test connector failover & latency spike' : 'Restore degraded connector'}
            >
              {globalStatus.isHealthy ? '⚡ Test Channel Latency' : '⟳ Reconnect Channel'}
            </button>
          )}
        </div>
      </div>

      {/* ── 4 Large Spacious Marketplace Cards ─────────────────────────────── */}
      <div className="marketplace-cards-grid">
        {channels.map((ch) => {
          const isHealthy = ch.healthStatus === 'Healthy'
          const logoUrl = getChannelLogo(ch.id, ch.name)
          const displayName = getChannelDisplayName(ch)

          return (
            <div
              key={ch.id}
              className={`marketplace-card ${isHealthy ? 'healthy' : 'degraded'}`}
            >
              {/* Card Top: Logo & Unmistakable 🟢 LIVE state */}
              <div className="mp-card-top">
                <div className="mp-logo-wrap">
                  {logoUrl ? (
                    <img
                      src={logoUrl}
                      alt={ch.name}
                      className="mp-logo-img"
                      onError={(e) => {
                        e.target.style.display = 'none'
                      }}
                    />
                  ) : (
                    <div className="mp-logo-fallback">
                      {displayName.slice(0, 2).toUpperCase()}
                    </div>
                  )}
                </div>

                <div className={`mp-status-pill ${isHealthy ? 'healthy' : 'degraded'}`}>
                  <span className={`mp-pulse-dot ${isHealthy ? 'green' : 'amber'}`} />
                  <span className="mp-status-label">
                    {isHealthy ? '🟢 LIVE' : '🟡 DEGRADED'}
                  </span>
                </div>
              </div>

              {/* Card Main: Channel Name, Receiving events, Last event, Latency */}
              <div className="mp-card-main">
                <h3 className="mp-channel-name">{displayName}</h3>

                <div className={`mp-live-banner ${isHealthy ? 'healthy' : 'degraded'}`}>
                  <span className={`mp-live-dot ${isHealthy ? 'green' : 'amber'}`} />
                  <span>
                    {isHealthy ? 'Receiving events' : 'Latency threshold breached'}
                  </span>
                </div>

                <div className="mp-telemetry-list">
                  <div className="mp-telemetry-row">
                    <span className="mp-telemetry-label">Last event:</span>
                    <span className="mp-telemetry-val dynamic-timer">
                      {formatSeconds(ch.lastEventSecondsAgo)}
                    </span>
                  </div>

                  <div className="mp-telemetry-row">
                    <span className="mp-telemetry-label">Latency:</span>
                    <span
                      className="mp-telemetry-val mono-val"
                      style={{
                        color: ch.latencyMs > 1000 ? 'var(--amber-warning)' : 'var(--teal-primary)',
                        fontWeight: 700,
                      }}
                    >
                      {ch.latencyMs} ms
                    </span>
                  </div>

                  <div className="mp-telemetry-row events-today-row">
                    <span className="mp-events-count">
                      {ch.incomingEventCount} events processed today
                    </span>
                  </div>
                </div>
              </div>

              {/* Card Footer: Operational Protocol Status (NO duplicate "Telemetry active") */}
              <div className="mp-card-footer">
                <div className="mp-footer-telemetry">
                  <span className={`mp-footer-dot ${isHealthy ? 'green' : 'amber'}`} />
                  <span>
                    {isHealthy ? 'Auto-reconciliation active' : 'Latency threshold breached'}
                  </span>
                </div>

                {!isHealthy && (
                  <button
                    type="button"
                    className="mp-btn-reconnect"
                    onClick={() => onReconnectChannel(ch.id)}
                  >
                    Reconnect Now
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
