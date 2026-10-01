// Customer-facing wording for the opportunities the SEO worker persists (the shared SEO overview, views.opportunities).
// Pure functions, no React, so the wording rules can be tested.
//
// Rules this file enforces:
//  - NO priority, severity or score is ever produced or shown. Order is the worker's order (a documented, deterministic
//    sort that is not importance).
//  - Status is the customer-facing lifecycle only: Needs review / Approved / In progress / Completed / Rejected / Monitoring.
//  - Google's result is quoted as Google reported it. Nothing here claims a cause. Separate observations stay separate:
//    they are never merged into one diagnosis.
//  - A value the worker did not supply is omitted, never filled in. No impact estimates.
//  - Database ids, internal paths and worker details are never read into the output.

export const STATUS_LABELS = ['Needs review', 'Approved', 'In progress', 'Completed', 'Rejected', 'Monitoring']

// Backend lifecycle -> the six words shown to the customer. APPROVED is a persisted backend state (human actor only).
const STATUS_MAP = {
  DISCOVERED: 'Needs review', QUALIFIED: 'Needs review', RESEARCHING: 'Needs review', ACTIONABLE: 'Needs review', AWAITING_APPROVAL: 'Needs review',
  APPROVED: 'Approved', IN_PROGRESS: 'In progress', COMPLETED: 'Completed', MEASURING: 'Monitoring', LEARNED: 'Completed', REJECTED: 'Rejected',
}
export const statusLabel = (s) => STATUS_MAP[s] || 'Needs review'

export const STATUS_GUIDE = [
  ['Needs review', 'SANOCEA found it and recommends an action. Nothing has been changed.'],
  ['Approved', 'You agreed the action should go ahead.'],
  ['In progress', 'The change is being made.'],
  ['Completed', 'The change was made. SANOCEA checks again before calling it done.'],
  ['Rejected', 'You decided not to act. SANOCEA will not raise it again.'],
  ['Monitoring', 'SANOCEA is watching what happens after the change.'],
]

export function pathOf(url) {
  if (typeof url !== 'string') return ''
  try {
    const u = new URL(url)
    return u.pathname === '/' || u.pathname === '' ? 'homepage' : u.pathname
  } catch {
    return url.startsWith('/') ? url : ''
  }
}
const pageName = (url) => { const p = pathOf(url); return p === 'homepage' ? 'The homepage' : p ? `The ${p.split('/').filter(Boolean).pop().replace(/[-_]/g, ' ')} page` : 'This page' }
const lower = (s) => s.charAt(0).toLowerCase() + s.slice(1)
const dateLabel = (iso) => (iso ? new Date(iso).toLocaleString('en-US', {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}) : null)

const NO_CHANGE = 'SANOCEA will not change your website.'

