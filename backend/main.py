"""BETANIA API: puente seguro entre la web y ComfyUI/Wan 2.2 TI2V-5B."""
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import uuid
import re
from pathlib import Path
from starlette.background import BackgroundTask
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
PUBLIC_ORIGIN = os.getenv("BETANIA_ORIGIN", "*")
API_KEY = os.getenv("BETANIA_API_KEY", "")
WORKFLOW_FILE = Path(os.getenv("WAN_WORKFLOW_JSON", Path(__file__).with_name("wan2_2_5b_t2v.json")))
app = FastAPI(title="BETANIA Video API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[PUBLIC_ORIGIN] if PUBLIC_ORIGIN != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

def require_api_key(authorization: str | None = Header(default=None)):
    if API_KEY and not hmac.compare_digest(authorization or "", "Bearer " + API_KEY):
        raise HTTPException(status_code=401, detail="Clave de BETANIA inválida o ausente.")


def video_signature(prompt_id: str) -> str:
    if not API_KEY:
        return "public"
    return hmac.new(API_KEY.encode("utf-8"), prompt_id.encode("utf-8"), hashlib.sha256).hexdigest()


class AssembleRequest(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=120)


class JobRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=12000)
    scene_index: int = Field(ge=1, le=120)
    title: str = Field(default="BETANIA", max_length=200)
    reference_image: str | None = Field(default=None, max_length=500)


def to_api_prompt(graph: dict, positive_prompt: str) -> dict:
    """Convert the official ComfyUI graph workflow into /prompt API format."""
    nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
    links = {}
    for link in graph.get("links", []):
        # ComfyUI graph link: [link_id, origin_node, origin_slot, target_node, target_slot, type]
        links[str(link[0])] = [str(link[1]), int(link[2])]

    widget_inputs = {
        "UNETLoader": ["unet_name", "weight_dtype"],
        "CLIPLoader": ["clip_name", "type", "device"],
        "VAELoader": ["vae_name"],
        "CLIPTextEncode": ["text"],
        "KSampler": ["seed", None, "steps", "cfg", "sampler_name", "scheduler", "denoise"],
        "ModelSamplingSD3": ["shift"],
        "Wan22ImageToVideoLatent": ["width", "height", "length", "batch_size"],
        "CreateVideo": ["fps"],
        "LoadImage": ["image"],
        "SaveVideo": ["filename_prefix", "format", "codec"],
    }
    prompt = {}
    for node_id, node in nodes.items():
        if int(node.get("mode", 0)) != 0:
            continue
        node_type = node.get("type")
        if node_type in ("MarkdownNote", "Note"):
            continue
        inputs = {}
        for item in node.get("inputs", []):
            link_id = item.get("link")
            if link_id is not None and str(link_id) in links:
                inputs[item["name"]] = links[str(link_id)]
        names = widget_inputs.get(node_type, [])
        values = node.get("widgets_values", [])
        for index, name in enumerate(names):
            if name and index < len(values):
                value = values[index]
                if node_type == "CLIPTextEncode" and node_id == "6":
                    value = positive_prompt
                if node_type == "KSampler" and name == "seed":
                    value = secrets.randbelow(2**63)
                inputs[name] = value
        if node_type == "CLIPTextEncode" and node_id == "6":
            inputs["text"] = positive_prompt
        prompt[node_id] = {"class_type": node_type, "inputs": inputs}
    if not any(node.get("class_type") == "SaveVideo" for node in prompt.values()):
        raise ValueError("El workflow no contiene un nodo SaveVideo.")
    return prompt


async def comfy_get(path: str):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(COMFYUI_URL + path)
            response.raise_for_status()
            return response
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con ComfyUI: {exc}") from exc


@app.get("/health")
async def health():
    try:
        await comfy_get("/system_stats")
        return {"status": "ok", "engine": "ComfyUI + Wan 2.2 TI2V-5B", "configured": True}
    except HTTPException:
        return {"status": "backend_online", "engine": "Wan 2.2 pendiente de ComfyUI", "configured": False}



@app.post("/api/reference")
async def upload_reference(file: UploadFile = File(...), _auth=Depends(require_api_key)):
    allowed = {"image/png", "image/jpeg", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Usa una imagen PNG, JPG o WEBP.")
    content = await file.read()
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La imagen debe pesar menos de 10 MB.")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                COMFYUI_URL + "/upload/image",
                files={"image": (file.filename or "betania-reference.png", content, file.content_type)},
                data={"type": "input", "overwrite": "true"},
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo subir la referencia a ComfyUI: {exc}") from exc
    name = result.get("name")
    subfolder = result.get("subfolder", "")
    if not name:
        raise HTTPException(status_code=502, detail="ComfyUI no devolvió el nombre del archivo.")
    return {"image_name": f"{subfolder}/{name}" if subfolder else name, "status": "uploaded"}

@app.post("/api/jobs")
async def create_job(body: JobRequest, _auth=Depends(require_api_key)):
    if not WORKFLOW_FILE.is_file():
        raise HTTPException(status_code=500, detail=f"No se encontró el workflow: {WORKFLOW_FILE}")
    try:
        graph = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
        if body.reference_image:
            image_node = next((node for node in graph.get("nodes", []) if node.get("type") == "LoadImage"), None)
            if image_node is None:
                raise ValueError("El workflow no contiene el nodo LoadImage.")
            image_node["mode"] = 0
            image_node["widgets_values"][0] = body.reference_image
        workflow = to_api_prompt(graph, body.prompt)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"Workflow Wan 2.2 inválido: {exc}") from exc
    client_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                COMFYUI_URL + "/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ComfyUI rechazó el trabajo: {exc}") from exc
    return {"job_id": result.get("prompt_id"), "status": "queued", "scene_index": body.scene_index}


