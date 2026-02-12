import { els, val } from './config.js';
import { pill, collapsible, renderKeyValTable } from './ui.js';
import { showModal, updateModal } from './modals.js';

// Color maps for node/edge kinds - will be updated from schema API
let COLORS = {
  person: '#0ea5e9',
  org: '#22c55e',
  location: '#a855f7',
  product: '#f97316',
  event: '#06b6d4',
  'semantic-snippet': '#fbbf24',
  seed: '#84cc16',
  entity: '#14b8a6',
  page: '#4366f1',
  intel: '#f43f5e',
  image: '#facc15',
  media: '#ec4899',
  unknown: '#94a3b8',
};

let EDGE_COLORS = {
  cooccurrence: 'rgba(148,163,184,0.22)',
  'page-mentions': 'rgba(34,197,94,0.28)',
  'intel-mentions': 'rgba(244,63,94,0.32)',
  'intel-primary': 'rgba(244,63,94,0.38)',
  'page-image': 'rgba(250,204,21,0.30)',
  'page-media': 'rgba(236,72,153,0.30)',
  'entity-media': 'rgba(236,72,153,0.35)',
  link: 'rgba(99,102,241,0.28)',
  relationship: 'rgba(139,92,246,0.35)',
  'seed-entity': 'rgba(132,204,22,0.30)',
  'semantic-hit': 'rgba(251,191,36,0.30)',
  'has-person': 'rgba(14,165,233,0.35)',
  'has-location': 'rgba(168,85,247,0.35)',
  'has-product': 'rgba(249,115,22,0.35)',
  default: 'rgba(148,163,184,0.18)',
};

// Schema cache
let schemaCache = null;
let schemaCacheTime = 0;
const SCHEMA_CACHE_TTL = 60000; // 1 minute cache

const PARTICLE_SPEED = 0.0002;
const PARTICLE_WIDTH_BASE = 0.45;
const PARTICLE_PROB = 0.08;
const HOVER_MODAL_DELAY = 3500;
const LABEL_ZOOM_THRESHOLD = 0.4;

function _isValidUUID(str) {
  return typeof str === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(str);
}

let use3D = false;
let graphInstance = null;
let currentNodes = [];
let currentLinks = [];
let filteredNodes = [];
let filteredLinks = [];
let selectedNodeId = null;
let hoverTimer = null;
let activeModalNodeId = null;
let activeModalId = null;

// --- Filter state: whitelist (allowed) / blacklist (excluded) ---
// whitelist empty = all allowed; items in blacklist are excluded
let nodeWhitelist = new Set();
let nodeBlacklist = new Set();
let edgeWhitelist = new Set();
let edgeBlacklist = new Set();

// --- Pre-request filter mode: filters marked as pre-request affect the API query ---
let preRequestNodeFilters = new Set(); // node kinds that are pre-request filters

// --- All known entity/edge kinds from the database schema ---
let allDbNodeKinds = new Set();
let allDbEdgeKinds = new Set();

// --- Node selection state ---
let selectedNodes = new Map(); // id -> node
let selectionMode = false;
let selectionRect = null; // {startX, startY} during drag
let selectionDepth = 0; // BFS depth for selection (0 = single node, 1-3 hops)

// --- Relation filter/highlight ---
let highlightedRelTypes = new Set();
let relationFilterText = '';

// --- Add-relation state ---
let addRelationSourceNodes = []; // nodes to connect from
let addRelationTargetNode = null;

const filterEls = {
  depth: () => document.getElementById('entities-graph-depth'),
  toggle3d: () => document.getElementById('entities-graph-toggle3d'),
};

