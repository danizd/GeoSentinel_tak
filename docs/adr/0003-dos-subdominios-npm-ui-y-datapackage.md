# ADR 0003 — Dos subdominios en NPM: UI y DataPackage

- **Estado:** Aceptado (2026-08), revisado (2026-09)
- **Contexto:** Con NPM delante y FTS en contenedores separados, hay dos puntos que deben ser alcanzables desde fuera: la UI de administración (5000) y el servicio DataPackage (8080), del que WinTAK descarga data packages (configuración, certificados, mapas). La API REST del core (19023) se consume internamente por la red Docker y no necesita proxy host propio. El spec original usaba un solo dominio hacia la UI y exponía 8080 en claro al host.
- **Decisión:** Dos proxy hosts en NPM, todos con certificado Let's Encrypt:
  - `fts.<dominio>` → `freetakserver-ui:5000` (UI de administración)
  - `dp.<dominio>` → `freetakserver:8080` (servicio DataPackage)
  - La UI apunta `FTS_IP`/`FTS_API_PORT`/`FTS_API_PROTO` a `freetakserver:19023/http` (hostname interno de la red Docker): la UI hace sus llamadas server-side al core por la red interna sin salir del host.
  - `FTS_DP_ADDRESS` / `FTS_USER_ADDRESS` apuntan a `dp.<dominio>` para que los enlaces de data packages que genera FTS ya salgan con HTTPS.
  - 8080, 8443, 19023 y 5000 no se publican al host; NPM y FTS comparten la red Docker externa `proxy_network`.
- **Revisión (2026-09):** originalmente se incluía un tercer proxy host `api.<dominio>` → `freetakserver:19023` para que el dashboard de la UI abriera su WebSocket desde el navegador. Se verificó que la UI funciona correctamente con el hostname interno `freetakserver:19023` por la red Docker, por lo que el proxy host API es innecesario.
- **Consecuencias:** WinTAK descarga data packages por TLS sin puertos extra abiertos en Oracle; hay dos certificados que NPM renueva automáticamente; los clientes solo necesitan dominios, no IPs. Menor superficie de ataque al eliminar un proxy host y un subdominio.
- **Alternativas descartadas:** un solo dominio + 8080 publicado en claro (superficie extra y DP sin TLS); acceso al DP solo por IP (sin TLS y frágil ante cambios de IP); tres proxy hosts con `api.<dominio>` (innecesario: la UI consume la API internamente).
