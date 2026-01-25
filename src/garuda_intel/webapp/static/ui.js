export function pill(text) {
  return `<span class="inline-flex items-center rounded-full bg-brand-100 text-brand-800 dark:bg-brand-900/60 dark:text-brand-100 px-2 py-0.5 text-xs font-medium">${text}</span>`;
}

export function chips(arr = []) {
  return arr.filter(Boolean).map((t) => pill(t)).join(' ');
}

export function setStatusBadge(el, ok) {
  if (!el) return;
  const okCls = ['bg-emerald-500'];
  const badCls = ['bg-rose-500'];
  el.classList.remove(...okCls, ...badCls);
  el.classList.add(ok ? 'bg-emerald-500' : 'bg-rose-500');
}

export function collapsible(label, content) {
  if (!content) return '';
  return `
    <details class="text-xs my-1 group">
      <summary class="cursor-pointer font-bold">${label}</summary>
      <div class="mt-2 ml-2">${content}</div>
    </details>
  `;
}

export function renderKeyValTable(obj) {
  if (!obj || typeof obj !== 'object') return '';
  return `
    <table class="text-xs w-full mb-2">
      <tbody>
        ${Object.entries(obj).map(([k, v]) => `<tr><td class="pr-1 text-slate-400">${k}</td><td>${v}</td></tr>`).join('')}
      </tbody>
    </table>
  `;
}
