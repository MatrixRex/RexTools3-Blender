import os
import time
import shutil
import tempfile
import threading
from mathutils import Vector
import bpy
from bpy.types import Operator

from ..core import notify
from ..core import meshy_client


# Thread-safe global state for background task tracking
TASK_STATE = {
    "thread": None,
    "cancelled": False,
    "finished": False,
    "error": None,
    "task_id": "",
    "task_type": "",
    "progress": 0,
    "status_message": "Idle",
    "result_filepath": "",
    "temp_files": [],
    "target_obj_name": "",
    "pipeline_stage": 1,
}

_TIMER_REGISTERED = False

MAX_CONCURRENT_TASKS = 2

# Thread-safe global task queue
TASK_QUEUE = []


def _clean_task_temp_files(task):
    """Remove any temporary files tracked for a specific task."""
    for fpath in task.get("temp_files", []):
        if os.path.isfile(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    task["temp_files"].clear()


def _dispatch_task_queue():
    """Start worker threads for QUEUED tasks up to MAX_CONCURRENT_TASKS."""
    running_count = len([t for t in TASK_QUEUE if t.get("status") == "RUNNING"])
    for task in TASK_QUEUE:
        if running_count >= MAX_CONCURRENT_TASKS:
            break
        if task.get("status") == "QUEUED":
            task["status"] = "RUNNING"
            task["status_message"] = "Starting..."
            running_count += 1
            t = threading.Thread(
                target=task["worker_target"],
                args=(task, *task["worker_args"]),
                daemon=True
            )
            task["thread"] = t
            t.start()


def _queue_task(title: str, task_type: str, worker_target, worker_args, target_obj_name="", replace_selected=True, temp_files=None):
    """Enqueue a new task and dispatch worker threads if slots are available."""
    global _TIMER_REGISTERED
    task_id = f"task_{int(time.time() * 1000)}_{len(TASK_QUEUE)}"
    task = {
        "id": task_id,
        "title": title,
        "task_type": task_type,
        "status": "QUEUED",
        "progress": 0,
        "status_message": "Queued...",
        "meshy_task_id": "",
        "target_obj_name": target_obj_name,
        "replace_selected": replace_selected,
        "result_filepath": "",
        "temp_files": list(temp_files or []),
        "error": None,
        "worker_target": worker_target,
        "worker_args": worker_args,
        "thread": None,
        "created_at": time.time(),
        "imported": False,
        "reported": False,
        "cleaned": False,
    }
    TASK_QUEUE.append(task)
    _dispatch_task_queue()
    _set_statusbar_active(True)

    props = getattr(bpy.context.scene, "rex_meshy_props", None)
    _sync_task_queue_items(props)

    if not _TIMER_REGISTERED:
        _TIMER_REGISTERED = True
        bpy.app.timers.register(_meshy_task_timer, first_interval=0.5)

    return task


def _cancel_task_by_id(task_id: str):
    """Cancel a specific task in the queue."""
    for task in TASK_QUEUE:
        if task.get("id") == task_id or task.get("meshy_task_id") == task_id:
            task["status"] = "CANCELLED"
            task["status_message"] = "Cancelled"
            _clean_task_temp_files(task)
            break
    props = getattr(bpy.context.scene, "rex_meshy_props", None)
    _sync_task_queue_items(props)
    _redraw_all_areas()


def _set_statusbar_active(active: bool):
    """Install or remove the progress bar in the center notification slot of all workspaces."""
    try:
        cb = _draw_meshy_status_middle if active else None
        for ws in bpy.data.workspaces:
            ws.status_text_set(cb)
    except Exception:
        pass


def _get_api_key(context) -> str:
    """Helper to retrieve the configured Meshy API key from preferences, persistent config, or environment."""
    addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
    prefs = context.preferences.addons.get(addon_name)
    if not prefs:
        for name, entry in context.preferences.addons.items():
            if "RexTools" in name:
                prefs = entry
                break

    key = ""
    if prefs and hasattr(prefs, "preferences"):
        key = getattr(prefs.preferences, "meshy_api_key", "").strip()

    if not key:
        from ..core.meshy_client import get_persistent_api_key
        key = get_persistent_api_key()
        if key and prefs and hasattr(prefs, "preferences"):
            try:
                prefs.preferences.meshy_api_key = key
            except Exception:
                pass
    return key


def _get_cache_dir(context=None) -> str:
    """
    Helper to retrieve or create the Meshy cache folder.
    Prioritizes a local cache folder ('rextools_meshy') alongside the saved .blend file.
    Falls back to preferences custom directory or system temp folder if .blend is unsaved.
    """
    addon_name = ".".join(__package__.split(".")[:3]) if __package__ and __package__.startswith("bl_ext.") else (__package__.partition('.')[0] if __package__ else "RexTools3")
    prefs = bpy.context.preferences.addons.get(addon_name)
    if not prefs:
        for name, entry in bpy.context.preferences.addons.items():
            if "RexTools" in name:
                prefs = entry
                break

    use_local = True
    custom_dir = ""
    if prefs and hasattr(prefs, "preferences"):
        use_local = getattr(prefs.preferences, "meshy_use_local_cache", True)
        custom_dir = getattr(prefs.preferences, "meshy_cache_dir", "").strip()

    if not custom_dir:
        from ..core.meshy_client import load_persistent_config
        cfg = load_persistent_config()
        if "meshy_use_local_cache" in cfg:
            use_local = bool(cfg["meshy_use_local_cache"])
        custom_dir = cfg.get("meshy_cache_dir", "").strip()

    # Prioritize local blend folder if enabled and blend file is saved
    if use_local and bpy.data.is_saved and bpy.data.filepath:
        blend_dir = os.path.dirname(bpy.data.filepath)
        cache_dir = os.path.join(blend_dir, "rextools_meshy")
    elif custom_dir and os.path.isdir(custom_dir):
        cache_dir = os.path.join(custom_dir, "rextools_meshy")
    else:
        cache_dir = os.path.join(tempfile.gettempdir(), "rextools_meshy")

    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

from ..core import meshy_io

_save_reference_image = meshy_io._save_reference_image
_export_temp_glb = meshy_io._export_temp_glb
_set_material_shading = meshy_io._set_material_shading
_safe_import_gltf = meshy_io._safe_import_gltf
_safe_import_fbx = meshy_io._safe_import_fbx
_replace_or_import_mesh = meshy_io._replace_or_import_mesh
_replace_mesh_with_imported = meshy_io._replace_or_import_mesh



def _redraw_all_areas():
    """Forces redraw of 3D Viewport and UI panels."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _sync_task_queue_items(props):
    """Synchronize props.task_queue_items collection with active tasks in TASK_QUEUE."""
    if not props:
        return
    active_tasks = [t for t in TASK_QUEUE if t.get("status") in ("RUNNING", "QUEUED")]
    if not active_tasks:
        if len(props.task_queue_items) > 0:
            props.task_queue_items.clear()
        return

    curr_ids = [item.task_id for item in props.task_queue_items]
    active_ids = [t.get("id", "") for t in active_tasks]

    if curr_ids != active_ids:
        props.task_queue_items.clear()
        for t in active_tasks:
            item = props.task_queue_items.add()
            item.task_id = t.get("id", "")
            item.title = t.get("title", "Task")
            item.task_type = t.get("task_type", "")
            item.status = t.get("status", "QUEUED")
            item.progress = int(t.get("progress", 0))
    else:
        for item, t in zip(props.task_queue_items, active_tasks):
            item.title = t.get("title", "Task")
            item.task_type = t.get("task_type", "")
            item.status = t.get("status", "QUEUED")
            item.progress = int(t.get("progress", 0))


def _refresh_credits_async():
    """Silently refresh Meshy credits balance in a background thread."""
    try:
        api_key = _get_api_key(bpy.context)
        if not api_key:
            return

        def _worker():
            try:
                bal = meshy_client.check_credit_balance(api_key)
                scene = getattr(bpy.context, "scene", None)
                props = getattr(scene, "rex_meshy_props", None) if scene else None
                if props:
                    props.credit_balance = bal
                    props.credit_status = f"{bal} credits"
                _redraw_all_areas()
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Timer Callback (Runs on Blender Main Thread)
# ---------------------------------------------------------------------------

def _meshy_task_timer():
    global _TIMER_REGISTERED
    scene = bpy.context.scene
    props = getattr(scene, "rex_meshy_props", None)

    # 1. Process completions and errors across all tasks in queue
    for task in list(TASK_QUEUE):
        status = task.get("status")

        # Handle completed task that needs import into Blender
        if status == "COMPLETED" and not task.get("imported"):
            task["imported"] = True
            result_path = task.get("result_filepath", "")
            target_name = task.get("target_obj_name", "")
            replace_sel = task.get("replace_selected", True)
            task_type = task.get("task_type", "")

            try:
                if result_path and os.path.isfile(result_path):
                    if task_type == 'IMAGE_TO_MESH':
                        new_mesh = _replace_or_import_mesh(
                            result_path,
                            target_name,
                            replace_selected=False
                        )
                        if props:
                            props.last_imported_object = new_mesh.name
                        notify.success(f"Generated 3D mesh '{new_mesh.name}' imported!")
                    elif task_type in ('UV_UNWRAP_ONLY', 'RETEXTURE', 'CHAINED_UNWRAP_TEXTURE'):
                        new_mesh = _replace_or_import_mesh(
                            result_path,
                            target_name,
                            replace_selected=replace_sel
                        )
                        if props:
                            props.last_imported_object = new_mesh.name
                        if task_type == 'UV_UNWRAP_ONLY':
                            if props:
                                props.uv_mode = 'PRESERVE'
                            notify.success(f"Selected mesh '{new_mesh.name}' replaced with UV unwrapped model!")
                        else:
                            notify.success(f"Selected mesh '{new_mesh.name}' replaced with PBR textured model!")

                    if props:
                        props.last_result_filepath = result_path
                        size_mb = os.path.getsize(result_path) / (1024 * 1024)
                        props.last_result_size = f"{size_mb:.2f} MB"
            except Exception as e:
                notify.error(f"Error importing '{task['title']}': {str(e)}")
            finally:
                _clean_task_temp_files(task)
                _refresh_credits_async()

        elif status == "FAILED" and not task.get("reported"):
            task["reported"] = True
            notify.error(f"Meshy Task Failed ({task['title']}): {task.get('error')}")
            _clean_task_temp_files(task)

        elif status == "CANCELLED" and not task.get("cleaned"):
            task["cleaned"] = True
            _clean_task_temp_files(task)

    # 2. Dispatch any queued tasks if slots opened up
    _dispatch_task_queue()

    # 3. Check for active tasks
    active_tasks = [t for t in TASK_QUEUE if t.get("status") in ("RUNNING", "QUEUED")]

    if active_tasks:
        if props:
            props.is_processing = True
            # Find the running task with highest progress
            running_tasks = [t for t in active_tasks if t.get("status") == "RUNNING"]
            display_task = running_tasks[0] if running_tasks else active_tasks[0]
            props.task_progress = display_task.get("progress", 0)
            props.status_message = display_task.get("status_message", "Processing...")
            props.task_type = display_task.get("task_type", "")
            props.task_id = display_task.get("meshy_task_id", "")
            _sync_task_queue_items(props)

        _set_statusbar_active(True)
        _redraw_all_areas()
        return 0.5  # Check again in 0.5s

    # 4. No active tasks remain
    if props:
        props.is_processing = False
        props.task_progress = 0
        props.status_message = "Ready"
        _sync_task_queue_items(props)

    _set_statusbar_active(False)
    _redraw_all_areas()
    _TIMER_REGISTERED = False
    return None

def _clean_temp_files():
    """Remove any temporary files tracked in TASK_STATE."""
    for fpath in TASK_STATE.get("temp_files", []):
        if os.path.isfile(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    TASK_STATE["temp_files"].clear()


# ---------------------------------------------------------------------------
# Background Worker Routines
# ---------------------------------------------------------------------------

# Map generation_mode enum values to (model_type, ai_model) pairs
_GENERATION_MODE_MAP = {
    "SMART_T2":        ("smart-topology", "meshy-t2"),
    "STANDARD_LATEST": ("standard", "latest"),
    "STANDARD_7_1":    ("standard", "meshy-7.1"),
    "STANDARD_6":      ("standard", "meshy-6"),
    "STANDARD_6_LITE": ("standard", "meshy-6-lite"),
}


def _run_image_to_mesh_worker(task, api_key, image_uri, topology, polycount, symmetry, should_texture, enable_pbr, generation_mode, cache_dir):
    try:
        task["status_message"] = "Submitting task to Meshy..."
        task["progress"] = 5
        TASK_STATE["status_message"] = task["status_message"]
        TASK_STATE["progress"] = 5

        model_type, ai_model = _GENERATION_MODE_MAP.get(generation_mode, ("standard", "latest"))

        task_id = meshy_client.create_image_to_3d_task(
            api_key=api_key,
            image_uri=image_uri,
            model_type=model_type,
            topology=topology,
            target_polycount=polycount,
            symmetry_mode=symmetry,
            should_remesh=True,
            should_texture=should_texture,
            enable_pbr=enable_pbr,
            ai_model=ai_model
        )
        task["meshy_task_id"] = task_id
        TASK_STATE["task_id"] = task_id

        # Polling loop
        while task.get("status") not in ("CANCELLED", "FAILED"):
            time.sleep(2.0)
            if task.get("status") == "CANCELLED":
                break
            res = meshy_client.get_image_to_3d_task(api_key, task_id)
            status = res.get("status", "").upper()
            progress = res.get("progress", 0)
            task["progress"] = max(progress, task["progress"])
            task["status_message"] = f"Generating 3D Mesh... ({progress}%)"
            TASK_STATE["progress"] = task["progress"]
            TASK_STATE["status_message"] = task["status_message"]

            if status == "SUCCEEDED":
                model_urls = res.get("model_urls", {})
                use_fbx = (model_type == "standard" and topology == "quad")

                if use_fbx:
                    fbx_url = model_urls.get("fbx")
                    if fbx_url:
                        task["status_message"] = "Downloading 3D Model (FBX / Quad)..."
                        out_path = os.path.join(cache_dir, f"meshy_{task_id}.fbx")
                        meshy_client.download_file(fbx_url, out_path)
                    else:
                        glb_url = model_urls.get("glb")
                        if not glb_url:
                            raise meshy_client.MeshyAPIError("No FBX or GLB URL returned by Meshy.")
                        task["status_message"] = "FBX not available, falling back to GLB (triangles)..."
                        out_path = os.path.join(cache_dir, f"meshy_{task_id}.glb")
                        meshy_client.download_file(glb_url, out_path)
                else:
                    glb_url = model_urls.get("glb")
                    if not glb_url:
                        raise meshy_client.MeshyAPIError("Meshy reported success, but no GLB download URL was returned.")
                    task["status_message"] = "Downloading 3D Model..."
                    out_path = os.path.join(cache_dir, f"meshy_{task_id}.glb")
                    meshy_client.download_file(glb_url, out_path)

                task["result_filepath"] = out_path
                task["progress"] = 100
                task["status"] = "COMPLETED"
                TASK_STATE["result_filepath"] = out_path
                TASK_STATE["progress"] = 100
                break
            elif status in ("FAILED", "EXPIRED"):
                error_msg = res.get("task_error", {}).get("message", "Task failed during generation.")
                raise meshy_client.MeshyAPIError(error_msg)

    except Exception as e:
        task["status"] = "FAILED"
        task["error"] = str(e)
        TASK_STATE["error"] = str(e)
    finally:
        TASK_STATE["finished"] = True


def _run_uv_unwrap_worker(task, api_key, glb_path, cache_dir):
    try:
        task["status_message"] = "Encoding model & submitting UV unwrap (5 cr)..."
        task["progress"] = 10

        model_uri = meshy_client.encode_file_to_octet_stream_data_uri(glb_path)
        task_id = meshy_client.create_uv_unwrap_task(api_key, model_uri, is_task_id=False)
        task["meshy_task_id"] = task_id

        while task.get("status") not in ("CANCELLED", "FAILED"):
            time.sleep(2.0)
            if task.get("status") == "CANCELLED":
                break
            res = meshy_client.get_uv_unwrap_task(api_key, task_id)
            status = res.get("status", "").upper()
            progress = res.get("progress", 0)
            task["progress"] = max(progress, task["progress"])
            task["status_message"] = f"Unwrapping UVs (5 credits)... ({progress}%)"

            if status == "SUCCEEDED":
                model_urls = res.get("model_urls", {})
                glb_url = model_urls.get("glb")
                if not glb_url:
                    raise meshy_client.MeshyAPIError("UV unwrap succeeded, but no GLB download URL was returned.")

                task["status_message"] = "Downloading unwrapped model..."
                out_path = os.path.join(cache_dir, f"meshy_unwrap_{task_id}.glb")
                meshy_client.download_file(glb_url, out_path)
                task["result_filepath"] = out_path
                task["progress"] = 100
                task["status"] = "COMPLETED"
                break
            elif status in ("FAILED", "EXPIRED"):
                error_msg = res.get("task_error", {}).get("message", "UV Unwrap task failed.")
                raise meshy_client.MeshyAPIError(error_msg)

    except Exception as e:
        task["status"] = "FAILED"
        task["error"] = str(e)
    finally:
        TASK_STATE["finished"] = True


def _run_chained_unwrap_and_retexture_worker(
    task, api_key, glb_path, image_ref_uri, text_prompt, enable_pbr, remove_lighting, uv_mode, cache_dir, ai_model="latest"
):
    try:
        # --- Stage 1: Dedicated UV Unwrap if requested ---
        if uv_mode == 'NEW_UNWRAP':
            task["status_message"] = "Stage 1/2: Submitting Dedicated UV Unwrap (5 cr)..."
            task["progress"] = 5

            model_uri = meshy_client.encode_file_to_octet_stream_data_uri(glb_path)
            unwrap_id = meshy_client.create_uv_unwrap_task(api_key, model_uri, is_task_id=False)
            task["meshy_task_id"] = unwrap_id

            while task.get("status") not in ("CANCELLED", "FAILED"):
                time.sleep(2.0)
                if task.get("status") == "CANCELLED":
                    break
                res = meshy_client.get_uv_unwrap_task(api_key, unwrap_id)
                status = res.get("status", "").upper()
                progress = res.get("progress", 0)
                task["progress"] = int(progress * 0.45)
                task["status_message"] = f"Stage 1/2: Dedicated UV Unwrapping ({progress}%)..."

                if status == "SUCCEEDED":
                    break
                elif status in ("FAILED", "EXPIRED"):
                    err = res.get("task_error", {}).get("message", "UV Unwrap failed.")
                    raise meshy_client.MeshyAPIError(err)

            # Ready for texturing onto the unwrapped task
            retexture_input = unwrap_id
            is_task_id = True
            enable_orig_uv = True
        elif uv_mode == 'PRESERVE':
            model_uri = meshy_client.encode_file_to_octet_stream_data_uri(glb_path)
            retexture_input = model_uri
            is_task_id = False
            enable_orig_uv = True
        else:  # LEGACY_AUTO
            model_uri = meshy_client.encode_file_to_octet_stream_data_uri(glb_path)
            retexture_input = model_uri
            is_task_id = False
            enable_orig_uv = False

        if task.get("status") == "CANCELLED":
            return

        # --- Stage 2: Retexture with Image Style Reference ---
        task["status_message"] = "Stage 2/2: Submitting Retexturing Task..."
        task["progress"] = 50 if uv_mode == 'NEW_UNWRAP' else 5

        retexture_id = meshy_client.create_retexture_task(
            api_key=api_key,
            model_uri_or_task_id=retexture_input,
            image_style_uri=image_ref_uri,
            text_style_prompt=text_prompt,
            enable_original_uv=enable_orig_uv,
            enable_pbr=enable_pbr,
            remove_lighting=remove_lighting,
            is_task_id=is_task_id,
            ai_model=ai_model
        )
        task["meshy_task_id"] = retexture_id

        while task.get("status") not in ("CANCELLED", "FAILED"):
            time.sleep(2.0)
            if task.get("status") == "CANCELLED":
                break
            res = meshy_client.get_retexture_task(api_key, retexture_id)
            status = res.get("status", "").upper()
            progress = res.get("progress", 0)

            base_progress = 50 if uv_mode == 'NEW_UNWRAP' else 0
            scale = 0.5 if uv_mode == 'NEW_UNWRAP' else 1.0
            task["progress"] = int(base_progress + (progress * scale))
            task["status_message"] = f"Generating PBR Textures from image... ({progress}%)"

            if status == "SUCCEEDED":
                model_urls = res.get("model_urls", {})
                glb_url = model_urls.get("glb")
                if not glb_url:
                    raise meshy_client.MeshyAPIError("Retexture succeeded, but no GLB download URL was returned.")

                task["status_message"] = "Downloading textured model..."
                out_path = os.path.join(cache_dir, f"meshy_textured_{retexture_id}.glb")
                meshy_client.download_file(glb_url, out_path)
                task["result_filepath"] = out_path
                task["progress"] = 100
                task["status"] = "COMPLETED"
                break
            elif status in ("FAILED", "EXPIRED"):
                err = res.get("task_error", {}).get("message", "Retexturing task failed.")
                raise meshy_client.MeshyAPIError(err)

    except Exception as e:
        task["status"] = "FAILED"
        task["error"] = str(e)
    finally:
        TASK_STATE["finished"] = True


# ---------------------------------------------------------------------------
# Blender Operators
# ---------------------------------------------------------------------------

class REXTOOLS3_OT_meshy_check_balance(Operator):
    """Check Meshy account credit balance"""
    bl_idname = "rextools3.meshy_check_balance"
    bl_label = "Check Credits"
    bl_description = "Check current available Meshy API credit balance"

    def execute(self, context):
        api_key = _get_api_key(context)
        if not api_key:
            notify.error("Please enter your Meshy API Key in RexTools3 Preferences.")
            return {'CANCELLED'}

        props = getattr(context.scene, "rex_meshy_props", None)

        def _worker():
            try:
                bal = meshy_client.check_credit_balance(api_key)
                if props:
                    props.credit_balance = bal
                    props.credit_status = f"{bal} credits"
                notify.success(f"Meshy Connected! Balance: {bal} credits")
            except Exception as e:
                if props:
                    props.credit_status = "Connection Error"
                notify.error(f"Meshy Error: {str(e)}")

        threading.Thread(target=_worker, daemon=True).start()
        return {'FINISHED'}


class REXTOOLS3_OT_meshy_image_to_mesh(Operator):
    """Generate 3D mesh from input image using Meshy API"""
    bl_idname = "rextools3.meshy_image_to_mesh"
    bl_label = "Generate 3D Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "rex_meshy_props", None)
        return props is not None

    def execute(self, context):
        api_key = _get_api_key(context)
        if not api_key:
            notify.error("Meshy API key is missing. Set it in RexTools3 Preferences.")
            return {'CANCELLED'}

        props = context.scene.rex_meshy_props

        # 1. Resolve source image to Base64 URI
        try:
            if props.image_source == 'FILE':
                if not props.image_filepath or not os.path.isfile(props.image_filepath):
                    notify.error("Please select a valid image file from disk.")
                    return {'CANCELLED'}
                image_uri = meshy_client.encode_image_file_to_data_uri(props.image_filepath)
                ref_name = os.path.basename(props.image_filepath)
            else:
                if not props.blender_image:
                    notify.error("Please pick an active Blender Image datablock.")
                    return {'CANCELLED'}
                image_uri = meshy_client.encode_blender_image_to_data_uri(props.blender_image)
                ref_name = props.blender_image.name
        except Exception as e:
            notify.error(f"Image encoding error: {str(e)}")
            return {'CANCELLED'}

        cache_dir = _get_cache_dir(context)

        # Cache input reference image to local/active cache
        saved_ref = _save_reference_image(
            source_type=props.image_source,
            filepath=props.image_filepath,
            blender_image=props.blender_image,
            cache_dir=cache_dir,
            prefix="ref_mesh"
        )
        if saved_ref:
            props.last_ref_image_filepath = saved_ref

        is_smart = props.generation_mode == "SMART_T2"
        polycount = props.polycount_smart if is_smart else props.polycount_standard
        task_title = f"Model: {ref_name}"

        _queue_task(
            title=task_title,
            task_type='IMAGE_TO_MESH',
            worker_target=_run_image_to_mesh_worker,
            worker_args=(
                api_key,
                image_uri,
                props.topology,
                polycount,
                props.symmetry_mode,
                props.should_texture,
                props.enable_pbr,
                props.generation_mode,
                cache_dir
            ),
            target_obj_name="",
            replace_selected=False
        )

        notify.info(f"Queued '{task_title}' for Meshy 3D generation.")
        return {'FINISHED'}


class REXTOOLS3_OT_meshy_uv_unwrap_only(Operator):
    """Unwrap active mesh using Meshy's new dedicated UV unwrapper (Costs 5 credits)"""
    bl_idname = "rextools3.meshy_uv_unwrap_only"
    bl_label = "Unwrap UVs Only (5 cr)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "rex_meshy_props", None)
        return (
            props and
            context.active_object and context.active_object.type == 'MESH'
        )

    def execute(self, context):
        api_key = _get_api_key(context)
        if not api_key:
            notify.error("Meshy API key is missing. Set it in RexTools3 Preferences.")
            return {'CANCELLED'}

        props = context.scene.rex_meshy_props
        obj = context.active_object

        face_count = len(obj.data.polygons)
        if face_count > 40000:
            notify.warning(f"Model has {face_count:,} faces (> 40,000 limit). Meshy may reject request.")

        cache_dir = _get_cache_dir(context)
        temp_glb = os.path.join(cache_dir, f"export_temp_{int(time.time()*1000)}.glb")

        try:
            _export_temp_glb(obj, temp_glb)
        except Exception as e:
            notify.error(f"GLB export failed: {str(e)}")
            return {'CANCELLED'}

        task_title = f"UV: {obj.name}"
        _queue_task(
            title=task_title,
            task_type='UV_UNWRAP_ONLY',
            worker_target=_run_uv_unwrap_worker,
            worker_args=(api_key, temp_glb, cache_dir),
            target_obj_name=obj.name,
            replace_selected=True,
            temp_files=[temp_glb]
        )

        notify.info(f"Queued '{task_title}' for dedicated UV unwrapping.")
        return {'FINISHED'}


class REXTOOLS3_OT_meshy_retexture(Operator):
    """Unwrap and texture mesh based on an image style reference"""
    bl_idname = "rextools3.meshy_retexture"
    bl_label = "Unwrap & Texture from Image"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "rex_meshy_props", None)
        return (
            props and
            context.active_object and context.active_object.type == 'MESH'
        )

    def execute(self, context):
        api_key = _get_api_key(context)
        if not api_key:
            notify.error("Meshy API key is missing. Set it in RexTools3 Preferences.")
            return {'CANCELLED'}

        props = context.scene.rex_meshy_props
        obj = context.active_object

        # 1. Resolve style reference image
        try:
            if props.retexture_image_source == 'FILE':
                if not props.retexture_image_filepath or not os.path.isfile(props.retexture_image_filepath):
                    notify.error("Please select a reference image file.")
                    return {'CANCELLED'}
                image_ref_uri = meshy_client.encode_image_file_to_data_uri(props.retexture_image_filepath)
            else:
                if not props.retexture_blender_image:
                    notify.error("Please pick a Blender Image datablock for reference.")
                    return {'CANCELLED'}
                image_ref_uri = meshy_client.encode_blender_image_to_data_uri(props.retexture_blender_image)
        except Exception as e:
            notify.error(f"Reference image error: {str(e)}")
            return {'CANCELLED'}

        cache_dir = _get_cache_dir(context)

        # Cache input reference image to local/active cache
        saved_ref = _save_reference_image(
            source_type=props.retexture_image_source,
            filepath=props.retexture_image_filepath,
            blender_image=props.retexture_blender_image,
            cache_dir=cache_dir,
            prefix="ref_texture"
        )
        if saved_ref:
            props.last_ref_image_filepath = saved_ref

        temp_glb = os.path.join(cache_dir, f"export_retex_{int(time.time()*1000)}.glb")

        try:
            _export_temp_glb(obj, temp_glb)
        except Exception as e:
            notify.error(f"GLB export failed: {str(e)}")
            return {'CANCELLED'}

        task_title = f"Texture: {obj.name}"
        task_type = 'CHAINED_UNWRAP_TEXTURE' if props.uv_mode == 'NEW_UNWRAP' else 'RETEXTURE'

        _queue_task(
            title=task_title,
            task_type=task_type,
            worker_target=_run_chained_unwrap_and_retexture_worker,
            worker_args=(
                api_key,
                temp_glb,
                image_ref_uri,
                props.text_style_prompt,
                props.retexture_enable_pbr,
                props.remove_lighting,
                props.uv_mode,
                cache_dir,
                props.retexture_ai_model
            ),
            target_obj_name=obj.name,
            replace_selected=props.replace_selected,
            temp_files=[temp_glb]
        )

        notify.info(f"Queued '{task_title}' for PBR texturing.")
        return {'FINISHED'}


