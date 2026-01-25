import { els, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderSemantic } from '../render-semantic.js';

export async function semanticSearch(e) {
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
  } catch (err) {
    els.semanticResults.innerHTML = `<div class="p-4 text-rose-500">${err.message}</div>`;
  }
}
