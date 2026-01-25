import { els, DEFAULT_BASE_URL } from './config.js';

export function getBaseUrl() {
  const fromInput = els.baseUrl && els.baseUrl.value ? els.baseUrl.value : null;
  const fromStorage = localStorage.getItem('garuda_base_url');
  return (fromInput || fromStorage || DEFAULT_BASE_URL).trim().replace(/\/+$/, '');
}

export function getApiKey() {
  const fromInput = els.apiKey && els.apiKey.value ? els.apiKey.value : null;
  const fromStorage = localStorage.getItem('garuda_api_key');
  return (fromInput || fromStorage || '').trim();
}

export function loadSettings() {
  const base = localStorage.getItem('garuda_base_url') || DEFAULT_BASE_URL;
  const key = localStorage.getItem('garuda_api_key') || '';
  if (els.baseUrl) els.baseUrl.value = base;
  if (els.apiKey) els.apiKey.value = key;

  if (els.dbUrl) els.dbUrl.value = localStorage.getItem('garuda_db_url') || '';
  if (els.qdrantUrl) els.qdrantUrl.value = localStorage.getItem('garuda_qdrant_url') || '';
  if (els.qdrantCollection) els.qdrantCollection.value = localStorage.getItem('garuda_qdrant_collection') || '';
  if (els.embeddingModel) els.embeddingModel.value = localStorage.getItem('garuda_embedding_model') || '';
  if (els.ollamaUrl) els.ollamaUrl.value = localStorage.getItem('garuda_ollama_url') || '';
  if (els.ollamaModel) els.ollamaModel.value = localStorage.getItem('garuda_ollama_model') || '';
}

export function saveSettings() {
  const base = getBaseUrl();
  const key = getApiKey();
  localStorage.setItem('garuda_base_url', base);
  localStorage.setItem('garuda_api_key', key);

  if (els.baseUrl) els.baseUrl.value = base;
  if (els.apiKey) els.apiKey.value = key;

  if (els.dbUrl) localStorage.setItem('garuda_db_url', (els.dbUrl.value || '').trim());
  if (els.qdrantUrl) localStorage.setItem('garuda_qdrant_url', (els.qdrantUrl.value || '').trim());
  if (els.qdrantCollection) localStorage.setItem('garuda_qdrant_collection', (els.qdrantCollection.value || '').trim());
  if (els.embeddingModel) localStorage.setItem('garuda_embedding_model', (els.embeddingModel.value || '').trim());
  if (els.ollamaUrl) localStorage.setItem('garuda_ollama_url', (els.ollamaUrl.value || '').trim());
  if (els.ollamaModel) localStorage.setItem('garuda_ollama_model', (els.ollamaModel.value || '').trim());

  if (els.saveStatus) {
    els.saveStatus.textContent = 'Saved';
    setTimeout(() => (els.saveStatus.textContent = ''), 1500);
  }
}
