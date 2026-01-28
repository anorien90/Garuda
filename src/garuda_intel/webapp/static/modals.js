function ensureModalRoot() {
  let root = document.getElementById('modal-root');
  if (!root) {
    root = document.createElement('div');
    root.id = 'modal-root';
    document.body.appendChild(root);
  }
  return root;
}

export function closeModal(id, callback) {
  const el = document.getElementById(id);
  if (el) {
    el.remove();
    if (callback && typeof callback === 'function') {
      callback();
    }
  }
}

export function updateModal(id, { title, content }) {
  const el = document.getElementById(id);
  if (!el) return false;
  
  if (title !== undefined) {
    const titleEl = el.querySelector('h3');
    if (titleEl) titleEl.textContent = title;
  }
  
  if (content !== undefined) {
    const contentEl = el.querySelector('.max-h-\\[70vh\\]');
    if (contentEl) contentEl.innerHTML = content;
  }
  
  return true;
}

export function showModal({ title = 'Details', content = '', size = 'md', onClose = null }) {
  const root = ensureModalRoot();
  const id = `modal-${Date.now()}`;
  const widths = { sm: 'max-w-md', md: 'max-w-3xl', lg: 'max-w-5xl' };
  const wrapper = document.createElement('div');
  wrapper.id = id;
  wrapper.className = 'fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm';
  wrapper.innerHTML = `
    <div class="w-full ${widths[size] || widths.md} bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      <div class="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700">
        <h3 class="text-lg font-semibold text-slate-900 dark:text-white">${title}</h3>
        <button class="text-slate-500 hover:text-slate-800 dark:hover:text-slate-200" aria-label="Close">&times;</button>
      </div>
      <div class="max-h-[70vh] overflow-y-auto px-4 py-3 text-sm text-slate-800 dark:text-slate-200">${content}</div>
    </div>
  `;
  const closeHandler = () => closeModal(id, onClose);
  wrapper.querySelector('button').onclick = closeHandler;
  wrapper.onclick = (e) => { if (e.target === wrapper) closeHandler(); };
  root.appendChild(wrapper);
  return id;
}
