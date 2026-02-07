import { els, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { renderChat, renderAutonomousInChat } from '../render-chat.js';

export async function chatAsk(e) {
  if (e) e.preventDefault();
  if (!els.chatAnswer) return;
  const qEl = getEl('chat-q');
  const entityEl = getEl('chat-entity');
  const topkEl = getEl('chat-topk');
  const maxCyclesEl = getEl('chat-max-cycles');
  const autonomousModeEl = getEl('chat-autonomous-mode');
  
  if (!qEl || !entityEl || !topkEl) {
    els.chatAnswer.innerHTML = '<div class="p-4 text-rose-500">Chat form is missing from the page.</div>';
    return;
  }

  const autonomousModeEnabled = autonomousModeEl ? autonomousModeEl.checked : false;
  
  // Phase indicator with animation
  const updatePhase = (phase, message) => {
    els.chatAnswer.innerHTML = `
      <div class="p-4 space-y-2">
        <div class="animate-pulse text-brand-600 font-semibold">${phase}</div>
        <div class="text-sm text-slate-600 dark:text-slate-400">${message}</div>
      </div>
    `;
  };

  updatePhase('Phase 1: RAG Search...', 'Searching through embeddings, graph, and SQL data');

  try {
    const body = {
      question: qEl.value,
      entity: entityEl.value,
      top_k: Number(topkEl.value || 6),
      max_search_cycles: Number((maxCyclesEl && maxCyclesEl.value) || 3),
    };
    
    const res = await fetchWithAuth('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    
    const chatData = await res.json();
    
    // Show appropriate phase messages based on what happened
    if (chatData.retry_attempted) {
      updatePhase('Phase 2: Paraphrasing...', 'Retrying with alternative queries');
      await new Promise(resolve => setTimeout(resolve, 500)); // Brief visual feedback
    }
    
    if (chatData.online_search_triggered) {
      const cycles = chatData.search_cycles_completed || 0;
      const maxCycles = chatData.max_search_cycles || 0;
      updatePhase(`Phase 3: Web Crawling (${cycles}/${maxCycles} cycles)...`, 'Discovering and indexing online sources');
      await new Promise(resolve => setTimeout(resolve, 500)); // Brief visual feedback
    }
    
    // Render the main chat result
    renderChat(chatData);
    
    // If autonomous mode is enabled, trigger autonomous discovery
    if (autonomousModeEnabled) {
      try {
        // Add autonomous loading indicator to the chat answer area
        const autonomousDiv = document.createElement('div');
        autonomousDiv.id = 'autonomous-results';
        autonomousDiv.className = 'mt-4 p-4 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-lg';
        autonomousDiv.innerHTML = `
          <div class="animate-pulse text-indigo-600 dark:text-indigo-400 font-semibold">
            🤖 Autonomous Mode: Discovering knowledge gaps...
          </div>
        `;
        els.chatAnswer.appendChild(autonomousDiv);
        
        // Call autonomous endpoint
        const autonomousRes = await fetchWithAuth('/api/agent/autonomous', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            auto_crawl: true,
            max_entities: 10,
            priority_threshold: 0.3,
            max_depth: 3,
            max_pages: 25,
          }),
        });
        
        const autonomousData = await autonomousRes.json();
        
        // Render autonomous results
        renderAutonomousInChat(autonomousData);
        
      } catch (autonomousErr) {
        // Show error but don't break the main chat experience
        const autonomousDiv = document.getElementById('autonomous-results');
        if (autonomousDiv) {
          autonomousDiv.innerHTML = `
            <div class="text-rose-500 text-sm">
              ⚠️ Autonomous discovery failed: ${autonomousErr.message}
            </div>
          `;
        }
      }
    }
    
  } catch (err) {
    els.chatAnswer.innerHTML = `<div class="p-4 text-rose-500">❌ Error: ${err.message || 'Unknown error occurred'}</div>`;
  }
}
