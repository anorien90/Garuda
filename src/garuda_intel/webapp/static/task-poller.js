/**
 * Task Queue Poller - Shared utility for submitting tasks and polling results.
 * All long-running operations go through the persistent task queue for:
 * - Persistent details surviving page reloads
 * - Sequential LLM processing (protecting Ollama)
 * - Task cancellation support
 * - Progress tracking
 */
import { fetchWithAuth } from './api.js';

// Configurable polling settings
export const POLL_CONFIG = {
  INTERVAL_MS: 2000,
  MAX_ATTEMPTS: 600, // 20 minutes max
  TIMEOUT_MS: 1200000 // 20 minutes
};

/**
 * Submit a task and poll for its result.
 * @param {string} endpoint - API endpoint (e.g., '/api/agent/chat')
 * @param {object} body - Request body (queued: true will be added)
 * @param {object} options - Polling options
 * @param {function} options.onProgress - Progress callback(progress, message)
 * @param {function} options.onStatus - Status callback(status, taskData)
 * @param {HTMLElement} options.statusElement - Element to show status in
 * @returns {Promise<object>} Task result
 */
export async function submitAndPoll(endpoint, body, options = {}) {
  const { onProgress, onStatus, statusElement } = options;

  // Submit task with queued: true
  const submitRes = await fetchWithAuth(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, queued: true }),
  });

  const submitData = await submitRes.json();
  const taskId = submitData.task_id;

  if (!taskId) {
    // Endpoint didn't queue - returned result directly
    return submitData;
  }

  // Store task ID for persistence across reloads
  storeActiveTask(taskId, endpoint, body);

  if (onStatus) onStatus('pending', submitData);
  if (statusElement) {
    renderTaskStatus(statusElement, 'pending', 'Task queued...', 0, taskId);
  }

  // Poll for result
  return pollTaskResult(taskId, options);
}

/**
 * Poll a task until completion.
 * @param {string} taskId - Task ID to poll
 * @param {object} options - Polling options
 * @returns {Promise<object>} Task result
 */
export async function pollTaskResult(taskId, options = {}) {
  const { onProgress, onStatus, statusElement } = options;

  for (let attempt = 0; attempt < POLL_CONFIG.MAX_ATTEMPTS; attempt++) {
    await sleep(POLL_CONFIG.INTERVAL_MS);

    try {
      const res = await fetchWithAuth(`/api/tasks/${taskId}`);
      const task = await res.json();

      if (task.error && !task.status) {
        throw new Error(task.error);
      }

      const status = task.status;
      const progress = task.progress || 0;
      const message = task.progress_message || '';

      if (onProgress) onProgress(progress, message);
      if (onStatus) onStatus(status, task);
      if (statusElement) {
        renderTaskStatus(statusElement, status, message, progress, taskId);
      }

      if (status === 'completed') {
        removeActiveTask(taskId);
        return task.result || {};
      }

      if (status === 'failed') {
        removeActiveTask(taskId);
        throw new Error(task.error || 'Task failed');
      }

      if (status === 'cancelled') {
        removeActiveTask(taskId);
        throw new Error('Task was cancelled');
      }
    } catch (err) {
      if (err.message.includes('Task was cancelled') || err.message.includes('Task failed')) {
        throw err;
      }
      console.warn('Poll error, retrying:', err);
    }
  }

  throw new Error('Task polling timed out');
}

/**
 * Cancel a running task.
 */
export async function cancelTask(taskId) {
  const res = await fetchWithAuth(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
  const data = await res.json();
  removeActiveTask(taskId);
  return data;
}

/**
 * Get all active tasks from localStorage.
 */
export function getActiveTasks() {
  try {
    return JSON.parse(localStorage.getItem('garuda_active_tasks') || '[]');
  } catch {
    return [];
  }
}

/**
 * Store a task ID for persistence across page reloads.
 */
function storeActiveTask(taskId, endpoint, body) {
  const tasks = getActiveTasks();
  tasks.push({
    taskId,
    endpoint,
    body,
    submittedAt: new Date().toISOString(),
  });
  localStorage.setItem('garuda_active_tasks', JSON.stringify(tasks));
}

/**
 * Remove a completed task from active tracking.
 */
function removeActiveTask(taskId) {
  const tasks = getActiveTasks().filter(t => t.taskId !== taskId);
  localStorage.setItem('garuda_active_tasks', JSON.stringify(tasks));
}

/**
 * Render task status in an element.
 * Uses event delegation to avoid duplicate listeners.
 */
export function renderTaskStatus(el, status, message, progress, taskId) {
  const progressPct = Math.round(progress * 100);
  const statusColors = {
    pending: 'text-amber-600 dark:text-amber-400',
    running: 'text-blue-600 dark:text-blue-400',
    completed: 'text-green-600 dark:text-green-400',
    failed: 'text-rose-600 dark:text-rose-400',
    cancelled: 'text-slate-600 dark:text-slate-400',
  };
  const statusIcons = {
    pending: '⏳',
    running: '⚙️',
    completed: '✅',
    failed: '❌',
    cancelled: '🚫',
  };

  const color = statusColors[status] || statusColors.pending;
  const icon = statusIcons[status] || '⏳';
  
  // Validate and sanitize taskId (strict UUID v4 format check)
  const uuidRegex = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
  const safeTaskId = uuidRegex.test(String(taskId)) ? String(taskId) : String(taskId).replace(/[^a-fA-F0-9-]/g, '').substring(0, 36);

  el.innerHTML = `
    <div class="p-4 space-y-2">
      <div class="flex items-center justify-between">
        <div class="${color} font-semibold text-sm">
          ${icon} ${status.charAt(0).toUpperCase() + status.slice(1)}${message ? ': ' + escapeHtml(message) : ''}
        </div>
        ${status === 'running' || status === 'pending' ? `
          <button data-cancel-task="${safeTaskId}"
            class="cancel-task-btn text-xs px-2 py-1 rounded bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300 hover:bg-rose-200 dark:hover:bg-rose-900/50">
            Cancel
          </button>
        ` : ''}
      </div>
      ${status === 'running' || status === 'pending' ? `
        <div class="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2">
          <div class="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-500" style="width: ${progressPct}%"></div>
        </div>
        <div class="text-xs text-slate-500 dark:text-slate-400">${progressPct}% complete • Task ID: ${safeTaskId.substring(0, 8)}...</div>
      ` : ''}
      ${status === 'pending' ? `
        <div class="animate-pulse text-xs text-amber-500 dark:text-amber-400">Waiting in queue...</div>
      ` : ''}
    </div>
  `;
  
  // Set up event delegation once on the element if not already set
  if (!el.dataset.cancelDelegated) {
    el.dataset.cancelDelegated = 'true';
    el.addEventListener('click', (e) => {
      const btn = e.target.closest('.cancel-task-btn');
      if (btn) {
        const taskIdToCancel = btn.getAttribute('data-cancel-task');
        if (taskIdToCancel) {
          cancelTask(taskIdToCancel).catch(err => {
            console.error('Failed to cancel task:', err);
          });
        }
      }
    });
  }
}

/**
 * Escape HTML to prevent XSS attacks.
 */
function escapeHtml(unsafe) {
  if (!unsafe) return '';
  return String(unsafe)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
