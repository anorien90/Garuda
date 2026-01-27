import { els } from './config.js';
import { fetchWithAuth } from './api.js';
import { setLastStatusData, getLastStatusData } from './state.js';
import { setStatusBadge } from './ui.js';
import { showModal } from './modals.js';

function computeHealthColor(health) {
  const services = health?.services || [];
  if (!services.length) return health?.status === 'ok' ? 'bg-emerald-500' : 'bg-rose-500';
  const failed = services.filter(s => (s.status || '').toLowerCase() !== 'ok').length;
  const ratio = failed / services.length;
  if (ratio === 0) return 'bg-emerald-500';
  if (ratio < 0.34) return 'bg-amber-300';
  if (ratio < 0.67) return 'bg-amber-500';
  if (ratio < 1) return 'bg-amber-700';
  return 'bg-rose-600';
}

export function renderHealthIndicator(health) {
  if (!els.healthIndicator) return;
  const color = computeHealthColor(health);
  els.healthIndicator.innerHTML = `
    <button class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold text-white ${color}">
      <span class="w-2.5 h-2.5 rounded-full bg-white/70"></span>
      ${health?.status || 'unknown'}
    </button>
  `;
  els.healthIndicator.onclick = () => showHealthPopup();
}

export function showHealthPopup() {
  const lastStatusData = getLastStatusData();
  if (!lastStatusData) return;
  const svcRows = (lastStatusData.services || []).map(s => `
    <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 py-1">
      <div>
        <div class="font-semibold">${s.name || 'Service'}</div>
        <div class="text-xs text-slate-500">${s.detail || ''}</div>
      </div>
        <span class="text-xs px-2 py-0.5 rounded ${computeHealthColor({ services: [s] })} text-white">${s.status || ''}</span>
    </div>
  `).join('') || '<div class="text-sm text-slate-500">No per-service data available.</div>';

  const coreItems = [
    { label: 'Database', ok: lastStatusData.db_ok, info: lastStatusData.db_url || '' },
    { label: 'Vector Store', ok: lastStatusData.qdrant_ok, info: lastStatusData.qdrant_url || '' },
    { label: 'Embedding', ok: lastStatusData.embedding_loaded, info: lastStatusData.model || '' },
    { label: 'Ollama', ok: !!lastStatusData.ollama_url, info: lastStatusData.ollama_url || '' },
  ].map(item => `
    <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 py-1">
      <div class="text-sm">${item.label}</div>
      <span class="text-xs px-2 py-0.5 rounded ${item.ok ? 'bg-emerald-500' : 'bg-rose-600'} text-white">${item.ok ? 'ok' : 'fail'}</span>
    </div>
    <div class="text-[11px] text-slate-500 mb-1">${item.info || ''}</div>
  `).join('');

  showModal({
    title: 'System Health',
    size: 'md',
    content: `
      <div class="space-y-3">
        <div class="text-sm">Overall status: <span class="font-semibold">${lastStatusData.status || (lastStatusData.db_ok && lastStatusData.qdrant_ok ? 'ok' : 'degraded')}</span></div>
        <div class="space-y-2">${coreItems}</div>
        <div class="pt-2">
          <div class="text-xs font-semibold uppercase text-slate-500">Services</div>
          ${svcRows}
        </div>
      </div>
    `
  });
}

export function renderStatus(data) {
  setLastStatusData(data || null);

  if (els.statusCards) els.statusCards.innerHTML = '';
  if (!data || typeof data !== 'object') {
    if (els.statusCards) els.statusCards.innerHTML = '<div class="p-4 text-sm text-rose-500">Invalid status data received.</div>';
    return;
  }

  setStatusBadge(els.statusBadges.api, true);
  setStatusBadge(els.statusBadges.db, !!data.db_ok);
  setStatusBadge(els.statusBadges.vector, !!data.qdrant_ok);
  setStatusBadge(els.statusBadges.llm, !!data.embedding_loaded);

  renderHealthIndicator({ status: data.status || (data.db_ok && data.qdrant_ok ? 'ok' : 'degraded'), services: data.services || [] });

  if (!els.statusCards) return;

  const items = [
    { label: 'Database', status: data.db_ok, info: data.db_url || '' },
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

export async function refreshStatus() {
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
