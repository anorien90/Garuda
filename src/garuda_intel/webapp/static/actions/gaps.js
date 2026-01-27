import { fetchWithAuth } from '../api.js';
import { getEl, val } from '../config.js';

export async function analyzeEntityGaps(e) {
  if (e) e.preventDefault();
  
  const entityId = val('gap-entity-id');
  if (!entityId || !entityId.trim()) {
    alert('Please enter an entity ID');
    return;
  }
  
  const resultsDiv = getEl('gap-analysis-results');
  if (resultsDiv) {
    resultsDiv.innerHTML = '<div class="p-4 animate-pulse text-xs text-blue-600">Analyzing entity gaps...</div>';
  }
  
  try {
    const res = await fetchWithAuth(`/api/entities/${entityId.trim()}/analyze_gaps`);
    const data = await res.json();
    
    if (data.error) {
      throw new Error(data.error);
    }
    
    if (resultsDiv) {
      resultsDiv.innerHTML = renderGapAnalysis(data);
    }
  } catch (err) {
    if (resultsDiv) {
      resultsDiv.innerHTML = `<div class="p-4 rounded-lg bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
        <strong>Error:</strong> ${err.message}
      </div>`;
    }
  }
}

export async function analyzeAllGaps(e) {
  if (e) e.preventDefault();
  
  const resultsDiv = getEl('gap-analysis-results');
  if (resultsDiv) {
    resultsDiv.innerHTML = '<div class="p-4 animate-pulse text-xs text-blue-600">Analyzing top entities...</div>';
  }
  
  try {
    const res = await fetchWithAuth('/api/entities/analyze_all_gaps?limit=20');
    const data = await res.json();
    
    if (data.error) {
      throw new Error(data.error);
    }
    
    if (resultsDiv) {
      resultsDiv.innerHTML = renderAllGapsAnalysis(data);
    }
  } catch (err) {
    if (resultsDiv) {
      resultsDiv.innerHTML = `<div class="p-4 rounded-lg bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
        <strong>Error:</strong> ${err.message}
      </div>`;
    }
  }
}

function renderGapAnalysis(data) {
  let html = '<div class="space-y-3 mt-3 p-4 rounded-lg bg-white dark:bg-slate-900/50 border border-blue-200 dark:border-blue-800">';
  
  // Entity Info
  html += `
    <div class="pb-3 border-b border-blue-200 dark:border-blue-700">
      <div class="text-sm font-semibold text-blue-900 dark:text-blue-100">${data.entity_name || 'Unknown'}</div>
      <div class="text-xs text-blue-700 dark:text-blue-300">Type: ${data.entity_type || 'N/A'}</div>
    </div>
  `;
  
  // Completeness Score
  const completeness = data.completeness_score || 0;
  const scoreColor = completeness >= 70 ? 'green' : completeness >= 40 ? 'amber' : 'rose';
  html += `
    <div class="flex items-center justify-between p-3 rounded bg-${scoreColor}-50 dark:bg-${scoreColor}-900/20 border border-${scoreColor}-200 dark:border-${scoreColor}-800">
      <span class="text-sm font-medium text-${scoreColor}-900 dark:text-${scoreColor}-100">Completeness Score</span>
      <span class="text-2xl font-bold text-${scoreColor}-700 dark:text-${scoreColor}-300">${completeness.toFixed(1)}%</span>
    </div>
  `;
  
  // Missing Fields
  if (data.prioritized_gaps && data.prioritized_gaps.length > 0) {
    html += `
      <div>
        <div class="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">Top Missing Fields (${data.prioritized_gaps.length})</div>
        <div class="space-y-1.5">
    `;
    
    data.prioritized_gaps.slice(0, 10).forEach(gap => {
      const priorityColor = gap.priority === 'critical' ? 'rose' : gap.priority === 'important' ? 'amber' : 'slate';
      html += `
        <div class="flex items-center justify-between p-2 rounded bg-slate-50 dark:bg-slate-800/50 text-xs">
          <div class="flex items-center gap-2">
            <span class="px-1.5 py-0.5 rounded text-xs font-medium bg-${priorityColor}-100 dark:bg-${priorityColor}-900/50 text-${priorityColor}-700 dark:text-${priorityColor}-300">${gap.priority}</span>
            <span class="font-medium">${gap.field}</span>
          </div>
          <span class="text-slate-600 dark:text-slate-400">Score: ${(gap.score || 0).toFixed(1)}</span>
        </div>
      `;
    });
    
    html += '</div></div>';
  }
  
  // Suggested Queries
  if (data.suggested_queries && data.suggested_queries.length > 0) {
    html += `
      <div>
        <div class="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">Suggested Search Queries</div>
        <div class="space-y-1">
    `;
    
    data.suggested_queries.slice(0, 5).forEach(query => {
      html += `<div class="text-xs text-blue-700 dark:text-blue-300 p-2 rounded bg-blue-50 dark:bg-blue-900/30">🔍 ${query}</div>`;
    });
    
    html += '</div></div>';
  }
  
  // Suggested Sources
  if (data.suggested_sources && data.suggested_sources.length > 0) {
    html += `
      <div>
        <div class="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">Recommended Sources</div>
        <div class="space-y-1">
    `;
    
    data.suggested_sources.forEach(source => {
      html += `
        <div class="text-xs p-2 rounded bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
          <div class="font-medium text-green-900 dark:text-green-100">${source.name}</div>
          <div class="text-green-700 dark:text-green-300 mt-0.5">${source.url_pattern}</div>
        </div>
      `;
    });
    
    html += '</div></div>';
  }
  
  html += '</div>';
  return html;
}

function renderAllGapsAnalysis(data) {
  const entities = data.entities || [];
  
  let html = '<div class="space-y-2 mt-3">';
  html += `<div class="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">Found ${entities.length} entities with gaps</div>`;
  
  entities.forEach((entity, idx) => {
    const completeness = entity.completeness_score || 0;
    const scoreColor = completeness >= 70 ? 'green' : completeness >= 40 ? 'amber' : 'rose';
    const gapCount = (entity.missing_fields || []).length;
    
    html += `
      <div class="p-3 rounded-lg bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 hover:border-blue-400 dark:hover:border-blue-600 transition cursor-pointer" onclick="document.getElementById('gap-entity-id').value='${entity.entity_id}'; document.getElementById('btn-analyze-gaps').click();">
        <div class="flex items-center justify-between">
          <div class="flex-1">
            <div class="text-sm font-medium text-slate-900 dark:text-slate-100">${entity.entity_name || 'Unknown'}</div>
            <div class="text-xs text-slate-600 dark:text-slate-400">Type: ${entity.entity_type || 'N/A'} • ${gapCount} gaps • ${entity.intelligence_count || 0} intel</div>
          </div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-1 rounded text-xs font-bold bg-${scoreColor}-100 dark:bg-${scoreColor}-900/50 text-${scoreColor}-700 dark:text-${scoreColor}-300">
              ${completeness.toFixed(0)}%
            </span>
          </div>
        </div>
      </div>
    `;
  });
  
  html += '</div>';
  return html;
}
