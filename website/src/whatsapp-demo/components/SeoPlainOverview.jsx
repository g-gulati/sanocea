import React, {useState} from 'react'
import {view, gscNumbers, latestHeartbeat, fmtTime} from '../useSeoOverview.js'
import {NotAvailable} from './SeoShared.jsx'
import {opportunitiesFrom, STATUS_GUIDE, STEP_GUIDE} from '../seoOpportunities.js'
import OpportunityLifecycle, {LifecycleDots} from './OpportunityLifecycle.jsx'

// The customer-facing PRIMARY layer of SEO & Commerce Audit. Reading order:
//   measured reality -> interpretation -> attention -> autonomous monitoring -> limitations; technical evidence is a
//   separate collapsed layer (SanoceaCaseStudyView). Plain business language only: no SEO jargon, no provenance codes
//   here. Every number and page name comes from the shared SEO store (the worker's persisted state). A card whose
//   source signal is missing is omitted, never invented, and any capability without a source is listed as
//   "not switched on yet" rather than estimated.

const card = {background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 12, padding: '16px 18px'}
const mut = {color: '#64748B'}
const secTitle = {fontSize: 15, fontWeight: 800, color: '#0F172A', margin: '26px 0 10px'}
const grid2 = {display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14}

const dayLabel = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', {month: 'short', day: 'numeric', timeZone: 'UTC'})
const when = (iso) => (iso ? new Date(iso).toLocaleString('en-US', {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}) : null)
const ago = (iso) => { const m = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000)); return m < 90 ? `${m} min ago` : `${Math.round(m / 60)} h ago` }
const sigOf = (overview, type) => { const v = view(overview, 'signals'); return v.ok ? (v.data.signals || []).find((s) => s.type === type) : null }

function Pill({tone, children}) {
  const t = {opp: ['#EFF6FF', '#1D4ED8'], att: ['#FFFBEB', '#92400E'], ok: ['#ECFDF5', '#047857'], na: ['#F1F5F9', '#475569']}[tone]
  return <span style={{display: 'inline-block', fontSize: 11, fontWeight: 700, background: t[0], color: t[1], borderRadius: 99, padding: '2px 9px', marginRight: 8}}>{children}</span>
}

// The page the visibility signal says is not appearing, taken from the signal's own evidence text.
function unsurfacedPage(sig) {
  const m = sig && /Unsurfaced in GSC:\s*(https?:\/\/\S+)/.exec(sig.observedEvidence || '')
  if (!m) return null
  const url = m[1].replace(/\)$/, '')
  const path = url.replace(/^https?:\/\/(www\.)?/, '')
  const last = path.split('/').filter(Boolean).pop() || path
  return {address: path, name: last.replace(/[-_]/g, ' ')}
}

const ROLE_LABEL = {
  TECHNICAL_SEO: 'Checking your site every hour', ANALYTICS_MANAGER: 'Reading your Google results',
  COMPETITIVE_INTELLIGENCE: 'Checking competitor sites', SEO_STRATEGIST: 'Summarising what the evidence supports',
  KEYWORD_RESEARCHER: ['Finding search terms and how many people search them', 'We would show which words your customers use and how popular they are.'],
  AEO_SPECIALIST: ['Checking whether Google highlights your content', 'We would show if Google puts your content in the highlighted box at the top of results.'],
  GEO_SPECIALIST: ['Checking whether AI assistants like ChatGPT mention you', 'We would show whether they name your site when shoppers ask them.'],
  LINK_BUILDING_MANAGER: ['Finding other sites that link to you', 'We would show who links to you and how trusted your site looks.'],
  CONTENT_OPTIMIZER: ['Improving the headline and summary shown for each page', 'We would suggest better wording for how your pages appear in Google.'],
  AI_CONTENT_AUDITOR: ['Reading your pages the way a crawler without JavaScript does', 'We would flag pages that show little text before JavaScript runs.'],
}
// Plain-English line built only from the numbers the worker measured; says nothing if it measured no pages.
function auditorText(x) {
  const pages = x && x.details && Array.isArray(x.details.pages) ? x.details.pages : null
  if (!pages || !pages.length) return x && x.outputSummary ? x.outputSummary : ''
  const thin = pages.filter((p) => p.staticWords < 100).length
  const retired = pages.filter((p) => (p.retiredSchemaTypes || []).length).length
  return `Read ${pages.length} of your pages as the server sends them, before any JavaScript runs. ${thin} of ${pages.length} contain almost no readable text that way, which is all that crawlers skipping JavaScript can read.${retired ? ` ${retired} carry FAQ or how-to markup that Google no longer shows (harmless).` : ''}`
}
const RUN_ORDER = ['TECHNICAL_SEO', 'ANALYTICS_MANAGER', 'COMPETITIVE_INTELLIGENCE', 'AI_CONTENT_AUDITOR', 'SEO_STRATEGIST']

