


function pill(text) {
  return `<span class="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 px-2 py-0.5 text-[10px] font-medium">${text}</span>`;
}

function truncate(str, len = 320) { 
  if (!str) return '';
  return str.length > len ? `${str.slice(0, len)}…` : str;
}

function renderSemanticHit(hit, idx) {
  const url = hit.url || '';
  const title = hit.entity || hit.page_type || hit.kind || 'Result';
  const body = hit.text || hit.snippet || '(no snippet)';
  const score = hit.score != null ? hit.score.toFixed(3) : '';
  const chips = [
    hit.kind && pill(hit.kind),
    hit.entity_type && pill(hit.entity_type),
    hit.page_type && pill(hit.page_type),
    score && pill(`score ${score}`),
  ].filter(Boolean).join('');

  return `
    <article class="border border-slate-200 dark:border-slate-800 rounded-lg p-3 bg-white dark:bg-slate-900 space-y-2 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="text-[11px] text-slate-500">#${idx + 1}</div>
          ${
            url
              ? `<a class="text-sm font-semibold break-all text-blue-600 hover:underline" href="${url}" target="_blank" rel="noreferrer">${title}</a>`
              : `<div class="text-sm font-semibold break-all">${title}</div>`
          }
        </div>
        ${score ? `<div class="text-[11px] px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">score ${score}</div>` : ''}
      </div>
      <p class="text-xs text-slate-700 dark:text-slate-200 leading-relaxed">${truncate(body, 500)}</p>
      ${chips ? `<div class="flex flex-wrap gap-1 text-[10px] text-slate-500">${chips}</div>` : ''}
    </article>
  `;
}

export function renderSemantic(data, target) {
  if (!target) return;
  const hits = Array.isArray(data?.semantic) ? data.semantic : [];
  if (!hits.length) {
    target.innerHTML = '<div class="p-4 text-sm text-slate-500">No semantic matches found.</div>';
    return;
  }
  target.innerHTML = `
    <div class="space-y-3">
      ${hits.map((h, i) => renderSemanticHit(h, i)).join('')}
    </div>
  `;
}
