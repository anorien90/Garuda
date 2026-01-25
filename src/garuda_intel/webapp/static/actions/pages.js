import { els } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderPages, showPageDetailModal } from '../render-pages.js';
import { getPagesCache } from '../state.js';

export async function loadPages(options = {}) {
  if (!els.pagesList) return;
  if (options.clientOnly) {
    renderPages(getPagesCache());
    return;
  }
  els.pagesList.innerHTML = '<div class="p-4 animate-pulse">Fetching pages...</div>';
  try {
    const limit = (els.pagesLimit && els.pagesLimit.value) || 100;
    const q = (els.pagesSearch && els.pagesSearch.value) || '';
    const params = new URLSearchParams({ limit });
    if (q) params.set('q', q);
    const res = await fetchWithAuth(`/api/pages?${params.toString()}`);
    renderPages(await res.json());
  } catch (err) {
    els.pagesList.innerHTML = `<div class="p-4 text-rose-500">${err.message}</div>`;
  }
}

export async function loadPageDetail(url) {
  if (els.pageDetail) els.pageDetail.innerHTML = '<div class="p-4 animate-pulse text-sm">Fetching page content...</div>';
  try {
    const res = await fetchWithAuth(`/api/page?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    showPageDetailModal(data);
    if (els.pageDetail) els.pageDetail.innerHTML = '';
  } catch (err) {
    if (els.pageDetail) els.pageDetail.innerHTML = `<div class="p-4 text-rose-500">Error: ${err.message}</div>`;
  }
}
