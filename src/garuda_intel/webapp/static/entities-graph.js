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

  const connections = links
    .filter(l => l.source?.id === node.id || l.target?.id === node.id)
    .map(l => {
      const other = l.source?.id === node.id ? l.target : l.source;
      return other ? { node: other, weight: l.weight } : null;
    })
    .filter(Boolean);

  els.entitiesGraphDetails.innerHTML = `
    <div class="flex items-center justify-between">
      <div>
        <div class="text-xs uppercase tracking-wide text-slate-500">Details</div>
        <div class="text-sm font-semibold">${node.label || node.id}</div>
        <div class="text-xs text-slate-500">
          ${node.type || 'unknown'} • score ${node.score ?? '—'} • count ${node.count ?? '—'}
        </div>
      </div>
      <button
        type="button"
        data-action="expand-node"
        data-node-id="${node.id}"
        data-node-label="${node.label || node.id}"
        data-node-type="${node.type || 'unknown'}"
        class="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs font-semibold text-slate-700 dark:text-slate-100 hover:border-brand-400 dark:hover:border-brand-500"
      >
        Expand
      </button>
    </div>
    <div class="mt-2 text-xs text-slate-400">Connected (${connections.length}):</div>
    <ul class="list-disc list-inside text-xs text-slate-600 dark:text-slate-200 space-y-0.5 max-h-56 overflow-auto">
      ${
        connections.length
          ? connections
              .map(
                ({ node: n, weight }) =>
                  `<li><span>${n.label || n.id}</span>${weight ? `<span class="text-slate-400"> (w:${weight})</span>` : ''}</li>`
              )
              .join('')
          : '<li>None</li>'
      }
    </ul>
  `;
}

function renderLegend() {
  if (!els.entitiesGraphLegend) return;
  els.entitiesGraphLegend.innerHTML = `
    <div class="flex flex-wrap gap-3">
      ${Object.entries(COLORS)
        .map(
          ([k, v]) => `
        <div class="flex items-center gap-2">
          <span class="inline-block w-3 h-3 rounded-full" style="background:${v}"></span>
          <span>${k}</span>
        </div>
      `
        )
        .join('')}
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
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
  });
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

  function tuneForces(instance) {
    // Smaller nodes and stronger repulsion to spread out
    const charge = instance.d3Force('charge');
    if (charge) charge.strength(-180).distanceMax(500);
    const linkForce = instance.d3Force('link');
    if (linkForce) {
      linkForce
        .distance((l) => 60 + (l.weight || 1) * 12)
        .strength((l) => 0.6 + Math.min(1, (l.weight || 1) * 0.15));
    }
  }

  async function loadAndRender(ev) {
    ev?.preventDefault();
    try {
      // Fetch data first
      const data = await fetchGraph();
      currentNodes = data.nodes || [];
      currentLinks = (data.links || []).map((l) => ({ ...l }));

      // Then load the graph lib and render
      const ForceGraph = await loadForceGraphLib();
      if (!graphInstance) {
        const createGraph = ForceGraph(); // factory → instance
        graphInstance = createGraph(els.entitiesGraphCanvas)
          .nodeRelSize(3) // base size multiplier
          .nodeLabel((n) => `${n.label || n.id} (${n.type || 'unknown'})`)
          .nodeColor((n) => COLORS[n.type] || COLORS.unknown)
          .nodeVal((n) => Math.max(1.5, (n.count || 1) * 0.4 + (n.score || 0) * 2))
          .linkColor(() => 'rgba(148, 163, 184, 0.35)')
          .linkDirectionalParticles(1)
          .linkDirectionalParticleWidth((l) => Math.max(0.6, (l.weight || 1) * 1.2))
          .onNodeClick((n) => renderDetails(n, currentLinks));
        tuneForces(graphInstance);
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

  // Allow expanding from the selected node
  if (els.entitiesGraphDetails) {
    els.entitiesGraphDetails.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action="expand-node"]');
      if (!btn) return;
      const nodeId = btn.dataset.nodeId || '';
      const nodeType = btn.dataset.nodeType || '';
      if (els.entitiesGraphQuery) els.entitiesGraphQuery.value = nodeId;
      if (els.entitiesGraphType && nodeType && nodeType !== 'unknown') {
        els.entitiesGraphType.value = nodeType;
      }
      loadAndRender();
    });
  }

  els.entitiesGraphForm.onsubmit = loadAndRender;
  if (els.entitiesGraphLoad) els.entitiesGraphLoad.onclick = loadAndRender;
}
