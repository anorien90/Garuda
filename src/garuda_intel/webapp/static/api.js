import { getBaseUrl, getApiKey } from './storage.js';

export async function fetchWithAuth(path, opts = {}) {
  const base = getBaseUrl();
  const endpoint = path.startsWith('/') ? path : `/${path}`;
  const url = base + endpoint;

  const headers = { ...(opts.headers || {}) };
  const key = getApiKey();
  if (key) headers['X-API-Key'] = key;

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
