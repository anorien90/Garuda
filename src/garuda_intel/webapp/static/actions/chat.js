import { els, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderChat } from '../render-chat.js';

export async function chatAsk(e) {
  if (e) e.preventDefault();
  if (!els.chatAnswer) return;
  const qEl = getEl('chat-q');
  const entityEl = getEl('chat-entity');
  const topkEl = getEl('chat-topk');
  if (!qEl || !entityEl || !topkEl) {
    els.chatAnswer.innerHTML = '<div class="p-4 text-rose-500">Chat form is missing from the page.</div>';
    return;
  }

  els.chatAnswer.innerHTML = '<div class="p-4 animate-pulse text-brand-600">Thinking (will search online if needed)...</div>';
  try {
    const body = {
      question: qEl.value,
      entity: entityEl.value,
      top_k: Number(topkEl.value || 6),
    };
    const res = await fetchWithAuth('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    renderChat(await res.json());
  } catch (err) {
    els.chatAnswer.innerHTML = `<div class="p-4 text-rose-500">${err.message}</div>`;
  }
}
