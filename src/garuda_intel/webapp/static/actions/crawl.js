import { els, val, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderCrawlResult } from '../ui.js';

export async function runCrawl(e) {
  if (e) e.preventDefault();
  if (els.crawlOutputPanel) els.crawlOutputPanel.innerHTML = '<div class="p-4 animate-pulse text-xs text-slate-500">Crawl initiated...</div>';
  try {
    const body = {
      entity: val('crawl-entity'),
      type: val('crawl-type'),
      max_pages: Number(val('crawl-max-pages') || 10),
      total_pages: Number(val('crawl-total-pages') || 50),
      max_depth: Number(val('crawl-max-depth') || 2),
      score_threshold: Number(val('crawl-score-threshold') || 35),
      seed_limit: Number(val('crawl-seed-limit') || 25),
      use_selenium: !!getEl('crawl-use-selenium')?.checked,
      active_mode: !!getEl('crawl-active-mode')?.checked,
      output: val('crawl-output') || '',
      fetch_text: val('crawl-fetch-url') || '',
      refresh: !!getEl('crawl-refresh')?.checked,
      refresh_batch: Number(val('crawl-refresh-batch') || 50),
    };

    const res = await fetchWithAuth('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (els.crawlOutputPanel) {
      els.crawlOutputPanel.innerHTML = renderCrawlResult(data);
    }
  } catch (err) {
    if (els.crawlOutputPanel) els.crawlOutputPanel.innerHTML = `<div class="text-rose-500 text-sm">${err.message}</div>`;
  }
}
