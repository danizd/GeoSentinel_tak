# ADR 0002 — Fase del canal CoT: humo en 8087 claro, producción en 8089 TLS

- **Estado:** Aceptado (2026-08)
- **Contexto:** WinTAK y el simulador se conectan al canal CoT de FTS. El spec original planteaba 8087 en texto claro con allowlist por IP en Oracle Cloud; la IP del cliente es dinámica, por lo que la allowlist es frágil y el canal claro queda expuesto a Internet.
- **Decisión:** Fasear el canal:
  - **Fase humo:** 8087 en texto claro, restringido en Oracle Security List, solo para validar la conectividad de extremo a extremo (WinTAK y simulador ven los 4 helicópteros).
  - **Fase producción:** 8089 CoT-TLS con certificados de cliente generados por FTS; WinTAK se enrola vía data package de configuración que incluye los certificados; 8087 se cierra en Oracle Security List una vez validada la fase humo.
- **Consecuencias:**
  - El entregable de WinTAK documenta ambas conexiones (humo en 8087, producción en 8089 con enrolamiento por data package).
  - 8087 se cierra en Oracle Security List tras la validación; 8089 queda como único canal CoT expuesto.
  - La allowlist por IP deja de ser el mecanismo principal de seguridad; la autenticación pasa a los certificados de cliente.
- **Alternativas descartadas:** VPN dedicada (WireGuard/Tailscale) como único acceso CoT — añade un componente extra a una infraestructura ya con NPM y dominio propio; 8087 claro permanente — expone telemetría en claro a Internet.
