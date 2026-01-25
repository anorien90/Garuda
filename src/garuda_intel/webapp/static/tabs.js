import { els } from './config.js';

export function setActiveTab(name) {
  const panelExists = !!document.querySelector(`[data-tab-panel="${name}"]`);
  const safeName = panelExists ? name : 'overview';

  els.tabButtons.forEach((btn) => {
    const isActive = btn.dataset.tabBtn === safeName;
    if (isActive) {
      btn.classList.add('active', 'bg-brand-600', 'text-white', 'shadow-sm', 'border-transparent');
      btn.classList.remove('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-slate-100', 'border-slate-200', 'dark:border-slate-700');
    } else {
      btn.classList.remove('active', 'bg-brand-600', 'text-white', 'shadow-sm', 'border-transparent');
      btn.classList.add('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-slate-100', 'border-slate-200', 'dark:border-slate-700');
    }
  });
  els.tabPanels.forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.tabPanel !== safeName);
    panel.setAttribute('aria-hidden', panel.dataset.tabPanel !== safeName);
  });
  localStorage.setItem('garuda_active_tab', safeName);
}

export function initTabs() {
  const saved = localStorage.getItem('garuda_active_tab') || 'overview';
  setActiveTab(saved);
  els.tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => setActiveTab(btn.dataset.tabBtn));
  });
}
