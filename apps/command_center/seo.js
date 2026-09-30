/* SEO Intelligence tab (light theme only).
 *
 * Data: ONE authenticated call, GET /internal/seo/overview, served by packages/seo_bridge from the SEO worker's
 * persisted endpoints. It is Sanocea's OWN internal SEO tenant, not a merchant: there is no merchant id in the URL. Opening this tab never calls a provider and never mutates anything.
 *
 * Truth rules enforced here:
 *  - Every number on screen is derived from the backend response; nothing is defaulted, estimated or invented.
 *  - GSC average position and LIVE SERP RANK MOVEMENT are separate capabilities with separate provenance. The SERP panel
 *    is never populated from GSC data.
 *  - Common Crawl data is a domain reference signal, never labelled backlinks.
 *  - A missing/failed view renders NOT AVAILABLE with the reason, never a zero.
 *  - Access: decided by the backend from the key class alone (service or internal-operator keys only; every
 *    single-merchant key gets 403). The tab is shown only when this authenticated probe succeeds, independently of
 *    which merchant is selected. Everything is keyed on the API key; a response that arrives after the key changed
 *    is discarded.
 *
 * Integration: loaded after app.js. It relies only on the globals STATE, apiCall and switchTab/renderActiveTab and does
 * not modify app.js.
 */
