import { openLogStream, fetchRecentLogs, clearLogs } from './api.js';

let stream;
const events = [];
const logPanel = document.getElementById('log-panel');
const logToggle = document.getElementById('log-toggle');
const logList = document.getElementById('log-list');
const logClear = document.getElementById('log-clear');
const logStatus = document.getElementById('log-status');

function render() {
  if (!logList) return;
  logList.innerHTML = events
    .slice(-200)
    .map(
      (e) => `
      <div class="log-row flex gap-2 items-start">
        <span class="log-ts text-[10px] text-slate-500">${new Date(e.ts).toLocaleTimeString()}</span>
        <span class="log-level text-[10px] px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 uppercase">${e.level}</span>
        <span class="log-step text-[11px] font-semibold text-slate-700 dark:text-slate-200">${e.step}</span>
       <span class="log-msg text-[11px] text-slate-800 dark:text-slate-100 break-words">${e.message}</span>
      </div>`
    )
    .join('');
}

function addEvent(e) {
  events.push(e);
  render();
}

function setStatus(text, variant = 'live') {
  if (!logStatus) return;
  logStatus.textContent = text;
  const base = 'text-[11px] px-2 py-0.5 rounded-full';
  const styles = {
    live: `${base} bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-200`,
    fallback: `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200`,
    error: `${base} bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200`,
  };
  logStatus.className = styles[variant] || base;
}

function startStream() {
  if (stream) stream.close();
  setStatus('live', 'live');
  try {
    stream = openLogStream(addEvent);
    stream.onerror = () => setStatus('polling', 'fallback');
  } catch (e) {
    console.warn('Failed to open SSE stream, falling back to polling', e);
    setStatus('polling', 'fallback');
  }
}

async function loadRecent() {
  try {
    const data = await fetchRecentLogs(200);
    (data.events || []).forEach(addEvent);
  } catch (e) {
    console.error('Failed to load recent logs', e);
    setStatus('error', 'error');
  }
}

async function handleClear() {
  try {
    await clearLogs();
    events.length = 0;
    render();
  } catch (e) {
    console.error('Failed to clear logs', e);
  }
}

function togglePanel() {
  if (!logPanel) return;
  logPanel.classList.toggle('hidden');
  if (!logPanel.classList.contains('hidden') && events.length === 0) {
    loadRecent();
  }
}

export function initLogs() {
  loadRecent();
  startStream();
  if (logClear) {
    logClear.addEventListener('click', handleClear);
  }
  if (logToggle) {
    logToggle.addEventListener('click', togglePanel);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initLogs();
});
