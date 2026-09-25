/**
 * RexTools3 AI 3D Web Bridge - Background Service Worker
 * Manages tab switching, window focusing, bridge status monitoring,
 * and live extension icon status dot (Green = Connected, Red = Disconnected).
 */

const BRIDGE_PORT = 28394;
const BRIDGE_BASE_URL = `http://127.0.0.1:${BRIDGE_PORT}`;
const POLL_INTERVAL = 1000;

let lastProcessedTimestamp = 0;
let isPolling = false;
let currentConnectedState = null;

console.log("[RexTools3 Background] Service Worker started.");

/**
 * Updates the extension icon status dot in the Chrome toolbar.
 * Shows a green dot on successful bridge connection, or red if disconnected.
 */
function updateExtensionStatusIcon(connected) {
  if (currentConnectedState === connected) return;
  currentConnectedState = connected;

  const color = connected ? "#00E676" : "#FF3B30";
  chrome.action.setBadgeBackgroundColor({ color: color });
  chrome.action.setBadgeText({ text: "●" });
  if (chrome.action.setBadgeTextColor) {
    try {
      chrome.action.setBadgeTextColor({ color: "#FFFFFF" });
    } catch (e) {}
  }
  chrome.action.setTitle({
    title: connected
      ? "RexTools3 AI Web Bridge: Connected (Blender active)"
      : "RexTools3 AI Web Bridge: Disconnected (Blender offline)"
  });
}

// Initial state until first poll completes
updateExtensionStatusIcon(false);

async function checkBridgeStatus() {
  if (isPolling) return;
  isPolling = true;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 800);
    const res = await fetch(`${BRIDGE_BASE_URL}/status`, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!res.ok) throw new Error("Offline");
    const status = await res.json();

    // Successful ping: show green dot on extension icon
    updateExtensionStatusIcon(true);

    if (
      status.active &&
      status.timestamp > lastProcessedTimestamp &&
      !status.ack_received
    ) {
      lastProcessedTimestamp = status.timestamp;
      const targetService = (status.service || "meshy").toLowerCase();
      console.log(`[RexTools3 Background] New export detected: '${status.model_name}' for target '${targetService}'`);

      const urlPattern = targetService === "meshy" ? "*://*.meshy.ai/*" : "*://*.tripo3d.ai/*";
      const fallbackUrl = targetService === "meshy" ? "https://www.meshy.ai/workspace" : "https://studio.tripo3d.ai";

      // 1. Query existing tabs strictly matching the TARGET SERVICE
      const tabs = await chrome.tabs.query({ url: urlPattern });

      if (tabs.length > 0) {
        // Target tab found! Focus existing window and tab instead of opening a new one
        const targetTab = tabs[0];
        console.log(`[RexTools3 Background] Found existing ${targetService} tab ${targetTab.id}. Bringing to front...`);

        try {
          await chrome.windows.update(targetTab.windowId, { focused: true });
        } catch (e) {
          console.warn("[RexTools3 Background] Could not focus window:", e);
        }

        try {
          await chrome.tabs.update(targetTab.id, { active: true });
        } catch (e) {
          console.warn("[RexTools3 Background] Could not activate tab:", e);
        }

        // Notify only the target tab's content script to trigger injection
        setTimeout(() => {
          chrome.tabs.sendMessage(targetTab.id, {
            type: "REXTOOLS_INJECT_MODEL",
            status: status,
          }).catch(() => {
            // Content script polling will also pick it up safely
          });
        }, 350);

      } else {
        // No existing tab found for this service - open a single new tab
        console.log(`[RexTools3 Background] No existing ${targetService} tab found. Opening: ${fallbackUrl}`);
        await chrome.tabs.create({ url: fallbackUrl, active: true });
      }
    }
  } catch (e) {
    // Offline or unreachable: show red dot on extension icon
    updateExtensionStatusIcon(false);
  } finally {
    isPolling = false;
  }
}

// Poll bridge server periodically
setInterval(checkBridgeStatus, POLL_INTERVAL);
checkBridgeStatus();