class REXTOOLS3_OT_meshy_cancel_task(Operator):
    """Cancel running Meshy task or all queued tasks"""
    bl_idname = "rextools3.meshy_cancel_task"
    bl_label = "Cancel Task"

    task_id: bpy.props.StringProperty(name="Task ID", default="")

    @classmethod
    def poll(cls, context):
        return any(t.get("status") in ("RUNNING", "QUEUED") for t in TASK_QUEUE) or getattr(getattr(context.scene, "rex_meshy_props", None), "is_processing", False)

    def execute(self, context):
        if self.task_id:
            _cancel_task_by_id(self.task_id)
            notify.warning("Meshy task cancelled.")
        else:
            active_tasks = [t for t in TASK_QUEUE if t.get("status") in ("RUNNING", "QUEUED")]
            if active_tasks:
                for t in active_tasks:
                    t["status"] = "CANCELLED"
                    t["status_message"] = "Cancelled"
                    _clean_task_temp_files(t)
                notify.warning(f"Cancelled {len(active_tasks)} Meshy task(s).")
            else:
                TASK_STATE["cancelled"] = True
                notify.warning("Meshy task cancelled.")

        props = getattr(context.scene, "rex_meshy_props", None)
        if props:
            _sync_task_queue_items(props)
        if props and not any(t.get("status") in ("RUNNING", "QUEUED") for t in TASK_QUEUE):
            props.is_processing = False
            props.status_message = "Cancelled"
            _set_statusbar_active(False)

        _redraw_all_areas()
        return {'FINISHED'}


