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
  recorderSearchForm: document.getElementById('recorder-search-form'),
  recorderResults: document.getElementById('recorder-results'),
  recorderHealth: document.getElementById('recorder-health'),
  themeToggle: document.getElementById('theme-toggle'),
  themeToggleLabel: document.getElementById('theme-toggle-label'),
  themeToggleIcon: document.getElementById('theme-toggle-icon'),
  tabButtons: document.querySelectorAll('[data-tab-btn]'),
  tabPanels: document.querySelectorAll('[data-tab-panel]'),
  recorderHealthRefresh: document.getElementById('recorder-health-refresh'),
  crawlForm: document.getElementById('crawl-form'),
  crawlOutputPanel: document.getElementById('crawl-output-panel'),
  
};

/* BASIC UI UTILS */

function pill(text) {
  return `<span class="inline-flex items-center rounded-full bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-100 px-2 py-0.5 text-xs font-medium">${text}</span>`;
}
function chips(arr = []) {
  return arr.filter(Boolean).map((t) => pill(t)).join(' ');
}

function applyTheme(mode) {
  const root = document.documentElement;
  const next = mode === 'dark' ? 'dark' : 'light';
  root.classList.toggle('dark', next === 'dark');
  localStorage.setItem('garuda_theme', next);
  // Optional: update theme toggle UI if you have labels/icons
  if (els.themeToggleLabel) els.themeToggleLabel.textContent = next === 'dark' ? 'Dark' : 'Light';
  if (els.themeToggleIcon) els.themeToggleIcon.textContent = next === 'dark' ? '🌙' : '🌞';
}

