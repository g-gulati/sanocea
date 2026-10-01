#!/usr/bin/env python3
"""Assembles the Opportunity Queue design preview from the frontend-design-preview scaffold.
Scaffold CSS/JS/skeleton is lifted verbatim; the previewed UI and the knob set are SANOCEA's own
(derived from website/src/whatsapp-demo/components/SeoPlainOverview.jsx inline styles)."""
import re, pathlib
T = pathlib.Path('/root/.claude/skills/frontend-design-preview/template.html').read_text().split('\n')
L = lambda a, b: '\n'.join(T[a-1:b])            # 1-based inclusive

css_scaffold = L(7, 393) + '\n' + L(547, 854)    # drops the template's sample-UI CSS (.wb-header ... .preview-progress)
js = L(1158, 2258)
# replace PREVIEW_META / TOKENS / SECTION_ORDER block
a = js.index('const PREVIEW_META'); b = js.index('/* ============================================================\n   DECISION SYSTEM')
TOKENS_JS = r"""const PREVIEW_META = {
  source: 'website/src/whatsapp-demo/components/SeoPlainOverview.jsx (sections 4-6) + SeoShared.jsx',
  topic: 'Opportunity Queue inside "5. What needs attention?"',
  targetFile: 'website/src/whatsapp-demo/components/SeoPlainOverview.jsx (inline style constants: card, mut, secTitle, Pill)',
};

// Knobs = the dimensions SeoPlainOverview.jsx really tunes inline today (card radius/padding, body size, the
// accent blue and the amber "attention" pill palette). The app has no CSS variables; names below are preview-only.
const TOKENS = {
  color: [
    { key: '--sx-accent', intent: 'accent blue (bars, left rules, links)', kind: 'color',
      options: [
        { id: 'A', light: '#0284C7', dark: '#38bdf8', note: 'current accent (default)' },
        { id: 'B', light: '#1D4ED8', dark: '#60a5fa', note: 'the "opp" pill blue' }
      ] }
  ],
  shape: [
    { key: '--sx-radius', intent: 'card corner radius (today 12px)', kind: 'slider', min: 6, max: 16, step: 2, defaultValue: 12, unit: 'px' },
    { key: '--sx-body', intent: 'body text in rows (today 13px)', kind: 'slider', min: 12, max: 15, step: 1, defaultValue: 13, unit: 'px' }
  ],
  density: [
    { key: '--sx-row-pad', intent: 'vertical padding of each opportunity row (today 10px)', kind: 'segmented',
      options: [
        { id: 'compact', value: '7px', note: 'compact' },
        { id: 'normal', value: '10px', note: 'normal (default)' },
        { id: 'spacious', value: '15px', note: 'spacious' }
      ], defaultId: 'normal' }
  ]
};

const SECTION_ORDER = [
  ['Colour', 'color'],
  ['Type & shape', 'shape'],
  ['Density', 'density']
];

"""
js = js[:a] + TOKENS_JS + js[b:]