function escapeHtml(val) {
  return String(val)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setStatus(msg, isError = false) {
  if (!els.entitiesGraphStatus) return;
  els.entitiesGraphStatus.textContent = msg || '';
  els.entitiesGraphStatus.classList.toggle('text-rose-500', isError);
}

/**
 * Fetch schema from API with caching
 */
async function fetchSchema() {
  const now = Date.now();
  if (schemaCache && (now - schemaCacheTime) < SCHEMA_CACHE_TTL) {
    return schemaCache;
  }
  
  try {
    const base = val('base-url') || '';
    const res = await fetch(`${base}/api/schema/full`, {
      headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
    });
    if (!res.ok) throw new Error(`Schema fetch failed (${res.status})`);
    schemaCache = await res.json();
    schemaCacheTime = now;
    
    // Update color maps
    if (schemaCache.colors?.nodes) {
      COLORS = { ...COLORS, ...schemaCache.colors.nodes };
    }
    if (schemaCache.colors?.edges) {
      EDGE_COLORS = { ...EDGE_COLORS, ...schemaCache.colors.edges };
    }

    // Populate all known entity/edge kinds from the schema
    if (schemaCache.kinds) {
      allDbNodeKinds = new Set(Object.keys(schemaCache.kinds));
    }
    if (schemaCache.relations) {
      allDbEdgeKinds = new Set(Object.keys(schemaCache.relations));
    }
    
    return schemaCache;
  } catch (e) {
    console.warn('Failed to fetch schema:', e);
    return null;
  }
}

/**
 * Get node color, falling back to defaults
 * Priority: node.kind > node.type > meta.entity_kind > unknown
 */
function getNodeColor(node) {
  // First try the explicit kind field (most specific)
  const kind = node.kind || node.meta?.kind;
  if (kind && COLORS[kind]) {
    return COLORS[kind];
  }
  // Then try the type field (type may already be derived from meta.entity_kind on backend)
  const type = node.type || node.meta?.entity_kind;
  return COLORS[type] || COLORS.unknown;
}

/**
 * Get edge color, falling back to defaults
 */
function getEdgeColor(link) {
  const kind = link.kind || link.meta?.relation_type;
  return EDGE_COLORS[kind] || EDGE_COLORS.default;
}

// ─── Dynamic filter pills ───

/**
 * Discover all node kinds present in current graph data
 */
function discoverNodeKinds(nodes) {
  const kinds = new Set();
  for (const n of nodes) {
    const k = (n.kind || n.type || n.meta?.entity_kind || 'unknown').toLowerCase();
    kinds.add(k);
  }
  return kinds;
}

/**
 * Discover all edge kinds present in current graph data
 */
function discoverEdgeKinds(links) {
  const kinds = new Set();
  for (const l of links) {
    kinds.add(l.kind || 'link');
  }
  return kinds;
}

/**
 * Discover all relation types from edge metadata
 */
function discoverRelationTypes(links) {
  const types = new Set();
  for (const l of links) {
    if (l.meta?.relation_type) types.add(l.meta.relation_type);
    if (l.kind) types.add(l.kind);
  }
  return types;
}

/**
 * Render colorized filter pills for node and edge types.
 * Shows all kinds from the database (not just current result set).
 * Kinds present in the current data are shown normally; db-only kinds are shown dimmer.
 * Whitelist empty = all allowed. Click cycles: allowed → blacklisted → removed (allowed again).
 * Right-click toggles pre-request mode (filter affects API query).
 */
function renderFilterBar() {
  const bar = document.getElementById('entities-graph-filter-bar');
  if (!bar) return;

  const resultNodeKinds = discoverNodeKinds(currentNodes);
  const resultEdgeKinds = discoverEdgeKinds(currentLinks);

  // Merge result kinds with all database kinds
  const allNodeKinds = new Set([...resultNodeKinds, ...allDbNodeKinds]);
  const allEdgeKinds = new Set([...resultEdgeKinds, ...allDbEdgeKinds]);

  let html = '';

  // Node kind pills
  html += '<span class="text-[10px] text-slate-400 uppercase mr-1">Nodes:</span>';
  for (const kind of allNodeKinds) {
    const color = COLORS[kind] || COLORS.unknown;
    const inWL = nodeWhitelist.has(kind);
    const inBL = nodeBlacklist.has(kind);
    const isPre = preRequestNodeFilters.has(kind);
    const inResult = resultNodeKinds.has(kind);
    const state = inBL ? 'blacklist' : inWL ? 'whitelist' : 'default';
    html += _filterPill(kind, color, state, 'node', isPre, inResult);
  }

  // Edge kind pills
  html += '<span class="text-[10px] text-slate-400 uppercase ml-3 mr-1">Edges:</span>';
  for (const kind of allEdgeKinds) {
    const color = EDGE_COLORS[kind] || EDGE_COLORS.default;
    const inWL = edgeWhitelist.has(kind);
    const inBL = edgeBlacklist.has(kind);
    const inResult = resultEdgeKinds.has(kind);
    const state = inBL ? 'blacklist' : inWL ? 'whitelist' : 'default';
    html += _filterPill(kind, color, state, 'edge', false, inResult);
  }

  bar.innerHTML = html;

  // Attach click handlers
  bar.querySelectorAll('[data-filter-kind]').forEach(el => {
    el.addEventListener('click', _onFilterPillClick);
    el.addEventListener('contextmenu', _onFilterPillRightClick);
  });
}

function _filterPill(kind, color, state, group, isPre = false, inResult = true) {
  const opacity = state === 'blacklist' ? '0.3' : inResult ? '1' : '0.55';
  const strike = state === 'blacklist' ? 'line-through' : 'none';
  const border = state === 'whitelist' ? `2px solid ${color}` : state === 'blacklist' ? '2px solid #ef4444' : `1.5px solid ${color}`;
  const preIcon = isPre ? '<span class="text-[9px]" title="Pre-request filter (affects API query)">⬆</span>' : '';
  return `<button type="button" data-filter-kind="${escapeHtml(kind)}" data-filter-group="${group}" data-filter-state="${state}"
    class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[11px] cursor-pointer transition-all hover:shadow-sm${!inResult ? ' italic' : ''}"
    style="border:${border};opacity:${opacity};text-decoration:${strike}"
    title="Left-click: toggle whitelist/blacklist. Right-click: toggle pre/post filter.${!inResult ? ' (not in current results)' : ''}">
    ${preIcon}<span class="inline-block w-2 h-2 rounded-full" style="background:${color}"></span>${escapeHtml(kind)}</button>`;
}

function _onFilterPillClick(e) {
  e.preventDefault();
  const kind = e.currentTarget.dataset.filterKind;
  const group = e.currentTarget.dataset.filterGroup;
  const state = e.currentTarget.dataset.filterState;
  const [wl, bl] = group === 'node' ? [nodeWhitelist, nodeBlacklist] : [edgeWhitelist, edgeBlacklist];

  if (state === 'default') {
    // Click on default → blacklist (exclude)
    bl.add(kind);
    wl.delete(kind);
  } else if (state === 'blacklist') {
    // Click on blacklisted → whitelist (include only)
    bl.delete(kind);
    wl.add(kind);
  } else {
    // Click on whitelisted → default (remove filter)
    wl.delete(kind);
    bl.delete(kind);
  }
  _applyAndRerender();
}

function _onFilterPillRightClick(e) {
  e.preventDefault();
  const kind = e.currentTarget.dataset.filterKind;
  const group = e.currentTarget.dataset.filterGroup;
  if (group === 'node') {
    // Right-click toggles pre-request mode for node filters
    if (preRequestNodeFilters.has(kind)) {
      preRequestNodeFilters.delete(kind);
    } else {
      preRequestNodeFilters.add(kind);
    }
  } else {
    // For edges, right-click removes filter (reset to default)
    const [wl, bl] = [edgeWhitelist, edgeBlacklist];
    wl.delete(kind);
    bl.delete(kind);
  }
  _applyAndRerender();
}

// Track the last pre-request filter state to detect changes
let _lastPreRequestState = '';

async function _applyAndRerender() {
  // Check if pre-request filters changed – if so, reload from API
  const currentPreState = JSON.stringify([...nodeWhitelist].filter(k => preRequestNodeFilters.has(k)).sort());
  if (currentPreState !== _lastPreRequestState) {
    _lastPreRequestState = currentPreState;
    try {
      const data = await fetchGraph();
      currentNodes = data.nodes || [];
      currentLinks = data.links || [];
    } catch (e) {
      console.warn('Failed to reload graph with pre-request filters:', e);
    }
  }
  applyFilters(currentNodes, currentLinks);
  renderFilterBar();
  renderRelationFilterBar();
  renderLegend();
  await renderGraph();
}

/**
 * Render relation type filter/highlight bar
 */
function renderRelationFilterBar() {
  const bar = document.getElementById('entities-graph-relation-filter-bar');
  if (!bar) return;

  const relTypes = discoverRelationTypes(filteredLinks);
  if (relTypes.size === 0) { bar.innerHTML = ''; return; }

  let html = '<span class="text-[10px] text-slate-400 uppercase mr-1">Relations:</span>';
  for (const rt of relTypes) {
    const active = highlightedRelTypes.has(rt);
    html += `<button type="button" data-rel-type="${escapeHtml(rt)}"
      class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] cursor-pointer transition-all border ${active ? 'border-purple-500 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 font-semibold' : 'border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300'}"
      title="Click to highlight this relation type">${escapeHtml(rt)}</button>`;
  }
  bar.innerHTML = html;

  bar.querySelectorAll('[data-rel-type]').forEach(el => {
    el.addEventListener('click', (e) => {
      const rt = e.currentTarget.dataset.relType;
      if (highlightedRelTypes.has(rt)) highlightedRelTypes.delete(rt);
      else highlightedRelTypes.add(rt);
      renderRelationFilterBar();
      _updateGraphHighlights();
    });
  });
}

function _updateGraphHighlights() {
  if (!graphInstance) return;
  // Re-apply link color with highlights
  graphInstance.linkColor((l) => {
    if (highlightedRelTypes.size > 0) {
      const rt = l.meta?.relation_type || l.kind || '';
      if (highlightedRelTypes.has(rt)) return 'rgba(139,92,246,0.85)';
      return 'rgba(148,163,184,0.08)';
    }
    return EDGE_COLORS[l.kind] || EDGE_COLORS.default;
  });
  graphInstance.linkWidth((l) => {
    if (highlightedRelTypes.size > 0) {
      const rt = l.meta?.relation_type || l.kind || '';
      if (highlightedRelTypes.has(rt)) return linkWidthFromWeight(l.weight) * 2.5;
      return 0.3;
    }
    return linkWidthFromWeight(l.weight);
  });
  graphInstance.nodeColor((n) => {
    if (selectedNodes.has(n.id)) return '#3b82f6'; // selected = blue
    return getNodeColor(n);
  });
}

/**
 * Render legend: only shows kinds present in current filtered graph data
 */
function renderLegend() {
  if (!els.entitiesGraphLegend) return;
  const nodes = filteredNodes.length > 0 ? filteredNodes : currentNodes;
  const links = filteredLinks.length > 0 ? filteredLinks : currentLinks;
  const nodeKinds = discoverNodeKinds(nodes);
  const edgeKinds = discoverEdgeKinds(links);

  const nodeItems = [...nodeKinds].map(k => {
    const c = COLORS[k] || COLORS.unknown;
    return `<span class="inline-flex items-center gap-1"><span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${c}"></span>${escapeHtml(k)}</span>`;
  }).join('');

  const edgeItems = [...edgeKinds].filter(k => k !== 'default').map(k => {
    const c = EDGE_COLORS[k] || EDGE_COLORS.default;
    return `<span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-0.5" style="background:${c}"></span>${escapeHtml(k)}</span>`;
  }).join('');

  els.entitiesGraphLegend.innerHTML = `<div class="flex flex-wrap gap-2 items-center text-[11px]">${nodeItems}${edgeItems ? '<span class="text-slate-400">•</span>' + edgeItems : ''}</div>`;
}

function fmt(val) {
  if (val === null || val === undefined) return '—';
  if (typeof val === 'number') return Number.isFinite(val) ? val.toString() : '—';
  return String(val);
}

function renderIntelDataSummary(data) {
  if (!data || typeof data !== 'object') return '';
  
  const parts = [];
  
  // Render Persons
  if (data.persons && Array.isArray(data.persons) && data.persons.length > 0) {
    const personsList = data.persons.map(p => `
      <div class="text-xs mb-1">
        <b>${escapeHtml(p.name || 'Unknown')}</b>
        ${p.title ? ` - ${escapeHtml(p.title)}` : ''}
        ${p.role ? ` (${escapeHtml(p.role)})` : ''}
      </div>
    `).join('');
    parts.push(`
      <details class="text-xs" open>
        <summary class="cursor-pointer font-semibold text-blue-600">👤 Persons (${data.persons.length})</summary>
        <div class="mt-1 ml-2 space-y-1">${personsList}</div>
      </details>
    `);
  }
  
  // Render Locations
  if (data.locations && Array.isArray(data.locations) && data.locations.length > 0) {
    const locationsList = data.locations.map(l => `
      <div class="text-xs mb-1">
        📍 ${escapeHtml(l.city || l.address || l.country || 'Unknown')}
        ${l.type ? ` (${escapeHtml(l.type)})` : ''}
      </div>
    `).join('');
    parts.push(`
      <details class="text-xs" open>
        <summary class="cursor-pointer font-semibold text-purple-600">📍 Locations (${data.locations.length})</summary>
        <div class="mt-1 ml-2 space-y-1">${locationsList}</div>
      </details>
    `);
  }
  
  // Render Products
  if (data.products && Array.isArray(data.products) && data.products.length > 0) {
    const productsList = data.products.map(p => `
      <div class="text-xs mb-1">
        <b>${escapeHtml(p.name || 'Unknown')}</b>
        ${p.status ? ` - ${escapeHtml(p.status)}` : ''}
        ${p.description ? `<div class="text-slate-500">${escapeHtml(p.description)}</div>` : ''}
      </div>
    `).join('');
    parts.push(`
      <details class="text-xs" open>
        <summary class="cursor-pointer font-semibold text-orange-600">📦 Products (${data.products.length})</summary>
        <div class="mt-1 ml-2 space-y-1">${productsList}</div>
      </details>
    `);
  }
  
  // Render Basic Info
  if (data.basic_info && typeof data.basic_info === 'object') {
    const info = data.basic_info;
    parts.push(`
      <details class="text-xs">
        <summary class="cursor-pointer font-semibold">ℹ️ Basic Info</summary>
        <div class="mt-1 ml-2 space-y-1">
          ${info.official_name ? `<div>Name: <b>${escapeHtml(info.official_name)}</b></div>` : ''}
          ${info.industry ? `<div>Industry: ${escapeHtml(info.industry)}</div>` : ''}
          ${info.ticker ? `<div>Ticker: ${escapeHtml(info.ticker)}</div>` : ''}
          ${info.founded ? `<div>Founded: ${escapeHtml(info.founded)}</div>` : ''}
          ${info.website ? `<div>Website: <a href="${escapeHtml(info.website)}" class="text-blue-600 underline" target="_blank">${escapeHtml(info.website)}</a></div>` : ''}
        </div>
      </details>
    `);
  }
  
  return parts.length > 0 ? `<div class="space-y-2 my-2">${parts.join('')}</div>` : '';
}

function metaTableWithLinks(meta) {
  if (!meta || typeof meta !== 'object' || !Object.keys(meta).length) {
    return '<div class="text-xs text-slate-500">No metadata</div>';
  }
  
  // Skip internal ID fields
  const skipKeys = ['source_id', 'target_id', 'page_id', 'entity_id', 'intel_id', 'seed_id', 'media_id'];
  const filteredMeta = Object.fromEntries(
    Object.entries(meta).filter(([k]) => !skipKeys.includes(k))
  );
  
  if (!Object.keys(filteredMeta).length) {
    return '<div class="text-xs text-slate-500">No metadata</div>';
  }
  
  return renderKeyValTable(
    Object.fromEntries(
      Object.entries(filteredMeta).map(([k, v]) => {
        const label = k.replace(/_/g, ' ');
        if (typeof v === 'string' && v.startsWith('http')) {
          const safeUrl = escapeHtml(v);
          return [
            escapeHtml(label),
            `<a class="text-blue-600 underline" href="${safeUrl}" target="_blank" rel="noreferrer">${safeUrl}</a>`,
          ];
        }
        // Handle objects
        if (typeof v === 'object' && v !== null) {
          return [escapeHtml(label), formatMetaValue(v)];
        }
        return [escapeHtml(label), escapeHtml(fmt(v))];
      })
    )
  );
}

function renderDetailBody(node) {
  const meta = node.meta || {};

  const pagePreview =
    node.type === 'page'
      ? `
    <div class="space-y-2">
      <div class="text-xs uppercase text-slate-500">Page</div>
      <div class="text-xs">${pill(meta.page_type || 'page')} ${
          meta.entity_type ? pill(meta.entity_type) : ''
        } ${meta.score ? pill(`score ${meta.score}`) : ''}</div>
      ${meta.last_status ? `<div class="text-xs text-slate-500">Last status: ${escapeHtml(meta.last_status)}</div>` : ''}
      ${meta.last_fetch_at ? `<div class="text-xs text-slate-500">Fetched: ${escapeHtml(meta.last_fetch_at)}</div>` : ''}
      ${meta.text_length ? `<div class="text-xs text-slate-500">Text length: ${escapeHtml(meta.text_length)}</div>` : ''}
      ${meta.id ? `<div class="text-xs text-slate-500">UUID: ${escapeHtml(meta.id)}</div>` : ''}
      <div class="text-xs"><a class="text-blue-600 underline" href="${escapeHtml(
        meta.source_url || node.id
      )}" target="_blank" rel="noreferrer">Open page</a></div>
    </div>`
      : '';

  const imagePreview =
    node.type === 'image'
      ? `
    <div class="space-y-2">
      <div class="text-xs uppercase text-slate-500">Image</div>
      <div class="rounded border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900">
        <img src="${escapeHtml(node.label)}" alt="${escapeHtml(meta.alt || node.label)}" class="max-h-56 w-full object-contain">
      </div>
      <div class="text-[11px] text-slate-500">${escapeHtml(meta.alt || '')}</div>
      <div class="text-[11px] text-slate-500">Source: ${escapeHtml(meta.source || 'unknown')}</div>
      <div class="text-xs"><a class="text-blue-600 underline" href="${escapeHtml(
        meta.source_url || node.label
      )}" target="_blank" rel="noreferrer">Open image</a></div>
    </div>`
      : '';

  const intelPreview =
    node.type === 'intel'
      ? `
    <div class="space-y-2">
      <div class="text-xs uppercase text-slate-500">Intel</div>
      ${meta.entity_name ? `<div class="text-xs">Entity: <b>${escapeHtml(meta.entity_name)}</b></div>` : ''}
      ${meta.entity ? `<div class="text-xs">Entity: <b>${escapeHtml(meta.entity)}</b></div>` : ''}
      ${meta.entity_type ? `<div class="text-xs">Type: <b>${escapeHtml(meta.entity_type)}</b></div>` : ''}
      ${meta.confidence ? `<div class="text-xs">Confidence: <b>${escapeHtml(meta.confidence)}</b></div>` : ''}
      ${meta.created_at ? `<div class="text-xs text-slate-500">Created: ${escapeHtml(meta.created_at)}</div>` : ''}
      ${renderIntelDataSummary(meta.data)}
      ${meta.data ? `<details class="text-xs"><summary class="cursor-pointer font-semibold">Raw Intel Data</summary><pre class="mt-1 p-2 bg-slate-900 text-slate-100 rounded text-xs whitespace-pre-wrap">${escapeHtml(JSON.stringify(meta.data, null, 2))}</pre></details>` : ''}
    </div>`
      : '';

  const entityBadge =
    node.type === 'entity' || node.meta?.entity_kind || node.kind
      ? `<div class="text-xs uppercase text-slate-500">Entity</div>
         <div class="flex flex-wrap gap-1 text-xs">
           ${pill(node.kind || node.meta?.entity_kind || node.type || 'entity')}
           ${node.score ? pill(`score ${node.score}`) : ''}
           ${node.count ? pill(`count ${node.count}`) : ''}
         </div>`
      : '';

  return `
      <div class="space-y-3">
        ${entityBadge}
        ${pagePreview}
        ${imagePreview}
        ${intelPreview}
        <div class="space-y-1">
          <div class="text-xs uppercase text-slate-500">Meta</div>
          ${metaTableWithLinks(meta)}
        </div>
      </div>
    `;
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
    .filter((l) => l.source?.id === node.id || l.target?.id === node.id || l.source === node.id || l.target === node.id)
    .map((l) => {
      const other = l.source?.id === node.id || l.source === node.id ? l.target : l.source;
      return other ? { node: other.id || other, weight: l.weight, kind: l.kind, meta: l.meta || {} } : null;
    })
    .filter(Boolean);

  // Check if it's a deletable entity (not a page/image/link/seed node)
  const isEntity = node.type && !['page', 'image', 'link', 'seed'].includes(node.type);

  els.entitiesGraphDetails.innerHTML = `
    <div class="flex items-center justify-between">
      <div>
        <div class="text-xs uppercase tracking-wide text-slate-500">Details</div>
        <div class="text-sm font-semibold break-all">${escapeHtml(node.label || node.id)}</div>
        <div class="text-xs text-slate-500">
          ${escapeHtml(node.kind || node.type || 'unknown')} • score ${escapeHtml(fmt(node.score))} • count ${escapeHtml(fmt(node.count))}
        </div>
      </div>
      <div class="flex items-center gap-2">
        ${
          node.type === 'page' || node.type === 'image'
            ? `<a class="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs font-semibold text-blue-600 dark:text-blue-200" href="${escapeHtml(
                node.meta?.source_url || node.label || node.id
              )}" target="_blank" rel="noreferrer">Open</a>`
            : ''
        }
        <button
          type="button"
          data-action="expand-node"
          data-node-id="${escapeHtml(node.id)}"
          data-node-label="${escapeHtml(node.label || node.id)}"
          data-node-type="${escapeHtml(node.kind || node.type || 'unknown')}"
          class="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs font-semibold text-slate-700 dark:text-slate-100 hover:border-brand-400 dark:hover:border-brand-500"
        >
          Expand
        </button>
        ${isEntity && _isValidUUID(node.id) ? `<button data-delete-entity="${escapeHtml(node.id)}" class="inline-flex items-center gap-1 rounded-md border border-red-200 dark:border-red-800 px-2 py-1 text-xs font-semibold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 transition" title="Delete entity">🗑</button>` : ''}
      </div>
    </div>

    ${renderDetailBody(node)}

    <div class="mt-3 text-xs uppercase text-slate-400">Connected (${connections.length}):</div>
    <ul class="list-disc list-inside text-xs text-slate-600 dark:text-slate-200 space-y-1 max-h-56 overflow-auto">
      ${
        connections.length
          ? connections
              .map(
                ({ node: nid, weight, kind, meta }) =>
                  `<li><span class="font-semibold">${escapeHtml(nid)}</span> <span class="text-slate-500">[${escapeHtml(
                    kind || 'link'
                  )}]</span>${weight ? `<span class="text-slate-400"> w:${escapeHtml(fmt(weight))}</span>` : ''}${
                    meta && Object.keys(meta).length
                      ? `<div class="text-slate-500">${Object.entries(meta)
                          .map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(fmt(v))}`)
                          .join(' • ')}</div>`
                      : ''
                  }</li>`
              )
              .join('')
          : '<li>None</li>'
      }
    </ul>
  `;

  // Wire delete button in the side panel
  _wireDeleteButtons(node);
}