@app.get("/api/jobs/{prompt_id}")
async def job_status(prompt_id: str, _auth=Depends(require_api_key)):
    response = await comfy_get("/history/" + prompt_id)
    history = response.json().get(prompt_id, {})
    if not history:
        return {"job_id": prompt_id, "status": "processing"}
    outputs = history.get("outputs", {})
    for node_output in outputs.values():
        for key in ("videos", "gifs"):
            for item in node_output.get(key, []):
                filename = item.get("filename")
                if filename:
                    return {"job_id": prompt_id, "status": "completed", "video_url": f"/api/jobs/{prompt_id}/video?token={video_signature(prompt_id)}"}
    status = history.get("status", {})
    if status.get("status_str") == "error":
        return {"job_id": prompt_id, "status": "failed", "error": "ComfyUI no pudo completar el workflow. Revisa los logs del servidor."}
    return {"job_id": prompt_id, "status": "processing"}



@app.post("/api/assemble")
async def assemble_video(body: AssembleRequest, _auth=Depends(require_api_key)):
    """Download completed ComfyUI clips and concatenate them into one MP4."""
    if shutil.which("ffmpeg") is None:
        raise HTTPException(status_code=503, detail="FFmpeg no está instalado en el servidor BETANIA.")
    temp_dir = Path(tempfile.mkdtemp(prefix="betania-"))
    try:
        clip_paths = []
        async with httpx.AsyncClient(timeout=180) as client:
            for index, prompt_id in enumerate(body.job_ids, start=1):
                if not re.fullmatch(r"[a-fA-F0-9-]{16,64}", prompt_id):
                    raise HTTPException(status_code=400, detail="Identificador de trabajo inválido.")
                response = await client.get(COMFYUI_URL + "/history/" + prompt_id)
                response.raise_for_status()
                history = response.json().get(prompt_id, {})
                video_meta = None
                for node_output in history.get("outputs", {}).values():
                    for key in ("videos", "gifs"):
                        if node_output.get(key):
                            video_meta = node_output[key][0]
                            break
                    if video_meta:
                        break
                if not video_meta:
                    raise HTTPException(status_code=409, detail=f"La escena {index} aún no tiene video terminado.")
                query = urlencode({
                    "filename": video_meta["filename"],
                    "subfolder": video_meta.get("subfolder", ""),
                    "type": video_meta.get("type", "output"),
                })
                video_response = await client.get(COMFYUI_URL + "/view?" + query)
                video_response.raise_for_status()
                clip_path = temp_dir / f"clip_{index:03d}.mp4"
                clip_path.write_bytes(video_response.content)
                clip_paths.append(clip_path)
        concat_file = temp_dir / "clips.txt"
        concat_file.write_text("".join(f"file '{path.name}'\\n" for path in clip_paths), encoding="utf-8")
        output_path = temp_dir / "BETANIA_pelicula_final.mp4"
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart", str(output_path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0 or not output_path.exists():
            raise HTTPException(status_code=500, detail="FFmpeg no pudo unir los clips: " + result.stderr[-1200:])
        return FileResponse(output_path, media_type="video/mp4", filename="BETANIA_pelicula_final.mp4", background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True))
    except HTTPException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except (httpx.HTTPError, OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=502, detail=f"No se pudo montar el video final: {exc}") from exc


@app.get("/api/jobs/{prompt_id}/video")
async def job_video(prompt_id: str, token: str):
    if not hmac.compare_digest(token, video_signature(prompt_id)):
        raise HTTPException(status_code=401, detail="Enlace de video inválido.")
    response = await comfy_get("/history/" + prompt_id)
    history = response.json().get(prompt_id, {})
    for node_output in history.get("outputs", {}).values():
        for key in ("videos", "gifs"):
            for item in node_output.get(key, []):
                filename = item.get("filename")
                if filename:
                    query = urlencode({
                        "filename": filename,
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                    })
                    video = await comfy_get("/view?" + query)
                    media_type = "video/mp4" if filename.lower().endswith(".mp4") else "application/octet-stream"
                    return Response(content=video.content, media_type=media_type, headers={"Cache-Control": "no-store"})
    raise HTTPException(status_code=404, detail="El video todavía no está disponible.")