CSS_APP = r"""
  /* ===== Preview-only: SANOCEA SEO page look (mirrors SeoPlainOverview.jsx inline styles) ===== */
  .theme-light { --sx-bg:#F8FAFC; --sx-card:#FFFFFF; --sx-line:#E2E8F0; --sx-ink:#0F172A; --sx-mut:#64748B; --sx-todo:#ECFDF5; --sx-todo-ink:#047857; --sx-opp:#EFF6FF; --sx-opp-ink:#1D4ED8; --sx-na:#F1F5F9; --sx-na-ink:#475569; --sx-ok:#ECFDF5; --sx-ok-ink:#047857; }
  .theme-dark  { --sx-bg:#0b1220; --sx-card:#111a2c; --sx-line:#243049; --sx-ink:#e6edf7; --sx-mut:#93a3bb; --sx-todo:#0e2a22; --sx-todo-ink:#34d399; --sx-opp:#13233f; --sx-opp-ink:#93c5fd; --sx-na:#182338; --sx-na-ink:#a7b4c9; --sx-ok:#0e2a22; --sx-ok-ink:#34d399; }
  .preview { --sx-accent:#0284C7; --sx-radius:12px; --sx-body:13px; --sx-row-pad:10px; }
  .theme-dark.preview { --sx-accent:#38bdf8; }
  .sx { background: var(--sx-bg); color: var(--sx-ink); border-radius: 10px; padding: 18px; font-size: var(--sx-body); line-height: 1.45; }
  .sx .sec { font-size: 15px; font-weight: 800; margin: 22px 0 10px; }
  .sx .sec:first-child { margin-top: 0; }
  .sx .card { background: var(--sx-card); border: 1px solid var(--sx-line); border-radius: var(--sx-radius); padding: 16px 18px; }
  .sx .mut { color: var(--sx-mut); }
  .sx .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
  .sx .chip { display: inline-block; font-size: 11px; font-weight: 700; border-radius: 99px; padding: 2px 9px; margin-right: 8px; white-space: nowrap; }
  .sx .chip.high { background: var(--sx-highbg); color: var(--sx-high); }
  .sx .chip.med { background: var(--sx-opp); color: var(--sx-opp-ink); }
  .sx .chip.na { background: var(--sx-na); color: var(--sx-na-ink); }
  .sx .chip.ok { background: var(--sx-ok); color: var(--sx-ok-ink); }
  .sx .summary-line { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: baseline; justify-content: space-between; margin-bottom: 4px; }
  .sx .summary-line b { font-size: 17px; }
  .sx details.opp { border-top: 1px solid var(--sx-line); }
  .sx details.opp:first-of-type { border-top: 0; }
  .sx details.opp > summary { list-style: none; cursor: pointer; padding: var(--sx-row-pad) 0; display: grid; grid-template-columns: 1fr auto auto; gap: 4px 10px; align-items: start; }
  .sx details.opp > summary::-webkit-details-marker { display: none; }
  .sx .opp-title { font-weight: 700; }
  .sx .opp-sub { grid-column: 1 / 2; color: var(--sx-mut); font-size: 12px; }
  .sx .status { font-size: 11.5px; font-weight: 700; color: var(--sx-na-ink); background: var(--sx-na); border-radius: 99px; padding: 2px 10px; white-space: nowrap; }
  .sx .chev { color: var(--sx-mut); transition: transform .15s; align-self: center; }
  .sx details[open] > summary .chev { transform: rotate(90deg); }
  .sx .opp-body { padding: 2px 0 14px 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px 18px; }
  .sx .opp-body .k { font-size: 11px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; color: var(--sx-mut); margin-bottom: 2px; }
  .sx .opp-body .v { font-size: var(--sx-body); }
  .sx .todo { grid-column: 1 / -1; background: var(--sx-todo); color: var(--sx-todo-ink); border-radius: 6px; padding: 7px 11px; }
  .sx details.tech { grid-column: 1 / -1; border-top: 1px dashed var(--sx-line); padding-top: 6px; }
  .sx details.tech > summary { cursor: pointer; font-size: 12px; color: var(--sx-mut); }
  .sx details.tech dl { margin: 6px 0 0; display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px; font-size: 12px; }
  .sx details.tech dt { color: var(--sx-mut); } .sx details.tech dd { margin: 0; }
  .sx .also { border-top: 1px solid var(--sx-line); margin-top: 12px; padding-top: 12px; }
  .sx .also-h { font-size: 12px; font-weight: 800; color: var(--sx-mut); margin-bottom: 4px; }
  .sx .item { padding: 8px 0; border-top: 1px solid var(--sx-line); }
  .sx .item:first-of-type { border-top: 0; }
  .sx .guide { margin-top: 12px; border-top: 1px solid var(--sx-line); padding-top: 8px; }
  .sx .guide > summary { cursor: pointer; font-size: 12px; color: var(--sx-mut); }
  .sx .guide dl { margin: 8px 0 0; display: grid; grid-template-columns: max-content 1fr; gap: 6px 12px; font-size: 12px; align-items: center; }
  .sx .guide dd { margin: 0; color: var(--sx-mut); }
  .sx .strip { border-left: 5px solid var(--sx-accent); }
  .sx .context { opacity: .9; }
"""

def chip(kind, t, fid, editable=True):
    e = ' data-fd-editable="text"' if editable else ''
    return f'<span class="chip {kind}" data-fd-id="{fid}"{e}>{t}</span>'