async function fetchNodeDetail(node) {
  try {
    const base = val('base-url') || '';
    const url = `${base}/api/entities/graph/node?id=${encodeURIComponent(node.id)}`;
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
    });
    if (!res.ok) throw new Error(`Detail fetch failed (${res.status})`);
    return await res.json();
  } catch (e) {
    console.warn(e);
    return null;
  }
}

/**
 * Format a metadata value for human-readable display
 */
function formatMetaValue(value, depth = 0) {
  if (value === null || value === undefined) return '—';
  // Limit recursion depth to prevent performance issues
  if (depth > 3) return '…';
  if (typeof value === 'object') {
    // Format nested objects
    if (Array.isArray(value)) {
      // Limit array length for performance
      const maxItems = 10;
      const items = value.slice(0, maxItems).map(v => formatMetaValue(v, depth + 1));
      return items.join(', ') + (value.length > maxItems ? ` (+${value.length - maxItems} more)` : '');
    }
    // Extract meaningful fields from object
    const meaningful = ['name', 'title', 'label', 'type', 'role', 'value', 'description'];
    for (const key of meaningful) {
      if (value[key]) return escapeHtml(String(value[key]));
    }
    // Fallback: show first few key-value pairs
    const entries = Object.entries(value).slice(0, 3);
    if (entries.length === 0) return '—';
    return entries.map(([k, v]) => `${k}: ${formatMetaValue(v, depth + 1)}`).join(', ');
  }
  return escapeHtml(String(value));
}

/**
 * Lookup a node's label by ID from the current graph data
 */
function lookupNodeLabel(nodeId) {
  if (!nodeId) return null;
  // Handle both string IDs and object references with id property
  const searchId = typeof nodeId === 'object' && nodeId !== null ? nodeId.id : nodeId;
  if (!searchId) return null;
  const node = filteredNodes.find(n => n.id === searchId);
  return node?.label || node?.meta?.name || null;
}

/**
 * Format a connection for human-readable display
 */
function formatConnection(conn) {
  const nodeLabel = lookupNodeLabel(conn.id) || conn.id;
  const kindLabel = formatRelationType(conn.kind);
  const weight = conn.weight ? `<span class="text-slate-400 ml-1">weight: ${conn.weight}</span>` : '';
  
  // Format meta, excluding internal IDs
  const metaDisplay = conn.meta && Object.keys(conn.meta).length
    ? formatConnectionMeta(conn.meta)
    : '';
  
  return `
    <li class="py-1 border-b border-slate-100 dark:border-slate-800 last:border-0">
      <div class="flex items-center gap-2">
        <span class="font-medium text-blue-600 dark:text-blue-400">${escapeHtml(nodeLabel)}</span>
        <span class="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 rounded text-[10px] text-slate-600 dark:text-slate-400">${escapeHtml(kindLabel)}</span>
        ${weight}
      </div>
      ${metaDisplay}
    </li>
  `;
}

/**
 * Format relation type for human display
 */
function formatRelationType(kind) {
  if (!kind) return 'link';
  return kind.replace(/_/g, ' ').replace(/-/g, ' ');
}

/**
 * Format connection metadata, excluding internal IDs
 */
function formatConnectionMeta(meta) {
  const skipKeys = ['source_id', 'target_id', 'metadata'];
  const displayEntries = Object.entries(meta)
    .filter(([k]) => !skipKeys.includes(k))
    .filter(([, v]) => v !== null && v !== undefined && v !== '');
  
  if (displayEntries.length === 0) return '';
  
  const formatted = displayEntries.map(([k, v]) => {
    const label = k.replace(/_/g, ' ');
    const value = formatMetaValue(v);
    return `<span class="inline-block mr-2">${escapeHtml(label)}: <b>${value}</b></span>`;
  }).join('');
  
  return `<div class="text-[11px] text-slate-500 mt-0.5">${formatted}</div>`;
}

