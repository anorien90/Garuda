// Always loads API key/server_url from chrome.storage before every fetch.
// Never uses unsaved input fields! Only gets from storage for ALL network requests.

// Tabs
for(let tab of document.querySelectorAll('.tab')) {
  tab.onclick = function() {
    for(let t of document.querySelectorAll('.tab')) t.classList.remove('selected');
    for(let tc of document.querySelectorAll('.tabcontent')) tc.classList.remove('active');
    tab.classList.add('selected');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
  };
}

function getSettings(cb) {
  chrome.storage.local.get(['server_url','api_key'], items => {
    cb({
      server_url: items.server_url || "http://127.0.0.1:8765",
      api_key: items.api_key || ""
    });
  });
}
function setSettings(s) {
  chrome.storage.local.set({"server_url": s.server_url, "api_key":s.api_key});
}

// Save settings
document.getElementById("save-settings").onclick = () => {
  setSettings({
    server_url: document.getElementById("server-url").value,
    api_key: document.getElementById("api-key").value
  });
  document.getElementById("settings-saved").textContent = "Saved!";
  setTimeout(()=>document.getElementById("settings-saved").textContent="", 1300);
};

// Load settings into fields on popup open
getSettings(s => {
  document.getElementById("server-url").value = s.server_url;
  document.getElementById("api-key").value = s.api_key;
});

// ---- Recorder tab
// Always use stored key for backend requests
function sendCommand(cmd) {
  getSettings(s => {
    if (!s.api_key) {
      document.getElementById("status").textContent = "Missing API Key! Please set it in Settings.";
      return;
    }
    chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
      chrome.tabs.sendMessage(
        tabs[0].id,
        {command: cmd, session_id: document.getElementById("session_id").value, settings: s}
      );
    });
  });
}
document.getElementById("mark-page").onclick = () => sendCommand("mark_page");
document.getElementById("mark-element").onclick = () => sendCommand("mark_element");
document.getElementById("mark-image").onclick = () => sendCommand("mark_image");
chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {
  if(message.status) document.getElementById("status").textContent = message.status;
});

// ---- Search tab (always use API key!)
document.getElementById("search-btn").onclick = function() {
  getSettings(s => {
    if (!s.api_key) {
      document.getElementById("search-results").textContent = "Missing API Key! Set it on the Settings tab.";
      return;
    }
    let q = document.getElementById("search-q").value;
    fetch(`${s.server_url}/search?q=${encodeURIComponent(q)}`, {
      headers: {"X-API-Key": s.api_key}
    }).then(resp => {
      if (resp.status === 401) throw new Error("Unauthorized (check API key)");
      return resp.json();
    }).then(data => {
      let out = "";
      (data.results||[]).forEach(r=>{
        out += `<div><b>${r.url}</b><br>${r.snippet||""}</div><hr>`;
      });
      document.getElementById("search-results").innerHTML = out || "No results.";
    }).catch(e=>{
      document.getElementById("search-results").textContent = "Err: "+e;
    });
  });
};
// ---- View tab (always use API key!)
document.getElementById("view-btn").onclick = function() {
  getSettings(s => {
    if (!s.api_key) {
      document.getElementById("view-content").textContent = "Missing API Key! Set it on the Settings tab.";
      return;
    }
    let url = document.getElementById("view-url").value;
    fetch(`${s.server_url}/view?url=${encodeURIComponent(url)}`, {
      headers: {"X-API-Key": s.api_key}
    }).then(resp => {
      if (resp.status === 401) throw new Error("Unauthorized (check API key)");
      return resp.json();
    }).then(data => {
      document.getElementById("view-content").textContent = JSON.stringify(data, null, 2);
    }).catch(e=>{
      document.getElementById("view-content").textContent = "Err: "+e;
    });
  });
};
