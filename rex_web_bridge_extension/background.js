/**
 * RexTools3 AI 3D Web Bridge - Background Service Worker
 * Manages tab switching, window focusing, and bridge status monitoring.
 */

const BRIDGE_PORT = 28394;
const BRIDGE_BASE_URL = `http://127.0.0.1:${BRIDGE_PORT}`;
const POLL_INTERVAL = 1000;

let lastProcessedTimestamp = 0;
let isPolling = false;

console.log("[RexTools3 Background] Service Worker started.");

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
    // Offline or unreachable, normal when Blender bridge is idle
  } finally {
    isPolling = false;
  }
}

// Poll bridge server periodically
setInterval(checkBridgeStatus, POLL_INTERVAL);
checkBridgeStatus();
