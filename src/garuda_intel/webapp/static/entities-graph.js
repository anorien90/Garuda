import { els, val } from './config.js';

// Expected backend response: { nodes:[{id,label,type,score,count}], links:[{source,target,weight}] }
const COLORS = {
  person: '#0ea5e9',
  org: '#22c55e',
  location: '#a855f7',
  product: '#f97316',
  unknown: '#94a3b8',
};

function setStatus(msg, isError = false) {
  if (!els.entitiesGraphStatus) return;
  els.entitiesGraphStatus.textContent = msg || '';
  els.entitiesGraphStatus.classList.toggle('text-rose-500', isError);
}

function renderDetails(node, links) {
  if (!els.entitiesGraphDetails) return;
  if (!node) {
    els.entitiesGraphDetails.innerHTML = `
      <div class="text-xs uppercase tracking-wide text-slate-500">Details</div>
      <div class="text-slate-700 dark:text-slate-100">Select a node to see details.</div>
    `;
    return;
  }
  const connected = links
    .filter(l => l.source?.id === node.id || l.target?.id === node.id)
    .map(l => (l.source?.id === node.id ? l.target : l.source))
    .filter(Boolean);
  els.entitiesGraphDetails.innerHTML = `
    <div class="text-xs uppercase tracking-wide text-slate-500">Details</div>
    <div class="space-y-1">
      <div class="text-sm font-semibold">${node.label || node.id}</div>
      <div class="text-xs text-slate-500">${node.type || 'unknown'} • score ${node.score ?? '—'} • count ${node.count ?? '—'}</div>
      <div class="text-xs text-slate-400">Connected (${connected.length}):</div>
      <ul class="list-disc list-inside text-xs text-slate-600 dark:text-slate-200">
        ${connected.map(n => `<li>${n.label || n.id}</li>`).join('') || '<li>None</li>'}
      </ul>
    </div>
  `;
}

function renderLegend() {
  if (!els.entitiesGraphLegend) return;
  els.entitiesGraphLegend.innerHTML = `
    <div class="flex flex-wrap gap-3">
      ${Object.entries(COLORS).map(([k, v]) => `
        <div class="flex items-center gap-2">
          <span class="inline-block w-3 h-3 rounded-full" style="background:${v}"></span>
          <span>${k}</span>
        </div>
      `).join('')}
    </div>
  `;
}

// Prefer local copy; fall back to CDNs if needed
const FORCE_GRAPH_SOURCES = [
  '/static/vendor/force-graph.min.js', // local v1.50.1
  'https://cdn.jsdelivr.net/npm/force-graph@1.50.1/dist/force-graph.min.js',
  'https://unpkg.com/force-graph@1.50.1/dist/force-graph.min.js',
];

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', (e) => reject(e));
      if (existing.readyState === 'complete') return resolve();
      return;
    }
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = (e) => reject(e);
    document.head.appendChild(s);
  });
}

async function loadForceGraphLib() {
  if (window.ForceGraph) return window.ForceGraph;
  let lastErr;
  for (const src of FORCE_GRAPH_SOURCES) {
    try {
      await loadScript(src);
      if (window.ForceGraph) return window.ForceGraph;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error('Failed to load force-graph library');
}

async function fetchGraph() {
  const base = val('base-url') || '';
  const q = encodeURIComponent(els.entitiesGraphQuery?.value || '');
  const type = encodeURIComponent(els.entitiesGraphType?.value || '');
  const min = encodeURIComponent(els.entitiesGraphMinScore?.value || 0);
  const limit = encodeURIComponent(els.entitiesGraphLimit?.value || 100);
  const url = `${base}/api/entities/graph?query=${q}&type=${type}&min_score=${min}&limit=${limit}`;
  setStatus('Loading...');
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' } });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export async function initEntitiesGraph() {
  if (!els.entitiesGraphForm || !els.entitiesGraphCanvas) return;
  renderLegend();
  renderDetails(null, []);
  let graphInstance = null;
  let currentLinks = [];
  let currentNodes = [];

  function resizeGraph() {
    if (!graphInstance || !els.entitiesGraphCanvas) return;
    const rect = els.entitiesGraphCanvas.getBoundingClientRect();
    const w = Math.max(320, rect.width || els.entitiesGraphCanvas.clientWidth || 800);
    const h = Math.max(320, rect.height || els.entitiesGraphCanvas.clientHeight || 540);
    graphInstance.width(w).height(h);
  }

  // When the tab is activated, resize to non-zero dimensions
  document.querySelectorAll('[data-tab-btn]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.tabBtn === 'entities-graph') {
        // allow layout to update before measuring
        setTimeout(resizeGraph, 50);
      }
    });
  });

  async function loadAndRender(ev) {
    ev?.preventDefault();
    try {
      // Fetch data first
      const data = await fetchGraph();
      currentNodes = data.nodes || [];
      currentLinks = (data.links || []).map(l => ({ ...l }));

      // Then load the graph lib and render
      const ForceGraph = await loadForceGraphLib();
      if (!graphInstance) {
        graphInstance = ForceGraph(els.entitiesGraphCanvas)
          .nodeLabel(n => `${n.label || n.id} (${n.type || 'unknown'})`)
          .nodeColor(n => COLORS[n.type] || COLORS.unknown)
          .nodeVal(n => (n.count || 1) + (n.score || 0) * 6)
          .linkColor(() => 'rgba(148, 163, 184, 0.4)')
          .linkDirectionalParticles(1)
          .linkDirectionalParticleWidth(l => Math.max(1, (l.weight || 1) * 1.5))
          .onNodeClick(n => renderDetails(n, currentLinks));
      }
      graphInstance.graphData({ nodes: currentNodes, links: currentLinks });
      resizeGraph(); // ensure visible size after data load
      renderDetails(null, []);
      setStatus(`Loaded ${currentNodes.length} nodes / ${currentLinks.length} links`);
    } catch (e) {
      console.error(e);
      setStatus(e.message || 'Failed to load graph', true);
    }
  }

  els.entitiesGraphForm.onsubmit = loadAndRender;
  if (els.entitiesGraphLoad) els.entitiesGraphLoad.onclick = loadAndRender;
}
