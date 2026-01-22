const els = {
  baseUrl: document.getElementById('base-url'),
  apiKey: document.getElementById('api-key'),
  saveBtn: document.getElementById('save-settings'),
  saveStatus: document.getElementById('save-status'),
  statusBtn: document.getElementById('refresh-status'),
  statusCards: document.getElementById('status-cards'),
  searchForm: document.getElementById('search-form'),
  results: document.getElementById('results'),
  semanticForm: document.getElementById('semantic-form'),
  semanticResults: document.getElementById('semantic-results'),
  chatForm: document.getElementById('chat-form'),
  chatAnswer: document.getElementById('chat-answer'),
  pagesBtn: document.getElementById('load-pages'),
  pagesLimit: document.getElementById('pages-limit'),
  pagesList: document.getElementById('pages'),
  pageDetail: document.getElementById('page-detail'),
  themeToggle: document.getElementById('theme-toggle'),
  themeToggleLabel: document.getElementById('theme-toggle-label'),
  themeToggleIcon: document.getElementById('theme-toggle-icon'),
  recorderSearchForm: document.getElementById('recorder-search-form'),
  recorderResults: document.getElementById('recorder-results'),
  recorderHealth: document.getElementById('recorder-health'),
  recorderHealthRefresh: document.getElementById('recorder-health-refresh'),
  recorderMarkForm: document.getElementById('recorder-mark-form'),
  recorderMarkStatus: document.getElementById('recorder-mark-status'),
  crawlForm: document.getElementById('crawl-form'),
  crawlOutputPanel: document.getElementById('crawl-output-panel'),
};