def opp(i, prio, title, sub, opp_txt, evidence, why, action, checked, tech, open_=False):
    dl = ''.join(f'<dt>{k}</dt><dd>{v}</dd>' for k, v in tech)
    return f'''
        <details class="opp" data-fd-id="row-opp-{i}"{' open' if open_ else ''}>
          <summary data-fd-id="row-opp-{i}-summary">
            <span><span class="opp-title" data-fd-id="text-opp-{i}-title" data-fd-editable="text">{title}</span></span>
            <span class="status" data-fd-id="pill-status-{i}">Needs review</span>
            <span class="chev" aria-hidden="true">›</span>
            <span class="opp-sub" data-fd-id="text-opp-{i}-sub">{sub}</span>
          </summary>
          <div class="opp-body" data-fd-id="panel-opp-{i}">
            <div data-fd-id="field-opportunity-{i}"><div class="k">Opportunity</div><div class="v" data-fd-editable="text" data-fd-id="text-opportunity-{i}">{opp_txt}</div></div>
            <div data-fd-id="field-evidence-{i}"><div class="k">Evidence</div><div class="v" data-fd-editable="text" data-fd-id="text-evidence-{i}">{evidence}</div></div>
            <div data-fd-id="field-why-{i}"><div class="k">Why it matters</div><div class="v" data-fd-editable="text" data-fd-id="text-why-{i}">{why}</div></div>
            <div data-fd-id="field-status-{i}"><div class="k">Status</div><div class="v">Needs review &middot; nothing has been changed</div></div>
            <div class="todo" data-fd-id="callout-action-{i}"><b>Recommended action:</b> <span data-fd-editable="text" data-fd-id="text-action-{i}">{action}</span></div>
            <div data-fd-id="field-checked-{i}"><div class="k">Last checked</div><div class="v">{checked}</div></div>
            <details class="tech" data-fd-id="details-technical-{i}"><summary>Technical details</summary><dl>{dl}</dl></details>
          </div>
        </details>'''

OPPS = ''.join([
  opp(1, '', 'The solutions page sends no text before JavaScript runs',
      'Observed Oct 1 &middot; /solutions/marketplace-reconciliation',
      'The page\'s address returns an empty page when it is requested without running JavaScript.',
      'We requested the page the way a crawler that does not run JavaScript would. It returned 0 words of text.',
      'Anything that does not run JavaScript sees an empty page. We have not measured whether Google runs it for this page, so we are not saying Google cannot read it.',
      'Ask your web team to send the page\'s main text in the HTML the server delivers (server-side or static rendering). SANOCEA will not change your website.',
      'Oct 1, 8:53 AM',
      [('Method','HTTP GET, no JavaScript'),('Readable words','0'),('Rule','fewer than 100 readable words'),('Source','Live page fetch')], True),
  opp(2, '', 'The homepage sends only a short shell before JavaScript runs',
      'Observed Oct 1 &middot; homepage',
      'Without JavaScript the homepage sends a heading and three links, and nothing else.',
      'We requested the homepage without running JavaScript. It returned 21 words in total.',
      'Anything else the page shows is added by JavaScript after it loads. We have not measured what Google does with it.',
      'Ask your web team whether the homepage\'s main content can be included in the delivered HTML.',
      'Oct 1, 8:53 AM',
      [('Method','HTTP GET, no JavaScript'),('Words in total','21'),('Words outside header/navigation','0'),('Source','Live page fetch')]),
  opp(3, '', 'The solutions page has no main heading in the delivered HTML',
      'Observed Oct 1 &middot; /solutions/marketplace-reconciliation',
      'The page\'s main heading (h1) is not in the HTML the server sends.',
      'We found 0 main headings in the delivered HTML.',
      'A heading may be added after JavaScript runs; we have not measured that.',
      'Ask your web team to include one main heading in the delivered HTML.',
      'Oct 1, 8:53 AM',
      [('Method','HTTP GET, no JavaScript'),('Main headings found','0'),('Source','Live page fetch')]),
  opp(4, '', 'A page address in your sitemap redirects',
      '/solutions/marketplace-reconciliation &rarr; /solutions/marketplace-reconciliation/ (redirect)',
      'The sitemap lists an address that sends visitors on to a different address.',
      'Requesting the sitemap\'s address returned a permanent redirect to the same address with a trailing slash.',
      'The sitemap should list the final address, so Google does not have to follow a redirect to reach the page.',
      'Ask your web team to list the final address in the sitemap.',
      'Oct 1, 8:53 AM',
      [('Method','HTTP GET following redirects'),('Listed address','…/marketplace-reconciliation'),('Final address','…/marketplace-reconciliation/'),('Source','Live page fetch')]),
  opp(5, '', 'Google has found the solutions page but not added it to search',
      'Checked Oct 1 &middot; /solutions/marketplace-reconciliation',
      'Google\'s own report for this page says: Discovered - currently not indexed.',
      'Google\'s URL Inspection reports "Discovered - currently not indexed" for this page. Google does not say why.',
      'A page that is not in Google\'s index cannot appear in Google results. SANOCEA has not determined the cause.',
      'Review the report with your web team alongside the redirect and content-delivery items above. Nothing has been changed.',
      'Oct 1, 9:09 AM',
      [('Source','Google Search Console, URL Inspection'),('Verdict','Neutral'),('Coverage','Discovered - currently not indexed'),('Last crawl','Not crawled yet')]),
])

