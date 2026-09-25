import bpy
import os
import sys
import tempfile
import json
import time
import threading
import webbrowser
import subprocess
from pathlib import Path
from mathutils import Vector
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from ..core import notify

# ─────────────────────────────────────────────────────────────────────────────
# Global Bridge State & Server Management
# ─────────────────────────────────────────────────────────────────────────────

BRIDGE_STATE = {
    "active": False,
    "service": "meshy",
    "filename": "",
    "model_name": "",
    "filepath": "",
    "timestamp": 0.0,
    "format": "GLB",
    "file_size": 0,
    "ack_received": False,
    "port": 28394,
    "last_client_poll_time": 0.0,
}

_HTTP_SERVER = None
_SERVER_THREAD = None
_SERVER_LOCK = threading.Lock()


class BridgeHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    Lightweight HTTP request handler for communicating with the
    RexTools3 Web Bridge Chrome Extension.
    """

    def log_message(self, format, *args):
        # Suppress routine request logging to prevent console clutter
        pass

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range, Authorization")

    def do_OPTIONS(self):
        """Handle CORS preflight requests from browser extension / web page."""
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        BRIDGE_STATE["last_client_poll_time"] = time.time()

        if path in ("/status", "/bridge/status"):
            self._handle_status()
        elif path in ("/file", "/bridge/file"):
            self._handle_file()
        elif path in ("/health", "/bridge/health"):
            self._handle_health()
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        BRIDGE_STATE["last_client_poll_time"] = time.time()

        if path in ("/ack", "/bridge/ack"):
            self._handle_ack()
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def _handle_health(self):
        data = json.dumps({"ok": True, "bridge": "RexTools3"}).encode("utf-8")
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_status(self):
        resp_data = {
            "active": BRIDGE_STATE["active"],
            "service": BRIDGE_STATE["service"],
            "filename": BRIDGE_STATE["filename"],
            "model_name": BRIDGE_STATE["model_name"],
            "timestamp": BRIDGE_STATE["timestamp"],
            "format": BRIDGE_STATE["format"],
            "file_size": BRIDGE_STATE["file_size"],
            "ack_received": BRIDGE_STATE["ack_received"],
            "port": BRIDGE_STATE["port"],
        }
        body = json.dumps(resp_data).encode("utf-8")
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_file(self):
        filepath = BRIDGE_STATE.get("filepath", "")
        if not filepath or not os.path.exists(filepath):
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()
            return

        fmt = BRIDGE_STATE.get("format", "GLB").upper()
        content_type = "application/octet-stream"
        if fmt == "OBJ":
            content_type = "text/plain"

        try:
            file_size = os.path.getsize(filepath)
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{os.path.basename(filepath)}"'
            )
            self.end_headers()

            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
        except Exception as e:
            print(f"[RexTools3 Bridge] Error streaming file: {e}")

    def _handle_ack(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            data = json.loads(post_body.decode("utf-8"))
        except Exception:
            data = {}

        BRIDGE_STATE["ack_received"] = True
        model_name = data.get("model_name") or BRIDGE_STATE.get("model_name", "Model")
        service = data.get("service") or BRIDGE_STATE.get("service", "meshy")
        service_label = "Meshy" if service == "meshy" else "Tripo"

        def _notify_ack():
            notify.success(f"Injected '{model_name}' into {service_label} upload modal!")
            return None

        # Queue notification onto Blender's main thread
        bpy.app.timers.register(_notify_ack)

        resp = json.dumps({"status": "acknowledged"}).encode("utf-8")
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


def ensure_bridge_server(port=28394):
    """Start the background daemon HTTP server if not already running on the port."""
    global _HTTP_SERVER, _SERVER_THREAD
    with _SERVER_LOCK:
        if _HTTP_SERVER is not None:
            return True

        try:
            _HTTP_SERVER = HTTPServer(("127.0.0.1", port), BridgeHTTPRequestHandler)
            BRIDGE_STATE["port"] = port
            _SERVER_THREAD = threading.Thread(target=_HTTP_SERVER.serve_forever, daemon=True)
            _SERVER_THREAD.start()
            return True
        except Exception as e:
            print(f"[RexTools3 Bridge] Could not start bridge server on 127.0.0.1:{port}: {e}")
            return False


def stop_bridge_server():
    """Cleanly shut down the background bridge server."""
    global _HTTP_SERVER, _SERVER_THREAD
    with _SERVER_LOCK:
        if _HTTP_SERVER is not None:
            try:
                _HTTP_SERVER.shutdown()
                _HTTP_SERVER.server_close()
            except Exception:
                pass
            _HTTP_SERVER = None
            _SERVER_THREAD = None


# ─────────────────────────────────────────────────────────────────────────────
# Windows Clipboard Helper
# ─────────────────────────────────────────────────────────────────────────────

def copy_file_to_windows_clipboard(filepath):
    """Copies the file to the Windows Clipboard as CF_HDROP (native file drop)."""
    if sys.platform != 'win32' or not os.path.exists(filepath):
        return
    try:
        import ctypes
        from ctypes import wintypes

        CF_HDROP = 15
        GMEM_MOVEABLE = 0x0002
        GMEM_ZEROINIT = 0x0040
        GHND = GMEM_MOVEABLE | GMEM_ZEROINIT

        class DROPFILES(ctypes.Structure):
            _fields_ = [
                ("pFiles", wintypes.DWORD),
                ("pt", wintypes.POINT),
                ("fNC", wintypes.BOOL),
                ("fWide", wintypes.BOOL),
            ]

        norm_path = os.path.normpath(filepath)
        # Double null-terminated utf-16 wide string
        buffer = norm_path.encode('utf-16le') + b'\x00\x00\x00\x00'
        df = DROPFILES()
        df.pFiles = ctypes.sizeof(DROPFILES)
        df.pt = wintypes.POINT(0, 0)
        df.fNC = False
        df.fWide = True

        total_size = ctypes.sizeof(DROPFILES) + len(buffer)
        hGlobal = ctypes.windll.kernel32.GlobalAlloc(GHND, total_size)
        if not hGlobal:
            return

        pMem = ctypes.windll.kernel32.GlobalLock(hGlobal)
        ctypes.memmove(pMem, ctypes.byref(df), ctypes.sizeof(DROPFILES))
        ctypes.memmove(pMem + ctypes.sizeof(DROPFILES), buffer, len(buffer))
        ctypes.windll.kernel32.GlobalUnlock(hGlobal)

        if ctypes.windll.user32.OpenClipboard(None):
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.SetClipboardData(CF_HDROP, hGlobal)
            ctypes.windll.user32.CloseClipboard()
    except Exception as e:
        print(f"[RexTools3] Error copying file drop to clipboard: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Operators
# ─────────────────────────────────────────────────────────────────────────────

class REXTOOLS3_OT_ai_web_bridge_export(bpy.types.Operator):
    """Export selected mesh for AI 3D Generators and trigger browser upload bridge"""
    bl_idname = "rextools3.ai_web_bridge_export"
    bl_label = "Send to AI Generator"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if context.mode != 'OBJECT':
            return False
        # Require at least one mesh object selected or active mesh
        mesh_objs = [o for o in context.selected_objects if o.type == 'MESH']
        if not mesh_objs and context.active_object and context.active_object.type == 'MESH':
            return True
        return bool(mesh_objs)

    def execute(self, context):
        props = getattr(context.scene, "rex_ai_web_bridge_props", None)
        if not props:
            self.report({'ERROR'}, "AI Web Bridge properties not found.")
            return {'CANCELLED'}

        # Gather target mesh objects
        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not selected_meshes:
            if context.active_object and context.active_object.type == 'MESH':
                selected_meshes = [context.active_object]
            else:
                notify.error("Please select a mesh object to bridge.")
                return {'CANCELLED'}

        active_obj = context.active_object if context.active_object in selected_meshes else selected_meshes[0]
        raw_name = active_obj.name.strip()
        safe_name = bpy.path.clean_name(raw_name) or "Model"

        # Prepare export directory
        export_dir = os.path.join(tempfile.gettempdir(), "RexTools3_AI_WebBridge")
        os.makedirs(export_dir, exist_ok=True)

        fmt = props.file_format
        ext = ".glb" if fmt == "GLB" else (".fbx" if fmt == "FBX" else ".obj")
        filepath = os.path.normpath(os.path.join(export_dir, f"{safe_name}{ext}"))

        # Non-destructive preparation using duplicated temporary objects
        orig_selected = list(context.selected_objects)
        orig_active = context.active_object

        temp_objs = []
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for orig in selected_meshes:
                dup = orig.copy()
                dup.data = orig.data.copy()
                context.collection.objects.link(dup)
                dup.select_set(True)
                temp_objs.append(dup)

            context.view_layer.objects.active = temp_objs[0]

            # Join multiple meshes if more than 1 selected
            if len(temp_objs) > 1:
                bpy.ops.object.join()
                temp_objs = [context.active_object]

            main_obj = temp_objs[0]

            # 1. Apply Transforms if enabled
            if props.apply_transforms:
                bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

            # 2. Auto Center to World Origin if enabled
            if props.auto_center:
                # Calculate bounding box center in world space
                bbox_corners = [main_obj.matrix_world @ Vector(corner) for corner in main_obj.bound_box]
                bbox_center = sum(bbox_corners, Vector()) / len(bbox_corners)
                main_obj.location -= bbox_center
                bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

            # 3. Export according to format
            if fmt == "GLB":
                # GLTF Binary: embeds textures, materials, and UVs cleanly
                bpy.ops.export_scene.gltf(
                    filepath=filepath,
                    export_format='GLB',
                    use_selection=True,
                    export_apply=True,
                    export_yup=True,
                    export_materials='EXPORT',
                    export_image_format='AUTO',
                    export_cameras=False,
                    export_lights=False
                )
            elif fmt == "FBX":
                bpy.ops.export_scene.fbx(
                    filepath=filepath,
                    use_selection=True,
                    apply_scale_options='FBX_SCALE_ALL',
                    bake_space_transform=True,
                    object_types={'MESH'}
                )
            elif fmt == "OBJ":
                if hasattr(bpy.ops.wm, "obj_export"):
                    bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=True)
                else:
                    bpy.ops.export_scene.obj(filepath=filepath, use_selection=True)

        except Exception as e:
            notify.error(f"Export failed: {e}")
            return {'CANCELLED'}
        finally:
            # Clean up temporary duplicated objects
            bpy.ops.object.select_all(action='DESELECT')
            for t_obj in temp_objs:
                try:
                    m = t_obj.data
                    context.collection.objects.unlink(t_obj)
                    bpy.data.objects.remove(t_obj, do_unlink=True)
                    if m:
                        bpy.data.meshes.remove(m, do_unlink=True)
                except Exception:
                    pass

            # Restore original selection and active object
            for o in orig_selected:
                try:
                    o.select_set(True)
                except Exception:
                    pass
            if orig_active:
                context.view_layer.objects.active = orig_active

        if not os.path.exists(filepath):
            notify.error("Exported file was not found on disk.")
            return {'CANCELLED'}

        # Update scene property record
        props.last_exported_file = filepath
        props.last_model_name = raw_name

        # Update global bridge state
        BRIDGE_STATE["active"] = True
        BRIDGE_STATE["service"] = props.target_service
        BRIDGE_STATE["filename"] = os.path.basename(filepath)
        BRIDGE_STATE["model_name"] = raw_name
        BRIDGE_STATE["filepath"] = filepath
        BRIDGE_STATE["timestamp"] = time.time()
        BRIDGE_STATE["format"] = props.file_format
        BRIDGE_STATE["file_size"] = os.path.getsize(filepath)
        BRIDGE_STATE["ack_received"] = False

        # Ensure background HTTP bridge server is running
        server_ok = ensure_bridge_server(props.server_port)
        if not server_ok:
            notify.warning(f"Could not bind port {props.server_port}. File saved to disk.")

        # Put file path on text clipboard and native CF_HDROP file drop clipboard
        context.window_manager.clipboard = filepath
        copy_file_to_windows_clipboard(filepath)

        service_label = "Meshy" if props.target_service == "meshy" else "Tripo"
        target_url = "https://www.meshy.ai/workspace" if props.target_service == "meshy" else "https://studio.tripo3d.ai"

        # Check if the companion browser extension is actively connected
        last_poll = BRIDGE_STATE.get("last_client_poll_time", 0.0)
        extension_active = (time.time() - last_poll) < 3.5

        if not extension_active:
            # Extension not currently connected: open browser window as fallback
            if props.auto_open_browser:
                webbrowser.open(target_url)
        else:
            # Extension is active: its background service worker will automatically
            # locate and focus the existing tab/window without opening duplicate tabs.
            pass

        notify.info(f"Model exported! Bridge sending '{raw_name}' to {service_label}...")
        return {'FINISHED'}


class REXTOOLS3_OT_ai_web_bridge_open_extension_folder(bpy.types.Operator):
    """Open the companion Chrome Extension folder in Windows Explorer to load in chrome://extensions"""
    bl_idname = "rextools3.ai_web_bridge_open_extension_folder"
    bl_label = "Open Chrome Extension Folder"

    def execute(self, context):
        addon_root = Path(__file__).resolve().parent.parent
        ext_folder = addon_root / "rex_web_bridge_extension"

        if not ext_folder.exists():
            ext_folder.mkdir(parents=True, exist_ok=True)

        if sys.platform == 'win32':
            os.startfile(str(ext_folder))
        else:
            subprocess.Popen(["xdg-open", str(ext_folder)])

        notify.info("Extension folder opened. In chrome://extensions, enable Dev Mode & click 'Load unpacked'.")
        return {'FINISHED'}


