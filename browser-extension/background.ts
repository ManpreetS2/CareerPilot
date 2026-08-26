// Service worker: makes the toolbar icon open the side panel (replacing the
// old popup behavior) and keeps the panel following the active tab. This is
// the piece that needs the "tabs" permission — a background context has no
// user gesture of its own to unlock "activeTab", so without "tabs" the Tab
// objects delivered here would have their url/title withheld.
chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

function notifyPanel(url: string | undefined) {
  if (!url) return;
  // No listener (panel not open) is the common case, not an error — Chrome
  // surfaces that as a rejected promise/lastError, both deliberately
  // swallowed here rather than logged, since it happens on every tab
  // switch while the panel is closed.
  chrome.runtime.sendMessage({ type: "TAB_CHANGED", url }).catch(() => {});
}

chrome.tabs.onActivated.addListener(({ tabId }) => {
  chrome.tabs.get(tabId, (tab) => {
    if (chrome.runtime.lastError) return;
    notifyPanel(tab?.url);
  });
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (!changeInfo.url) return; // only fires once per actual URL change
  if (!tab.active) return; // ignore background-tab navigation
  notifyPanel(changeInfo.url);
});
