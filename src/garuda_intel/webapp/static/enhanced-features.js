/**
 * Enhanced Features UI - Entity Management, Relationships, and Learning
 * Provides UI for Phase 2-4 enhancements
 */

import { API_BASE } from './config.js';
import { getApiKey } from './storage.js';
import { showModal } from './modals.js';
import { pill } from './ui.js';

// ========== Entity Gap Analysis ==========

export async function analyzeEntityGaps(entityId) {
  try {
    const response = await fetch(`${API_BASE}/api/entities/${entityId}/gaps`, {
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) {
      throw new Error(`Gap analysis failed: ${response.statusText}`);
    }
    
    const gaps = await response.json();
    displayEntityGaps(entityId, gaps);
    return gaps;
  } catch (error) {
    console.error('Entity gap analysis error:', error);
    throw error;
  }
}

function displayEntityGaps(entityId, gaps) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  const missingFields = gaps.missing_fields || [];
  const completeness = ((gaps.completeness_score || 0) * 100).toFixed(1);
  const highPriority = gaps.high_priority_gaps || [];
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Entity Data Gaps</h2>
    
    <div class="mb-4">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-medium">Completeness</span>
        <span class="text-sm font-bold">${completeness}%</span>
      </div>
      <div class="w-full bg-slate-200 rounded-full h-2">
        <div class="bg-blue-500 h-2 rounded-full" style="width: ${completeness}%"></div>
      </div>
    </div>
    
    ${highPriority.length > 0 ? `
      <div class="mb-4">
        <h3 class="font-semibold mb-2">High Priority Gaps</h3>
        <div class="flex flex-wrap gap-2">
          ${highPriority.map(field => `
            <span class="px-2 py-1 bg-rose-100 text-rose-800 rounded text-sm">${field}</span>
          `).join('')}
        </div>
      </div>
    ` : ''}
    
    ${missingFields.length > 0 ? `
      <div class="mb-4">
        <h3 class="font-semibold mb-2">Missing Fields (${missingFields.length})</h3>
        <div class="flex flex-wrap gap-2 max-h-40 overflow-y-auto">
          ${missingFields.map(field => `
            <span class="px-2 py-1 bg-slate-100 text-slate-700 rounded text-xs">${field}</span>
          `).join('')}
        </div>
      </div>
    ` : ''}
    
    <div class="flex gap-2 mt-4">
      <button onclick="executeTargetedCrawl('${entityId}')" 
              class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
        Fill Gaps with Targeted Crawl
      </button>
      <button onclick="this.closest('.modal').remove()" 
              class="px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
        Close
      </button>
    </div>
  `;
  
  showModal(modal);
}

// ========== Entity-Aware Crawling ==========

export async function executeEntityCrawl(entityName, options = {}) {
  const {
    entityType = 'PERSON',
    mode = 'TARGETING',
    locationHint = '',
    aliases = [],
    officialDomains = []
  } = options;
  
  try {
    const response = await fetch(`${API_BASE}/api/entities/crawl`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({
        entity_name: entityName,
        entity_type: entityType,
        mode: mode,
        location_hint: locationHint,
        aliases: aliases,
        official_domains: officialDomains
      })
    });
    
    if (!response.ok) {
      throw new Error(`Entity crawl failed: ${response.statusText}`);
    }
    
    const result = await response.json();
    displayCrawlResult(result);
    return result;
  } catch (error) {
    console.error('Entity crawl error:', error);
    throw error;
  }
}

function displayCrawlResult(result) {
  const message = `
    <div class="p-4">
      <h3 class="text-lg font-bold mb-2">Crawl Complete</h3>
      <p class="mb-2">Crawled ${result.urls?.length || 0} URLs</p>
      ${result.entity_id ? `<p class="text-sm text-slate-600">Entity ID: ${result.entity_id}</p>` : ''}
    </div>
  `;
  
  const modal = document.createElement('div');
  modal.innerHTML = message;
  showModal(modal);
}

// ========== Entity Deduplication ==========

export async function deduplicateEntities(threshold = 0.85) {
  try {
    const response = await fetch(`${API_BASE}/api/entities/deduplicate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({ threshold })
    });
    
    if (!response.ok) {
      throw new Error(`Deduplication failed: ${response.statusText}`);
    }
    
    const result = await response.json();
    alert(`Successfully merged ${result.merged_count} duplicate entities`);
    return result;
  } catch (error) {
    console.error('Entity deduplication error:', error);
    throw error;
  }
}

