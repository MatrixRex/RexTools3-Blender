import os
import json
import base64
import urllib.request
import urllib.error
import tempfile
import bpy

BASE_URL = "https://api.meshy.ai/openapi/v1"


# ---------------------------------------------------------------------------
# Persistent Configuration Storage (~/.rextools3/config.json)
# ---------------------------------------------------------------------------

def get_config_dir() -> str:
    """Return the user configuration directory for RexTools3 (~/.rextools3)."""
    cfg_dir = os.path.join(os.path.expanduser("~"), ".rextools3")
    try:
        os.makedirs(cfg_dir, exist_ok=True)
    except Exception:
        pass
    return cfg_dir


def get_config_filepath() -> str:
    """Return the path to the persistent config.json."""
    return os.path.join(get_config_dir(), "config.json")


def load_persistent_config() -> dict:
    """Read the persistent configuration dictionary from ~/.rextools3/config.json."""
    cfg_path = get_config_filepath()
    if not os.path.isfile(cfg_path):
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[RexTools3] Warning: could not load config from {cfg_path}: {e}")
        return {}


def save_persistent_config(data: dict) -> None:
    """Update and write persistent configuration to ~/.rextools3/config.json atomically."""
    if not isinstance(data, dict):
        return
    cfg_path = get_config_filepath()
    existing = load_persistent_config()
    changed = False
    for k, v in data.items():
        if existing.get(k) != v:
            existing[k] = v
            changed = True
    if not changed and os.path.exists(cfg_path):
        return

    try:
        tmp_path = cfg_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        if os.path.exists(cfg_path):
            os.replace(tmp_path, cfg_path)
        else:
            os.rename(tmp_path, cfg_path)
    except Exception as e:
        print(f"[RexTools3] Warning: could not save config to {cfg_path}: {e}")


def get_persistent_api_key() -> str:
    """Retrieve Meshy API key from persistent config or environment variable."""
    cfg = load_persistent_config()
    key = cfg.get("meshy_api_key", "")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return os.environ.get("MESHY_API_KEY", "").strip()


def save_persistent_api_key(api_key: str) -> None:
    """Save Meshy API key to persistent config."""
    save_persistent_config({"meshy_api_key": (api_key or "").strip()})


