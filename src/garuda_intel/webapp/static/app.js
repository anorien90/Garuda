const els = {
  // --- Settings & Status ---
  baseUrl: document.getElementById('base-url'),
  apiKey: document.getElementById('api-key'),
  dbUrl: document.getElementById('db-url'),
  qdrantUrl: document.getElementById('qdrant-url'),
  qdrantCollection: document.getElementById('qdrant-collection'),
  embeddingModel: document.getElementById('embedding-model'),
  ollamaUrl: document.getElementById('ollama-url'),
  ollamaModel: document.getElementById('ollama-model'),
  saveBtn: document.getElementById('save-settings'),
  saveStatus: document.getElementById('save-status'),
  statusBtn: document.getElementById('refresh-status'),
  statusCards: document.getElementById('status-cards'),
  statusBadges: {
    api: document.getElementById('status-api'),
    db: document.getElementById('status-db'),
    vector: document.getElementById('status-vector'),
    llm: document.getElementById('status-llm'),
  },

  // --- Forms & Results ---
  searchForm: document.getElementById('search-form'),
  results: document.getElementById('results'),
  
  semanticForm: document.getElementById('semantic-form'),
  semanticResults: document.getElementById('semantic-results'),
  
  chatForm: document.getElementById('chat-form'),
  chatAnswer: document.getElementById('chat-answer'),
  chatToggle: document.getElementById('chat-toggle'),
  chatContainer: document.getElementById('chat-container'),
  
  pagesBtn: document.getElementById('load-pages'),
  pagesLimit: document.getElementById('pages-limit'),
  pagesList: document.getElementById('pages'),
  pageDetail: document.getElementById('page-detail'),
  pageModal: document.getElementById('page-modal'),
  pageModalContent: document.getElementById('page-modal-content'),
  pageModalClose: document.getElementById('page-modal-close'),
  
  // --- Recorder & Crawl ---
  recorderSearchForm: document.getElementById('recorder-search-form'),
  recorderResults: document.getElementById('recorder-results'),
  recorderHealth: document.getElementById('recorder-health'),
  recorderHealthRefresh: document.getElementById('recorder-health-refresh'),
  recorderMarkForm: document.getElementById('recorder-mark-form'),
  recorderMarkStatus: document.getElementById('recorder-mark-status'),
  
  crawlForm: document.getElementById('crawl-form'),
  crawlOutputPanel: document.getElementById('crawl-output-panel'),

  // --- Navigation & Theme ---
  themeToggle: document.getElementById('theme-toggle'),
  themeToggleLabel: document.getElementById('theme-toggle-label'),
  themeToggleIcon: document.getElementById('theme-toggle-icon'),
  tabButtons: document.querySelectorAll('[data-tab-btn]'),
  tabPanels: document.querySelectorAll('[data-tab-panel]'),
};

/* =========================================
   Helpers
   ========================================= */

const DEFAULT_BASE_URL = 'http://localhost:8080';

const getEl = (id) => document.getElementById(id);
const val = (id) => {
  const el = getEl(id);
  return el ? el.value : '';
};

function getBaseUrl() {
  const fromInput = els.baseUrl && els.baseUrl.value ? els.baseUrl.value : null;
  const fromStorage = localStorage.getItem('garuda_base_url');
  return (fromInput || fromStorage || DEFAULT_BASE_URL).trim().replace(/\/+$/, '');
}

function getApiKey() {
  const fromInput = els.apiKey && els.apiKey.value ? els.apiKey.value : null;
  const fromStorage = localStorage.getItem('garuda_api_key');
  return (fromInput || fromStorage || '').trim();
}

/* =========================================
   CORE: Fetch & Settings
   ========================================= */