const PILL = {neutral: {background: '#F1F5F9', color: '#475569'}, warn: {background: '#FFFBEB', color: '#B45309'}, ok: {background: '#ECFDF5', color: '#047857'}, info: {background: '#F1F5F9', color: '#2563EB'}}
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`
function breakdown(items) {
  const n = (label) => items.filter((i) => i.pill && i.pill.label === label).length
  const parts = [[n('Needs your decision'), 'needs one decision from you', 'need decisions from you'], [n('Needs a person'), 'needs a person', 'need a person'], [n('Investigating'), 'being investigated', 'being investigated'],
    [n('Monitoring'), 'being monitored after a change', 'being monitored after a change'], [n('Completed'), 'completed', 'completed'], [n('Needs review'), 'needs your review', 'need your review']].filter(([c]) => c > 0)
  return parts.map(([c, one, many]) => (c === 1 ? `1 ${one}` : `${c} ${many}`)).join(' · ')
}

// Section 5 operational view: the real opportunities from the worker (views.opportunities), one expandable row each.
// No priority, severity or score is shown: the order is the worker's deterministic order and means nothing about importance.
function OpportunityQueue({items, updatedAt}) {
  const [open, setOpen] = useState(() => new Set())
  const toggle = (key) => setOpen((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next })
  const label = {fontSize: 11, fontWeight: 800, letterSpacing: '.04em', textTransform: 'uppercase', color: '#64748B', marginBottom: 2}
  if (!items.length) {
    return <div style={{...mut, fontSize: 13}}>SANOCEA has not found anything to review in its latest checks{updatedAt ? ` (last checked ${when(updatedAt)})` : ''}.</div>
  }
  return (
    <div id="seo-opportunities">
      <div style={{display: 'flex', flexWrap: 'wrap', gap: '8px 14px', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4}}>
        <b style={{fontSize: 17}}>{items.length === 1 ? '1 thing needs attention' : `${items.length} things need attention`}</b>
        <span style={{...mut, fontSize: 12}}>{breakdown(items)}{updatedAt ? ` · last checked ${when(updatedAt)}` : ''}</span>
      </div>
      <div style={{...mut, fontSize: 12, marginBottom: 4}}>Open one to see how SANOCEA got from what it found to what it did. SANOCEA changes your website on its own only for low-risk fixes its policy permits; nothing on this page changes it.</div>
      {items.map((it, idx) => {
        const isOpen = open.has(it.key)
        const bodyId = `opp-body-${idx}`
        return (
          <div key={it.key} style={{borderTop: idx ? '1px solid #E2E8F0' : 'none'}}>
            <button type="button" aria-expanded={isOpen} aria-controls={bodyId} onClick={() => toggle(it.key)}
              style={{all: 'unset', boxSizing: 'border-box', width: '100%', cursor: 'pointer', padding: '10px 0', display: 'grid', gridTemplateColumns: '1fr auto auto', gap: '4px 10px', alignItems: 'start'}}>
              <span style={{fontWeight: 700}}>{it.title}</span>
              <span style={{fontSize: 11.5, fontWeight: 700, borderRadius: 99, padding: '2px 10px', whiteSpace: 'nowrap', ...PILL[(it.pill && it.pill.tone) || 'neutral']}}>{it.pill ? it.pill.label : it.status}</span>
              <span aria-hidden="true" style={{color: '#64748B', alignSelf: 'center', display: 'inline-block', transform: isOpen ? 'rotate(90deg)' : 'none'}}>›</span>
              {it.sub ? <span style={{gridColumn: '1 / 2', color: '#64748B', fontSize: 12}}>{it.checkedAt ? `${it.observedVerb} ${it.checkedAt} · ` : ''}{it.sub}</span> : null}
              {it.lifecycle ? <span style={{gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 10, color: '#64748B', fontSize: 12}}><LifecycleDots stages={it.lifecycle.stages} /><span>{it.lifecycle.summary}</span></span> : null}
            </button>
            {isOpen ? (
              <div id={bodyId} style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '10px 18px', padding: '2px 0 14px'}}>
                {it.lifecycle ? <OpportunityLifecycle lifecycle={it.lifecycle} /> : null}
                {it.lifecycle ? (
                  <details style={{gridColumn: '1 / -1', borderTop: '1px dashed #E2E8F0', paddingTop: 6}}>
                    <summary style={{cursor: 'pointer', fontSize: 12, color: '#64748B'}}>The evidence behind this</summary>
                    <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '10px 18px', paddingTop: 8}}>
                      <div><div style={label}>Opportunity</div><div>{it.what}</div></div>
                      <div><div style={label}>Evidence</div><div>{it.evidence}</div></div>
                      <div><div style={label}>Why it matters</div><div>{it.why}</div></div>
                      <div><div style={label}>Status</div><div>{it.pill ? it.pill.label : it.status}{it.status === 'Needs review' ? ' · nothing has been changed' : ''}</div></div>
                      <div style={{gridColumn: '1 / -1', background: '#ECFDF5', color: '#047857', borderRadius: 6, padding: '7px 11px'}}><b>Recommended action:</b> {it.action}</div>
                    </div>
                  </details>
                ) : (<>
                <div><div style={label}>Opportunity</div><div>{it.what}</div></div>
                <div><div style={label}>Evidence</div><div>{it.evidence}</div></div>
                <div><div style={label}>Why it matters</div><div>{it.why}</div></div>
                <div><div style={label}>Status</div><div>{it.pill ? it.pill.label : it.status}{it.status === 'Needs review' ? ' · nothing has been changed' : ''}</div></div>
                <div style={{gridColumn: '1 / -1', background: '#ECFDF5', color: '#047857', borderRadius: 6, padding: '7px 11px'}}><b>Recommended action:</b> {it.action}</div>
                </>)}
                {it.checkedAt ? <div><div style={label}>Last checked</div><div>{it.checkedAt}</div></div> : null}
                {it.tech.length ? (
                  <details style={{gridColumn: '1 / -1', borderTop: '1px dashed #E2E8F0', paddingTop: 6}}>
                    <summary style={{cursor: 'pointer', fontSize: 12, color: '#64748B'}}>Technical details</summary>
                    <dl style={{margin: '6px 0 0', display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '3px 12px', fontSize: 12}}>
                      {it.tech.map(([k, v]) => (<React.Fragment key={k}><dt style={{color: '#64748B'}}>{k}</dt><dd style={{margin: 0, overflowWrap: 'anywhere'}}>{v}</dd></React.Fragment>))}
                    </dl>
                  </details>
                ) : null}
              </div>
            ) : null}
          </div>
        )
      })}
      <details style={{marginTop: 12, borderTop: '1px solid #E2E8F0', paddingTop: 8}}>
        <summary style={{cursor: 'pointer', fontSize: 12, color: '#64748B'}}>What the six steps mean</summary>
        <dl style={{margin: '8px 0 0', display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '6px 12px', fontSize: 12}}>
          {STEP_GUIDE.map(([k, v]) => (<React.Fragment key={k}><dt style={{fontWeight: 700}}>{k}</dt><dd style={{margin: 0, color: '#64748B'}}>{v}</dd></React.Fragment>))}
        </dl>
        <div style={{marginTop: 10, fontSize: 12, color: '#64748B'}}>What the statuses mean</div>
        <dl style={{margin: '8px 0 0', display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '6px 12px', fontSize: 12, alignItems: 'center'}}>
          {STATUS_GUIDE.map(([k, v]) => (<React.Fragment key={k}><dt><span style={{fontSize: 11.5, fontWeight: 700, color: '#475569', background: '#F1F5F9', borderRadius: 99, padding: '2px 10px'}}>{k}</span></dt><dd style={{margin: 0, color: '#64748B'}}>{v}</dd></React.Fragment>))}
        </dl>
      </details>
    </div>
  )
}

export default function SeoPlainOverview({overview, status, error}) {
  if (!overview) {
    return (
      <div style={{...card, marginBottom: 16}}>
        {status === 'loading' ? <span style={mut}>Reading your latest search results…</span>
          : <NotAvailable title="Your search visibility" reason={`${error || 'The SEO service is unavailable'}. Nothing is shown because nothing was returned.`} />}
      </div>
    )
  }
  const g = gscNumbers(overview)
  const moveV = view(overview, 'rank_movement_gsc')
  const site = moveV.ok && moveV.data.site && moveV.data.site.trajectories ? moveV.data.site.trajectories[0] : null
  const snapV = view(overview, 'gsc_snapshots')
  const snap = snapV.ok && Array.isArray(snapV.data) && snapV.data.length ? snapV.data[snapV.data.length - 1] : null
  const dev = {}; (snap ? snap.deviceRows || [] : []).forEach((r) => { dev[r.device] = r })
  const hb = latestHeartbeat(overview)
  const rosterV = view(overview, 'agent_roster')
  const roster = rosterV.ok ? rosterV.data.roster || [] : []
  const ciV = view(overview, 'competitive_intel')
  const serpV = view(overview, 'serp_rank_movement')
  const sFoot = sigOf(overview, 'SERP_FOOTPRINT'); const sVel = sigOf(overview, 'SEARCH_VELOCITY'); const sPriv = sigOf(overview, 'PRIVACY_THRESHOLD')
  const page = unsurfacedPage(sFoot)
  const opps = opportunitiesFrom(overview)
  // The same fact reported by Google's URL Inspection is already an opportunity above; do not list it twice.
  const googleCoversPage = opps.ok && opps.items.some((i) => i.key.startsWith('GOOGLE_INDEX_STATUS_ISSUE|'))
  const hasPageSignal = Boolean(sFoot && sFoot.calculatedMetrics.unsurfacedCommercialRoutesCount > 0 && !googleCoversPage)
  const hasPrivSignal = Boolean(sPriv && sPriv.calculatedMetrics.queryRowsAvailable === 0)
  const pts = site ? site.points || [] : []
  const maxShown = pts.reduce((m, p) => Math.max(m, p.impressions), 1)
  // Every roster entry is counted exactly once: known roles get plain-English labels, any other role still appears
  // (with a generic label and the worker's own summary), so the two lists always add up to the roster.
  const completed = roster.filter((x) => x.status === 'COMPLETED')
  const done = [...RUN_ORDER.map((r) => completed.find((x) => x.role === r)).filter(Boolean), ...completed.filter((x) => !RUN_ORDER.includes(x.role))]
  const waiting = roster.filter((x) => x.status !== 'COMPLETED')
  const labelOf = (x) => (typeof ROLE_LABEL[x.role] === 'string' ? ROLE_LABEL[x.role] : Array.isArray(ROLE_LABEL[x.role]) ? ROLE_LABEL[x.role][0] : 'Another check')
  const waitLabel = (x) => (Array.isArray(ROLE_LABEL[x.role]) ? ROLE_LABEL[x.role] : ['Another check', 'This check is not switched on yet.'])
  const nextReview = roster.reduce((m, x) => (x.nextScheduledAt && x.nextScheduledAt > m ? x.nextScheduledAt : m), '')
  const okSites = ciV.ok ? (ciV.data.sitemapObservations || []).filter((o) => o.status === 'POLL_OK').length : null
  const totalSites = ciV.ok ? (ciV.data.sitemapObservations || []).length : null

  const doneText = {
    TECHNICAL_SEO: hb ? `Last check ${when(hb.timestamp)}: ${hb.status === 'ok' ? 'everything responded normally' : 'a problem was reported'}, ${hb.changeCount} changes found.` : 'No check result is available yet.',
    ANALYTICS_MANAGER: g ? `Read the latest Google figures for your site: ${g.impressions} times shown and ${g.clicks} visits.` : 'No Google figures are available yet.',
    COMPETITIVE_INTELLIGENCE: okSites === null ? 'No competitor result is available yet.' : `Read the public page lists of ${okSites} of ${totalSites} competitors.${okSites < totalSites ? ` ${totalSites - okSites} blocked the check.` : ''}`,
    AI_CONTENT_AUDITOR: auditorText(roster.find((x) => x.role === 'AI_CONTENT_AUDITOR')),
    SEO_STRATEGIST: 'Pulled the findings together and marked which parts are measured, which are worked out from measured numbers, and which are our reasoning.',
  }

  // Limitations: each listed only while its source is genuinely missing.
  const rosterOff = (role) => roster.some((x) => x.role === role && x.status !== 'COMPLETED')
  const limits = [
    serpV.ok && serpV.data.status === 'NOT_AVAILABLE' && ['Where you rank for specific searches', 'It would show how you stack up for the exact words customers type.', 'Needs a paid service we have not added, and Google hides these searches at your size.'],
    rosterOff('KEYWORD_RESEARCHER') && ['How many people search for your key terms, and what they want', 'It would size the demand for what you sell and show what shoppers are after.', 'Needs a service we have not added, and Google hides your searches. We do not guess.'],
    rosterOff('GEO_SPECIALIST') && ['Whether AI assistants like ChatGPT mention you', 'More shoppers now ask AI assistants instead of searching.', 'The service that checks this has not been added yet.'],
    rosterOff('AEO_SPECIALIST') && ['Whether Google highlights your content', 'Google sometimes shows one answer in a highlighted box above all results.', 'Needs a service we have not added yet.'],
    ciV.ok && ciV.data.keywordGapsStatus === 'NOT_AVAILABLE' && ['How you rank against competitors', 'It would show which searches competitors win that you do not.', 'We can see how big their sites are, but where they rank needs a paid service.'],
    ciV.ok && ciV.data.backlinkStatus && ciV.data.backlinkStatus.status === 'NOT AVAILABLE' && ['Who links to you, and how trusted your site looks', 'Links from trusted sites help you rank.', 'Needs a paid service we have not added.'],
    rosterOff('CONTENT_OPTIMIZER') && ['The wording of your page titles and summaries', 'It would suggest better wording for how your pages appear in Google.', 'The check is not switched on yet.'],
  ].filter(Boolean)

  return (
    <div id="seo-plain-overview" style={{marginBottom: 8}}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap', marginBottom: 6}}>
        <div>
          <h2 style={{fontSize: 22, fontWeight: 800, margin: 0, color: '#0F172A'}}>Your search visibility</h2>
          {g ? <div style={{...mut, fontSize: 12.5}}>SANOCEA.com · Google, {dayLabel(g.startDate)} to {dayLabel(g.endDate)}</div> : null}
        </div>
        {hb ? <span style={{fontSize: 12.5, color: '#047857', background: '#ECFDF5', padding: '4px 10px', borderRadius: 99}}>● We check your site every hour · last check {ago(hb.timestamp)}</span> : null}
      </div>

      {/* 1. How visible are we? */}
      <div style={secTitle}>1. How visible are we?</div>
      {g ? (
        <div style={{...card, borderLeft: '5px solid #0284C7'}}>
          <p style={{fontSize: 20, fontWeight: 800, margin: '0 0 4px', color: '#0F172A'}}>Your site is showing up in Google.</p>
          <p style={{...mut, margin: 0, fontSize: 14}}>It appeared {g.impressions} times in the last 28 days, and when it did, it usually showed up as roughly the {Math.round(g.position)}{Math.round(g.position) === 1 ? 'st' : Math.round(g.position) === 2 ? 'nd' : Math.round(g.position) === 3 ? 'rd' : 'th'} result (average position {g.position.toFixed(2)}; 1 would be the very top). That is an early, small sample, so it is a promising start rather than a trend.</p>
        </div>
      ) : <NotAvailable title="How visible you are on Google" reason="No Google figures were returned." />}

      {/* 2. Are people finding us and clicking? */}
      <div style={secTitle}>2. Are people finding us and clicking?</div>
      {g ? (
        <div style={grid2}>
          <div style={card}><div style={{fontSize: 30, fontWeight: 800}}>{g.clicks}</div><div style={{fontWeight: 700, fontSize: 13}}>People are clicking through from Google</div><div style={{...mut, fontSize: 12.5, marginTop: 4}}>{g.clicks} visits to your site from those {g.impressions} appearances.</div></div>
          <div style={card}><div style={{fontSize: 30, fontWeight: 800}}>{(g.ctr * 100).toFixed(2)}%</div><div style={{fontWeight: 700, fontSize: 13}}>A high share of searchers clicked</div><div style={{...mut, fontSize: 12.5, marginTop: 4}}>{g.clicks} of the {g.impressions} who saw your site clicked. That is a good start, but with so few people, one or two clicks more or less would change this a lot, so it is not yet a reliable pattern.</div></div>
        </div>
      ) : null}

      {/* 3. Is visibility improving or declining? */}
      <div style={secTitle}>3. Is visibility improving or declining?</div>
      {site && pts.length ? (
        <div style={grid2}>
          <div style={card}>
            <div style={{fontWeight: 700, fontSize: 14}}>Times your site was shown, day by day</div>
            <div style={{...mut, fontSize: 12}}>The {pts.length} days we have data for</div>
            <div style={{display: 'flex', alignItems: 'flex-end', gap: 6, height: 90, margin: '8px 0 2px'}}>
              {pts.map((p) => (
                <div key={p.date} title={`${dayLabel(p.date)}: shown ${p.impressions} times, ${p.clicks} visits`} style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%'}}>
                  <i style={{display: 'block', width: '100%', height: `${Math.max(6, Math.round((p.impressions / maxShown) * 100))}%`, background: '#0284C7', borderRadius: '4px 4px 0 0', opacity: 0.85}} />
                  <span style={{fontSize: 10.5, color: '#64748B'}}>{p.date.slice(8)}</span>
                </div>
              ))}
            </div>
            <div style={{...mut, fontSize: 11.5}}>Day of the month. Hover a bar for details.</div>
          </div>
          <div style={card}>
            <div style={{fontWeight: 700, fontSize: 14, marginBottom: 6}}>{site.lowSample ? 'There is not enough data yet to call this a trend' : 'How your position has moved'}</div>
            <p style={{margin: 0, fontSize: 14}}>Your average position was {site.start.position.toFixed(1)} on {dayLabel(site.start.date)} and {site.current.position.toFixed(1)} on {dayLabel(site.current.date)}{site.current.position > site.start.position ? ', a small slip' : site.current.position < site.start.position ? ', a small improvement' : ', unchanged'}.{site.lowSample ? ` On those days your site was shown only ${site.start.impressions} and ${site.current.impressions} times, so please treat this as something to watch, not a result.` : ''}</p>
          </div>
        </div>
      ) : <NotAvailable title="How your visibility is changing" reason={moveV.error || 'No day-by-day figures were returned.'} />}

      {/* 4. What did SANOCEA find? */}
      <div style={secTitle}>4. What did SANOCEA find?</div>
      <div style={grid2}>
        {sFoot && sFoot.calculatedMetrics.unsurfacedCommercialRoutesCount > 0 ? <div style={card}><b>Only {sFoot.calculatedMetrics.surfacedCommercialRoutesCount === 1 ? 'one' : sFoot.calculatedMetrics.surfacedCommercialRoutesCount} of your {sFoot.calculatedMetrics.totalIndexableCommercialRoutes === 2 ? 'two' : sFoot.calculatedMetrics.totalIndexableCommercialRoutes} main pages is appearing in search</b><p style={{...mut, margin: '4px 0 0', fontSize: 13}}>Your homepage gets all your Google visibility. {page ? `Your ${page.name} page (${page.address}) has not appeared in any searches yet.` : 'Your other main page has not appeared in any searches yet.'}</p></div> : null}
        {dev.DESKTOP && dev.MOBILE && g ? <div style={card}><b>{dev.DESKTOP.impressions >= dev.MOBILE.impressions ? 'Most people find you on a computer' : 'Most people find you on a phone'}</b><p style={{...mut, margin: '4px 0 0', fontSize: 13}}>{dev.DESKTOP.impressions} of your {g.impressions} appearances were on desktop and {dev.MOBILE.impressions} on mobile. With so few, this is a first impression, not a firm profile of your shoppers.</p></div> : null}
        {sPriv && sPriv.calculatedMetrics.queryRowsAvailable === 0 ? <div style={card}><b>Google is hiding what people searched for</b><p style={{...mut, margin: '4px 0 0', fontSize: 13}}>For privacy, Google does not share the exact phrases when only a few people use them. You can see how many people found you, but not what they typed.</p></div> : null}
        {sVel ? <div style={card}><b>Your presence is still small</b><p style={{...mut, margin: '4px 0 0', fontSize: 13}}>About {Math.round(sVel.calculatedMetrics.dailyAverageImpressions) === 1 ? 'one appearance' : `${Math.round(sVel.calculatedMetrics.dailyAverageImpressions)} appearances`} a day over the last 28 days. It is early days.</p></div> : null}
      </div>

      {/* 5. What needs attention? Real opportunities first (no priority labels), existing signals kept below. */}
      <div style={secTitle}>5. What needs attention?</div>
      <div style={card}>
        {opps.ok ? <OpportunityQueue items={opps.items} updatedAt={opps.updatedAt} /> : null}
        {hasPageSignal || sVel || hasPrivSignal ? (
          <div style={opps.ok && opps.items.length ? {borderTop: '1px solid #E2E8F0', marginTop: 12, paddingTop: 12} : null}>
            {opps.ok && opps.items.length ? <div style={{fontSize: 12, fontWeight: 800, color: '#64748B', marginBottom: 4}}>Also worth knowing</div> : null}
            {hasPageSignal ? (
              <div style={{paddingBottom: 10}}><Pill tone="opp">We found a page that needs attention</Pill><b>{page ? `Your ${page.name} page (${page.address}) is not appearing in search` : 'One of your main pages is not appearing in search'}</b>
                <div style={{fontSize: 13, background: '#ECFDF5', color: '#047857', borderRadius: 6, padding: '6px 10px', marginTop: 6}}><b>What to do:</b> Ask your web team to check three things: that Google has picked up this page, that your site tells Google the page exists, and that your homepage links to it.</div></div>
            ) : null}
            {sVel ? <div style={{borderTop: hasPageSignal ? '1px solid #E2E8F0' : 'none', padding: '10px 0'}}><Pill tone="att">Keep watching</Pill><b>Your presence on Google is still small</b>
              <div style={{fontSize: 13, background: '#ECFDF5', color: '#047857', borderRadius: 6, padding: '6px 10px', marginTop: 6}}><b>What to do:</b> We will track it week by week. When you add new pages, make sure your web team tells Google about them.</div></div> : null}
            {hasPrivSignal ? <div style={{borderTop: hasPageSignal || sVel ? '1px solid #E2E8F0' : 'none', paddingTop: 10}}><Pill tone="att">Good to know</Pill><b>You cannot see which searches find you yet</b>
              <div style={{fontSize: 13, background: '#ECFDF5', color: '#047857', borderRadius: 6, padding: '6px 10px', marginTop: 6}}><b>What to do:</b> Use page and device trends for now. The exact phrases will appear as your numbers grow.</div></div> : null}
          </div>
        ) : null}
      </div>

      {/* 6. What is SANOCEA doing about it? (the product differentiator: kept prominent) */}
      <div style={secTitle}>6. What is SANOCEA doing about it?</div>
      <div style={{...card, borderLeft: '5px solid #0284C7', marginBottom: 14}}>
        <p style={{fontSize: 16, fontWeight: 800, margin: '0 0 4px', color: '#0F172A'}}>SANOCEA keeps checking your site, works out what the evidence shows, and tells you what needs attention.</p>
        <p style={{...mut, margin: 0, fontSize: 13}}>SANOCEA reads, checks and reports. Nothing on this page changes your website.{nextReview ? ` Next full review: ${when(nextReview)}.` : ''}</p>
      </div>
      <div style={grid2}>
        <div style={card}>
          <div style={{fontWeight: 800, fontSize: 14, marginBottom: 6}}>Running now ({done.length} of {roster.length} checks)</div>
          {done.length ? done.map((x) => (
            <div key={x.role} style={{borderTop: '1px solid #E2E8F0', padding: '8px 0'}}><Pill tone="ok">Done</Pill><b style={{fontSize: 13.5}}>{labelOf(x)}</b><div style={{...mut, fontSize: 12.5, marginTop: 2}}>{doneText[x.role] || x.outputSummary || ''}</div></div>
          )) : <div style={{...mut, fontSize: 13}}>No completed checks were reported.</div>}
        </div>
        <div style={{...card, background: '#F8FAFC'}}>
          <div style={{fontWeight: 700, fontSize: 13, color: '#475569'}}>Not switched on yet ({waiting.length} checks)</div>
          <div style={{...mut, fontSize: 12, margin: '2px 0 6px'}}>These need an outside service that has not been set up yet. Nothing here needs action from you. Until then they show nothing rather than guess.</div>
          {waiting.map((x) => (
            <div key={x.role} title={waitLabel(x)[1]} style={{borderTop: '1px solid #E2E8F0', padding: '5px 0', fontSize: 12.5, color: '#64748B'}}>{waitLabel(x)[0]}</div>
          ))}
        </div>
      </div>

      {/* 7. Limitations: deliberately low visual weight; each item expands for its reason */}
      {limits.length ? (
        <div style={{marginTop: 22, background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 10, padding: '10px 14px'}}>
          <div style={{fontSize: 13, fontWeight: 700, color: '#475569'}}>7. Not switched on yet</div>
          <div style={{fontSize: 12, color: '#64748B', margin: '2px 0 6px'}}>Things SANOCEA cannot tell you yet. They are not problems with your site. Open one to see why.</div>
          {limits.map(([name, why, reason]) => (
            <details key={name} style={{borderTop: '1px solid #E2E8F0'}}>
              <summary style={{cursor: 'pointer', fontSize: 12.5, color: '#475569', padding: '6px 0'}}>{name}</summary>
              <div style={{fontSize: 12, color: '#64748B', padding: '0 0 8px 14px'}}><b>Why it matters:</b> {why}<br /><b>Why we cannot show it:</b> {reason}</div>
            </details>
          ))}
        </div>
      ) : null}
    </div>
  )
}
