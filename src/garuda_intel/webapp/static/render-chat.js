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
  
  // Show RAG usage status
  const ragCount = payload.rag_hits_count || 0;
  const sqlCount = payload.sql_hits_count || 0;
  
  if (ragCount > 0) {
    metaBadges.push(pill(`🧠 RAG: ${ragCount} semantic hits`, 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200'));
  }
  if (sqlCount > 0) {
    metaBadges.push(pill(`📊 SQL: ${sqlCount} keyword hits`, 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200'));
  }
  
  if (payload.online_search_triggered) {
    const reason = payload.crawl_reason || 'Insufficient local data';
    metaBadges.push(pill(`🌐 Live Crawl: ${reason}`, 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'));
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
        <h5 class="text-xs font-bold uppercase text-slate-500 mb-2">Sources & Context (${(payload.context || []).length} total)</h5>
        <div class="space-y-2">
            ${(payload.context || []).length
              ? (payload.context || []).map(ctx => {
                  const sourceClass = ctx.source === 'rag' 
                    ? 'border-purple-200 dark:border-purple-800/50 bg-purple-50/50 dark:bg-purple-900/10'
                    : 'border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900';
                  const sourceLabel = ctx.source === 'rag' ? '🧠 RAG' : '📊 SQL';
                  const scoreDisplay = ctx.score ? `Score: ${ctx.score.toFixed(3)}` : '';
                  const kindDisplay = ctx.kind ? ` • ${ctx.kind}` : '';
                  
                  return `
                  <div class="text-xs p-2 border rounded ${sourceClass}">
                      <div class="flex justify-between mb-1">
                          <span class="font-semibold text-xs">${sourceLabel}${kindDisplay}</span>
                          <span class="text-slate-500 dark:text-slate-400">${scoreDisplay}</span>
                      </div>
                      <div class="text-brand-600 dark:text-brand-400 mb-1 truncate text-xs">
                          ${ctx.url || 'Database Context'}
                      </div>
                      ${ctx.entity ? `<div class="text-slate-500 dark:text-slate-400 text-xs mb-1">Entity: ${ctx.entity}</div>` : ''}
                      <p class="text-slate-600 dark:text-slate-400 line-clamp-2">"${ctx.snippet || ctx.text || ''}"</p>
                  </div>
              `}).join('')
              : '<div class="text-xs text-slate-500">No context returned.</div>'
            }
        </div>
    </div>
  `;
  els.chatAnswer.appendChild(div);
}