class REXTOOLS3_OT_ai_web_bridge_open_cache_folder(bpy.types.Operator):
    """Open the temporary exported models cache folder in Windows Explorer"""
    bl_idname = "rextools3.ai_web_bridge_open_cache_folder"
    bl_label = "Open Bridge Export Folder"

    def execute(self, context):
        export_dir = os.path.join(tempfile.gettempdir(), "RexTools3_AI_WebBridge")
        os.makedirs(export_dir, exist_ok=True)

        props = getattr(context.scene, "rex_ai_web_bridge_props", None)
        target_file = props.last_exported_file if props and props.last_exported_file else ""

        if sys.platform == 'win32':
            if target_file and os.path.exists(target_file):
                subprocess.Popen(f'explorer /select,"{os.path.normpath(target_file)}"')
            else:
                os.startfile(export_dir)
        else:
            subprocess.Popen(["xdg-open", export_dir])

        return {'FINISHED'}


class REXTOOLS3_OT_ai_web_bridge_copy_file(bpy.types.Operator):
    """Copy the last exported model file to clipboard for manual paste / drag-and-drop"""
    bl_idname = "rextools3.ai_web_bridge_copy_file"
    bl_label = "Copy Model to Clipboard"

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "rex_ai_web_bridge_props", None)
        return bool(props and props.last_exported_file and os.path.exists(props.last_exported_file))

    def execute(self, context):
        props = context.scene.rex_ai_web_bridge_props
        filepath = props.last_exported_file
        context.window_manager.clipboard = filepath
        copy_file_to_windows_clipboard(filepath)
        notify.success("Model file copied to clipboard! You can paste or drag it directly.")
        return {'FINISHED'}


def register():
    # Attempt to start the bridge server in background when addon loads
    ensure_bridge_server()


def unregister():
    stop_bridge_server()
