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
const PARTICLE_PROB = 0.28;
const HOVER_MODAL_DELAY = 3500;

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

const filterEls = {
  nodeFilters: () => Array.from(document.querySelectorAll('.entities-node-filter')),
  edgeFilters: () => Array.from(document.querySelectorAll('.entities-edge-filter')),
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
    
    return schemaCache;
  } catch (e) {
    console.warn('Failed to fetch schema:', e);
    return null;
  }
}

/**
 * Get node color, falling back to defaults
 */
function getNodeColor(node) {
  const type = node.type || node.meta?.entity_kind;
  return COLORS[type] || COLORS[node.meta?.entity_kind] || COLORS.unknown;
}

/**
 * Get edge color, falling back to defaults
 */
function getEdgeColor(link) {
  const kind = link.kind || link.meta?.relation_type;
  return EDGE_COLORS[kind] || EDGE_COLORS.default;
}

function renderLegend() {
  if (!els.entitiesGraphLegend) return;
  els.entitiesGraphLegend.innerHTML = `
    <div class="flex flex-wrap gap-3 items-start">
      ${Object.entries(COLORS)
        .map(
          ([k, v]) => `
        <div class="flex items-center gap-2">
          <span class="inline-block w-3 h-3 rounded-full" style="background:${v}"></span>
          <span>${escapeHtml(k)}</span>
        </div>
      `
        )
        .join('')}
      <span class="text-slate-400">•</span>
      <div class="flex flex-wrap gap-2 text-[11px]">
        ${Object.entries(EDGE_COLORS)
          .filter(([k]) => k !== 'default')
          .map(
            ([k, v]) =>
              `<span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-0.5" style="background:${v}"></span>${escapeHtml(
                k
              )}</span>`
          )
          .join('')}
      </div>
    </div>
  `;
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
    node.type === 'entity' || node.meta?.entity_kind
      ? `<div class="text-xs uppercase text-slate-500">Entity</div>
         <div class="flex flex-wrap gap-1 text-xs">
           ${pill(node.meta?.entity_kind || node.type || 'entity')}
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

  els.entitiesGraphDetails.innerHTML = `
    <div class="flex items-center justify-between">
      <div>
        <div class="text-xs uppercase tracking-wide text-slate-500">Details</div>
        <div class="text-sm font-semibold break-all">${escapeHtml(node.label || node.id)}</div>
        <div class="text-xs text-slate-500">
          ${escapeHtml(node.type || 'unknown')} • score ${escapeHtml(fmt(node.score))} • count ${escapeHtml(fmt(node.count))}
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
          data-node-type="${escapeHtml(node.type || 'unknown')}"
          class="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs font-semibold text-slate-700 dark:text-slate-100 hover:border-brand-400 dark:hover:border-brand-500"
        >
          Expand
        </button>
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
function formatMetaValue(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') {
    // Format nested objects
    if (Array.isArray(value)) {
      return value.map(v => formatMetaValue(v)).join(', ');
    }
    // Extract meaningful fields from object
    const meaningful = ['name', 'title', 'label', 'type', 'role', 'value', 'description'];
    for (const key of meaningful) {
      if (value[key]) return escapeHtml(String(value[key]));
    }
    // Fallback: show first few key-value pairs
    const entries = Object.entries(value).slice(0, 3);
    if (entries.length === 0) return '—';
    return entries.map(([k, v]) => `${k}: ${formatMetaValue(v)}`).join(', ');
  }
  return escapeHtml(String(value));
}

/**
 * Lookup a node's label by ID from the current graph data
 */