function loadSettings() {
  const base = localStorage.getItem('garuda_base_url') || DEFAULT_BASE_URL;
  const key = localStorage.getItem('garuda_api_key') || '';
  if (els.baseUrl) els.baseUrl.value = base;
  if (els.apiKey) els.apiKey.value = key;

  if (els.dbUrl) els.dbUrl.value = localStorage.getItem('garuda_db_url') || '';
  if (els.qdrantUrl) els.qdrantUrl.value = localStorage.getItem('garuda_qdrant_url') || '';
  if (els.qdrantCollection) els.qdrantCollection.value = localStorage.getItem('garuda_qdrant_collection') || '';
  if (els.embeddingModel) els.embeddingModel.value = localStorage.getItem('garuda_embedding_model') || '';
  if (els.ollamaUrl) els.ollamaUrl.value = localStorage.getItem('garuda_ollama_url') || '';
  if (els.ollamaModel) els.ollamaModel.value = localStorage.getItem('garuda_ollama_model') || '';
}

function saveSettings() {
  const base = getBaseUrl();
  const key = getApiKey();
  localStorage.setItem('garuda_base_url', base);
  localStorage.setItem('garuda_api_key', key);

  if (els.baseUrl) els.baseUrl.value = base;
  if (els.apiKey) els.apiKey.value = key;

  if (els.dbUrl) localStorage.setItem('garuda_db_url', (els.dbUrl.value || '').trim());
  if (els.qdrantUrl) localStorage.setItem('garuda_qdrant_url', (els.qdrantUrl.value || '').trim());
  if (els.qdrantCollection) localStorage.setItem('garuda_qdrant_collection', (els.qdrantCollection.value || '').trim());
  if (els.embeddingModel) localStorage.setItem('garuda_embedding_model', (els.embeddingModel.value || '').trim());
  if (els.ollamaUrl) localStorage.setItem('garuda_ollama_url', (els.ollamaUrl.value || '').trim());
  if (els.ollamaModel) localStorage.setItem('garuda_ollama_model', (els.ollamaModel.value || '').trim());

  if (els.saveStatus) {
    els.saveStatus.textContent = 'Saved';
    setTimeout(() => (els.saveStatus.textContent = ''), 1500);
  }
  refreshStatus(); // Refresh connection immediately on save
}

async function fetchWithAuth(path, opts = {}) {
  const base = getBaseUrl();
  const endpoint = path.startsWith('/') ? path : `/${path}`;
  const url = base + endpoint;

  const headers = { ...(opts.headers || {}) };
  const key = getApiKey();
  if (key) headers['X-API-Key'] = key;

  try {
    const res = await fetch(url, { ...opts, headers });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`API Error ${res.status}: ${text}`);
    }
    return res;
  } catch (err) {
    console.error("Fetch failed:", err);
    throw new Error(`Connection failed to ${url}. Check if backend is running on port 8080.`);
  }
}

/* =========================================
   UI: Theme & Tabs
   ========================================= */

function applyTheme(mode) {
  const root = document.documentElement;
  const next = mode === 'dark' ? 'dark' : 'light';
  root.classList.toggle('dark', next === 'dark');
  root.dataset.theme = next;
  localStorage.setItem('garuda_theme', next);
  if (els.themeToggleLabel) els.themeToggleLabel.textContent = next === 'dark' ? 'Dark' : 'Light';
  if (els.themeToggleIcon) els.themeToggleIcon.textContent = next === 'dark' ? '🌙' : '🌞';
}

function initTheme() {
  const saved = localStorage.getItem('garuda_theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (prefersDark ? 'dark' : 'light'));
}

function setActiveTab(name) {
  const panelExists = !!document.querySelector(`[data-tab-panel="${name}"]`);
  const safeName = panelExists ? name : 'overview';

  els.tabButtons.forEach((btn) => {
    const isActive = btn.dataset.tabBtn === safeName;
    if(isActive) {
        btn.classList.add('active', 'bg-brand-600', 'text-white', 'shadow-sm', 'border-transparent');
        btn.classList.remove('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-slate-100', 'border-slate-200', 'dark:border-slate-700');
    } else {
        btn.classList.remove('active', 'bg-brand-600', 'text-white', 'shadow-sm', 'border-transparent');
        btn.classList.add('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-slate-100', 'border-slate-200', 'dark:border-slate-700');
    }
  });
  els.tabPanels.forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.tabPanel !== safeName);
    panel.setAttribute('aria-hidden', panel.dataset.tabPanel !== safeName);
  });
  localStorage.setItem('garuda_active_tab', safeName);
}

