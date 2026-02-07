/**
 * Graph Search UI - Semantic Entity Search, Path Finding, and Traversal
 * Provides UI for the new graph search functionality
 */

import { API_BASE } from './config.js';
import { getApiKey } from './storage.js';
import { showModal } from './modals.js';

// ========== Hybrid Entity Search ==========

export async function searchEntitiesSemantic(query, options = {}) {
  const { kind = '', threshold = 0.7, limit = 20 } = options;
  
  try {
    const params = new URLSearchParams({
      query,
      threshold: threshold.toString(),
      limit: limit.toString(),
    });
    if (kind) params.append('kind', kind);
    
    const response = await fetch(`${API_BASE}/api/graph/search?${params}`, {
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Semantic search error:', error);
    throw error;
  }
}

export function displaySearchResults(results, container) {
  if (!container) return;
  
  const { query, total, results: entities } = results;
  
  container.innerHTML = `
    <div class="p-4 border rounded-lg bg-slate-50 dark:bg-slate-900">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold">Search Results for "${query}"</h3>
        <span class="text-sm text-slate-500">${total} found</span>
      </div>
      
      ${entities.length > 0 ? `
        <div class="space-y-2 max-h-96 overflow-y-auto">
          ${entities.map(r => `
            <div class="p-3 border rounded hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                 onclick="showEntityDetails('${r.entity.id}')">
              <div class="flex items-center justify-between">
                <span class="font-medium">${escapeHtml(r.entity.name)}</span>
                <span class="text-xs px-2 py-0.5 rounded ${r.match_type === 'sql_exact' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'}">
                  ${r.match_type === 'sql_exact' ? 'Exact' : 'Semantic'} (${(r.score * 100).toFixed(0)}%)
                </span>
              </div>
              <div class="text-sm text-slate-600 dark:text-slate-400">
                ${r.entity.kind ? `Type: ${r.entity.kind}` : 'No type'}
              </div>
            </div>
          `).join('')}
        </div>
      ` : '<p class="text-slate-500">No entities found</p>'}
    </div>
  `;
}

// ========== Semantic Duplicate Detection ==========

export async function findSemanticDuplicates(name, options = {}) {
  const { kind = '', threshold = 0.85, limit = 10 } = options;
  
  try {
    const params = new URLSearchParams({
      name,
      threshold: threshold.toString(),
      limit: limit.toString(),
    });
    if (kind) params.append('kind', kind);
    
    const response = await fetch(`${API_BASE}/api/graph/semantic-duplicates?${params}`, {
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) {
      throw new Error(`Duplicate search failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Semantic duplicates error:', error);
    throw error;
  }
}

export function displayDuplicates(results) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  const { query_name, duplicates, threshold } = results;
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Semantic Duplicates</h2>
    <p class="mb-4">
      Found ${duplicates.length} potential duplicates for "<strong>${escapeHtml(query_name)}</strong>"
      <span class="text-sm text-slate-500">(threshold: ${(threshold * 100).toFixed(0)}%)</span>
    </p>
    
    ${duplicates.length > 0 ? `
      <div class="space-y-2 max-h-80 overflow-y-auto">
        ${duplicates.map(d => `
          <div class="p-3 border rounded hover:bg-slate-50 dark:hover:bg-slate-800">
            <div class="flex items-center justify-between">
              <span class="font-medium">${escapeHtml(d.entity.name)}</span>
              <span class="text-xs px-2 py-0.5 rounded ${d.match_type === 'exact' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}">
                ${(d.similarity * 100).toFixed(0)}% similar
              </span>
            </div>
            <div class="text-sm text-slate-600 dark:text-slate-400">
              ID: ${d.entity.id.slice(0, 8)}... • Type: ${d.entity.kind || 'unknown'}
            </div>
            <button onclick="mergeEntitiesFromDuplicates('${d.entity.id}')"
                    class="mt-2 text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600">
              Merge
            </button>
          </div>
        `).join('')}
      </div>
    ` : '<p class="text-slate-500">No duplicates found at this threshold</p>'}
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  showModal(modal);
}

// ========== Deduplication Scan ==========

export async function runDedupeScan(options = {}) {
  const { threshold = 0.9, kind = '', merge = false } = options;
  
  try {
    const response = await fetch(`${API_BASE}/api/graph/dedupe-scan`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({ threshold, kind, merge })
    });
    
    if (!response.ok) {
      throw new Error(`Dedupe scan failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Dedupe scan error:', error);
    throw error;
  }
}

export function displayDedupeScanResults(results) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  const { dry_run, duplicates_found, merged_count, report } = results;
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Deduplication Scan Results</h2>
    
    <div class="grid grid-cols-2 gap-4 mb-4">
      <div class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded">
        <div class="text-2xl font-bold text-amber-700 dark:text-amber-300">${duplicates_found}</div>
        <div class="text-sm text-amber-600 dark:text-amber-400">Duplicate Groups</div>
      </div>
      <div class="p-3 ${dry_run ? 'bg-slate-50 dark:bg-slate-800' : 'bg-green-50 dark:bg-green-900/20'} rounded">
        <div class="text-2xl font-bold ${dry_run ? 'text-slate-700 dark:text-slate-300' : 'text-green-700 dark:text-green-300'}">
          ${dry_run ? 'Dry Run' : merged_count}
        </div>
        <div class="text-sm ${dry_run ? 'text-slate-600 dark:text-slate-400' : 'text-green-600 dark:text-green-400'}">
          ${dry_run ? 'No merges performed' : 'Entities Merged'}
        </div>
      </div>
    </div>
    
    ${report.duplicates_found && report.duplicates_found.length > 0 ? `
      <div class="mb-4">
        <h3 class="font-semibold mb-2">Duplicate Groups Found</h3>
        <div class="space-y-3 max-h-60 overflow-y-auto">
          ${report.duplicates_found.slice(0, 10).map((group, i) => `
            <div class="p-2 border rounded text-sm">
              <div class="font-medium mb-1">Group ${i + 1}: "${escapeHtml(group.canonical.name)}"</div>
              <div class="text-xs text-slate-600 dark:text-slate-400">
                ${group.duplicates.length} potential duplicates
              </div>
            </div>
          `).join('')}
          ${report.duplicates_found.length > 10 ? `
            <div class="text-sm text-slate-500">...and ${report.duplicates_found.length - 10} more groups</div>
          ` : ''}
        </div>
      </div>
    ` : ''}
    
    ${dry_run && duplicates_found > 0 ? `
      <button data-action="merge-all" data-threshold="${results.threshold}" data-kind="${escapeAttr(results.kind || '')}"
              class="mt-2 px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600">
        ⚠️ Merge All Duplicates
      </button>
    ` : ''}
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 ml-2 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  // Add event listener for merge button
  const mergeBtn = modal.querySelector('[data-action="merge-all"]');
  if (mergeBtn) {
    mergeBtn.addEventListener('click', () => {
      const threshold = parseFloat(mergeBtn.dataset.threshold);
      const kind = mergeBtn.dataset.kind;
      window.runActualMerge(threshold, kind);
    });
  }
  
  showModal(modal);
}

// ========== Graph Traversal ==========

export async function traverseGraph(entityIds, options = {}) {
  const { maxDepth = 2, topN = 10, relationTypes = null } = options;
  
  try {
    const response = await fetch(`${API_BASE}/api/graph/traverse`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({
        entity_ids: entityIds,
        max_depth: maxDepth,
        top_n_per_depth: topN,
        relation_types: relationTypes
      })
    });
    
    if (!response.ok) {
      throw new Error(`Graph traversal failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Graph traversal error:', error);
    throw error;
  }
}

export function displayTraversalResults(results) {
  const modal = document.createElement('div');
  modal.className = 'modal-content max-w-2xl';
  
  const { root_entities, depths, all_relationships } = results;
  
  let depthsHtml = '';
  for (const [depth, data] of Object.entries(depths || {})) {
    depthsHtml += `
      <div class="mb-3">
        <h4 class="font-medium text-sm mb-1">Depth ${depth} (${data.entity_count} entities)</h4>
        <div class="space-y-1 pl-3">
          ${data.entities.slice(0, 5).map(item => `
            <div class="text-sm p-2 border rounded flex items-center justify-between">
              <span>${escapeHtml(item.entity.name)}</span>
              <span class="text-xs text-slate-500">${item.relation_type} (${item.direction})</span>
            </div>
          `).join('')}
          ${data.entities.length > 5 ? `<div class="text-xs text-slate-500">...and ${data.entities.length - 5} more</div>` : ''}
        </div>
      </div>
    `;
  }
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Graph Traversal Results</h2>
    
    <div class="mb-4">
      <h3 class="font-semibold mb-2">Starting Entities</h3>
      <div class="flex flex-wrap gap-2">
        ${root_entities.map(e => `
          <span class="px-2 py-1 bg-blue-100 text-blue-800 rounded text-sm">${escapeHtml(e.name)}</span>
        `).join('')}
      </div>
    </div>
    
    ${depthsHtml || '<p class="text-slate-500">No connected entities found</p>'}
    
    <div class="mt-4 text-sm text-slate-600">
      Total relationships found: ${(all_relationships || []).length}
    </div>
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  showModal(modal);
}

// ========== Path Finding ==========

export async function findPath(sourceId, targetId, maxDepth = 5) {
  try {
    const params = new URLSearchParams({
      source_id: sourceId,
      target_id: targetId,
      max_depth: maxDepth.toString()
    });
    
    const response = await fetch(`${API_BASE}/api/graph/path?${params}`, {
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) {
      throw new Error(`Path finding failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Path finding error:', error);
    throw error;
  }
}

export function displayPathResults(results) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  const { found, path, path_length } = results;
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Path Between Entities</h2>
    
    ${found ? `
      <p class="mb-4 text-green-600 dark:text-green-400">
        ✓ Path found with ${path_length} step${path_length !== 1 ? 's' : ''}
      </p>
      
      <div class="space-y-2">
        ${path.map((step, i) => `
          <div class="flex items-center gap-2">
            <div class="p-2 border rounded flex-1 ${i === 0 || i === path.length - 1 ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200' : ''}">
              <div class="font-medium">${escapeHtml(step.entity.name)}</div>
              <div class="text-xs text-slate-500">${step.entity.kind || 'unknown'}</div>
            </div>
            ${step.relationship ? `
              <div class="text-xs px-2 py-1 bg-slate-100 dark:bg-slate-800 rounded">
                ${step.relationship.direction === 'outgoing' ? '→' : '←'} ${step.relationship.type}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    ` : `
      <p class="text-amber-600 dark:text-amber-400">
        ✗ No path found between these entities
      </p>
    `}
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  showModal(modal);
}

// ========== Relationship Confidence ==========

export async function recordRelationship(sourceId, targetId, relationType, sourceUrl = null) {
  try {
    const response = await fetch(`${API_BASE}/api/relationships/record`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({
        source_id: sourceId,
        target_id: targetId,
        relation_type: relationType,
        source_url: sourceUrl
      })
    });
    
    if (!response.ok) {
      throw new Error(`Record relationship failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Record relationship error:', error);
    throw error;
  }
}

export async function getHighConfidenceRelationships(options = {}) {
  const { minConfidence = 0.7, minOccurrences = 2, limit = 100 } = options;
  
  try {
    const params = new URLSearchParams({
      min_confidence: minConfidence.toString(),
      min_occurrences: minOccurrences.toString(),
      limit: limit.toString()
    });
    
    const response = await fetch(`${API_BASE}/api/relationships/high-confidence?${params}`, {
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) {
      throw new Error(`High confidence query failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('High confidence relationships error:', error);
    throw error;
  }
}

export async function getRelationshipStats() {
  try {
    const response = await fetch(`${API_BASE}/api/relationships/confidence-stats`, {
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) {
      throw new Error(`Stats query failed: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Relationship stats error:', error);
    throw error;
  }
}

export function displayRelationshipStats(stats) {
  const modal = document.createElement('div');
  modal.className = 'modal-content';
  
  const { total_relationships, multi_occurrence_count, confidence_distribution, top_relation_types } = stats;
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">Relationship Confidence Statistics</h2>
    
    <div class="grid grid-cols-2 gap-4 mb-4">
      <div class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded">
        <div class="text-2xl font-bold text-blue-700 dark:text-blue-300">${total_relationships}</div>
        <div class="text-sm text-blue-600 dark:text-blue-400">Total Relationships</div>
      </div>
      <div class="p-3 bg-green-50 dark:bg-green-900/20 rounded">
        <div class="text-2xl font-bold text-green-700 dark:text-green-300">${multi_occurrence_count}</div>
        <div class="text-sm text-green-600 dark:text-green-400">Multi-Occurrence</div>
      </div>
    </div>
    
    <div class="mb-4">
      <h3 class="font-semibold mb-2">Confidence Distribution</h3>
      <div class="space-y-2">
        ${Object.entries(confidence_distribution || {}).map(([level, count]) => `
          <div class="flex items-center justify-between">
            <span class="text-sm capitalize">${level.replace('_', ' ')}</span>
            <div class="flex items-center gap-2">
              <div class="w-24 bg-slate-200 rounded-full h-2">
                <div class="h-2 rounded-full ${level === 'very_high' ? 'bg-green-500' : level === 'high' ? 'bg-blue-500' : level === 'medium' ? 'bg-amber-500' : 'bg-red-500'}"
                     style="width: ${total_relationships > 0 ? (count / total_relationships * 100) : 0}%"></div>
              </div>
              <span class="text-sm font-mono w-12 text-right">${count}</span>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
    
    ${top_relation_types && top_relation_types.length > 0 ? `
      <div class="mb-4">
        <h3 class="font-semibold mb-2">Top Relation Types</h3>
        <div class="space-y-1 max-h-32 overflow-y-auto">
          ${top_relation_types.slice(0, 10).map(t => `
            <div class="flex items-center justify-between text-sm">
              <span>${t.type || 'unknown'}</span>
              <span class="font-mono">${t.count}</span>
            </div>
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

export function displayHighConfidenceRelationships(results) {
  const modal = document.createElement('div');
  modal.className = 'modal-content max-w-2xl';
  
  const { total, relationships } = results;
  
  modal.innerHTML = `
    <h2 class="text-xl font-bold mb-4">High Confidence Relationships</h2>
    <p class="mb-4 text-sm text-slate-600 dark:text-slate-400">
      Found ${total} relationship${total !== 1 ? 's' : ''} meeting the criteria
    </p>
    
    ${relationships.length > 0 ? `
      <div class="space-y-2 max-h-80 overflow-y-auto">
        ${relationships.map(r => `
          <div class="p-3 border rounded">
            <div class="flex items-center justify-between mb-1">
              <span class="font-medium">${r.relation_type}</span>
              <span class="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded">
                ${(r.confidence * 100).toFixed(0)}% confidence
              </span>
            </div>
            <div class="text-xs text-slate-500">
              Seen ${r.occurrence_count} time${r.occurrence_count !== 1 ? 's' : ''} •
              ${(r.sources || []).length} source${(r.sources || []).length !== 1 ? 's' : ''}
            </div>
          </div>
        `).join('')}
      </div>
    ` : '<p class="text-slate-500">No relationships found matching criteria</p>'}
    
    <button onclick="this.closest('.modal').remove()" 
            class="mt-4 px-4 py-2 bg-slate-300 text-slate-700 rounded hover:bg-slate-400">
      Close
    </button>
  `;
  
  showModal(modal);
}

// ========== Utility Functions ==========

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function escapeAttr(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ========== Export Functions for Global Access ==========

window.searchEntitiesSemantic = async function(query, options) {
  const results = await searchEntitiesSemantic(query, options);
  const container = document.getElementById('graph-search-results');
  if (container) {
    displaySearchResults(results, container);
  }
  return results;
};

window.findSemanticDuplicates = async function(name, options) {
  const results = await findSemanticDuplicates(name, options);
  displayDuplicates(results);
  return results;
};

window.runDedupeScan = async function(options) {
  const results = await runDedupeScan(options);
  displayDedupeScanResults(results);
  return results;
};

window.runActualMerge = async function(threshold, kind) {
  if (!confirm('⚠️ This will permanently merge duplicate entities. This cannot be undone. Continue?')) {
    return;
  }
  const results = await runDedupeScan({ threshold, kind, merge: true });
  displayDedupeScanResults(results);
  return results;
};

window.traverseGraph = async function(entityIds, options) {
  const results = await traverseGraph(entityIds, options);
  displayTraversalResults(results);
  return results;
};

window.findPath = async function(sourceId, targetId, maxDepth) {
  const results = await findPath(sourceId, targetId, maxDepth);
  displayPathResults(results);
  return results;
};

window.recordRelationship = recordRelationship;

window.getHighConfidenceRelationships = async function(options) {
  const results = await getHighConfidenceRelationships(options);
  displayHighConfidenceRelationships(results);
  return results;
};

window.getRelationshipStats = async function() {
  const stats = await getRelationshipStats();
  displayRelationshipStats(stats);
  return stats;
};

window.mergeEntitiesFromDuplicates = async function(sourceId) {
  const targetId = prompt('Enter target entity ID to merge into:');
  if (!targetId) return;
  
  if (!confirm('Are you sure you want to merge these entities? This cannot be undone.')) {
    return;
  }
  
  try {
    const response = await fetch(`${API_BASE}/api/graph/merge-entities`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey() || ''
      },
      body: JSON.stringify({ source_id: sourceId, target_id: targetId })
    });
    
    if (!response.ok) throw new Error('Merge failed');
    
    alert('Entities merged successfully');
    document.querySelector('.modal')?.remove();
  } catch (error) {
    alert('Merge failed: ' + error.message);
  }
};

window.showEntityDetails = async function(entityId) {
  try {
    const response = await fetch(`${API_BASE}/api/entities/${entityId}`, {
      headers: { 'X-API-Key': getApiKey() || '' }
    });
    
    if (!response.ok) throw new Error('Failed to load entity');
    
    const entity = await response.json();
    
    const modal = document.createElement('div');
    modal.className = 'modal-content';
    modal.innerHTML = `
      <h2 class="text-xl font-bold mb-4">${escapeHtml(entity.name)}</h2>
      <div class="space-y-2 text-sm">
        <div><strong>ID:</strong> ${escapeHtml(entity.id)}</div>
        <div><strong>Type:</strong> ${escapeHtml(entity.kind || 'unknown')}</div>
        ${entity.data ? `
          <div><strong>Data:</strong></div>
          <pre class="p-2 bg-slate-100 dark:bg-slate-800 rounded text-xs overflow-auto max-h-40">${escapeHtml(JSON.stringify(entity.data, null, 2))}</pre>
        ` : ''}
      </div>
      <div class="flex gap-2 mt-4">
        <button data-action="explore" data-entity-id="${escapeAttr(entity.id)}"
                class="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600">
          Explore Connections
        </button>
        <button data-action="find-dups" data-entity-name="${escapeAttr(entity.name)}"
                class="px-3 py-1 bg-amber-500 text-white rounded text-sm hover:bg-amber-600">
          Find Duplicates
        </button>
        <button onclick="this.closest('.modal').remove()" 
                class="px-3 py-1 bg-slate-300 text-slate-700 rounded text-sm hover:bg-slate-400">
          Close
        </button>
      </div>
    `;
    
    // Add event listeners
    modal.querySelector('[data-action="explore"]')?.addEventListener('click', function() {
      window.traverseGraph([this.dataset.entityId]);
    });
    modal.querySelector('[data-action="find-dups"]')?.addEventListener('click', function() {
      window.findSemanticDuplicates(this.dataset.entityName);
    });
    
    showModal(modal);
  } catch (error) {
    alert('Failed to load entity details: ' + error.message);
  }
};
