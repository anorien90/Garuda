import { els, val, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderCrawlResult } from '../ui.js';

export async function runIntelligentCrawl(e) {
  if (e) e.preventDefault();
  
  const entityName = val('intelligent-entity-name');
  if (!entityName || !entityName.trim()) {
    alert('Please enter an entity name');
    return;
  }
  
  const outputPanel = getEl('crawl-output-panel');
  if (outputPanel) {
    outputPanel.innerHTML = '<div class="p-4 animate-pulse text-xs text-blue-600 dark:text-blue-400">🧠 Analyzing entity and generating intelligent crawl plan...</div>';
  }
  
  try {
    const body = {
      entity_name: entityName.trim(),
      entity_type: val('intelligent-entity-type') || null,
      max_pages: 50,
      max_depth: 2
    };

    const res = await fetchWithAuth('/api/crawl/intelligent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (outputPanel) {
      outputPanel.innerHTML = renderIntelligentCrawlResult(data);
    }
  } catch (err) {
    if (outputPanel) {
      outputPanel.innerHTML = `<div class="p-4 rounded-lg bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
        <strong>Error:</strong> ${err.message}
      </div>`;
    }
  }
}

function renderIntelligentCrawlResult(data) {
  const plan = data.plan || {};
  const results = data.results || {};
  
  let html = '<div class="space-y-4">';
  
  // Crawl Plan Section
  html += `
    <div class="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
      <h4 class="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">📋 Crawl Plan</h4>
      <div class="grid gap-2 text-xs">
        <div><span class="font-medium">Mode:</span> <span class="px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-800">${plan.mode || 'unknown'}</span></div>
        <div><span class="font-medium">Strategy:</span> ${plan.strategy || 'N/A'}</div>
        <div><span class="font-medium">Entity:</span> ${plan.entity_name || results.entity_name || 'N/A'}</div>
      </div>
    </div>
  `;
  
  // Gap Analysis (if in gap-filling mode)
  if (plan.mode === 'gap_filling' && plan.analysis) {
    const analysis = plan.analysis;
    html += `
      <div class="p-4 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
        <h4 class="text-sm font-semibold text-amber-900 dark:text-amber-100 mb-2">🎯 Gap Analysis</h4>
        <div class="grid gap-2 text-xs">
          <div><span class="font-medium">Completeness:</span> <span class="font-bold">${(analysis.completeness_score || 0).toFixed(1)}%</span></div>
          <div><span class="font-medium">Missing Fields:</span> ${(analysis.missing_fields || []).length}</div>
          <div><span class="font-medium">Intelligence Records:</span> ${analysis.intelligence_count || 0}</div>
        </div>
        ${(analysis.prioritized_gaps && analysis.prioritized_gaps.length > 0) ? `
          <div class="mt-3 pt-3 border-t border-amber-200 dark:border-amber-700">
            <div class="text-xs font-medium text-amber-900 dark:text-amber-100 mb-1">Top Missing Fields:</div>
            <div class="flex flex-wrap gap-1">
              ${analysis.prioritized_gaps.slice(0, 8).map(gap => 
                `<span class="px-2 py-0.5 rounded text-xs bg-amber-100 dark:bg-amber-800 text-amber-800 dark:text-amber-200">${gap.field}</span>`
              ).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }
  
  // Suggested Queries
  if (plan.queries && plan.queries.length > 0) {
    html += `
      <div class="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
        <h4 class="text-sm font-semibold text-green-900 dark:text-green-100 mb-2">🔍 Generated Queries (${plan.queries.length})</h4>
        <div class="space-y-1 text-xs">
          ${plan.queries.slice(0, 5).map(q => `<div class="text-green-700 dark:text-green-300">• ${q}</div>`).join('')}
          ${plan.queries.length > 5 ? `<div class="text-green-600 dark:text-green-400 italic">+ ${plan.queries.length - 5} more...</div>` : ''}
        </div>
      </div>
    `;
  }
  
  // Learning Stats
  if (results.learning_stats) {
    const stats = results.learning_stats;
    html += `
      <div class="p-4 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
        <h4 class="text-sm font-semibold text-purple-900 dark:text-purple-100 mb-2">📊 Learning Statistics</h4>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div><span class="font-medium">Known Domains:</span> ${stats.total_domains || 0}</div>
          <div><span class="font-medium">Page Patterns:</span> ${stats.total_page_patterns || 0}</div>
          <div><span class="font-medium">High Confidence:</span> ${stats.high_confidence_patterns || 0}</div>
          <div><span class="font-medium">Reliable Domains:</span> ${stats.reliable_domains || 0}</div>
        </div>
      </div>
    `;
  }
  
  html += '</div>';
  return html;
}

export async function runCrawl(e) {
  if (e) e.preventDefault();
  if (els.crawlOutputPanel) els.crawlOutputPanel.innerHTML = '<div class="p-4 animate-pulse text-xs text-slate-500">Crawl initiated...</div>';
  try {
    const body = {
      entity: val('crawl-entity'),
      type: val('crawl-type'),
      max_pages: Number(val('crawl-max-pages') || 10),
      total_pages: Number(val('crawl-total-pages') || 50),
      max_depth: Number(val('crawl-max-depth') || 2),
      score_threshold: Number(val('crawl-score-threshold') || 35),
      seed_limit: Number(val('crawl-seed-limit') || 25),
      use_selenium: !!getEl('crawl-use-selenium')?.checked,
      active_mode: !!getEl('crawl-active-mode')?.checked,
      output: val('crawl-output') || '',
      fetch_text: val('crawl-fetch-url') || '',
      refresh: !!getEl('crawl-refresh')?.checked,
      refresh_batch: Number(val('crawl-refresh-batch') || 50),
    };

    const res = await fetchWithAuth('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (els.crawlOutputPanel) {
      els.crawlOutputPanel.innerHTML = renderCrawlResult(data);
    }
  } catch (err) {
    if (els.crawlOutputPanel) els.crawlOutputPanel.innerHTML = `<div class="text-rose-500 text-sm">${err.message}</div>`;
  }
}
