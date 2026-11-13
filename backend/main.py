"""BETANIA API: puente seguro entre la web y ComfyUI/Wan 2.2 TI2V-5B."""
import json
import os
import secrets
import uuid
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
PUBLIC_ORIGIN = os.getenv("BETANIA_ORIGIN", "*")
WORKFLOW_FILE = Path(os.getenv("WAN_WORKFLOW_JSON", Path(__file__).with_name("wan2_2_5b_t2v.json")))
app = FastAPI(title="BETANIA Video API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[PUBLIC_ORIGIN] if PUBLIC_ORIGIN != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

class JobRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=12000)
    scene_index: int = Field(ge=1, le=100)
    title: str = Field(default="BETANIA", max_length=200)


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


@app.post("/api/jobs")
async def create_job(body: JobRequest):
    if not WORKFLOW_FILE.is_file():
        raise HTTPException(status_code=500, detail=f"No se encontró el workflow: {WORKFLOW_FILE}")
    try:
        graph = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
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
async def job_status(prompt_id: str):
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
                    return {"job_id": prompt_id, "status": "completed", "video_url": f"/api/jobs/{prompt_id}/video"}
    status = history.get("status", {})
    if status.get("status_str") == "error":
        return {"job_id": prompt_id, "status": "failed", "error": "ComfyUI no pudo completar el workflow. Revisa los logs del servidor."}
    return {"job_id": prompt_id, "status": "processing"}


@app.get("/api/jobs/{prompt_id}/video")
async def job_video(prompt_id: str):
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