function renderNodeModalContent(node, links, detail) {
  const meta = detail?.meta || node.meta || {};
  const connections = links
    .filter((l) => l.source?.id === node.id || l.target?.id === node.id || l.source === node.id || l.target === node.id)
    .map((l) => {
      const other = l.source?.id === node.id || l.source === node.id ? l.target : l.source;
      return other ? { id: other.id || other, kind: l.kind, weight: l.weight, meta: l.meta || {} } : null;
    })
    .filter(Boolean);

  const metaTable = metaTableWithLinks(meta);
  const connList = connections.length
    ? `<ul class="text-xs space-y-0">${connections.map(c => formatConnection(c)).join('')}</ul>`
    : `<div class="text-xs text-slate-500">No connections</div>`;

  if (node.type === 'page' || detail?.type === 'page') {
    const content = detail?.content || {};
    const metaMerged = { ...meta, ...(detail?.page || {}) };
    const sd = metaMerged.structured_data
      ? collapsible(
          'Structured data',
          `<pre class="p-2 bg-slate-900 text-white rounded text-xs whitespace-pre-wrap">${escapeHtml(
            JSON.stringify(metaMerged.structured_data, null, 2)
          )}</pre>`
        )
      : '';
    const previewText = content.text || metaMerged.content_preview || '';
    const preview = previewText
      ? `<div class="bg-slate-50 dark:bg-slate-900 p-2 rounded text-xs font-mono max-h-64 overflow-y-auto whitespace-pre-wrap">${escapeHtml(
          previewText.slice(0, 5000)
        )}${previewText.length > 5000 ? '…' : ''}</div>`
      : '';
    return `
      <div class="space-y-3">
        <div class="text-xs uppercase text-slate-500">Page</div>
        <div class="text-sm font-semibold break-all">${escapeHtml(node.label || node.id)}</div>
        <div class="text-xs text-slate-500">${pill(metaMerged.page_type || 'page')} ${
      metaMerged.entity_type ? pill(metaMerged.entity_type) : ''
    } ${metaMerged.score ? pill('score ' + metaMerged.score) : ''}</div>
        ${metaMerged.last_fetch_at ? `<div class="text-xs text-slate-500">Fetched: ${escapeHtml(metaMerged.last_fetch_at)}</div>` : ''}
        ${metaMerged.text_length ? `<div class="text-xs text-slate-500">Text length: ${escapeHtml(metaMerged.text_length)}</div>` : ''}
        ${metaMerged.id ? `<div class="text-xs text-slate-500">UUID: ${escapeHtml(metaMerged.id)}</div>` : ''}
        <div class="text-xs"><a class="text-blue-600 underline" href="${escapeHtml(
          metaMerged.source_url || node.label || node.id
        )}" target="_blank" rel="noreferrer">Open page</a></div>
        ${preview}
        ${sd}
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Meta</div>
          ${metaTableWithLinks(metaMerged)}
        </div>
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Connections (${connections.length})</div>
          ${connList}
        </div>
      </div>
    `;
  }

  if (node.type === 'image' || detail?.type === 'image') {
    return `
      <div class="space-y-3">
        <div class="text-xs uppercase text-slate-500">Image</div>
        <img src="${escapeHtml(node.label)}" alt="${escapeHtml(meta.alt || node.label)}" class="w-full max-h-72 object-contain rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
        <div class="text-xs text-slate-500">${escapeHtml(meta.alt || '')}</div>
        <div class="text-xs text-slate-500">Source: ${escapeHtml(meta.source || 'unknown')}</div>
        ${
          meta.page
            ? `<div class="text-xs">Found on: <a class="text-blue-600 underline" href="${escapeHtml(
                meta.page
              )}" target="_blank" rel="noreferrer">${escapeHtml(meta.page)}</a></div>`
            : ''
        }
        <div class="text-xs"><a class="text-blue-600 underline" href="${escapeHtml(
          meta.source_url || node.label
        )}" target="_blank" rel="noreferrer">Open image</a></div>
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Meta</div>
          ${metaTable}
        </div>
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Connections (${connections.length})</div>
          ${connList}
        </div>
      </div>
    `;
  }

  if (node.type === 'intel' || detail?.type === 'intel') {
    const payload = detail?.payload || detail?.data || meta.data || meta.payload_preview;
    const payloadBlock = payload
      ? `<pre class="p-2 bg-slate-900 text-white rounded text-xs whitespace-pre-wrap max-h-64 overflow-y-auto">${escapeHtml(
          JSON.stringify(payload, null, 2)
        )}</pre>`
      : '<div class="text-xs text-slate-500">No payload available</div>';
    return `
      <div class="space-y-3">
        <div class="text-xs uppercase text-slate-500">Intel</div>
        <div class="text-sm font-semibold">${escapeHtml(node.label || node.id)}</div>
        ${meta.entity_name ? `<div class="text-xs">Entity: <b>${escapeHtml(meta.entity_name)}</b></div>` : ''}
        ${meta.entity ? `<div class="text-xs">Entity: <b>${escapeHtml(meta.entity)}</b></div>` : ''}
        ${meta.entity_type ? `<div class="text-xs">Type: <b>${escapeHtml(meta.entity_type)}</b></div>` : ''}
        ${meta.confidence ? `<div class="text-xs">Confidence: <b>${escapeHtml(meta.confidence)}</b></div>` : ''}
        ${meta.created_at ? `<div class="text-xs text-slate-500">Created: ${escapeHtml(meta.created_at)}</div>` : ''}
        ${
          meta.source_url
            ? `<div class="text-xs"><a class="text-blue-600 underline" href="${escapeHtml(
                meta.source_url
              )}" target="_blank" rel="noreferrer">Source</a></div>`
            : ''
        }
        ${payloadBlock}
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Meta</div>
          ${metaTable}
        </div>
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Connections (${connections.length})</div>
          ${connList}
        </div>
      </div>
    `;
  }

  if (node.type === 'seed' || detail?.type === 'seed') {
    return `
      <div class="space-y-3">
        <div class="text-xs uppercase text-slate-500">Seed</div>
        <div class="text-sm font-semibold break-all">${escapeHtml(node.label || node.id)}</div>
        ${meta.entity_type ? `<div class="text-xs">Entity Type: <b>${escapeHtml(meta.entity_type)}</b></div>` : ''}
        ${meta.source ? `<div class="text-xs text-slate-500">Source: ${escapeHtml(meta.source)}</div>` : ''}
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Meta</div>
          ${metaTable}
        </div>
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Connections (${connections.length})</div>
          ${connList}
        </div>
      </div>
    `;
  }

  if (node.type === 'media' || detail?.type === 'media') {
    const mediaUrl = meta.url || node.label || '';
    const mediaType = meta.media_type || 'media';
    const hasValidUrl = mediaUrl && (mediaUrl.startsWith('http://') || mediaUrl.startsWith('https://'));
    const mediaPreview = (mediaType === 'image' && hasValidUrl)
      ? `<img src="${escapeHtml(mediaUrl)}" alt="Media" class="w-full max-h-72 object-contain rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">`
      : '';
    
    return `
      <div class="space-y-3">
        <div class="text-xs uppercase text-slate-500">Media (${escapeHtml(mediaType)})</div>
        <div class="text-sm font-semibold break-all">${escapeHtml(node.label || node.id)}</div>
        ${meta.processed ? `<div class="text-xs text-green-600">✓ Processed</div>` : `<div class="text-xs text-slate-500">⏳ Not processed</div>`}
        ${meta.extracted_text ? `<div class="text-xs text-slate-600">Extracted text: ${escapeHtml(meta.extracted_text)}</div>` : ''}
        ${mediaPreview}
        ${hasValidUrl ? `<div class="text-xs"><a class="text-blue-600 underline" href="${escapeHtml(mediaUrl)}" target="_blank" rel="noreferrer">Open media</a></div>` : ''}
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Meta</div>
          ${metaTable}
        </div>
        <div>
          <div class="text-xs uppercase text-slate-500 mb-1">Connections (${connections.length})</div>
          ${connList}
        </div>
      </div>
    `;
  }

  // Render relationships from API if available
  const rels = detail?.relationships || [];
  const isEntityNode = detail?.type && !['page', 'image', 'intel', 'seed', 'media', 'link'].includes(detail.type);
  const relationshipsSection = rels.length > 0
    ? `
      <div>
        <div class="flex items-center justify-between mb-1">
          <div class="text-xs uppercase text-slate-500">Relationships (${rels.length})</div>
          ${isEntityNode && _isValidUUID(node.id) ? `<button id="modal-add-relation-toggle" type="button" class="text-[10px] px-1.5 py-0.5 rounded bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-800 transition font-semibold">+ Add</button>` : ''}
        </div>
        <input id="modal-relation-search" type="text" placeholder="Filter relations…" class="w-full mb-1 rounded border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400">
        <ul id="modal-relation-list" class="text-xs space-y-1 max-h-48 overflow-y-auto">
          ${rels.map(r => {
            const direction = r.direction === 'outgoing' ? '→' : '←';
            const otherName = r.direction === 'outgoing' ? (r.target_name || 'Unknown') : (r.source_name || 'Unknown');
            const otherKind = r.direction === 'outgoing' ? (r.target_kind || 'entity') : (r.source_kind || 'entity');
            const other = `<b class="text-blue-600">${escapeHtml(otherName)}</b> <span class="text-slate-400">(${escapeHtml(otherKind)})</span>`;
            const relType = escapeHtml(formatRelationType(r.type || 'related'));
            const confidence = r.confidence ? ` <span class="text-slate-400">confidence: ${r.confidence}</span>` : '';
            const deleteRelBtn = r.id
              ? `<button data-delete-rel="${escapeHtml(r.id)}" data-entity-id="${escapeHtml(node.id)}" class="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-800 transition" title="Delete relationship">✕</button>`
              : '';
            return `<li class="py-1 border-b border-slate-100 dark:border-slate-800 last:border-0 flex items-center gap-1" data-rel-name="${escapeHtml(otherName.toLowerCase())}" data-rel-type="${escapeHtml((r.type || '').toLowerCase())}">${direction} <span class="px-1 py-0.5 bg-slate-100 dark:bg-slate-800 rounded text-[10px]">${relType}</span> ${other}${confidence}${deleteRelBtn}</li>`;
          }).join('')}
        </ul>
      </div>
    `
    : (isEntityNode && _isValidUUID(node.id)
      ? `<div>
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs uppercase text-slate-500">Relationships (0)</div>
            <button id="modal-add-relation-toggle" type="button" class="text-[10px] px-1.5 py-0.5 rounded bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-800 transition font-semibold">+ Add</button>
          </div>
          <div class="text-xs text-slate-500">No relationships</div>
        </div>`
      : '');

  // Inline add-relation form for the modal
  const addRelationForm = isEntityNode && _isValidUUID(node.id)
    ? `<div id="modal-add-relation-section" class="hidden mt-1 p-2 rounded border border-green-200 dark:border-green-800 bg-green-50/60 dark:bg-green-900/20 space-y-2 text-xs">
        <div class="font-semibold text-green-700 dark:text-green-400">Add Relation from "${escapeHtml(node.label || node.id)}"</div>
        <input id="modal-add-relation-target" type="text" placeholder="Search target entity…" class="w-full rounded border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-xs">
        <div id="modal-add-relation-results" class="max-h-24 overflow-y-auto space-y-0.5"></div>
        <input id="modal-add-relation-type" type="text" placeholder="Relation type (e.g. works_at, owns)" list="modal-add-relation-type-list" class="w-full rounded border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-xs">
        <datalist id="modal-add-relation-type-list">
          ${[...allDbEdgeKinds].map(k => `<option value="${escapeHtml(k)}">`).join('')}
        </datalist>
        <div class="flex gap-2">
          <button id="modal-add-relation-save" type="button" class="px-3 py-1 rounded bg-green-600 text-white text-xs font-semibold hover:bg-green-500 disabled:opacity-40" disabled>Save Relation</button>
          <button id="modal-add-relation-cancel" type="button" class="px-3 py-1 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold hover:bg-slate-300">Cancel</button>
        </div>
        <div id="modal-add-relation-status" class="text-[10px] text-slate-400 italic"></div>
      </div>`
    : '';

  // Delete entity button (only for entities with a valid UUID id)
  const deleteEntityBtn = isEntityNode && _isValidUUID(node.id)
    ? `<div class="mt-3 pt-3 border-t border-slate-200 dark:border-slate-800">
        <button data-delete-entity="${escapeHtml(node.id)}" class="px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-semibold hover:bg-red-500 transition">Delete Entity</button>
       </div>`
    : '';

  // Get kind from meta or node type (must be before editForm which references it)
  const kind = meta.kind || node.type || 'entity';
  const kindColor = COLORS[kind] || COLORS.entity;

  // Inline edit form for entity nodes
  const kindOptions = [...allDbNodeKinds, 'person', 'org', 'location', 'product', 'event', 'entity', 'unknown']
    .filter((v, i, a) => a.indexOf(v) === i);

  const editForm = isEntityNode && _isValidUUID(node.id)
    ? `<div id="entity-edit-section" class="hidden mt-2 p-2 rounded border border-blue-200 dark:border-blue-800 bg-blue-50/60 dark:bg-blue-900/20 space-y-2">
        <label class="block text-xs text-slate-500">Name
          <input id="entity-edit-name" type="text" value="${escapeHtml(node.label || meta.name || '')}" class="mt-0.5 w-full rounded border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-sm">
        </label>
        <label class="block text-xs text-slate-500">Kind
          <select id="entity-edit-kind" class="mt-0.5 w-full rounded border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-sm">
            ${kindOptions.map(k => `<option value="${escapeHtml(k)}"${k === kind ? ' selected' : ''}>${escapeHtml(k)}</option>`).join('')}
          </select>
        </label>
        <div class="flex gap-2">
          <button id="entity-edit-save" type="button" class="px-3 py-1 rounded bg-blue-600 text-white text-xs font-semibold hover:bg-blue-500">Save</button>
          <button id="entity-edit-cancel" type="button" class="px-3 py-1 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold hover:bg-slate-300">Cancel</button>
        </div>
      </div>`
    : '';

  const editButton = isEntityNode && _isValidUUID(node.id)
    ? `<button id="entity-edit-toggle" type="button" class="px-2 py-1 rounded border border-blue-200 dark:border-blue-800 text-blue-600 dark:text-blue-400 text-xs font-semibold hover:bg-blue-50 dark:hover:bg-blue-900/30">✏ Edit</button>`
    : '';

  return `
    <div class="space-y-3">
      <div class="flex items-center gap-2">
        <span class="inline-block w-3 h-3 rounded-full" style="background:${kindColor}"></span>
        <span class="text-xs uppercase text-slate-500">${escapeHtml(kind)}</span>
        ${editButton}
      </div>
      <div class="text-lg font-semibold break-all">${escapeHtml(node.label || meta.name || node.id)}</div>
      ${editForm}
      ${meta.last_seen ? `<div class="text-xs text-slate-500">Last seen: ${escapeHtml(meta.last_seen)}</div>` : ''}
      ${node.score ? `<div class="text-xs"><span class="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900 rounded">score: ${escapeHtml(fmt(node.score))}</span></div>` : ''}
      ${node.count ? `<div class="text-xs"><span class="px-1.5 py-0.5 bg-green-100 dark:bg-green-900 rounded">mentions: ${escapeHtml(fmt(node.count))}</span></div>` : ''}
      <div>
        <div class="text-xs uppercase text-slate-500 mb-1">Details</div>
        ${metaTable}
      </div>
      ${relationshipsSection}
      ${addRelationForm}
      <div>
        <div class="text-xs uppercase text-slate-500 mb-1">Graph Connections (${connections.length})</div>
        ${connList}
      </div>
      ${deleteEntityBtn}
    </div>
  `;
}

function openNodeModal(node) {
  if (!node) return;
  // Prevent opening multiple modals for the same node
  if (activeModalNodeId === node.id) return;
  
  activeModalNodeId = node.id;
  activeModalId = showModal({
    title: node.label || node.id || 'Node detail',
    size: 'lg',
    content: `<div class="text-xs text-slate-500">Loading…</div>`,
    onClose: () => {
      // Clear active modal node when modal is closed
      activeModalNodeId = null;
      activeModalId = null;
    }
  });
  
  fetchNodeDetail(node).then((detail) => {
    // Only update if this is still the active modal node
    if (activeModalNodeId !== node.id || !activeModalId) return;
    const content = renderNodeModalContent(node, filteredLinks, detail || {});
    // Update the existing modal instead of creating a new one
    updateModal(activeModalId, {
      title: node.label || node.id || 'Node detail',
      content
    });
    // Wire delete buttons inside the modal
    _wireDeleteButtons(node);
  });
}

// ------------------------------------------------------------------
// Delete helpers – called from modal buttons
// ------------------------------------------------------------------
async function _deleteEntity(entityId) {
  if (!confirm('Delete this entity and all its relationships? This cannot be undone.')) return;
  try {
    const base = val('base-url') || '';
    const res = await fetch(`${base}/api/entities/${encodeURIComponent(entityId)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
    });
    if (!res.ok) {
      const err = await res.text();
      alert('Delete failed: ' + err);
      return;
    }
    // Close modal and reload graph
    if (activeModalId) {
      const overlay = document.getElementById(activeModalId);
      if (overlay) overlay.remove();
      activeModalNodeId = null;
      activeModalId = null;
    }
    // Reload graph if button exists
    const loadBtn = document.getElementById('entities-graph-load');
    if (loadBtn) loadBtn.click();
  } catch (e) {
    alert('Delete failed: ' + e.message);
  }
}

