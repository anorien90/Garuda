import { els, getEl } from '../config.js';
import { fetchWithAuth } from '../api.js';
import { submitAndPoll, cancelTask, getActiveTasks, pollTaskResult } from '../task-poller.js';
import { renderChat, renderAutonomousInChat } from '../render-chat.js';

export async function chatAsk(e) {
  if (e) e.preventDefault();
  
  // Find the correct answer container relative to the submitted form
  const submittedForm = e && e.target;
  const chatContainer = submittedForm ? submittedForm.closest('#chat-container') : null;
  const answerEl = chatContainer
    ? chatContainer.querySelector('#chat-answer')
    : els.chatAnswer;
  
  if (!answerEl) return;
  // Resolve input elements relative to the submitted form so that
  // the correct values are read when chat.html is included more than
  // once on the page (e.g. search-tab AND floating chat widget).
  const qEl = submittedForm ? submittedForm.querySelector('#chat-q') : getEl('chat-q');
  const entityEl = submittedForm ? submittedForm.querySelector('#chat-entity') : getEl('chat-entity');
  const topkEl = submittedForm ? submittedForm.querySelector('#chat-topk') : getEl('chat-topk');
  const maxCyclesEl = submittedForm ? submittedForm.querySelector('#chat-max-cycles') : getEl('chat-max-cycles');
  const autonomousModeEl = submittedForm ? submittedForm.querySelector('#chat-autonomous-mode') : getEl('chat-autonomous-mode');
  
  if (!qEl || !entityEl || !topkEl) {
    answerEl.innerHTML = '<div class="p-4 text-rose-500">Chat form is missing from the page.</div>';
    return;
  }

  const question = qEl.value;
  const entity = entityEl.value;
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
  
  // If multiple tasks exist, process the most recent one
  // (In future, could create separate containers for each task)
  const mostRecentTask = chatTasks[chatTasks.length - 1];
  
  try {
    const result = await pollTaskResult(mostRecentTask.taskId, {
      statusElement: answerEl,
    });
    renderChat(result, answerEl);
  } catch (err) {
    answerEl.innerHTML = `<div class="p-4 text-rose-500">❌ Previous task failed: ${err.message}</div>`;
  }
}
