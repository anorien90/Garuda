export const DEFAULT_BASE_URL = 'http://localhost:8080';
export const API_BASE = DEFAULT_BASE_URL;

export const els = {
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

  logList: document.getElementById('log-list'),
  logClearBtn: document.getElementById('log-clear'),

  searchForm: document.getElementById('search-form'),
  results: document.getElementById('results'),

  semanticForm: document.getElementById('semantic-form'),
  semanticResults: document.getElementById('semantic-results'),

  chatForm: document.getElementById('chat-form'),
  chatAnswer: document.getElementById('chat-answer'),
  chatToggle: document.getElementById('chat-toggle'),
  chatContainer: document.getElementById('chat-container'),
  
  pagesList: document.getElementById('pages'),
  pageDetail: document.getElementById('page-detail'),
  pagesSearch: document.getElementById('pages-search'),
  pagesEntityFilter: document.getElementById('pages-entity-filter'),
  pagesTypeFilter: document.getElementById('pages-type-filter'),
  pagesMinScore: document.getElementById('pages-min-score'),
  pagesSort: document.getElementById('pages-sort'),
  pagesLimit: document.getElementById('pages-limit'),
  pagesLoad: document.getElementById('load-pages'),
  pageModal: document.getElementById('page-modal'),
  pageModalContent: document.getElementById('page-modal-content'),
  pageModalClose: document.getElementById('page-modal-close'),

  recorderSearchForm: document.getElementById('recorder-search-form'),
  recorderResults: document.getElementById('recorder-results'),
  recorderHealth: document.getElementById('recorder-health'),
  recorderHealthRefresh: document.getElementById('recorder-health-refresh'),
  recorderMarkForm: document.getElementById('recorder-mark-form'),
  recorderMarkStatus: document.getElementById('recorder-mark-status'),

  crawlForm: document.getElementById('crawl-form'),
  crawlOutputPanel: document.getElementById('crawl-output-panel'),

  themeToggle: document.getElementById('theme-toggle'),
  themeToggleLabel: document.getElementById('theme-toggle-label'),
  themeToggleIcon: document.getElementById('theme-toggle-icon'),
  tabButtons: document.querySelectorAll('[data-tab-btn]'),
  tabPanels: document.querySelectorAll('[data-tab-panel]'),

  entitiesGraphForm: document.getElementById('entities-graph-form'),
  entitiesGraphQuery: document.getElementById('entities-graph-query'),
  entitiesGraphType: document.getElementById('entities-graph-type'),
  entitiesGraphMinScore: document.getElementById('entities-graph-min-score'),
  entitiesGraphLimit: document.getElementById('entities-graph-limit'),
  entitiesGraphLoad: document.getElementById('entities-graph-load'),
  entitiesGraphStatus: document.getElementById('entities-graph-status'),
  entitiesGraphCanvas: document.getElementById('entities-graph-canvas'),
  entitiesGraphLegend: document.getElementById('entities-graph-legend'),
  entitiesGraphDetails: document.getElementById('entities-graph-details'),
};

export const getEl = (id) => document.getElementById(id);
export const val = (id) => {
  const el = document.getElementById(id);
  return el?.value;
};
