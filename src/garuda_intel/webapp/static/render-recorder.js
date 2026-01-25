import { els } from './config.js';
import { renderIntel } from './render-intel.js';
import { renderHealthIndicator } from './status.js';
import { setLastIntelHits } from './state.js';

export function renderRecorderResults(data) {
  if (!els.recorderResults) return;
  els.recorderResults.innerHTML = '';
  const results = data.results || [];

  if (!results.length) {
    els.recorderResults.innerHTML = '<div class="p-4 text-sm text-slate-500">No recorder hits.</div>';
    return;
  }
  setLastIntelHits(results);
  els.recorderResults.innerHTML = results.map((r) => renderIntel([r], { innerHTML: '' })).join('');
}

export function renderRecorderHealth({ health, queue }) {
  if (!els.recorderHealth) return;
  els.recorderHealth.innerHTML = `
    <div class="grid gap-4 sm:grid-cols-2">
        <div class="p-3 bg-slate-50 dark:bg-slate-800 rounded border border-slate-200 dark:border-slate-700">
            <div class="text-xs font-bold uppercase text-slate-500">Status</div>
            <div>${health.status}</div>
        </div>
        <div class="p-3 bg-slate-50 dark:bg-slate-800 rounded border border-slate-200 dark:border-slate-700">
            <div class="text-xs font-bold uppercase text-slate-500">Queue Length</div>
            <div>${queue.length || 0}</div>
        </div>
    </div>
  `;
  renderHealthIndicator({ status: health.status, services: health.services || [] });
}
