import { els } from './config.js';
import { chips } from './ui.js';
import { showModal } from './modals.js';
import { getPagesCache, setPagesCache } from './state.js';

function renderStructuredData(structured) {
  if (!Array.isArray(structured) || !structured.length) return '';
  const first = structured[0] || {};
  const img = first.image || (first.logo && first.logo.url);
  return `
    <div class="space-y-2">
      ${first.headline ? `<div class="text-sm font-semibold">${first.headline}</div>` : ''}
      ${first.datePublished ? `<div class="text-xs text-slate-500">Published: ${first.datePublished}</div>` : ''}
      ${first.dateModified ? `<div class="text-xs text-slate-500">Updated: ${first.dateModified}</div>` : ''}
      ${first.publisher && first.publisher.name ? `<div class="text-xs text-slate-500">Publisher: ${first.publisher.name}</div>` : ''}
      ${first.author && first.author.name ? `<div class="text-xs text-slate-500">Author: ${first.author.name}</div>` : ''}
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
            <div class="text-sm text-slate-700 dark:text-slate-300">
              ${chips([meta.content_type || 'Unknown type', meta.language, meta.site_name])}
              ${meta.text_length ? `<div class="mt-1 text-xs text-slate-500">${Math.round(meta.text_length/1024)} KB</div>` : ''}
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

export function renderPages(pages) {
  setPagesCache(pages || []);
  if (!els.pagesList) return;
  const q = (els.pagesSearch?.value || '').toLowerCase().trim();
  const filtered = q
    ? getPagesCache().filter(p =>
        (p.url || '').toLowerCase().includes(q) ||
        (p.title || '').toLowerCase().includes(q) ||
        (p.page_type || '').toLowerCase().includes(q)
      )
    : getPagesCache();

  if (!filtered.length) {
    els.pagesList.innerHTML = '<div class="p-4 text-sm text-slate-500">No pages indexed.</div>';
    return;
  }

  els.pagesList.innerHTML = filtered.map((p) => `
    <article class="p-3 border rounded-lg border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 hover:border-brand-300 transition cursor-pointer" data-page-url="${p.url}">
      <div class="flex justify-between items-start">
        <div class="w-full">
            <div class="flex justify-between w-full">
                <h5 class="text-sm font-semibold text-slate-900 dark:text-white truncate w-3/4">${p.url}</h5>
                <span class="text-[10px] text-slate-400">${p.score ?? 0}</span>
            </div>
            <div class="flex gap-2 mt-1 text-xs text-slate-500">
                <span>${p.entity_type || 'Unknown Entity'}</span>
                <span>•</span>
                <span>${p.page_type || 'General'}</span>
                ${p.text_length ? `<span>• ${Math.round(p.text_length/1024)} KB</span>` : ''}
            </div>
        </div>
      </div>
    </article>
  `).join('');
}
