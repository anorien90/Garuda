export function pill(text) {
  return `<span class="inline-flex items-center rounded-full bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-100 px-2 py-0.5 text-xs font-medium">${text}</span>`;
}

export function chips(arr = []) {
  return arr.filter(Boolean).map((t) => pill(t)).join(' ');
}

export function setStatusBadge(el, ok) {
  if (!el) return;
  const okCls = ['bg-emerald-500'];
  const badCls = ['bg-rose-500'];
  el.classList.remove(...okCls, ...badCls);
  el.classList.add(ok ? 'bg-emerald-500' : 'bg-rose-500');
}

export function collapsible(label, content) {
  if (!content) return '';
  return `
    <details class="text-xs my-1 group">
      <summary class="cursor-pointer font-bold">${label}</summary>
      <div class="mt-2 ml-2">${content}</div>
    </details>
  `;
}

export function renderKeyValTable(obj) {
  if (!obj || typeof obj !== 'object') return '';
  return `
    <table class="text-xs w-full mb-2">
      <tbody>
        ${Object.entries(obj).map(([k, v]) => `<tr><td class="pr-1 text-slate-400">${k}</td><td>${v}</td></tr>`).join('')}
      </tbody>
    </table>
  `;
}

// Render a single page result
export function renderCrawlPage(url, page) {
  const intel = (page.extracted_intel || []).map((fi, i) => collapsible(
    `Finding ${i + 1}`,
    [
      renderKeyValTable(fi.basic_info),
      fi.events?.length ? collapsible('Events', fi.events.map(e => `<div class="mb-1"><div class="font-semibold">${e.title || ''}</div><div class="text-slate-500">${e.date || ''}</div><div>${e.description || ''}</div></div>`).join('')) : '',
      fi.products?.length ? collapsible('Products', fi.products.map(p => `<div class="mb-1"><div class="font-semibold">${p.name || ''}</div><div>${p.description || ''}</div></div>`).join('')) : '',
    ].join('')
  )).join('');

  return `
    <article class="border border-slate-200 dark:border-slate-800 rounded-lg p-3 bg-white dark:bg-slate-900 space-y-2">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="text-xs text-slate-500 truncate">${page.domain_key || ''}</div>
          <a class="text-sm font-semibold break-all text-blue-600 hover:underline" href="${url}" target="_blank" rel="noreferrer">${url}</a>
        </div>
        <div class="text-xs px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">score ${page.score ?? ''}</div>
      </div>
      ${page.summary ? `<p class="text-xs text-slate-700 dark:text-slate-200">${page.summary}</p>` : ''}
      ${intel || '<div class="text-xs text-slate-400">No extracted intel</div>'}
      <div class="flex flex-wrap gap-1 text-[10px] text-slate-500">
        ${page.page_type ? pill(page.page_type) : ''}
        ${page.entity_type ? pill(page.entity_type) : ''}
        ${page.depth !== undefined ? pill(`depth ${page.depth}`) : ''}
        ${page.text_length ? pill(`${page.text_length} chars`) : ''}
        ${page.id ? pill(`uuid ${page.id}`) : ''}
      </div>
    </article>
  `;
}

// Render full crawl result
export function renderCrawlResult(payload) {
  if (!payload || !payload.explored_data) {
    return `<div class="text-xs text-slate-400">No crawl results</div>`;
  }
  const cards = Object.entries(payload.explored_data)
    .map(([url, page]) => renderCrawlPage(url, page))
    .join('');
  return `<div class="space-y-3">${cards}</div>`;
}