export async function findSimilarEntities(entityId, threshold = 0.75) {
  try {
    const response = await fetch(
      `${API_BASE}/api/entities/${entityId}/similar?threshold=${threshold}`,
      {
        headers: { 'X-API-Key': getApiKey() || '' }
      }
    );
    
    if (!response.ok) {
      throw new Error(`Similar entities lookup failed: ${response.statusText}`);
    }
    
    const result = await response.json();
    displaySimilarEntities(entityId, result);
    return result;
  } catch (error) {
    console.error('Similar entities error:', error);
    throw error;
  }
}

function displaySimilarEntities(entityId, result) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  const similar = result.similar_entities || [];
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Similar Entities</h2>
    <p class="mb-4">Found ${similar.length} entities similar to "${result.entity_name}"</p>
    
    ${similar.length > 0 ? `
      <div class="space-y-2 max-h-96 overflow-y-auto">
        ${similar.map(entity => `
          <div class="p-3 border rounded hover:bg-slate-50">
            <div class="font-semibold">${entity.name}</div>
            <div class="text-sm text-slate-600">
              ${entity.kind ? `Type: ${entity.kind}` : ''}
              ${entity.last_seen ? ` • Last seen: ${new Date(entity.last_seen).toLocaleDateString()}` : ''}
            </div>
            <button onclick="mergeEntities('${entity.id}', '${entityId}')"
                    class="mt-2 text-sm px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600">
              Merge into Current
            </button>
          </div>
        `).join('')}
      </div>
    ` : '<p class="text-slate-500">No similar entities found</p>'}
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  showModal(modal);
}

export async function mergeEntities(sourceId, targetId) {
  if (!confirm('Are you sure you want to merge these entities? This cannot be undone.')) {
    return;
  }
  
  try {
    const response = await fetch(
      `${API_BASE}/api/entities/${sourceId}/merge/${targetId}`,
      {
        method: 'POST',
        headers: { 'X-API-Key': getApiKey() || '' }
      }
    );
    
    if (!response.ok) {
      throw new Error(`Entity merge failed: ${response.statusText}`);
    }
    
    alert('Entities merged successfully');
    window.location.reload(); // Refresh to show updated data
  } catch (error) {
    console.error('Entity merge error:', error);
    alert(`Merge failed: ${error.message}`);
  }
}

// ========== Relationship Management ==========

export async function inferRelationships(entityIds, context = null) {
  try {
    const response = await fetch(`${API_BASE}/api/relationships/infer`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({
        entity_ids: entityIds,
        context: context
      })
    });
    
    if (!response.ok) {
      throw new Error(`Relationship inference failed: ${response.statusText}`);
    }
    
    const result = await response.json();
    alert(`Inferred ${result.inferred_count} new relationships`);
    return result;
  } catch (error) {
    console.error('Relationship inference error:', error);
    throw error;
  }
}

