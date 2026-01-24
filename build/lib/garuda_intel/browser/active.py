import os
import logging
import uuid
from selenium.webdriver.chrome.options import Options
from selenium import webdriver

def get_env_chrome_args():
    # Supports comma-separated extra Chrome args from .env
    chrome_args = []
    chrome_args_env = os.environ.get("BROWSER_EXTRA_CHROME_ARGS", "")
    if chrome_args_env:
        chrome_args = [arg.strip() for arg in chrome_args_env.split(",") if arg.strip()]
    return chrome_args

def get_browser_start_url():
    # Allow user override of browser start page via env/CLI
    return os.environ.get("BROWSER_START_URL", None)

def get_session_id():
    return os.environ.get("SESSION_ID", str(uuid.uuid4())[:12])

class RecordingBrowser:
    def __init__(self, inject_server_url="http://localhost:8765/mark_page", start_url=None, extra_chrome_args=None, session_id=None):
        self.server_url = inject_server_url
        self.session_id = session_id or get_session_id()
        options = Options()
        options.add_argument("--window-size=1920,1080")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        # Add custom Chrome args
        if extra_chrome_args:
            for arg in extra_chrome_args:
                options.add_argument(arg)
        # Optionally always-on-top (platform dependent)
        if os.environ.get("BROWSER_ALWAYS_ON_TOP", "0") == "1":
            options.add_argument("--app=https://always-on-top/")
        # Init Chrome
        self.driver = webdriver.Chrome(options=options)
        self._setup_automatic_injection()
        open_url = start_url or get_browser_start_url() or "https://www.google.com"
        self.driver.get(open_url)

    def _get_js_payload(self):
        # This JS supports keyboard shortcuts, drag panel, status feedback, and session id
        return f"""
        (function() {{
            if (window._recorderInitialized) return;
            window._recorderInitialized = true;

            const session_id = "{self.session_id}";

            function initUI() {{
                if (!document.documentElement) {{
                    setTimeout(initUI, 50);
                    return;
                }}
                // Host & Shadow
                const host = document.createElement('div');
                host.id = '_recorder_host';
                host.style.cssText = 'position:fixed; top:32px; left:32px; width:0; height:0; z-index:2147483647;';
                document.documentElement.appendChild(host);
                const shadow = host.attachShadow({{mode: 'closed'}});

                // Drag support for panel
                let offsetX=0, offsetY=0, dragging = false;
                const startDrag = (e) => {{
                    dragging = true;
                    offsetX = e.clientX - host.getBoundingClientRect().left;
                    offsetY = e.clientY - host.getBoundingClientRect().top;
                    document.addEventListener('mousemove', onDrag);
                    document.addEventListener('mouseup', stopDrag);
                }};
                const onDrag = (e) => {{
                    if (!dragging) return;
                    host.style.left = (e.clientX - offsetX) + "px";
                    host.style.top = (e.clientY - offsetY) + "px";
                }};
                const stopDrag = () => {{
                    dragging = false;
                    document.removeEventListener('mousemove', onDrag);
                    document.removeEventListener('mouseup', stopDrag);
                }};

                // Styles & Panel
                const container = document.createElement('div');
                container.innerHTML = `
                    <style>
                        .panel {{
                            position: fixed; right: 0; bottom: 0; margin: 20px;
                            display: flex; flex-direction: column; gap: 10px;
                            font-family: system-ui, sans-serif;
                            background: #f4f4f4ef; border-radius:8px; box-shadow:0 6px 20px rgba(0,0,0,0.32);
                            padding: 16px 20px 12px 20px; cursor: move;
                            min-width: 180px;
                        }}
                        .panel-header {{
                            font-size: 13px; font-weight:bold; margin-bottom:7px; cursor:move;
                        }}
                        button {{
                            width: 170px; height: 45px; cursor: pointer;
                            border: 2px solid #000; border-radius: 8px;
                            font-weight: bold; transition: 0.2s;
                            box-shadow: 0 3px 13px rgba(0,0,0,0.20);
                        }}
                        #page-btn {{ background: #ffcc00; }}
                        #elem-btn {{ background: #29df96; }}
                        #img-btn {{ background: #5abfff; }}
                        button:active {{ transform: scale(0.97); }}
                        #highlighter {{
                            position: fixed; pointer-events: none;
                            border: 3px dashed #1be71b;
                            background: rgba(41,223,150,0.16);
                            display: none; z-index: 2147483646;
                        }}
                        .rec-status {{
                            display:block; margin-top:5px; font-size:11.3px;
                            color:#777;font-weight:normal; word-break:break-all;
                        }}
                    </style>
                    <div id="highlighter"></div>
                    <div class="panel" id="recorder-panel">
                        <div class="panel-header" id="panel-header" title="Drag me! (Shift+P/E/I for mark)">
                            🟡 Mark Recorder
                        </div>
                        <button id="page-btn" title="Mark full page (Shift+P)">MARK PAGE</button>
                        <button id="elem-btn" title="Mark a text/element (Shift+E)">ELEMENT SELECT</button>
                        <button id="img-btn" title="Mark an image (Shift+I)">IMAGE SELECT</button>
                        <span class="rec-status" id="recorder-status"></span>
                    </div>
                `;
                shadow.appendChild(container);

                // Drag support
                const panel = shadow.getElementById('recorder-panel');
                const header = shadow.getElementById('panel-header');
                header.addEventListener('mousedown', startDrag);

                // Buttons & indicators
                const highlight = shadow.querySelector('#highlighter');
                const pBtn = shadow.querySelector('#page-btn');
                const eBtn = shadow.querySelector('#elem-btn');
                const iBtn = shadow.querySelector('#img-btn');
                const status = shadow.querySelector('#recorder-status');
                function showStatus(msg, good) {{
                    status.textContent = msg;
                    status.style.color = good ? "#222" : "#c00";
                    status.style.fontWeight = good ? "bold" : "";
                }}

                // POST wrapper for all marks; adds session_id
                async function sendMark(payload, button) {{
                    button.innerText = "MARKING...";
                    try {{
                        payload.session_id = session_id;
                        let resp = await fetch('{self.server_url}', {{
                            method: 'POST', mode: 'cors', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(payload)
                        }});
                        const ok = resp && resp.ok;
                        if(ok) {{
                            button.innerText = "RECORDED!";
                            showStatus(`Saved [${{payload.mode}}]!`, true);
                            setTimeout(()=>{{button.innerText = button.dataset.orig}}, 1800);
                        }} else {{
                            button.innerText = "!ERROR!";
                            showStatus("Failed to save: "+resp.status+" ["+payload.mode+"]", false);
                        }}
                    }} catch (e) {{
                        button.innerText = "!FAIL!";
                        showStatus("Mark error: "+e+" ["+payload.mode+"]", false);
                    }}
                }}
                pBtn.dataset.orig = pBtn.innerText;
                eBtn.dataset.orig = eBtn.innerText;
                iBtn.dataset.orig = iBtn.innerText;

                // Mark full page
                pBtn.onclick = ()=>{{
                    sendMark({{
                        mode:'page', url:location.href, html:document.documentElement.outerHTML, ts:Date.now()/1000
                    }}, pBtn);
                }};
                // Mark a selected element (with highlight and selector)
                eBtn.onclick = () => {{
                    if(window._isSelecting) return;
                    window._isSelecting = true;
                    eBtn.innerText = "CLICK TARGET...";
                    eBtn.style.background = "#ff5555";
                    document.body.style.cursor = "crosshair";
                    const mm = (e) => {{
                        let t = e.target;
                        if(!t || t === host || t === panel) {{highlight.style.display="none";return;}}
                        let r = t.getBoundingClientRect();
                        highlight.style.display="block";
                        highlight.style.left = r.left+"px";
                        highlight.style.top = r.top+"px";
                        highlight.style.width = r.width+"px";
                        highlight.style.height = r.height+"px";
                    }};
                    const click = (ev) => {{
                        ev.preventDefault(); ev.stopPropagation();
                        document.removeEventListener('mousemove', mm);
                        document.removeEventListener('click', click, true);
                        document.body.style.cursor = "";
                        highlight.style.display = "none";
                        window._isSelecting = false;
                        const sel = getDomSelector(ev.target);
                        sendMark({{
                            mode:'element', url:location.href,
                            selected_text:ev.target.innerText||ev.target.alt||"",
                            element_html:ev.target.outerHTML, selector:sel, ts:Date.now()/1000
                        }}, eBtn);
                        eBtn.style.background = "#29df96";
                        setTimeout(()=>eBtn.innerText=eBtn.dataset.orig,1800);
                    }};
                    document.addEventListener('mousemove', mm);
                    document.addEventListener('click', click, true);
                }};
                // Mark an image (prefer img, or prompt warning)
                iBtn.onclick = () => {{
                    if(window._isSelectingImage) return;
                    window._isSelectingImage = true;
                    iBtn.innerText = "CLICK IMAGE...";
                    iBtn.style.background = "#ff9222";
                    document.body.style.cursor = "zoom-in";
                    const mm = (e) => {{
                        let t = e.target;
                        if(!t || t.tagName!=="IMG") {{highlight.style.display="none";return;}}
                        let r = t.getBoundingClientRect();
                        highlight.style.display="block";
                        highlight.style.left = r.left+"px";
                        highlight.style.top = r.top+"px";
                        highlight.style.width = r.width+"px";
                        highlight.style.height = r.height+"px";
                    }};
                    const click = (ev) => {{
                        ev.preventDefault(); ev.stopPropagation();
                        document.removeEventListener('mousemove', mm);
                        document.removeEventListener('click', click, true);
                        document.body.style.cursor = "";
                        highlight.style.display = "none";
                        window._isSelectingImage = false;
                        if(ev.target.tagName!=="IMG") {{
                            showStatus("Not an image!", false);
                            iBtn.style.background = "#5abfff";
                            iBtn.innerText = iBtn.dataset.orig;
                            return;
                        }}
                        const sel = getDomSelector(ev.target);
                        sendMark({{
                            mode:'image', url:location.href, selected_text:ev.target.alt||"", element_html:ev.target.outerHTML, selector:sel, ts:Date.now()/1000
                        }}, iBtn);
                        iBtn.style.background = "#5abfff";
                        setTimeout(()=>iBtn.innerText = iBtn.dataset.orig, 1800);
                    }};
                    document.addEventListener('mousemove', mm);
                    document.addEventListener('click', click, true);
                }};
                // Status: session id
                status.textContent = "[session: "+session_id+"]";

                // Keyboard shortcuts
                document.addEventListener("keydown", (e) => {{
                    if(e.shiftKey && e.code==="KeyP") pBtn.click();
                    if(e.shiftKey && e.code==="KeyE") eBtn.click();
                    if(e.shiftKey && e.code==="KeyI") iBtn.click();
                }});

                // Helper: accurate selector for marked element
                function getDomSelector(el) {{
                  if (!el || !el.tagName) return "";
                  let path = [];
                  while (el && el.nodeType === 1 && el.tagName.toLowerCase() !== "html") {{
                    let sibIdx = 1, sib = el;
                    while((sib = sib.previousElementSibling)) if(sib.tagName === el.tagName) ++sibIdx;
                    const id = el.id && /^[a-z_\\-][\\w\\-]+$/i.test(el.id) ? "#" + el.id : "";
                    path.unshift(el.tagName.toLowerCase() + (id ? id : sibIdx > 1 ? ":nth-of-type("+sibIdx+")" : ""));
                    if(id) break;
                    el = el.parentElement;
                  }}
                  return path.join(">");
                }}
            }}
            initUI();
        }})();
        """

    def _setup_automatic_injection(self):
        # Automatic JS injection on every new page; ensures panel is present
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": self._get_js_payload()
        })

    def is_alive(self):
        try:
            return len(self.driver.window_handles) > 0
        except Exception:
            return False

    def close(self):
        if getattr(self, "driver", None):
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, val, tb):
        self.close()
