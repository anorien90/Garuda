import { els, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderIntel } from '../render-intel.js';

export async function searchIntel(e) {
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
  } catch (err) {
    els.results.innerHTML = `<div class="p-4 text-rose-500">${err.message}</div>`;
  }
}
