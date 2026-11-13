# Backend de BETANIA (Wan 2.2 / ComfyUI)

Este directorio define el contrato de API entre la página BETANIA y un servidor GPU. La página estática de GitHub Pages **no ejecuta** modelos de video ni incluye GPU.

## Contrato esperado

- `GET /health` devuelve JSON, por ejemplo `{"status":"ok","engine":"ComfyUI + Wan 2.2"}`.
- `POST /api/jobs` recibe `{"prompt":"...","scene_index":1,"title":"..."}` y devuelve un identificador de trabajo. Puede devolver `video_url` cuando el clip ya esté listo.
- El servidor debe habilitar CORS para el dominio publicado de BETANIA.

## Motor recomendado

Usar ComfyUI con el workflow oficial de Wan 2.2 TI2V-5B. El workflow debe estar instalado en el servidor y sus nodos/entradas deben mapear el prompt recibido. El adaptador debe crear el trabajo en la API de ComfyUI, consultar su historial hasta que termine y publicar el MP4 en una URL accesible.

## Estado

La interfaz y el contrato HTTP están preparados. No se incluye una dirección de GPU, claves privadas, pesos del modelo ni un workflow ComfyUI inventado. Por tanto, la generación real permanece desactivada hasta desplegar y probar ese servidor.
