/**
 * RexTools3 AI 3D Web Bridge - Content Script
 * Injected into Meshy (meshy.ai) and Tripo (studio.tripo3d.ai)
 */

(function () {
  const BRIDGE_PORT = 28394;
  const BRIDGE_BASE_URL = `http://127.0.0.1:${BRIDGE_PORT}`;
  const POLL_INTERVAL = 1200;

  let lastProcessedTimestamp = 0;
  let isProcessing = false;
  let isConnected = false;

  function getCurrentPlatform() {
    const host = window.location.hostname.toLowerCase();
    if (host.includes("meshy.ai")) return "meshy";
    if (host.includes("tripo3d.ai")) return "tripo";
    return null;
  }

  const currentPlatform = getCurrentPlatform();
  console.log(`%c[RexTools3 Web Bridge]%c Active on platform: ${currentPlatform || "unknown"}`, "color: #00ff88; font-weight: bold;", "color: inherit;");

  // ─────────────────────────────────────────────────────────────────────────
  // UI Helpers (In-Page Toast & Status Badge)
  // ─────────────────────────────────────────────────────────────────────────

  function showToast(message, type = "info", duration = 4500) {
    const existing = document.getElementById("rextools-bridge-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "rextools-bridge-toast";
    toast.innerHTML = `
      <div style="display: flex; align-items: center; gap: 10px;">
        <span style="font-size: 18px;">${type === "success" ? "✨" : type === "error" ? "❌" : "🚀"}</span>
        <div>
          <div style="font-weight: 700; font-size: 13px; letter-spacing: 0.5px; text-transform: uppercase; color: ${type === "success" ? "#00ff88" : type === "error" ? "#ff4444" : "#44bbff"};">RexTools3 Bridge</div>
          <div style="font-size: 13px; color: #f0f0f0; margin-top: 2px;">${message}</div>
        </div>
      </div>
    `;

    Object.assign(toast.style, {
      position: "fixed",
      top: "24px",
      right: "24px",
      zIndex: "9999999",
      background: "rgba(18, 20, 26, 0.95)",
      backdropFilter: "blur(12px)",
      border: `1px solid ${type === "success" ? "rgba(0, 255, 136, 0.4)" : type === "error" ? "rgba(255, 68, 68, 0.4)" : "rgba(68, 187, 255, 0.4)"}`,
      borderRadius: "10px",
      padding: "14px 20px",
      boxShadow: "0 10px 30px rgba(0, 0, 0, 0.5)",
      fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      color: "#ffffff",
      maxWidth: "380px",
      transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
      opacity: "0",
      transform: "translateY(-15px)",
      pointerEvents: "none",
    });

    document.body.appendChild(toast);

    requestAnimationFrame(() => {
      toast.style.opacity = "1";
      toast.style.transform = "translateY(0)";
    });

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-15px)";
      setTimeout(() => toast.remove(), 350);
    }, duration);
  }

  function createStatusBadge() {
    if (document.getElementById("rextools-bridge-badge")) return;

    const platformLabel = currentPlatform === "meshy" ? "Meshy" : (currentPlatform === "tripo" ? "Tripo" : "Web");
    const badge = document.createElement("div");
    badge.id = "rextools-bridge-badge";
    badge.innerHTML = `
      <div id="rextools-badge-dot" style="width: 8px; height: 8px; border-radius: 50%; background: #666; transition: background 0.3s;"></div>
      <span id="rextools-badge-text" style="font-size: 11px; font-weight: 600; color: #a0a0a0;">RexTools (${platformLabel})</span>
    `;

    Object.assign(badge.style, {
      position: "fixed",
      bottom: "16px",
      right: "16px",
      zIndex: "999999",
      display: "flex",
      alignItems: "center",
      gap: "8px",
      background: "rgba(18, 20, 26, 0.85)",
      backdropFilter: "blur(8px)",
      border: "1px solid rgba(255, 255, 255, 0.1)",
      borderRadius: "20px",
      padding: "6px 12px",
      fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      userSelect: "none",
      cursor: "pointer",
      boxShadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
      transition: "all 0.2s ease",
    });

    badge.title = `RexTools3 AI Web Bridge (${platformLabel}) - Click to test Blender connection`;
    badge.addEventListener("click", () => {
      checkBridgeStatus(true);
    });

    document.body.appendChild(badge);
  }

  function updateBadgeStatus(connected, targetService = null) {
    isConnected = connected;
    const dot = document.getElementById("rextools-badge-dot");
    const text = document.getElementById("rextools-badge-text");
    if (!dot || !text) return;

    const platformLabel = currentPlatform === "meshy" ? "Meshy" : (currentPlatform === "tripo" ? "Tripo" : "Bridge");

    if (connected) {
      dot.style.background = "#00ff88";
      dot.style.boxShadow = "0 0 8px #00ff88";
      text.style.color = "#e0e0e0";
      text.textContent = `RexTools (${platformLabel})`;
    } else {
      dot.style.background = "#666666";
      dot.style.boxShadow = "none";
      text.style.color = "#888888";
      text.textContent = `RexTools Idle (${platformLabel})`;
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // React / DOM Helpers
  // ─────────────────────────────────────────────────────────────────────────

  function setReactInputValue(inputElement, value) {
    if (!inputElement) return;
    const prototype = Object.getPrototypeOf(inputElement);
    const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    const valueSetter = Object.getOwnPropertyDescriptor(inputElement, "value")?.set;

    if (prototypeValueSetter && valueSetter !== prototypeValueSetter) {
      prototypeValueSetter.call(inputElement, value);
    } else if (valueSetter) {
      valueSetter.call(inputElement, value);
    } else {
      inputElement.value = value;
    }

    inputElement.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
    inputElement.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitForElement(selectorFn, timeout = 7000, interval = 100) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const el = selectorFn();
      if (el) return el;
      await sleep(interval);
    }
    return null;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Meshy Platform Automation
  // ─────────────────────────────────────────────────────────────────────────

  function findMeshyUploadButton() {
    // 1. By data-testid or title/tooltip
    let btn = document.querySelector(
      'button[data-testid*="upload" i], button[aria-label*="Upload" i], [title*="Upload your own model" i], [title*="Upload" i], [data-tooltip*="Upload" i]'
    );
    if (btn) return btn;

    // 2. Buttons containing exact or matching text "Upload"
    const allButtons = Array.from(document.querySelectorAll("button, [role='button'], a"));
    for (const b of allButtons) {
      const txt = b.textContent.trim().toLowerCase();
      if (txt === "upload" || txt.includes("upload your own model")) {
        return b;
      }
    }

    // 3. Match by leaf element containing "Upload"
    const leafSpans = Array.from(document.querySelectorAll("span, p, div")).filter(
      (el) => el.children.length === 0 && el.textContent.trim().toLowerCase() === "upload"
    );
    for (const span of leafSpans) {
      const clickable = span.closest("button, [role='button'], div[tabindex]");
      if (clickable) return clickable;
    }

    return null;
  }

  function isMeshyUploadModalOpen() {
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [data-state="open"], [aria-modal="true"]'));
    for (const dialog of dialogs) {
      const modelInput = dialog.querySelector('input[type="file"][accept*=".glb"], input[type="file"][accept*=".fbx"]');
      if (modelInput) return true;
    }
    return false;
  }

  /**
   * Specifically locate the 3D model file input.
   * STRICT GUARD: Never target 2D image upload inputs on the sidebar or avatar modals!
   */
  function findModelFileInput() {
    // 1. Check open dialogs for an input with 3D model accept extensions
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [data-state="open"], [aria-modal="true"]'));
    for (const dialog of dialogs) {
      const inputs = Array.from(dialog.querySelectorAll('input[type="file"]'));
      for (const input of inputs) {
        const accept = (input.getAttribute("accept") || "").toLowerCase();
        if (
          (accept.includes(".glb") || accept.includes(".fbx") || accept.includes(".obj") || accept.includes(".stl") || accept.includes(".gltf")) &&
          !accept.includes("image")
        ) {
          return input;
        }
      }
    }

    // 2. Search anywhere on the page for an input with 3D model accept extensions
    const all3DInputs = Array.from(document.querySelectorAll('input[type="file"]')).filter((inp) => {
      const accept = (inp.getAttribute("accept") || "").toLowerCase();
      return (
        (accept.includes(".glb") || accept.includes(".fbx") || accept.includes(".obj") || accept.includes(".stl") || accept.includes(".gltf")) &&
        !accept.includes("image") && !accept.includes("png") && !accept.includes("jpg")
      );
    });
    if (all3DInputs.length > 0) {
      return all3DInputs[0];
    }

    // 3. Fallback inside open dialog: first input that strictly does NOT accept images
    for (const dialog of dialogs) {
      const inputs = Array.from(dialog.querySelectorAll('input[type="file"]'));
      for (const input of inputs) {
        const accept = (input.getAttribute("accept") || "").toLowerCase();
        if (accept && !accept.includes("image") && !accept.includes("png") && !accept.includes("jpg")) {
          return input;
        }
      }
    }

    return null;
  }

  function findModelDropzone(fileInput) {
    if (fileInput) {
      return fileInput.closest("div[class*='border-dashed'], div[class*='group'], div[role='presentation']") || fileInput.parentElement;
    }
    return null;
  }

  async function handleMeshyInjection(status) {
    showToast(`Incoming model <b>${status.model_name || "Model"}</b> from Blender...`, "info");

    // 1. If modal is not open, click the "Upload" button
    if (!isMeshyUploadModalOpen()) {
      const uploadBtn = findMeshyUploadButton();
      if (!uploadBtn) {
        showToast("Could not find 'Upload' button on Meshy page. Please click it manually.", "error");
        return false;
      }

      console.log("[RexTools3] Clicking Upload button on Meshy...");
      uploadBtn.click();
    }

    // 2. Wait for the 3D model file input inside the modal
    const fileInput = await waitForElement(() => findModelFileInput(), 7000);
    if (!fileInput) {
      showToast("3D Model upload input not found inside modal.", "error");
      return false;
    }
    console.log("[RexTools3] Target 3D Model input found:", fileInput, "accept:", fileInput.accept);

    // 3. Fetch model file bytes from local Blender HTTP server
    console.log("[RexTools3] Fetching model file from local bridge...");
    let fileBlob;
    try {
      const res = await fetch(`${BRIDGE_BASE_URL}/file`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      fileBlob = await res.blob();
    } catch (err) {
      showToast(`Failed to fetch model from Blender: ${err.message}`, "error");
      return false;
    }

    // Ensure filename ends with correct 3D extension (.glb)
    let filename = status.filename || "model.glb";
    if (!filename.toLowerCase().endsWith(".glb") && !filename.toLowerCase().endsWith(".fbx") && !filename.toLowerCase().endsWith(".obj")) {
      filename += ".glb";
    }

    const fileObj = new File([fileBlob], filename, {
      type: "model/gltf-binary",
      lastModified: Date.now(),
    });

    console.log(`[RexTools3] Prepared File object: name='${fileObj.name}', size=${fileObj.size} bytes`);

    // 4. Inject file into input using DataTransfer
    const dt = new DataTransfer();
    dt.items.add(fileObj);

    try {
      fileInput.files = dt.files;
    } catch (e) {
      console.warn("[RexTools3] Direct fileInput.files set warning:", e);
    }

    // 5. Trigger React's internal handler directly if available
    const findReactProps = (el) => {
      if (!el) return null;
      const key = Object.keys(el).find((k) => k.startsWith("__reactProps$") || k.startsWith("__reactEventHandlers$"));
      return key ? el[key] : null;
    };

    const inputProps = findReactProps(fileInput);
    const dropzone = findModelDropzone(fileInput);
    const dropzoneProps = findReactProps(dropzone);
    let reactTriggered = false;

    // Use Proxy on target to guarantee e.target.files returns the File object
    // even if browser sandbox restricts synthetic assignment on hidden inputs
    const fileListMock = dt.files.length > 0 ? dt.files : [fileObj];
    const targetProxy = new Proxy(fileInput, {
      get(obj, prop) {
        if (prop === "files") return fileListMock;
        const val = obj[prop];
        return typeof val === "function" ? val.bind(obj) : val;
      }
    });

    if (inputProps && typeof inputProps.onChange === "function") {
      try {
        console.log("[RexTools3] Directly calling inputProps.onChange with targetProxy");
        await inputProps.onChange({
          target: targetProxy,
          currentTarget: targetProxy,
          preventDefault: () => {},
          stopPropagation: () => {},
        });
        reactTriggered = true;
      } catch (err) {
        console.warn("[RexTools3] Direct onChange call error:", err);
      }
    }

    if (!reactTriggered && dropzoneProps && typeof dropzoneProps.onDrop === "function") {
      try {
        console.log("[RexTools3] Directly calling dropzoneProps.onDrop");
        await dropzoneProps.onDrop({
          preventDefault: () => {},
          stopPropagation: () => {},
          dataTransfer: {
            files: fileListMock,
            items: dt.items,
            types: ["Files"],
          },
        });
        reactTriggered = true;
      } catch (err) {
        console.warn("[RexTools3] Direct onDrop call error:", err);
      }
    }

    // Also dispatch standard DOM input & change events
    fileInput.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
    fileInput.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));

    // 6. Set Model Name input field (placeholder: "Give your model a name")
    await sleep(400);
    const nameInput = document.querySelector(
      'input[placeholder*="Give your model a name" i], input[placeholder*="model name" i], input[name*="name" i]'
    );
    if (nameInput && status.model_name) {
      setReactInputValue(nameInput, status.model_name);
    }

    // 7. Acknowledge success to Blender server
    try {
      await fetch(`${BRIDGE_BASE_URL}/ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          success: true,
          model_name: status.model_name,
          service: "meshy",
        }),
      });
    } catch (e) {
      console.warn("[RexTools3] Ack failed:", e);
    }

    showToast(`Model <b>${status.model_name}</b> injected! Review settings & click Continue.`, "success", 6000);
    return true;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Tripo Platform Automation
  // ─────────────────────────────────────────────────────────────────────────

  async function handleTripoInjection(status) {
    showToast(`Incoming model <b>${status.model_name}</b> from Blender...`, "info");

    const fileInput = await waitForElement(() => {
      const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
      return (
        inputs.find((inp) => {
          const accept = (inp.getAttribute("accept") || "").toLowerCase();
          return (
            (accept.includes(".glb") || accept.includes(".fbx") || accept.includes(".obj") || accept.includes(".stl")) &&
            !accept.includes("image")
          );
        }) ||
        inputs.find((inp) => {
          const accept = (inp.getAttribute("accept") || "").toLowerCase();
          return !accept.includes("image") && !accept.includes("png");
        }) ||
        inputs[0]
      );
    }, 4000);

    if (!fileInput) {
      showToast("Please open the Upload / Import modal on Tripo to receive the model.", "info");
      return false;
    }

    try {
      const res = await fetch(`${BRIDGE_BASE_URL}/file`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const fileBlob = await res.blob();
      const filename = status.filename || "model.glb";
      const fileObj = new File([fileBlob], filename, {
        type: "model/gltf-binary",
        lastModified: Date.now(),
      });

      const dt = new DataTransfer();
      dt.items.add(fileObj);
      fileInput.files = dt.files;

      const findReactProps = (el) => {
        if (!el) return null;
        const key = Object.keys(el).find((k) => k.startsWith("__reactProps$") || k.startsWith("__reactEventHandlers$"));
        return key ? el[key] : null;
      };

      const inputProps = findReactProps(fileInput);
      if (inputProps && typeof inputProps.onChange === "function") {
        await inputProps.onChange({
          target: fileInput,
          currentTarget: fileInput,
          preventDefault: () => {},
          stopPropagation: () => {},
        });
      }

      fileInput.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
      fileInput.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));

      await fetch(`${BRIDGE_BASE_URL}/ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          success: true,
          model_name: status.model_name,
          service: "tripo",
        }),
      });

      showToast(`Model <b>${status.model_name}</b> injected into Tripo Studio!`, "success", 5000);
      return true;
    } catch (err) {
      showToast(`Tripo injection failed: ${err.message}`, "error");
      return false;
    }
  }

  async function handleInjectionForCurrentPage(status) {
    const targetService = (status.service || "meshy").toLowerCase();
    const platform = getCurrentPlatform();

    // STRICT SERVICE MATCH: Only proceed if this page matches the intended target!
    if (platform !== targetService) {
      console.log(`[RexTools3] Skipping injection: export is for '${targetService}', but current page is '${platform}'.`);
      return false;
    }

    if (platform === "meshy") {
      return await handleMeshyInjection(status);
    } else if (platform === "tripo") {
      return await handleTripoInjection(status);
    }
    return false;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Listen for Messages from Background Service Worker
  // ─────────────────────────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message && message.type === "REXTOOLS_INJECT_MODEL" && message.status) {
      const targetService = (message.status.service || "meshy").toLowerCase();
      const platform = getCurrentPlatform();

      // Only handle if this message targets this specific platform
      if (platform !== targetService) {
        sendResponse({ received: false, ignored: true, reason: `Target '${targetService}' does not match page '${platform}'` });
        return;
      }

      if (message.status.timestamp > lastProcessedTimestamp && !message.status.ack_received) {
        lastProcessedTimestamp = message.status.timestamp;
        handleInjectionForCurrentPage(message.status);
      }
      sendResponse({ received: true });
    }
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Main Polling Loop (Fallback & Ping)
  // ─────────────────────────────────────────────────────────────────────────

  async function checkBridgeStatus(userInitiated = false) {
    if (isProcessing) return;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1000);
      const res = await fetch(`${BRIDGE_BASE_URL}/status`, { signal: controller.signal });
      clearTimeout(timeoutId);

      if (!res.ok) throw new Error("Status error");
      const status = await res.json();
      updateBadgeStatus(true, status.service);

      if (userInitiated) {
        showToast("Blender RexTools3 is connected and ready!", "success", 3000);
      }

      // Check if new model export is waiting
      if (
        status.active &&
        status.timestamp > lastProcessedTimestamp &&
        !status.ack_received
      ) {
        const targetService = (status.service || "meshy").toLowerCase();
        const platform = getCurrentPlatform();

        // STRICT TARGET FILTER:
        // If the export was sent to Meshy, Tripo must NEVER process it!
        // If the export was sent to Tripo, Meshy must NEVER touch it!
        if (platform !== targetService) {
          return;
        }

        isProcessing = true;
        lastProcessedTimestamp = status.timestamp;

        await handleInjectionForCurrentPage(status);

        isProcessing = false;
      }
    } catch (e) {
      updateBadgeStatus(false);
      if (userInitiated) {
        showToast("Blender RexTools3 is not reachable. Is Blender running?", "error", 4000);
      }
    }
  }

  // Initialize badge and start polling
  window.addEventListener("DOMContentLoaded", () => {
    createStatusBadge();
  });
  createStatusBadge();

  setInterval(checkBridgeStatus, POLL_INTERVAL);
  checkBridgeStatus();
})();
