# BETANIA — backend de video Wan 2.2

## Qué está listo

- Workflow oficial de ComfyUI para Wan 2.2 TI2V-5B guardado en `wan2_2_5b_t2v.json`.
- Conversión del grafo de ComfyUI a formato API.
- Envío de trabajos a `POST /prompt`.
- Carga opcional de imagen de referencia con `POST /api/reference` y modo imagen-a-video del workflow.
- Seguimiento de trabajos con `GET /history/{prompt_id}`.
- Entrega de MP4 a BETANIA mediante un endpoint proxy, sin exponer la dirección interna de ComfyUI al navegador.
- `GET /health` para comprobar si ComfyUI está disponible.

## Requisitos del servidor GPU

1. Un servidor Linux con GPU NVIDIA y controladores/CUDA compatibles con la versión de PyTorch y ComfyUI instalada.
2. ComfyUI actualizado y los tres modelos del workflow oficial:
   - `wan2.2_ti2v_5B_fp16.safetensors` en `ComfyUI/models/diffusion_models/`
   - `umt5_xxl_fp8_e4m3fn_scaled.safetensors` en `ComfyUI/models/text_encoders/`
   - `wan2.2_vae.safetensors` en `ComfyUI/models/vae/`
3. Iniciar ComfyUI escuchando en la interfaz de red del servidor, por ejemplo `python main.py --listen 0.0.0.0 --port 8188`.
4. Instalar esta API en el mismo servidor o en una red que pueda alcanzar ComfyUI.

La documentación de ComfyUI indica que el workflow Wan 2.2 TI2V-5B es híbrido texto/imagen a video y puede funcionar con offloading nativo en equipos con 8 GB de VRAM, aunque la velocidad y resolución dependen del hardware. Guía: https://docs.comfy.org/tutorials/video/wan/wan2_2

## Ejecutar la API

Desde este directorio:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export COMFYUI_URL=http://127.0.0.1:8188
export BETANIA_ORIGIN=https://TU-USUARIO.github.io/TU-REPOSITORIO
uvicorn main:app --host 0.0.0.0 --port 8000
```

En BETANIA, pega la URL pública HTTPS de esta API y pulsa **Guardar conexión** y **Probar servidor**. La API debe publicarse detrás de HTTPS; el navegador bloqueará llamadas HTTP desde GitHub Pages.

## Endpoints

- `GET /health`
- `POST /api/reference` multipart con campo `file` (PNG/JPG/WEBP, máximo 10 MB).
- `POST /api/jobs` JSON: `{"prompt":"...","scene_index":1,"title":"Rut y Noemí","reference_image":"nombre.png"}`; `reference_image` es opcional.
- `GET /api/jobs/{prompt_id}`
- `GET /api/jobs/{prompt_id}/video`

## Ejecutar la API en Docker

Si ComfyUI está instalado en el mismo servidor físico y escucha en el puerto 8188:

```bash
docker build -t betania-api .
docker run --add-host=host.docker.internal:host-gateway -p 8000:8000 \
  -e COMFYUI_URL=http://host.docker.internal:8188 \
  -e BETANIA_ORIGIN=https://TU-USUARIO.github.io/TU-REPOSITORIO \
  betania-api
```

ComfyUI debe escuchar en `0.0.0.0:8188` para que el contenedor pueda alcanzarlo. No publiques el puerto 8188 abierto a internet; expón solo la API HTTPS protegida por un proxy inverso.

## Importante

El repositorio incluye el código, el workflow y la interfaz. No incluye una GPU remota, pesos del modelo (son archivos de varios GB), ni una URL pública de servidor. Por eso el render real solo queda activo después de desplegar esos componentes. No se ha simulado ninguna generación.