async function _deleteRelationship(entityId, relId, buttonEl) {
  if (!confirm('Delete this relationship?')) return;
  try {
    const base = val('base-url') || '';
    const res = await fetch(
      `${base}/api/entities/${encodeURIComponent(entityId)}/relationships/${encodeURIComponent(relId)}`,
      {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
      }
    );
    if (!res.ok) {
      const err = await res.text();
      alert('Delete failed: ' + err);
      return;
    }
    // Remove the parent <li> from the DOM
    const li = buttonEl.closest('li');
    if (li) li.remove();
  } catch (e) {
    alert('Delete failed: ' + e.message);
  }
}

function _wireDeleteButtons(node) {
  // Short delay to ensure the modal DOM has been rendered before binding handlers
  setTimeout(() => {
    // Delete entity buttons
    document.querySelectorAll('[data-delete-entity]').forEach(btn => {
      btn.onclick = () => _deleteEntity(btn.dataset.deleteEntity);
    });
    // Delete relationship buttons
    document.querySelectorAll('[data-delete-rel]').forEach(btn => {
      btn.onclick = () => _deleteRelationship(btn.dataset.entityId, btn.dataset.deleteRel, btn);
    });
    // Inline edit toggle
    const editToggle = document.getElementById('entity-edit-toggle');
    const editSection = document.getElementById('entity-edit-section');
    if (editToggle && editSection) {
      editToggle.onclick = () => editSection.classList.toggle('hidden');
      const cancelBtn = document.getElementById('entity-edit-cancel');
      if (cancelBtn) cancelBtn.onclick = () => editSection.classList.add('hidden');
      const saveBtn = document.getElementById('entity-edit-save');
      if (saveBtn) saveBtn.onclick = () => _saveEntityEdit(node);
    }
    // Relation search filter
    const relSearch = document.getElementById('modal-relation-search');
    if (relSearch) {
      relSearch.oninput = () => {
        const q = relSearch.value.toLowerCase().trim();
        document.querySelectorAll('#modal-relation-list li').forEach(li => {
          const name = li.dataset.relName || '';
          const type = li.dataset.relType || '';
          li.style.display = (!q || name.includes(q) || type.includes(q)) ? '' : 'none';
        });
      };
    }
    // Add relation toggle & form in modal
    _wireModalAddRelation(node);
  }, 50);
}