(function () {
  'use strict';

  const TTL_MS = 5000;
  const cache = { apiKey: null, at: 0, overview: null, error: null, inflight: null };
  const ui = { level: 'site' };

  // ---- helpers ------------------------------------------------------------------------------------------------
  const esc = (v) => String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const int = (n) => Number(n).toLocaleString('en-US');
  const ts = (iso) => (iso ? esc(String(iso).replace('T', ' ').replace(/(\+00:00|Z)$/, 'Z').replace(/:\d\d(\.\d+)?Z$/, 'Z')) : '—');
  const dayDiff = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
  const view = (o, name) => (o.views && o.views[name]) || { ok: false, error: 'view missing from response' };

  const STATE_LABEL = { green: 'LIVE-VERIFIED', amber: 'AMBER', na: 'NOT AVAILABLE', danger: 'FAILED' };
  function pill(state, label) {
    return `<span class="seo-pill" data-state="${state}"><span class="seo-pill-ico" aria-hidden="true"></span>${esc(label || STATE_LABEL[state])}</span>`;
  }
  function viewError(v, what) {
    return `<div class="seo-empty"><p><strong>${esc(what)}: NOT AVAILABLE.</strong> ${esc(v.error || 'no data returned')}.</p></div>`;
  }
  function card(title, pillHtml, body, extra) {
    return `<section class="card" ${extra || ''}><div class="card-header"><h3 class="card-title">${esc(title)}</h3>${pillHtml || ''}</div>${body}</section>`;
  }

  // ---- data loading -------------------------------------------------------------------------------------------
  async function load(force) {
    const apiKey = STATE.apiKey;
    if (!apiKey) return { apiKey, overview: null, error: null };
    const fresh = cache.apiKey === apiKey && Date.now() - cache.at < TTL_MS;
    if (fresh && !force) return { apiKey, overview: cache.overview, error: cache.error };
    if (cache.inflight && cache.inflight.apiKey === apiKey) return cache.inflight.promise;
    const promise = (async () => {
      let overview = null;
      let error = null;
      try {
        overview = await apiCall('/internal/seo/overview');
      } catch (e) {
        error = e && e.message ? e.message : String(e);
      }
      cache.apiKey = apiKey; cache.at = Date.now(); cache.overview = overview; cache.error = error; cache.inflight = null;
      return { apiKey, overview, error };
    })();
    cache.inflight = { apiKey, promise };
    return promise;
  }

  function setTabVisible(visible) {
    const btn = document.getElementById('tab-btn-seo');
    if (btn) btn.style.display = visible ? '' : 'none';
    if (!visible && STATE.activeTab === 'seo' && typeof window.switchTab === 'function') window.switchTab('overview');
  }

  // The tab is visible iff the caller is authorized. 200 = authorized and data available. 503 = authorized (the
  // authorization check runs first) but the worker is down, so the tab is shown and renders the failure. 401/403
  // (no key, or a single-merchant key) and anything else: hidden.
  async function probe() {
    const r = await load(false);
    if (r.apiKey !== STATE.apiKey) return; // key changed meanwhile: discard
    setTabVisible(Boolean((r.overview && r.overview.monitored === true) || (r.error && /^API 503/.test(r.error))));
  }

  // ---- components ---------------------------------------------------------------------------------------------
  function chart(t) {
    const pts = t.points || [];
    if (pts.length === 0) return '';
    const W = 620, H = 178, L = 44, R = 14, T = 14, B = 44;
    const first = pts[0].date, last = pts[pts.length - 1].date;
    const span = Math.max(1, dayDiff(first, last));
    const x = (d) => L + (dayDiff(first, d) / span) * (W - L - R);
    const positions = pts.map((p) => p.position);
    const yMin = Math.max(0.5, Math.min(...positions) - 0.5);
    const yMax = Math.max(yMin + 1, Math.max(...positions) + 0.5);
    const y = (p) => T + ((p - yMin) / (yMax - yMin)) * (H - T - B);
    const out = [`<svg class="seo-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily GSC average position, observed days only" data-testid="seo-gsc-chart">`];
    for (let g = Math.ceil(yMin); g <= Math.floor(yMax); g++) {
      out.push(`<line x1="${L}" x2="${W - R}" y1="${y(g).toFixed(1)}" y2="${y(g).toFixed(1)}" class="seo-grid-line"/><text x="${L - 8}" y="${(y(g) + 4).toFixed(1)}" class="seo-axis" text-anchor="end">${g}</text>`);
    }
    out.push(`<text x="${L - 8}" y="${T - 3}" class="seo-axis" text-anchor="end">better ↑</text>`);
    const observed = new Set(pts.map((p) => p.date));
    if (span <= 45) {
      for (let i = 0; i <= span; i++) {
        const d = new Date(Date.parse(first) + i * 86400000).toISOString().slice(0, 10);
        if (observed.has(d)) out.push(`<text x="${x(d).toFixed(1)}" y="${H - 24}" class="seo-axis" text-anchor="middle">${d.slice(8)}</text>`);
        else out.push(`<line x1="${x(d).toFixed(1)}" x2="${x(d).toFixed(1)}" y1="${H - 40}" y2="${H - 32}" class="seo-gap"/>`);
      }
    } else {
      out.push(`<text x="${L}" y="${H - 24}" class="seo-axis">${esc(first)}</text><text x="${W - R}" y="${H - 24}" class="seo-axis" text-anchor="end">${esc(last)}</text>`);
    }
    out.push(`<text x="${L}" y="${H - 6}" class="seo-axis">${esc(first)} → ${esc(last)} · ticks = dates with no impressions, so no observation (not interpolated, not read as “>100”)</text>`);
    // connect only consecutive calendar days: a line across a gap would imply data that does not exist
    let run = [];
    const flush = () => { if (run.length > 1) out.push(`<polyline class="seo-line" points="${run.map((p) => `${x(p.date).toFixed(1)},${y(p.position).toFixed(1)}`).join(' ')}"/>`); run = []; };
    pts.forEach((p) => { if (run.length && dayDiff(run[run.length - 1].date, p.date) !== 1) flush(); run.push(p); });
    flush();
    pts.forEach((p) => {
      const low = p.impressions < 5;
      out.push(`<circle cx="${x(p.date).toFixed(1)}" cy="${y(p.position).toFixed(1)}" r="${(3 + Math.sqrt(p.impressions) * 1.3).toFixed(1)}" class="seo-dot${low ? ' low' : ''}"><title>${esc(p.date)}: avg position ${p.position.toFixed(2)} · ${p.impressions} impression${p.impressions === 1 ? '' : 's'}${low ? ' · low sample' : ''}</title></circle>`);
    });
    out.push('</svg>');
    return out.join('');
  }

  function trajectoryBlock(t, showTitle) {
    const span = dayDiff(t.start.date, t.current.date) + 1;
    const moveText = t.movementSinceStart === null
      ? 'first observation, so there is nothing to compare yet'
      : t.movementSinceStart > 0 ? `position number fell from ${t.start.position.toFixed(1)} to ${t.current.position.toFixed(1)}, so it moved up (better)`
        : t.movementSinceStart < 0 ? `position number rose from ${t.start.position.toFixed(1)} to ${t.current.position.toFixed(1)}, so it moved down (worse)`
          : 'unchanged since the first observation';
    const moveBig = t.movementSinceStart === null ? 'N/A' : (t.movementSinceStart > 0 ? '▲ ' : t.movementSinceStart < 0 ? '▼ ' : '') + Math.abs(t.movementSinceStart).toFixed(2);
    const step = (label, p, extra, cls) => `<div class="seo-step ${cls || ''}"><span>${label}</span><strong>${p ? p.position.toFixed(1) : 'N/A'}</strong><em>${p ? `${p.impressions} impr · ${esc(p.date)}${extra || ''}` : 'no earlier observation'}</em></div>`;
    return `
      ${showTitle ? `<div class="seo-traj-title">${esc(t.key)}</div>` : ''}
      <div class="seo-traj">
        ${step('Start', t.start, t.observationDays === 1 ? ' · first observation' : '')}
        <div class="seo-arrow" aria-hidden="true">→</div>
        ${step('Previous', t.previous)}
        <div class="seo-arrow" aria-hidden="true">→</div>
        ${step('Current', t.current, '', 'current')}
        <div class="seo-move"><span>Movement since start</span><strong>${moveBig}</strong><em>${esc(moveText)}</em></div>
      </div>
      ${t.lowSample ? `<div class="seo-flag"><span aria-hidden="true">⚠</span> <strong>Low sample.</strong> Start and current points rest on ${t.start.impressions} and ${t.current.impressions} impression${t.current.impressions === 1 ? '' : 's'}, so this movement is noise-level. ${t.observationDays} observed day${t.observationDays === 1 ? '' : 's'} of ${span}; the other ${span - t.observationDays} had no impressions.</div>` : ''}
      ${chart(t)}
      <div class="seo-key"><span><i></i> 5+ impressions</span><span><i class="low"></i> under 5 impressions (low sample)</span><span>Dot size = impressions</span><span>Y axis: 1 is best</span></div>`;
  }

  // ---- panels -------------------------------------------------------------------------------------------------
  function legendPanel() {
    return `
      <section class="card">
        <div class="card-header"><h3 class="card-title">How to read every panel</h3></div>
        <div class="seo-legend-grid">
          <div>${pill('green')}<p>Returned by a real external source and verified live. Shows the source, date and method.</p></div>
          <div>${pill('amber', 'AMBER · UNVERIFIED')}<p>Implemented and tested with fakes, but it depends on a provider, credential or deployment that has not been verified live. No values are shown until it is.</p></div>
          <div>${pill('na')}<p>Cannot be obtained honestly at zero cost. Shown as an empty state with the exact dependency. Never filled in.</p></div>
        </div>
      </section>`;
  }

  function kpiCard(label, value, small, sub, pillHtml) {
    return `<div class="kpi-card"><div class="kpi-label">${label}</div><div class="kpi-value">${value} <small style="font-size:12px;font-weight:500;color:var(--text-muted);">${small}</small></div><div class="kpi-sub">${sub}</div><div class="seo-kpi-pill">${pillHtml}</div></div>`;
  }

  function kpis(o) {
    const g = view(o, 'gsc_summary'), ci = view(o, 'competitive_intel'), au = view(o, 'authority'), sc = view(o, 'scheduler');
    const cards = [];

    if (!g.ok) cards.push(kpiCard('Own site · GSC', '—', '', esc(g.error), pill('na')));
    else if (!g.data.snapshot) cards.push(kpiCard('Own site · GSC', '—', '', 'No GSC snapshot has been stored.', pill('na')));
    else {
      const s = g.data.snapshot;
      cards.push(kpiCard(`Own site · GSC snapshot ${esc(s.startDate)} → ${esc(s.endDate)}`, int(s.totalImpressions), 'impressions',
        `${int(s.totalClicks)} clicks · CTR ${(s.averageCtr * 100).toFixed(2)}% · average position ${s.averagePosition.toFixed(2)}`,
        g.data.live ? pill('green') : pill('amber', 'AMBER · NOT LIVE')));
    }

    if (!ci.ok) cards.push(kpiCard('Competitor sitemaps', '—', '', esc(ci.error), pill('na')));
    else {
      const obs = ci.data.sitemapObservations || [];
      const ok = obs.filter((x) => x.status === 'POLL_OK');
      const failed = obs.filter((x) => x.status !== 'POLL_OK');
      const urls = ok.reduce((n, x) => n + x.totalUrls, 0);
      const sub = obs.length === 0 ? 'No sitemap has been polled yet.'
        : `${int(urls)} public URLs.${failed.length ? ' ' + failed.map((f) => `${esc(f.competitorDomain)} not polled${f.httpStatus ? ` (HTTP ${f.httpStatus})` : ''}`).join('; ') + '.' : ''}`;
      cards.push(kpiCard('Competitor sitemaps', String(ok.length), `of ${obs.length} polled`, sub,
        obs.length === 0 ? pill('na') : ok.length === obs.length ? pill('green') : ok.length === 0 ? pill('na') : pill('amber', `AMBER · ${ok.length} OF ${obs.length}`)));
    }

    if (!au.ok) cards.push(kpiCard('Common Crawl reference graph', '—', '', esc(au.error), pill('na')));
    else {
      const rows = au.data.rows || [];
      const rel = rows.length ? rows[0].releaseId : null;
      const cur = rows.filter((r) => r.releaseId === rel);
      const inG = cur.filter((r) => r.inGraph);
      const notIn = cur.filter((r) => !r.inGraph);
      cards.push(kpiCard('Common Crawl reference graph', rel ? String(inG.length) : '—', rel ? `of ${cur.length} domains in graph` : '',
        rel ? `Release ${esc(rel)}${notIn.length ? ' · ' + notIn.map((r) => esc(r.domain)).join(', ') + ' not in graph' : ''}` : 'No release has been fetched yet.', rel ? pill('green') : pill('na')));
    }

    if (!sc.ok) cards.push(kpiCard('Scheduler', '—', '', esc(sc.error), pill('na')));
    else {
      const jobs = sc.data.jobs || [];
      const cnt = (s) => jobs.filter((j) => j.lastStatus === s).length;
      const alive = schedulerAlive(sc.data);
      const detail = [`${cnt('OK')} OK`, cnt('UNAVAILABLE') ? `${cnt('UNAVAILABLE')} unavailable` : '', cnt('FAILED') ? `${cnt('FAILED')} failed` : '', jobs.filter((j) => !j.lastStatus).length ? `${jobs.filter((j) => !j.lastStatus).length} not yet run` : ''].filter(Boolean).join(' · ');
      cards.push(kpiCard('Scheduler', String(jobs.length), `jobs · ${detail}`,
        alive ? 'Loop running with a fresh heartbeat.' : 'No fresh scheduler heartbeat: the loop is not confirmed running.', alive ? pill('green') : pill('amber', 'AMBER · NOT RUNNING')));
    }
    return `<div class="seo-kpis">${cards.join('')}</div>`;
  }

  function schedulerAlive(s) {
    const hb = s.lastHeartbeat;
    return Boolean(s.loopRunning && hb && typeof hb.ageMs === 'number' && hb.ageMs <= Math.max(5 * (s.tickMs || 30000), 120000));
  }

  function gscMovementPanel(o) {
    const v = view(o, 'rank_movement_gsc');
    const g = view(o, 'gsc_summary');
    const title = 'Own-site position movement';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'GSC position movement'));
    const d = v.data;
    const levels = [['site', 'Site', d.site, 'Site position'], ['pages', 'Pages', d.pages, 'Page position'], ['queries', 'Queries', d.queries, 'Query-level position']];
    const has = (lv) => lv && lv.trajectories && lv.trajectories.length > 0;
    const anyObserved = has(d.site) || has(d.pages) || has(d.queries);
    const live = g.ok && g.data.live;
    const headPill = !anyObserved ? pill('na') : live ? pill('green', 'LIVE-VERIFIED · GSC') : pill('amber', 'AMBER · NOT LIVE');
    if (!levels.some(([k]) => k === ui.level)) ui.level = 'site';
    const tabs = levels.map(([k, label, lv]) => `<button type="button" class="seo-level ${ui.level === k ? 'active' : ''}" onclick="window.seoSetLevel('${k}')">${label}${has(lv) ? '' : ' ' + pill('na')}</button>`).join('');
    const cur = levels.find(([k]) => k === ui.level)[2];
    let body;
    if (has(cur)) {
      body = cur.trajectories.slice(0, 5).map((t) => trajectoryBlock(t, ui.level !== 'site')).join('');
      if (cur.trajectories.length > 5) body += `<div class="seo-note">Showing the 5 highest-impression of ${cur.trajectories.length}.</div>`;
    } else {
      const imp = g.ok && g.data.snapshot ? `${int(g.data.snapshot.totalImpressions)} impressions` : 'the impressions it has recorded';
      body = `<div class="seo-empty"><p><strong>${esc(levels.find(([k]) => k === ui.level)[3])}: NOT AVAILABLE.</strong> ${esc((cur && cur.note) || 'No rows stored.')}</p>${ui.level === 'queries' ? `<p>GSC's ${esc(imp)} are not attributable to any single query at this privacy threshold. Not approximated from page or site data. Bing (needs a free key) may fill this.</p>` : ''}</div>`;
    }
    const inner = `
      <p class="seo-def">Google Search Console <strong>average position</strong> for our own property: an impression-weighted average per date. It is not an exact keyword rank and not a point-in-time SERP position. Provenance: <code>[OBSERVED: GSC AVERAGE POSITION]</code></p>
      <div class="seo-levels" role="tablist">${tabs}</div>${body}`;
    return card(title, headPill, inner, 'data-testid="seo-gsc-panel"');
  }

  function liveSerpPanel(o) {
    const v = view(o, 'serp_rank_movement');
    const title = 'Live SERP rank movement';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'Live SERP rank movement'), 'data-testid="seo-serp-panel"');
    const d = v.data;
    const def = `<p class="seo-def">Exact keyword positions from a SERP data source: Start → Previous → Current rank with daily and net delta. This is a <strong>separate capability</strong> from the GSC panel above: it is never populated from GSC average position, and nothing here is estimated or modelled. Provenance: <code>[OBSERVED: SERP PROVIDER]</code></p>`;
    if (d.status !== 'OBSERVED' || !d.rows || d.rows.length === 0) {
      const fields = ['Target query', 'Start rank', 'Previous rank', 'Current rank', 'Daily delta', 'Net delta', 'First observed', 'Last checked', 'Provider / methodology'];
      const providers = d.verifiedProviders && d.verifiedProviders.length ? d.verifiedProviders.map(esc).join(', ') : 'none';
      const ignored = d.ignoredRowCount > 0 ? `<p><strong>${int(d.ignoredRowCount)} stored row${d.ignoredRowCount === 1 ? '' : 's'} from unverified providers ${d.ignoredRowCount === 1 ? 'was' : 'were'} ignored</strong> and never shown as a rank.</p>` : '';
      return card(title, pill('na'), `${def}
        <div class="seo-empty" data-testid="seo-serp-empty">
          <p><strong>NOT AVAILABLE.</strong> ${esc(d.reason || 'No live SERP observation exists.')}</p>
          <p><strong>Dependency:</strong> ${esc(d.dependency || 'A verified SERP provider adapter.')}</p>
          <p>Verified providers connected: ${providers}.</p>${ignored}
        </div>
        <div class="seo-note" style="margin-top:10px;">Fields this panel will show once a verified provider exists (no values are shown until then):</div>
        <div class="seo-fields">${fields.map((f) => `<span class="seo-field">${f}</span>`).join('')}</div>`, 'data-testid="seo-serp-panel"');
    }
    const rows = d.rows.map((r) => `<tr>
      <td><strong>${esc(r.query)}</strong></td>
      <td class="seo-num">${esc(r.startRankFormatted)}</td><td class="seo-num">${esc(r.previousRankFormatted)}</td><td class="seo-num">${esc(r.currentRankFormatted)}</td>
      <td>${esc(r.dailyDeltaFormatted)}</td><td>${esc(r.netDeltaFormatted)}</td>
      <td>${ts(r.firstObservedAt)}</td><td>${ts(r.lastCheckedAt)}</td>
      <td><code class="seo-prov">${esc(r.provider)}</code><div class="seo-note">${esc(r.methodology)}</div></td></tr>`).join('');
    return card(title, pill('green', 'LIVE-VERIFIED · SERP PROVIDER'), `${def}
      <div class="table-container"><table><thead><tr><th>Target query</th><th>Start rank</th><th>Previous rank</th><th>Current rank</th><th>Daily Δ</th><th>Net Δ</th><th>First observed</th><th>Last checked</th><th>Provider / methodology</th></tr></thead><tbody>${rows}</tbody></table></div>`, 'data-testid="seo-serp-panel"');
  }

  function sitemapPanel(o) {
    const v = view(o, 'competitive_intel');
    const title = 'Competitor sitemap footprint';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'Competitor sitemaps'));
    const obs = v.data.sitemapObservations || [];
    const ok = obs.filter((x) => x.status === 'POLL_OK');
    const headPill = obs.length === 0 ? pill('na') : ok.length === obs.length ? pill('green') : ok.length === 0 ? pill('na') : pill('amber', `AMBER · ${ok.length} OF ${obs.length}`);
    const baseline = ok.length ? ok.map((x) => x.polledAt).sort()[0].slice(0, 10) : null;
    const rows = obs.map((x) => {
      const isOk = x.status === 'POLL_OK';
      return `<tr><td><strong>${esc(x.competitorDomain)}</strong>${x.error ? `<div class="seo-note">${esc(x.error)}</div>` : ''}</td>
        <td>${pill(isOk ? 'green' : x.status === 'DEGRADED' ? 'amber' : 'na', x.status)}</td>
        <td class="seo-num">${isOk ? int(x.totalUrls) : '—'}</td>
        <td class="seo-num">${isOk ? (x.diffedAgainstPrevious ? `+${x.newlyDiscoveredUrls.length} / −${x.removedUrls.length}` : 'baseline') : '—'}</td>
        <td class="seo-num">${x.httpStatus ?? '—'}</td></tr>`;
    }).join('');
    const gaps = v.data.keywordGapsStatus === 'OBSERVED' ? '' : `<div class="seo-note" style="margin-top:8px;">Competitor keyword gaps: NOT AVAILABLE. ${esc(v.data.keywordGapsUnavailableReason || '')}</div>`;
    return card(title, headPill, `
      <p class="seo-def">URLs listed in each competitor's public sitemap, diffed against the last successful snapshot. This is footprint only: it says nothing about rankings or traffic.${baseline ? ` First baseline set ${esc(baseline)}; "baseline" means no earlier snapshot to compare.` : ''} <code>[OBSERVED: SITEMAP FETCH]</code></p>
      ${obs.length ? `<div class="table-container"><table><thead><tr><th>Competitor</th><th>Poll</th><th>URLs</th><th>Δ vs previous</th><th>HTTP</th></tr></thead><tbody>${rows}</tbody></table></div>${gaps}` : '<div class="seo-empty"><p><strong>NOT AVAILABLE.</strong> No competitor sitemap has been polled yet.</p></div>'}`, 'data-testid="seo-sitemap-panel"');
  }

  function authorityPanel(o) {
    const v = view(o, 'authority');
    const title = 'Common Crawl domain reference signal';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'Common Crawl reference graph'));
    const rows = v.data.rows || [];
    if (!rows.length) return card(title, pill('na'), '<div class="seo-empty"><p><strong>NOT AVAILABLE.</strong> No Common Crawl release has been fetched yet.</p></div>');
    const rel = rows[0].releaseId;
    const cur = rows.filter((r) => r.releaseId === rel).sort((a, b) => (a.inGraph === b.inGraph ? (a.harmonicPos || 0) - (b.harmonicPos || 0) : a.inGraph ? -1 : 1));
    const body = cur.map((r) => r.inGraph
      ? `<tr><td><strong>${esc(r.domain)}</strong></td><td class="seo-num">${int(r.harmonicPos)}</td><td class="seo-num">${int(r.pagerankPos)}</td><td class="seo-num">${int(r.nHosts)}</td></tr>`
      : `<tr class="seo-row-na"><td><strong>${esc(r.domain)}</strong></td><td colspan="3"><span class="seo-na-text">Not in this release's graph</span> <span class="seo-note">— absence, not a zero score</span></td></tr>`).join('');
    return card(title, pill('green'), `
      <p class="seo-def"><strong>Not backlinks.</strong> Centrality of each domain in Common Crawl's domain-level hyperlink graph, one crawl release: a historical snapshot, not current. A lower rank number means more central. Domains absent from the release are shown as absent, never as zero. <code>[OBSERVED: COMMON CRAWL DOMAIN REFERENCE GRAPH]</code></p>
      <div class="table-container"><table><thead><tr><th>Domain</th><th>Harmonic rank</th><th>PageRank rank</th><th>Hosts</th></tr></thead><tbody>${body}</tbody></table></div>
      <div class="seo-source">Release <code>${esc(rel)}</code> · file last modified ${esc(cur[0].sourceLastModified || 'unknown')} · fetched ${ts(cur[0].fetchedAt)}</div>`, 'data-testid="seo-authority-panel"');
  }

  function schedulerPanel(o) {
    const v = view(o, 'scheduler');
    const title = 'Scheduler health';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'Scheduler'));
    const s = v.data;
    const alive = schedulerAlive(s);
    const hb = s.lastHeartbeat;
    const summaryFor = (name) => { const r = (s.recentRuns || []).find((x) => x.job === name && x.summary); return r ? r.summary : null; };
    const rows = (s.jobs || []).map((j) => {
      const st = j.lastStatus === 'OK' ? 'green' : j.lastStatus === 'UNAVAILABLE' ? 'na' : j.lastStatus === 'FAILED' ? 'danger' : 'amber';
      const detail = j.lastStatus === 'FAILED' || j.lastStatus === 'UNAVAILABLE' ? j.lastError : summaryFor(j.name);
      return `<tr><td><code class="seo-jobname">${esc(j.name)}</code></td><td>${pill(st, j.lastStatus || 'NOT YET RUN')}${j.overdue ? ' ' + pill('amber', 'OVERDUE') : ''}${j.consecutiveFailures ? `<div class="seo-note">${j.consecutiveFailures} consecutive failure${j.consecutiveFailures === 1 ? '' : 's'}</div>` : ''}</td><td class="seo-num">${ts(j.nextRunAt)}</td><td class="seo-note">${esc(detail || '—')}</td></tr>`;
    }).join('');
    return card(title, alive ? pill('green') : pill('amber', 'AMBER · NOT RUNNING'), `
      <div class="seo-hb"><span class="seo-hb-dot ${alive ? '' : 'stale'}"></span><strong>${alive ? 'Loop running' : 'Loop not confirmed running'}</strong><span class="seo-note">${hb ? `last heartbeat ${ts(hb.tickAt)}` : 'no heartbeat recorded'} · next runs are persisted, so a restart does not reset them</span></div>
      <div class="table-container"><table><thead><tr><th>Job</th><th>Last run</th><th>Next run</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="seo-note" style="margin-top:10px;"><strong>Unavailable is not a failure:</strong> a missing key or model is recorded with its reason and retried at the normal cadence. A thrown error or timeout is FAILED and retried with backoff.</div>`, 'data-testid="seo-scheduler-panel"');
  }

  function bingPanel(o) {
    const v = view(o, 'bing');
    const title = 'Bing Webmaster';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'Bing Webmaster'));
    const d = v.data;
    const traj = (d.queryPositions && d.queryPositions.trajectories) || [];
    const links = (d.linkCounts && d.linkCounts.rows) || [];
    if (!traj.length && !links.length) {
      return card(title, pill('amber', 'AMBER · UNVERIFIED'), `<div class="seo-empty amber"><p><strong>No values yet.</strong> ${d.configured ? 'A Bing API key is configured but no rows have been stored yet.' : 'Connector implemented and tested with fakes; never run against the live API. Needs a free <code>BING_WEBMASTER_API_KEY</code>.'} Would add own-site per-query positions and inbound link counts for our own pages only.</p></div>`, 'data-testid="seo-bing-panel"');
    }
    const trows = traj.slice(0, 8).map((t) => `<tr><td><strong>${esc(t.key)}</strong></td><td class="seo-num">${t.start.position.toFixed(1)}</td><td class="seo-num">${t.current.position.toFixed(1)}</td><td>${esc(t.movementFormatted)}</td><td class="seo-num">${t.current.impressions}</td></tr>`).join('');
    const lrows = links.slice(0, 8).map((l) => `<tr><td>${esc(l.pageUrl)}</td><td class="seo-num">${int(l.inboundLinks)}</td></tr>`).join('');
    return card(title, pill('green', 'LIVE-VERIFIED · BING'), `
      ${traj.length ? `<div class="table-container"><table><thead><tr><th>Query</th><th>Start</th><th>Current</th><th>Movement</th><th>Impr</th></tr></thead><tbody>${trows}</tbody></table></div><div class="seo-note">Bing average position <code>[OBSERVED: BING WEBMASTER AVERAGE POSITION]</code> for our own site.</div>` : ''}
      ${links.length ? `<div class="table-container" style="margin-top:10px;"><table><thead><tr><th>Own page</th><th>Inbound links (Bing)</th></tr></thead><tbody>${lrows}</tbody></table></div>` : ''}`, 'data-testid="seo-bing-panel"');
  }

  function modelPanel(o) {
    const v = view(o, 'model_visibility');
    const title = 'Model-specific AEO';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'Model-specific AEO'));
    const d = v.data;
    const models = d.models || [];
    const scope = `<div class="seo-scope">${esc(d.scopeNotice || 'Observed for the named model only.')}</div>`;
    if (!models.length) {
      return card(title, pill('amber', 'AMBER · UNVERIFIED'), `<div class="seo-empty amber"><p><strong>No observations yet.</strong> No model has been asked anything, so no visibility is claimed.</p></div>${scope}`, 'data-testid="seo-model-panel"');
    }
    const rows = models.map((m) => `<tr><td><code>${esc(m.modelAtHost)}</code></td><td class="seo-num">${int(m.samples)}</td><td class="seo-num">${int(m.mentions)}</td><td class="seo-num">${m.mentionRatePercent}%</td><td>${ts(m.lastObservedAt)}</td></tr>`).join('');
    return card(title, pill('green', 'LIVE-VERIFIED · MODEL-SPECIFIC'), `<div class="table-container"><table><thead><tr><th>Model @ host</th><th>Samples</th><th>Mentions</th><th>Rate</th><th>Last observed</th></tr></thead><tbody>${rows}</tbody></table></div>${scope}`, 'data-testid="seo-model-panel"');
  }

  function agentsPanel(o) {
    const v = view(o, 'agent_roster');
    const title = 'Autonomous agents';
    if (!v.ok) return card(title, pill('na'), viewError(v, 'Agent roster'));
    const d = v.data;
    const roster = d.roster || [];
    const rows = roster.map((a) => {
      const st = a.status === 'COMPLETED' ? 'green' : a.status === 'ALERT' ? 'danger' : 'na';
      return `<tr><td><strong>${esc(a.agentName)}</strong></td><td>${pill(st, String(a.status).replace(/_/g, ' '))}</td><td><code class="seo-prov">${esc(a.provenance)}</code><div class="seo-note">${esc(a.outputSummary)}</div><div class="seo-note">Executed ${ts(a.executedAt)}</div></td></tr>`;
    }).join('');
    return card(title, `<span class="seo-count">${int(d.activeAgentsCount)} of ${int(d.totalAgentsCount)} completed</span>`, `
      <p class="seo-def">Each agent either reads real persisted data or a provider and reports exactly what it found, or reports AWAITING PROVIDER with <code>[NOT AVAILABLE]</code>. None returns a pre-written result.</p>
      ${roster.length ? `<div class="table-container"><table><thead><tr><th>Agent</th><th>Status</th><th>Provenance and result</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<div class="seo-empty"><p><strong>NOT AVAILABLE.</strong> No agent has executed yet.</p></div>'}`, 'data-testid="seo-agents-panel"');
  }

  function unavailablePanel(o) {
    const rm = view(o, 'rank_movement_gsc');
    const queriesEmpty = !rm.ok || !(rm.data.queries && rm.data.queries.trajectories && rm.data.queries.trajectories.length);
    const tiles = [];
    if (queriesEmpty) tiles.push(['Per-query keyword position (GSC)', 'GSC returns no query-level rows for this property: queries below its privacy threshold are anonymized. Page and site data are never used to approximate it.', 'Resolves by itself if GSC starts returning query rows, or once a Bing key is added.']);
    tiles.push(
      ['Keyword volume, CPC, difficulty', 'No zero-cost compliant source exists for absolute search volume.', 'Requires paid keyword data.'],
      ['SERP features: snippet, People Also Ask, AI Overview', 'No compliant free source for third-party result pages.', 'Requires paid SERP data, or scraping that breaches provider terms.'],
      ['Competitor SERP rankings and keyword gaps', 'Competitor positions are not observable without SERP data. None are shown or implied.', 'Requires a verified SERP provider (see Live SERP rank movement).'],
      ['Consumer AI-assistant visibility', 'ChatGPT, Perplexity, Gemini and Google AI Overview cannot be queried at zero cost. Only a named model can (see Model-specific AEO).', "No zero-cost API returns those products' answers."],
      ['Competitor backlinks', 'Backlink counts are not obtainable at zero cost. The Common Crawl panel is a domain reference signal, not backlinks.', 'Requires a paid backlink index.']);
    return `<section>
      <div class="seo-section-head"><h3 class="card-title">Not available: no honest source at zero cost</h3>${pill('na')}</div>
      <div class="seo-na-grid">${tiles.map(([t, why, dep]) => `<div class="seo-na-tile"><div class="seo-na-head"><strong>${esc(t)}</strong>${pill('na')}</div><p>${esc(why)}</p><p class="dep"><span>Dependency</span> ${esc(dep)}</p></div>`).join('')}</div>
    </section>`;
  }

  function banner(o) {
    return `<div class="governance-banner info" data-testid="seo-source-banner"><div><div class="governance-title">Persisted data, loaded ${ts(o.fetched_at)}</div><div class="governance-desc">Internal SEO tenant <code>${esc(o.tenant_id)}</code> · SEO worker ${esc(o.worker_status || 'status unknown')}. This view reads the worker's persisted results only: opening it never calls a provider or triggers a job.</div></div></div>`;
  }

  // ---- render -------------------------------------------------------------------------------------------------
  function paint(html) {
    const el = document.getElementById('tab-seo');
    if (el) el.innerHTML = html;
  }

  function renderOverview(o) {
    paint(`<div class="seo-view">
      <div><h2 style="font-size:18px; font-weight:700;">SEO Intelligence</h2><div style="font-size:13px; color:var(--text-muted);">Operational SEO evidence for Sanocea's own internal SEO tenant: what was observed, how, and what cannot be known.</div></div>
      ${banner(o)}${legendPanel()}${kpis(o)}${gscMovementPanel(o)}${liveSerpPanel(o)}
      <div class="seo-cols">${sitemapPanel(o)}${authorityPanel(o)}</div>
      <div class="seo-cols">${schedulerPanel(o)}<div class="seo-stack">${bingPanel(o)}${modelPanel(o)}</div></div>
      ${agentsPanel(o)}${unavailablePanel(o)}
    </div>`);
  }

  async function render(force) {
    const el = document.getElementById('tab-seo');
    if (!el) return;
    if (!(cache.apiKey === STATE.apiKey && cache.overview)) paint('<div class="card" style="text-align:center; padding:32px; color:var(--text-muted);">Loading SEO intelligence…</div>');
    const r = await load(Boolean(force));
    if (r.apiKey !== STATE.apiKey || STATE.activeTab !== 'seo') return; // stale: key/tab changed while loading
    if (r.error) {
      paint(`<div class="seo-view"><div class="seo-error">SEO intelligence could not be loaded: ${esc(r.error)}. Nothing is shown rather than stale or default data.</div></div>`);
      return;
    }
    if (!r.overview || r.overview.monitored !== true) {
      paint('<div class="seo-view"><div class="seo-empty"><p><strong>NOT AVAILABLE.</strong> No SEO data was returned.</p></div></div>');
      return;
    }
    renderOverview(r.overview);
  }

  window.seoSetLevel = function (level) {
    ui.level = level;
    if (cache.overview && cache.apiKey === STATE.apiKey) renderOverview(cache.overview);
  };

  // ---- integration (no app.js edits): wrap the global renderActiveTab ------------------------------------------
  const originalRenderActiveTab = window.renderActiveTab;
  window.renderActiveTab = function () {
    originalRenderActiveTab.apply(this, arguments);
    if (STATE.activeTab === 'seo') render(false);
    else probe();
  };
})();
