import { getLastIntelHits } from './state.js';
import { renderKeyValTable } from './ui.js';
import { showModal, closeModal } from './modals.js';
import { loadPageDetail } from './actions/pages.js';
import { els } from './config.js';

export function bindDelegatedEvents() {
  document.addEventListener('click', (e) => {
    const intelBtn = e.target.closest('[data-intel-detail]');
    if (intelBtn) {
      const card = intelBtn.closest('article');
      if (!card || !card.parentElement) return;
      const idx = Array.from(card.parentElement.children).indexOf(card);
      const hit = getLastIntelHits()[idx];
      const tpl = card.querySelector('template[data-intel-detail-content]');
      const title = card.querySelector('h4')?.textContent || 'Details';
      const content = tpl ? tpl.innerHTML : renderKeyValTable(hit?.data || hit || {});
      showModal({ title, content, size: 'lg' });
      return;
    }

    const pageEl = e.target.closest('[data-page-url]');
    if (pageEl) {
      const url = pageEl.getAttribute('data-page-url');
      if (url) loadPageDetail(url);
      return;
    }
  });

  if (els.pageModalClose) els.pageModalClose.onclick = () => closeModal('page-modal');
  if (els.pageModal) {
    els.pageModal.addEventListener('click', (ev) => {
      if (ev.target === els.pageModal) closeModal('page-modal');
    });
  }
}
