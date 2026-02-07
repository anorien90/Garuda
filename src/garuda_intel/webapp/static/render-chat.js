import { els } from './config.js';
import { pill, collapsible } from './ui.js';

export function renderChat(payload) {
  if (!els.chatAnswer) return;
  els.chatAnswer.innerHTML = '';
  
  // Always show an answer - even if it's empty or null
  let answer = payload?.answer || '';
  
  // If answer is missing, empty, or looks like a refusal, provide a meaningful fallback
  if (!answer || answer.trim() === '') {
    if (payload?.context && payload.context.length > 0) {
      // Try to build an answer from context snippets
      const snippets = payload.context
        .slice(0, 3)
        .map(ctx => ctx.snippet || ctx.text || '')
        .filter(s => s.trim() !== '');
      
      if (snippets.length > 0) {
        answer = "Based on the available information:\n\n" + snippets.join("\n\n");
      } else {
        answer = "I searched through local data and online sources but couldn't find a definitive answer. Try refining your question or providing more context.";
      }
    } else {
      answer = "No relevant information was found in local data or online sources. Try a different question or crawl some relevant pages first.";
    }
  }

  const metaBadges = [];
  
  // Show RAG usage status
  const ragCount = payload.rag_hits_count || 0;
  const graphCount = payload.graph_hits_count || 0;
  const sqlCount = payload.sql_hits_count || 0;
  
  if (ragCount > 0) {
    metaBadges.push(pill(`🧠 RAG: ${ragCount} semantic hits`, 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200'));
  }
  if (graphCount > 0) {
    metaBadges.push(pill(`🕸️ Graph: ${graphCount} relation hits`, 'bg-teal-100 dark:bg-teal-900/30 text-teal-800 dark:text-teal-200'));
  }
  if (sqlCount > 0) {
    metaBadges.push(pill(`📊 SQL: ${sqlCount} keyword hits`, 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200'));
  }
  
  // Show search cycle progress
  const cyclesCompleted = payload.search_cycles_completed || 0;
  const maxCycles = payload.max_search_cycles || 0;
  if (maxCycles > 0) {
    metaBadges.push(pill(`🔄 Search Cycles: ${cyclesCompleted}/${maxCycles}`, 'bg-slate-100 dark:bg-slate-900/30 text-slate-800 dark:text-slate-200'));
  }
  
  if (payload.retry_attempted) {
    metaBadges.push(pill('🔄 Retry with paraphrasing', 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200'));
  }
  
  if (payload.online_search_triggered) {
    const reason = payload.crawl_reason || 'Insufficient local data';
    metaBadges.push(pill(`🌐 Live Crawl: ${reason}`, 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'));
  }
  if (payload.entity) {
    metaBadges.push(pill(`Entity: ${payload.entity}`));
  }

  const liveUrls = Array.isArray(payload.live_urls) ? payload.live_urls : [];
  
  // Paraphrased queries section
  let paraphrasedSection = '';
  if (payload.retry_attempted && payload.paraphrased_queries && payload.paraphrased_queries.length > 0) {
    const paraphrasedList = payload.paraphrased_queries
      .map(q => `<li class="text-xs text-slate-700 dark:text-slate-300">"${q}"</li>`)
      .join('');
    paraphrasedSection = `
      <div class="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
        <h5 class="text-xs font-bold text-amber-800 dark:text-amber-200 mb-1">🔄 Paraphrased Queries</h5>
        <ul class="list-disc list-inside space-y-0.5">
          ${paraphrasedList}
        </ul>
      </div>
    `;
  }

  const div = document.createElement('div');
  div.className = 'space-y-4';
  div.innerHTML = `
    <div class="flex flex-wrap gap-2">${metaBadges.join(' ')}</div>

    ${paraphrasedSection}

    <div class="prose prose-sm dark:prose-invert max-w-none bg-slate-50 dark:bg-slate-800/50 p-4 rounded-lg border border-slate-100 dark:border-slate-800">
        <p>${answer.replace(/\n/g, '<br>')}</p>
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
                  let sourceClass, sourceLabel;
                  if (ctx.source === 'rag') {
                    sourceClass = 'border-purple-200 dark:border-purple-800/50 bg-purple-50/50 dark:bg-purple-900/10';
                    sourceLabel = '🧠 RAG';
                  } else if (ctx.source === 'graph') {
                    sourceClass = 'border-teal-200 dark:border-teal-800/50 bg-teal-50/50 dark:bg-teal-900/10';
                    sourceLabel = '🕸️ Graph';
                  } else {
                    sourceClass = 'border-blue-200 dark:border-blue-800/50 bg-blue-50/50 dark:bg-blue-900/10';
                    sourceLabel = '📊 SQL';
                  }
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

export function renderAutonomousInChat(data) {
  const autonomousDiv = document.getElementById('autonomous-results');
  if (!autonomousDiv) return;
  
  if (!data || data.error) {
    autonomousDiv.innerHTML = `
      <div class="text-rose-500 text-sm">
        ⚠️ Autonomous discovery error: ${data?.error || 'Unknown error'}
      </div>
    `;
    return;
  }
  
  const stats = data.statistics || {};
  const deadEnds = data.dead_ends || [];
  const gaps = data.knowledge_gaps || [];
  const crawlPlans = data.crawl_plans || [];
  const crawlResults = data.crawl_results || [];
  
  // Build summary badges
  const summaryBadges = [
    pill(`🔴 ${stats.dead_ends_found || 0} Dead Ends`, 'bg-rose-100 dark:bg-rose-900/30 text-rose-800 dark:text-rose-200'),
    pill(`❓ ${stats.gaps_found || 0} Knowledge Gaps`, 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200'),
    pill(`📋 ${stats.crawl_plans_generated || 0} Plans`, 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200'),
    pill(`✅ ${stats.crawls_executed || 0} Crawls`, 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'),
  ].join(' ');
  
  // Build dead ends section
  let deadEndsHtml = '';
  if (deadEnds.length > 0) {
    const deadEndsList = deadEnds.slice(0, 5).map(entity => {
      return `<li class="text-xs text-slate-700 dark:text-slate-300">
        <strong>${entity.name || 'Unknown'}</strong> 
        ${entity.type ? `(${entity.type})` : ''} 
        - Priority: ${(entity.priority || 0).toFixed(2)}
      </li>`;
    }).join('');
    deadEndsHtml = collapsible(
      `🔴 Dead Ends (${deadEnds.length})`,
      `<ul class="list-disc list-inside space-y-1 ml-2">${deadEndsList}</ul>`
    );
  }
  
  // Build knowledge gaps section
  let gapsHtml = '';
  if (gaps.length > 0) {
    const gapsList = gaps.slice(0, 5).map(gap => {
      return `<li class="text-xs text-slate-700 dark:text-slate-300">
        <strong>${gap.entity || 'Unknown'}</strong> - ${gap.gap_type || 'Unknown type'}: ${gap.description || 'No description'}
      </li>`;
    }).join('');
    gapsHtml = collapsible(
      `❓ Knowledge Gaps (${gaps.length})`,
      `<ul class="list-disc list-inside space-y-1 ml-2">${gapsList}</ul>`
    );
  }
  
  // Build crawl plans section
  let plansHtml = '';
  if (crawlPlans.length > 0) {
    const plansList = crawlPlans.slice(0, 5).map(plan => {
      const urls = plan.urls || [];
      const urlsPreview = urls.length > 3 
        ? urls.slice(0, 3).join(', ') + `... (+${urls.length - 3} more)`
        : urls.join(', ');
      return `<li class="text-xs text-slate-700 dark:text-slate-300">
        <strong>${plan.entity || 'Unknown'}</strong> (${urls.length} URLs): ${urlsPreview}
      </li>`;
    }).join('');
    plansHtml = collapsible(
      `📋 Crawl Plans (${crawlPlans.length})`,
      `<ul class="list-disc list-inside space-y-1 ml-2">${plansList}</ul>`
    );
  }
  
  // Build crawl results section
  let resultsHtml = '';
  if (crawlResults.length > 0) {
    const resultsList = crawlResults.map(result => {
      const pages = result.pages_crawled || 0;
      const intel = result.intel_extracted || 0;
      return `<li class="text-xs text-slate-700 dark:text-slate-300">
        <strong>${result.entity || 'Unknown'}</strong>: ${pages} pages, ${intel} intel items
      </li>`;
    }).join('');
    resultsHtml = collapsible(
      `✅ Crawl Results (${crawlResults.length})`,
      `<ul class="list-disc list-inside space-y-1 ml-2">${resultsList}</ul>`
    );
  }
  
  autonomousDiv.innerHTML = `
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <h4 class="text-sm font-bold text-indigo-800 dark:text-indigo-200">🤖 Autonomous Discovery Results</h4>
      </div>
      <div class="flex flex-wrap gap-2">
        ${summaryBadges}
      </div>
      ${deadEndsHtml}
      ${gapsHtml}
      ${plansHtml}
      ${resultsHtml}
      ${stats.dead_ends_found === 0 && stats.gaps_found === 0 
        ? '<p class="text-xs text-slate-500 italic">No knowledge gaps or dead ends found.</p>' 
        : ''}
    </div>
  `;
}