export async function validateRelationships(fixInvalid = true) {
  try {
    const response = await fetch(`${API_BASE}/api/relationships/validate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({ fix_invalid: fixInvalid })
    });
    
    if (!response.ok) {
      throw new Error(`Relationship validation failed: ${response.statusText}`);
    }
    
    const result = await response.json();
    displayValidationReport(result);
    return result;
  } catch (error) {
    console.error('Relationship validation error:', error);
    throw error;
  }
}

function displayValidationReport(report) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Relationship Validation Report</h2>
    
    <div class="grid grid-cols-2 gap-4 mb-4">
      <div class="p-3 bg-green-50 rounded">
        <div class="text-2xl font-bold text-green-700">${report.valid || 0}</div>
        <div class="text-sm text-green-600">Valid</div>
      </div>
      <div class="p-3 bg-rose-50 rounded">
        <div class="text-2xl font-bold text-rose-700">${report.invalid || 0}</div>
        <div class="text-sm text-rose-600">Invalid</div>
      </div>
    </div>
    
    <div class="mb-4">
      <p class="text-sm">Total: ${report.total || 0} relationships</p>
      ${report.fixed ? `<p class="text-sm text-blue-600">Fixed: ${report.fixed} issues</p>` : ''}
    </div>
    
    ${report.issues && report.issues.length > 0 ? `
      <div class="mb-4">
        <h3 class="font-semibold mb-2">Issues Found</h3>
        <div class="space-y-1 max-h-40 overflow-y-auto text-sm">
          ${report.issues.map(issue => `
            <div class="text-slate-600">• ${issue}</div>
          `).join('')}
        </div>
      </div>
    ` : ''}
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  showModal(modal);
}

export async function deduplicateRelationships() {
  try {
    const response = await fetch(`${API_BASE}/api/relationships/deduplicate`, {
      method: 'POST',
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) {
      throw new Error(`Relationship deduplication failed: ${response.statusText}`);
    }
    
    const result = await response.json();
    alert(`Removed ${result.removed_count} duplicate relationships`);
    return result;
  } catch (error) {
    console.error('Relationship deduplication error:', error);
    throw error;
  }
}

// ========== Crawl Learning Stats ==========

export async function getCrawlLearningStats(domains = []) {
  try {
    const domainParam = domains.length > 0 ? `?domains=${domains.join(',')}` : '';
    const response = await fetch(
      `${API_BASE}/api/crawl/learning/stats${domainParam}`,
      {
        headers: { 'X-API-Key': getApiKey() || '' }
      }
    );
    
    if (!response.ok) {
      throw new Error(`Learning stats failed: ${response.statusText}`);
    }
    
    const stats = await response.json();
    displayLearningStats(stats);
    return stats;
  } catch (error) {
    console.error('Crawl learning stats error:', error);
    throw error;
  }
}

function displayLearningStats(stats) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  const domainReliability = stats.domain_reliability || {};
  const patterns = stats.successful_patterns || {};
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Crawl Learning Statistics</h2>
    
    ${Object.keys(domainReliability).length > 0 ? `
      <div class="mb-4">
        <h3 class="font-semibold mb-2">Domain Reliability</h3>
        <div class="space-y-2 max-h-40 overflow-y-auto">
          ${Object.entries(domainReliability).map(([domain, reliability]) => `
            <div class="flex items-center justify-between">
              <span class="text-sm">${domain}</span>
              <span class="text-sm font-mono">${(reliability * 100).toFixed(1)}%</span>
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}
    
    ${Object.keys(patterns).length > 0 ? `
      <div class="mb-4">
        <h3 class="font-semibold mb-2">Successful Patterns by Entity Type</h3>
        ${Object.entries(patterns).map(([entityType, typePatterns]) => `
          <div class="mb-3">
            <div class="font-medium text-sm mb-1">${entityType}</div>
            <div class="space-y-1 pl-3">
              ${typePatterns.slice(0, 5).map(pattern => `
                <div class="text-xs text-slate-600">
                  ${pattern.page_type}: ${(pattern.avg_quality * 100).toFixed(0)}% quality
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}
      </div>
    ` : ''}
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  showModal(modal);
}

// ========== Export Functions for Global Access ==========

window.analyzeEntityGaps = analyzeEntityGaps;
window.executeEntityCrawl = executeEntityCrawl;
window.executeTargetedCrawl = (entityId) => {
  // Get entity details first, then execute crawl
  // This would need entity lookup which we'll add
  alert('Targeted crawl will be executed for entity: ' + entityId);
};
window.deduplicateEntities = deduplicateEntities;
window.findSimilarEntities = findSimilarEntities;
window.mergeEntities = mergeEntities;
window.inferRelationships = inferRelationships;
window.validateRelationships = validateRelationships;
window.deduplicateRelationships = deduplicateRelationships;
window.getCrawlLearningStats = getCrawlLearningStats;
