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
};

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

/* ---------- Render helpers ---------- */
function chips(arr = []) {
  return arr.map((t) => `<span class="pill">${t}</span>`).join(' ');
}
function renderStatus(data) {
  els.statusCards.innerHTML = '';
  if (!data || typeof data !== 'object') {
    els.statusCards.innerHTML = '<article class="card muted">No status available.</article>';
    return;
  }
  const card = document.createElement('article');
  card.className = 'card';
  card.innerHTML = `
    <strong>Database:</strong> ${data.db_ok ? '<span class="status-ok">OK</span>' : '<span class="status-bad">Down</span>'}<br>
    <strong>Qdrant:</strong> ${data.qdrant_ok ? '<span class="status-ok">OK</span>' : '<span class="status-bad">Off</span>'} (${data.qdrant_url || 'n/a'})<br>
    <strong>Embedding:</strong> ${data.embedding_loaded ? '<span class="status-ok">Loaded</span>' : '<span class="status-bad">Missing</span>'}<br>
    <strong>Model:</strong> ${data.model || ''} @ ${data.ollama_url || ''}
  `;
  els.statusCards.appendChild(card);
}
function summarizeBasicInfo(bi = {}) {
  const lines = [];
  if (bi.official_name) lines.push(`<div><strong>Name:</strong> ${bi.official_name}</div>`);
  if (bi.description) lines.push(`<div>${bi.description}</div>`);
  if (bi.website) lines.push(`<div><strong>Website:</strong> ${bi.website}</div>`);
  return lines.join('') || '<div class="muted">No basic info.</div>';
}
function summarizePeople(list = []) {
  const people = list.filter((p) => p && (p.name || p.title || p.role || p.bio));
  if (!people.length) return '';
  return `
    <div><strong>People</strong></div>
    <ul>
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
    <div><strong>Products</strong></div>
    <ul>
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
    <div><strong>Metrics</strong></div>
    <ul>
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
    <div><strong>Locations</strong></div>
    <ul>
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

/* ---------- Render sections ---------- */
function renderIntel(results, target) {
  target.innerHTML = '';
  if (!results || !results.length) {
    target.innerHTML = '<article class="card muted">No results.</article>';
    return;
  }
  results.forEach((r) => {
    const card = document.createElement('article');
    card.className = 'card';
    const conf = r.confidence ?? '-';
    const created = r.created || '';
    card.innerHTML = `
      <div class="muted">Confidence: ${conf} • Created: ${created}</div>
      <h4>${r.entity || '(unknown entity)'}</h4>
      ${summarizeIntel(r) || '<div class="muted">No structured fields.</div>'}
      <details><summary>Raw JSON</summary><pre>${JSON.stringify(r, null, 2)}</pre></details>
    `;
    target.appendChild(card);
  });
}
function renderSemantic(results, target) {
  target.innerHTML = '';
  const hits = (results && results.semantic) || [];
  if (!hits.length) {
    target.innerHTML = '<article class="card muted">No semantic results.</article>';
    return;
  }
  hits.forEach((h) => {
    const card = document.createElement('article');
    card.className = 'card';
    const snippet = (h.text || h.snippet || '').slice(0, 260);
    const extra = [h.entity, h.entity_type, h.page_type].filter(Boolean);
    card.innerHTML = `
      <div class="muted">Score: ${h.score?.toFixed ? h.score.toFixed(3) : h.score}</div>
      <strong>${h.url || '(no url)'}</strong>
      ${extra.length ? `<div>${chips(extra)}</div>` : ''}
      <p>${snippet}${snippet && (h.text || h.snippet || '').length > 260 ? '…' : ''}</p>
      <details><summary>Raw JSON</summary><pre>${JSON.stringify(h, null, 2)}</pre></details>
    `;
    target.appendChild(card);
  });
}
function renderChat(payload) {
  els.chatAnswer.innerHTML = '';
  if (!payload || !payload.answer) {
    els.chatAnswer.innerHTML = '<article class="card muted">No answer.</article>';
    return;
  }
  const wrap = document.createElement('article');
  wrap.className = 'card';
  wrap.innerHTML = `
    <h4>Answer</h4>
    <p>${payload.answer}</p>
    <div class="muted">Context</div>
    <div class="cards" id="chat-context-cards"></div>
    <details><summary>Raw JSON</summary><pre>${JSON.stringify(payload, null, 2)}</pre></details>
  `;
  els.chatAnswer.appendChild(wrap);
  const ctxWrap = wrap.querySelector('#chat-context-cards');
  (payload.context || []).forEach((c) => {
    const cCard = document.createElement('article');
    cCard.className = 'card';
    const snippet = (c.snippet || c.text || '').slice(0, 220);
    cCard.innerHTML = `
      <div class="muted">Score: ${c.score ?? '-'} • Source: ${c.source || 'sql'}</div>
      <strong>${c.url || '(no url)'}</strong>
      <p>${snippet}${snippet && (c.snippet || c.text || '').length > 220 ? '…' : ''}</p>
      <details><summary>Raw</summary><pre>${JSON.stringify(c, null, 2)}</pre></details>
    `;
    ctxWrap.appendChild(cCard);
  });
}
function renderPages(pages) {
  els.pagesList.innerHTML = '';
  if (!pages || !pages.length) {
    els.pagesList.innerHTML = '<article class="card muted">No pages found.</article>';
    return;
  }
  pages.forEach((p) => {
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `
      <strong>${p.url || '(no url)'}</strong><br>
      <div class="muted">
        Entity: ${p.entity_type || '-'} • Page: ${p.page_type || '-'} • Score: ${p.score ?? '-'}
      </div>
      <div class="muted">Last fetch: ${p.last_fetch_at || p.created_at || ''}</div>
      <button class="secondary outline" data-url="${p.url}">View details</button>
    `;
    card.querySelector('button').onclick = () => loadPageDetail(p.url);
    els.pagesList.appendChild(card);
  });
}
async function loadPageDetail(url) {
  els.pageDetail.innerHTML = '<article class="card">Loading…</article>';
  const res = await fetchWithAuth('/api/page?url=' + encodeURIComponent(url));
  const data = await res.json();
  const text = (data && data.content && data.content.text) || '';
  const meta = (data && data.content && data.content.metadata) || {};
  const extracted = (data && data.content && data.content.extracted) || {};
  const card = document.createElement('article');
  card.className = 'card';
  card.innerHTML = `
    <h4>${data.url}</h4>
    <p class="muted">Length: ${text.length} chars</p>
    <p>${text.slice(0, 500)}${text.length > 500 ? '…' : ''}</p>
    <details><summary>Metadata</summary><pre>${JSON.stringify(meta, null, 2)}</pre></details>
    <details><summary>Extracted</summary><pre>${JSON.stringify(extracted, null, 2)}</pre></details>
    <details><summary>Raw</summary><pre>${JSON.stringify(data, null, 2)}</pre></details>
  `;
  els.pageDetail.innerHTML = '';
  els.pageDetail.appendChild(card);
}

/* ---------- Actions ---------- */
async function refreshStatus() {
  els.statusCards.innerHTML = '<article class="card">Loading...</article>';
  const res = await fetchWithAuth('/api/status');
  renderStatus(await res.json());
}
async function searchIntel(e) {
  e.preventDefault();
  els.results.innerHTML = '<article class="card">Loading…</article>';
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
  els.semanticResults.innerHTML = '<article class="card">Loading…</article>';
  const params = new URLSearchParams({
    q: document.getElementById('semantic-q').value,
    top_k: document.getElementById('semantic-topk').value || 10,
  });
  const res = await fetchWithAuth('/api/intel/semantic?' + params.toString());
  renderSemantic(await res.json(), els.semanticResults);
}
async function chatAsk(e) {
  e.preventDefault();
  els.chatAnswer.innerHTML = '<article class="card">Thinking…</article>';
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
  els.pagesList.innerHTML = '<article class="card">Loading…</article>';
  const limit = els.pagesLimit.value || 100;
  const res = await fetchWithAuth('/api/pages?limit=' + limit);
  renderPages(await res.json());
}

/* ---------- Init ---------- */
loadSettings();
els.saveBtn?.addEventListener('click', saveSettings);
els.statusBtn?.addEventListener('click', refreshStatus);
els.searchForm?.addEventListener('submit', searchIntel);
els.semanticForm?.addEventListener('submit', semanticSearch);
els.chatForm?.addEventListener('submit', chatAsk);
els.pagesBtn?.addEventListener('click', loadPages);
refreshStatus();
