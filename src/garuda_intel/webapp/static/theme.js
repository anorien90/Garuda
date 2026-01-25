import { els } from './config.js';

export function applyTheme(mode) {
  const root = document.documentElement;
  const next = mode === 'dark' ? 'dark' : 'light';
  root.classList.toggle('dark', next === 'dark');
  root.dataset.theme = next;
  localStorage.setItem('garuda_theme', next);
  if (els.themeToggleLabel) els.themeToggleLabel.textContent = next === 'dark' ? 'Dark' : 'Light';
  if (els.themeToggleIcon) els.themeToggleIcon.textContent = next === 'dark' ? '🌙' : '🌞';
}

export function initTheme() {
  const saved = localStorage.getItem('garuda_theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (prefersDark ? 'dark' : 'light'));
}
