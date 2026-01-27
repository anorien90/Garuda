import { els } from './config.js';
import { initTheme } from './theme.js';
import { loadSettings, saveSettings } from './storage.js';
import { initTabs } from './tabs.js';
import { refreshStatus } from './status.js';
import { searchIntel } from './actions/search.js';
import { semanticSearch } from './actions/semantic.js';
import { chatAsk } from './actions/chat.js';
import { loadPages } from './actions/pages.js';
import { recorderSearch, recorderRefreshHealth, recorderMark } from './actions/recorder.js';
import { runCrawl } from './actions/crawl.js';
import { bindDelegatedEvents } from './events.js';
import { initEntitiesGraph } from './entities-graph.js';

export function init() {
  initTheme();
  loadSettings();
  initTabs();

  if (els.saveBtn) els.saveBtn.onclick = saveSettings;
  if (els.statusBtn) els.statusBtn.onclick = refreshStatus;
  if (els.themeToggle) {
    els.themeToggle.onclick = () => {
      const current = localStorage.getItem('garuda_theme') || (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
      const next = current === 'dark' ? 'light' : 'dark';
      import('./theme.js').then(({ applyTheme }) => applyTheme(next));
    };
  }
  if (els.chatToggle && els.chatContainer) {
    els.chatToggle.onclick = () => els.chatContainer.classList.toggle('hidden');
  }

  if (els.searchForm) els.searchForm.onsubmit = searchIntel;
  if (els.semanticForm) els.semanticForm.onsubmit = semanticSearch;
  if (els.chatForm) els.chatForm.onsubmit = chatAsk;
  if (els.pagesLoad) els.pagesLoad.onclick = loadPages;
  if (els.pagesLimit) els.pagesLimit.onchange = loadPages;
  if (els.pagesSearch) els.pagesSearch.oninput = () => loadPages({ clientOnly: true });
  if (els.recorderSearchForm) els.recorderSearchForm.onsubmit = recorderSearch;
  if (els.recorderHealthRefresh) els.recorderHealthRefresh.onclick = recorderRefreshHealth;
  if (els.recorderMarkForm) els.recorderMarkForm.onsubmit = recorderMark;
  if (els.crawlForm) els.crawlForm.onsubmit = runCrawl;

  initEntitiesGraph();

  bindDelegatedEvents();
  refreshStatus();
}