class REXTOOLS3_OT_meshy_open_cache(Operator):
    """Open Meshy cache directory in system file browser"""
    bl_idname = "rextools3.meshy_open_cache"
    bl_label = "Open Cache Folder"

    def execute(self, context):
        cache_dir = _get_cache_dir(context)
        import subprocess
        import sys
        if sys.platform == "win32":
            os.startfile(cache_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", cache_dir])
        else:
            subprocess.Popen(["xdg-open", cache_dir])
        return {'FINISHED'}


class REXTOOLS3_OT_meshy_clear_cache(Operator):
    """Delete all cached files in Meshy cache folder"""
    bl_idname = "rextools3.meshy_clear_cache"
    bl_label = "Clear Cache"
    bl_description = "Delete cached GLB models and textures"

    def execute(self, context):
        cache_dir = _get_cache_dir(context)
        count = 0
        if os.path.exists(cache_dir):
            for fname in os.listdir(cache_dir):
                fpath = os.path.join(cache_dir, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                        count += 1
                except Exception:
                    pass
        notify.info(f"Cleared {count} cached Meshy files.")
        return {'FINISHED'}


class REXTOOLS3_OT_meshy_replace_from_last(Operator):
    """Replace active selected mesh with the last downloaded Meshy model"""
    bl_idname = "rextools3.meshy_replace_from_last"
    bl_label = "Replace Selected with Last Model"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "rex_meshy_props", None)
        return (
            props and props.last_result_filepath and
            os.path.isfile(props.last_result_filepath) and
            os.path.getsize(props.last_result_filepath) > 0 and
            context.active_object and context.active_object.type == 'MESH'
        )

    def execute(self, context):
        props = context.scene.rex_meshy_props
        try:
            new_mesh = _replace_or_import_mesh(
                props.last_result_filepath,
                context.active_object.name,
                replace_selected=True
            )
            notify.success(f"Replaced selected mesh with '{new_mesh.name}'!")
            return {'FINISHED'}
        except Exception as e:
            notify.error(f"Replace failed: {str(e)}")
            return {'CANCELLED'}


class REXTOOLS3_OT_meshy_import_last(Operator):
    """Import the last generated Meshy model at the 3D Cursor"""
    bl_idname = "rextools3.meshy_import_last"
    bl_label = "Import Last Model at Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "rex_meshy_props", None)
        return (
            props and props.last_result_filepath and
            os.path.isfile(props.last_result_filepath) and
            os.path.getsize(props.last_result_filepath) > 0
        )

    def execute(self, context):
        props = context.scene.rex_meshy_props
        try:
            new_mesh = _replace_or_import_mesh(
                props.last_result_filepath,
                "",
                replace_selected=False
            )
            notify.success(f"Imported model '{new_mesh.name}' at 3D cursor!")
            return {'FINISHED'}
        except Exception as e:
            notify.error(f"Import failed: {str(e)}")
            return {'CANCELLED'}



class REXTOOLS3_OT_meshy_switch_tab(bpy.types.Operator):
    '''Switch the Meshy panel to a specific tab'''
    bl_idname = 'rextools3.meshy_switch_tab'
    bl_label = 'Switch Meshy Tab'

    tab: bpy.props.StringProperty(name='Tab', default='SETTINGS')  # type: ignore

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, 'rex_meshy_props', None) is not None

    def execute(self, context):
        context.scene.rex_meshy_props.active_tab = self.tab
        return {'FINISHED'}



