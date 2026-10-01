import React from 'react'
import {view, fmtTime} from '../useSeoOverview.js'
import {Chip, NotAvailable, SectionHead, Unavailable, OpportunityModelUnavailable, RankMovementAndSerp, GrowthConstraintsEditorial} from './SeoShared.jsx'

const box = {background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: '8px'}
const num = {fontFamily: 'var(--font-mono)'}

export default function SeoSearchIntelPanel({overview, status, error, growthConstraints}) {
  if (!overview) {
    return (
      <div className="cs-diffs-table-wrap">
        {status === 'loading'
          ? <div style={{...box, padding: 16, fontSize: 13, color: '#64748B'}}>Reading the SEO worker&apos;s persisted state…</div>
          : <NotAvailable title="SEO intelligence" reason={`${error || 'SEO worker unavailable'}. No values are shown because none were returned.`} />}
      </div>
    )
  }
  const gscV = view(overview, 'gsc_summary')
  const sigV = view(overview, 'signals')
  const snapV = view(overview, 'gsc_snapshots')
  const ciV = view(overview, 'competitive_intel')
  const ccV = view(overview, 'authority')
  const gsc = gscV.ok ? gscV.data.snapshot : null
  const sig = sigV.ok ? sigV.data : null
  const ctrSignal = sig && (sig.signals || []).find((s) => s.type === 'CTR_BENCHMARK')
  const snapshot = snapV.ok && Array.isArray(snapV.data) && snapV.data.length ? snapV.data[snapV.data.length - 1] : null

  return (
    <div className="cs-diffs-table-wrap">
      {/* GSC telemetry */}
      {gsc ? (
        <>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '6px'}}>
            {[
              ['GSC Total Impressions', gsc.totalImpressions.toLocaleString(), '[OBSERVED]', `${gsc.startDate} → ${gsc.endDate}`],
              ['GSC Total Clicks', gsc.totalClicks.toLocaleString(), '[OBSERVED]', `${gsc.queryRowCount} query rows disclosed`],
              ['Average CTR', `${(gsc.averageCtr * 100).toFixed(2)}%`, '[CALCULATED]', ctrSignal && ctrSignal.calculatedMetrics && typeof ctrSignal.calculatedMetrics.ctrDelta === 'number' ? `${ctrSignal.calculatedMetrics.ctrDelta >= 0 ? '+' : ''}${(ctrSignal.calculatedMetrics.ctrDelta * 100).toFixed(1)} pts vs configured benchmark` : 'clicks ÷ impressions'],
              ['Average SERP Position', gsc.averagePosition.toFixed(2), '[OBSERVED]', 'impression-weighted · all pages'],
            ].map(([t, v, p, sub]) => (
              <div key={t} style={{...box, padding: '12px'}}>
                <div style={{fontSize: '11.5px', color: '#64748B', fontWeight: 600}}>{t}</div>
                <div style={{fontSize: '20px', fontWeight: 800, color: '#0F172A', marginTop: '4px'}}>{v}</div>
                <div style={{fontSize: '11px', color: '#64748B', marginTop: '4px', display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap'}}><Chip label={p} /><span>{sub}</span></div>
              </div>
            ))}
          </div>
          <div style={{fontSize: '11.5px', color: '#64748B', marginBottom: '18px', fontFamily: 'var(--font-mono)'}}>{gscV.data.provenance} · snapshot captured {fmtTime(gsc.capturedAt)} · {gsc.snapshotId}</div>
        </>
      ) : <Unavailable v={gscV} title="Google Search Console telemetry" />}

      {/* Search Signals Engine */}
      {sig ? (
        <div style={{marginBottom: '24px'}}>
          <SectionHead
            title={`Actionable SEO Signals & Evidence Provenance (${sig.signalsCount})`}
            stamp={sigV.updated_at}
            sub={<>Defensible intelligence distinguishing <strong>Directly Observed</strong> facts, <strong>Calculated</strong> derivations, and <strong>Inferred</strong> hypotheses. Window {sig.observationWindow}{sig.sampleSize && sig.sampleSize.isSmallSample ? ' · small sample flagged by the engine' : ''}.</>}
          />
          <div style={{display: 'grid', gap: '14px'}}>
            {(sig.signals || []).map((s) => {
              const confColor = s.confidence === 'HIGH' ? '#047857' : s.confidence === 'MEDIUM' ? '#1D4ED8' : '#B45309'
              const confBg = s.confidence === 'HIGH' ? '#D1FAE5' : s.confidence === 'MEDIUM' ? '#DBEAFE' : '#FEF3C7'
              return (
                <div key={s.id} style={{background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '8px', padding: '16px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)'}}>
                  <div style={{display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: '8px'}}>
                    <div style={{display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap'}}>
                      <span style={{fontSize: '11px', fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#64748B'}}>{s.id}</span>
                      <Chip label={s.provenance} />
                      <strong style={{fontSize: '14px', color: '#0F172A'}}>{s.title}</strong>
                    </div>
                    <span style={{fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background: confBg, color: confColor}}>Confidence: {s.confidence}</span>
                  </div>
                  <p style={{fontSize: '12.5px', color: '#334155', margin: '0 0 10px 0', lineHeight: 1.5}}>{s.summary}</p>
                  <div style={{display: 'grid', gap: '8px', marginBottom: '10px'}}>
                    <div style={{fontSize: '12px', background: '#F8FAFC', borderLeft: '3px solid #0284C7', padding: '8px 12px', borderRadius: '0 6px 6px 0'}}>
                      <strong style={{color: '#0369A1'}}>1. Directly Observed (GSC Fact):</strong> <span style={{color: '#334155'}}>{s.observedEvidence}</span>
                    </div>
                    <div style={{fontSize: '12px', background: '#F8FAFC', borderLeft: '3px solid #7C3AED', padding: '8px 12px', borderRadius: '0 6px 6px 0'}}>
                      <strong style={{color: '#6D28D9'}}>2. Calculated Metrics:</strong> <span style={{color: '#334155'}}>{Object.entries(s.calculatedMetrics || {}).map(([k, v]) => `${k}: ${v}`).join(' · ')}</span>
                      {s.externalBenchmark ? (
                        <div style={{fontSize: '11.5px', color: '#6B21A8', marginTop: '6px', borderTop: '1px dashed #E9D5FF', paddingTop: '6px'}}>
                          <div><strong>Benchmark Reference:</strong> {s.externalBenchmark.source}{s.externalBenchmark.provenanceNote ? <> — <em>{s.externalBenchmark.provenanceNote}</em></> : null}</div>
                          <div style={{fontSize: '11px', color: '#7E22CE', marginTop: '3px'}}>Population: {s.externalBenchmark.population || 'n/a'} · Device: {s.externalBenchmark.device || 'n/a'} · Geo: {s.externalBenchmark.geography || 'n/a'} · Version: {s.externalBenchmark.dateVersion || 'n/a'}</div>
                        </div>
                      ) : null}
                    </div>
                    <div style={{fontSize: '12px', background: '#FFFBEB', borderLeft: '3px solid #D97706', padding: '8px 12px', borderRadius: '0 6px 6px 0'}}>
                      <strong style={{color: '#B45309'}}>3. Analytical Inference:</strong> <span style={{color: '#78350F'}}>{s.inference}</span>
                      <div style={{fontSize: '11px', color: '#92400E', marginTop: '3px'}}><strong>Confidence Rationale:</strong> {s.confidenceRationale}</div>
                    </div>
                  </div>
                  <div style={{fontSize: '12px', color: '#0F172A', background: '#F0FDF4', padding: '10px 14px', borderRadius: '6px', border: '1px solid #BBF7D0'}}>
                    <strong style={{color: '#15803D'}}>Deterministic Action:</strong> <span>{s.actionableRemediation}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : <Unavailable v={sigV} title="Search Signals Engine" />}

      {/* Device + landing page footprint, from the persisted GSC snapshot */}
      <h4 style={{fontSize: '14.5px', fontWeight: 700, marginBottom: '10px', color: '#0F172A'}}>Device Search Intent &amp; Landing Page Footprint</h4>
      {snapshot ? (
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px', marginBottom: '20px'}}>
          <div style={{background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '8px', padding: '12px'}}>
            <div style={{fontSize: '12px', fontWeight: 700, color: '#475569', marginBottom: '8px'}}>Device Breakdown <Chip label="[OBSERVED]" /></div>
            {(snapshot.deviceRows || []).map((d, i) => (
              <div key={d.device} style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: i === 0 ? '1px solid #F1F5F9' : 'none', gap: 8, flexWrap: 'wrap'}}>
                <span style={{fontSize: '13px', fontWeight: 600, color: '#0F172A'}}>{d.device}</span>
                <span style={{fontSize: '12px', ...num, color: '#475569'}}>{d.clicks} clicks · {d.impressions} imps ({(d.ctr * 100).toFixed(1)}% CTR) · Pos {Number(d.position).toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div style={{background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '8px', padding: '12px'}}>
            <div style={{fontSize: '12px', fontWeight: 700, color: '#475569', marginBottom: '8px'}}>Surfaced Landing Pages in SERP <Chip label="[OBSERVED]" /></div>
            {(snapshot.pageRows || []).map((p) => (
              <div key={p.page} style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', gap: 8, flexWrap: 'wrap'}}>
                <code style={{fontSize: '12px', color: '#2563EB'}}>{p.page}</code>
                <span style={{fontSize: '12px', ...num, color: '#475569'}}>{p.clicks} clicks · {p.impressions} imps · Pos {Number(p.position).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : <Unavailable v={snapV} title="Device and landing-page breakdown" />}

      {/* Query-level data: the privacy state and the table, both from the snapshot */}
      {snapshot && (snapshot.queryRows || []).length > 0 ? (
        <>
          <h4 style={{fontSize: '14.5px', fontWeight: 700, marginBottom: '10px', color: '#0F172A'}}>Discovered Queries (GSC Performance) <Chip label="[OBSERVED]" /></h4>
          <table className="cs-diffs-table" style={{marginBottom: 16}}>
            <thead><tr><th>Search Query</th><th>Impressions</th><th>Clicks</th><th>Average Position</th></tr></thead>
            <tbody>{snapshot.queryRows.map((q) => (<tr key={q.query}><td><strong>{q.query}</strong></td><td style={num}>{q.impressions}</td><td style={num}>{q.clicks}</td><td style={{...num, fontWeight: 700, color: '#00838F'}}>{Number(q.position).toFixed(2)}</td></tr>))}</tbody>
          </table>
        </>
      ) : snapshot ? (
        <div style={{...box, padding: '16px 20px', marginBottom: '16px'}}>
          <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: 8}}>
            <h4 style={{fontSize: '14px', fontWeight: 700, color: '#0F172A', margin: 0}}>🔒 GSC Query-Level Data: Withheld Under Privacy Anonymization <Chip label="[OBSERVED]" /></h4>
            <span style={{fontSize: '11px', fontWeight: 700, background: '#E2E8F0', color: '#475569', padding: '3px 8px', borderRadius: '4px'}}>{(snapshot.queryRows || []).length} query rows disclosed</span>
          </div>
          <p style={{fontSize: '13px', color: '#475569', margin: '0 0 10px 0', lineHeight: 1.5}}>Google Search Console returned <strong>0 query dimension rows</strong> for this reporting window. Under Google&apos;s searcher privacy filtering threshold, individual query strings are withheld; query-level positions are not approximated from page or site data.</p>
          <div style={{fontSize: '12px', color: '#64748B', display: 'flex', gap: '16px', flexWrap: 'wrap'}}>
            <span><strong>API Property:</strong> <code>{snapshot.siteUrl}</code></span>
            <span><strong>Window:</strong> {snapshot.dateRange && `${snapshot.dateRange.startDate} → ${snapshot.dateRange.endDate}`}</span>
            <span><strong>Observed Totals:</strong> {snapshot.totalClicks} clicks / {snapshot.totalImpressions} impressions</span>
          </div>
        </div>
      ) : null}

      {/* SEO Opportunity Model: no persisted source exists, so nothing is modeled here */}
      <div style={{background: '#FAF5FF', border: '1px solid #E9D5FF', borderRadius: '8px', padding: '16px 20px', marginBottom: '16px'}}>
        <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: 8}}>
          <h4 style={{fontSize: '14px', fontWeight: 700, color: '#581C87', margin: 0}}>🎯 SEO Opportunity Model — Not GSC Observed <Chip label="[MODELED]" /></h4>
        </div>
        <OpportunityModelUnavailable />
      </div>

      <div style={{marginTop: '24px', ...box, padding: '16px'}}>
        <RankMovementAndSerp overview={overview} />
      </div>

      {/* Competitor sitemap footprint */}
      <div style={{marginTop: '24px', background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '8px', padding: '16px'}}>
        {ciV.ok ? (() => {
          const obs = ciV.data.sitemapObservations || []
          const okCount = obs.filter((o) => o.status === 'POLL_OK').length
          const name = (id) => ((ciV.data.competitors || []).find((c) => (c.id || c.competitorId) === id) || {}).name || id
          return (
            <>
              <SectionHead title="Competitor Sitemap Footprint" chip={ciV.data.provenance} stamp={ciV.updated_at} sub={<><strong>{okCount}/{obs.length}</strong> competitor sitemaps polled successfully.</>} />
              <table className="cs-diffs-table">
                <thead><tr><th>Competitor</th><th>Sitemap</th><th>Poll</th><th>URLs</th><th>Reason</th></tr></thead>
                <tbody>{obs.map((o) => (
                  <tr key={o.competitorId}>
                    <td><strong>{name(o.competitorId)}</strong></td>
                    <td><code style={{fontSize: 11}}>{o.sitemapUrl.replace('https://', '')}</code></td>
                    <td>{o.status === 'POLL_OK' ? <Chip label="POLL_OK" /> : <Chip label="POLL_FAILED" />}</td>
                    <td style={num}>{o.status === 'POLL_OK' ? o.totalUrls.toLocaleString() : 'NOT AVAILABLE'}</td>
                    <td style={{fontSize: 11.5, color: '#64748B'}}>{o.status === 'POLL_OK' ? '' : o.error}</td>
                  </tr>))}
                </tbody>
              </table>
              {ciV.data.keywordGapsStatus === 'NOT_AVAILABLE' ? <NotAvailable title="Competitor keyword gaps" reason={ciV.data.keywordGapsUnavailableReason} /> : null}
              {ciV.data.backlinkStatus && ciV.data.backlinkStatus.status === 'NOT AVAILABLE' ? <NotAvailable title="Backlink counts and third-party domain authority" reason={ciV.data.backlinkStatus.reason} /> : null}
            </>
          )
        })() : <Unavailable v={ciV} title="Competitor sitemap footprint" />}
      </div>

      {/* Common Crawl reference graph */}
      <div style={{marginTop: '24px', background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '8px', padding: '16px'}}>
        {ccV.ok ? (
          <>
            <SectionHead title="Common Crawl Reference Graph" chip={ccV.data.provenance} stamp={ccV.updated_at} sub={<>Release {ccV.data.rows[0] && ccV.data.rows[0].releaseId}. A domain reference signal, <strong>not</strong> a backlink count.</>} />
            <table className="cs-diffs-table">
              <thead><tr><th>Domain</th><th>In graph</th><th>Harmonic-centrality rank</th><th>PageRank rank</th><th>Hosts</th></tr></thead>
              <tbody>{[...ccV.data.rows].sort((a, b) => Number(b.inGraph) - Number(a.inGraph) || (a.harmonicPos || 0) - (b.harmonicPos || 0)).map((r) => (
                <tr key={r.domain}>
                  <td><strong>{r.domain}</strong></td>
                  <td>{r.inGraph ? <Chip label="IN GRAPH" /> : <Chip label="[NOT AVAILABLE] not in graph" />}</td>
                  <td style={num}>{r.inGraph ? r.harmonicPos.toLocaleString() : '—'}</td>
                  <td style={num}>{r.inGraph ? r.pagerankPos.toLocaleString() : '—'}</td>
                  <td style={num}>{r.inGraph ? r.nHosts : '—'}</td>
                </tr>))}
              </tbody>
            </table>
          </>
        ) : <Unavailable v={ccV} title="Common Crawl reference graph" />}
      </div>

      {/* Strategic Growth Constraints: editorial analysis, not worker data */}
      <div style={{marginTop: '24px', background: '#FFFFFF', border: '1px solid #FDE68A', borderRadius: '8px', padding: '16px'}}>
        <GrowthConstraintsEditorial items={growthConstraints} />
      </div>
    </div>
  )
}
