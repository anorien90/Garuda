import { pill, collapsible, renderKeyValTable } from './ui.js';
import { setLastIntelHits } from './state.js';

function renderIntelCard(hit) {
  const info = hit.data?.basic_info || hit.basic_info || {};
  const data = hit.data || hit;
  const metrics = data.metrics || [];
  const persons = data.persons || [];
  const jobs = data.jobs || [];
  const locations = data.locations || [];
  const events = data.events || [];
  const products = data.products || [];
  const financials = data.financials || [];

  const detailContent = `
    <div class="space-y-3">
      ${renderKeyValTable(info)}
      ${metrics.length ? collapsible('Metrics', renderKeyValTable(Object.fromEntries(metrics.map((m, i) => [`#${i + 1}`, `${m.type || ''} ${m.value || ''} ${m.unit || ''} ${m.date || ''}`])))) : ''}
      ${financials.length ? collapsible('Financials', financials.map(f => `<div>${pill(f.year || '')} ${pill(f.currency || '')} Rev: ${f.revenue || ''} Profit: ${f.profit || ''}</div>`).join('')) : ''}
      ${events.length ? collapsible('Events', events.map(ev => `<div class="mb-1"><b>${ev.title || ''}</b> ${ev.date || ''}<div class="text-xs">${ev.description || ''}</div></div>`).join('')) : ''}
      ${products.length ? collapsible('Products', products.map(p => `<div class="mb-1"><b>${p.name || ''}</b> — ${p.status || ''}<div class="text-xs">${p.description || ''}</div></div>`).join('')) : ''}
      ${persons.length ? collapsible('People', persons.map(p => `<div class="mb-1"><b>${p.name || ''}</b> ${p.title || ''} ${p.role || ''}<div class="text-xs">${p.bio || ''}</div></div>`).join('')) : ''}
      ${jobs.length ? collapsible('Jobs', jobs.map(j => `<div class="mb-1"><b>${j.title || ''}</b> @ ${j.location || ''}<div class="text-xs">${j.description || ''}</div></div>`).join('')) : ''}
      ${locations.length ? collapsible('Locations', locations.map(l => `<div class="mb-1">${pill(l.type || '')} ${l.city || ''}, ${l.country || ''}<div class="text-xs">${l.address || ''}</div></div>`).join('')) : ''}
      <details class="text-xs"><summary class="font-bold">Raw JSON</summary><pre class="mt-1 p-2 bg-slate-900 text-slate-100 rounded text-xs whitespace-pre-wrap">${JSON.stringify(hit.data || hit, null, 2)}</pre></details>
    </div>
  `;

  const idPill = hit.id ? pill(`id: ${hit.id}`) : '';
  const entityIdPill = hit.entity_id ? pill(`entity_id: ${hit.entity_id}`) : '';

  return `
  <article class="rounded-lg border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/70 p-4 space-y-3">
    <div class="flex justify-between items-center">
      <div>
        <h4 class="text-lg font-semibold text-slate-900 dark:text-white">${hit.entity || info.official_name || ''}</h4>
        <div class="flex flex-wrap gap-1 text-[11px] text-brand-600">${idPill}${entityIdPill}${hit.entity_type ? pill(hit.entity_type) : ''}</div>
      </div>
      <span class="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded" title="Confidence">${hit.confidence ?? (hit.score?.toFixed?.(2) ?? '')}</span>
    </div>
    ${info.description ? `<div class="text-sm text-slate-700 dark:text-slate-300">${info.description}</div>` : ''}

    <div class="flex flex-wrap gap-2 mt-2">
      ${info.industry ? pill(info.industry) : ''}
      ${info.ticker ? pill('Ticker: ' + info.ticker) : ''}
      ${info.founded ? pill('Founded: ' + info.founded) : ''}
      ${info.website ? pill('🌐 ' + info.website) : ''}
    </div>
    <div class="flex gap-2 mt-2">
      <button class="inline-flex items-center px-3 py-1.5 rounded bg-brand-600 text-white text-xs font-semibold hover:bg-brand-500" data-intel-detail>View details</button>
      ${hit.url ? `<a class="text-xs text-brand-600 underline" href="${hit.url}" target="_blank" rel="noreferrer">Source</a>` : ''}
    </div>
    <template data-intel-detail-content>${detailContent}</template>
  </article>
  `;
}

export function renderIntel(results, target) {
  if (!target) return;
  target.innerHTML = '';
  const list = Array.isArray(results) ? results : [results];

  if (!list.length) {
    target.innerHTML = '<div class="p-4 text-sm text-slate-500">No results found.</div>';
    setLastIntelHits([]);
    return;
  }
  setLastIntelHits(list);
  target.innerHTML = list.map(renderIntelCard).join('');
}
