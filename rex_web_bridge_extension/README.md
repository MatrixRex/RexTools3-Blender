# RexTools3 AI 3D Web Bridge (Chrome Extension)

Seamlessly bridges 3D models exported from Blender's **RexTools3** add-on directly into AI 3D web generators like **Meshy** (`meshy.ai/workspace`) and **Tripo 3D** (`studio.tripo3d.ai`).

---

## 🚀 Quick Setup (15 Seconds)

1. Open **Google Chrome**, **Microsoft Edge**, or **Brave**.
2. Navigate to:
   ```
   chrome://extensions
   ```
3. Enable **Developer mode** toggle in the top-right corner.
4. Click **Load unpacked** (top-left).
5. Select this folder:
   ```
   e:\Nazmul\RexToolsBlender\rex_web_bridge_extension
   ```
   *(Or click "Open Extension Folder" directly inside the RexTools3 Blender panel!)*

---

## ⚡ How to Use

1. In Blender, select the mesh object(s) you want to generate textures/remesh/etc. for.
2. In the 3D Viewport sidebar (`N` panel) under **RexTools3** &rarr; **AI 3D Web Bridge**:
   - Choose your target generator (**Meshy** or **Tripo 3D**).
   - Format: **GLB** (recommended by Meshy) or FBX.
   - Leave **Center at World Origin** checked (Meshy requires centered models).
   - Click **Send Selected to Meshy**.
3. Blender will:
   - Export your model cleanly to `.glb`.
   - Start the local bridge daemon (`127.0.0.1:28394`).
   - Automatically open `https://www.meshy.ai/workspace`.
4. On the Meshy page, the extension will:
   - Detect the incoming model.
   - Automatically click the green **Upload** button.
   - Inject the model file directly into the **Upload your own model** modal.
   - Fill in the **Model Name** from your Blender object.
   - Keep the modal open so you can review texture/UV settings, select your CC license, and click **Continue** when ready!
   - Report success back to Blender to show a green success notification!
