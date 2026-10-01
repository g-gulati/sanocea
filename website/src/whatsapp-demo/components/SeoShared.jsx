import React from 'react'
import {view, fmtTime} from '../useSeoOverview.js'

// Provenance chip. The label is exactly what the worker (or this page, for [EDITORIAL · STATIC]) supplied; it is
// styled by family but never rewritten or remapped.
const CHIP = {
  observed: ['#0284C7', '#F0F9FF', '#BAE6FD'],
  calculated: ['#7C3AED', '#F5F3FF', '#DDD6FE'],
  inferred: ['#D97706', '#FFFBEB', '#FDE68A'],
  unavailable: ['#475569', '#F1F5F9', '#CBD5E1'],
  modeled: ['#6B21A8', '#F3E8FF', '#E9D5FF'],
  editorial: ['#6B7280', '#F9FAFB', '#E5E7EB'],
  bad: ['#B91C1C', '#FEF2F2', '#FECACA'],
}
function family(label) {
  const l = String(label || '').toUpperCase()
  if (l.includes('NOT AVAILABLE') || l.includes('NOT_AVAILABLE')) return 'unavailable'
  if (l.includes('OBSERVED')) return 'observed'
  if (l.includes('CALCULATED')) return 'calculated'
  if (l.includes('MODELED')) return 'modeled'
  if (l.includes('EDITORIAL') || l.includes('HISTORICAL')) return 'editorial'
  if (l.includes('FAIL')) return 'bad'
  return 'inferred' // [INFERRED], [ESTIMATED], [REQUIRES_ACCESS] and any other worker label
}
export function Chip({label}) {
  const [color, background, border] = CHIP[family(label)]
  return <span style={{fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background, color, border: `1px solid ${border}`, whiteSpace: 'nowrap'}}>{label}</span>
}

