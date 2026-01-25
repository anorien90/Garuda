export const DEFAULT_BASE_URL = 'http://localhost:8080';

export const els = {
  // --- Settings & Status ---
  baseUrl: document.getElementById('base-url'),
  apiKey: document.getElementById('api-key'),
  dbUrl: document.getElementById('db-url'),
  qdrantUrl: document.getElementById('qdrant-url'),
  qdrantCollection: document.getElementById('qdrant-collection'),
  embeddingModel: document.getElementById('embedding-model'),
  ollamaUrl: document.getElementById('ollama-url'),
  ollamaModel: document.getElementById('ollama-model'),
  saveBtn: document.getElementById('save-settings'),
  saveStatus: document.getElementById('save-status'),
  statusBtn: document.getElementById('refresh-status'),
  statusCards: document.getElementById('status-cards'),
  statusBadges: {
    api: document.getElementById('status-api'),
    db: document.getElementById('status-db'),
    vector: document.getElementById('status-vector'),
    llm: document.getElementById('status-llm'),
  },
  healthIndicator: document.getElementById('health-indicator'),

  // --- Log / Steps panel ---
  logList: document.getElementById('log-list'),
  logClearBtn: document.getElementById('log-clear'),

  // --- Forms & Results ---
  searchForm: document.getElementById('search-form'),
  results: document.getElementById('results'),

  semanticForm: document.getElementById('semantic-form'),
  semanticResults: document.getElementById('semantic-results'),

  chatForm: document.getElementById('chat-form'),
  chatAnswer: document.getElementById('chat-answer'),
  chatToggle: document.getElementById('chat-toggle'),
  chatContainer: document.getElementById('chat-container'),

  pagesBtn: document.getElementById('load-pages'),
  pagesLimit: document.getElementById('pages-limit'),
  pagesSearch: document.getElementById('pages-search'),
  pagesList: document.getElementById('pages'),
  pageDetail: document.getElementById('page-detail'),
  pageModal: document.getElementById('page-modal'),
  pageModalContent: document.getElementById('page-modal-content'),
  pageModalClose: document.getElementById('page-modal-close'),

  // --- Recorder & Crawl ---
  recorderSearchForm: document.getElementById('recorder-search-form'),
  recorderResults: document.getElementById('recorder-results'),
  recorderHealth: document.getElementById('recorder-health'),
  recorderHealthRefresh: document.getElementById('recorder-health-refresh'),
  recorderMarkForm: document.getElementById('recorder-mark-form'),
  recorderMarkStatus: document.getElementById('recorder-mark-status'),

  crawlForm: document.getElementById('crawl-form'),
  crawlOutputPanel: document.getElementById('crawl-output-panel'),

  // --- Navigation & Theme ---
  themeToggle: document.getElementById('theme-toggle'),
  themeToggleLabel: document.getElementById('theme-toggle-label'),
  themeToggleIcon: document.getElementById('theme-toggle-icon'),
  tabButtons: document.querySelectorAll('[data-tab-btn]'),
  tabPanels: document.querySelectorAll('[data-tab-panel]'),
};

export const getEl = (id) => document.getElementById(id);
export const val = (id) => {
  const el = getEl(id);
  return el ? el.value : '';
};