function initTabs() {
  const saved = localStorage.getItem('garuda_active_tab') || 'overview';
  setActiveTab(saved);
  els.tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => setActiveTab(btn.dataset.tabBtn));
  });
}

/* =========================================
   RENDERERS
   ========================================= */

function pill(text) {
  return `<span class="inline-flex items-center rounded-full bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-100 px-2 py-0.5 text-xs font-medium">${text}</span>`;
}
function chips(arr = []) {
  return arr.filter(Boolean).map((t) => pill(t)).join(' ');
}

function setStatusBadge(el, ok) {
  if (!el) return;
  const okCls = ['bg-emerald-500'];
  const badCls = ['bg-rose-500'];
  el.classList.remove(...okCls, ...badCls);
  el.classList.add(ok ? 'bg-emerald-500' : 'bg-rose-500');
}

// 1. Status Bar Renderer
function renderStatus(data) {
  if (els.statusCards) els.statusCards.innerHTML = '';
  if (!data || typeof data !== 'object') {
    if (els.statusCards) els.statusCards.innerHTML = '<div class="p-4 text-sm text-rose-500">Invalid status data received.</div>';
    return;
  }
  
  // Update compact header badges
  setStatusBadge(els.statusBadges.api, true);
  setStatusBadge(els.statusBadges.db, !!data.db_ok);
  setStatusBadge(els.statusBadges.vector, !!data.qdrant_ok);
  setStatusBadge(els.statusBadges.llm, !!data.embedding_loaded);

  if (!els.statusCards) return;

  const items = [
      { label: 'Database', status: data.db_ok, info: '' },
      { label: 'Vector Store', status: data.qdrant_ok, info: data.qdrant_url || 'Not configured' },
      { label: 'Embedding', status: data.embedding_loaded, info: data.model || 'No model' },
      { label: 'Ollama', status: !!data.ollama_url, info: data.ollama_url || 'Not configured' }
  ];

  items.forEach(item => {
      const div = document.createElement('div');
      div.className = `p-3 rounded-lg border ${item.status ? 'border-emerald-200 bg-emerald-50 dark:bg-emerald-900/20' : 'border-rose-200 bg-rose-50 dark:bg-rose-900/20'}`;
      div.innerHTML = `
        <div class="flex items-center gap-2">
            <div class="h-2 w-2 rounded-full ${item.status ? 'bg-emerald-500' : 'bg-rose-500'}"></div>
            <span class="text-xs font-bold uppercase text-slate-700 dark:text-slate-200">${item.label}</span>
        </div>
        <div class="text-[10px] mt-1 text-slate-500 dark:text-slate-400 truncate">${item.info}</div>
      `;
      els.statusCards.appendChild(div);
  });
}