function initTheme() {
  const saved = localStorage.getItem('garuda_theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (prefersDark ? 'dark' : 'light'));
}

function collapsible(label, content) {
  if (!content) return '';
  return `
      <details class="text-xs my-1 group">
        <summary class="cursor-pointer font-bold">${label}</summary>
        <div class="mt-2 ml-2">${content}</div>
      </details>
  `;
}

function renderKeyValTable(obj) {
  if (!obj || typeof obj !== 'object') return '';
  return `
    <table class="text-xs w-full mb-2">
      <tbody>
        ${Object.entries(obj).map(([k, v]) => `<tr><td class="pr-1 text-slate-400">${k}</td><td>${v}</td></tr>`).join('')}
      </tbody>
    </table>
  `;
}

function renderIntelCard(hit) {
  // Accepts either {entity, confidence, data, ...} or plain .data or .basic_info shape
  let info = hit.data?.basic_info || hit.basic_info || {};
  let data = hit.data || hit;
  let metrics = data.metrics || [];
  let persons = data.persons || [];
  let jobs = data.jobs || [];
  let locations = data.locations || [];
  let events = data.events || [];
  let products = data.products || [];
  let financials = data.financials || [];

  return `
  <article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-3">
    <div class="flex justify-between items-center">
      <div>
        <h4 class="text-lg font-semibold text-slate-900 dark:text-white">${hit.entity || info.official_name || ''}</h4>
        <div class="text-xs uppercase text-brand-600">${hit.entity_type || ''}</div>
      </div>
      <span class="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded" title="Confidence">${hit.confidence ?? (hit.score?.toFixed?.(2) ?? '')}</span>
    </div>
    ${info.description ? `<div class="text-sm text-slate-700 dark:text-slate-300">${info.description}</div>` : ''}

    <div class="flex flex-wrap gap-2 mt-2">
      ${info.industry ? pill(info.industry) : ''}
      ${info.ticker ? pill('Ticker: '+info.ticker) : ''}
      ${info.founded ? pill('Founded: '+info.founded) : ''}
      ${info.website ? pill('🌐 ' + info.website) : ''}
    </div>
    ${metrics.length || financials.length ? collapsible('Financial Metrics',
      `<ul>${metrics.map(m=>`<li>${pill(m.type)}: <b>${m.value}</b> ${m.unit||''}</li>`).join('')}
                     ${financials.map(f=>`<li>${pill(f.year)} ${pill(f.currency)} Rev: <b>${f.revenue || ''}</b> Profit: <b>${f.profit||''}</b></li>`).join('')}
      </ul>`) : ''}
    ${persons.length ? collapsible('Persons', 
      persons.map(p=>`<div class="mb-1">
      <b>${p.name||''}</b> 
      ${p.title?pill(p.title):''} 
      ${p.role?pill(p.role):''}
      <div class="text-xs text-slate-500">${p.bio||''}</div>
      </div>`).join('')
      ) : ''}
    ${jobs.length ? collapsible('Jobs', jobs.map(j=>`<div class="mb-1">${pill(j.title)} at ${j.location||''} <div class="text-xs text-slate-500">${j.description||''}</div></div>`).join('')) : ''}
    ${locations.length ? collapsible('Locations', locations.map(l=>`<div class="mb-1">${pill(l.type)} ${l.city||''}, ${l.country||''} (${l.address||''})</div>`).join('')) : ''}
    ${events.length ? collapsible('Events', events.map(ev=>`<div class="mb-1"><strong>${ev.title || ''}</strong> &mdash; ${ev.date||''}<div class="text-xs">${ev.description||''}</div></div>`).join('')) : ''}
    ${products.length ? collapsible('Products', products.map(pr=>`<div class="mb-1">${pill(pr.status||'')} <b>${pr.name||''}</b> <span class="text-xs text-slate-400">${pr.description||''}</span></div>`).join('')) : ''}
    ${data.text ? collapsible("Hit Text", `<div class='text-xs bg-slate-100 dark:bg-slate-800 p-2 rounded overflow-x-auto'>${data.text?.slice(0,500)}${data.text?.length>500?'…':''}</div>`) : ''}
    <details class="text-xs text-slate-400 cursor-pointer mt-2"><summary>Raw Data</summary>
      <pre class="mt-2 bg-slate-100 dark:bg-slate-800 p-2 rounded overflow-auto">${JSON.stringify(hit, null, 2)}</pre>
    </details>
  </article>
  `;
}

/* RENDERERS */

function renderStatus(data) {
  els.statusCards.innerHTML = '';
  if (!data || typeof data !== 'object') {
    els.statusCards.innerHTML = '<div class="p-4 text-sm text-rose-500">Invalid status data received.</div>';
    return;
  }
  const items = [
      { label: 'Database', status: data.db_ok, info: '', diag: data.db_ok ? '' : 'DB not reachable or query failed.' },
      { label: 'Vector Store', status: data.qdrant_ok, info: data.qdrant_url || 'Not configured', diag: data.qdrant_ok ? '' : 'Qdrant unreachable or collection missing.' },
      { label: 'Embedding', status: data.embedding_loaded, info: data.model || 'No model', diag: data.embedding_loaded ? '' : 'Embedding model not loaded.' },
      { label: 'Ollama', status: !!data.ollama_url, info: data.ollama_url || 'Not configured', diag: data.ollama_url ? '' : 'Ollama API URL not set.' }
  ];

  items.forEach(item => {
      const div = document.createElement('div');
      div.className = `p-3 rounded-lg border flex flex-col gap-1 ${item.status ? 'border-emerald-200 bg-emerald-50 dark:bg-emerald-900/20' : 'border-rose-200 bg-rose-50 dark:bg-rose-900/20'}`;
      div.innerHTML = `
        <div class="flex items-center gap-2">
          <div class="h-2 w-2 rounded-full ${item.status ? 'bg-emerald-500' : 'bg-rose-500'}" title="${item.status ? 'Healthy' : 'Unhealthy'}"></div>
          <span class="text-xs font-bold uppercase text-slate-700 dark:text-slate-200">${item.label}</span>
        </div>
        <div class="text-[10px] mt-1 text-slate-500 dark:text-slate-400 truncate">${item.info}</div>
        ${item.diag&&(!item.status) ? `<div class="text-[10px] text-rose-600 mt-1 italic">${item.diag}</div>` : ''}
      `;
      div.title = item.diag || '';
      els.statusCards.appendChild(div);
  });
}

function renderIntel(results, target) {
  target.innerHTML = '';
  const list = Array.isArray(results) ? results : [results];
  if (!list.length) {
    target.innerHTML = '<div class="p-4 text-sm text-slate-500">No results found.</div>';
    return;
  }
  list.forEach((r) => target.insertAdjacentHTML('beforeend', renderIntelCard(r)));
}

function renderSemantic(data, target) {
  // Accept hits in .semantic, fallback to top array
  const hits = (data && data.semantic) ? data.semantic : Array.isArray(data) ? data : [];
  target.innerHTML = hits.length
    ? hits.map(renderIntelCard).join('')
    : '<div class="p-4 text-sm text-slate-500">No semantic matches found.</div>';
}

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
            ${(payload.context || []).map(renderIntelCard).join('')}
        </div>
    </div>
  `;
  els.chatAnswer.appendChild(div);
}

function renderRecorderResults(data) {
  els.recorderResults.innerHTML = '';
  const results = data.results || [];
  if (!results.length) {
    els.recorderResults.innerHTML = '<div class="p-4 text-sm text-slate-500">No recorder hits.</div>';
    return;
  }
  results.forEach(r => els.recorderResults.insertAdjacentHTML('beforeend', renderIntelCard(r)));
}

async function loadPageDetail(url) {
  els.pageDetail.innerHTML = '<div class="p-4 animate-pulse text-sm">Fetching page content...</div>';
  try {
    const res = await fetchWithAuth(`/api/page?url=${encodeURIComponent(url)}`);
    const data = await res.json(); // returns { url, content: {...}, page: {...} }
    const content = data.content || {};
    const meta = content.metadata || {};
    const text = content.text || "";
    els.pageDetail.innerHTML = `
        <div class="space-y-4">
            <div class="border-b border-slate-200 dark:border-slate-700 pb-2">
                <h3 class="font-bold text-slate-900 dark:text-white break-all">${data.url}</h3>
                <div class="flex gap-2 mt-2">
                    ${chips([meta.content_type, `Size: ${text.length}`])}
                </div>
            </div>
            <div class="bg-slate-50 dark:bg-slate-900 p-3 rounded-lg border border-slate-200 dark:border-slate-800 text-xs font-mono h-64 overflow-y-auto whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                ${text.slice(0, 5000)}${text.length > 5000 ? '...' : ''}
            </div>
            <details class="text-xs"><summary class="cursor-pointer font-bold">Metadata JSON</summary>
                <pre class="mt-2 bg-slate-100 dark:bg-slate-800 p-2 rounded overflow-auto">${JSON.stringify(meta, null, 2)}</pre>
            </details>
        </div>
    `;
  } catch (e) {
    els.pageDetail.innerHTML = `<div class="p-4 text-rose-500">Error: ${e.message}</div>`;
  }
}

/* Add full rest of setup/handlers as before, unchanged except render functions usage... */

async function refreshStatus() {
  try {
      // 1. Force UI to loading state
      if (els.statusCards) els.statusCards.innerHTML = '<div class="p-4 text-sm animate-pulse">Connecting to backend...</div>';
      
      // 2. Fetch from backend
      const res = await fetchWithAuth('/api/status');
      const data = await res.json();
      renderStatus(data);
  } catch (e) {
      if (els.statusCards) els.statusCards.innerHTML = `<div class="p-4 text-sm text-rose-500 font-bold">${e.message}</div>`;
  }
}

async function searchIntel(e) {
  e.preventDefault();
  els.results.innerHTML = '<div class="p-4 animate-pulse">Searching...</div>';
  try {
      const params = new URLSearchParams({
        q: document.getElementById('q').value,
        entity: document.getElementById('entity').value,
        min_conf: document.getElementById('min_conf').value || 0,
        limit: document.getElementById('limit').value || 50,
      });
      const res = await fetchWithAuth(`/api/intel?${params}`);
      renderIntel(await res.json(), els.results);
  } catch(e) { els.results.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function semanticSearch(e) {
  e.preventDefault();
  els.semanticResults.innerHTML = '<div class="p-4 animate-pulse">Searching vectors...</div>';
  try {
      const params = new URLSearchParams({
        q: document.getElementById('semantic-q').value,
        top_k: document.getElementById('semantic-topk').value || 10,
      });
      // Corrected endpoint to match app.py
      const res = await fetchWithAuth(`/api/intel/semantic?${params}`);
      renderSemantic(await res.json(), els.semanticResults);
  } catch(e) { els.semanticResults.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function chatAsk(e) {
  e.preventDefault();
  els.chatAnswer.innerHTML = '<div class="p-4 animate-pulse text-brand-600">Thinking...</div>';
  try {
      const body = {
        question: document.getElementById('chat-q').value, // app.py expects "question"
        entity: document.getElementById('chat-entity').value,
        top_k: Number(document.getElementById('chat-topk').value || 6),
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
  els.pagesList.innerHTML = '<div class="p-4 animate-pulse">Fetching pages...</div>';
  try {
      const limit = els.pagesLimit.value || 100;
      const res = await fetchWithAuth(`/api/pages?limit=${limit}`);
      renderPages(await res.json());
  } catch(e) { els.pagesList.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function recorderSearch(e) {
  e.preventDefault();
  els.recorderResults.innerHTML = '<div class="p-4 animate-pulse">Searching...</div>';
  try {
      const params = new URLSearchParams({
        q: document.getElementById('recorder-q').value,
        entity_type: document.getElementById('recorder-entity-type').value,
        page_type: document.getElementById('recorder-page-type').value,
        limit: document.getElementById('recorder-limit').value || 20,
      });
      const res = await fetchWithAuth(`/api/recorder/search?${params}`);
      renderRecorderResults(await res.json());
  } catch(e) { els.recorderResults.innerHTML = `<div class="p-4 text-rose-500">${e.message}</div>`; }
}

async function recorderRefreshHealth() {
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

async function runCrawl(e) {
  e.preventDefault();
  els.crawlOutputPanel.innerHTML = '<div class="p-4 animate-pulse">Crawl initiated...</div>';
  try {
      // Gather all fields safely
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
      
      const res = await fetchWithAuth('/api/crawl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      els.crawlOutputPanel.innerHTML = `<pre class="text-xs bg-slate-900 text-green-400 p-4 rounded overflow-auto h-64">${JSON.stringify(data, null, 2)}</pre>`;
  } catch(e) { els.crawlOutputPanel.innerHTML = `<div class="text-rose-500">${e.message}</div>`; }
}

/* =========================================
   INITIALIZATION
========================================= */

function loadSettings() {
  // Default to the Flask port 8080 if not set
  if (!els.baseUrl || !els.apiKey) return;
  els.baseUrl.value = localStorage.getItem('garuda_base_url') || 'http://localhost:8080';
  els.apiKey.value = localStorage.getItem('garuda_api_key') || '';
}

function saveSettings() {
  if (!els.baseUrl || !els.apiKey || !els.saveStatus) return;
  localStorage.setItem('garuda_base_url', els.baseUrl.value.trim());
  localStorage.setItem('garuda_api_key', els.apiKey.value.trim());
  els.saveStatus.textContent = 'Saved';
  setTimeout(() => (els.saveStatus.textContent = ''), 1500);
  refreshStatus(); // Optional: refresh status after saving settings
}

function setActiveTab(name) {
  els.tabButtons.forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tabBtn === name);
  });
  els.tabPanels.forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.tabPanel !== name);
  });
  localStorage.setItem('garuda_active_tab', name);
}

function initTabs() {
  const saved = localStorage.getItem('garuda_active_tab') || 'overview';
  setActiveTab(saved);
  els.tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => setActiveTab(btn.dataset.tabBtn));
  });
}

function init() {
    initTheme();
    loadSettings();
    initTabs();
    
    // Attach Listeners safely
    if (els.saveBtn) els.saveBtn.onclick = saveSettings;
    if (els.statusBtn) els.statusBtn.onclick = refreshStatus;
    if (els.themeToggle) els.themeToggle.onclick = () => {
        const current = localStorage.getItem('garuda_theme') || (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
        applyTheme(current === 'dark' ? 'light' : 'dark');
    };
    
    // Forms
    if (els.searchForm) els.searchForm.onsubmit = searchIntel;
    if (els.semanticForm) els.semanticForm.onsubmit = semanticSearch;
    if (els.chatForm) els.chatForm.onsubmit = chatAsk;
    if (els.pagesBtn) els.pagesBtn.onclick = loadPages;
    if (els.recorderSearchForm) els.recorderSearchForm.onsubmit = recorderSearch;
    if (els.recorderHealthRefresh) els.recorderHealthRefresh.onclick = recorderRefreshHealth;
    if (els.crawlForm) els.crawlForm.onsubmit = runCrawl;

    // Initial Status Check
    refreshStatus();
}

document.addEventListener('DOMContentLoaded', init);
