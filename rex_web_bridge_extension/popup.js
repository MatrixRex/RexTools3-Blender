document.addEventListener("DOMContentLoaded", () => {
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const modelName = document.getElementById("model-name");
  const modelMeta = document.getElementById("model-meta");

  const openMeshyBtn = document.getElementById("open-meshy");
  const openTripoBtn = document.getElementById("open-tripo");

  openMeshyBtn.addEventListener("click", () => {
    chrome.tabs.create({ url: "https://www.meshy.ai/workspace" });
  });

  openTripoBtn.addEventListener("click", () => {
    chrome.tabs.create({ url: "https://studio.tripo3d.ai" });
  });

  async function checkStatus() {
    try {
      const res = await fetch("http://127.0.0.1:28394/status");
      if (!res.ok) throw new Error("Offline");
      const data = await res.json();

      statusDot.className = "dot online";
      statusText.textContent = "Online";

      if (data.model_name) {
        modelName.textContent = data.model_name;
        const sizeKb = (data.file_size / 1024).toFixed(1);
        const dateStr = data.timestamp ? new Date(data.timestamp * 1000).toLocaleTimeString() : "";
        modelMeta.textContent = `${data.format} • ${sizeKb} KB • ${dateStr} • Target: ${data.service}`;
      }
    } catch (e) {
      statusDot.className = "dot offline";
      statusText.textContent = "Offline";
    }
  }

  checkStatus();
});
