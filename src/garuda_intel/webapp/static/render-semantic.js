export function renderSemantic(data, target) {
  if (!target) return;
  target.innerHTML = '';
  const hits = (data && data.semantic) ? data.semantic : [];

  if (!hits.length) {
    target.innerHTML = '<div class="p-4 text-sm text-slate-500">No semantic matches found.</div>';
    return;
  }

  hits.forEach((h) => {
    const card = document.createElement('div');
    card.className = 'p-3 border-b border-slate-100 dark:border-slate-800 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-800/50';
    card.innerHTML = `
        <div class="flex justify-between text-xs mb-1">
            <a href="${h.url}" target="_blank" class="text-brand-600 hover:underline truncate w-3/4">${h.url}</a>
            <span class="text-slate-400 font-mono">${h.score ? h.score.toFixed(3) : '0.00'}</span>
        </div>
        <p class="text-sm text-slate-700 dark:text-slate-300 line-clamp-2">"${h.text || h.snippet || 'No text content'}"</p>
        <div class="mt-1 flex gap-2">
            ${h.entity ? `<span class="text-[10px] bg-slate-100 dark:bg-slate-800 px-1 rounded text-slate-500">${h.entity}</span>` : ''}
            ${h.page_type ? `<span class="text-[10px] bg-slate-100 dark:bg-slate-800 px-1 rounded text-slate-500">${h.page_type}</span>` : ''}
        </div>
    `;
    target.appendChild(card);
  });
}
