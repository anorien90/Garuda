import { els } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderPages, showPageDetailModal } from '../render-pages.js';
import { getPagesCache, setPagesCache } from '../state.js';

function bindFilters() {
  const inputs = [
    els.pagesSearch,
    els.pagesEntityFilter,
    els.pagesTypeFilter,
    els.pagesMinScore,
    els.pagesSort,
  ].filter(Boolean);

  inputs.forEach((el) => {
    el.addEventListener('input', () => loadPages({ clientOnly: false }));
    el.addEventListener('change', () => loadPages({ clientOnly: false }));
  });

  if (els.pagesLoad) {
    els.pagesLoad.addEventListener('click', () => loadPages({ clientOnly: false }));
  }
}

export async function loadPages(options = {}) {
  if (!els.pagesList) return;

  if (options.clientOnly) {
    renderPages(getPagesCache());
    return;
  }

  els.pagesList.innerHTML = '<div class="p-4 animate-pulse">Fetching pages...</div>';
  try {
    const params = new URLSearchParams();
    const limit = (els.pagesLimit && els.pagesLimit.value) || 100;
    params.set('limit', limit);

    const q = (els.pagesSearch && els.pagesSearch.value) || '';
    const entity = (els.pagesEntityFilter && els.pagesEntityFilter.value) || '';
    const pageType = (els.pagesTypeFilter && els.pagesTypeFilter.value) || '';
    const minScore = (els.pagesMinScore && els.pagesMinScore.value) || '';
    const sort = (els.pagesSort && els.pagesSort.value) || 'fresh';

    if (q) params.set('q', q);
    if (entity) params.set('entity_type', entity);
    if (pageType) params.set('page_type', pageType);
    if (minScore !== '') params.set('min_score', minScore);
    if (sort) params.set('sort', sort);

    const res = await fetchWithAuth(`/api/pages?${params.toString()}`);
    const data = await res.json();
    setPagesCache(data);
    renderPages(data);
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

bindFilters();

if (els.pagesList) {
  els.pagesList.addEventListener('click', (e) => {
    const article = e.target.closest('[data-page-url]');
    if (article?.dataset.pageUrl) {
      loadPageDetail(article.dataset.pageUrl);
    }
  });
}