function applyTheme(mode) {
  const root = document.documentElement;
  const next = mode === 'dark' ? 'dark' : 'light';
  root.classList.toggle('dark', next === 'dark');
  root.setAttribute('data-theme', next);
  localStorage.setItem('garuda_theme', next);
  if (els.themeToggleLabel) els.themeToggleLabel.textContent = next === 'dark' ? 'Dark' : 'Light';
  if (els.themeToggleIcon) els.themeToggleIcon.textContent = next === 'dark' ? '🌙' : '🌞';
}
function initTheme() {
  const saved = localStorage.getItem('garuda_theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (prefersDark ? 'dark' : 'light'));
}

function loadSettings() {
  els.baseUrl.value = localStorage.getItem('garuda_base_url') || 'http://localhost:8080';
  els.apiKey.value = localStorage.getItem('garuda_api_key') || '';
}
function saveSettings() {
  localStorage.setItem('garuda_base_url', els.baseUrl.value.trim());
  localStorage.setItem('garuda_api_key', els.apiKey.value.trim());
  els.saveStatus.textContent = 'Saved';
  setTimeout(() => (els.saveStatus.textContent = ''), 1500);
}
async function fetchWithAuth(path, opts = {}) {
  const base = (els.baseUrl.value || '').replace(/\/+$/, '');
  const url = base + path;
  const headers = { ...(opts.headers || {}) };
  const key = els.apiKey.value.trim();
  if (key) headers['X-API-Key'] = key;
  return fetch(url, { ...opts, headers });
}

function pill(text) {
  return `<span class="inline-flex items-center rounded-full bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-100 px-2 py-0.5 text-xs font-medium">${text}</span>`;
}
function chips(arr = []) {
  return arr.map((t) => pill(t)).join(' ');
}
function renderStatus(data) {
  els.statusCards.innerHTML = '';
  if (!data || typeof data !== 'object') {
    els.statusCards.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm text-slate-600 dark:text-slate-300">No status available.</article>';
    return;
  }
  const card = document.createElement('article');
  card.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
  card.innerHTML = `
    <div class="flex items-center justify-between">
      <span class="text-sm font-semibold text-slate-800 dark:text-slate-100">Database</span>
      <span class="${data.db_ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'} font-semibold">${data.db_ok ? 'OK' : 'Down'}</span>
    </div>
    <div class="flex items-center justify-between">
      <span class="text-sm font-semibold text-slate-800 dark:text-slate-100">Qdrant</span>
      <span class="${data.qdrant_ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'} font-semibold">
        ${data.qdrant_ok ? 'OK' : 'Off'} <span class="text-xs text-slate-500 dark:text-slate-400">${data.qdrant_url || 'n/a'}</span>
      </span>
    </div>
    <div class="flex items-center justify-between">
      <span class="text-sm font-semibold text-slate-800 dark:text-slate-100">Embedding</span>
      <span class="${data.embedding_loaded ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'} font-semibold">${data.embedding_loaded ? 'Loaded' : 'Missing'}</span>
    </div>
    <div class="text-sm text-slate-600 dark:text-slate-300">
      <div><span class="font-semibold text-slate-800 dark:text-slate-100">Model:</span> ${data.model || ''}</div>
      <div><span class="font-semibold text-slate-800 dark:text-slate-100">Ollama:</span> ${data.ollama_url || ''}</div>
    </div>
  `;
  els.statusCards.appendChild(card);
}
function summarizeBasicInfo(bi = {}) {
  const lines = [];
  if (bi.official_name) lines.push(`<div class="font-semibold text-slate-900 dark:text-slate-100">${bi.official_name}</div>`);
  if (bi.description) lines.push(`<div class="text-sm text-slate-700 dark:text-slate-300">${bi.description}</div>`);
  if (bi.website) lines.push(`<div class="text-sm text-brand-600 dark:text-brand-300">${bi.website}</div>`);
  return lines.join('') || '<div class="text-sm text-slate-500">No basic info.</div>';
}
function summarizePeople(list = []) {
  const people = list.filter((p) => p && (p.name || p.title || p.role || p.bio));
  if (!people.length) return '';
  return `
    <div class="text-sm font-semibold text-slate-800 dark:text-slate-100">People</div>
    <ul class="text-sm text-slate-700 dark:text-slate-300 space-y-1">
      ${people
        .map(
          (p) =>
            `<li><strong>${p.name || '(unknown)'}</strong> ${p.title || p.role || ''}${p.bio ? ` — ${p.bio}` : ''}</li>`
        )
        .join('')}
    </ul>
  `;
}
function summarizeProducts(list = []) {
  const items = list.filter((p) => p && (p.name || p.description));
  if (!items.length) return '';
  return `
    <div class="text-sm font-semibold text-slate-800 dark:text-slate-100">Products</div>
    <ul class="text-sm text-slate-700 dark:text-slate-300 space-y-1">
      ${items
        .map(
          (p) =>
            `<li><strong>${p.name || '(unnamed)'}</strong>${p.status ? ` (${p.status})` : ''}${p.description ? ` — ${p.description}` : ''}</li>`
        )
        .join('')}
    </ul>
  `;
}
function summarizeMetrics(list = []) {
  const items = list.filter((m) => m && (m.type || m.value));
  if (!items.length) return '';
  return `
    <div class="text-sm font-semibold text-slate-800 dark:text-slate-100">Metrics</div>
    <ul class="text-sm text-slate-700 dark:text-slate-300 space-y-1">
      ${items
        .map(
          (m) =>
            `<li>${m.type || 'metric'}: ${m.value ?? ''} ${m.unit || ''} ${m.date ? `(${m.date})` : ''}</li>`
        )
        .join('')}
    </ul>
  `;
}
function summarizeLocations(list = []) {
  const items = list.filter((l) => l && (l.address || l.city || l.country));
  if (!items.length) return '';
  return `
    <div class="text-sm font-semibold text-slate-800 dark:text-slate-100">Locations</div>
    <ul class="text-sm text-slate-700 dark:text-slate-300 space-y-1">
      ${items
        .map(
          (l) =>
            `<li>${l.address || l.city || l.country || ''}${l.type ? ` (${l.type})` : ''}</li>`
        )
        .join('')}
    </ul>
  `;
}
function summarizeIntel(r) {
  const data = r.data || {};
  const parts = [];
  parts.push(summarizeBasicInfo(data.basic_info || {}));
  parts.push(summarizePeople(data.persons || []));
  parts.push(summarizeProducts(data.products || []));
  parts.push(summarizeMetrics(data.metrics || []));
  parts.push(summarizeLocations(data.locations || []));
  return parts.filter(Boolean).join('');
}

function renderIntel(results, target) {
  target.innerHTML = '';
  if (!results || !results.length) {
    target.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm text-slate-500">No results.</article>';
    return;
  }
  results.forEach((r) => {
    const card = document.createElement('article');
    card.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
    const conf = r.confidence ?? '-';
    const created = r.created || '';
    card.innerHTML = `
      <div class="text-xs text-slate-500 dark:text-slate-400">Confidence: ${conf} • Created: ${created}</div>
      <h4 class="text-lg font-semibold text-slate-900 dark:text-white">${r.entity || '(unknown entity)'}</h4>
      ${summarizeIntel(r) || '<div class="text-sm text-slate-500">No structured fields.</div>'}
      <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Raw JSON</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(r, null, 2)}</pre></details>
    `;
    target.appendChild(card);
  });
}
function renderSemantic(results, target) {
  target.innerHTML = '';
  const hits = (results && results.semantic) || [];
  if (!hits.length) {
    target.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm text-slate-500">No semantic results.</article>';
    return;
  }
  hits.forEach((h) => {
    const card = document.createElement('article');
    card.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
    const snippet = (h.text || h.snippet || '').slice(0, 260);
    const extra = [h.entity, h.entity_type, h.page_type].filter(Boolean);
    card.innerHTML = `
      <div class="text-xs text-slate-500 dark:text-slate-400">Score: ${h.score?.toFixed ? h.score.toFixed(3) : h.score}</div>
      <div class="text-sm font-semibold text-slate-900 dark:text-white break-words">${h.url || '(no url)'}</div>
      ${extra.length ? `<div class="flex flex-wrap gap-2">${chips(extra)}</div>` : ''}
      <p class="text-sm text-slate-700 dark:text-slate-300">${snippet}${snippet && (h.text || h.snippet || '').length > 260 ? '…' : ''}</p>
      <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Raw JSON</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(h, null, 2)}</pre></details>
    `;
    target.appendChild(card);
  });
}
function renderChat(payload) {
  els.chatAnswer.innerHTML = '';
  if (!payload || !payload.answer) {
    els.chatAnswer.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm text-slate-500">No answer.</article>';
    return;
  }
  const wrap = document.createElement('article');
  wrap.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-3';
  wrap.innerHTML = `
    <h4 class="text-lg font-semibold text-slate-900 dark:text-white">Answer</h4>
    <p class="text-sm text-slate-800 dark:text-slate-100 leading-relaxed">${payload.answer}</p>
    <div class="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 font-semibold">Context</div>
    <div class="grid gap-3" id="chat-context-cards"></div>
    <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Raw JSON</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(payload, null, 2)}</pre></details>
  `;
  els.chatAnswer.appendChild(wrap);
  const ctxWrap = wrap.querySelector('#chat-context-cards');
  (payload.context || []).forEach((c) => {
    const cCard = document.createElement('article');
    cCard.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-3 space-y-1';
    const snippet = (c.snippet || c.text || '').slice(0, 220);
    cCard.innerHTML = `
      <div class="text-xs text-slate-500 dark:text-slate-400">Score: ${c.score ?? '-'} • Source: ${c.source || 'sql'}</div>
      <div class="text-sm font-semibold text-slate-900 dark:text-white break-words">${c.url || '(no url)'}</div>
      <p class="text-sm text-slate-700 dark:text-slate-300">${snippet}${snippet && (c.snippet || c.text || '').length > 220 ? '…' : ''}</p>
      <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Raw</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(c, null, 2)}</pre></details>
    `;
    ctxWrap.appendChild(cCard);
  });
}
function renderPages(pages) {
  els.pagesList.innerHTML = '';
  if (!pages || !pages.length) {
    els.pagesList.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm text-slate-500">No pages found.</article>';
    return;
  }
  pages.forEach((p) => {
    const card = document.createElement('article');
    card.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
    card.innerHTML = `
      <div class="text-sm font-semibold text-slate-900 dark:text-white break-words">${p.url || '(no url)'}</div>
      <div class="text-xs text-slate-500 dark:text-slate-400">
        Entity: ${p.entity_type || '-'} • Page: ${p.page_type || '-'} • Score: ${p.score ?? '-'}
      </div>
      <div class="text-xs text-slate-500 dark:text-slate-400">Last fetch: ${p.last_fetch_at || p.created_at || ''}</div>
      <button class="inline-flex items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-sm font-medium text-slate-800 dark:text-slate-100 hover:border-brand-400 dark:hover;border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1 focus:ring-offset-slate-50 dark:focus:ring-offset-slate-900" data-url="${p.url}">View details</button>
    `;
    card.querySelector('button').onclick = () => loadPageDetail(p.url);
    els.pagesList.appendChild(card);
  });
}
async function loadPageDetail(url) {
  els.pageDetail.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Loading…</article>';
  const res = await fetchWithAuth('/api/page?url=' + encodeURIComponent(url));
  const data = await res.json();
  const text = (data && data.content && data.content.text) || '';
  const meta = (data && data.content && data.content.metadata) || {};
  const extracted = (data && data.content && data.content.extracted) || {};
  const card = document.createElement('article');
  card.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
  card.innerHTML = `
    <h4 class="text-lg font-semibold text-slate-900 dark:text-white break-words">${data.url}</h4>
    <p class="text-xs text-slate-500 dark:text-slate-400">Length: ${text.length} chars</p>
    <p class="text-sm text-slate-800 dark:text-slate-100 leading-relaxed">${text.slice(0, 500)}${text.length > 500 ? '…' : ''}</p>
    <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Metadata</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(meta, null, 2)}</pre></details>
    <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Extracted</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(extracted, null, 2)}</pre></details>
    <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Raw</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(data, null, 2)}</pre></details>
  `;
  els.pageDetail.innerHTML = '';
  els.pageDetail.appendChild(card);
}

function renderRecorderResults(data) {
  els.recorderResults.innerHTML = '';
  const results = (data && data.results) || [];
  if (!results.length) {
    els.recorderResults.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm text-slate-500">No recorder results.</article>';
    return;
  }
  results.forEach((r) => {
    const card = document.createElement('article');
    card.className = 'rounded-lg border border-slate-200 dark;border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
    card.innerHTML = `
      <div class="text-sm font-semibold text-slate-900 dark:text-white break-words">${r.url || '(no url)'}</div>
      <div class="text-xs text-slate-500 dark:text-slate-400">Entity: ${r.entity_type || '-'} • Page: ${r.page_type || '-'}</div>
      <div class="text-xs text-slate-500 dark:text-slate-400">Score: ${r.score ?? '-'}</div>
      <details class="text-sm text-slate-600 dark:text-slate-300"><summary class="cursor-pointer">Raw JSON</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(r, null, 2)}</pre></details>
    `;
    els.recorderResults.appendChild(card);
  });
}
function renderRecorderHealth(data) {
  els.recorderHealth.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'grid gap-3 sm:grid-cols-2';
  grid.innerHTML = `
    <article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2">
      <div class="text-sm font-semibold text-slate-800 dark:text-slate-100">Health</div>
      <div class="text-sm text-slate-700 dark:text-slate-300">${JSON.stringify(data.health || data, null, 2)}</div>
    </article>
    <article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2">
      <div class="text-sm font-semibold text-slate-800 dark:text-slate-100">Queue</div>
      <div class="text-sm text-slate-700 dark:text-slate-300">${JSON.stringify(data.queue || data, null, 2)}</div>
    </article>
  `;
  els.recorderHealth.appendChild(grid);
}
function renderCrawlOutput(payload) {
  els.crawlOutputPanel.innerHTML = '';
  const card = document.createElement('article');
  card.className = 'rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-2';
  card.innerHTML = `
    <div class="text-sm font-semibold text-slate-900 dark:text-white">Crawl response</div>
    <details class="text-sm text-slate-600 dark:text-slate-300" open><summary class="cursor-pointer">Raw JSON</summary><pre class="mt-2 text-xs bg-slate-100 dark:bg-slate-800/70 rounded p-2 overflow-auto">${JSON.stringify(payload, null, 2)}</pre></details>
  `;
  els.crawlOutputPanel.appendChild(card);
}

async function refreshStatus() {
  if (els.statusCards) els.statusCards.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Loading...</article>';
  const res = await fetchWithAuth('/api/status');
  renderStatus(await res.json());
}
async function searchIntel(e) {
  e.preventDefault();
  els.results.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Loading…</article>';
  const params = new URLSearchParams({
    q: document.getElementById('q').value,
    entity: document.getElementById('entity').value,
    min_conf: document.getElementById('min_conf').value || 0,
    limit: document.getElementById('limit').value || 50,
  });
  const res = await fetchWithAuth('/api/intel?' + params.toString());
  renderIntel(await res.json(), els.results);
}
async function semanticSearch(e) {
  e.preventDefault();
  els.semanticResults.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Loading…</article>';
  const params = new URLSearchParams({
    q: document.getElementById('semantic-q').value,
    top_k: document.getElementById('semantic-topk').value || 10,
  });
  const res = await fetchWithAuth('/api/intel/semantic?' + params.toString());
  renderSemantic(await res.json(), els.semanticResults);
}
async function chatAsk(e) {
  e.preventDefault();
  els.chatAnswer.innerHTML = '<article class="rounded-lg border border-slate-200 dark;border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Thinking…</article>';
  const body = {
    question: document.getElementById('chat-q').value,
    entity: document.getElementById('chat-entity').value,
    top_k: Number(document.getElementById('chat-topk').value || 6),
  };
  const res = await fetchWithAuth('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  renderChat(await res.json());
}
async function loadPages() {
  els.pagesList.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Loading…</article>';
  const limit = els.pagesLimit.value || 100;
  const res = await fetchWithAuth('/api/pages?limit=' + limit);
  renderPages(await res.json());
}
async function recorderSearch(e) {
  e.preventDefault();
  els.recorderResults.innerHTML = '<article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Loading…</article>';
  const params = new URLSearchParams({
    q: document.getElementById('recorder-q').value,
    entity_type: document.getElementById('recorder-entity-type').value,
    page_type: document.getElementById('recorder-page-type').value,
    limit: document.getElementById('recorder-limit').value || 20,
  });
  const res = await fetchWithAuth('/search?' + params.toString());
  renderRecorderResults(await res.json());
}
async function recorderRefreshHealth() {
  els.recorderHealth.innerHTML = '<article class="rounded-lg border border-slate-200 dark;border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Loading…</article>';
  const [healthRes, queueRes] = await Promise.all([
    fetchWithAuth('/healthz'),
    fetchWithAuth('/queue_info'),
  ]);
  const health = await healthRes.json();
  const queue = await queueRes.json();
  renderRecorderHealth({ health, queue });
}
async function recorderMark(e) {
  e.preventDefault();
  els.recorderMarkStatus.textContent = 'Sending…';
  const body = {
    url: document.getElementById('recorder-mark-url').value,
    mode: document.getElementById('recorder-mark-mode').value || 'manual',
    session_id: document.getElementById('recorder-mark-session').value || 'ui-session',
  };
  const res = await fetchWithAuth('/mark_page', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  els.recorderMarkStatus.textContent = `Result: ${JSON.stringify(data)}`;
}
async function runCrawl(e) {
  e.preventDefault();
  els.crawlOutputPanel.innerHTML = '<article class="rounded-lg border border-slate-200 dark;border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 text-sm">Running…</article>';
  // This assumes a backend shim exists that proxies to search.py CLI; adjust endpoint as implemented.
  const body = {
    entity: document.getElementById('crawl-entity').value,
    type: document.getElementById('crawl-type').value,
    max_pages: Number(document.getElementById('crawl-max-pages').value || 10),
    total_pages: Number(document.getElementById('crawl-total-pages').value || 50),
    max_depth: Number(document.getElementById('crawl-max-depth').value || 2),
    score_threshold: Number(document.getElementById('crawl-score-threshold').value || 35),
    seed_limit: Number(document.getElementById('crawl-seed-limit').value || 25),
    use_selenium: !!document.getElementById('crawl-use-selenium').checked,
    active_mode: !!document.getElementById('crawl-active-mode').checked,
    output: document.getElementById('crawl-output').value || '',
    list_pages: Number(document.getElementById('crawl-list-pages').value || 0),
    fetch_text: document.getElementById('crawl-fetch-url').value || '',
    refresh: !!document.getElementById('crawl-refresh').checked,
    refresh_batch: Number(document.getElementById('crawl-refresh-batch').value || 50),
  };
  // Replace /api/crawl with the actual endpoint that wraps search.py; this is the UI hook.
  const res = await fetchWithAuth('/api/crawl', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  renderCrawlOutput(await res.json());
}

initTheme();
loadSettings();
els.saveBtn?.addEventListener('click', saveSettings);
els.statusBtn?.addEventListener('click', refreshStatus);
els.searchForm?.addEventListener('submit', searchIntel);
els.semanticForm?.addEventListener('submit', semanticSearch);
els.chatForm?.addEventListener('submit', chatAsk);
els.pagesBtn?.addEventListener('click', loadPages);
els.themeToggle?.addEventListener('click', () => {
  const current = localStorage.getItem('garuda_theme') || (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  applyTheme(current === 'dark' ? 'light' : 'dark');
});
els.recorderSearchForm?.addEventListener('submit', recorderSearch);
els.recorderHealthRefresh?.addEventListener('click', recorderRefreshHealth);
els.recorderMarkForm?.addEventListener('submit', recorderMark);
els.crawlForm?.addEventListener('submit', runCrawl);
refreshStatus();