function lookupNodeLabel(nodeId) {
  if (!nodeId) return null;
  const node = filteredNodes.find(n => n.id === nodeId || n.id === nodeId?.id);
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
  const relationshipsSection = detail?.relationships && detail.relationships.length > 0
    ? `
      <div>
        <div class="text-xs uppercase text-slate-500 mb-1">Relationships (${detail.relationships.length})</div>
        <ul class="text-xs space-y-1">
          ${detail.relationships.map(r => {
            const direction = r.direction === 'outgoing' ? '→' : '←';
            const other = r.direction === 'outgoing' 
              ? `<b class="text-blue-600">${escapeHtml(r.target_name || 'Unknown')}</b> <span class="text-slate-400">(${escapeHtml(r.target_kind || 'entity')})</span>`
              : `<b class="text-blue-600">${escapeHtml(r.source_name || 'Unknown')}</b> <span class="text-slate-400">(${escapeHtml(r.source_kind || 'entity')})</span>`;
            const relType = escapeHtml(formatRelationType(r.type || 'related'));
            const confidence = r.confidence ? ` <span class="text-slate-400">confidence: ${r.confidence}</span>` : '';
            return `<li class="py-1 border-b border-slate-100 dark:border-slate-800 last:border-0">${direction} <span class="px-1 py-0.5 bg-slate-100 dark:bg-slate-800 rounded text-[10px]">${relType}</span> ${other}${confidence}</li>`;
          }).join('')}
        </ul>
      </div>
    `
    : '';

  // Get kind from meta or node type
  const kind = meta.kind || node.type || 'entity';
  const kindColor = COLORS[kind] || COLORS.entity;

  return `
    <div class="space-y-3">
      <div class="flex items-center gap-2">
        <span class="inline-block w-3 h-3 rounded-full" style="background:${kindColor}"></span>
        <span class="text-xs uppercase text-slate-500">${escapeHtml(kind)}</span>
      </div>
      <div class="text-lg font-semibold break-all">${escapeHtml(node.label || meta.name || node.id)}</div>
      ${meta.last_seen ? `<div class="text-xs text-slate-500">Last seen: ${escapeHtml(meta.last_seen)}</div>` : ''}
      ${node.score ? `<div class="text-xs"><span class="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900 rounded">score: ${escapeHtml(fmt(node.score))}</span></div>` : ''}
      ${node.count ? `<div class="text-xs"><span class="px-1.5 py-0.5 bg-green-100 dark:bg-green-900 rounded">mentions: ${escapeHtml(fmt(node.count))}</span></div>` : ''}
      <div>
        <div class="text-xs uppercase text-slate-500 mb-1">Details</div>
        ${metaTable}
      </div>
      ${relationshipsSection}
      <div>
        <div class="text-xs uppercase text-slate-500 mb-1">Graph Connections (${connections.length})</div>
        ${connList}
      </div>
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
  return filterEls.nodeFilters()
    .filter((c) => c.checked)
    .map((c) => c.value);
}

function getEdgeKindFilters() {
  return filterEls.edgeFilters()
    .filter((c) => c.checked)
    .map((c) => c.value);
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
    const ek = (n.meta?.entity_kind || '').toLowerCase();
    return nodeTypes.has(t) || nodeTypes.has(ek) || (nodeTypes.has('entity') && t === 'unknown');
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

function shouldAnimateLink(l) {
  const key = `${l.source?.id || l.source}-${l.target?.id || l.target}-${l.kind || ''}`;
  return pseudoRandomFromKey(key) < PARTICLE_PROB;
}

async function fetchGraph() {
  const base = val('base-url') || '';
  const q = encodeURIComponent(els.entitiesGraphQuery?.value || '');
  const type = encodeURIComponent(els.entitiesGraphType?.value || '');
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
    .nodeColor((n) => COLORS[n.type] || COLORS[n.meta?.entity_kind] || COLORS.unknown)
    .nodeVal((n) => Math.max(2, (n.count || 1) * 0.4 + (n.score || 0) * 2))
    .linkColor((l) => EDGE_COLORS[l.kind] || EDGE_COLORS.default)
    .linkWidth((l) => linkWidthFromWeight(l.weight))
    .linkDirectionalParticles((l) => (shouldAnimateLink(l) ? 1 : 0))
    .linkDirectionalParticleWidth((l) => Math.max(PARTICLE_WIDTH_BASE, (l.weight || 1) * 0.6))
    .linkDirectionalParticleSpeed(() => PARTICLE_SPEED)
    .linkLabel(
      (l) => {
        // For relationship edges, show the specific relation_type from metadata
        const displayKind = l.kind === 'relationship' && l.meta?.relation_type 
          ? l.meta.relation_type 
          : l.kind || 'link';
        
        return `${displayKind}${l.weight ? ` (w:${l.weight})` : ''}${
          l.meta && Object.keys(l.meta).length
            ? `\n${Object.entries(l.meta)
                .filter(([k]) => k !== 'relation_type') // Don't duplicate relation_type
                .map(([k, v]) => `${k}: ${fmt(v)}`)
                .join('\n')}`
            : ''
        }`;
      }
    )
    .onNodeClick((n) => {
      selectedNodeId = n.id;
      renderDetails(n, filteredLinks);
      openNodeModal(n);
    });

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
    // Re-render legend with updated colors
    renderLegend();
    
    const data = await fetchGraph();
    currentNodes = data.nodes || [];
    currentLinks = data.links || [];
    applyFilters(currentNodes, currentLinks);
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

  [...filterEls.nodeFilters(), ...filterEls.edgeFilters()].forEach((c) =>
    c.addEventListener('change', async () => {
      applyFilters(currentNodes, currentLinks);
      await renderGraph();
    })
  );
  filterEls.depth()?.addEventListener('change', async () => {
    applyFilters(currentNodes, currentLinks);
    await renderGraph();
  });

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

  await loadAndRender();
}
