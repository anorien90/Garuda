import { els, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { submitAndPoll, cancelTask, getActiveTasks, pollTaskResult } from '../task-poller.js';
import { renderChat, renderAutonomousInChat } from '../render-chat.js';

export async function chatAsk(e) {
  if (e) e.preventDefault();
  
  // Find the correct answer container relative to the submitted form
  const submittedForm = e && e.target;
  const formId = submittedForm?.id;
  
  let answerEl, qEl, entityEl, topkEl, maxCyclesEl, autonomousModeEl;
  
  // Determine which form was submitted and get the corresponding elements
  if (formId === 'popup-chat-form') {
    // Popup chat form
    answerEl = document.getElementById('popup-chat-answer');
    qEl = document.getElementById('popup-chat-q');
    entityEl = document.getElementById('popup-chat-entity');
    topkEl = document.getElementById('popup-chat-topk');
    maxCyclesEl = document.getElementById('popup-chat-max-cycles');
    autonomousModeEl = document.getElementById('popup-chat-autonomous-mode');
  } else if (formId === 'search-tab-chat-form') {
    // Search tab chat form
    answerEl = document.getElementById('search-tab-chat-answer');
    qEl = document.getElementById('search-tab-chat-q');
    entityEl = document.getElementById('search-tab-chat-entity');
    topkEl = document.getElementById('search-tab-chat-topk');
    maxCyclesEl = document.getElementById('search-tab-chat-max-cycles');
    autonomousModeEl = document.getElementById('search-tab-chat-autonomous-mode');
  } else {
    // Minimal fallback - should rarely be needed with new structure
    console.warn('Chat form submitted without recognized ID, using fallback detection');
    answerEl = els.chatAnswer;
    qEl = getEl('chat-q');
    entityEl = getEl('chat-entity');
    topkEl = getEl('chat-topk');
    maxCyclesEl = getEl('chat-max-cycles');
    autonomousModeEl = getEl('chat-autonomous-mode');
  }
  
  if (!answerEl) {
    console.error('No answer container found');
    return;
  }
  
  if (!qEl || !topkEl) {
    answerEl.innerHTML = '<div class="p-4 text-rose-500">Chat form is missing required fields.</div>';
    return;
  }

  const question = qEl.value;
  const entity = entityEl?.value || '';
  const autonomousModeEnabled = autonomousModeEl ? autonomousModeEl.checked : false;

  try {
    // Use task queue for chat - persistent across page reloads
    const chatData = await submitAndPoll('/api/agent/chat', {
      question: question,
      entity: entity,
    }, {
      statusElement: answerEl,
      onProgress: (progress, message) => {
        // Progress updates are shown via statusElement
      },
    });
    
    // Render the main chat result
    renderChat(chatData, answerEl);
    
    // If autonomous mode is enabled, trigger autonomous discovery via task queue
    if (autonomousModeEnabled) {
      try {
        const autonomousDiv = document.createElement('div');
        autonomousDiv.id = 'autonomous-results';
        autonomousDiv.className = 'mt-4 p-4 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-lg';
        answerEl.appendChild(autonomousDiv);
        
        const autonomousData = await submitAndPoll('/api/agent/autonomous', {
          auto_crawl: true,
          max_entities: 10,
          priority_threshold: 0.3,
          max_depth: 3,
          max_pages: 25,
        }, {
          statusElement: autonomousDiv,
        });
        
        renderAutonomousInChat(autonomousData);
      } catch (autonomousErr) {
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
    answerEl.innerHTML = `<div class="p-4 text-rose-500">❌ Error: ${err.message || 'Unknown error occurred'}</div>`;
  }
}

/**
 * Resume polling for any active chat tasks after page reload.
 * Note: Multiple tasks render to the same element, so only the last completed
 * task's result will be visible. Consider UI enhancement to show all tasks.
 */
export async function resumeActiveChatTasks() {
  const activeTasks = getActiveTasks();
  const chatTasks = activeTasks.filter(task => task.endpoint === '/api/agent/chat');
  
  if (chatTasks.length === 0) return;
  
  const answerEl = els.chatAnswer;
  if (!answerEl) return;
  
  // Resume only the most recent task; clear older ones to prevent storage buildup
  const mostRecentTask = chatTasks[chatTasks.length - 1];
  const olderTaskIds = chatTasks.slice(0, -1).map(t => t.taskId);
  if (olderTaskIds.length > 0) {
    const remaining = getActiveTasks().filter(t => !olderTaskIds.includes(t.taskId));
    localStorage.setItem('garuda_active_tasks', JSON.stringify(remaining));
  }
  
  try {
    const result = await pollTaskResult(mostRecentTask.taskId, {
      statusElement: answerEl,
    });
    renderChat(result, answerEl);
  } catch (err) {
    answerEl.innerHTML = `<div class="p-4 text-rose-500">❌ Previous task failed: ${err.message}</div>`;
  }
}