async function _saveEntityEdit(node) {
  const nameInput = document.getElementById('entity-edit-name');
  const kindSelect = document.getElementById('entity-edit-kind');
  if (!nameInput || !kindSelect) return;

  const newName = nameInput.value.trim();
  const newKind = kindSelect.value;
  if (!newName) { alert('Name cannot be empty'); return; }

  const base = val('base-url') || '';
  try {
    const res = await fetch(`${base}/api/entities/${encodeURIComponent(node.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
      body: JSON.stringify({ name: newName, kind: newKind }),
    });
    if (!res.ok) {
      const err = await res.text();
      alert('Update failed: ' + err);
      return;
    }
    // Update local graph data immediately
    const updateNode = (n) => {
      if (n.id === node.id) {
        n.label = newName;
        n.kind = newKind;
        n.type = newKind;
        if (n.meta) { n.meta.name = newName; n.meta.kind = newKind; }
      }
    };
    currentNodes.forEach(updateNode);
    filteredNodes.forEach(updateNode);

    // Close edit section and re-render
    const editSection = document.getElementById('entity-edit-section');
    if (editSection) editSection.classList.add('hidden');
    _updateGraphHighlights();
    if (graphInstance) graphInstance.nodeColor(graphInstance.nodeColor());
    setStatus(`Updated "${newName}"`);
  } catch (e) {
    alert('Update failed: ' + e.message);
  }
}

// --- Modal add-relation wiring ---
let _modalAddRelationTargetId = null;

function _wireModalAddRelation(node) {
  const toggleBtn = document.getElementById('modal-add-relation-toggle');
  const section = document.getElementById('modal-add-relation-section');
  if (!toggleBtn || !section) return;

  toggleBtn.onclick = () => section.classList.toggle('hidden');

  const cancelBtn = document.getElementById('modal-add-relation-cancel');
  if (cancelBtn) cancelBtn.onclick = () => { section.classList.add('hidden'); _modalAddRelationTargetId = null; };

  const targetInput = document.getElementById('modal-add-relation-target');
  const resultsDiv = document.getElementById('modal-add-relation-results');
  const typeInput = document.getElementById('modal-add-relation-type');
  const saveBtn = document.getElementById('modal-add-relation-save');

  function updateSaveState() {
    if (saveBtn) saveBtn.disabled = !_modalAddRelationTargetId || !(typeInput?.value?.trim());
  }

  if (typeInput) typeInput.oninput = updateSaveState;

  let searchTimeout = null;
  if (targetInput && resultsDiv) {
    targetInput.oninput = () => {
      clearTimeout(searchTimeout);
      const q = targetInput.value.trim().toLowerCase();
      if (q.length < 2) { resultsDiv.innerHTML = ''; _modalAddRelationTargetId = null; updateSaveState(); return; }
      searchTimeout = setTimeout(() => {
        const matches = filteredNodes
          .filter(n => n.id !== node.id && (n.label || '').toLowerCase().includes(q))
          .slice(0, 8);
        resultsDiv.innerHTML = matches.map(n =>
          `<div class="px-2 py-1 rounded cursor-pointer hover:bg-green-100 dark:hover:bg-green-800/30 text-xs" data-target-id="${escapeHtml(n.id)}">${escapeHtml(n.label || n.id)} <span class="text-slate-400">(${escapeHtml(n.type || 'entity')})</span></div>`
        ).join('') || '<div class="text-[10px] text-slate-400 px-2">No matches in graph</div>';
        resultsDiv.querySelectorAll('[data-target-id]').forEach(el => {
          el.onclick = () => {
            _modalAddRelationTargetId = el.dataset.targetId;
            targetInput.value = el.textContent.trim();
            resultsDiv.innerHTML = '';
            updateSaveState();
          };
        });
      }, 200);
    };
  }

  if (saveBtn) saveBtn.onclick = () => _saveModalRelation(node);
}

async function _saveModalRelation(sourceNode) {
  const typeInput = document.getElementById('modal-add-relation-type');
  const statusDiv = document.getElementById('modal-add-relation-status');
  const relType = typeInput?.value?.trim();
  if (!_modalAddRelationTargetId || !relType) return;

  const base = val('base-url') || '';
  try {
    const res = await fetch(`${base}/api/relationships/record`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
      body: JSON.stringify({
        source_id: sourceNode.id,
        target_id: _modalAddRelationTargetId,
        relation_type: relType,
      }),
    });
    if (!res.ok) {
      const err = await res.text();
      if (statusDiv) statusDiv.textContent = 'Failed: ' + err;
      return;
    }
    if (statusDiv) statusDiv.innerHTML = '<span class="text-green-600">✓ Relation saved</span>';
    _modalAddRelationTargetId = null;
    const targetInput = document.getElementById('modal-add-relation-target');
    if (targetInput) targetInput.value = '';
    const saveBtn = document.getElementById('modal-add-relation-save');
    if (saveBtn) saveBtn.disabled = true;
    setStatus('Relation added');

    // Refresh the modal by re-fetching node detail
    const detail = await fetchNodeDetail(sourceNode);
    if (activeModalNodeId === sourceNode.id && activeModalId) {
      const content = renderNodeModalContent(sourceNode, filteredLinks, detail || {});
      updateModal(activeModalId, { title: sourceNode.label || sourceNode.id || 'Node detail', content });
      _wireDeleteButtons(sourceNode);
    }
  } catch (e) {
    if (statusDiv) statusDiv.textContent = 'Failed: ' + e.message;
  }
}

// --- Management tools panel wiring ---
function _wireManagementTools() {
  const toggleBtn = document.getElementById('entities-graph-mgmt-toggle');
  const body = document.getElementById('entities-graph-mgmt-body');
  const arrow = document.getElementById('entities-graph-mgmt-arrow');
  if (toggleBtn && body) {
    toggleBtn.onclick = () => {
      body.classList.toggle('hidden');
      if (arrow) arrow.textContent = body.classList.contains('hidden') ? '▸' : '▾';
    };
  }

  const mgmtStatus = document.getElementById('entities-graph-mgmt-status');
  function setMgmtStatus(msg) { if (mgmtStatus) mgmtStatus.textContent = msg; }

  document.getElementById('entities-graph-validate-rels')?.addEventListener('click', async () => {
    setMgmtStatus('Validating…');
    try {
      const base = val('base-url') || '';
      const res = await fetch(`${base}/api/relationships/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
        body: JSON.stringify({ fix: true }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMgmtStatus(`✓ Validated: ${data.total_checked || 0} checked, ${data.issues_fixed || 0} fixed`);
    } catch (e) { setMgmtStatus('Failed: ' + e.message); }
  });

  document.getElementById('entities-graph-dedup-rels')?.addEventListener('click', async () => {
    setMgmtStatus('Deduplicating relationships…');
    try {
      const base = val('base-url') || '';
      const res = await fetch(`${base}/api/relationships/deduplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMgmtStatus(`✓ Removed ${data.duplicates_removed || 0} duplicates`);
    } catch (e) { setMgmtStatus('Failed: ' + e.message); }
  });

  document.getElementById('entities-graph-infer-rels')?.addEventListener('click', async () => {
    const entityIds = [...selectedNodes.keys()];
    if (entityIds.length === 0) { setMgmtStatus('Select nodes first to infer relationships'); return; }
    setMgmtStatus('Inferring relationships…');
    try {
      const base = val('base-url') || '';
      const res = await fetch(`${base}/api/relationships/infer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
        body: JSON.stringify({ entity_ids: entityIds }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMgmtStatus(`✓ Inferred ${data.relationships_found || 0} relationships`);
    } catch (e) { setMgmtStatus('Failed: ' + e.message); }
  });

  document.getElementById('entities-graph-dedup-entities')?.addEventListener('click', async () => {
    setMgmtStatus('Scanning for duplicates…');
    try {
      const base = val('base-url') || '';
      const res = await fetch(`${base}/api/entities/deduplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
        body: JSON.stringify({ threshold: 0.85 }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMgmtStatus(`✓ Found ${data.duplicates_found || data.groups?.length || 0} duplicate groups`);
    } catch (e) { setMgmtStatus('Failed: ' + e.message); }
  });

  document.getElementById('entities-graph-rel-stats')?.addEventListener('click', async () => {
    setMgmtStatus('Fetching stats…');
    try {
      const base = val('base-url') || '';
      const res = await fetch(`${base}/api/relationships/confidence-stats`, {
        headers: { 'X-API-Key': els.apiKey?.value || '' },
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const total = data.total_relationships || 0;
      const types = data.top_relation_types ? data.top_relation_types.length : 0;
      setMgmtStatus(`✓ ${total} relationships, ${types} types`);
    } catch (e) { setMgmtStatus('Failed: ' + e.message); }
  });
}

function wireHoverModal(graph) {
  graph.onNodeHover((n) => {
    // Clear any existing hover timer
    if (hoverTimer) {
      clearTimeout(hoverTimer);
      hoverTimer = null;
    }
    // Don't set hover timer if no node or if modal is already open for this node
    if (!n || activeModalNodeId === n.id) return;
    hoverTimer = setTimeout(() => openNodeModal(n), HOVER_MODAL_DELAY);
  });
  if (els.entitiesGraphCanvas) {
    els.entitiesGraphCanvas.addEventListener('mouseleave', () => {
      if (hoverTimer) clearTimeout(hoverTimer);
      hoverTimer = null;
    });
  }
}

const FORCE_GRAPH_2D_SOURCES = [
  '/static/vendor/force-graph.min.js',
  'https://cdn.jsdelivr.net/npm/force-graph@1.50.1/dist/force-graph.min.js',
  'https://unpkg.com/force-graph@1.50.1/dist/force-graph.min.js',
];
const FORCE_GRAPH_3D_SOURCES = [
  '/static/vendor/3d-force-graph.min.js',
  'https://cdn.jsdelivr.net/npm/3d-force-graph@1.72.6/dist/3d-force-graph.min.js',
  'https://unpkg.com/3d-force-graph@1.72.6/dist/3d-force-graph.min.js',
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

async function loadForceGraphLib(is3D) {
  if (is3D) {
    if (window.ForceGraph3D) return window.ForceGraph3D;
    let lastErr;
    for (const src of FORCE_GRAPH_3D_SOURCES) {
      try {
        await loadScript(src);
        if (window.ForceGraph3D) return window.ForceGraph3D;
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error('Failed to load 3d-force-graph library');
  } else {
    if (window.ForceGraph) return window.ForceGraph;
    let lastErr;
    for (const src of FORCE_GRAPH_2D_SOURCES) {
      try {
        await loadScript(src);
        if (window.ForceGraph) return window.ForceGraph;
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error('Failed to load force-graph (2D) library');
  }
}

function getNodeTypeFilters() {
  // If whitelist is set, only those are allowed; otherwise all minus blacklist
  const allKinds = discoverNodeKinds(currentNodes);
  if (nodeWhitelist.size > 0) {
    return [...nodeWhitelist].filter(k => !nodeBlacklist.has(k));
  }
  return [...allKinds].filter(k => !nodeBlacklist.has(k));
}

function getEdgeKindFilters() {
  const allKinds = discoverEdgeKinds(currentLinks);
  if (edgeWhitelist.size > 0) {
    return [...edgeWhitelist].filter(k => !edgeBlacklist.has(k));
  }
  return [...allKinds].filter(k => !edgeBlacklist.has(k));
}

function getDepthLimit() {
  const v = parseInt(filterEls.depth()?.value || '1', 10);
  return Number.isFinite(v) ? v : 1;
}

function seedsFromQuery(nodes, query) {
  if (!query) return nodes.map((n) => n.id);
  const q = query.toLowerCase();
  const seeds = nodes
    .filter((n) => (n.label || '').toLowerCase().includes(q) || (String(n.id) || '').toLowerCase().includes(q))
    .map((n) => n.id);
  return seeds.length ? seeds : nodes.map((n) => n.id);
}

function filterByDepth(nodes, links, depthLimit, seeds) {
  if (!Number.isFinite(depthLimit) || depthLimit >= 99) return { nodes, links };
  const adj = new Map();
  links.forEach((l) => {
    const a = l.source?.id || l.source;
    const b = l.target?.id || l.target;
    if (!a || !b) return;
    if (!adj.has(a)) adj.set(a, new Set());
    if (!adj.has(b)) adj.set(b, new Set());
    adj.get(a).add(b);
    adj.get(b).add(a);
  });

  const keep = new Set();
  const queue = [];
  seeds.forEach((s) => {
    keep.add(s);
    queue.push({ id: s, d: 0 });
  });

  while (queue.length) {
    const { id, d } = queue.shift();
    if (d >= depthLimit) continue;
    const next = adj.get(id) || [];
    next.forEach((n) => {
      if (!keep.has(n)) {
        keep.add(n);
        queue.push({ id: n, d: d + 1 });
      }
    });
  }

  const filteredN = nodes.filter((n) => keep.has(n.id));
  const filteredL = links.filter((l) => keep.has(l.source?.id || l.source) && keep.has(l.target?.id || l.target));
  return { nodes: filteredN, links: filteredL };
}

function applyFilters(rawNodes, rawLinks) {
  const nodeTypes = new Set(getNodeTypeFilters());
  const edgeKinds = new Set(getEdgeKindFilters());
  const depthLimit = getDepthLimit();
  const q = (els.entitiesGraphQuery?.value || '').trim().toLowerCase();

  let nodes = rawNodes.filter((n) => {
    const t = (n.type || 'unknown').toLowerCase();
    const k = (n.kind || '').toLowerCase();
    const ek = (n.meta?.entity_kind || '').toLowerCase();
    // Check if any of the type/kind identifiers match the filter
    return nodeTypes.has(t) || nodeTypes.has(k) || nodeTypes.has(ek) || (nodeTypes.has('entity') && t === 'unknown');
  });

  let links = rawLinks
    .map((l) => ({ ...l, kind: l.kind || 'link' }))
    .filter((l) => edgeKinds.has(l.kind));

  const nodeSet = new Set(nodes.map((n) => n.id));
  links = links.filter((l) => nodeSet.has(l.source) && nodeSet.has(l.target));

  const seeds = seedsFromQuery(nodes, q);
  const depthFiltered = filterByDepth(nodes, links, depthLimit, seeds);
  nodes = depthFiltered.nodes;
  links = depthFiltered.links;

  filteredNodes = nodes;
  filteredLinks = links;
}

function updateToggleButton() {
  const btn = filterEls.toggle3d();
  if (!btn) return;
  btn.textContent = use3D ? 'Switch to 2D' : 'Switch to 3D';
  btn.setAttribute('aria-pressed', use3D ? 'true' : 'false');
  btn.classList.toggle('border-blue-500', use3D);
  btn.classList.toggle('bg-blue-50', use3D);
}

function linkWidthFromWeight(weight) {
  const w = Number(weight) || 1;
  return Math.max(0.6, Math.log1p(w) * 1.8);
}

function nodeRadius(node) {
  return Math.max(3, Math.sqrt(Math.max(2, (node.count || 1) * 0.4 + (node.score || 0) * 2)) * 4);
}

function shouldAnimateLink(l) {
  const key = `${l.source?.id || l.source}-${l.target?.id || l.target}-${l.kind || ''}`;
  return pseudoRandomFromKey(key) < PARTICLE_PROB;
}

async function fetchGraph() {
  const base = val('base-url') || '';
  const q = encodeURIComponent(els.entitiesGraphQuery?.value || '');
  // Build pre-request type filter from whitelisted + pre-request node filters
  const preTypes = _getPreRequestTypes();
  const type = encodeURIComponent(preTypes.join(','));
  const min = encodeURIComponent(els.entitiesGraphMinScore?.value || 0);
  const limit = encodeURIComponent(els.entitiesGraphLimit?.value || 100);
  const nodeTypes = encodeURIComponent(getNodeTypeFilters().join(','));
  const edgeKinds = encodeURIComponent(getEdgeKindFilters().join(','));
  const depth = encodeURIComponent(getDepthLimit());
  const url = `${base}/api/entities/graph?query=${q}&type=${type}&min_score=${min}&limit=${limit}&node_types=${nodeTypes}&edge_kinds=${edgeKinds}&depth=${depth}&include_meta=1`;
  setStatus('Loading...');
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

/**
 * Get entity types that should be sent as pre-request filters to the API.
 * These are node kinds marked as pre-request that are also whitelisted,
 * or all pre-request kinds when the whitelist is empty (all types allowed).
 */
function _getPreRequestTypes() {
  const types = [];
  if (nodeWhitelist.size === 0) {
    // No whitelist = all types allowed; send any pre-request filters directly
    for (const kind of preRequestNodeFilters) {
      types.push(kind);
    }
  } else {
    for (const kind of nodeWhitelist) {
      if (preRequestNodeFilters.has(kind)) {
        types.push(kind);
      }
    }
  }
  return types;
}

function clearGraphCanvas() {
  if (!els.entitiesGraphCanvas) return;
  while (els.entitiesGraphCanvas.firstChild) {
    els.entitiesGraphCanvas.removeChild(els.entitiesGraphCanvas.firstChild);
  }
}

function resizeGraph() {
  if (!graphInstance || !els.entitiesGraphCanvas) return;
  const rect = els.entitiesGraphCanvas.getBoundingClientRect();
  const w = Math.max(320, rect.width || els.entitiesGraphCanvas.clientWidth || 800);
  const h = Math.max(320, rect.height || els.entitiesGraphCanvas.clientHeight || 540);
  if (use3D) {
    setTimeout(() => graphInstance && graphInstance.width(w).height(h), 10);
  } else {
    graphInstance.width(w).height(h);
  }
}

function tuneForces(instance) {
  const charge = instance.d3Force && instance.d3Force('charge');
  if (charge) charge.strength(-180).distanceMax(500);
  const linkForce = instance.d3Force && instance.d3Force('link');
  if (linkForce) {
    linkForce
      .distance((l) => 60 + (l.weight || 1) * 12)
      .strength((l) => 0.6 + Math.min(1, (l.weight || 1) * 0.15));
  }
  // Speed up simulation convergence
  if (typeof instance.cooldownTicks === 'function') instance.cooldownTicks(150);
  if (typeof instance.warmupTicks === 'function') instance.warmupTicks(50);
}

function pseudoRandomFromKey(key) {
  let hash = 2166136261;
  for (let i = 0; i < key.length; i++) {
    hash ^= key.charCodeAt(i);
    hash *= 16777619;
  }
  return (hash >>> 0) / 0xffffffff;
}

function renderGraphData(forceGraphInstance) {
  // ForceGraph accepts ids or node objects; pass ids or objects as available
  const nodeMap = new Map(filteredNodes.map((n) => [n.id, n]));
  const links = filteredLinks.map((l) => ({
    ...l,
    source: nodeMap.get(l.source?.id || l.source) || l.source,
    target: nodeMap.get(l.target?.id || l.target) || l.target,
  }));
  forceGraphInstance.graphData({ nodes: filteredNodes, links });
}

// ─── Node selection helpers ───

function toggleNodeSelection(node) {
  if (selectedNodes.has(node.id)) {
    selectedNodes.delete(node.id);
  } else {
    selectedNodes.set(node.id, node);
  }
  renderSelectionPanel();
  _updateGraphHighlights();
}

function clearSelection() {
  selectedNodes.clear();
  renderSelectionPanel();
  _updateGraphHighlights();
}

function renderSelectionPanel() {
  const panel = document.getElementById('entities-graph-selection-panel');
  const countEl = document.getElementById('entities-graph-selection-count');
  const listEl = document.getElementById('entities-graph-selection-list');
  if (!panel || !countEl || !listEl) return;

  const count = selectedNodes.size;
  countEl.textContent = count;
  panel.classList.toggle('hidden', count === 0);

  if (count === 0) { listEl.innerHTML = ''; return; }

  listEl.innerHTML = [...selectedNodes.values()].map(n => {
    const color = getNodeColor(n);
    return `<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] border" style="border-color:${color}">
      <span class="w-1.5 h-1.5 rounded-full" style="background:${color}"></span>
      ${escapeHtml((n.label || n.id).slice(0, 20))}
      <button type="button" data-deselect="${escapeHtml(n.id)}" class="ml-0.5 text-slate-400 hover:text-red-500">✕</button>
    </span>`;
  }).join('');

  listEl.querySelectorAll('[data-deselect]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.dataset.deselect;
      selectedNodes.delete(id);
      renderSelectionPanel();
      _updateGraphHighlights();
    });
  });
}

async function deleteSelectedNodes() {
  if (selectedNodes.size === 0) return;
  const allNames = [...selectedNodes.values()].map(n => n.label || n.id);
  const displayNames = allNames.length > 5
    ? allNames.slice(0, 5).join(', ') + ` …and ${allNames.length - 5} more`
    : allNames.join(', ');
  if (!confirm(`Delete ${selectedNodes.size} selected node(s)?\n${displayNames}\nThis cannot be undone.`)) return;
  const base = val('base-url') || '';
  for (const [id] of selectedNodes) {
    if (!_isValidUUID(id)) continue;
    try {
      await fetch(`${base}/api/entities/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
      });
    } catch (e) { console.warn('Delete failed for', id, e); }
  }
  clearSelection();
  loadAndRender();
}

// Build adjacency map from links for BFS traversal
// When relTypes is provided (non-empty Set), only include links matching those types
function _buildAdjacencyMap(links, relTypes) {
  const adj = new Map();
  for (const l of links) {
    if (relTypes && relTypes.size > 0) {
      const rt = l.meta?.relation_type || l.kind || '';
      if (!relTypes.has(rt)) continue;
    }
    const src = l.source?.id || l.source;
    const tgt = l.target?.id || l.target;
    if (!adj.has(src)) adj.set(src, []);
    if (!adj.has(tgt)) adj.set(tgt, []);
    adj.get(src).push(tgt);
    adj.get(tgt).push(src);
  }
  return adj;
}

// Select connected nodes: BFS from all currently-selected nodes using highlighted relation types and depth
function selectConnectedNodes() {
  if (filteredNodes.length === 0) return;
  const depth = selectionDepth || 1;
  const relTypes = highlightedRelTypes.size > 0 ? highlightedRelTypes : null;
  const adj = _buildAdjacencyMap(filteredLinks, relTypes);

  // BFS from every currently-selected node (or all nodes if none selected)
  const seeds = selectedNodes.size > 0
    ? [...selectedNodes.keys()]
    : filteredNodes.map(n => n.id);

  const visited = new Set(seeds);
  const bfsQueue = seeds.map(id => ({ id, depth: 0 }));
  let qi = 0;
  while (qi < bfsQueue.length) {
    const { id, depth: d } = bfsQueue[qi++];
    if (d >= depth) continue;
    const neighbors = adj.get(id) || [];
    for (const nbrId of neighbors) {
      if (!visited.has(nbrId)) {
        visited.add(nbrId);
        bfsQueue.push({ id: nbrId, depth: d + 1 });
      }
    }
  }

  // Select all visited nodes
  for (const nId of visited) {
    const node = filteredNodes.find(nd => nd.id === nId);
    if (node) selectedNodes.set(nId, node);
  }
  renderSelectionPanel();
  _updateGraphHighlights();
}

// Select all nodes that have no connections in the current graph
function selectDisconnectedNodes() {
  if (filteredNodes.length === 0) return;
  const relTypes = highlightedRelTypes.size > 0 ? highlightedRelTypes : null;
  const adj = _buildAdjacencyMap(filteredLinks, relTypes);
  for (const node of filteredNodes) {
    const neighbors = adj.get(node.id);
    if (!neighbors || neighbors.length === 0) {
      selectedNodes.set(node.id, node);
    }
  }
  renderSelectionPanel();
  _updateGraphHighlights();
}

// Invert the current selection: select all unselected, deselect all selected
function invertSelection() {
  if (filteredNodes.length === 0) return;
  const newSelection = new Map();
  for (const node of filteredNodes) {
    if (!selectedNodes.has(node.id)) {
      newSelection.set(node.id, node);
    }
  }
  selectedNodes = newSelection;
  renderSelectionPanel();
  _updateGraphHighlights();
}

// Bulk Link All: create relationships between all selected node pairs
async function bulkLinkAll() {
  if (selectedNodes.size < 2) { alert('Select at least 2 nodes to link.'); return; }
  const relType = prompt('Relationship type for all pairs:', 'related_to');
  if (!relType) return;

  const nodes = [...selectedNodes.values()];
  const base = val('base-url') || '';
  let saved = 0, failed = 0;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      try {
        const res = await fetch(`${base}/api/relationships/record`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
          body: JSON.stringify({
            source_id: nodes[i].id,
            target_id: nodes[j].id,
            relation_type: relType,
          }),
        });
        if (res.ok) saved++; else failed++;
      } catch (e) { console.warn('Link failed', e); failed++; }
    }
  }
  setStatus(`Linked ${saved} pairs${failed ? `, ${failed} failed` : ''}`);
  loadAndRender();
}

