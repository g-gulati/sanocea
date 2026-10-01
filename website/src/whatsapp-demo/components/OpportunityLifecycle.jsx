import React from 'react'

// Section 5: the lifecycle of one opportunity (Found -> Concluded -> Selected -> Policy decision -> Executed -> Verified).
// Presentation only: every sentence comes from the worker's lifecycle (seoOpportunities.js -> lifecycleOf). A step the worker
// did not supply is not drawn. Tokens follow the approved design proposal and the existing SeoPlainOverview inline styles.

const T = {
  ink: '#0F172A', mut: '#64748B', line: '#E2E8F0', soft: '#F1F5F9', softInk: '#475569', call: '#ECFDF5',
  done: '#047857', blocked: '#B45309', current: '#2563EB', wait: '#CBD5E1', warnBg: '#FFFBEB', card: '#FFFFFF',
  marker: 18, text: 13, radius: 12, gap: 14,
}
const MARK = {done: '✓', blocked: '!', current: '', waiting: '', not_applicable: '–'}
const fill = (state) => (state === 'done' ? T.done : state === 'blocked' ? T.blocked : state === 'current' ? T.current : 'transparent')

// The six-dot progress strip shown on every row (collapsed or open).
export function LifecycleDots({stages}) {
  return (
    <span role="img" aria-label={`Progress: ${stages.map((s) => `${s.label} ${s.state.replace('_', ' ')}`).join(', ')}`} style={{display: 'inline-flex', gap: 4}}>
      {stages.map((s) => (
        <i key={s.key || s.label} style={{width: 9, height: 9, borderRadius: '50%', display: 'inline-block', background: s.state === 'waiting' ? T.wait : s.state === 'not_applicable' ? 'transparent' : fill(s.state),
          border: s.state === 'not_applicable' ? `1.5px dashed ${T.wait}` : 'none'}} />
      ))}
    </span>
  )
}

function Step({s, last}) {
  const hollow = s.state === 'waiting' || s.state === 'not_applicable'
  return (
    <li style={{display: 'grid', gridTemplateColumns: `${T.marker}px 1fr`, gap: 12, position: 'relative', paddingBottom: last ? 0 : T.gap}}>
      {!last ? <span aria-hidden="true" style={{position: 'absolute', left: T.marker / 2 - 1, top: T.marker + 2, bottom: 2, width: 2, background: T.line}} /> : null}
      <span aria-hidden="true" style={{width: T.marker, height: T.marker, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: T.marker * 0.62, fontWeight: 800,
        color: s.state === 'not_applicable' ? T.mut : '#fff', background: hollow ? 'transparent' : fill(s.state), border: s.state === 'waiting' ? `2px solid ${T.wait}` : s.state === 'not_applicable' ? `1.5px dashed ${T.wait}` : 'none'}}>
        {MARK[s.state]}
      </span>
      <div style={{minWidth: 0}}>
        <div style={{fontSize: 11, fontWeight: 800, letterSpacing: '.04em', textTransform: 'uppercase', color: T.mut, display: 'flex', gap: 10, flexWrap: 'wrap'}}>
          <span>{s.label}</span>{s.at ? <span style={{fontWeight: 600, textTransform: 'none', letterSpacing: 0}}>{s.at}</span> : null}
        </div>
        <div style={{fontWeight: hollow ? 600 : 700, color: hollow ? T.mut : T.ink, overflowWrap: 'anywhere'}}>{s.headline}</div>
        {s.detail ? <div style={{color: T.mut, fontSize: T.text - 1, marginTop: 2, overflowWrap: 'anywhere'}}>{s.detail}</div> : null}
      </div>
    </li>
  )
}

// The one question SANOCEA cannot settle by observing. Read-only here: an answer is recorded by the owner through SANOCEA, never from this page.
function DecisionCard({decision}) {
  return (
    <div style={{border: `1.5px solid ${T.blocked}`, background: T.warnBg, borderRadius: T.radius, padding: '14px 16px', marginBottom: 6}}>
      <div style={{fontSize: 11, fontWeight: 800, letterSpacing: '.04em', textTransform: 'uppercase', color: T.blocked}}>One decision needed from you</div>
      <div style={{fontSize: 16, fontWeight: 800, margin: '4px 0'}}>{decision.question}</div>
      <div style={{color: T.mut, fontSize: 12.5, marginBottom: 10}}>{decision.why} Your answer is recorded and SANOCEA continues on its own.</div>
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 12}}>
        {decision.options.map((o) => (
          <div key={o.address} style={{background: T.card, border: `1px solid ${T.line}`, borderRadius: T.radius - 2, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6}}>
            <div style={{fontWeight: 800, fontFamily: 'var(--font-mono, ui-monospace, Menlo, monospace)', fontSize: 12.5, overflowWrap: 'anywhere'}}>{o.address}</div>
            <div style={{alignSelf: 'flex-start', fontSize: 11, fontWeight: 700, borderRadius: 99, padding: '2px 9px', color: o.needsServerChange ? T.blocked : T.done, background: o.needsServerChange ? T.warnBg : T.call}}>
              {o.needsServerChange ? 'Needs a web-server change' : 'No server change needed'}
            </div>
            <ul style={{margin: 0, paddingLeft: 16, color: T.mut, fontSize: 12}}>{o.signals.map((x) => <li key={x}>{x}</li>)}</ul>
            <div style={{fontSize: 12}}>{o.consequence}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function OpportunityLifecycle({lifecycle}) {
  if (!lifecycle) return null
  return (
    <div style={{gridColumn: '1 / -1'}}>
      {lifecycle.decision ? <DecisionCard decision={lifecycle.decision} /> : null}
      <div style={{fontSize: 11, fontWeight: 800, letterSpacing: '.04em', textTransform: 'uppercase', color: T.mut, margin: '14px 0 8px'}}>How SANOCEA got here</div>
      <ol style={{listStyle: 'none', margin: 0, padding: 0, fontSize: T.text}}>
        {lifecycle.stages.map((s, i) => <Step key={s.key || s.label} s={s} last={i === lifecycle.stages.length - 1} />)}
      </ol>
    </div>
  )
}