// 2. Intel Renderer
function renderIntel(results, target) {
  target.innerHTML = '';
  const list = Array.isArray(results) ? results : [results];
  
  if (!list.length) {
    target.innerHTML = '<div class="p-4 text-sm text-slate-500">No results found.</div>';
    return;
  }
  list.forEach((r) => {
    const card = document.createElement('article');
    card.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
    
    const data = r.data || {};
    const info = data.basic_info || {};
    const metrics = (data.metrics || []).slice(0,3).map(m => `${m.type}: ${m.value}`).join(' • ');

    card.innerHTML = `
      <div class="flex justify-between items-start">
        <div>
            <div class="text-xs text-slate-500 uppercase font-bold">${r.entity_type || 'Entity'}</div>
            <h4 class="text-lg font-semibold text-slate-900 dark:text-white">${r.entity || info.official_name || '(unknown)'}</h4>
        </div>
        <span class="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">Conf: ${r.confidence ?? 0}</span>
      </div>
      
      ${info.description ? `<p class="text-sm text-slate-700 dark:text-slate-300">${info.description}</p>` : ''}
      ${metrics ? `<div class="text-xs text-slate-500 mt-2">${metrics}</div>` : ''}
      
      <details class="text-xs text-slate-400 cursor-pointer"><summary>Raw Data</summary>
        <pre class="mt-2 bg-slate-100 dark:bg-slate-800 p-2 rounded overflow-auto">${JSON.stringify(r, null, 2)}</pre>
      </details>
    `;
    target.appendChild(card);
  });
}

// 3. Semantic Search Renderer
function renderSemantic(data, target) {
  target.innerHTML = '';
  const hits = (data && data.semantic) ? data.semantic : [];
  
  if (!hits.length) {
    target.innerHTML = '<div class="p-4 text-sm text-slate-500">No semantic matches found.</div>';
    return;
  }
  
  hits.forEach((h) => {
    const card = document.createElement('div');
    card.className = 'p-3 border-b border-slate-100 dark:border-slate-800 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-800/50';
    card.innerHTML = `
        <div class="flex justify-between text-xs mb-1">
            <a href="${h.url}" target="_blank" class="text-brand-600 hover:underline truncate w-3/4">${h.url}</a>
            <span class="text-slate-400 font-mono">${h.score ? h.score.toFixed(3) : '0.00'}</span>
        </div>
        <p class="text-sm text-slate-700 dark:text-slate-300 line-clamp-2">"${h.text || h.snippet || 'No text content'}"</p>
        <div class="mt-1 flex gap-2">
            ${h.entity ? `<span class="text-[10px] bg-slate-100 dark:bg-slate-800 px-1 rounded text-slate-500">${h.entity}</span>` : ''}
            ${h.page_type ? `<span class="text-[10px] bg-slate-100 dark:bg-slate-800 px-1 rounded text-slate-500">${h.page_type}</span>` : ''}
        </div>
    `;
    target.appendChild(card);
  });
}

// 4. Pages Renderer
function renderPages(pages) {
  els.pagesList.innerHTML = '';
  if (!pages || !Array.isArray(pages) || !pages.length) {
    els.pagesList.innerHTML = '<div class="p-4 text-sm text-slate-500">No pages indexed.</div>';
    return;
  }
  
  pages.forEach((p) => {
    const card = document.createElement('article');
    card.className = 'p-3 border rounded-lg border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 hover:border-brand-300 transition cursor-pointer';
    
    card.innerHTML = `
      <div class="flex justify-between items-start">
        <div class="w-full">
            <div class="flex justify-between w-full">
                <h5 class="text-sm font-semibold text-slate-900 dark:text-white truncate w-3/4">${p.url}</h5>
                <span class="text-[10px] text-slate-400">${p.score ?? 0}</span>
            </div>
            <div class="flex gap-2 mt-1 text-xs text-slate-500">
                <span>${p.entity_type || 'Unknown Entity'}</span>
                <span>•</span>
                <span>${p.page_type || 'General'}</span>
                ${p.text_length ? `<span>• ${Math.round(p.text_length/1024)} KB</span>` : ''}
            </div>
        </div>
      </div>
    `;
    card.onclick = () => loadPageDetail(p.url);
    els.pagesList.appendChild(card);
  });
}

