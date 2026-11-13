"""API mínima para BETANIA. Adaptador de despliegue; no ejecuta Wan sin ComfyUI configurado."""
import os
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

COMFYUI_URL = os.getenv("COMFYUI_URL", "").rstrip("/")
PUBLIC_ORIGIN = os.getenv("BETANIA_ORIGIN", "*")
app = FastAPI(title="BETANIA Video API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[PUBLIC_ORIGIN] if PUBLIC_ORIGIN != "*" else ["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

class JobRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=12000)
    scene_index: int = Field(ge=1, le=100)
    title: str = Field(default="BETANIA", max_length=200)

@app.get("/health")
async def health():
    return {"status": "ok", "engine": "ComfyUI + Wan 2.2" if COMFYUI_URL else "backend listo; falta configurar ComfyUI", "configured": bool(COMFYUI_URL)}

@app.post("/api/jobs")
async def create_job(body: JobRequest):
    if not COMFYUI_URL:
        raise HTTPException(status_code=503, detail="Configura COMFYUI_URL y un workflow Wan 2.2 antes de generar clips.")
    # No se envía un workflow ficticio: se requiere un JSON real exportado desde ComfyUI.
    workflow_path = os.getenv("WAN_WORKFLOW_JSON", "")
    if not workflow_path or not os.path.isfile(workflow_path):
        raise HTTPException(status_code=503, detail="Falta WAN_WORKFLOW_JSON: exporta el workflow API de Wan 2.2.")
    import json
    with open(workflow_path, "r", encoding="utf-8") as handle:
        workflow = json.load(handle)
    # Sustituye el marcador BETANIA_PROMPT en los nodos de texto del workflow.
    replaced = False
    for node in workflow.values():
        inputs = node.get("inputs", {}) if isinstance(node, dict) else {}
        for key, value in list(inputs.items()):
            if isinstance(value, str) and value == "BETANIA_PROMPT":
                inputs[key] = body.prompt
                replaced = True
    if not replaced:
        raise HTTPException(status_code=500, detail="El workflow debe contener BETANIA_PROMPT en el campo de texto del prompt.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(COMFYUI_URL + "/prompt", json={"prompt": workflow, "client_id": str(uuid.uuid4())})
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="ComfyUI rechazó el workflow: " + response.text[:500])
    data = response.json()
    return {"job_id": data.get("prompt_id"), "status": "queued", "message": "Trabajo enviado a ComfyUI; consulta el historial de ComfyUI para obtener el MP4."}

@app.get("/api/jobs/{prompt_id}")
async def job_status(prompt_id: str):
    if not COMFYUI_URL:
        raise HTTPException(status_code=503, detail="ComfyUI no está configurado.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(COMFYUI_URL + "/history/" + prompt_id)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="No se pudo consultar ComfyUI.")
    history = response.json().get(prompt_id, {})
    if not history:
        return {"job_id": prompt_id, "status": "processing"}
    outputs = history.get("outputs", {})
    for node in outputs.values():
        for key in ("videos", "gifs"):
            for item in node.get(key, []):
                filename = item.get("filename")
                if filename:
                    from urllib.parse import urlencode
                    query = urlencode({"filename": filename, "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")})
                    return {"job_id": prompt_id, "status": "completed", "video_url": COMFYUI_URL + "/view?" + query}
    status = history.get("status", {})
    if status.get("status_str") == "error":
        return {"job_id": prompt_id, "status": "failed", "error": "ComfyUI no pudo completar el workflow."}
    return {"job_id": prompt_id, "status": "processing"}
