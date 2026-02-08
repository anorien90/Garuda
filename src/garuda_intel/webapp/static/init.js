import { els } from './config.js';
import { initTheme } from './theme.js';
import { loadSettings, saveSettings } from './storage.js';
import { initTabs } from './tabs.js';
import { refreshStatus } from './status.js';
import { searchIntel } from './actions/search.js';
import { semanticSearch } from './actions/semantic.js';
import { chatAsk, resumeActiveChatTasks } from './actions/chat.js';
import { loadPages } from './actions/pages.js';
import { recorderSearch, recorderRefreshHealth, recorderMark } from './actions/recorder.js';
import { runCrawl, runIntelligentCrawl, runUnifiedCrawl } from './actions/crawl.js';
import { analyzeEntityGaps, analyzeAllGaps } from './actions/gaps.js';
import { bindDelegatedEvents } from './events.js';
import { initEntitiesGraph } from './entities-graph.js';

// Import graph search functionality
import './graph-search.js';

export function init() {
  initTheme();
  loadSettings();
  initTabs();
  
  // Resume any active chat tasks that may have been interrupted by page reload
  resumeActiveChatTasks();

  if (els.saveBtn) els.saveBtn.onclick = saveSettings;
  if (els.statusBtn) els.statusBtn.onclick = refreshStatus;
  if (els.themeToggle) {
    els.themeToggle.onclick = () => {
      const current = localStorage.getItem('garuda_theme') || (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
      const next = current === 'dark' ? 'light' : 'dark';
      import('./theme.js').then(({ applyTheme }) => applyTheme(next));
    };
  }
  if (els.chatToggle) {
    els.chatToggle.onclick = () => {
      const popupContainer = document.getElementById('popup-chat-container');
      if (popupContainer) popupContainer.classList.toggle('hidden');
    };
  }

  if (els.searchForm) els.searchForm.onsubmit = searchIntel;
  if (els.semanticForm) els.semanticForm.onsubmit = semanticSearch;
  
  // Bind all chat forms (popup and search tab)
  document.querySelectorAll('#popup-chat-form, #search-tab-chat-form').forEach(form => {
    form.addEventListener('submit', chatAsk);
  });
  if (els.pagesLoad) els.pagesLoad.onclick = loadPages;
  if (els.pagesLimit) els.pagesLimit.onchange = loadPages;
  if (els.pagesSearch) els.pagesSearch.oninput = () => loadPages({ clientOnly: true });
  if (els.recorderSearchForm) els.recorderSearchForm.onsubmit = recorderSearch;
  if (els.recorderHealthRefresh) els.recorderHealthRefresh.onclick = recorderRefreshHealth;
  if (els.recorderMarkForm) els.recorderMarkForm.onsubmit = recorderMark;
  if (els.crawlForm) els.crawlForm.onsubmit = runCrawl;
  
  // NEW: Intelligent crawl button
  const btnIntelligentCrawl = document.getElementById('btn-intelligent-crawl');
  if (btnIntelligentCrawl) btnIntelligentCrawl.onclick = runIntelligentCrawl;
  
  // NEW: Unified smart crawl button
  const btnUnifiedCrawl = document.getElementById('btn-unified-crawl');
  if (btnUnifiedCrawl) btnUnifiedCrawl.onclick = runUnifiedCrawl;
  
  // NEW: Gap analysis buttons
  const btnAnalyzeGaps = document.getElementById('btn-analyze-gaps');
  if (btnAnalyzeGaps) btnAnalyzeGaps.onclick = analyzeEntityGaps;
  
  const btnAnalyzeAllGaps = document.getElementById('btn-analyze-all-gaps');
  if (btnAnalyzeAllGaps) btnAnalyzeAllGaps.onclick = analyzeAllGaps;

  initEntitiesGraph();

  bindDelegatedEvents();
  refreshStatus();
}
