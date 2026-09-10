# ADR 0005 — Pin por digest de imágenes y estrategia ante el EOL de FTS

- **Estado:** Aceptado (2026-08)
- **Contexto:** FTS 2.2.1 (mayo 2024) es la última release publicada; el proyecto lleva más de un año sin versiones nuevas. El despliegue es "listo para producción" y debe ser reproducible.
- **Decisión:** Fijar las imágenes oficiales (`ghcr.io/freetakteam/freetakserver`, `ghcr.io/freetakteam/ui`) **por digest SHA** en el compose, no por tag. Las actualizaciones son manuales y programadas (`docker compose pull && docker compose up -d` tras leer el changelog), nunca automáticas (sin Watchtower). El riesgo EOL queda documentado; no se reabre la elección de servidor.
- **Consecuencias:** el despliegue es bit-a-bit reproducible y una actualización no puede colar cambios sin decisión consciente; el coste es revisar manualmente si el upstream publica.
- **Alternativas descartadas:** pin por tag `2.2.1` (mutable), Watchtower (actualiza sin decisión), migrar a OpenTAKServer (reabriría la decisión base del proyecto).
