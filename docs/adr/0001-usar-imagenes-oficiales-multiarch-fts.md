# ADR 0001 — Usar las imágenes oficiales multi-arch de FTS en vez de un build propio

- **Estado:** Aceptado (2026-08)
- **Contexto:** El despliegue va sobre Oracle Cloud Free Tier ARM64 (Ampere A1). El documento original de especificaciones proponía construir una imagen propia desde `python:3.11-slim` con FreeTAKServer 2.2.1 y la UI en el mismo contenedor, por temor a un "fallo de manifiesto" de la imagen oficial en ARM64.
- **Verificación:** La documentación oficial de Docker de FTS confirma que la imagen `ghcr.io/freetakteam/freetakserver` se compila por cross-compile para `linux/amd64`, `linux/arm64` y `linux/arm/v7`, y que la UI es una imagen separada (`ghcr.io/freetakteam/ui`). El riesgo de manifiesto que motivaba el build propio está desactualizado.
- **Decisión:** Usar las imágenes oficiales multi-arch de GHCR en dos servicios separados (core + UI), pinneadas por digest, con un build propio documentado solo como plan B si GHCR fuera inalcanzable desde Oracle.
- **Consecuencias:**
  - No se compilan dependencias nativas en ARM (el punto débil del build propio).
  - La UI deja de compartir proceso con el core: se elimina el patrón de dos procesos en un contenedor y el bug latente de `wait -n` bajo dash.
  - Queda documentado el riesgo EOL: FTS 2.2.1 (mayo 2024) es la última release y el proyecto lleva más de un año sin publicar; se pinnea por digest.
- **Alternativas descartadas:** build propio multi-proceso (fragilidad del supervisor, mantenimiento de un Dockerfile ajeno al upstream), cambio a OpenTAKServer (reabriría la decisión base del proyecto).