// 5. Chat Renderer
function renderChat(payload) {
  els.chatAnswer.innerHTML = '';
  if (!payload || !payload.answer) {
    els.chatAnswer.innerHTML = '<div class="p-4 text-sm text-rose-500">No answer generated.</div>';
    return;
  }
  
  const div = document.createElement('div');
  div.className = 'space-y-4';
  div.innerHTML = `
    <div class="prose prose-sm dark:prose-invert max-w-none bg-slate-50 dark:bg-slate-800/50 p-4 rounded-lg border border-slate-100 dark:border-slate-800">
        <p>${payload.answer.replace(/\n/g, '<br>')}</p>
    </div>
    
    <div>
        <h5 class="text-xs font-bold uppercase text-slate-500 mb-2">Sources & Context</h5>
        <div class="space-y-2">
            ${(payload.context || []).map(ctx => `
                <div class="text-xs p-2 border border-slate-100 dark:border-slate-800 rounded bg-white dark:bg-slate-900">
                    <div class="flex justify-between text-brand-600 mb-1">
                        <span class="truncate w-3/4">${ctx.url || 'Database Context'}</span>
                        <span>${ctx.score ? ctx.score.toFixed(2) : ''}</span>
                    </div>
                    <p class="text-slate-600 dark:text-slate-400 line-clamp-2">"${ctx.snippet || ctx.text || ''}"</p>
                </div>
            `).join('')}
        </div>
    </div>
  `;
  els.chatAnswer.appendChild(div);
}

// 6. Recorder Results
function renderRecorderResults(data) {
  els.recorderResults.innerHTML = '';
  const results = data.results || [];
  
  if (!results.length) {
    els.recorderResults.innerHTML = '<div class="p-4 text-sm text-slate-500">No recorder hits.</div>';
    return;
  }
  
  results.forEach(r => {
    const div = document.createElement('div');
    div.className = 'p-2 border-b border-slate-100 dark:border-slate-800 text-sm';
    div.innerHTML = `
        <div class="font-medium text-slate-900 dark:text-white truncate">${r.url}</div>
        <div class="text-xs text-slate-500">${r.entity_type} • ${r.page_type} • Score: ${r.score}</div>
    `;
    els.recorderResults.appendChild(div);
  });
}

/* =========================================
   ACTIONS
   ========================================= */

function renderStructuredData(structured) {
  if (!Array.isArray(structured) || !structured.length) return '';
  const first = structured[0] || {};
  const img = first.image || (first.logo && first.logo.url);
  return `
    <div class="space-y-2">
      ${first.headline ? `<div class="text-sm font-semibold">${first.headline}</div>` : ''}
      ${first.datePublished ? `<div class="text-xs text-slate-500">Published: ${first.datePublished}</div>` : ''}
      ${first.dateModified ? `<div class="text-xs text-slate-500">Updated: ${first.dateModified}</div>` : ''}
      ${first.publisher && first.publisher.name ? `<div class="text-xs text-slate-500">Publisher: ${first.publisher.name}</div>` : ''}
      ${first.author && first.author.name ? `<div class="text-xs text-slate-500">Author: ${first.author.name}</div>` : ''}
      ${img ? `<img src="${img}" alt="${first.headline || 'preview'}" class="rounded-lg border border-slate-200 dark:border-slate-800 w-full object-cover max-h-56">` : ''}
      <details class="text-xs"><summary class="cursor-pointer font-semibold">Structured data (JSON-LD)</summary>
        <pre class="mt-2 bg-slate-100 dark:bg-slate-800 p-2 rounded overflow-auto">${JSON.stringify(structured, null, 2)}</pre>
      </details>
    </div>
  `;
}

