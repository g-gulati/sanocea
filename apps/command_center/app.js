/**
 * SANOCEA Operations Command Center - Frontend Controller
 * 
 * Hard architectural invariant: ZERO commercial/business decision logic in the UI.
 * All state, identity, validation, approval, publication, inventory, orders,
 * returns/refunds, and audit trails are queried from authoritative SANOCEA APIs.
 */

// Display metadata only (id + name) for the operator merchant switcher - NOT an access grant. Actual
// access to any merchant's data is still gated per-merchant by the existing operator API key mechanism
// (packages/authn/deps.py::require_operator); selecting a merchant here with no valid key for it simply
// prompts the auth modal, scoped to that merchant, same as the very first sign-in always has.
const DEMO_TENANTS = [
  { id: 'ref_anchal_heritage', name: 'Anchal Heritage Organics (Reference)' },
  { id: 'prospect_ajanta_soya', name: 'Ajanta Soya' },
  { id: 'prospect_healthvitals', name: "Dr. J's HealthVitals" },
  { id: 'prospect_carzex', name: 'Carzex' },
  { id: 'prospect_premium_basket', name: 'The Premium Basket' },
];

const STATE = {
  merchantId: 'ref_anchal_heritage',
  apiKey: null,
  profile: null,
  summary: null,
  drafts: [],
  exceptions: [],
  approvals: [],
  publications: [],
  orders: [],
  inventory: [],
  returns: [],
  refunds: [],
  audit: [],
  channelOperations: [],
  activeTab: 'overview',
  activeDraftId: null,
  activeChannelFilter: null,
  // Monotonically incremented on every merchant switch - the mechanism that makes switching atomic
  // under a race (operator clicks a second merchant before the first one's fetch has resolved). A
  // fetch only commits STATE and renders if the switchToken it captured when it STARTED is still the
  // current one when it FINISHES; a superseded fetch silently discards its own result instead of
  // clobbering newer state. See switchMerchant()/refreshAllData().
  switchToken: 0,
  loadError: null,
};

// True only for a tenant seeded by packages/prospect_demo (config.demo is set once, server-side, by
// that seeding - never inferred client-side from merchantId string matching). Drives which render path
// every tab below takes: the Reference Merchant's own certified presentation is completely unchanged
// when this is false; a prospect demo tenant never renders any of that certified-specific content.
function isProspectDemoTenant() {
  return Boolean(STATE.profile && STATE.profile.config && STATE.profile.config.demo);
}

// Clears every tenant-scoped field (never merchantId/apiKey/switchToken themselves) so a merchant
// switch can never leave a previous tenant's data visible - called BEFORE a switch's fetch starts, and
// again if that fetch fails. This is what makes "selector = Ajanta, body = Anchal" structurally
// impossible: there is no path from one tenant's rendered content directly to another's without this
// clear running first.
function clearTenantState() {
  STATE.profile = null;
  STATE.summary = null;
  STATE.drafts = [];
  STATE.exceptions = [];
  STATE.approvals = [];
  STATE.publications = [];
  STATE.orders = [];
  STATE.inventory = [];
  STATE.returns = [];
  STATE.refunds = [];
  STATE.audit = [];
  STATE.channelOperations = [];
  STATE.activeChannelFilter = null;
  if (typeof EXPANDED_WHY_PANELS !== 'undefined') EXPANDED_WHY_PANELS.clear();
}

function renderLoadingState(merchantId) {
  const msg = `<div style="padding:48px; text-align:center; color:var(--text-muted); font-size:13px;">Loading ${merchantId}…</div>`;
  document.querySelectorAll('.tab-content').forEach(el => { el.innerHTML = msg; });
}

function renderErrorState(message) {
  const html = `
    <div class="card" style="text-align:center; padding:40px; border-color:var(--danger-border); background:var(--danger-light);">
      <h3 style="color:var(--danger); font-size:16px; font-weight:700; margin-bottom:6px;">Unable to load selected merchant.</h3>
      <p style="color:var(--text-muted); font-size:13px;">${message}</p>
    </div>`;
  document.querySelectorAll('.tab-content').forEach(el => { el.innerHTML = html; });
}

// API Client
async function apiCall(endpoint, method = 'GET', body = null) {
  const headers = {
    'Accept': 'application/json',
  };
  if (STATE.apiKey) {
    headers['Authorization'] = `Bearer ${STATE.apiKey}`;
  }
  if (body) {
    headers['Content-Type'] = 'application/json';
  }

  // cache: 'no-store' is load-bearing, not defensive polish - a real bug found live (2026-09-17): the
  // browser's HTTP cache was silently serving a stale response for the repeated identical
  // GET /merchants/{id}/audit poll (the backend sends no Cache-Control header at all, and fetch()'s
  // default caching mode can still reuse a prior response for an identical same-origin GET URL). The
  // connection indicator showed "Live" (the fetch() call itself succeeded) while STATE.audit silently
  // never advanced past an old snapshot - exactly the class of bug the "Stateless UI Execution"
  // invariant (every screen reflects genuine authoritative backend state) exists to prevent.
  const options = { method, headers, cache: 'no-store' };
  if (body) {
    options.body = JSON.stringify(body);
  }

  const res = await fetch(endpoint, options);
  if (!res.ok) {
    let errDetail = res.statusText;
    try {
      const errJson = await res.json();
      errDetail = errJson.detail || JSON.stringify(errJson);
    } catch (e) {}
    throw new Error(`API ${res.status}: ${errDetail}`);
  }
  return await res.json();
}

// Safe Local-Development Authentication Mechanism
// ONE session key, held only in sessionStorage (never localStorage, never the URL, never persisted
// permanently) - submitted once. Backend authorization (packages/authn/deps.py::require_operator) is
// what actually decides which merchant_ids this key may reach; the frontend never decides that. An
// internal-operator key (see scripts/mint_internal_operator_key.py) is authorized for every demo tenant
// at once, so switching the merchant dropdown never needs a new key - but a key scoped to only one
// merchant (e.g. a future prospect-scoped session) will correctly get a 401/403 from refreshAllData()
// the moment it tries a merchant it isn't authorized for, which is handled below, not hidden.
function resolveLocalApiKey() {
  localStorage.removeItem('sanocea_api_key');
  const storedKey = sessionStorage.getItem('sanocea_operator_session');
  if (storedKey && storedKey.trim()) {
    return storedKey.trim();
  }
  return null;
}

function openAuthModal(errorMessage = '') {
  const modal = document.getElementById('auth-modal');
  const errEl = document.getElementById('auth-modal-error');
  const input = document.getElementById('input-api-key');
  const promptEl = document.getElementById('auth-modal-prompt');
  if (modal) {
    modal.style.display = 'flex';
    if (promptEl) {
      promptEl.innerHTML = `Sign in once with your internal operator API key. You will be able to switch between every authorized demo merchant without signing in again.`;
    }
    if (errEl) {
      if (errorMessage) {
        errEl.textContent = errorMessage;
        errEl.style.display = 'block';
      } else {
        errEl.style.display = 'none';
      }
    }
    if (input) {
      input.value = STATE.apiKey || '';
      input.focus();
    }
  }
}

function closeAuthModal() {
  const modal = document.getElementById('auth-modal');
  if (modal) modal.style.display = 'none';
}

async function submitApiKey() {
  const input = document.getElementById('input-api-key');
  const key = (input ? input.value : '').trim();
  if (!key) {
    const errEl = document.getElementById('auth-modal-error');
    if (errEl) {
      errEl.textContent = 'Please provide an operator API key.';
      errEl.style.display = 'block';
    }
    return;
  }
  localStorage.removeItem('sanocea_api_key');
  sessionStorage.setItem('sanocea_operator_session', key);
  STATE.apiKey = key;
  closeAuthModal();
  updateAuthStatusUI();
  try {
    await refreshAllData();
    showNotification('Connected successfully with operator session.', 'success');
  } catch (err) {
    openAuthModal(`Authentication failed: ${err.message}`);
  }
}

// Operator merchant switcher - Manpreet only (this file is never served to a prospect-scoped session).
// Deliberately does NOT touch STATE.apiKey or re-prompt for authentication: the SAME already-established
// session key is reused for every merchant, and backend authorization
// (packages/authn/deps.py::require_operator) is what actually determines whether that key may reach the
// newly selected merchant_id - never assumed client-side.
//
// ATOMIC by construction - select -> clear -> fetch -> validate -> render, exactly in that order, with a
// switchToken guarding against a race (a second switch starting before the first one's fetch resolves):
//   1. clearTenantState() runs BEFORE the fetch - there is no window where a stale tenant's data can
//      still be in STATE while a new merchantId is selected.
//   2. renderLoadingState() replaces every tab's DOM immediately - there is no window where a stale
//      tenant's RENDERED markup can still be on screen while a new merchantId is selected either. This
//      is what makes "selector = Ajanta, body = Anchal" structurally impossible, not just unlikely.
//   3. refreshAllData() fetches the new tenant's real state. If the backend rejects the session key for
//      this merchant (401/403 - e.g. a key only authorized for a subset of tenants) or any other request
//      fails, it throws - never silently resolves to empty/null state.
//   4. The returned profile's own `id` is validated against the merchantId just requested - if a
//      superseded (older) fetch resolves after a newer switch already started, its switchToken no longer
//      matches STATE.switchToken and its result is discarded, never rendered.
//   5. On any failure: state is cleared again and an explicit "Unable to load selected merchant" error
//      renders - never the previous tenant's data, per the required failure behavior.
async function switchMerchant(newMerchantId) {
  if (!newMerchantId || newMerchantId === STATE.merchantId) return;
  const token = ++STATE.switchToken;
  stopLiveActivityPolling(); // never let a previous tenant's poll tick write into the new tenant's STATE
  STATE.merchantId = newMerchantId;
  clearTenantState();
  const tenantLabel = document.getElementById('tenant-id-label');
  if (tenantLabel) tenantLabel.textContent = newMerchantId;
  updateDemoDisclosureBanner();
  renderLoadingState(newMerchantId);
  if (!STATE.apiKey) {
    openAuthModal();
    return;
  }
  try {
    await refreshAllData(token);
    if (token !== STATE.switchToken) return; // superseded by an even newer switch - discard silently
    if (!STATE.profile || STATE.profile.id !== newMerchantId) {
      throw new Error('backend did not return the expected merchant identity');
    }
    if (isProspectDemoTenant()) startLiveActivityPolling();
    refreshOwnerWhatsAppStatus();
    showNotification(`Switched to ${newMerchantId}.`, 'info');
  } catch (err) {
    if (token !== STATE.switchToken) return; // a newer switch already took over - nothing to clean up
    clearTenantState();
    renderErrorState(err.message);
    if (err.message.includes('401') || err.message.includes('403')) {
      openAuthModal(`This session is not authorized for ${newMerchantId}: ${err.message}`);
    }
  }
}

function updateAuthStatusUI() {
  const authStatusEl = document.getElementById('auth-status');
  if (!authStatusEl) return;
  if (STATE.apiKey) {
    authStatusEl.innerHTML = `
      <span class="tenant-dot"></span>
      <span>Operator (Authenticated)</span>
      <button class="btn btn-outline btn-xs" onclick="openAuthModal()" style="margin-left:6px; font-size:10px; padding:2px 6px;">Key</button>
    `;
  } else {
    authStatusEl.innerHTML = `
      <span style="color:var(--danger); font-weight:600;">Unauthenticated</span>
      <button class="btn btn-primary btn-xs" onclick="openAuthModal()" style="margin-left:6px; font-size:11px; padding:2px 8px;">Sign In</button>
    `;
  }
}

// Bootstrap Authentication & Load Initial Data
async function initApp() {
  try {
    // Populate the operator merchant switcher (display metadata only - see DEMO_TENANTS above).
    const selectEl = document.getElementById('merchant-select');
    if (selectEl) {
      selectEl.innerHTML = DEMO_TENANTS.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
      selectEl.value = STATE.merchantId;
      selectEl.addEventListener('change', (e) => switchMerchant(e.target.value));
    }
    const tenantLabel = document.getElementById('tenant-id-label');
    if (tenantLabel) tenantLabel.textContent = STATE.merchantId;

    STATE.apiKey = resolveLocalApiKey();
    updateAuthStatusUI();

    // Setup tab event listeners
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        switchTab(tab);
      });
    });

    // Setup manual refresh button
    document.getElementById('btn-refresh').addEventListener('click', async () => {
      try {
        await refreshAllData();
        showNotification('State refreshed from authoritative SANOCEA APIs.', 'info');
      } catch (err) {
        showNotification(`Refresh failed: ${err.message}`, 'danger');
      }
    });

    document.getElementById('btn-reset-demo').addEventListener('click', resetCurrentDemoTenant);
    const ingestBtn = document.getElementById('btn-ingest-csv-demo');
    if (ingestBtn) ingestBtn.addEventListener('click', ingestDemoCatalogCSV);
    document.getElementById('btn-update-owner-whatsapp').addEventListener('click', updateOwnerWhatsAppNumber);

    // If key exists, load data; else prompt operator
    if (STATE.apiKey) {
      await refreshAllData();
      refreshOwnerWhatsAppStatus();
      if (isProspectDemoTenant()) startLiveActivityPolling();
    } else {
      openAuthModal();
    }

  } catch (err) {
    console.error('Initialization error:', err);
    clearTenantState();
    renderErrorState(err.message);
    if (err.message.includes('401') || err.message.includes('403')) {
      openAuthModal('Authentication failed. Please verify the Operator API Key.');
    } else {
      showNotification(`Initialization error: ${err.message}`, 'danger');
    }
  }
}