STATUSES = [('Needs review','na','SANOCEA found it and recommends an action. Nothing has been changed.'),
            ('Approved','ok','You agreed the action should go ahead.'),
            ('In progress','med','The change is being made.'),
            ('Completed','ok','The change was made. SANOCEA checks again before calling it done.'),
            ('Rejected','na','You decided not to act. SANOCEA will not raise it again.'),
            ('Monitoring','med','SANOCEA is watching what happens after the change.')]
GUIDE = ''.join(f'<dt><span class="chip {k}" style="margin:0" data-fd-id="pill-guide-{n.lower().replace(" ","-")}">{n}</span></dt><dd>{d}</dd>' for n, k, d in STATUSES)

def ui():
    return f'''
        <div class="sx" data-fd-id="page-seo-audit">
          <div class="sec context" data-fd-id="heading-section-4">4. What did SANOCEA find?</div>
          <div class="grid2 context" data-fd-id="grid-section-4">
            <div class="card" data-fd-id="card-found-pages"><b>Only one of your two main pages is appearing in search</b><p class="mut" style="margin:4px 0 0">Your homepage gets all your Google visibility. Your marketplace reconciliation page has not appeared in any searches yet.</p></div>
            <div class="card" data-fd-id="card-found-privacy"><b>Google is hiding what people searched for</b><p class="mut" style="margin:4px 0 0">For privacy, Google does not share the exact phrases when only a few people use them.</p></div>
          </div>

          <div class="sec" data-fd-id="heading-section-5">5. What needs attention?</div>
          <div class="card" data-fd-id="card-attention">
            <div class="summary-line" data-fd-id="row-summary">
              <b data-fd-id="text-summary-count" data-fd-editable="text">5 things need attention</b>
              <span class="mut" style="font-size:12px" data-fd-id="text-summary-note">All 5 need your review &middot; last checked Oct 1</span>
            </div>
            <div class="mut" style="font-size:12px;margin-bottom:4px" data-fd-id="text-summary-reassure">Open one to see the evidence. Nothing on this page changes your website.</div>
            {OPPS}
            <div class="also" data-fd-id="section-also-known">
              <div class="also-h">Also worth knowing</div>
              <div class="item" data-fd-id="item-known-presence"><span class="chip na">Keep watching</span><b>Your presence on Google is still small</b></div>
              <div class="item" data-fd-id="item-known-queries"><span class="chip na">Good to know</span><b>You cannot see which searches find you yet</b></div>
            </div>
            <details class="guide" data-fd-id="details-status-guide"><summary>What the statuses mean</summary><dl data-fd-id="list-status-guide">{GUIDE}</dl></details>
          </div>

          <div class="sec context" data-fd-id="heading-section-6">6. What is SANOCEA doing about it?</div>
          <div class="card strip context" data-fd-id="card-doing"><b>SANOCEA keeps checking your site, works out what the evidence shows, and tells you what needs attention.</b></div>
        </div>'''

def pane(theme, toggle, label):
    return f'''      <div class="preview theme-{theme}" id="preview-{theme}" data-theme="{theme}">
        <button class="pane-toggle-btn" type="button" data-pane="{theme}" title="Expand {theme} pane" aria-label="Expand {theme} pane">{toggle}</button>
        <div class="label" data-fd-id="theme-label">{label}</div>
{ui()}
      </div>
'''

head = L(1, 6) + '\n' + css_scaffold + CSS_APP + '\n' + L(855, 903)
head = head.replace('<title>', '<title>', 1)
# the line range 855-903 starts with </style> ... through the light pane opening comment; ensure we stop before light <div>
mid = pane('light', '▶', 'Light theme (the live site is light only; dark is a review mirror)') + '\n      <!-- DARK PREVIEW (mirror of light) -->\n' + pane('dark', '◀', 'Dark theme (review mirror)')
tail_start = next(i for i, l in enumerate(T) if l.strip() == '</section>')
tail = '      </div>\n' + L(tail_start + 1, 1157) + '\n<script>\n' + js.split('\n', 1)[1].replace('<script>', '') + '\n</body>\n</html>\n'
html = head + '\n' + mid + tail
html = html.replace('frontend-design preview', 'Opportunity Queue · design preview (not production)')
html = html.replace('Decision controls on the left · live preview on the right', 'SANOCEA SEO &amp; Commerce Audit, section 5 · decision controls left · preview right')
pathlib.Path('/opt/sanocea/repo/.frontend-design/opportunity-queue/2026-10-01-opportunity-queue.html').write_text(html)
print(len(html))
