# BETANIA — Generador cinematográfico bíblico

Aplicación independiente para planificar producciones bíblicas: historia, continuidad de personajes, imagen de referencia, escenas con prompts, narración y exportación/importación de proyectos JSON.

## Publicación

La interfaz es estática y se publica con GitHub Pages. La publicación usa la configuración de GitHub Pages ya habilitada en el repositorio.

## Generación real de video

La web no puede ejecutar un modelo de varios miles de millones de parámetros dentro de GitHub Pages. Para generar MP4 hace falta un servidor GPU con ComfyUI y Wan 2.2 TI2V-5B. El backend ya incluye el workflow oficial, conversión al formato API, carga opcional de imagen de referencia, cola de trabajos, seguimiento y entrega del MP4. Consulta [backend/README.md](backend/README.md) para el contrato y configuración del backend.

No se muestran clips falsos ni se afirma que el renderizado esté activo mientras el backend no esté conectado y probado.