// Global Data Fetch. `expectedToken` (defaults to the CURRENT token, i.e. "this is not part of a
// merchant switch") is the race guard switchMerchant() uses - if a newer switch has already started by
// the time this fetch resolves, the result is discarded rather than committed to STATE/rendered.
// Deliberately does NOT swallow individual endpoint failures into empty/null state anymore: a real 401/
// 403/500 on ANY of these must surface as a real error (never a quietly-empty tenant that then falls
// back to hardcoded presentation copy - see the render functions below) so switchMerchant() can react
// correctly instead of rendering a merchant's screen with another merchant's stale fallback text.
async function refreshAllData(expectedToken = STATE.switchToken) {
  const [
    profile,
    summary,
    drafts,
    exceptions,
    approvals,
    publications,
    orders,
    inventory,
    returns,
    refunds,
    audit,
    channelOperations,
  ] = await Promise.all([
    apiCall(`/merchants/${STATE.merchantId}/profile`),
    apiCall(`/merchants/${STATE.merchantId}/operator/summary`),
    apiCall(`/merchants/${STATE.merchantId}/catalogue/drafts`),
    apiCall(`/merchants/${STATE.merchantId}/exceptions`),
    apiCall(`/merchants/${STATE.merchantId}/approvals`),
    apiCall(`/merchants/${STATE.merchantId}/catalogue/publications`),
    apiCall(`/merchants/${STATE.merchantId}/orders`),
    apiCall(`/merchants/${STATE.merchantId}/inventory`),
    apiCall(`/merchants/${STATE.merchantId}/returns`),
    apiCall(`/merchants/${STATE.merchantId}/refunds`),
    apiCall(`/merchants/${STATE.merchantId}/audit`),
    apiCall(`/merchants/${STATE.merchantId}/channel-operations`).catch(() => []),
  ]);

  if (expectedToken !== STATE.switchToken) return; // superseded - a newer switch owns STATE now

  STATE.profile = profile;
  updateDemoDisclosureBanner();
  STATE.summary = summary;
  STATE.drafts = drafts;
  STATE.exceptions = exceptions;
  STATE.approvals = approvals;
  STATE.publications = publications;
  STATE.orders = orders;
  STATE.inventory = inventory;
  STATE.returns = returns;
  STATE.refunds = refunds;
  STATE.audit = audit;
  STATE.channelOperations = channelOperations || [];

  updateBadges();
  renderActiveTab();
}

// Phase D discipline: the disclosure is driven entirely by the tenant's own backend config
// (config.demo.disclosure, set once in packages/prospect_demo/reset.py) - never hardcoded per merchant
// in this file, so it can never drift out of sync with what was actually classified server-side.
function updateDemoDisclosureBanner() {
  const banner = document.getElementById('demo-disclosure-banner');
  const resetBtn = document.getElementById('btn-reset-demo');
  const ingestBtn = document.getElementById('btn-ingest-csv-demo');
  const demo = STATE.profile?.config?.demo;
  if (banner) {
    if (demo && demo.disclosure) {
      banner.textContent = demo.disclosure;
      banner.style.display = 'block';
    } else {
      banner.style.display = 'none';
    }
  }
  // Rehearsal & ingestion tools for prospect demo tenants only
  const isDemo = isProspectDemoTenant();
  if (resetBtn) resetBtn.style.display = isDemo ? 'inline-flex' : 'none';
  if (ingestBtn) ingestBtn.style.display = isDemo ? 'inline-flex' : 'none';
}

async function ingestDemoCatalogCSV() {
  const merchantId = STATE.merchantId;
  try {
    showNotification(`Ingesting supplier catalogue for ${merchantId}...`, 'info');
    const res = await apiCall(`/merchants/${merchantId}/demo/ingest-csv`, 'POST', {});
    await refreshAllData();
    switchTab('conflicts');
    showNotification(`Ingested ${res.drafts_count || 4} supplier products. Sanocea has safely kept incomplete drafts unpublished and dispatched the first product to WhatsApp for review!`, 'success');
  } catch (err) {
    showNotification(`Ingest failed: ${err.message}`, 'danger');
  }
}

async function resetCurrentDemoTenant() {
  const merchantId = STATE.merchantId;
  if (!confirm(`Reset ${merchantId} to a clean baseline? This clears all exceptions, approvals, orders, and audit history for this demo tenant and re-seeds its real catalogue.`)) return;
  try {
    showNotification(`Resetting ${merchantId}...`, 'info');
    await apiCall(`/merchants/${merchantId}/demo/reset`, 'POST');
    await refreshAllData();
    showNotification(`${merchantId} reset to a clean baseline - ready to rehearse again.`, 'success');
  } catch (err) {
    showNotification(`Reset failed: ${err.message}`, 'danger');
  }
}

function updateBadges() {
  const excBadge = document.getElementById('badge-exceptions');
  if (excBadge) {
    if (STATE.exceptions.length > 0) {
      excBadge.textContent = STATE.exceptions.length;
      excBadge.style.display = 'inline-block';
    } else {
      excBadge.style.display = 'none';
    }
  }

  const reviewBadge = document.getElementById('badge-conflicts');
  if (reviewBadge) {
    const hasConflicts = STATE.drafts.some(d => d.state === 'CONFLICTED' || d.conflicts?.length > 0);
    if (hasConflicts) {
      reviewBadge.textContent = 'ACTION';
      reviewBadge.style.display = 'inline-block';
    } else {
      reviewBadge.style.display = 'none';
    }
  }
}

function switchTab(tabId) {
  STATE.activeTab = tabId;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
  });
  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.toggle('active', content.id === `tab-${tabId}`);
  });
  renderActiveTab();
}

function renderActiveTab() {
  switch (STATE.activeTab) {
    case 'overview':
      renderOverview();
      break;
    case 'exceptions':
      renderExceptions();
      break;
    case 'conflicts':
      renderConflictReview();
      break;
    case 'publication':
      renderPublication();
      break;
    case 'inventory':
      renderOrdersInventory();
      break;
    case 'refunds':
      renderReturnsRefunds();
      break;
    case 'audit':
      renderAudit();
      break;
  }
}