// Bulk Merge: merge N selected entities into the first selected
async function bulkMerge() {
  if (selectedNodes.size < 2) { alert('Select at least 2 nodes to merge.'); return; }
  const nodes = [...selectedNodes.values()];
  const targetNode = nodes[0];
  const sources = nodes.slice(1);
  const displayTarget = targetNode.label || targetNode.id;
  const displaySrcs = sources.map(n => n.label || n.id).join(', ');
  if (!confirm(`Merge ${sources.length} node(s) into "${displayTarget}"?\n\nWill merge: ${displaySrcs}\n\nThis cannot be undone.`)) return;

  const base = val('base-url') || '';
  let merged = 0, failed = 0;
  for (const src of sources) {
    try {
      const res = await fetch(`${base}/api/entities/${encodeURIComponent(src.id)}/merge/${encodeURIComponent(targetNode.id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
      });
      if (res.ok) merged++; else failed++;
    } catch (e) { console.warn('Merge failed', e); failed++; }
  }
  setStatus(`Merged ${merged} entities into "${displayTarget}"${failed ? `, ${failed} failed` : ''}`);
  clearSelection();
  loadAndRender();
}

function openConnectPanel() {
  if (selectedNodes.size === 0) return;
  addRelationSourceNodes = [...selectedNodes.values()];
  addRelationTargetNode = null;

  const panel = document.getElementById('entities-graph-add-relation-panel');
  const srcLabel = document.getElementById('entities-graph-relation-source-label');
  const saveBtn = document.getElementById('entities-graph-relation-save');
  if (!panel) return;

  panel.classList.remove('hidden');
  if (srcLabel) {
    srcLabel.textContent = `From: ${addRelationSourceNodes.map(n => n.label || n.id).join(', ')}`;
  }
  if (saveBtn) saveBtn.disabled = true;

  // Populate relation type datalist with known types
  _populateRelationTypeList();
  _clearRelationTargetResults();
}

function _populateRelationTypeList() {
  const list = document.getElementById('entities-graph-relation-type-list');
  if (!list) return;
  const types = discoverRelationTypes(currentLinks);
  list.innerHTML = [...types].map(t => `<option value="${escapeHtml(t)}">`).join('');
}

function _clearRelationTargetResults() {
  const el = document.getElementById('entities-graph-relation-target-results');
  if (el) el.innerHTML = '';
}

function _searchTargetNodes(query) {
  if (!query || query.length < 2) { _clearRelationTargetResults(); return; }
  const q = query.toLowerCase();
  const results = filteredNodes
    .filter(n => (n.label || '').toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
    .slice(0, 8);

  const el = document.getElementById('entities-graph-relation-target-results');
  if (!el) return;

  el.innerHTML = results.map(n => {
    const color = getNodeColor(n);
    const selected = addRelationTargetNode?.id === n.id;
    return `<button type="button" data-target-id="${escapeHtml(n.id)}"
      class="w-full text-left px-2 py-1 rounded text-[11px] flex items-center gap-1.5 ${selected ? 'bg-green-100 dark:bg-green-900/30 font-semibold' : 'hover:bg-slate-100 dark:hover:bg-slate-800'}">
      <span class="w-2 h-2 rounded-full shrink-0" style="background:${color}"></span>
      ${escapeHtml((n.label || n.id).slice(0, 40))}
      <span class="text-[9px] text-slate-400 ml-auto">${escapeHtml(n.kind || n.type || '')}</span>
    </button>`;
  }).join('');

  el.querySelectorAll('[data-target-id]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.targetId;
      addRelationTargetNode = filteredNodes.find(n => n.id === id) || null;
      _searchTargetNodes(document.getElementById('entities-graph-relation-target-search')?.value || '');
      _updateRelationSaveBtn();
    });
  });
}

function _updateRelationSaveBtn() {
  const btn = document.getElementById('entities-graph-relation-save');
  const typeInput = document.getElementById('entities-graph-relation-type-input');
  if (!btn) return;
  btn.disabled = !(addRelationTargetNode && typeInput?.value?.trim());
}

async function _saveRelation() {
  const typeInput = document.getElementById('entities-graph-relation-type-input');
  const relType = typeInput?.value?.trim();
  if (!addRelationTargetNode || !relType || addRelationSourceNodes.length === 0) return;

  const base = val('base-url') || '';
  let savedCount = 0;
  const failedSrcs = [];
  for (const src of addRelationSourceNodes) {
    try {
      const res = await fetch(`${base}/api/relationships/record`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': els.apiKey?.value || '' },
        body: JSON.stringify({
          source_id: src.id,
          target_id: addRelationTargetNode.id,
          relation_type: relType,
        }),
      });
      if (res.ok) savedCount++;
      else failedSrcs.push(src.label || src.id);
    } catch (e) {
      console.warn('Save relation failed', e);
      failedSrcs.push(src.label || src.id);
    }
  }

  // Keep panel open for next target selection, reset target but keep sources and relation type
  addRelationTargetNode = null;
  const targetSearch = document.getElementById('entities-graph-relation-target-search');
  if (targetSearch) targetSearch.value = '';
  _clearRelationTargetResults();
  _updateRelationSaveBtn();

  // Show confirmation using textContent for safe parts and controlled HTML for formatting
  const srcLabel = document.getElementById('entities-graph-relation-source-label');
  if (srcLabel) {
    const fromText = `From: ${addRelationSourceNodes.map(n => escapeHtml(n.label || n.id)).join(', ')}`;
    const safeSavedCount = parseInt(savedCount, 10) || 0;
    const statusMsg = failedSrcs.length > 0
      ? `<span class="text-amber-600 ml-1">✓ ${safeSavedCount} saved, ${failedSrcs.length} failed — select next target or close</span>`
      : `<span class="text-green-600 ml-1">✓ ${safeSavedCount} saved — select next target or close</span>`;
    srcLabel.innerHTML = `${fromText} ${statusMsg}`;
  }

  // Reload graph data in background
  try {
    await fetchSchema();
    const data = await fetchGraph();
    currentNodes = data.nodes || [];
    currentLinks = data.links || [];
    applyFilters(currentNodes, currentLinks);
    renderFilterBar();
    renderRelationFilterBar();
    renderLegend();
    await renderGraph();
  } catch (e) { console.warn('Graph reload failed', e); }
}

function _closeRelationPanel() {
  const panel = document.getElementById('entities-graph-add-relation-panel');
  if (panel) panel.classList.add('hidden');
  addRelationSourceNodes = [];
  addRelationTargetNode = null;
}

// ─── Rectangle selection on canvas ───

function _initRectangleSelection() {
  const canvas = els.entitiesGraphCanvas;
  if (!canvas) return;

  let overlay = null;
  let startX = 0, startY = 0;
  let dragging = false;

  canvas.addEventListener('mousedown', (e) => {
    if (!selectionMode || use3D) return;
    if (e.button !== 0) return;
    dragging = true;
    const rect = canvas.getBoundingClientRect();
    startX = e.clientX - rect.left;
    startY = e.clientY - rect.top;

    overlay = document.createElement('div');
    overlay.style.cssText = `position:absolute;border:2px dashed #3b82f6;background:rgba(59,130,246,0.08);pointer-events:none;z-index:50;`;
    overlay.style.left = startX + 'px';
    overlay.style.top = startY + 'px';
    canvas.style.position = 'relative';
    canvas.appendChild(overlay);
    e.preventDefault();
  });

  canvas.addEventListener('mousemove', (e) => {
    if (!dragging || !overlay) return;
    const rect = canvas.getBoundingClientRect();
    const curX = e.clientX - rect.left;
    const curY = e.clientY - rect.top;
    const x = Math.min(startX, curX);
    const y = Math.min(startY, curY);
    const w = Math.abs(curX - startX);
    const h = Math.abs(curY - startY);
    overlay.style.left = x + 'px';
    overlay.style.top = y + 'px';
    overlay.style.width = w + 'px';
    overlay.style.height = h + 'px';
  });

  canvas.addEventListener('mouseup', (e) => {
    if (!dragging || !overlay) return;
    dragging = false;
    const rect = canvas.getBoundingClientRect();
    const curX = e.clientX - rect.left;
    const curY = e.clientY - rect.top;
    const selRect = {
      x1: Math.min(startX, curX),
      y1: Math.min(startY, curY),
      x2: Math.max(startX, curX),
      y2: Math.max(startY, curY),
    };

    overlay.remove();
    overlay = null;

    // Only select if dragged a meaningful rectangle
    if (selRect.x2 - selRect.x1 < 5 && selRect.y2 - selRect.y1 < 5) return;

    // Find nodes inside selection rectangle (2D only)
    if (graphInstance && graphInstance.screen2GraphCoords) {
      const topLeft = graphInstance.screen2GraphCoords(selRect.x1, selRect.y1);
      const bottomRight = graphInstance.screen2GraphCoords(selRect.x2, selRect.y2);
      const minX = Math.min(topLeft.x, bottomRight.x);
      const maxX = Math.max(topLeft.x, bottomRight.x);
      const minY = Math.min(topLeft.y, bottomRight.y);
      const maxY = Math.max(topLeft.y, bottomRight.y);
      for (const n of filteredNodes) {
        if (n.x >= minX && n.x <= maxX && n.y >= minY && n.y <= maxY) {
          selectedNodes.set(n.id, n);
        }
      }
      renderSelectionPanel();
      _updateGraphHighlights();
    }
  });
}

async function renderGraph() {
  if (!els.entitiesGraphCanvas) return;
  clearGraphCanvas();

  const ForceLib = await loadForceGraphLib(use3D);
  const createGraph = use3D
    ? ForceLib({ rendererConfig: { antialias: true, useLegacyLights: false } })
    : ForceLib();

  graphInstance = createGraph(els.entitiesGraphCanvas)
    .nodeRelSize(4)
    .nodeLabel((n) => `${n.label || n.id} (${n.type || 'unknown'})`)
    .nodeColor((n) => {
      if (selectedNodes.has(n.id)) return '#3b82f6';
      return getNodeColor(n);
    })
    .nodeVal((n) => Math.max(2, (n.count || 1) * 0.4 + (n.score || 0) * 2))
    .linkColor((l) => {
      if (highlightedRelTypes.size > 0) {
        const rt = l.meta?.relation_type || l.kind || '';
        if (highlightedRelTypes.has(rt)) return 'rgba(139,92,246,0.85)';
        return 'rgba(148,163,184,0.08)';
      }
      return EDGE_COLORS[l.kind] || EDGE_COLORS.default;
    })
    .linkWidth((l) => {
      if (highlightedRelTypes.size > 0) {
        const rt = l.meta?.relation_type || l.kind || '';
        if (highlightedRelTypes.has(rt)) return linkWidthFromWeight(l.weight) * 2.5;
        return 0.3;
      }
      return linkWidthFromWeight(l.weight);
    })
    .linkDirectionalParticles((l) => (shouldAnimateLink(l) ? 1 : 0))
    .linkDirectionalParticleWidth((l) => Math.max(PARTICLE_WIDTH_BASE, (l.weight || 1) * 0.6))
    .linkDirectionalParticleSpeed(() => PARTICLE_SPEED)
    .linkLabel(
      (l) => {
        const displayKind = l.kind === 'relationship' && l.meta?.relation_type 
          ? l.meta.relation_type 
          : l.kind || 'link';
        
        return `${displayKind}${l.weight ? ` (w:${l.weight})` : ''}${
          l.meta && Object.keys(l.meta).length
            ? `\n${Object.entries(l.meta)
                .filter(([k]) => k !== 'relation_type')
                .map(([k, v]) => `${k}: ${fmt(v)}`)
                .join('\n')}`
            : ''
        }`;
      }
    )
    .onNodeClick((n) => {
      if (selectionMode) {
        toggleNodeSelection(n);
        // Depth-based BFS selection on node click
        // When relation types are highlighted, only traverse matching links
        if (selectionDepth > 0) {
          const relTypes = highlightedRelTypes.size > 0 ? highlightedRelTypes : null;
          const adj = _buildAdjacencyMap(filteredLinks, relTypes);
          const bfsQueue = [{ id: n.id, depth: 0 }];
          const visited = new Set([n.id]);
          let qi = 0;
          while (qi < bfsQueue.length) {
            const { id, depth } = bfsQueue[qi++];
            if (depth >= selectionDepth) continue;
            const neighbors = adj.get(id) || [];
            for (const nbrId of neighbors) {
              if (!visited.has(nbrId)) {
                visited.add(nbrId);
                const nbrNode = filteredNodes.find(nd => nd.id === nbrId);
                if (nbrNode) {
                  selectedNodes.set(nbrId, nbrNode);
                  bfsQueue.push({ id: nbrId, depth: depth + 1 });
                }
              }
            }
          }
          renderSelectionPanel();
          _updateGraphHighlights();
        }
        return;
      }
      selectedNodeId = n.id;
      renderDetails(n, filteredLinks);
      openNodeModal(n);
    });

  // Custom node rendering for 2D mode: selected border + early labels
  if (!use3D) {
    graphInstance.nodeCanvasObject((node, ctx, globalScale) => {
      const r = nodeRadius(node);
      const color = getNodeColor(node);
      const isSelected = selectedNodes.has(node.id);

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = isSelected ? '#3b82f6' : color;
      ctx.fill();

      // White 2px stroke border on selected nodes
      if (isSelected) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
      }

      // Label (visible at low zoom)
      if (globalScale > LABEL_ZOOM_THRESHOLD) {
        const label = node.label || node.id || '';
        const fontSize = Math.max(10, 12 / globalScale);
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = isSelected ? '#3b82f6' : '#64748b';
        ctx.fillText(label.slice(0, 24), node.x, node.y + r + 2);
      }
    }).nodePointerAreaPaint((node, color, ctx) => {
      const r = nodeRadius(node);
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
    });
  }

  tuneForces(graphInstance);
  renderGraphData(graphInstance);
  wireHoverModal(graphInstance);
  resizeGraph();
  renderDetails(null, []);
  setStatus(`Loaded ${filteredNodes.length} nodes / ${filteredLinks.length} links (${use3D ? '3D' : '2D'})`);
}

