import { getBaseUrl, getApiKey } from './storage.js';

// Generic fetch that always applies the API key header.
export async function fetchWithAPIKey(path, opts = {}) {
  const base = getBaseUrl();
  const endpoint = path.startsWith('/') ? path : `/${path}`;
  const url = base + endpoint;

  const headers = { ...(opts.headers || {}) };
  const key = getApiKey();
  if (key) headers['X-API-Key'] = key;
  
  // Automatically add Content-Type header for JSON requests
  if (opts.body && typeof opts.body === 'string' && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const res = await fetch(url, { ...opts, headers });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API Error ${res.status}: ${text}`);
    }
    return res;
  } catch (err) {
    console.error('Fetch failed:', err);
    throw new Error(`Connection failed to ${url}. Check if backend is running on port 8080.`);
  }
}

// Backward-compatible alias (if other code imports fetchWithAuth)
export const fetchWithAuth = fetchWithAPIKey;

// SSE log stream still must send the api_key via query param (EventSource cannot set headers).
export function openLogStream(onEvent) {
  const base = getBaseUrl();
  const key = getApiKey();
  const qp = key ? `?api_key=${encodeURIComponent(key)}` : '';
  const url = base + `/api/logs/stream${qp}`;
  const es = new EventSource(url, { withCredentials: false });
  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      onEvent?.(data);
    } catch (e) {
      console.error('Bad log event', e, ev.data);
    }
  };
  es.onerror = (err) => {
    console.warn('Log stream error (will rely on polling fallback)', err);
  };
  return es;
}

export async function fetchRecentLogs(limit = 200) {
  const res = await fetchWithAPIKey(`/api/logs/recent?limit=${limit}`);
  return res.json();
}

export async function clearLogs() {
  const res = await fetchWithAPIKey('/api/logs/clear', { method: 'POST' });
  return res.json();
}