// One description per opportunity type. `evidence` is the worker's own evidence object.
const DESCRIBE = {
  SERVER_RENDERED_CONTENT_GAP: (o, e) => {
    const shell = Number(e.bodyWords) > 0
    return {
      title: `${pageName(e.url)} ${shell ? 'sends only a short shell' : 'sends no text'} before JavaScript runs`,
      what: shell ? 'Without JavaScript, this page sends a short shell (for example a heading and links) and nothing else.' : 'The page returns an empty page when it is requested without running JavaScript.',
      evidence: `We requested the page the way a crawler that does not run JavaScript would. It returned ${shell ? `${e.bodyWords} words in total` : '0 words of text'}.`,
      why: 'Anything that does not run JavaScript sees only that. We have not measured what Google does with this page.',
      action: `Ask your web team whether the page's main text can be included in the HTML the server delivers (server-side or static rendering). ${NO_CHANGE}`,
      tech: [['Method', e.method], ['Words in total', e.bodyWords], ['Words outside header and navigation', e.staticWords], ['Rule', e.threshold ? `fewer than ${e.threshold} readable words` : null], ['Source', 'Live page fetch']],
    }
  },
  MISSING_STATIC_H1: (o, e) => ({
    title: `${pageName(e.url)} has no main heading in the delivered HTML`,
    what: "The page's main heading (h1) is not in the HTML the server sends.",
    evidence: `We found ${e.h1Count === 0 ? 'no' : e.h1Count} main headings in the delivered HTML.`,
    why: 'A heading may be added after JavaScript runs; we have not measured that.',
    action: `Ask your web team to include one main heading in the delivered HTML. ${NO_CHANGE}`,
    tech: [['Method', e.method], ['Main headings found', e.h1Count], ['Source', 'Live page fetch']],
  }),
  SITEMAP_URL_REDIRECTS: (o, e) => o.recommendedAction === 'INVESTIGATE' && o.diagnosis ? ({
    title: 'The address in your sitemap, the redirect and the page\'s preferred address do not agree',
    what: o.diagnosis.conclusion,
    evidence: `${o.diagnosis.finding} SANOCEA has not yet established which address is intended.`,
    why: 'Changing the wrong one could point search engines at the wrong address, so SANOCEA is gathering more evidence first. Nothing is being changed.',
    action: `Nothing is needed from you now. SANOCEA is gathering: ${(o.actionPlan && o.actionPlan.investigate_next || []).map((x) => x.replace(/^Gather: /, '')).join('; ') || 'more evidence'}.`,
    tech: [['Method', e.method], ['Listed address', pathOf(e.listedUrl)], ['Final address', pathOf(e.finalUrl)], ['Destination canonical', e.destinationCanonical ? pathOf(e.destinationCanonical) : 'none found'], ['Source', 'Live page fetch']],
    sub: `${pathOf(e.listedUrl)} → ${pathOf(e.finalUrl)} (redirect)`,
  }) : ({
    title: 'A page address in your sitemap redirects',
    what: 'The sitemap lists an address that sends visitors on to a different address.',
    evidence: `Requesting ${pathOf(e.listedUrl)} returned a redirect to ${pathOf(e.finalUrl)}.`,
    why: 'The sitemap should list the final address, so a visitor or crawler does not have to follow a redirect to reach the page.',
    action: `Ask your web team to list the final address in the sitemap. ${NO_CHANGE}`,
    tech: [['Method', e.method], ['Listed address', pathOf(e.listedUrl)], ['Final address', pathOf(e.finalUrl)], ['Source', 'Live page fetch']],
    sub: `${pathOf(e.listedUrl)} → ${pathOf(e.finalUrl)} (redirect)`,
  }),
  GOOGLE_INDEX_STATUS_ISSUE: (o, e) => {
    const state = e.coverageState || 'no status given'
    const found = /^Discovered\b/i.test(state)
    return {
      title: found ? `Google has found ${lower(pageName(e.url))} but has not added it to search yet` : `Google reports "${state}" for ${lower(pageName(e.url))}`,
      what: `Google's own report for this page says: ${state}.`,
      evidence: `Google's URL Inspection reports "${state}" for this page.${e.lastCrawlTime ? ` Google last crawled it on ${dateLabel(e.lastCrawlTime)}.` : ' Google reports no crawl yet.'} Google does not say why.`,
      why: "A page that is not in Google's index does not appear in Google results. SANOCEA has not determined a cause.",
      action: `Review Google's report with your web team. The other items on this list are separate observations; SANOCEA is not linking them to this one. ${NO_CHANGE}`,
      tech: [['Source', 'Google Search Console, URL Inspection'], ['Verdict', e.verdict], ['Coverage', e.coverageState], ['Last crawl', e.lastCrawlTime ? dateLabel(e.lastCrawlTime) : 'No crawl reported'], ['Indexing', e.indexingState], ['Page fetch', e.pageFetchState]],
      checkedAt: e.inspectedAt, observedVerb: 'Checked',
    }
  },
  SITEMAP_REPORTED_ISSUES: (o, e) => ({
    title: 'Google reports problems with your sitemap',
    what: `Google reports ${e.errors || 0} errors and ${e.warnings || 0} warnings for your sitemap.`,
    evidence: 'These counts come from the Search Console sitemap report.',
    why: "Google's report lists the affected entries. SANOCEA has not determined their effect.",
    action: `Open the sitemap report in Search Console with your web team. ${NO_CHANGE}`,
    tech: [['Source', 'Google Search Console, sitemaps'], ['Errors', e.errors], ['Warnings', e.warnings]],
  }),
  HIGH_IMPRESSIONS_LOW_CTR: (o, e) => ({
    title: `${pageName(e.page)} is shown often in Google but rarely clicked`,
    what: `Search Console reports ${e.clicks} clicks from ${e.impressions} views for this page.`,
    evidence: `The click rate (${(Number(e.ctr) * 100).toFixed(2)}%) is calculated from those two Search Console numbers.`,
    why: 'The title and description shown for a page are the first thing to review. Google may choose to display different text.',
    action: `Ask your web team to review the page's title and description. A before-and-after comparison will not prove the change caused any difference. ${NO_CHANGE}`,
    tech: [['Source', 'Google Search Console snapshot'], ['Views', e.impressions], ['Clicks', e.clicks], ['Rule', e.rule]],
  }),
  QUERY_PAGE_MATCH_GAP: (o, e) => ({
    title: `People are shown your site for "${e.query}", but no checked page is clearly about it`,
    what: `Search Console reports ${e.impressions} views for "${e.query}".`,
    evidence: `None of the ${e.pagesCompared} pages checked shares enough of the phrase's words in its address, title or heading.`,
    why: e.limitation || 'Only some pages were compared.',
    action: `Confirm whether a page already covers this phrase before anything is created. ${NO_CHANGE}`,
    tech: [['Source', 'Google Search Console snapshot'], ['Views', e.impressions], ['Pages compared', e.pagesCompared]],
  }),
}

const clean = (tech) => (tech || []).filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, v]) => [k, String(v)])

// Returns the customer-facing record for one backend opportunity. Unknown types fall back to the worker's own plain text.
export function describeOpportunity(o) {
  const e = (o && o.evidence) || {}
  const d = DESCRIBE[o && o.type] ? DESCRIBE[o.type](o, e) : {
    title: (o && o.plainEnglish) || 'SANOCEA found something to review',
    what: (o && o.plainEnglish) || '', evidence: (o && o.reason) || '', why: (o && o.decision && o.decision.rationale) || '',
    action: `Review this with your web team. ${NO_CHANGE}`, tech: [['Source', o && o.source]],
  }
  const target = e.url || e.page || e.listedUrl || e.sitemap || o.target
  return {
    key: `${o.type}|${o.target}`,
    title: d.title,
    sub: d.sub || (target && /^https?:/.test(String(target)) ? pathOf(target) : e.query ? `"${e.query}"` : ''),
    what: d.what, evidence: d.evidence, why: d.why, action: d.action,
    observedVerb: d.observedVerb || 'Observed',
    status: statusLabel(o.status),
    checkedAt: dateLabel(d.checkedAt || e.observedAt || e.capturedAt || e.fetchedAt || o.lastSeenAt),
    tech: clean(d.tech),
  }
}

// Selector over the shared overview: ok=false means the worker did not supply the view (nothing is invented).
export function opportunitiesFrom(overview) {
  const v = overview && overview.views && overview.views.opportunities
  if (!v || !v.ok || !v.data || !Array.isArray(v.data.opportunities)) return {ok: false, items: []}
  return {ok: true, items: v.data.opportunities.map(describeOpportunity), updatedAt: v.updated_at || null}
}
