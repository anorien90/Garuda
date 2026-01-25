import { els, getEl, val } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderRecorderResults, renderRecorderHealth } from '../render-recorder.js';

export async function recorderSearch(e) {
  if (e) e.preventDefault();
  if (!els.recorderResults) return;
  const qEl = getEl('recorder-q');
  const entityTypeEl = getEl('recorder-entity-type');
  const pageTypeEl = getEl('recorder-page-type');
  const limitEl = getEl('recorder-limit');
  if (!qEl || !entityTypeEl || !pageTypeEl || !limitEl) {
    els.recorderResults.innerHTML = '<div class="p-4 text-rose-500">Recorder form is missing from the page.</div>';
    return;
  }

  els.recorderResults.innerHTML = '<div class="p-4 animate-pulse">Searching...</div>';
  try {
    const params = new URLSearchParams({
      q: qEl.value || '',
      entity_type: entityTypeEl.value || '',
      page_type: pageTypeEl.value || '',
      limit: limitEl.value || 20,
    });
    const res = await fetchWithAuth(`/api/recorder/search?${params}`);
    renderRecorderResults(await res.json());
  } catch (err) {
    els.recorderResults.innerHTML = `<div class="p-4 text-rose-500">${err.message}</div>`;
  }
}

export async function recorderRefreshHealth() {
  if (!els.recorderHealth) return;
  try {
    const [healthRes, queueRes] = await Promise.all([
      fetchWithAuth('/api/recorder/health'),
      fetchWithAuth('/api/recorder/queue'),
    ]);
    const health = await healthRes.json();
    const queue = await queueRes.json();
    renderRecorderHealth({ health, queue });
  } catch (err) {
    els.recorderHealth.innerHTML = `<div class="text-rose-500 text-xs">${err.message}</div>`;
  }
}

export async function recorderMark(e) {
  if (e) e.preventDefault();
  if (els.recorderMarkStatus) els.recorderMarkStatus.textContent = 'Sending...';
  try {
    const body = {
      url: val('recorder-mark-url'),
      mode: val('recorder-mark-mode') || 'manual',
      session_id: val('recorder-mark-session') || 'ui-session',
    };
    const res = await fetchWithAuth('/api/recorder/mark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    els.recorderMarkStatus.textContent = `OK: ${data.url} (${data.mode})`;
    els.recorderMarkStatus.classList.remove('text-rose-500');
    els.recorderMarkStatus.classList.add('text-emerald-600');
  } catch (err) {
    if (els.recorderMarkStatus) {
      els.recorderMarkStatus.textContent = `Error: ${err.message}`;
      els.recorderMarkStatus.classList.remove('text-emerald-600');
      els.recorderMarkStatus.classList.add('text-rose-500');
    }
  }
}