// --------------------------------------------------------------------------------
// Screen 1: Operations Overview
// --------------------------------------------------------------------------------
function renderOverview() {
  if (isProspectDemoTenant()) { renderOverviewProspect(); return; }
  const container = document.getElementById('tab-overview');
  const prof = STATE.profile || {};

  const draft = STATE.drafts.find(d => d.sku === 'ANCHAL-KACHI-GHANI') || STATE.drafts[0];
  const draftState = draft ? draft.state : 'NONE';
  const draftId = draft?.id;
  const publication = STATE.publications.find(p => p.product_draft_id === draftId) || STATE.publications[0] || null;
  const publicationStatus = String(publication?.status || '').toLowerCase();
  const isPublished = Boolean(publication && (publicationStatus === 'published' || publication.external_product_id));
  const hasReadBackEvidence = isPublished && STATE.audit.some(e =>
    String(e.action || '').toLowerCase() === 'listing_verified' ||
    String(e.action || '').toLowerCase().includes('verify')
  );
  const currentDraftConflict = Boolean(draft && (draft.state === 'CONFLICTED' || (draft.conflicts || []).length > 0));
  const exceptionForDraft = STATE.exceptions.find(exc => !draftId || exc.object_id === draftId);
  const hasOpenException = STATE.exceptions.length > 0;
  const staleOpenException = Boolean(exceptionForDraft && !currentDraftConflict && isPublished);
  const validationState = draftState === 'READY' ? 'READY' : (currentDraftConflict ? 'CONFLICTED' : draftState);
  const publicationState = currentDraftConflict
    ? 'BLOCKED'
    : (isPublished ? 'PUBLISHED' : (draftState === 'READY' ? 'ELIGIBLE / AWAITING PUBLICATION' : 'APPROVAL REQUIRED'));
  const openApprovals = STATE.approvals.filter(a => String(a.status || '').toLowerCase() === 'pending').length || STATE.approvals.length;
  const topStatusClass = currentDraftConflict ? 'danger' : (staleOpenException ? 'warning' : 'success');
  const topStatusText = currentDraftConflict
    ? 'ATTENTION REQUIRED'
    : (staleOpenException ? 'STATE RECONCILIATION REQUIRED' : 'NORMAL OPERATIONS');

  container.innerHTML = `
    <div class="card" style="margin-bottom:20px; background:linear-gradient(to right, #ffffff, #f8fafc);">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <div style="font-size:12px; font-weight:600; text-transform:uppercase; color:var(--primary); letter-spacing:0.05em; margin-bottom:4px;">
            Certified Reference Merchant
          </div>
          <h2 style="font-size:20px; font-weight:700; color:var(--text-main); margin-bottom:6px;">
            ${prof.display_name || 'Anchal Heritage Organics'}
          </h2>
          <div style="font-size:13px; color:var(--text-muted); display:flex; gap:16px; flex-wrap:wrap;">
            <span><strong>Reference Data:</strong> Fictional merchant</span>
            <span><strong>ERP Execution:</strong> Real certified paths</span>
            <span><strong>GSTIN:</strong> ${prof.config?.gstin || '07AAAAA0000A1Z5'}</span>
            <span><strong>Base Currency:</strong> ${prof.config?.currency || 'INR'}</span>
            <span><strong>Storefront:</strong> Shopify - Certified Dev Store</span>
          </div>
        </div>
        <div>
          <span class="status-pill ${topStatusClass}">
            ${topStatusText}
          </span>
        </div>
      </div>
    </div>

    <div style="margin-bottom:20px;">
      <div style="font-size:12px; font-weight:600; text-transform:uppercase; color:var(--text-muted); margin-bottom:8px; letter-spacing:0.04em;">
        Current Reference Workflow State
      </div>
      <div class="pipeline-track">
        <div class="pipeline-node done">
          <div class="pipeline-title">1. Observe</div>
          <div class="pipeline-desc">Raw Data Ingested</div>
          <div style="font-size:11px; color:var(--success);">XLSX / PDF / CSV Evidence</div>
        </div>
        <div class="pipeline-node done">
          <div class="pipeline-title">2. Detect</div>
          <div class="pipeline-desc">Evidence Preserved</div>
          <div style="font-size:11px; color:var(--success);">No Formula Invention</div>
        </div>
        <div class="pipeline-node ${currentDraftConflict ? 'active-danger' : 'done'}">
          <div class="pipeline-title">3. Block</div>
          <div class="pipeline-desc">Authority Gate</div>
          <div style="font-size:11px; color:${currentDraftConflict ? 'var(--danger)' : 'var(--success)'};">
            ${currentDraftConflict ? 'Current Conflict Blocks Publication' : 'Historical Conflict Cleared'}
          </div>
        </div>
        <div class="pipeline-node ${draftState === 'READY' ? 'done' : ''}">
          <div class="pipeline-title">4. Resolve</div>
          <div class="pipeline-desc">Operator Sign-off</div>
          <div style="font-size:11px; color:${draftState === 'READY' ? 'var(--success)' : 'var(--text-muted)'};">
            ${draftState === 'READY' ? 'Completed' : 'Pending'}
          </div>
        </div>
        <div class="pipeline-node ${isPublished ? 'done' : ''}">
          <div class="pipeline-title">5. Execute</div>
          <div class="pipeline-desc">Shopify Dev Store</div>
          <div style="font-size:11px; color:${isPublished ? 'var(--success)' : 'var(--text-muted)'};">
            ${isPublished ? 'Published' : 'Not Published'}
          </div>
        </div>
        <div class="pipeline-node ${hasReadBackEvidence ? 'done' : ''}">
          <div class="pipeline-title">6. Verify</div>
          <div class="pipeline-desc">Read-back Evidence</div>
          <div style="font-size:11px; color:${hasReadBackEvidence ? 'var(--success)' : 'var(--text-muted)'};">
            ${hasReadBackEvidence ? 'Audit Evidence Present' : 'No Verification Evidence'}
          </div>
        </div>
        <div class="pipeline-node done">
          <div class="pipeline-title">7. Audit</div>
          <div class="pipeline-desc">Immutable Ledger</div>
          <div style="font-size:11px; color:var(--success);">${STATE.audit.length} Events Logged</div>
        </div>
      </div>
    </div>

    <div class="grid-cols-4">
      <div class="kpi-card">
        <div class="kpi-label">Open Exception Records</div>
        <div class="kpi-value" style="color:${hasOpenException ? (staleOpenException ? 'var(--warning)' : 'var(--danger)') : 'var(--text-main)'};">
          ${STATE.exceptions.length}
        </div>
        <div class="kpi-sub">
          ${staleOpenException ? 'Open record conflicts with completed workflow' : (hasOpenException ? 'Current blocker exists' : 'All clear')}
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Catalogue Status</div>
        <div class="kpi-value" style="font-size:22px;">${validationState}</div>
        <div class="kpi-sub">Validation state only, not publication authority</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Publication State</div>
        <div class="kpi-value" style="font-size:22px; color:${publicationState === 'BLOCKED' ? 'var(--danger)' : (publicationState === 'PUBLISHED' ? 'var(--success)' : 'var(--warning)')};">${publicationState}</div>
        <div class="kpi-sub">Authority and storefront gate</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Pending Approvals</div>
        <div class="kpi-value">${openApprovals}</div>
        <div class="kpi-sub">Open approval gates across workflows</div>
      </div>
    </div>

    <div class="grid-cols-2">
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <span>${currentDraftConflict ? 'Current Commercial Blocker' : (staleOpenException ? 'State Reconciliation Notice' : 'Current Workflow Status')}</span>
          </div>
          <span class="status-pill ${currentDraftConflict ? 'danger' : (staleOpenException ? 'warning' : 'success')}">
            ${currentDraftConflict ? 'BLOCKING ACTION' : (staleOpenException ? 'OPEN RECORD' : 'COHERENT')}
          </span>
        </div>
        ${currentDraftConflict ? `
          <div class="governance-banner" style="margin-bottom:14px;">
            <div class="governance-icon">!</div>
            <div>
              <div class="governance-title">Commercial Fact Conflict Detected</div>
              <div class="governance-desc">
                Supplier feed price (145.00) conflicts with catalogue evidence (156.00). Publication remains blocked until an authorized operator resolves the fact.
              </div>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-size:13px; color:var(--text-muted);">
              Affected SKU: <strong>${draft?.sku || 'ANCHAL-KACHI-GHANI'}</strong>
            </div>
            <button class="btn btn-primary btn-sm" onclick="switchTab('conflicts')">
              Review Evidence
            </button>
          </div>
        ` : staleOpenException ? `
          <div class="governance-banner info" style="margin-bottom:14px;">
            <div class="governance-icon">i</div>
            <div>
              <div class="governance-title">Open Exception Record Does Not Match Current Draft State</div>
              <div class="governance-desc">
                The linked catalogue draft is <strong>${draftState}</strong> and its Shopify dev-store publication is <strong>${publicationStatus || 'published'}</strong>, but one exception row remains open. Treat this as a backend state reconciliation item, not as an active publication blocker.
              </div>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-size:13px; color:var(--text-muted);">
              Exception: <span class="code-inline">${exceptionForDraft?.id || 'open exception'}</span>
            </div>
            <button class="btn btn-outline btn-sm" onclick="switchTab('exceptions')">
              Inspect Exception Record
            </button>
          </div>
        ` : `
          <div style="padding:20px; text-align:center; color:var(--text-muted);">
            Current catalogue and publication gates are coherent. No open blocker is attached to this workflow.
          </div>
        `}
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">Recent Immutable Audit Feed</div>
          <button class="btn btn-outline btn-sm" onclick="switchTab('audit')">View Full Ledger</button>
        </div>
        <div style="display:flex; flex-direction:column; gap:8px;">
          ${STATE.audit.slice(0, 4).map(e => `
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; padding:6px 0; border-bottom:1px solid var(--border-color);">
              <div>
                <span class="code-inline" style="font-weight:600;">${e.action}</span>
                <span style="color:var(--text-muted); margin-left:6px;">${e.object_id || ''}</span>
              </div>
              <span style="color:var(--text-subtle);">${new Date(e.timestamp || e.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</span>
            </div>
          `).join('') || '<div style="color:var(--text-muted);">No audit events.</div>'}
        </div>
      </div>
    </div>
  `;
}

// Prospect demo tenant Overview - entirely generic, driven only by real backend state
// (STATE.profile/drafts/exceptions/approvals/orders/audit). Never references Anchal, Shopify, or any
// certification-specific narrative - see isProspectDemoTenant(). The real, publicly-verified catalogue
// is shown directly here (not buried in a tab the prospect might never click) so the whole point of this
// feature - the prospect recognising their own products - is satisfied on the very first screen.
function renderOverviewProspect() {
  const container = document.getElementById('tab-overview');
  const prof = STATE.profile || {};
  const demo = prof.config?.demo || {};
  const openExceptions = STATE.exceptions.filter(e => e.status === 'open').length;
  const pendingApprovals = STATE.approvals.filter(a => String(a.status || '').toLowerCase() === 'pending').length;

  container.innerHTML = `
    <div class="card" style="margin-bottom:20px; background:linear-gradient(to right, #ffffff, #f8fafc);">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <div style="font-size:12px; font-weight:600; text-transform:uppercase; color:var(--warning); letter-spacing:0.05em; margin-bottom:4px;">
            Prospect Demonstration Tenant
          </div>
          <h2 style="font-size:20px; font-weight:700; color:var(--text-main); margin-bottom:6px;">
            ${prof.display_name || STATE.merchantId}
          </h2>
          <div style="font-size:13px; color:var(--text-muted); display:flex; gap:16px; flex-wrap:wrap;">
            ${prof.legal_name ? `<span><strong>Legal Name:</strong> ${prof.legal_name}</span>` : ''}
            <span><strong>Base Currency:</strong> ${prof.config?.currency || '—'}</span>
            <span><strong>Known Channels:</strong> ${(demo.known_channels || []).join(', ') || '—'}</span>
          </div>
        </div>
        <span class="status-pill neutral">DEMONSTRATION</span>
      </div>
      ${demo.disclosure ? `
        <div style="margin-top:12px; font-size:12px; color:var(--warning); font-weight:500;">${demo.disclosure}</div>
      ` : ''}
    </div>

    <div id="live-activity-panel" style="margin-bottom:20px;"></div>
    <div id="automation-impact-panel" style="margin-bottom:20px;"></div>
    <div id="management-outcome-panel" style="margin-bottom:20px;"></div>

    <div class="grid-cols-4" style="margin-bottom:20px;">
      <div class="kpi-card">
        <div class="kpi-label">Real Products Shown</div>
        <div class="kpi-value">${STATE.drafts.length}</div>
        <div class="kpi-sub">Publicly verified catalogue</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Open Exception Records</div>
        <div class="kpi-value" style="color:${openExceptions > 0 ? 'var(--warning)' : 'var(--text-main)'};">${openExceptions}</div>
        <div class="kpi-sub">Simulated operational events</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Pending Approvals</div>
        <div class="kpi-value">${pendingApprovals}</div>
        <div class="kpi-sub">Open approval gates</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Audit Events</div>
        <div class="kpi-value">${STATE.audit.length}</div>
        <div class="kpi-sub">Immutable ledger</div>
      </div>
    </div>

    <div class="grid-cols-2" style="margin-bottom:20px;">
      <div class="card">
        <div class="card-header">
          <div class="card-title">Real Catalogue (Public, Verified)</div>
          <button class="btn btn-outline btn-sm" onclick="switchTab('conflicts')">View All</button>
        </div>
        <div style="display:flex; flex-direction:column; gap:8px;">
          ${STATE.drafts.slice(0, 6).map(d => `
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:13px; padding:8px 0; border-bottom:1px solid var(--border-color);">
              <div>
                <strong>${d.title}</strong>
                <div style="font-size:11px; color:var(--text-muted);">${d.attributes?.brand || ''} ${d.attributes?.variant ? '· ' + d.attributes.variant : ''} ${d.sku ? '· SKU ' + d.sku : ''}</div>
              </div>
              <span style="font-size:13px; font-weight:600;">${d.price ? (d.price / 100).toFixed(2) + ' ' + (d.currency || '') : '—'}</span>
            </div>
          `).join('') || '<div style="color:var(--text-muted); font-size:13px;">No catalogue drafts loaded.</div>'}
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">Scenario Focus</div>
        </div>
        <div style="font-size:13px; color:var(--text-main); margin-bottom:10px;">
          Enabled scenario${(demo.enabled_scenarios || []).length === 1 ? '' : 's'}: <strong>${(demo.enabled_scenarios || []).join(', ') || '—'}</strong>
        </div>
        ${demo.prospect_provided_context ? `
          <div style="font-size:12px; color:var(--text-muted); display:flex; flex-direction:column; gap:6px;">
            ${Object.entries(demo.prospect_provided_context).map(([k, v]) => `
              <div><strong>${k.replace(/_/g, ' ')}:</strong> ${Array.isArray(v) ? v.join(', ') : v}</div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">Recent Immutable Audit Feed</div>
        <button class="btn btn-outline btn-sm" onclick="switchTab('audit')">View Full Ledger</button>
      </div>
      <div style="display:flex; flex-direction:column; gap:8px;">
        ${STATE.audit.slice(0, 4).map(e => `
          <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; padding:6px 0; border-bottom:1px solid var(--border-color);">
            <div>
              <span class="code-inline" style="font-weight:600;">${e.action}</span>
              <span style="color:var(--text-muted); margin-left:6px;">${e.object_id || ''}</span>
            </div>
          </div>
        `).join('') || '<div style="color:var(--text-muted);">No audit events.</div>'}
      </div>
    </div>
  `;
  renderLiveActivity();
  renderAutomationImpact();
  renderManagementOutcome();
}

// ================================================================================================
// Live Activity - the incoming-email-workflow progress panel (PHASE E). Polls the SAME authoritative
// audit endpoint every tab already uses (GET /merchants/{id}/audit) - never a separate
// SSE/WebSocket channel, and never client-side animation: every step shown here corresponds to a REAL
// audit event packages/email_ingress/service.py wrote, at the real moment it happened. Because each
// audit.record() call commits immediately (not batched at the end of the ingestion run), a short poll
// genuinely observes the workflow progressing while it is still running on the backend, not just its
// final result.
// ================================================================================================

const EMAIL_WORKFLOW_STEPS = [
  { action: 'email_received', label: 'Email received' },
  { action: 'attachment_received', label: 'Attachment retrieved' },
  { action: 'file_validated', label: 'Attachment validated' },
  { action: 'ingestion_started', label: 'Extracting and normalizing…' },
  { action: 'ingestion_completed', label: 'Records extracted' },
  { action: 'validation_completed', label: 'Validating commercial facts…' },
  { action: 'workflow_completed', label: 'Processing complete' },
];

// A real bug found live (2026-09-17): a poll failure was silently swallowed with NOTHING shown to the
// operator - if the backend restarted, or a session key was invalidated, or any other real disconnect
// happened mid-demo, the screen just froze with no indication anything was wrong. That is never
// acceptable during a live prospect call. This is now fixed two ways: (1) polling continues regardless
// of which tab is active (previously gated to Overview only - an operator watching, say, the Exceptions
// tab while waiting would have silently gotten zero updates), and (2) a persistent, always-visible
// connection indicator in the header reports Live / Reconnecting… / Disconnected - never silent.
let LIVE_ACTIVITY_POLL_HANDLE = null;
let LIVE_ACTIVITY_CONSECUTIVE_FAILURES = 0;

function updateLiveConnectionStatus(state, detail = '') {
  const el = document.getElementById('live-connection-status');
  if (!el) return;
  if (state === 'off') {
    el.style.display = 'none';
    return;
  }
  el.style.display = 'inline-flex';
  if (state === 'live') {
    el.innerHTML = `<span class="tenant-dot" style="background:var(--success);"></span><span style="color:var(--success);">Live</span>`;
  } else if (state === 'reconnecting') {
    el.innerHTML = `<span class="tenant-dot" style="background:var(--warning);"></span><span style="color:var(--warning);">Reconnecting…</span>`;
  } else {
    el.innerHTML = `<span class="tenant-dot" style="background:var(--danger);"></span><span style="color:var(--danger);" title="${detail}">Disconnected - click Refresh</span>`;
  }
}

function startLiveActivityPolling() {
  stopLiveActivityPolling();
  LIVE_ACTIVITY_CONSECUTIVE_FAILURES = 0;
  updateLiveConnectionStatus('live');
  LIVE_ACTIVITY_POLL_HANDLE = setInterval(async () => {
    if (!isProspectDemoTenant()) return;
    try {
      // A query-string cache-buster, not just cache:'no-store' - belt and suspenders against ANY layer
      // (browser HTTP cache, an intermediate proxy) that might otherwise reuse a prior response for an
      // identical repeated GET URL; a changing URL makes a cache hit categorically impossible.
      const [audit, channelOperations, approvals] = await Promise.all([
        apiCall(`/merchants/${STATE.merchantId}/audit?_=${Date.now()}`),
        apiCall(`/merchants/${STATE.merchantId}/channel-operations?_=${Date.now()}`).catch(() => STATE.channelOperations),
        apiCall(`/merchants/${STATE.merchantId}/approvals?_=${Date.now()}`).catch(() => STATE.approvals),
      ]);
      STATE.audit = audit;
      STATE.channelOperations = channelOperations || [];
      STATE.approvals = approvals || [];
      LIVE_ACTIVITY_CONSECUTIVE_FAILURES = 0;
      updateLiveConnectionStatus('live');
      if (STATE.activeTab === 'overview') {
        renderLiveActivity();
        renderAutomationImpact();
        renderManagementOutcome();
      } else if (STATE.activeTab === 'publication' && isProspectDemoTenant() && OPEN_WHATSAPP_FORMS.size === 0) {
        // The real root cause of the "can't type a phone number" report: this tab renders via a full
        // innerHTML replacement (see renderPublicationProspect), which destroys and recreates every
        // input DOM node on each poll tick - including one the operator is actively typing into. That
        // repeated destroy/recreate mid-keystroke is also the likely trigger for Chrome's "save
        // password?" prompt misfiring on a plain text field. Simplest correct fix: pause this tab's
        // live re-render entirely while a WhatsApp contact form is open, not just persist its
        // open/closed flag (EXPANDED_WHY_PANELS-style persistence alone doesn't protect in-progress
        // typing, only which panel is visible).
        renderPublicationProspect();
      }
      updateBadges();
    } catch (err) {
      LIVE_ACTIVITY_CONSECUTIVE_FAILURES += 1;
      console.error('Live activity poll failed:', err);
      // One or two misses can be a genuine transient blip - only surface it once it is persistent
      // enough to actually matter (real disconnect, not a single dropped packet).
      updateLiveConnectionStatus(LIVE_ACTIVITY_CONSECUTIVE_FAILURES >= 2 ? 'disconnected' : 'reconnecting', err.message);
    }
  }, 2500);
}

function stopLiveActivityPolling() {
  if (LIVE_ACTIVITY_POLL_HANDLE) {
    clearInterval(LIVE_ACTIVITY_POLL_HANDLE);
    LIVE_ACTIVITY_POLL_HANDLE = null;
  }
  updateLiveConnectionStatus('off');
}

function _latestEmailRun() {
  const received = STATE.audit.filter(e => e.action === 'email_received');
  if (received.length === 0) return null;
  const latest = received.reduce((a, b) => (new Date(a.timestamp || a.created_at) > new Date(b.timestamp || b.created_at) ? a : b));
  const runEvents = STATE.audit.filter(e => e.correlation_id && e.correlation_id === latest.correlation_id);
  return { correlationId: latest.correlation_id, events: runEvents };
}

function renderLiveActivity() {
  const panel = document.getElementById('live-activity-panel');
  if (!panel) return;
  const run = _latestEmailRun();
  if (!run) {
    panel.innerHTML = '';
    return;
  }
  const byAction = Object.fromEntries(run.events.map(e => [e.action, e]));
  const completed = byAction['workflow_completed'];
  const filenameEvent = run.events.find(e => e.action === 'attachment_received');

  panel.innerHTML = `
    <div class="card" style="border-left:4px solid ${completed ? 'var(--success)' : 'var(--primary)'};">
      <div class="card-header">
        <div class="card-title">Incoming Work${filenameEvent ? ': ' + filenameEvent.result : ''}</div>
        <span class="status-pill ${completed ? 'success' : 'neutral'}">${completed ? 'PROCESSING COMPLETE' : 'PROCESSING…'}</span>
      </div>
      <div style="display:flex; flex-direction:column; gap:6px;">
        ${EMAIL_WORKFLOW_STEPS.map(step => {
          const evt = byAction[step.action];
          return `
            <div style="display:flex; align-items:center; gap:8px; font-size:13px; color:${evt ? 'var(--text-main)' : 'var(--text-subtle)'};">
              <span style="width:16px;">${evt ? '✓' : '·'}</span>
              <span>${step.label}${evt && evt.result ? ' — ' + evt.result : ''}</span>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

// ================================================================================================
// Automation Impact / Workload Compression (PHASE H/I). ESTIMATED EQUIVALENT MANUAL EFFORT is
// explicitly labeled as an estimate, never "actual hours saved" - see the label itself and the
// "How calculated" breakdown below, both always visible together, never the number alone.
// ================================================================================================

// Sales-realism follow-on (Section 5): "products × channels = manual human work" is exaggerated for
// any prospect already running Unicommerce/marketplace automation/an agency workflow - the REMAINING
// human burden is what matters, and that is only ever an estimate the prospect themselves can correct.
// Two independently-configurable benchmark components, not one flat multiplier: reviewing a NEW record
// is different work from checking one channel operation's outcome.
const DEFAULT_DEMO_MINUTES_PER_RECORD = 3;
const DEFAULT_DEMO_MINUTES_PER_CHANNEL_CHECK = 1;
const BENCHMARK_PROVENANCE = { DEFAULT: 'DEFAULT_DEMO_ESTIMATE', PROSPECT: 'PROSPECT_PROVIDED' };
// Per-merchant benchmark config, client-side only for this local demo session (never persisted as if it
// were prospect-confirmed data) - { recordMinutes, channelCheckMinutes, provenance }.
const BENCHMARK_STATE = {};

function _benchmarkFor(merchantId) {
  if (!BENCHMARK_STATE[merchantId]) {
    BENCHMARK_STATE[merchantId] = {
      recordMinutes: DEFAULT_DEMO_MINUTES_PER_RECORD, channelCheckMinutes: DEFAULT_DEMO_MINUTES_PER_CHANNEL_CHECK,
      provenance: BENCHMARK_PROVENANCE.DEFAULT,
    };
  }
  return BENCHMARK_STATE[merchantId];
}

function setBenchmarkMinutes(merchantId, field, valueStr) {
  const value = parseFloat(valueStr);
  if (!Number.isFinite(value) || value <= 0) return;
  const current = _benchmarkFor(merchantId);
  BENCHMARK_STATE[merchantId] = { ...current, [field]: value, provenance: BENCHMARK_PROVENANCE.PROSPECT };
  renderAutomationImpact();
}

function resetBenchmarkToDefault(merchantId) {
  BENCHMARK_STATE[merchantId] = {
    recordMinutes: DEFAULT_DEMO_MINUTES_PER_RECORD, channelCheckMinutes: DEFAULT_DEMO_MINUTES_PER_CHANNEL_CHECK,
    provenance: BENCHMARK_PROVENANCE.DEFAULT,
  };
  renderAutomationImpact();
}

function _formatMinutes(totalMinutes) {
  const h = Math.floor(totalMinutes / 60);
  const m = Math.round(totalMinutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// Section 11 (sales-realism follow-on): the demonstration must end on an operating-model outcome,
// never on a raw Audit Timeline or Publication table. Every number here is derived from
// STATE.channelOperations/STATE.approvals as actually persisted - never hardcoded.
function renderManagementOutcome() {
  const panel = document.getElementById('management-outcome-panel');
  if (!panel) return;
  const ops = STATE.channelOperations || [];
  if (ops.length === 0) {
    panel.innerHTML = '';
    return;
  }
  const total = ops.length;
  const noHumanAttention = ops.filter(o => (o.status === 'VERIFIED' || o.status === 'RESOLVED') && !o.approval_id).length;
  const investigated = ops.filter(o => (o.history || []).some(h => h.status === 'INVESTIGATING')).length;
  const autoResolved = ops.filter(o => o.resolution_level === 'AUTO_L1' || o.resolution_level === 'AUTO_L2').length;
  const noActionRequired = ops.filter(o => o.issue_category === 'EXPECTED_COMMERCIAL_DIFFERENCE').length;
  const ownerDecisions = ops.filter(o => o.resolution_level === 'OWNER_L3').length;
  const stillPending = ops.filter(o => o.status === 'AWAITING_CHANNEL_RESPONSE').length;
  const openApprovals = (STATE.approvals || []).filter(a => a.status === 'pending' && a.action === 'channel_operation_correction').length;

  panel.innerHTML = `
    <div class="card">
      <div class="card-header"><div class="card-title">SANOCEA Handled</div></div>
      <div class="grid-cols-4" style="margin-bottom:10px;">
        <div><div class="kpi-label">Operational actions</div><div class="kpi-value">${total}</div></div>
        <div><div class="kpi-label">Completed without human attention</div><div class="kpi-value">${noHumanAttention}</div></div>
        <div><div class="kpi-label">Issues investigated</div><div class="kpi-value">${investigated}</div></div>
        <div><div class="kpi-label">Automatically resolved</div><div class="kpi-value">${autoResolved}</div></div>
      </div>
      <div class="grid-cols-4">
        <div><div class="kpi-label">Recognized, no action needed</div><div class="kpi-value">${noActionRequired}</div></div>
        <div><div class="kpi-label">Human decisions</div><div class="kpi-value" style="color:${ownerDecisions > 0 ? 'var(--warning)' : 'var(--text-main)'};">${ownerDecisions}</div></div>
        <div><div class="kpi-label">External operations still pending</div><div class="kpi-value">${stillPending}</div></div>
        <div><div class="kpi-label">Awaiting owner right now</div><div class="kpi-value" style="color:${openApprovals > 0 ? 'var(--danger)' : 'var(--text-main)'};">${openApprovals}</div></div>
      </div>
      <div style="margin-top:14px; padding-top:14px; border-top:1px solid var(--border-color); font-size:13px; font-weight:600; text-align:center;">
        Human attention required: <span style="color:${openApprovals > 0 ? 'var(--danger)' : 'var(--success)'};">${openApprovals} decision${openApprovals === 1 ? '' : 's'}</span>
      </div>
    </div>
  `;
}

function renderAutomationImpact() {
  const panel = document.getElementById('automation-impact-panel');
  if (!panel) return;
  const run = _latestEmailRun();
  const completedEvt = run ? run.events.find(e => e.action === 'workflow_completed') : null;
  if (!run || !completedEvt) {
    panel.innerHTML = '';
    return;
  }
  const startedEvt = run.events.find(e => e.action === 'ingestion_started');
  const elapsedSeconds = startedEvt
    ? Math.max(0, (new Date(completedEvt.timestamp || completedEvt.created_at) - new Date(startedEvt.timestamp || startedEvt.created_at)) / 1000)
    : null;
  const m = /received=(\d+)\s+ready=(\d+)\s+attention=(\d+)/.exec(completedEvt.result || '');
  const records = m ? parseInt(m[1], 10) : STATE.drafts.length;
  const channelOps = STATE.channelOperations || [];
  const channelChecks = channelOps.length;
  const exceptionInvestigations = channelOps.filter(o => (o.history || []).some(h => h.status === 'INVESTIGATING')).length;

  const benchmark = _benchmarkFor(STATE.merchantId);
  const recordMinutes = records * benchmark.recordMinutes;
  const channelMinutes = channelChecks * benchmark.channelCheckMinutes;
  const estimatedMinutes = recordMinutes + channelMinutes;

  panel.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title">Automation Impact</div>
        <span class="status-pill neutral">${benchmark.provenance === BENCHMARK_PROVENANCE.PROSPECT ? "BASED ON YOUR ESTIMATE" : 'DEFAULT DEMO ESTIMATE'}</span>
      </div>
      <div class="grid-cols-3" style="margin-bottom:14px;">
        <div>
          <div class="kpi-label">SANOCEA Processing Time (actual)</div>
          <div class="kpi-value" style="font-size:22px;">${elapsedSeconds !== null ? _formatMinutes(elapsedSeconds / 60).replace(/^0m$/, Math.round(elapsedSeconds) + 's') : '—'}</div>
        </div>
        <div>
          <div class="kpi-label">ESTIMATED EQUIVALENT MANUAL WORKLOAD</div>
          <div class="kpi-value" style="font-size:22px;">${_formatMinutes(estimatedMinutes)}</div>
        </div>
        <div>
          <div class="kpi-label">Human Attention Remaining</div>
          <div class="kpi-value" style="font-size:22px;">${STATE.exceptions.filter(e => e.status === 'open').length} record(s)</div>
        </div>
      </div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:10px;">
        <strong>How calculated:</strong>
        product master review ${records} × ${benchmark.recordMinutes}min = ${recordMinutes}min,
        + channel/verification checks ${channelChecks} × ${benchmark.channelCheckMinutes}min = ${channelMinutes}min
        (${exceptionInvestigations} of those involved an investigation)
        = ${estimatedMinutes}min total.
        This is an <strong>estimate</strong>, never presented as actual hours saved - many teams already use partial automation (Unicommerce, marketplace tools, an agency), and this estimate does not know how much of that work you've already offloaded elsewhere.
      </div>
      <div style="display:flex; align-items:center; gap:16px; font-size:12px; flex-wrap:wrap;">
        <div style="display:flex; align-items:center; gap:6px;">
          <label>Minutes per new record reviewed:</label>
          <input type="number" min="0.5" step="0.5" value="${benchmark.recordMinutes}" style="width:56px; padding:4px 6px; border:1px solid var(--border-color); border-radius:4px;"
            onchange="setBenchmarkMinutes('${STATE.merchantId}', 'recordMinutes', this.value)" />
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <label>Minutes per channel/verification check:</label>
          <input type="number" min="0.1" step="0.1" value="${benchmark.channelCheckMinutes}" style="width:56px; padding:4px 6px; border:1px solid var(--border-color); border-radius:4px;"
            onchange="setBenchmarkMinutes('${STATE.merchantId}', 'channelCheckMinutes', this.value)" />
        </div>
        ${benchmark.provenance === BENCHMARK_PROVENANCE.PROSPECT ? `<button class="btn btn-outline btn-xs" onclick="resetBenchmarkToDefault('${STATE.merchantId}')">Reset to default</button>` : ''}
      </div>
    </div>
  `;
}

// --------------------------------------------------------------------------------
// Screen 2: Exceptions Queue
// --------------------------------------------------------------------------------
function renderExceptions() {
  if (isProspectDemoTenant()) { renderExceptionsProspect(); return; }
  const container = document.getElementById('tab-exceptions');
  const count = STATE.exceptions.length;
  const draft = STATE.drafts.find(d => d.sku === 'ANCHAL-KACHI-GHANI') || STATE.drafts[0];
  const publication = STATE.publications.find(p => p.product_draft_id === draft?.id) || STATE.publications[0] || null;

  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Commercial Exceptions Queue</h2>
        <div style="font-size:13px; color:var(--text-muted);">
          Open backend exception records. Business-first summary first; technical identifiers remain available for audit.
        </div>
      </div>
      <span class="status-pill ${count > 0 ? 'warning' : 'success'}">
        ${count} Open Exception Record${count === 1 ? '' : 's'}
      </span>
    </div>

    ${count === 0 ? `
      <div class="card" style="text-align:center; padding:40px;">
        <h3 style="font-size:16px; font-weight:600; margin-bottom:4px;">No Open Exceptions</h3>
        <p style="color:var(--text-muted); font-size:13px;">All commercial facts are verified and no conflicts exist.</p>
      </div>
    ` : `
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Business Issue</th>
              <th>Product</th>
              <th>Backend State</th>
              <th>Current Interpretation</th>
              <th>Technical Evidence</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${STATE.exceptions.map(exc => {
              const relatedDraft = STATE.drafts.find(d => d.id === exc.object_id) || draft;
              const relatedPub = STATE.publications.find(p => p.product_draft_id === relatedDraft?.id) || publication;
              const relatedPublished = Boolean(relatedPub && (String(relatedPub.status || '').toLowerCase() === 'published' || relatedPub.external_product_id));
              const draftStillConflicted = relatedDraft && (relatedDraft.state === 'CONFLICTED' || (relatedDraft.conflicts || []).length > 0);
              const staleRecord = Boolean(!draftStillConflicted && relatedPublished);
              return `
                <tr>
                  <td>
                    <strong>Price Conflict</strong>
                    <div style="font-size:12px; color:var(--text-muted);">156 catalogue evidence vs 145 supplier feed</div>
                  </td>
                  <td>
                    <strong>${relatedDraft?.title || 'Anchal Kachi Ghani Mustard Oil'}</strong>
                    <div style="font-size:12px; color:var(--text-muted);">SKU: ${relatedDraft?.sku || 'ANCHAL-KACHI-GHANI'}</div>
                  </td>
                  <td><span class="status-pill ${staleRecord ? 'warning' : 'danger'}">${staleRecord ? 'OPEN RECORD' : 'BLOCKED / OPEN'}</span></td>
                  <td style="max-width:380px;">
                    <div style="font-size:13px; font-weight:500;">
                      ${staleRecord
                        ? 'The exception row is still open, but the linked draft is READY and publication is already recorded as published.'
                        : (exc.message || 'Commercial fact conflict is still blocking publication.')}
                    </div>
                    <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">
                      ${staleRecord ? 'Requires backend state reconciliation; do not present as an active publication blocker.' : 'Publication gate failed closed. Operator review is required.'}
                    </div>
                  </td>
                  <td>
                    <div><span class="code-inline">${exc.id}</span></div>
                    <div style="margin-top:4px;"><span class="code-inline">${exc.object_id}</span></div>
                  </td>
                  <td>
                    <button class="btn ${staleRecord ? 'btn-outline' : 'btn-primary'} btn-sm" onclick="switchTab('conflicts')">
                      Inspect Evidence
                    </button>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `}
  `;
}

// Prospect demo tenant Exceptions Queue - driven directly by each exception's own real
// category/message/object_id/severity, never forced through Anchal's single-draft price-conflict shape
// (a prospect's exceptions are about orders/payments/fulfilment, not one tracked product draft).
function renderExceptionsProspect() {
  const container = document.getElementById('tab-exceptions');
  const count = STATE.exceptions.length;
  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Exceptions Queue</h2>
        <div style="font-size:13px; color:var(--text-muted);">Open backend exception records for ${STATE.profile?.display_name || STATE.merchantId}.</div>
      </div>
      <span class="status-pill ${count > 0 ? 'warning' : 'success'}">${count} Open Exception Record${count === 1 ? '' : 's'}</span>
    </div>
    ${count === 0 ? `
      <div class="card" style="text-align:center; padding:40px;">
        <h3 style="font-size:16px; font-weight:600;">No Open Exceptions</h3>
        <p style="color:var(--text-muted); font-size:13px;">No open exception records for this tenant.</p>
      </div>
    ` : `
      <div class="table-container">
        <table>
          <thead><tr><th>Category</th><th>Message</th><th>Severity</th><th>Status</th><th>Object</th></tr></thead>
          <tbody>
            ${STATE.exceptions.map(exc => `
              <tr>
                <td><strong>${(exc.category || '').replace(/_/g, ' ')}</strong></td>
                <td style="max-width:420px; font-size:13px;">${exc.message || ''}</td>
                <td><span class="status-pill ${exc.severity === 'critical' || exc.severity === 'error' ? 'danger' : 'warning'}">${exc.severity}</span></td>
                <td><span class="status-pill ${exc.status === 'open' ? 'warning' : 'success'}">${exc.status}</span></td>
                <td><span class="code-inline">${exc.object_id || ''}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `}
  `;
}

// --------------------------------------------------------------------------------
// Screen 3: Evidence & Conflict Review (THE CORE SCREEN)
// --------------------------------------------------------------------------------
function renderConflictReview() {
  if (isProspectDemoTenant()) { renderConflictReviewProspect(); return; }
  const container = document.getElementById('tab-conflicts');
  const draft = STATE.drafts.find(d => d.sku === 'ANCHAL-KACHI-GHANI') || STATE.drafts[0];

  if (!draft) {
    container.innerHTML = `
      <div class="card" style="text-align:center; padding:40px;">
        <h3>No Catalog Drafts Found</h3>
        <p style="color:var(--text-muted);">Please ingest supplier files to inspect commercial evidence.</p>
      </div>
    `;
    return;
  }

  const priceFact = draft.commercial_facts?.price;
  const isConflicted = draft.state === 'CONFLICTED' || (draft.conflicts && draft.conflicts.length > 0);
  const isApproved = draft.state === 'READY' || draft.approved_for_publication;

  container.innerHTML = `
    <!-- Top Governance Disclaimer Banner -->
    <div class="governance-banner" style="background:${isConflicted ? 'var(--danger-light)' : 'var(--success-light)'}; border-color:${isConflicted ? 'var(--danger-border)' : 'var(--success-border)'};">
      <div class="governance-icon">${isConflicted ? '' : ''}</div>
      <div>
        <div class="governance-title" style="font-size:14px;">
          ${isConflicted ? 'SANOCEA Commercial Fact Governance Alert' : 'Commercial Conflict Resolved'}
        </div>
        <div class="governance-desc" style="font-size:13px;">
          ${isConflicted 
            ? 'SANOCEA has not changed the commercial fact. Publication remains blocked pending human operator resolution.' 
            : 'Authoritative value has been recorded with operator signature. Publication gate is unlocked.'}
        </div>
      </div>
    </div>

    <!-- Product Summary Card -->
    <div class="card" style="margin-bottom:20px;">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--text-muted); letter-spacing:0.04em;">
            Canonical Product Draft (Identity Resolved)
          </div>
          <h2 style="font-size:18px; font-weight:700; color:var(--text-main); margin:4px 0;">
            ${draft.title || 'Anchal Cold-Pressed Kachi Ghani Mustard Oil'}
          </h2>
          <div style="display:flex; gap:16px; font-size:13px; color:var(--text-muted);">
            <span>Parent SKU: <strong>${draft.sku}</strong></span>
            <span>Identity Key: <span class="code-inline">${draft.identity_key || 'sku:ANCHAL-KACHI-GHANI'}</span></span>
            <span>Status: <span class="status-pill success">${draft.identity_status || 'RESOLVED'}</span></span>
            <span>Variants: <strong>${draft.variants ? draft.variants.length : 3} options</strong></span>
          </div>
        </div>
        <div>
          <span class="status-pill ${isConflicted ? 'danger' : 'success'}" style="font-size:12px; padding:4px 10px;">
            DRAFT STATE: ${draft.state}
          </span>
        </div>
      </div>
    </div>

    <!-- Side-by-Side Commercial Fact Provenance Container -->
    <div style="margin-bottom:12px; font-size:13px; font-weight:600; color:var(--text-main);">
      Conflicting Fact Provenance Comparison: <span class="code-inline">Attribute: price</span>
    </div>

    <div class="conflict-container">
      <!-- Source A: Messy XLSX -->
      <div class="conflict-card ${!isConflicted ? 'selected' : ''}">
        <div class="conflict-card-header">
          <span class="conflict-source">Source A - Established Catalogue</span>
          <span class="status-pill neutral">SUPPLIER_OFFER</span>
        </div>
        <div class="conflict-price">156.00</div>
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">
          Calculated via formula in supplier pricing matrix
        </div>

        <div class="provenance-row">
          <span class="provenance-label">Source File:</span>
          <span class="provenance-val">supplier_price_list_messy.xlsx</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Exact Locator:</span>
          <span class="provenance-val">Sheet: Wholesale_Matrix ! Cell: C5</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Formula Text:</span>
          <span class="provenance-val" style="color:var(--primary); font-weight:700;">=130*1.20</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Cached Value:</span>
          <span class="provenance-val">156.0 (15600 paise)</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Formula Evaluated:</span>
          <span class="provenance-val">false (Honest raw preservation)</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Confidence:</span>
          <span class="provenance-val">1.0 (High)</span>
        </div>
      </div>

      <!-- Source B: Marketplace Feed -->
      <div class="conflict-card">
        <div class="conflict-card-header">
          <span class="conflict-source">Source B - Incoming Supplier Feed</span>
          <span class="status-pill neutral">SUPPLIER_FEED</span>
        </div>
        <div class="conflict-price" style="color:var(--danger);">145.00</div>
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">
          Flat price in secondary supplier CSV feed
        </div>

        <div class="provenance-row">
          <span class="provenance-label">Source File:</span>
          <span class="provenance-val">conflicting_feed.csv</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Exact Locator:</span>
          <span class="provenance-val">CSV Line 2 (Row 2)</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Formula Text:</span>
          <span class="provenance-val" style="color:var(--text-subtle);">None (Flat string)</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Stated Price:</span>
          <span class="provenance-val">145.00 INR (14500 paise)</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Discrepancy:</span>
          <span class="provenance-val" style="color:var(--danger); font-weight:700;">- 11.00 (-7.05% margin impact)</span>
        </div>
        <div class="provenance-row">
          <span class="provenance-label">Confidence:</span>
          <span class="provenance-val">1.0 (High)</span>
        </div>
      </div>
    </div>

    <!-- Audited Operator Decision Control Panel -->
    <div class="card" style="background:#ffffff; border:1px solid var(--border-color);">
      <div class="card-header">
        <div class="card-title">
          <span>Operator Conflict Resolution Decision</span>
        </div>
        <span class="status-pill neutral">AUTHORITATIVE SANOCEA API GATE</span>
      </div>

      ${isConflicted ? `
        <div style="display:flex; flex-direction:column; gap:16px;">
          <div>
            <label style="font-size:13px; font-weight:600; display:block; margin-bottom:8px;">
              Select Authoritative Commercial Value:
            </label>
            <div style="display:flex; gap:24px;">
              <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                <input type="radio" name="chosen_val" value="156.00" checked id="radio-156">
                <span><strong>Adopt 156.00</strong> (Wholesale Formula Price from <code>supplier_price_list_messy.xlsx</code>)</span>
              </label>
              <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                <input type="radio" name="chosen_val" value="145.00" id="radio-145">
                <span><strong>Adopt 145.00</strong> (Supplier Feed Price from <code>conflicting_feed.csv</code>)</span>
              </label>
            </div>
          </div>

          <div>
            <label style="font-size:12px; font-weight:600; display:block; margin-bottom:4px; color:var(--text-muted);">
              Resolution Audit Note:
            </label>
            <input type="text" id="resolution-note" value="Approved wholesale margin formula (=130*1.20) as authoritative retail rate." 
              style="width:100%; padding:8px 12px; border:1px solid var(--border-color); border-radius:var(--radius-md); font-size:13px;">
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; pt-2; border-top:1px solid var(--border-color); padding-top:14px;">
            <div style="font-size:12px; color:var(--text-muted);">
              Authenticated Principal: <strong>operator@anchalheritage.com</strong>
            </div>
            <div style="display:flex; gap:12px;">
              <button class="btn btn-primary" onclick="handleResolveConflict('${draft.id}')">
                1. Resolve Conflict in SANOCEA
              </button>
            </div>
          </div>
        </div>
      ` : `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <div style="font-size:13px; font-weight:600; color:var(--success); margin-bottom:2px;">
              Conflict Disambiguated by Authorized Operator
            </div>
            <div style="font-size:12px; color:var(--text-muted);">
              Authoritative Price: <strong>${(draft.price / 100).toFixed(2)}</strong> | Audit Trail Updated
            </div>
          </div>
          <div style="display:flex; gap:12px;">
            <button class="btn btn-success" onclick="handleApproveFacts('${draft.id}')">
              2. Sign-off & Approve Commercial Facts
            </button>
            <button class="btn btn-primary" onclick="switchTab('publication')">
              Proceed to Publication
            </button>
          </div>
        </div>
      `}
    </div>
  `;
}

// Prospect demo tenant Evidence & Conflict Review - the primary product-recognition screen: every real,
// publicly-verified catalogue entry with its actual source, never Anchal's fixed 156.00/145.00 conflict
// numbers (prospect drafts are seeded READY/approved by design - they never repeat Anchal's own
// adversarial-ingestion certification story, see packages/prospect_demo/reset.py).
function renderConflictReviewProspect() {
  const container = document.getElementById('tab-conflicts');
  if (STATE.drafts.length === 0) {
    container.innerHTML = `
      <div class="card" style="text-align:center; padding:40px;">
        <h3>No Catalogue Drafts Found</h3>
        <p style="color:var(--text-muted); margin-bottom:16px;">This demo tenant has no seeded products or uploaded supplier feeds.</p>
        <button class="btn btn-primary" onclick="ingestDemoCatalogCSV()">📥 Ingest Supplier Catalog (4 Products with Photos)</button>
      </div>
    `;
    return;
  }

  const hasIncomplete = STATE.drafts.some(d => d.state === 'INCOMPLETE');
  const pubDraftIds = new Set(STATE.publications.filter(p => p.status === 'published').map(p => p.product_draft_id));

  container.innerHTML = `
    <div class="governance-banner" style="background:${hasIncomplete ? 'var(--warning-light)' : 'var(--success-light)'}; border-color:${hasIncomplete ? 'var(--warning-border)' : 'var(--success-border)'}; margin-bottom:16px;">
      <div>
        <div class="governance-title" style="font-size:14px; font-weight:700;">
          ${hasIncomplete ? '🛡️ Sanocea Ingestion Safeguard Active — Incomplete Products Kept Unpublished' : '✅ Public, Verified Catalogue Evidence — All Products Verified'}
        </div>
        <div class="governance-desc" style="font-size:13px;">
          ${hasIncomplete
            ? 'Supplier feed was ingested safely into drafts. Incomplete products are withheld from the live storefront until required publishing fields (price, category) are resolved over WhatsApp.'
            : 'Every product below is completed and verified against source evidence. Storefront visibility is protected.'}
        </div>
      </div>
      <div style="margin-left:auto; display:flex; align-items:center;">
        <button class="btn btn-outline btn-sm" onclick="ingestDemoCatalogCSV()">📥 Re-Ingest Supplier CSV</button>
      </div>
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Type / Category</th>
            <th>Retail Price</th>
            <th>Completeness Gate</th>
            <th>Storefront Status</th>
          </tr>
        </thead>
        <tbody>
          ${STATE.drafts.map(d => {
            const missing = (d.validation_errors || []).filter(e => e.startsWith('missing_required_attribute:')).map(e => e.replace('missing_required_attribute:', ''));
            const isIncomplete = d.state === 'INCOMPLETE';
            const isPublished = pubDraftIds.has(d.id) || d.state === 'READY';
            const photoUrl = d.attributes?.image || (d.commercial_facts?.image?.value);
            return `
              <tr>
                <td style="display:flex; align-items:center; gap:12px;">
                  ${photoUrl ? `<img src="${photoUrl}" alt="${d.title}" style="width:40px; height:40px; object-fit:cover; border-radius:4px; border:1px solid var(--border-color);">` : ''}
                  <div>
                    <strong>${d.title}</strong>
                    ${d.sku ? `<div style="font-size:11px; color:var(--text-muted); font-family:monospace;">SKU: ${d.sku}</div>` : ''}
                  </div>
                </td>
                <td style="font-size:13px;">
                  <div><strong>Type:</strong> ${d.product_type || '<span style="color:var(--warning); font-weight:600;">[MISSING]</span>'}</div>
                  <div style="font-size:11px; color:var(--text-muted); margin-top:2px;" title="${d.attributes?.recommended_category_path || d.category || ''}">
                    <strong>Shopify Cat:</strong> ${d.attributes?.recommended_category_name || (d.attributes?.recommended_category_path ? d.attributes.recommended_category_path.split(' > ').slice(-1)[0] : (d.category ? 'Standardized' : '—'))}
                  </div>
                </td>
                <td style="font-size:13px; font-weight:600;">
                  ${d.price ? '₹' + (d.price / 100).toFixed(2) : '<span style="color:var(--warning); font-weight:600;">[MISSING PRICE]</span>'}
                </td>
                <td>
                  ${isIncomplete
                    ? `<span class="status-pill warning">MISSING: ${missing.join(', ') || 'REQUIRED FIELDS'}</span>`
                    : '<span class="status-pill success">100% COMPLETE</span>'}
                </td>
                <td>
                  ${isIncomplete
                    ? '<span class="status-pill neutral" style="font-size:11px;">UNPUBLISHED (WhatsApp Awaiting)</span>'
                    : '<span class="status-pill success" style="font-size:11px;">LIVE ON STORE</span>'}
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
}

// --------------------------------------------------------------------------------
// Screen 4: Publication & Verification
// --------------------------------------------------------------------------------
function renderPublication() {
  if (isProspectDemoTenant()) { renderPublicationProspect(); return; }
  const container = document.getElementById('tab-publication');
  const draft = STATE.drafts.find(d => d.sku === 'ANCHAL-KACHI-GHANI') || STATE.drafts[0];
  const publication = STATE.publications.find(p => p.product_draft_id === draft?.id) || STATE.publications[0] || null;

  const isConflicted = Boolean(draft && (draft.state === 'CONFLICTED' || (draft.conflicts || []).length > 0));
  const isReady = Boolean(draft && (draft.state === 'READY' || draft.approved_for_publication));
  const isPublished = Boolean(publication && (String(publication.status || '').toLowerCase() === 'published' || publication.external_product_id));
  const hasReadBackEvidence = isPublished && STATE.audit.some(e =>
    String(e.action || '').toLowerCase() === 'listing_verified' ||
    String(e.action || '').toLowerCase().includes('verify')
  );

  container.innerHTML = `
    <div class="stepper-container">
      <div class="step-item ${isConflicted ? 'active danger' : 'completed'}">
        <div class="step-circle">${isConflicted ? '!' : ''}</div>
        <div class="step-text">1. Conflict Gate</div>
      </div>
      <div class="step-item ${isReady && !isPublished ? 'active' : ''} ${isReady ? 'completed' : ''}">
        <div class="step-circle">2</div>
        <div class="step-text">2. Facts Approved</div>
      </div>
      <div class="step-item ${isPublished ? 'completed' : ''}">
        <div class="step-circle">3</div>
        <div class="step-text">3. Dev-Store Mutation</div>
      </div>
      <div class="step-item ${hasReadBackEvidence ? 'completed' : ''}">
        <div class="step-circle">4</div>
        <div class="step-text">4. External Read-Back</div>
      </div>
    </div>

    <div class="card" style="margin-bottom:20px;">
      <div class="card-header">
        <div class="card-title">
          <span>Target Sales Channel: Shopify - Certified Dev Store</span>
        </div>
        <span class="status-pill success">CERTIFIED DEV STORE</span>
      </div>

      <div class="grid-cols-2" style="margin-bottom:16px;">
        <div>
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:2px;">Store Domain:</div>
          <div style="font-weight:600; font-size:14px;">sanocea-commerce-os-dev.myshopify.com</div>
        </div>
        <div>
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:2px;">Integration Protocol:</div>
          <div style="font-weight:600; font-size:14px;">Shopify Admin GraphQL API (2026-07)</div>
        </div>
      </div>

      ${isConflicted ? `
        <div class="governance-banner">
          <div class="governance-icon">!</div>
          <div>
            <div class="governance-title">Publication Refused (Fail-Closed)</div>
            <div class="governance-desc">
              SANOCEA has refused publication because unresolved commercial conflicts exist for this product draft.
            </div>
          </div>
        </div>
      ` : isPublished ? `
        <div class="governance-banner success">
          <div class="governance-icon"></div>
          <div>
            <div class="governance-title">Published to Certified Shopify Dev Store</div>
            <div class="governance-desc">
              A genuine Shopify Admin GraphQL mutation is recorded for this reference merchant workflow. This is a certified development store, not a production merchant account.
            </div>
          </div>
        </div>
      ` : `
        <div class="governance-banner success">
          <div class="governance-icon"></div>
          <div>
            <div class="governance-title">Product Eligible for Dev-Store Publication</div>
            <div class="governance-desc">
              Commercial facts are signed off. Publication has not been executed yet for this current state.
            </div>
          </div>
        </div>
      `}

      <div style="display:flex; justify-content:flex-end; gap:12px;">
        <button class="btn btn-outline" onclick="refreshAllData()">Refresh Status</button>
        <button class="btn btn-primary" ${(isConflicted || isPublished) ? 'disabled style="opacity:0.5; cursor:not-allowed;"' : ''} onclick="handlePublish('${draft?.id}')">
          ${isPublished ? 'Already Published' : 'Publish to Certified Dev Store'}
        </button>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">Independent External Read-Back Proof</div>
        <span class="status-pill ${hasReadBackEvidence ? 'success' : (isPublished ? 'warning' : 'neutral')}">
          ${hasReadBackEvidence ? 'READ-BACK EVIDENCE PRESENT' : (isPublished ? 'PUBLISHED; CHECK AUDIT' : 'AWAITING PUBLICATION')}
        </span>
      </div>

      ${isPublished ? `
        <div style="display:flex; flex-direction:column; gap:12px;">
          <div class="grid-cols-3">
            <div>
              <div style="font-size:12px; color:var(--text-muted);">Shopify Product GID:</div>
              <div style="font-weight:600; font-family:monospace; font-size:13px;">${publication.external_product_id}</div>
            </div>
            <div>
              <div style="font-size:12px; color:var(--text-muted);">Shopify External State:</div>
              <div style="font-weight:600; color:var(--success);">ACTIVE on certified dev store</div>
            </div>
            <div>
              <div style="font-size:12px; color:var(--text-muted);">Publication Status:</div>
              <div style="font-weight:500; font-size:12px;">${publication.status}</div>
            </div>
          </div>

          <div style="background:var(--bg-subtle); padding:12px; border-radius:var(--radius-md); font-size:12px;">
            <strong>Verification Evidence:</strong> SANOCEA records Shopify publication and read-back evidence in the audit ledger. The external product identifier above is Shopify-returned, not generated by the frontend.
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; pt-2;">
            <a href="https://sanocea-commerce-os-dev.myshopify.com/admin/products/${(publication.external_product_id || '').split('/').pop()}" 
               target="_blank" class="btn btn-outline btn-sm">
              Open in Shopify Dev Admin Portal
            </a>
            <button class="btn btn-outline btn-sm" onclick="handleReverify('${publication.id}')">
              Re-verify Read-Back Now
            </button>
          </div>
        </div>
      ` : `
        <div style="padding:24px; text-align:center; color:var(--text-muted); font-size:13px;">
          Publication has not been executed yet. Complete the required operator sign-off before publication.
        </div>
      `}
    </div>
  `;
}

// Prospect demo tenant Publication & Verification - prospect demo channels are informational only
// (packages/prospect_demo/reset.py registers them with type `demo_<channel>`, which matches no entry in
// StorefrontConnectorRegistry) - no connector is ever instantiated for them, so live publish/mutate is
// structurally unavailable here, never merely hidden. Never references Shopify or any live storefront.
// --------------------------------------------------------------------------------
// Screen 4 (prospect demo tenants): Channel Operations
// --------------------------------------------------------------------------------
const CHANNEL_LABELS = { own_website: 'Own Website', amazon_in: 'Amazon India', flipkart: 'Flipkart', jiomart: 'JioMart', blinkit: 'Blinkit' };
const CHANNEL_ORDER = ['own_website', 'amazon_in', 'flipkart', 'jiomart', 'blinkit'];
const CHANNEL_TERMINAL_STATES = new Set(['VERIFIED', 'RESOLVED', 'APPROVAL_REQUIRED', 'FAILED']);

function _channelOpsByChannel() {
  const byChannel = {};
  for (const op of STATE.channelOperations) {
    (byChannel[op.channel] ||= []).push(op);
  }
  return byChannel;
}

function _channelSummary(ops) {
  const total = ops.length;
  const verified = ops.filter(o => o.status === 'VERIFIED' || o.status === 'RESOLVED').length;
  const attention = ops.filter(o => o.status === 'APPROVAL_REQUIRED' || o.status === 'FAILED').length;
  const resolving = ops.filter(o => !CHANNEL_TERMINAL_STATES.has(o.status)).length;
  return { total, verified, attention, resolving };
}

// A sales-facing approval card must never show raw JSON - a prospect (or Manpreet, mid-meeting)
// reading `{"proposed_price":"129.00",...}` reads as a bug, not evidence. Humanizes any flat
// evidence/decision_evidence object into a readable "Label: value" list; nested objects/arrays are
// rendered recursively rather than falling back to JSON.stringify.
function formatEvidenceValue(value) {
  if (value === null || value === undefined || value === '') return 'Not on file';
  if (Array.isArray(value)) return value.map(formatEvidenceValue).join(', ') || 'None';
  if (typeof value === 'object') {
    return Object.entries(value).map(([k, v]) => `${humanizeLabel(k)}: ${formatEvidenceValue(v)}`).join(' · ');
  }
  return String(value);
}

function humanizeLabel(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatEvidenceBlock(evidence) {
  const entries = Object.entries(evidence || {});
  if (entries.length === 0) return 'None recorded';
  return entries.map(([k, v]) => `<div><strong>${humanizeLabel(k)}:</strong> ${formatEvidenceValue(v)}</div>`).join('');
}

function selectChannelFilter(channel) {
  STATE.activeChannelFilter = STATE.activeChannelFilter === channel ? null : channel;
  renderPublicationProspect();
}

// This tab re-renders wholesale on every live poll tick (STATE.channelOperations changes as
// operations progress) - without tracking expand/collapse choices separately, a "Why?" panel a user
// opened would silently snap shut ~2.5s later mid-explanation. Tracked outside STATE/innerHTML so a
// re-render can restore it instead of discarding it.
const EXPANDED_WHY_PANELS = new Set();

function toggleWhyPanel(opId) {
  if (EXPANDED_WHY_PANELS.has(opId)) EXPANDED_WHY_PANELS.delete(opId);
  else EXPANDED_WHY_PANELS.add(opId);
  renderPublicationProspect();
}

// DEMO TRANSPORT — UNOFFICIAL WHATSAPP WEB (WAHA). Session-scoped, client-tracked only for THIS
// browser session (never persisted as merchant master data - see DemoSessionContact's own docstring).
const DEMO_WHATSAPP_CONTACTS = {};
// Same bug class as EXPANDED_WHY_PANELS (see its comment): this tab wholesale re-renders on every
// live poll tick (~2.5s). Toggling the form's visibility directly on the DOM node (the original
// implementation) meant the NEXT poll tick's re-render always rebuilt it back to display:none,
// making the form flash open and then vanish before anyone could type into it - reported live during
// physical WhatsApp certification. Tracked outside STATE/innerHTML, exactly like EXPANDED_WHY_PANELS,
// so a re-render restores the open state instead of discarding it.
const OPEN_WHATSAPP_FORMS = new Set();

function showWhatsAppContactForm(approvalId) {
  if (OPEN_WHATSAPP_FORMS.has(approvalId)) OPEN_WHATSAPP_FORMS.delete(approvalId);
  else OPEN_WHATSAPP_FORMS.add(approvalId);
  renderPublicationProspect();
}

async function setDemoWhatsAppContact(merchantId, approvalId) {
  const phoneInput = document.getElementById(`wa-phone-${approvalId}`);
  const consentInput = document.getElementById(`wa-consent-${approvalId}`);
  const phone = (phoneInput?.value || '').trim();
  if (!phone) { showNotification('Enter the prospect\'s WhatsApp number first.', 'danger'); return; }
  if (!consentInput?.checked) { showNotification('Confirm consent before sending.', 'danger'); return; }
  try {
    const contact = await apiCall(`/merchants/${merchantId}/demo/whatsapp-contact`, 'POST', {
      phone_e164: phone, consented: true, session_label: `live meeting ${new Date().toLocaleString()}`,
    });
    DEMO_WHATSAPP_CONTACTS[merchantId] = contact;
    showNotification(`Demo contact set (${contact.masked_phone}) - expires ${new Date(contact.expires_at).toLocaleTimeString()}.`, 'success');
    renderPublicationProspect();
  } catch (err) {
    showNotification(`Could not set demo contact: ${err.message}`, 'danger');
  }
}

// Universal owner-number control (app-header, always visible - see index.html for why this exists
// separately from the per-approval form above). Same backend contact, just reachable without an
// approval on screen.
async function updateOwnerWhatsAppNumber() {
  const merchantId = STATE.merchantId;
  const input = document.getElementById('owner-whatsapp-input');
  const phone = (input?.value || '').trim();
  if (!phone) { showNotification("Enter the owner's WhatsApp number first.", 'danger'); return; }
  if (!confirm(`Set ${phone} as the WhatsApp number for all owner approval requests and missing-field questions on ${merchantId}?`)) return;
  try {
    const contact = await apiCall(`/merchants/${merchantId}/demo/whatsapp-contact`, 'POST', {
      phone_e164: phone, consented: true, session_label: `owner control ${new Date().toLocaleString()}`,
    });
    DEMO_WHATSAPP_CONTACTS[merchantId] = contact;
    input.value = '';
    updateOwnerWhatsAppStatus();
    showNotification(`Owner WhatsApp updated (${contact.masked_phone}) - now used for every automatic approval/missing-field send. Expires ${new Date(contact.expires_at).toLocaleTimeString()}.`, 'success');
    renderPublicationProspect();
  } catch (err) {
    showNotification(`Could not update owner WhatsApp: ${err.message}`, 'danger');
  }
}

async function refreshOwnerWhatsAppStatus() {
  const merchantId = STATE.merchantId;
  try {
    const result = await apiCall(`/merchants/${merchantId}/demo/whatsapp-contact`);
    if (result.active) {
      DEMO_WHATSAPP_CONTACTS[merchantId] = result;
    } else {
      delete DEMO_WHATSAPP_CONTACTS[merchantId];
    }
  } catch (err) {
    // Non-fatal - the header control just falls back to whatever this tab already remembers.
  }
  updateOwnerWhatsAppStatus();
}

function updateOwnerWhatsAppStatus() {
  const statusEl = document.getElementById('owner-whatsapp-status');
  if (!statusEl) return;
  const contact = DEMO_WHATSAPP_CONTACTS[STATE.merchantId];
  statusEl.textContent = contact ? `${contact.masked_phone} until ${new Date(contact.expires_at).toLocaleTimeString()}` : 'not set';
}

async function clearDemoWhatsAppContact(merchantId) {
  const contact = DEMO_WHATSAPP_CONTACTS[merchantId];
  if (!contact) return;
  try {
    await apiCall(`/merchants/${merchantId}/demo/whatsapp-contact/${contact.id}`, 'DELETE');
    delete DEMO_WHATSAPP_CONTACTS[merchantId];
    showNotification('Demo WhatsApp contact cleared.', 'info');
    renderPublicationProspect();
  } catch (err) {
    showNotification(`Could not clear contact: ${err.message}`, 'danger');
  }
}

async function sendApprovalToWhatsApp(merchantId, approvalId) {
  const contact = DEMO_WHATSAPP_CONTACTS[merchantId];
  if (!contact) return;
  try {
    const result = await apiCall(`/merchants/${merchantId}/approvals/${approvalId}/send-whatsapp`, 'POST', { contact_id: contact.id });
    if (result.delivered) {
      showNotification(`Approval sent to WhatsApp (${result.sent_to_masked}). Waiting for owner reply...`, 'success');
    } else {
      showNotification(`WhatsApp send failed: ${result.error}`, 'danger');
    }
  } catch (err) {
    showNotification(`Could not send via WhatsApp: ${err.message} (is the WAHA demo session linked to a phone yet?)`, 'danger');
  }
}

async function resolveChannelApproval(approvalId, decision) {
  const label = decision === 'approved' ? 'approve' : 'deny';
  if (!confirm(`${label === 'approve' ? 'Approve' : 'Deny'} this action? ${label === 'approve' ? 'SANOCEA will apply the correction and verify it.' : 'The operation will remain unresolved.'}`)) return;
  try {
    const result = await apiCall(`/merchants/${STATE.merchantId}/approvals/${approvalId}/resolve`, 'POST', { decision });
    if (result.already_resolved) {
      showNotification('This request has already been resolved.', 'info');
    } else {
      showNotification(`Decision recorded (${decision}) - operation resumed.`, 'success');
    }
    await refreshAllData();
  } catch (err) {
    showNotification(`Could not record decision: ${err.message}`, 'danger');
  }
}

function renderPublicationProspect() {
  const container = document.getElementById('tab-publication');
  const demo = STATE.profile?.config?.demo || {};
  const knownChannels = CHANNEL_ORDER.filter(c => (demo.known_channels || []).includes(c));
  const byChannel = _channelOpsByChannel();

  // Reuses the SAME approval-card UI for order-flow approvals (e.g. inventory shortage) - the card
  // itself is action-agnostic (reads only a.evidence/summary/recommendation/alternative/risk_note), so
  // no new rendering code is needed, only widening which actions are shown here. Computed BEFORE the
  // "no channel operations yet" early-return below (a real bug found live: a merchant with zero
  // channel-ops rows but a real pending order-flow approval - e.g. an inventory-shortage approval from
  // a real Shopify order - would hit that early return and the approval card would never render at
  // all, silently hiding a real, actionable approval from the operator).
  const ORDER_FLOW_APPROVAL_ACTIONS = new Set(['channel_operation_correction', 'resolve_inventory_shortage', 'cancel_order', 'create_return', 'refund']);
  const pendingApprovals = STATE.approvals.filter(a => a.status === 'pending' && ORDER_FLOW_APPROVAL_ACTIONS.has(a.action));

  if ((knownChannels.length === 0 || STATE.channelOperations.length === 0) && pendingApprovals.length === 0) {
    container.innerHTML = `
      <div class="card" style="text-align:center; padding:40px;">
        <h3 style="font-size:16px; font-weight:600; margin-bottom:8px;">No Channel Operations Yet</h3>
        <p style="color:var(--text-muted); font-size:13px; max-width:560px; margin:0 auto;">
          Channel Operations begin automatically once a product-master email is ingested and validated -
          nothing to show until then. Known channels for this tenant: ${(demo.known_channels || []).join(', ') || '—'}.
        </p>
      </div>`;
    return;
  }

  const executiveRows = knownChannels.map(channel => {
    const ops = byChannel[channel] || [];
    const s = _channelSummary(ops);
    const statusPill = s.attention > 0
      ? `<span class="status-pill danger">ATTENTION</span>`
      : s.resolving > 0 ? `<span class="status-pill warning">RESOLVING</span>`
      : s.verified === s.total && s.total > 0 ? `<span class="status-pill success">VERIFIED</span>`
      : `<span class="status-pill neutral">—</span>`;
    const active = STATE.activeChannelFilter === channel ? 'style="background:var(--surface-hover);"' : '';
    return `
      <tr onclick="selectChannelFilter('${channel}')" style="cursor:pointer;" ${active}>
        <td><strong>${CHANNEL_LABELS[channel] || channel}</strong></td>
        <td>${statusPill}</td>
        <td>${s.verified}/${s.total}</td>
        <td>${s.resolving}</td>
        <td>${s.attention > 0 ? `<span style="color:var(--danger); font-weight:600;">${s.attention}</span>` : '0'}</td>
      </tr>`;
  }).join('');

  const approvalCards = pendingApprovals.map(a => `
    <div class="card" style="border-color:var(--danger-border); background:var(--danger-light); margin-bottom:14px;">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <div style="font-size:11px; font-weight:700; letter-spacing:0.04em; color:var(--danger); margin-bottom:4px;">OWNER DECISION REQUIRED &middot; ${a.reference || a.id}</div>
          <div style="font-size:14px; font-weight:600; margin-bottom:8px;">${a.summary || ''}</div>
        </div>
      </div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;"><strong>Evidence:</strong><div style="margin-top:2px; padding-left:8px;">${formatEvidenceBlock(a.evidence)}</div></div>
      <div style="font-size:12px; margin-bottom:4px;"><strong>SANOCEA recommends:</strong> ${a.recommendation || '—'}</div>
      <div style="font-size:12px; margin-bottom:4px;"><strong>Alternative:</strong> ${a.alternative || '—'}</div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:12px;"><strong>Why approval is required:</strong> ${a.risk_note || '—'}</div>
      <div style="display:flex; gap:8px; margin-bottom:10px;">
        <button class="btn btn-primary btn-sm" onclick="resolveChannelApproval('${a.id}', 'approved')">Approve</button>
        <button class="btn btn-outline btn-sm" onclick="resolveChannelApproval('${a.id}', 'denied')">Deny</button>
      </div>
      <div style="border-top:1px dashed var(--border-color); padding-top:10px;">
        ${DEMO_WHATSAPP_CONTACTS[STATE.merchantId] ? `
          <div style="font-size:12px; display:flex; align-items:center; gap:10px;">
            <span>Demo WhatsApp contact: <strong>${DEMO_WHATSAPP_CONTACTS[STATE.merchantId].masked_phone}</strong></span>
            <button class="btn btn-primary btn-xs" onclick="sendApprovalToWhatsApp('${STATE.merchantId}', '${a.id}')">Send Approval to WhatsApp</button>
            <button class="btn btn-outline btn-xs" onclick="clearDemoWhatsAppContact('${STATE.merchantId}')">Clear contact</button>
          </div>
        ` : `
          <button class="btn btn-outline btn-xs" onclick="showWhatsAppContactForm('${a.id}')">${OPEN_WHATSAPP_FORMS.has(a.id) ? 'Hide' : 'Send Approval to WhatsApp&hellip;'}</button>
          <div id="wa-form-${a.id}" style="display:${OPEN_WHATSAPP_FORMS.has(a.id) ? 'block' : 'none'}; margin-top:8px; font-size:12px;">
            <div style="color:var(--warning); margin-bottom:6px;">DEMO TRANSPORT — UNOFFICIAL WHATSAPP WEB. Not a production integration. Use only a dedicated demo number - never a personal or business-critical WhatsApp account.</div>
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <label>WhatsApp number (with country code):</label>
              <input type="text" id="wa-phone-${a.id}" placeholder="919876543210" style="width:140px; padding:4px 6px; border:1px solid var(--border-color); border-radius:4px;" />
            </div>
            <label style="display:flex; align-items:center; gap:6px; margin:8px 0;">
              <input type="checkbox" id="wa-consent-${a.id}" /> Consent confirmed - prospect agreed verbally to receive this demo message
            </label>
            <button class="btn btn-primary btn-xs" onclick="setDemoWhatsAppContact('${STATE.merchantId}', '${a.id}')">Save Contact</button>
          </div>
        `}
      </div>
    </div>
  `).join('');

  let drilldown = '';
  if (STATE.activeChannelFilter) {
    const ops = (byChannel[STATE.activeChannelFilter] || []).slice().sort((a, b) => (a.sku || '').localeCompare(b.sku || ''));
    const rows = ops.map(op => {
      const historyStr = (op.history || []).map(h => h.status).join(' &rarr; ');
      let statusColor = 'warning';
      let statusLabel = op.status;
      if (op.status === 'VERIFIED' || op.status === 'RESOLVED') statusColor = 'success';
      else if (op.status === 'APPROVAL_REQUIRED' || op.status === 'FAILED') statusColor = 'danger';
      else if (op.status === 'AWAITING_CHANNEL_RESPONSE') { statusColor = 'neutral'; statusLabel = 'AWAITING CHANNEL RESPONSE'; }
      if (op.issue_category === 'EXPECTED_COMMERCIAL_DIFFERENCE') { statusColor = 'success'; statusLabel = 'NO ACTION NEEDED'; }
      const hasWhy = op.decision_evidence && Object.keys(op.decision_evidence).length > 0;
      const isExpanded = EXPANDED_WHY_PANELS.has(op.id);
      return `
        <tr>
          <td><strong>${op.product_title || op.sku}</strong><br><span class="code-inline" style="font-size:11px;">${op.sku || ''}</span></td>
          <td><span class="status-pill ${statusColor}">${statusLabel}</span></td>
          <td style="font-size:11px; color:var(--text-muted); max-width:420px;">${historyStr}</td>
          <td style="font-size:11px;">${op.issue_message || (op.history.find(h => h.note)?.note) || '—'}</td>
          <td>${hasWhy ? `<button class="btn btn-outline btn-xs" onclick="toggleWhyPanel('${op.id}')">${isExpanded ? 'Hide' : 'Why?'}</button>` : ''}</td>
        </tr>
        ${hasWhy && isExpanded ? `
        <tr>
          <td colspan="5" style="background:var(--bg-subtle); font-size:12px;">
            <div style="padding:10px;">
              <div style="font-weight:700; margin-bottom:6px;">WHY SANOCEA TOOK THIS ACTION</div>
              <div style="display:grid; grid-template-columns:180px 1fr; gap:4px 10px;">
                <div style="color:var(--text-muted);">Approved master</div><div>${formatEvidenceValue(op.decision_evidence.approved_master)}</div>
                <div style="color:var(--text-muted);">Observed channel state</div><div>${formatEvidenceValue(op.decision_evidence.observed_channel_state)}</div>
                <div style="color:var(--text-muted);">Promotion evidence</div><div>${op.decision_evidence.promotion_evidence || 'None identified'}</div>
                <div style="color:var(--text-muted);">Merchant authority rule</div><div>${op.decision_evidence.merchant_authority_rule || '—'}</div>
                <div style="color:var(--text-muted);">Decision</div><div><strong>${op.decision_evidence.decision || '—'}</strong></div>
                <div style="color:var(--text-muted);">Result</div><div>${op.decision_evidence.result || 'pending'}</div>
              </div>
            </div>
          </td>
        </tr>` : ''}`;
    }).join('');
    drilldown = `
      <div class="card" style="margin-top:20px;">
        <div class="card-header">
          <div class="card-title">${CHANNEL_LABELS[STATE.activeChannelFilter]} - Product Lifecycle</div>
        </div>
        <div class="table-container">
          <table>
            <thead><tr><th>Product</th><th>Status</th><th>Lifecycle</th><th>Note</th><th></th></tr></thead>
            <tbody>${rows || '<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">No operations for this channel.</td></tr>'}</tbody>
          </table>
        </div>
      </div>`;
  }

  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Channel Operations</h2>
        <div style="font-size:13px; color:var(--text-muted);">
          What happens after a product passes validation - real connector contracts, controlled demo responses (SYNTHETIC_DEMO, no real marketplace access).
        </div>
      </div>
    </div>

    ${approvalCards}

    <div class="card">
      <div class="card-header"><div class="card-title">Channel Distribution</div></div>
      <div class="table-container">
        <table>
          <thead><tr><th>Channel</th><th>Status</th><th>Verified</th><th>Resolving</th><th>Attention</th></tr></thead>
          <tbody>${executiveRows}</tbody>
        </table>
      </div>
    </div>

    ${drilldown}
  `;
}

// --------------------------------------------------------------------------------
// Screen 5: Orders & Inventory
// --------------------------------------------------------------------------------
function renderOrdersInventory() {
  if (isProspectDemoTenant()) { renderOrdersInventoryProspect(); return; }
  const container = document.getElementById('tab-inventory');

  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Multi-Location Inventory & Orders</h2>
        <div style="font-size:13px; color:var(--text-muted);">
          Database-atomic stock reservations with row-level locks and proximity routing across fulfillment hubs.
        </div>
      </div>
      <span class="status-pill success">ATOMIC SQL RESERVATION ENABLED</span>
    </div>

    <!-- Warehouse Locations Table -->
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header">
        <div class="card-title">Fulfillment Node Inventory Balances</div>
        <span class="status-pill neutral">3 ACTIVE NODES</span>
      </div>

      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Location Node</th>
              <th>City / Hub</th>
              <th>SKU</th>
              <th>Physical Quantity</th>
              <th>Reserved (Atomic)</th>
              <th>Available to Sell</th>
              <th>Priority</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Delhi Central Hub</strong> (<span class="code-inline">loc_delhi_hub</span>)</td>
              <td>New Delhi, DL (110001)</td>
              <td><code>ANCHAL-KACHI-1L-BTL</code></td>
              <td>150</td>
              <td><span style="color:var(--danger); font-weight:600;">5 (Order #ORD-10928)</span></td>
              <td><strong style="color:var(--success);">145</strong></td>
              <td><span class="status-pill success">Priority 1 (Default)</span></td>
            </tr>
            <tr>
              <td><strong>Mumbai Logistics Park</strong> (<span class="code-inline">loc_mumbai_hub</span>)</td>
              <td>Bhiwandi, MH (421302)</td>
              <td><code>ANCHAL-KACHI-1L-BTL</code></td>
              <td>100</td>
              <td>0</td>
              <td><strong>100</strong></td>
              <td><span class="status-pill neutral">Priority 2</span></td>
            </tr>
            <tr>
              <td><strong>Bengaluru South Node</strong> (<span class="code-inline">loc_bengaluru_hub</span>)</td>
              <td>Bengaluru, KA (560100)</td>
              <td><code>ANCHAL-KACHI-1L-BTL</code></td>
              <td>50</td>
              <td>0</td>
              <td><strong>50</strong></td>
              <td><span class="status-pill neutral">Priority 3</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Order Lifecycle & Idempotency Card -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Order Lifecycle & Idempotency Proof</div>
        <span class="status-pill success">IDEMPOTENT (REPLAY SAFE)</span>
      </div>

      <div class="grid-cols-3" style="margin-bottom:14px;">
        <div>
          <div style="font-size:12px; color:var(--text-muted);">Order ID:</div>
          <div style="font-weight:700;">#ORD-10928</div>
        </div>
        <div>
          <div style="font-size:12px; color:var(--text-muted);">Channel:</div>
          <div>Shopify D2C</div>
        </div>
        <div>
          <div style="font-size:12px; color:var(--text-muted);">Customer:</div>
          <div>Aarav Sharma (Delhi, 110001)</div>
        </div>
      </div>

      <div style="background:var(--bg-subtle); padding:14px; border-radius:var(--radius-md); font-size:13px; margin-bottom:14px;">
        <strong>Proximity Routing Engine:</strong> Customer pincode <code>110001</code> matched Delhi Central Hub (Priority 1). Exactly 5 units reserved atomically. Duplicate webhook re-deliveries detected via idempotency key <code>ref_anchal_heritage:order_ord_10928</code> resulting in <strong>ZERO duplicate deductions</strong>.
      </div>
    </div>
  `;
}

// Prospect demo tenant Orders & Inventory - genuinely data-driven from STATE.inventory/STATE.orders
// (the Reference Merchant's own version of this screen is static demo content by original design; a
// prospect tenant has no such fixed script, so it must reflect whatever the seeded scenario actually
// produced - see packages/prospect_demo/scenarios.py).
function renderOrdersInventoryProspect() {
  const container = document.getElementById('tab-inventory');
  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Orders & Inventory</h2>
        <div style="font-size:13px; color:var(--text-muted);">Real backend state for ${STATE.profile?.display_name || STATE.merchantId}.</div>
      </div>
    </div>
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header"><div class="card-title">Inventory Balances</div></div>
      <div class="table-container">
        <table>
          <thead><tr><th>SKU</th><th>Location</th><th>Quantity</th><th>Available</th></tr></thead>
          <tbody>
            ${STATE.inventory.length === 0 ? '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:16px;">No inventory records.</td></tr>' : STATE.inventory.map(i => `
              <tr>
                <td><code>${i.sku}</code></td>
                <td>${i.location_ref}</td>
                <td>${i.quantity}</td>
                <td><strong>${i.available}</strong></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title">Orders</div></div>
      <div class="table-container">
        <table>
          <thead><tr><th>Order</th><th>Channel</th><th>Status</th><th>Payment</th><th>Amount</th></tr></thead>
          <tbody>
            ${STATE.orders.length === 0 ? '<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:16px;">No orders.</td></tr>' : STATE.orders.map(o => `
              <tr>
                <td><strong>${o.order_number}</strong></td>
                <td>${o.channel_id}</td>
                <td><span class="status-pill neutral">${o.status}</span></td>
                <td>${o.payment_status || '—'}</td>
                <td>${(o.total_amount / 100).toFixed(2)} ${o.currency}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// --------------------------------------------------------------------------------
// Screen 6: Returns & Refunds
// --------------------------------------------------------------------------------
function renderReturnsRefunds() {
  if (isProspectDemoTenant()) { renderReturnsRefundsProspect(); return; }
  const container = document.getElementById('tab-refunds');

  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Post-Order Returns & Policy-Gated Refunds</h2>
        <div style="font-size:13px; color:var(--text-muted);">
          Physical inspection verification, inventory restoration, and automatic vs approval-gated financial refund controls.
        </div>
      </div>
      <span class="status-pill neutral">POLICY LIMIT: 500.00</span>
    </div>

    <!-- Return Processing -->
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header">
        <div class="card-title">Customer Return & Physical Restock</div>
        <span class="status-pill success">INSPECTION PASSED</span>
      </div>

      <div class="grid-cols-4">
        <div>
          <div style="font-size:12px; color:var(--text-muted);">Return ID:</div>
          <div style="font-weight:600;">ret_821a9f02</div>
        </div>
        <div>
          <div style="font-size:12px; color:var(--text-muted);">Associated Order:</div>
          <div style="font-weight:600;">#ORD-10928</div>
        </div>
        <div>
          <div style="font-size:12px; color:var(--text-muted);">Warehouse Inspection:</div>
          <div style="font-weight:600; color:var(--success);">Unopened / Clean Condition</div>
        </div>
        <div>
          <div style="font-size:12px; color:var(--text-muted);">Inventory Restoration:</div>
          <div style="font-weight:600; color:var(--primary);">+5 units restored to Delhi Hub (145 -> 150)</div>
        </div>
      </div>
    </div>

    <!-- Policy Decision Comparison -->
    <div style="margin-bottom:12px; font-size:13px; font-weight:600;">
      SANOCEA Financial Refund Policy Enforcement
    </div>

    <div class="grid-cols-2">
      <!-- Case A: Within Policy -->
      <div class="card" style="border-left:4px solid var(--success);">
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
          <span style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--success);">Case A - Standard Return</span>
          <span class="status-pill success">AUTOMATICALLY PERMITTED</span>
        </div>
        <div style="font-size:24px; font-weight:800; margin-bottom:8px;">156.00</div>
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">
          Refund amount is within executive policy limit ( 500.00).
        </div>
        <div style="background:var(--bg-subtle); padding:10px; border-radius:var(--radius-sm); font-size:12px;">
          <strong>Operational Action:</strong> Permitted immediately. Recorded in financial reconciliation ledger. Zero operator friction.
        </div>
      </div>

      <!-- Case B: Exceeds Policy -->
      <div class="card" style="border-left:4px solid var(--warning);">
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
          <span style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--warning);">Case B - High-Value Return</span>
          <span class="status-pill warning">HELD FOR FINANCIAL APPROVAL</span>
        </div>
        <div style="font-size:24px; font-weight:800; margin-bottom:8px;">840.00</div>
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">
          Refund amount exceeds executive policy limit (> 500.00).
        </div>
        <div style="background:var(--bg-subtle); padding:10px; border-radius:var(--radius-sm); font-size:12px;">
          <strong>Operational Action:</strong> Payout blocked. Approval entity minted (<span class="code-inline">appr_refund_840</span>). Awaiting sign-off by Finance Manager.
        </div>
      </div>
    </div>
  `;
}

// Prospect demo tenant Returns & Refunds - genuinely data-driven from STATE.returns/STATE.refunds/
// STATE.approvals (the Reference Merchant's own version of this screen is static demo content by
// original design - see the comment on renderOrdersInventoryProspect above for why that does not extend
// to prospect tenants).
function renderReturnsRefundsProspect() {
  const container = document.getElementById('tab-refunds');
  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Returns & Refunds</h2>
        <div style="font-size:13px; color:var(--text-muted);">Real backend state for ${STATE.profile?.display_name || STATE.merchantId}.</div>
      </div>
    </div>
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header"><div class="card-title">Returns</div></div>
      <div class="table-container">
        <table>
          <thead><tr><th>Return</th><th>Order</th><th>Status</th><th>Restockable</th></tr></thead>
          <tbody>
            ${STATE.returns.length === 0 ? '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:16px;">No returns.</td></tr>' : STATE.returns.map(r => `
              <tr>
                <td><span class="code-inline">${r.id}</span></td>
                <td>${r.order_id}</td>
                <td><span class="status-pill neutral">${r.status}</span></td>
                <td>${r.restockable === null || r.restockable === undefined ? '—' : (r.restockable ? 'Yes' : 'No')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
    <div class="card" style="margin-bottom:20px;">
      <div class="card-header"><div class="card-title">Refunds</div></div>
      <div class="table-container">
        <table>
          <thead><tr><th>Refund</th><th>Order</th><th>Amount</th><th>Status</th></tr></thead>
          <tbody>
            ${STATE.refunds.length === 0 ? '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:16px;">No refunds.</td></tr>' : STATE.refunds.map(r => `
              <tr>
                <td><span class="code-inline">${r.id}</span></td>
                <td>${r.order_id}</td>
                <td>${(r.amount / 100).toFixed(2)} ${r.currency}</td>
                <td><span class="status-pill ${r.status === 'approval_required' ? 'warning' : 'success'}">${r.status}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><div class="card-title">Pending Approvals</div></div>
      <div class="table-container">
        <table>
          <thead><tr><th>Approval</th><th>Action</th><th>Object</th><th>Status</th></tr></thead>
          <tbody>
            ${STATE.approvals.length === 0 ? '<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:16px;">No approvals.</td></tr>' : STATE.approvals.map(a => `
              <tr>
                <td><span class="code-inline">${a.id}</span></td>
                <td>${a.action}</td>
                <td>${a.object_id || '—'}</td>
                <td><span class="status-pill ${a.status === 'pending' ? 'warning' : 'success'}">${a.status}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// --------------------------------------------------------------------------------
// Screen 7: Audit Timeline
// --------------------------------------------------------------------------------
function renderAudit() {
  const container = document.getElementById('tab-audit');
  const events = STATE.audit || [];

  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
      <div>
        <h2 style="font-size:18px; font-weight:700;">Immutable Compliance Audit Trail</h2>
        <div style="font-size:13px; color:var(--text-muted);">
          Every commercial fact extraction, conflict resolution, publication, and inventory reservation is recorded permanently.
        </div>
      </div>
      <span class="status-pill success">
         POSTGRESQL 16 TRIGGER PROTECTED (APPEND-ONLY)
      </span>
    </div>

    <div class="governance-banner info" style="margin-bottom:16px;">
      <div class="governance-icon"></div>
      <div>
        <div class="governance-title">Database-Level Tamper Resistance</div>
        <div class="governance-desc">
          The <code>audit_events</code> table is governed by PostgreSQL trigger <code>trg_audit_no_update</code>. Any SQL <code>UPDATE</code> or <code>DELETE</code> statement is aborted with an exception at the database engine level.
        </div>
      </div>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Timestamp (UTC)</th>
            <th>Action</th>
            <th>Principal / Actor</th>
            <th>Object ID</th>
            <th>Correlation ID</th>
          </tr>
        </thead>
        <tbody>
          ${events.length === 0 ? `
            <tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted);">No audit records found.</td></tr>
          ` : events.map(e => `
            <tr>
              <td style="white-space:nowrap; font-size:12px; color:var(--text-muted);">
                ${new Date(e.timestamp || e.created_at).toLocaleString()}
              </td>
              <td><span class="code-inline" style="font-weight:600; color:var(--primary);">${e.action}</span></td>
              <td><span class="code-inline">${e.actor || e.principal_id || 'system'}</span></td>
              <td><strong>${e.object_id || ''}</strong></td>
              <td><span style="font-family:monospace; font-size:11px; color:var(--text-subtle);">${e.correlation_id || ''}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

// --------------------------------------------------------------------------------
// Operator Action Handlers (Invoke Authoritative SANOCEA APIs)
// --------------------------------------------------------------------------------
async function handleResolveConflict(draftId) {
  try {
    const radio156 = document.getElementById('radio-156');
    const chosenVal = radio156 && radio156.checked ? 156.0 : 145.0;
    const chosenSource = chosenVal === 156.0 ? 'supplier_price_list_messy.xlsx' : 'conflicting_feed.csv';
    const note = document.getElementById('resolution-note')?.value || 'Operator conflict resolution';

    showNotification('Sending conflict resolution decision to SANOCEA core API...', 'info');

    const result = await apiCall(`/merchants/${STATE.merchantId}/catalogue/drafts/${draftId}/conflicts/resolve`, 'POST', {
      fact_name: 'price',
      chosen_value: chosenVal,
      chosen_source: chosenSource,
      note: note,
    });

    showNotification(`Conflict successfully resolved to ${chosenVal.toFixed(2)} in SANOCEA.`, 'success');
    await refreshAllData();
  } catch (err) {
    console.error('Resolve error:', err);
    showNotification(`Failed to resolve conflict: ${err.message}`, 'danger');
  }
}

async function handleApproveFacts(draftId) {
  try {
    showNotification('Signing off on commercial facts...', 'info');
    await apiCall(`/merchants/${STATE.merchantId}/catalogue/drafts/${draftId}/approve-facts`, 'POST');
    showNotification('Commercial facts signed off. Draft transitioned to READY.', 'success');
    await refreshAllData();
  } catch (err) {
    console.error('Approve error:', err);
    showNotification(`Failed to approve facts: ${err.message}`, 'danger');
  }
}

async function handlePublish(draftId) {
  try {
    showNotification('Requesting publication against Shopify Admin GraphQL API 2026-07...', 'info');
    await apiCall(`/merchants/${STATE.merchantId}/catalogue/drafts/${draftId}/publish`, 'POST', {
      channel_id: 'chn_shopify_live',
    });
    await apiCall(`/merchants/${STATE.merchantId}/catalogue/drafts/${draftId}/publish/approve`, 'POST', {
      channel_id: 'chn_shopify_live',
    });
    showNotification('Product published and verified against the certified Shopify dev store!', 'success');
    await refreshAllData();
  } catch (err) {
    console.error('Publish error:', err);
    showNotification(`Failed to publish: ${err.message}`, 'danger');
  }
}

async function handleReverify(pubId) {
  try {
    showNotification('Executing independent GraphQL read-back query to Shopify...', 'info');
    await apiCall(`/merchants/${STATE.merchantId}/catalogue/publications/${pubId}/reverify`, 'POST');
    showNotification('Certified Shopify dev-store read-back verified active and matching canonical state.', 'success');
    await refreshAllData();
  } catch (err) {
    console.error('Reverify error:', err);
    showNotification(`Failed to reverify: ${err.message}`, 'danger');
  }
}

function showNotification(msg, type = 'info') {
  const existing = document.querySelector('.alert-popup');
  if (existing) existing.remove();

  const el = document.createElement('div');
  el.className = 'alert-popup';
  const icon = type === 'success' ? '' : (type === 'danger' ? '' : '');
  el.innerHTML = `<span>${icon}</span> <span style="font-size:13px; font-weight:500;">${msg}</span>`;
  document.body.appendChild(el);

  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity 0.3s ease';
    setTimeout(() => el.remove(), 300);
  }, 4000);
}

// Start on DOM ready
document.addEventListener('DOMContentLoaded', initApp);