// A value the worker could not supply. Shows the worker's own reason; never a zero, a default or an estimate.
export function NotAvailable({title, reason, extra}) {
  return (
    <div style={{background: '#F8FAFC', border: '1px dashed #CBD5E1', borderRadius: '8px', padding: '12px 14px', margin: '8px 0'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
        <Chip label="[NOT AVAILABLE]" />
        <strong style={{fontSize: '13px', color: '#0F172A'}}>{title}</strong>
      </div>
      <div style={{fontSize: '12px', color: '#64748B', marginTop: 4, lineHeight: 1.45}}>{reason || 'no data returned'}</div>
      {extra}
    </div>
  )
}

// "Persisted by the worker at <its own timestamp>". Missing timestamp is stated, never invented.
export function Stamp({at, prefix = 'Persisted'}) {
  return <span style={{fontSize: '11.5px', color: '#64748B', fontFamily: 'var(--font-mono)'}}>{prefix} · {fmtTime(at)}</span>
}

export function SectionHead({title, chip, stamp, sub}) {
  return (
    <div style={{display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', marginBottom: 10}}>
      <div>
        <h4 style={{fontSize: '14.5px', fontWeight: 700, margin: 0, color: '#0F172A', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>{title}{chip ? <Chip label={chip} /> : null}</h4>
        {sub ? <div style={{fontSize: '12px', color: '#64748B', marginTop: 2}}>{sub}</div> : null}
      </div>
      {stamp !== undefined ? <Stamp at={stamp} /> : null}
    </div>
  )
}

export function relativeAge(iso, now = Date.now()) {
  const t = Date.parse(iso)
  if (!iso || Number.isNaN(t)) return null
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 90) return `${s}s ago`
  if (s < 5400) return `${Math.round(s / 60)}m ago`
  if (s < 129600) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

const num = {fontFamily: 'var(--font-mono)'}
const box = {background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: '8px'}

export function Unavailable({v, title}) {
  return <NotAvailable title={title} reason={v.error || 'view not returned by the SEO worker'} />
}

// SEO Opportunity Model: the worker has no persisted source for it, so nothing is modeled or shown.
export function OpportunityModelUnavailable() {
  return (
    <NotAvailable
      title="Modeled opportunity / demand data"
      reason="The SEO worker has no persisted opportunity-model source: its keyword-intelligence and model-visibility views both report NOT AVAILABLE. No target queries, demand volumes, click targets or CTRs are shown, because none exist to be shown."
    />
  )
}

// GSC average-position movement and the exact-keyword SERP ledger: two capabilities, two provenances, never blended.
export function RankMovementAndSerp({overview}) {
  const moveV = view(overview, 'rank_movement_gsc')
  const serpV = view(overview, 'serp_rank_movement')
  const trajectories = moveV.ok ? [...(moveV.data.site.trajectories || []), ...(moveV.data.pages.trajectories || [])] : []
  return (
    <div>
      <SectionHead title="📈 Rank Movement & Velocity Tracker" stamp={moveV.updated_at} sub="Two separate capabilities with separate provenance. They are never blended." />
      {moveV.ok ? (
        <>
          <div style={{fontSize: '12px', fontWeight: 700, color: '#0F172A', marginBottom: 6}}>GSC average-position movement <Chip label={moveV.data.site.provenance} /></div>
          <div style={{fontSize: '11.5px', color: '#64748B', marginBottom: 8}}>{moveV.data.definition}</div>
          <div style={{overflowX: 'auto'}}><table className="cs-diffs-table">
            <thead><tr><th>Scope</th><th>Start</th><th>Previous</th><th>Current</th><th>Movement</th><th>Observed days</th><th>Sample</th></tr></thead>
            <tbody>
              {trajectories.map((t) => (
                <tr key={`${t.dimension}:${t.key}`}>
                  <td><strong>{t.dimension === 'SITE' ? 'Whole site' : t.key.replace('https://www.sanocea.com', '') || '/'}</strong></td>
                  <td style={{...num, fontSize: 12, whiteSpace: 'nowrap'}}>{t.startFormatted}</td>
                  <td style={{...num, fontSize: 12, whiteSpace: 'nowrap'}}>{t.previousFormatted}</td>
                  <td style={{...num, fontSize: 12, fontWeight: 800, whiteSpace: 'nowrap'}}>{t.currentFormatted}</td>
                  <td style={{...num, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap'}}>{t.movementFormatted}</td>
                  <td style={num}>{t.observationDays}</td>
                  <td>{t.lowSample ? <span style={{fontSize: 11, fontWeight: 700, background: '#FFFBEB', color: '#92400E', border: '1px solid #FDE68A', borderRadius: 4, padding: '2px 6px'}}>⚠ LOW SAMPLE</span> : <span style={{fontSize: 11, color: '#64748B'}}>adequate</span>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          {trajectories.some((t) => t.lowSample) ? (
            <div style={{fontSize: 12, background: '#FFFBEB', border: '1px solid #FDE68A', color: '#92400E', borderRadius: 6, padding: '8px 12px', marginTop: 8}}>
              <strong>⚠ Low sample:</strong> the tracker flags a trajectory when its current or starting day has fewer than 5 impressions. Treat that movement as directional, not statistically meaningful.
            </div>
          ) : null}
          {moveV.data.queries && moveV.data.queries.provenance === '[NOT AVAILABLE]' ? <NotAvailable title="Query-level positions" reason={moveV.data.queries.note} /> : null}
        </>
      ) : <Unavailable v={moveV} title="GSC average-position movement" />}

      <div style={{fontSize: '12px', fontWeight: 700, color: '#0F172A', margin: '14px 0 6px'}}>Exact keyword SERP positions (velocity ledger)</div>
      {serpV.ok && Array.isArray(serpV.data.rows) && serpV.data.rows.length > 0 && serpV.data.status !== 'NOT_AVAILABLE' ? (
        <div style={{overflowX: 'auto'}}><table className="cs-diffs-table">
          <thead><tr><th>Target Search Query</th><th>Start</th><th>Previous</th><th>Current</th><th>Daily Δ</th><th>Cumulative Δ</th><th>Provider</th></tr></thead>
          <tbody>{serpV.data.rows.map((r, i) => (<tr key={i}><td><strong>{r.query}</strong></td><td style={num}>{r.startRankFormatted}</td><td style={num}>{r.previousRankFormatted}</td><td style={{...num, fontWeight: 800}}>{r.currentRankFormatted}</td><td style={num}>{r.dailyDeltaFormatted}</td><td style={num}>{r.cumulativeDeltaFormatted}</td><td style={{fontSize: 11}}><Chip label={r.provenance} /></td></tr>))}</tbody>
        </table></div>
      ) : (
        <NotAvailable title="No verified SERP provider is connected" reason={serpV.ok ? serpV.data.reason : serpV.error} extra={serpV.ok && serpV.data.dependency ? <div style={{fontSize: '11.5px', color: '#64748B', marginTop: 4}}><strong>Requires:</strong> {serpV.data.dependency}</div> : null} />
      )}
    </div>
  )
}

export function GrowthConstraintsEditorial({items}) {
  return (
    <div>
      <div style={{marginBottom: 12}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap'}}>
          <span style={{fontSize: 10, fontWeight: 800, background: '#D97706', color: '#FFFFFF', padding: '2px 6px', borderRadius: 4}}>STRATEGIC ANALYSIS</span>
          <h4 style={{fontSize: '14px', fontWeight: 700, color: '#92400E', margin: 0}}>Four Current Growth Constraints Identified From Available Evidence</h4>
          <Chip label="[EDITORIAL · STATIC]" />
        </div>
        <span style={{fontSize: '12px', color: '#78350F'}}>Written analysis, not worker telemetry. It carries no live figures; the numbers elsewhere on this page are the evidence.</span>
      </div>
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12}}>
        {items.map((gc) => (
          <div key={gc.id} style={{background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8, padding: '12px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between'}}>
            <div>
              <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6}}>
                <span style={{fontSize: 11, fontWeight: 800, color: '#B45309'}}>{gc.id}</span>
                <span style={{fontSize: 10, fontWeight: 800, padding: '2px 6px', borderRadius: 4, background: '#FEF3C7', color: '#92400E'}}>{gc.classification}</span>
              </div>
              <div style={{fontSize: '13px', fontWeight: 700, color: '#78350F', marginBottom: 4}}>{gc.title}</div>
              <div style={{fontSize: 11.5, color: '#92400E', lineHeight: 1.45, marginBottom: 8}}><strong>Evidence:</strong> {gc.evidence}</div>
            </div>
            <div style={{fontSize: 11, color: '#451A03', background: '#FEF3C7', padding: '6px 8px', borderRadius: 6, lineHeight: 1.35}}><strong>Action:</strong> {gc.actionPlan}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// What the Tier-1 sentinel is configured to probe. The worker persists one aggregate outcome per probe run, not a
// per-endpoint result, so per-endpoint status is NOT AVAILABLE rather than asserted.
const MONITORED = [
  {url: 'https://www.sanocea.com', role: 'Canonical Storefront Root'},
  {url: 'https://www.sanocea.com/robots.txt', role: 'Crawler Policy & AI Directives'},
  {url: 'https://www.sanocea.com/sitemap.xml', role: 'Production XML Sitemap'},
  {url: 'https://www.sanocea.com/llms.txt', role: 'AI / GEO Context Standard'},
]

export function MonitoredEndpoints({overview}) {
  const hbV = view(overview, 'heartbeats')
  const latest = hbV.ok && Array.isArray(hbV.data) ? hbV.data[0] : null
  return (
    <div style={{marginBottom: 24}}>
      <h4 style={{fontSize: '14.5px', fontWeight: 700, marginBottom: '10px', color: '#0F172A'}}>Monitored Production Endpoints (Tier 1 Hourly Probes)</h4>
      <div style={{overflowX: 'auto'}}><table className="cs-diffs-table" style={{marginBottom: 8}}>
        <thead><tr><th>Target URL</th><th>Role &amp; Policy Scope</th><th>Per-endpoint result</th></tr></thead>
        <tbody>{MONITORED.map((e) => (
          <tr key={e.url}><td><code>{e.url}</code></td><td><strong>{e.role}</strong></td><td><Chip label="[NOT AVAILABLE]" /> <span style={{fontSize: 12, color: '#64748B'}}>only the aggregate probe outcome is persisted</span></td></tr>))}
        </tbody>
      </table></div>
      {latest ? <div style={{fontSize: 12.5, color: '#475569'}}>Latest aggregate probe over this set: <strong style={{color: latest.status === 'ok' ? '#059669' : '#B91C1C'}}>{String(latest.status).toUpperCase()}</strong> · {latest.durationMs} ms · {latest.changeCount} changes detected · {fmtTime(latest.timestamp)} ({relativeAge(latest.timestamp)})</div> : <NotAvailable title="Latest probe" reason={hbV.error || 'no heartbeat persisted'} />}
    </div>
  )
}

export function HeartbeatsTable({overview}) {
  const hbV = view(overview, 'heartbeats')
  const beats = hbV.ok && Array.isArray(hbV.data) ? hbV.data : []
  return (
    <div>
      <SectionHead title="Recent Sentinel Heartbeats (Persisted to SQLite WAL)" stamp={hbV.updated_at} />
      {hbV.ok ? (
        <div style={{overflowX: 'auto'}}><table className="cs-diffs-table">
          <thead><tr><th>Heartbeat ID</th><th>Tier</th><th>Timestamp</th><th>Duration</th><th>Status</th><th>Changes</th></tr></thead>
          <tbody>{beats.map((hb) => (
            <tr key={hb.id}>
              <td><code>#{hb.id}</code></td>
              <td><span style={{...num, fontWeight: 600, color: '#2563EB'}}>{hb.tier}</span></td>
              <td style={{...num, fontSize: 12}}>{fmtTime(hb.timestamp)}</td>
              <td style={num}>{hb.durationMs}ms</td>
              <td><span style={{color: hb.status === 'ok' ? '#059669' : '#B91C1C', fontWeight: 700}}>{hb.status === 'ok' ? '✓ ' : '✗ '}{String(hb.status).toUpperCase()}</span></td>
              <td style={{fontSize: 12.5, color: '#475569'}}>{hb.changeCount} detected</td>
            </tr>))}
          </tbody>
        </table></div>
      ) : <NotAvailable title="Sentinel heartbeats" reason={hbV.error} />}
    </div>
  )
}

export function SchedulerTable({overview}) {
  const schV = view(overview, 'scheduler')
  return (
    <div style={{marginBottom: 24}}>
      <SectionHead title="Scheduler / Sentinel" stamp={schV.updated_at} sub={schV.ok ? <>Loop {schV.data.loopRunning ? 'running' : 'STOPPED'} · tick every {Math.round(schV.data.tickMs / 1000)}s · last scheduler heartbeat {fmtTime(schV.data.lastHeartbeat && schV.data.lastHeartbeat.tickAt)}</> : null} />
      {schV.ok ? (
        <div style={{overflowX: 'auto'}}><table className="cs-diffs-table">
          <thead><tr><th>Job</th><th>Last status</th><th>Last run</th><th>Next run</th><th>Failures</th><th>Reason</th></tr></thead>
          <tbody>{(schV.data.jobs || []).map((j) => (
            <tr key={j.name}>
              <td><code>{j.name}</code></td>
              <td>{j.lastStatus === 'OK' ? <span style={{color: '#059669', fontWeight: 700}}>✓ OK</span> : <Chip label={`[NOT AVAILABLE] ${j.lastStatus}`} />}</td>
              <td style={{...num, fontSize: 12}}>{fmtTime(j.lastRunAt)}</td>
              <td style={{...num, fontSize: 12}}>{fmtTime(j.nextRunAt)}</td>
              <td style={num}>{j.consecutiveFailures}</td>
              <td style={{fontSize: 12, color: '#64748B'}}>{j.lastError || ''}</td>
            </tr>))}
          </tbody>
        </table></div>
      ) : <NotAvailable title="Scheduler" reason={schV.error} />}
    </div>
  )
}

export const panelBox = box

// Marks static case-study content (the September 2026 intervention record) so it is never mistaken for live worker telemetry.
export function HistoricalNotice() {
  return (
    <div style={{display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 12, color: '#64748B', background: '#F9FAFB', border: '1px solid #E5E7EB', borderRadius: 6, padding: '8px 12px', marginBottom: 14}}>
      <Chip label="[HISTORICAL · STATIC]" />
      <span>A static record of a past intervention. It is not current worker telemetry and the worker does not validate it.</span>
    </div>
  )
}
