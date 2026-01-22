function getMarkConfig(cb) {
  chrome.runtime.sendMessage({action: "get_config"}, resp => {
    // Defensive: If response unavailable, warn.
    if (!resp || typeof resp.server_url === "undefined") {
      alert("Mark Recorder: Could not fetch extension settings. Please check your configuration in the Settings tab.");
      cb({server_url: "http://127.0.0.1:8765", api_key: ""});
      return;
    }
    cb(resp);
  });
}

// ----- Listen for popup commands
chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (!msg.command) return requestMark(msg.command, msg.session_id);

  // Fallback: in case popup logic triggers this from old versions
  if (["mark_page", "mark_element", "mark_image"].includes(msg.command)) {
    requestMark(msg.command, msg.session_id);
  }
});

// Main mark function for hotkeys and popup
function requestMark(command, session_id) {
  getMarkConfig(settings => {
    const getHTML = () => document.documentElement.outerHTML;

    if (command === "mark_page") {
      fetch(`${settings.server_url}/mark_page`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": settings.api_key
        },
        body: JSON.stringify({
          mode: "page",
          url: location.href,
          html: getHTML(),
          ts: Date.now()/1000,
          session_id
        })
      }).then(resp => {
        chrome.runtime.sendMessage({status:"Page marked!"});
      }).catch(err => {
        chrome.runtime.sendMessage({status:"Error: "+err});
      });
      return;
    }

    if (command === "mark_element" || command === "mark_image") {
      const mode = command === "mark_element" ? "element" : "image";
      document.body.style.cursor = (mode === "element") ? "crosshair" : "zoom-in";
      let highlight = document.createElement("div");
      highlight.style.position = "fixed";
      highlight.style.border = "3px dashed #29df96";
      highlight.style.background = "rgba(41,223,150,0.10)";
      highlight.style.zIndex = "2147483647";
      highlight.style.pointerEvents = "none";
      document.body.appendChild(highlight);

      function moveHighlight(e) {
        let t = e.target;
        if(mode === "image" && t.tagName !== "IMG") { highlight.style.display="none"; return; }
        let r = t.getBoundingClientRect();
        highlight.style.display="block";
        highlight.style.left = r.left+"px";
        highlight.style.top = r.top+"px";
        highlight.style.width = r.width+"px";
        highlight.style.height = r.height+"px";
      }

      function handleClick(ev) {
        ev.preventDefault(); ev.stopPropagation();
        document.removeEventListener("mousemove", moveHighlight);
        document.removeEventListener("click", handleClick, true);
        document.body.style.cursor = "";
        highlight.remove();

        if(mode === "image" && ev.target.tagName !== "IMG") {
          chrome.runtime.sendMessage({status: "Not an image!"});
          return;
        }

        let selected_text = ev.target.innerText || ev.target.alt || "";
        let element_html = ev.target.outerHTML;
        let selector = ""; // (Enhance with selector logic if you want)
        fetch(`${settings.server_url}/mark_page`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": settings.api_key
          },
          body: JSON.stringify({
            mode,
            url: location.href,
            ts: Date.now()/1000,
            element_html,
            selected_text,
            selector,
            session_id
          })
        }).then(resp => {
          chrome.runtime.sendMessage({status:`${mode.charAt(0).toUpperCase()+mode.slice(1)} marked!`});
        }).catch(err => {
          chrome.runtime.sendMessage({status:"Error: "+err});
        });
      }

      document.addEventListener("mousemove", moveHighlight);
      document.addEventListener("click", handleClick, true);
    }
  });
}

// --------- Hotkey handler (Shift+P/E/I, all browsers/tabs where content script loaded)
document.addEventListener("keydown", function(e) {
  if(!e.shiftKey) return;
  // Prevent hotkeys from working in inputs/forms
  if(["INPUT","TEXTAREA"].includes(document.activeElement.tagName)) return;

  if(e.code === "KeyP") { requestMark("mark_page"); e.preventDefault(); }
  if(e.code === "KeyE") { requestMark("mark_element"); e.preventDefault(); }
  if(e.code === "KeyI") { requestMark("mark_image");  e.preventDefault(); }
});
