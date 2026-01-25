import { els } from './config.js';
import { chips, pill } from './ui.js';
import { showModal } from './modals.js';
import { setPagesCache } from './state.js';

function renderStructuredData(structured) {
  if (!Array.isArray(structured) || !structured.length) return '';
  const first = structured[0] || {};
  const img = first.image || (first.logo && first.logo.url);
  return `
    <div class="space-y-2">
      ${first.headline ? `<div class="text-sm font-semibold">${first.headline}</div>` : ''}
      ${first.datePublished ? `<div class="text-xs text-slate-500">Published: ${first.datePublished}</div>` : ''}
      ${first.dateModified ? `<div class="text-xs text-slate-500">Updated: ${first.dateModified}</div>` : ''}
      ${first.publisher?.name ? `<div class="text-xs text-slate-500">Publisher: ${first.publisher.name}</div>` : ''}
      ${img ? `<img src="${img}" alt="${first.headline || 'preview'}" class="rounded-lg border border-slate-200 dark:border-slate-800 w-full object-cover max-h-56">` : ''}
      <details class="text-xs"><summary class="cursor-pointer font-semibold">Structured data (JSON-LD)</summary>
        <pre class="mt-2 bg-slate-100 dark:bg-slate-800 p-2 rounded overflow-auto">${JSON.stringify(structured, null, 2)}</pre>
      </details>
    </div>
  `;
}

export function showPageDetailModal(payload) {
  const content = payload.content || {};
  const meta = content.metadata || {};
  const text = content.text || '';
  const og = meta.og_title || meta.title || payload.title || payload.og_title;
  const structured = payload.structured_data || meta.structured_data || [];

  showModal({
    title: 'Page Detail',
    size: 'lg',
    content: `
      <div class="space-y-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Page Detail</p>
          <h3 class="text-lg font-bold text-slate-900 dark:text-white break-all">${payload.url || 'Selected page'}</h3>
          ${og ? `<div class="text-sm text-slate-600 dark:text-slate-300 mt-1">${og}</div>` : ''}
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="space-y-3">
            <div class="text-xs font-semibold text-slate-500 uppercase">Overview</div>
            <div class="text-sm text-slate-700 dark:text-slate-300 space-y-1">
              ${chips([meta.content_type || 'Unknown type', meta.language, meta.site_name])}
              ${meta.text_length ? `<div class="text-xs text-slate-500">${Math.round(meta.text_length/1024)} KB</div>` : ''}
              ${meta.last_fetch_at ? `<div class="text-xs text-slate-500">Fetched: ${meta.last_fetch_at}</div>` : ''}
            </div>
            ${renderStructuredData(structured)}
          </div>
          <div class="space-y-3">
            <div class="text-xs font-semibold text-slate-500 uppercase">Preview</div>
            <div class="bg-slate-50 dark:bg-slate-900 p-3 rounded-lg border border-slate-200 dark:border-slate-800 text-xs font-mono h-64 overflow-y-auto whitespace-pre-wrap text-slate-700 dark:text-slate-200">
              ${text.slice(0, 5000)}${text.length > 5000 ? '...' : ''}
            </div>
          </div>
        </div>
      </div>
    `
  });
}

function renderPageCard(p) {
  const size = p.text_length ? `${Math.round(p.text_length / 1024)} KB` : '';
  const summary = p.summary || (p.content && p.content.text ? p.content.text.slice(0, 240) : '');
  const highConf = p.has_high_confidence_intel ? pill('high confidence') : '';
  const chipsRow = [
    p.entity_type && pill(p.entity_type),
    p.page_type && pill(p.page_type),
    p.score != null && pill(`score ${p.score}`),
    size && pill(size),
    highConf,
  ].filter(Boolean).join('');

  return `
    <article class="p-3 border rounded-lg border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 hover:border-brand-300 transition cursor-pointer" data-page-url="${p.url}">
      <div class="flex justify-between items-start gap-2">
        <div class="w-full min-w-0">
          <h5 class="text-sm font-semibold text-slate-900 dark:text-white break-all">${p.url}</h5>
          <div class="text-[11px] text-slate-500 flex flex-wrap gap-1 mt-1">
            ${chipsRow}
          </div>
          ${summary ? `<p class="text-xs text-slate-600 dark:text-slate-300 mt-2 line-clamp-2">${summary}</p>` : ''}
        </div>
      </div>
    </article>
  `;
}

export function renderPages(pages) {
  setPagesCache(pages || []);
  if (!els.pagesList) return;

  if (!pages || !pages.length) {
    els.pagesList.innerHTML = '<div class="p-4 text-sm text-slate-500">No pages match your filters.</div>';
    return;
  }

  els.pagesList.innerHTML = pages.map(renderPageCard).join('');
}
