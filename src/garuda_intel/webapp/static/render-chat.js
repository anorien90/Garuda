import { els } from './config.js';
import { pill } from './ui.js';

export function renderChat(payload) {
  if (!els.chatAnswer) return;
  els.chatAnswer.innerHTML = '';
  if (!payload || !payload.answer) {
    els.chatAnswer.innerHTML = '<div class="p-4 text-sm text-rose-500">No answer generated.</div>';
    return;
  }

  const metaBadges = [];
  if (payload.online_search_triggered) {
    metaBadges.push(pill('Online research performed'));
  }
  if (payload.entity) {
    metaBadges.push(pill(`Entity: ${payload.entity}`));
  }

  const liveUrls = Array.isArray(payload.live_urls) ? payload.live_urls : [];

  const div = document.createElement('div');
  div.className = 'space-y-4';
  div.innerHTML = `
    <div class="flex flex-wrap gap-2">${metaBadges.join(' ')}</div>

    <div class="prose prose-sm dark:prose-invert max-w-none bg-slate-50 dark:bg-slate-800/50 p-4 rounded-lg border border-slate-100 dark:border-slate-800">
        <p>${payload.answer.replace(/\n/g, '<br>')}</p>
    </div>

    ${liveUrls.length ? `
      <div>
        <h5 class="text-xs font-bold uppercase text-slate-500 mb-2">Live URLs Crawled</h5>
        <ul class="list-disc list-inside text-xs text-brand-600 space-y-1">
          ${liveUrls.map(u => `<li><a class="underline" href="${u}" target="_blank" rel="noreferrer">${u}</a></li>`).join('')}
        </ul>
      </div>
    ` : ''}

    <div>
        <h5 class="text-xs font-bold uppercase text-slate-500 mb-2">Sources & Context</h5>
        <div class="space-y-2">
            ${(payload.context || []).length
              ? (payload.context || []).map(ctx => `
                  <div class="text-xs p-2 border border-slate-100 dark:border-slate-800 rounded bg-white dark:bg-slate-900">
                      <div class="flex justify-between text-brand-600 mb-1">
                          <span class="truncate w-3/4">${ctx.url || 'Database Context'}</span>
                          <span>${ctx.score ? ctx.score.toFixed(2) : ''}</span>
                      </div>
                      <p class="text-slate-600 dark:text-slate-400 line-clamp-2">"${ctx.snippet || ctx.text || ''}"</p>
                  </div>
              `).join('')
              : '<div class="text-xs text-slate-500">No context returned.</div>'
            }
        </div>
    </div>
  `;
  els.chatAnswer.appendChild(div);
}
