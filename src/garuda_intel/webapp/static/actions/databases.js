/**
 * Database management UI – create, switch, merge, delete, global search.
 *
 * Works with the /api/databases/* endpoints.
 */

import { fetchWithAPIKey } from '../api.js';

// ---------------------------------------------------------------
// helpers
// ---------------------------------------------------------------

function el(id) { return document.getElementById(id); }

function badge(text, color) {
  return `<span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${color}">${text}</span>`;
}

// ---------------------------------------------------------------
// state
// ---------------------------------------------------------------

let _databases = [];

// ---------------------------------------------------------------
// load & render
// ---------------------------------------------------------------

async function loadDatabases() {
  try {
    const res = await fetchWithAPIKey('/api/databases/');
    const data = await res.json();
    _databases = data.databases || [];
    renderList();
    populateMergeSelects();
    renderActiveBanner();
  } catch (err) {
    console.error('loadDatabases failed', err);
  }
}

function renderActiveBanner() {
  const active = _databases.find(d => d.is_active);
  if (!active) return;
  const nameEl = el('db-active-name');
  const descEl = el('db-active-desc');
  if (nameEl) nameEl.textContent = active.name;
  if (descEl) descEl.textContent = active.description || '';
  // Update header indicator
  const headerIndicator = el('header-db-name');
  if (headerIndicator) headerIndicator.textContent = active.name;
}