function showPageModal(payload) {
  if (!els.pageModal || !els.pageModalContent) return;
  const content = payload.content || {};
  const meta = content.metadata || {};
  const text = content.text || '';
  const og = meta.og_title || meta.title || payload.title || payload.og_title;
  const structured = payload.structured_data || meta.structured_data || [];

  els.pageModalContent.innerHTML = `
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Page Detail</p>
        <h3 class="text-lg font-bold text-slate-900 dark:text-white break-all">${payload.url || 'Selected page'}</h3>
        ${og ? `<div class="text-sm text-slate-600 dark:text-slate-300 mt-1">${og}</div>` : ''}
      </div>
      <button id="page-modal-close-inner" class="text-slate-400 hover:text-slate-700 text-xl leading-none">&times;</button>
    </div>

    <div class="grid gap-4 md:grid-cols-2 mt-4">
      <div class="space-y-3">
        <div class="text-xs font-semibold text-slate-500 uppercase">Overview</div>
        <div class="text-sm text-slate-700 dark:text-slate-300">
          ${chips([meta.content_type || 'Unknown type', meta.language, meta.site_name])}
          ${meta.text_length ? `<div class="mt-1 text-xs text-slate-500">${Math.round(meta.text_length/1024)} KB</div>` : ''}
        </div>
        ${renderStructuredData(structured)}
      </div>
      <div class="space-y-3">
        <div class="text-xs font-semibold text-slate-500 uppercase">Preview</div>
        <div class="bg-slate-50 dark:bg-slate-900 p-3 rounded-lg border border-slate-200 dark:border-slate-800 text-xs font-mono h-64 overflow-y-auto whitespace-pre-wrap text-slate-700 dark:text-slate-200">
          ${text.slice(0, 5000)}${text.length > 5000 ? '...' : ''}
        </div>
      </div>
    </div>
  `;
  els.pageModal.classList.remove('hidden');

  const closer = getEl('page-modal-close-inner');
  if (closer) closer.onclick = hidePageModal;
}

function hidePageModal() {
  if (els.pageModal) els.pageModal.classList.add('hidden');
}