def _get_short_meshy_status(task_type: str, status_msg: str) -> str:
    msg_l = (status_msg or "").lower()
    if "download" in msg_l:
        return "Downloading model..."
    if "stage 1" in msg_l or "unwrap" in msg_l or task_type == 'UV_UNWRAP_ONLY':
        return "UV unwrapping..."
    if "texture" in msg_l or "pbr" in msg_l or task_type in ('RETEXTURE', 'CHAINED_UNWRAP_TEXTURE'):
        return "Mesh texturing..."
    if "mesh" in msg_l or task_type == 'IMAGE_TO_MESH':
        return "Mesh generating..."
    return "Mesh generating..."


def _draw_meshy_status_middle(header, context):
    """Draws a complete status bar layout with the progress bar in the exact center."""
    scene = getattr(context, "scene", None)
    props = getattr(scene, 'rex_meshy_props', None) if scene else None
    layout = header.layout

    # 1. Left side input/keymap shortcuts
    try:
        layout.template_input_status()
    except Exception:
        pass

    # 2. Expanding spacer to push towards center
    if hasattr(layout, "separator_spacer"):
        layout.separator_spacer()

    # 3. Center: Meshy Progress Bar Widget
    if props and props.is_processing:
        row = layout.row(align=True)
        task_type = getattr(props, "task_type", "") or TASK_STATE.get("task_type", "")
        short_text = _get_short_meshy_status(task_type, props.status_message)

        # Active tasks badge
        active_count = len([t for t in TASK_QUEUE if t.get("status") in ("RUNNING", "QUEUED")])
        badge = f" ({active_count})" if active_count > 1 else ""

        sub = row.row(align=True)
        if hasattr(sub, "ui_units_x"):
            sub.ui_units_x = 14.0
        sub.prop(
            props, "task_progress",
            text=f"{short_text}{badge}",
            icon='TIME',
            slider=True
        )
        row.operator("rextools3.meshy_cancel_task", text="", icon='CANCEL')

    # Also display any active reports banner (e.g. Save notifications)
    try:
        layout.template_reports_banner()
    except Exception:
        pass

    # 4. Expanding spacer to push stats to the right
    if hasattr(layout, "separator_spacer"):
        layout.separator_spacer()

    # 5. Right side scene statistics and version info
    try:
        r = layout.row()
        r.alignment = 'RIGHT'
        r.template_status_info()
    except Exception:
        pass


_draw_meshy_status = _draw_meshy_status_middle


def register():
    # Clean up any lingering header append callbacks from previous versions
    try:
        bpy.types.STATUSBAR_HT_header.remove(_draw_meshy_status)
    except Exception:
        pass
    try:
        bpy.types.STATUSBAR_HT_header.remove(_draw_meshy_status_middle)
    except Exception:
        pass


def unregister():
    _set_statusbar_active(False)
    try:
        bpy.types.STATUSBAR_HT_header.remove(_draw_meshy_status)
    except Exception:
        pass
    try:
        bpy.types.STATUSBAR_HT_header.remove(_draw_meshy_status_middle)
    except Exception:
        pass