async function loadAndRender(ev) {
  ev?.preventDefault();
  try {
    // Fetch schema first to update colors
    await fetchSchema();
    
    const data = await fetchGraph();
    currentNodes = data.nodes || [];
    currentLinks = data.links || [];
    // Sync pre-request state tracker
    _lastPreRequestState = JSON.stringify([...nodeWhitelist].filter(k => preRequestNodeFilters.has(k)).sort());
    applyFilters(currentNodes, currentLinks);
    renderFilterBar();
    renderRelationFilterBar();
    renderLegend();
    await renderGraph();
  } catch (e) {
    console.error(e);
    setStatus(e.message || 'Failed to load graph', true);
  }
}

export async function initEntitiesGraph() {
  if (!els.entitiesGraphForm || !els.entitiesGraphCanvas) return;
  
  // Fetch schema on init
  await fetchSchema();
  renderLegend();
  renderDetails(null, []);
  updateToggleButton();

  document.querySelectorAll('[data-tab-btn]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.tabBtn === 'entities-graph') {
        setTimeout(resizeGraph, 50);
      }
    });
  });

  els.entitiesGraphForm.onsubmit = loadAndRender;
  if (els.entitiesGraphLoad) els.entitiesGraphLoad.onclick = loadAndRender;
  if (filterEls.toggle3d()) {
    filterEls.toggle3d().onclick = async () => {
      use3D = !use3D;
      updateToggleButton();
      await renderGraph();
    };
  }

  // Advanced options toggle
  const advToggle = document.getElementById('entities-graph-advanced-toggle');
  const advPanel = document.getElementById('entities-graph-advanced');
  if (advToggle && advPanel) {
    advToggle.addEventListener('click', () => advPanel.classList.toggle('hidden'));
  }

  // Selection mode toggle
  const selModeBtn = document.getElementById('entities-graph-selection-mode');
  if (selModeBtn) {
    selModeBtn.addEventListener('click', () => {
      selectionMode = !selectionMode;
      selModeBtn.classList.toggle('border-blue-500', selectionMode);
      selModeBtn.classList.toggle('bg-blue-50', selectionMode);
      selModeBtn.classList.toggle('dark:bg-blue-900/30', selectionMode);
      if (selectionMode && use3D) {
        selModeBtn.textContent = '⬚ Select (click only)';
        selModeBtn.title = 'Rectangle selection is not available in 3D mode. Click nodes to select.';
      } else {
        selModeBtn.textContent = selectionMode ? '⬚ Select ✓' : '⬚ Select';
        selModeBtn.title = 'Toggle rectangle selection mode';
      }
    });
  }

  // Selection panel buttons
  document.getElementById('entities-graph-clear-selection')?.addEventListener('click', clearSelection);
  document.getElementById('entities-graph-delete-selected')?.addEventListener('click', deleteSelectedNodes);
  document.getElementById('entities-graph-connect-selected')?.addEventListener('click', openConnectPanel);
  document.getElementById('entities-graph-link-all-selected')?.addEventListener('click', bulkLinkAll);
  document.getElementById('entities-graph-merge-selected')?.addEventListener('click', bulkMerge);
  document.getElementById('entities-graph-select-connected')?.addEventListener('click', selectConnectedNodes);
  document.getElementById('entities-graph-select-disconnected')?.addEventListener('click', selectDisconnectedNodes);
  document.getElementById('entities-graph-invert-selection')?.addEventListener('click', invertSelection);

  // Selection depth dropdown
  document.getElementById('entities-graph-selection-depth')?.addEventListener('change', (e) => {
    selectionDepth = parseInt(e.target.value, 10) || 0;
  });

  // Add relation panel
  document.getElementById('entities-graph-cancel-relation')?.addEventListener('click', _closeRelationPanel);
  document.getElementById('entities-graph-relation-save')?.addEventListener('click', _saveRelation);
  document.getElementById('entities-graph-relation-target-search')?.addEventListener('input', (e) => {
    _searchTargetNodes(e.target.value);
  });
  document.getElementById('entities-graph-relation-type-input')?.addEventListener('input', _updateRelationSaveBtn);

  // Depth filter
  filterEls.depth()?.addEventListener('change', async () => {
    applyFilters(currentNodes, currentLinks);
    renderFilterBar();
    renderRelationFilterBar();
    renderLegend();
    await renderGraph();
  });

  if (els.entitiesGraphDetails) {
    els.entitiesGraphDetails.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action="expand-node"]');
      if (!btn) return;
      const nodeId = btn.dataset.nodeId || '';
      const nodeType = btn.dataset.nodeType || '';
      if (els.entitiesGraphQuery) els.entitiesGraphQuery.value = nodeId;
      // Use the filter pill system: whitelist the node type if known
      if (nodeType && nodeType !== 'unknown') {
        nodeWhitelist.clear();
        nodeWhitelist.add(nodeType);
      }
      loadAndRender();
    });
  }

  // Init rectangle selection
  _initRectangleSelection();

  // Management tools panel toggle and buttons
  _wireManagementTools();

  await loadAndRender();
}