async function loadPageDetail(url) {
  if (els.pageDetail) els.pageDetail.innerHTML = '<div class="p-4 animate-pulse text-sm">Fetching page content...</div>';
  try {
    const res = await fetchWithAuth(`/api/page?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    showPageModal(data);
    if (els.pageDetail) els.pageDetail.innerHTML = '';
  } catch (e) {
    if (els.pageDetail) els.pageDetail.innerHTML = `<div class="p-4 text-rose-500">Error: ${e.message}</div>`;
  }
}

async function refreshStatus() {
  try {
      if (els.statusCards) els.statusCards.innerHTML = '<div class="p-4 text-sm animate-pulse">Connecting to backend...</div>';
      const res = await fetchWithAuth('/api/status');
      const data = await res.json();
      renderStatus(data);
  } catch (e) {
      if (els.statusCards) els.statusCards.innerHTML = `<div class="p-4 text-sm text-rose-500 font-bold">${e.message}</div>`;
      setStatusBadge(els.statusBadges.api, false);
  }
}

async function searchIntel(e) {
  if (e) e.preventDefault();
  if (!els.results) return;
  els.results.innerHTML = '<div class="p-4 animate-pulse">Searching...</div>';
  const qEl = getEl('q');
  const entityEl = getEl('entity');
  const minConfEl = getEl('min_conf');
  const limitEl = getEl('limit');
  if (!qEl || !entityEl || !minConfEl || !limitEl) {
    els.results.innerHTML = '<div class="p-4 text-rose-500">Search form is missing from the page.</div>';
    return;
  }
  try {
      const params = new URLSearchParams({
        q: qEl.value || '',
        entity: entityEl.value || '',
        min_conf: minConfEl.value || 0,
        limit: limitEl.value || 50,
      });
      const res = await fetchWithAuth(`/api/intel?${params}`);
      renderIntel(await res.json(), els.results);
  } catch(e) { els.results.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function semanticSearch(e) {
  if (e) e.preventDefault();
  if (!els.semanticResults) return;
  const qEl = getEl('semantic-q');
  const topkEl = getEl('semantic-topk');
  if (!qEl || !topkEl) {
    els.semanticResults.innerHTML = '<div class="p-4 text-rose-500">Semantic form is missing from the page.</div>';
    return;
  }

  els.semanticResults.innerHTML = '<div class="p-4 animate-pulse">Searching vectors...</div>';
  try {
      const params = new URLSearchParams({
        q: qEl.value || '',
        top_k: topkEl.value || 10,
      });
      const res = await fetchWithAuth(`/api/intel/semantic?${params}`);
      renderSemantic(await res.json(), els.semanticResults);
  } catch(e) { els.semanticResults.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function chatAsk(e) {
  if (e) e.preventDefault();
  if (!els.chatAnswer) return;
  const qEl = getEl('chat-q');
  const entityEl = getEl('chat-entity');
  const topkEl = getEl('chat-topk');
  if (!qEl || !entityEl || !topkEl) {
    els.chatAnswer.innerHTML = '<div class="p-4 text-rose-500">Chat form is missing from the page.</div>';
    return;
  }

  els.chatAnswer.innerHTML = '<div class="p-4 animate-pulse text-brand-600">Thinking...</div>';
  try {
      const body = {
        question: qEl.value,
        entity: entityEl.value,
        top_k: Number(topkEl.value || 6),
      };
      const res = await fetchWithAuth('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      renderChat(await res.json());
  } catch(e) { els.chatAnswer.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function loadPages() {
  if (!els.pagesList) return;
  els.pagesList.innerHTML = '<div class="p-4 animate-pulse">Fetching pages...</div>';
  try {
      const limit = (els.pagesLimit && els.pagesLimit.value) || 100;
      const res = await fetchWithAuth(`/api/pages?limit=${limit}`);
      renderPages(await res.json());
  } catch(e) { els.pagesList.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function recorderSearch(e) {
  if (e) e.preventDefault();
  if (!els.recorderResults) return;
  const qEl = getEl('recorder-q');
  const entityTypeEl = getEl('recorder-entity-type');
  const pageTypeEl = getEl('recorder-page-type');
  const limitEl = getEl('recorder-limit');
  if (!qEl || !entityTypeEl || !pageTypeEl || !limitEl) {
    els.recorderResults.innerHTML = '<div class="p-4 text-rose-500">Recorder form is missing from the page.</div>';
    return;
  }

  els.recorderResults.innerHTML = '<div class="p-4 animate-pulse">Searching...</div>';
  try {
      const params = new URLSearchParams({
        q: qEl.value || '',
        entity_type: entityTypeEl.value || '',
        page_type: pageTypeEl.value || '',
        limit: limitEl.value || 20,
      });
      const res = await fetchWithAuth(`/api/recorder/search?${params}`);
      renderRecorderResults(await res.json());
  } catch(e) { els.recorderResults.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function recorderRefreshHealth() {
  if (!els.recorderHealth) return;
  try {
      const [healthRes, queueRes] = await Promise.all([
        fetchWithAuth('/api/recorder/health'),
        fetchWithAuth('/api/recorder/queue'),
      ]);
      const health = await healthRes.json();
      const queue = await queueRes.json();
      
      els.recorderHealth.innerHTML = `
        <div class="grid gap-4 sm:grid-cols-2">
            <div class="p-3 bg-slate-50 dark:bg-slate-800 rounded border border-slate-200 dark:border-slate-700">
                <div class="text-xs font-bold uppercase text-slate-500">Status</div>
                <div>${health.status}</div>
            </div>
            <div class="p-3 bg-slate-50 dark:bg-slate-800 rounded border border-slate-200 dark:border-slate-700">
                <div class="text-xs font-bold uppercase text-slate-500">Queue Length</div>
                <div>${queue.length || 0}</div>
            </div>
        </div>
      `;
  } catch(e) { els.recorderHealth.innerHTML = `<div class="text-rose-500 text-xs">${e.message}</div>`; }
}

async function recorderMark(e) {
  if (e) e.preventDefault();
  if (els.recorderMarkStatus) els.recorderMarkStatus.textContent = 'Sending...';
  try {
    const body = {
      url: val('recorder-mark-url'),
      mode: val('recorder-mark-mode') || 'manual',
      session_id: val('recorder-mark-session') || 'ui-session',
    };
    const res = await fetchWithAuth('/api/recorder/mark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    els.recorderMarkStatus.textContent = `OK: ${data.url} (${data.mode})`;
    els.recorderMarkStatus.classList.remove('text-rose-500');
    els.recorderMarkStatus.classList.add('text-emerald-600');
  } catch (e) {
    if (els.recorderMarkStatus) {
      els.recorderMarkStatus.textContent = `Error: ${e.message}`;
      els.recorderMarkStatus.classList.remove('text-emerald-600');
      els.recorderMarkStatus.classList.add('text-rose-500');
    }
  }
}

async function runCrawl(e) {
  if (e) e.preventDefault();
  if (els.crawlOutputPanel) els.crawlOutputPanel.innerHTML = '<div class="p-4 animate-pulse">Crawl initiated...</div>';
  try {
      const body = {
        entity: val('crawl-entity'),
        type: val('crawl-type'),
        max_pages: Number(val('crawl-max-pages') || 10),
        total_pages: Number(val('crawl-total-pages') || 50),
        max_depth: Number(val('crawl-max-depth') || 2),
        score_threshold: Number(val('crawl-score-threshold') || 35),
        seed_limit: Number(val('crawl-seed-limit') || 25),
        use_selenium: !!getEl('crawl-use-selenium')?.checked,
        active_mode: !!getEl('crawl-active-mode')?.checked,
        output: val('crawl-output') || '',
        list_pages: Number(val('crawl-list-pages') || 0),
        fetch_text: val('crawl-fetch-url') || '',
        refresh: !!getEl('crawl-refresh')?.checked,
        refresh_batch: Number(val('crawl-refresh-batch') || 50),
      };
      
      const res = await fetchWithAuth('/api/crawl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (els.crawlOutputPanel) els.crawlOutputPanel.innerHTML = `<pre class="text-xs bg-slate-900 text-green-400 p-4 rounded overflow-auto h-64">${JSON.stringify(data, null, 2)}</pre>`;
  } catch(e) { if (els.crawlOutputPanel) els.crawlOutputPanel.innerHTML = `<div class="text-rose-500">${e.message}</div>`; }
}

/* =========================================
   INITIALIZATION
   ========================================= */

function init() {
    initTheme();
    loadSettings();
    initTabs();
    
    if (els.saveBtn) els.saveBtn.onclick = saveSettings;
    if (els.statusBtn) els.statusBtn.onclick = refreshStatus;
    if (els.themeToggle) els.themeToggle.onclick = () => {
        const current = localStorage.getItem('garuda_theme') || (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
        applyTheme(current === 'dark' ? 'light' : 'dark');
    };
    if (els.chatToggle && els.chatContainer) {
        els.chatToggle.onclick = () => els.chatContainer.classList.toggle('hidden');
    }
    
    // Forms
    if (els.searchForm) els.searchForm.onsubmit = searchIntel;
    if (els.semanticForm) els.semanticForm.onsubmit = semanticSearch;
    if (els.chatForm) els.chatForm.onsubmit = chatAsk;
    if (els.pagesBtn) els.pagesBtn.onclick = loadPages;
    if (els.recorderSearchForm) els.recorderSearchForm.onsubmit = recorderSearch;
    if (els.recorderHealthRefresh) els.recorderHealthRefresh.onclick = recorderRefreshHealth;
    if (els.recorderMarkForm) els.recorderMarkForm.onsubmit = recorderMark;
    if (els.crawlForm) els.crawlForm.onsubmit = runCrawl;

    if (els.pageModalClose) els.pageModalClose.onclick = hidePageModal;
    if (els.pageModal) els.pageModal.addEventListener('click', (ev) => {
      if (ev.target === els.pageModal) hidePageModal();
    });

    refreshStatus();
}

document.addEventListener('DOMContentLoaded', init);