function renderList() {
  const container = el('db-list');
  if (!container) return;
  if (!_databases.length) { container.innerHTML = '<p class="text-slate-400 text-xs">No databases registered.</p>'; return; }

  container.innerHTML = _databases.map(db => {
    const active = db.is_active;
    const isDefault = db.name === 'default';
    const activeBadge = active ? badge('ACTIVE', 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300') : '';
    const defaultBadge = isDefault ? badge('DEFAULT', 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400') : '';
    const switchBtn = active ? '' : `<button data-db-switch="${db.name}" class="text-[11px] px-2 py-1 rounded bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-800 transition font-semibold">Switch</button>`;
    const deleteBtn = (isDefault || active) ? '' : `<button data-db-delete="${db.name}" class="text-[11px] px-2 py-1 rounded bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-800 transition font-semibold">Delete</button>`;

    return `
      <div class="flex items-center justify-between p-3 rounded-lg border ${active ? 'border-brand-300 dark:border-brand-700 bg-brand-50/50 dark:bg-brand-950/30' : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900'}">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-semibold text-slate-800 dark:text-slate-200">${db.name}</span>
          ${activeBadge}${defaultBadge}
          <span class="text-[10px] text-slate-400">${db.description || ''}</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="text-[10px] text-slate-400 hidden sm:inline">${db.qdrant_collection}</span>
          ${switchBtn}${deleteBtn}
        </div>
      </div>`;
  }).join('');

  // Bind switch / delete buttons
  container.querySelectorAll('[data-db-switch]').forEach(btn => {
    btn.onclick = () => switchDatabase(btn.dataset.dbSwitch);
  });
  container.querySelectorAll('[data-db-delete]').forEach(btn => {
    btn.onclick = () => deleteDatabase(btn.dataset.dbDelete);
  });
}

function populateMergeSelects() {
  const src = el('db-merge-source');
  const tgt = el('db-merge-target');
  if (!src || !tgt) return;
  const opts = _databases.map(d => `<option value="${d.name}">${d.name}</option>`).join('');
  src.innerHTML = opts;
  tgt.innerHTML = opts;
}

// ---------------------------------------------------------------
// actions
// ---------------------------------------------------------------

async function createDatabase() {
  const name = (el('db-new-name')?.value || '').trim();
  if (!name) { alert('Database name is required'); return; }
  const description = (el('db-new-desc')?.value || '').trim();
  const setActive = el('db-new-activate')?.checked || false;
  try {
    await fetchWithAPIKey('/api/databases/create', {
      method: 'POST',
      body: JSON.stringify({ name, description, set_active: setActive }),
    });
    if (el('db-new-name')) el('db-new-name').value = '';
    if (el('db-new-desc')) el('db-new-desc').value = '';
    loadDatabases();
  } catch (err) {
    alert('Create failed: ' + err.message);
  }
}

async function switchDatabase(name) {
  try {
    await fetchWithAPIKey('/api/databases/switch', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
    loadDatabases();
  } catch (err) {
    alert('Switch failed: ' + err.message);
  }
}

async function deleteDatabase(name) {
  if (!confirm(`Delete database "${name}"? This also deletes the file and vector collection.`)) return;
  try {
    await fetchWithAPIKey(`/api/databases/${encodeURIComponent(name)}?delete_files=true`, {
      method: 'DELETE',
    });
    loadDatabases();
  } catch (err) {
    alert('Delete failed: ' + err.message);
  }
}

async function mergeDatabases() {
  const source = el('db-merge-source')?.value;
  const target = el('db-merge-target')?.value;
  if (!source || !target) return;
  if (source === target) { alert('Source and target must differ'); return; }
  if (!confirm(`Merge "${source}" → "${target}"? This copies all data from source into target.`)) return;
  const statusEl = el('db-merge-status');
  if (statusEl) { statusEl.textContent = 'Merging… this may take a while.'; statusEl.classList.remove('hidden'); }
  try {
    const res = await fetchWithAPIKey('/api/databases/merge', {
      method: 'POST',
      body: JSON.stringify({ source, target }),
    });
    const data = await res.json();
    if (statusEl) {
      const s = data.stats || {};
      statusEl.textContent = `Merge complete – ${JSON.stringify(s)}`;
    }
    loadDatabases();
  } catch (err) {
    if (statusEl) statusEl.textContent = 'Merge failed: ' + err.message;
  }
}

async function globalSearch() {
  const q = (el('db-global-query')?.value || '').trim();
  if (!q) return;
  const container = el('db-global-results');
  if (!container) return;
  container.classList.remove('hidden');
  container.innerHTML = '<p class="text-xs text-slate-400">Searching…</p>';
  try {
    const res = await fetchWithAPIKey(`/api/databases/search?q=${encodeURIComponent(q)}&limit=10`);
    const data = await res.json();
    const results = data.results || {};
    const dbNames = Object.keys(results);
    if (!dbNames.length) { container.innerHTML = '<p class="text-xs text-slate-400">No results found.</p>'; return; }

    let html = '';
    for (const dbName of dbNames) {
      html += `<div class="font-semibold text-xs text-brand-600 dark:text-brand-400 mt-2">📂 ${dbName}</div>`;
      for (const hit of results[dbName]) {
        if (hit.type === 'entity') {
          html += `<div class="ml-3 p-2 rounded border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-xs">
            <span class="font-bold">${hit.name}</span>
            <span class="text-slate-400 ml-1">${hit.kind || ''}</span>
          </div>`;
        } else {
          html += `<div class="ml-3 p-2 rounded border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-xs">
            <span class="font-bold">${hit.entity_name || '?'}</span>
            <span class="text-slate-400 ml-1">${hit.entity_type || ''}</span>
            <span class="text-emerald-500 ml-1">conf ${(hit.confidence || 0).toFixed(2)}</span>
          </div>`;
        }
      }
    }
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<p class="text-xs text-red-500">${err.message}</p>`;
  }
}

// ---------------------------------------------------------------
// init
// ---------------------------------------------------------------

export function initDatabases() {
  const createBtn = el('db-create-btn');
  if (createBtn) createBtn.onclick = createDatabase;

  const mergeBtn = el('db-merge-btn');
  if (mergeBtn) mergeBtn.onclick = mergeDatabases;

  const searchBtn = el('db-global-search-btn');
  if (searchBtn) searchBtn.onclick = globalSearch;

  const refreshBtn = el('db-refresh');
  if (refreshBtn) refreshBtn.onclick = loadDatabases;

  const searchInput = el('db-global-query');
  if (searchInput) searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') globalSearch(); });

  loadDatabases();
}
