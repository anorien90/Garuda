chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if(msg.action === "get_config") {
    chrome.storage.local.get(['server_url','api_key'], items => {
      sendResponse({
        server_url: items.server_url || "http://127.0.0.1:8765",
        api_key: items.api_key || ""
      });
    });
    // CRUCIAL: return true here for async sendResponse!
    return true;
  }
});