class MeshyAPIError(Exception):
    """Exception raised for errors during Meshy API interaction."""
    def __init__(self, message, status_code=None, error_code=None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def _make_request(endpoint: str, api_key: str, method: str = "GET", data: dict = None, timeout: int = 45) -> dict:
    """Internal helper to perform HTTPS requests to the Meshy API."""
    if not api_key or not api_key.strip():
        api_key = get_persistent_api_key()

    if not api_key or not api_key.strip():
        raise MeshyAPIError("Meshy API key is missing. Please enter your API key in RexTools3 Preferences.", status_code=401)

    url = f"{BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "User-Agent": "RexTools3-Blender-Addon/1.0",
        "Accept": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_bytes = response.read()
            if not resp_bytes:
                return {}
            return json.loads(resp_bytes.decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = f"HTTP {e.code}: {e.reason}"
        err_code = None
        try:
            err_body = e.read().decode("utf-8")
            err_json = json.loads(err_body)
            if "message" in err_json:
                err_msg = err_json["message"]
            elif "error" in err_json:
                err_msg = err_json["error"]
            err_code = err_json.get("code")
        except Exception:
            pass

        if e.code == 401:
            err_msg = "Invalid API Key. Please verify your Meshy API key in Preferences."
        elif e.code == 402:
            err_msg = "Insufficient Meshy credits for this request. Please check your credit balance."
        elif e.code == 429:
            err_msg = "Rate limit reached. Please wait a moment before trying again."

        raise MeshyAPIError(err_msg, status_code=e.code, error_code=err_code)
    except urllib.error.URLError as e:
        raise MeshyAPIError(f"Network error connecting to Meshy API: {e.reason}")
    except Exception as e:
        raise MeshyAPIError(f"Unexpected error: {str(e)}")


# ---------------------------------------------------------------------------
# Data Encoding Utilities
# ---------------------------------------------------------------------------

def encode_image_file_to_data_uri(filepath: str) -> str:
    """Encode an image file on disk to a Base64 data URI."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Image file not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()
    mime = "image/png"
    if ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"

    with open(filepath, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime};base64,{encoded}"


def encode_blender_image_to_data_uri(image: bpy.types.Image) -> str:
    """
    Encode a Blender Image datablock to a Base64 data URI.
    If image is on disk, reads directly; otherwise saves to a temporary PNG.
    """
    if not image:
        raise ValueError("No Blender Image provided.")

    filepath = bpy.path.abspath(image.filepath) if image.filepath else ""
    if filepath and os.path.isfile(filepath):
        return encode_image_file_to_data_uri(filepath)

    # Image is packed or procedural (e.g. Render Result) -> write temporary file
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"rextools_meshy_{image.name.replace(' ', '_')}.png")
    
    # Save a copy using Blender's image API
    orig_file_format = image.file_format
    try:
        image.file_format = 'PNG'
        image.save(filepath=temp_path)
    finally:
        image.file_format = orig_file_format

    try:
        return encode_image_file_to_data_uri(temp_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def encode_file_to_octet_stream_data_uri(filepath: str) -> str:
    """Encode a binary file (such as a .glb) to a Base64 data URI."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:application/octet-stream;base64,{encoded}"


# ---------------------------------------------------------------------------
# Meshy API Client Endpoints
# ---------------------------------------------------------------------------

def check_credit_balance(api_key: str) -> int:
    """Retrieve the user's available Meshy credit balance."""
    data = _make_request("/balance", api_key, method="GET")
    # Response usually has {"balance": 150} or credits info
    return data.get("balance", 0)


def create_image_to_3d_task(
    api_key: str,
    image_uri: str,
    model_type: str = "standard",
    topology: str = "triangle",
    target_polycount: int = 30000,
    symmetry_mode: str = "auto",
    should_remesh: bool = True,
    should_texture: bool = True,
    enable_pbr: bool = True,
    ai_model: str = "latest"
) -> str:
    """Submit an Image-to-3D generation task. Returns task_id.

    When model_type is 'smart-topology', the API ignores topology, should_remesh,
    and save_pre_remeshed_model — so we omit those from the payload.
    """
    payload = {
        "image_url": image_uri,
        "model_type": model_type,
        "target_polycount": int(target_polycount),
        "symmetry_mode": symmetry_mode,
        "should_texture": should_texture,
        "enable_pbr": enable_pbr,
        "ai_model": ai_model
    }
    # topology / should_remesh are only meaningful for standard generation
    if model_type == "standard":
        payload["topology"] = topology
        payload["should_remesh"] = should_remesh

    res = _make_request("/image-to-3d", api_key, method="POST", data=payload)
    return res.get("result", "")


def get_image_to_3d_task(api_key: str, task_id: str) -> dict:
    """Get the current status of an Image-to-3D task."""
    return _make_request(f"/image-to-3d/{task_id}", api_key, method="GET")


def create_uv_unwrap_task(
    api_key: str,
    model_uri_or_task_id: str,
    is_task_id: bool = False
) -> str:
    """
    Submit a Dedicated UV Unwrap task (costs 5 credits).
    Returns task_id.
    """
    if is_task_id:
        payload = {"input_task_id": model_uri_or_task_id}
    else:
        payload = {"model_url": model_uri_or_task_id}

    res = _make_request("/uv-unwrap", api_key, method="POST", data=payload)
    return res.get("result", "")


def get_uv_unwrap_task(api_key: str, task_id: str) -> dict:
    """Get the status and model_urls for a UV Unwrap task."""
    return _make_request(f"/uv-unwrap/{task_id}", api_key, method="GET")


def create_retexture_task(
    api_key: str,
    model_uri_or_task_id: str,
    image_style_uri: str = "",
    text_style_prompt: str = "",
    enable_original_uv: bool = True,
    enable_pbr: bool = True,
    remove_lighting: bool = True,
    is_task_id: bool = False,
    ai_model: str = "latest"
) -> str:
    """Submit a Retexture task. Returns task_id."""
    payload = {
        "enable_original_uv": enable_original_uv,
        "enable_pbr": enable_pbr,
        "remove_lighting": remove_lighting,
        "ai_model": ai_model
    }

    if is_task_id:
        payload["input_task_id"] = model_uri_or_task_id
    else:
        payload["model_url"] = model_uri_or_task_id

    if image_style_uri:
        payload["image_style_url"] = image_style_uri
    if text_style_prompt:
        payload["text_style_prompt"] = text_style_prompt

    res = _make_request("/retexture", api_key, method="POST", data=payload)
    return res.get("result", "")


def get_retexture_task(api_key: str, task_id: str) -> dict:
    """Get the status and results of a Retexture task."""
    return _make_request(f"/retexture/{task_id}", api_key, method="GET")


def download_file(url: str, destination_path: str, timeout: int = 120) -> str:
    """
    Download a remote file (GLB or texture) to local disk safely.
    Writes to a temporary .tmp file first, verifies non-zero byte size,
    and atomically moves it to destination_path to prevent 0-byte corrupted files.
    """
    import ssl
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    temp_path = destination_path + ".tmp"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    try:
        ctx = ssl.create_default_context()
    except Exception:
        ctx = ssl._create_unverified_context()

    req = urllib.request.Request(url, headers=headers)
    resp = None

    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
    except Exception as e:
        # Fallback to unverified SSL context in case of local certificate store issues in Blender
        try:
            unverified_ctx = ssl._create_unverified_context()
            resp = urllib.request.urlopen(req, context=unverified_ctx, timeout=timeout)
        except Exception:
            # Fallback to direct URL open without custom request headers (for strict S3 signed URLs)
            resp = urllib.request.urlopen(url, timeout=timeout)

    total_bytes = 0
    try:
        with resp, open(temp_path, "wb") as out_file:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out_file.write(chunk)
                total_bytes += len(chunk)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise MeshyAPIError(f"Error downloading asset file: {str(e)}")

    if total_bytes == 0:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise MeshyAPIError("Downloaded asset file is empty (0 bytes). The download link may have expired or is unavailable.")

    # Atomically replace destination file
    if os.path.exists(destination_path):
        try:
            os.remove(destination_path)
        except Exception:
            pass

    os.rename(temp_path, destination_path)
    return destination_path
