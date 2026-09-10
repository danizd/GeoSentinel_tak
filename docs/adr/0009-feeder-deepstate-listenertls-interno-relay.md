# ADR 0009 — Feeder deepstatemap.live: listener TLS interno en el relay

- **Estado:** Aceptado (2026-09)
- **Contexto:** Se quiere integrar en el despliegue el feeder
  [tak-feeder-deepstate](https://github.com/sgofferj/tak-feeder-deepstate)
  (GPL-3.0, uso autorizado por el equipo de deepstatemap.live), que convierte
  la última capa de unidades del conflicto de Ucrania (OSINT) a eventos CoT y
  los envía a un servidor TAK. El feeder upstream es Node.js y **solo habla
  `ssl://host:puerto`** con cert+key de cliente obligatorios (`checkFile`
  aborta si faltan), pero usa `rejectUnauthorized:false` (no valida la CA del
  servidor). En este despliegue el canal CoT lo sirve `cot-relay` (ADR 0008):
  el core de FTS 2.2.1 no reenvía CoT a los clientes, así que conectar el
  feeder al canal SSL del core no haría visibles sus eventos en WinTAK.
  Además, el puerto 8089 ya está reservado por ADR 0002 como canal CoT TLS de
  la fase de producción.
- **Decisión:**
  - Añadir a `cot-relay` un **listener TLS opcional** en 8089
    (`RELAY_TLS_CERT`/`RELAY_TLS_KEY`), servido por el mismo hub que el
    listener en claro: un evento entrante por cualquier listener se reenvía a
    **todos** los clientes. WinTAK (8087) y el simulador no cambian nada.
  - Añadir el servicio **`deepstate`** con la imagen oficial multi-arch
    `ghcr.io/sgofferj/tak-feeder-deepstate:latest` (ADR 0001: imagen oficial,
    no build propio; ADR 0007: multi-arch, sin qemu en ARM64), apuntando a
    `ssl://cot-relay:8089` por la red Docker.
  - Certificado **autofirmado** del relay generado en `data/certs/` (gitignored
    vía `data/`); los mismos ficheros sirven de cert/key de "cliente" del
    feeder, que no los envía porque el listener no pide cert de cliente y que
    de todos modos no valida la CA.
  - El puerto 8089 **no se publica al host**: es consumo interno del feeder
    hasta que la fase producción (ADR 0002) publique el canal TLS para WinTAK.
  - Si faltan los certs, el relay **no** aborta: sigue sirviendo 8087 y solo
    avisa por log de que el listener TLS está desactivado.
- **Verificación:**
  - `docker compose logs cot-relay` → `relay CoT TLS 0.0.0.0:8089 escuchando`.
  - `docker compose logs deepstate` → `Found /certs/server.pem` y
    `nameFull ...` en cada ciclo; sin `process.exit()` por error de conexión.
  - WinTAK (conexión 8087 ya existente) muestra los marcadores `a-h-G-U-*`
    al navegar a Ucrania, además de los `RESCUE-0N` de Chamoli.
- **Consecuencias:**
  - El canal CoT del despliegue gana un punto TLS interno que será el mismo
    punto de entrada de la fase producción de ADR 0002 (publicar 8089 y
    enrolar WinTAK por data package).
  - Conviven en el mismo mapa datos **reales** (deepstatemap.live, con
    atribución y licencia GPL-3.0 del feeder) y los **ficticios** del
    simulador; se distinguen por tipo 2525 y zona geográfica.
  - El `PULL_INTERVAL` mínimo real del feeder es 300 s (clamp en el código
    upstream), no los 60 s de su README.
- **Alternativas descartadas:**
  - Conectar el feeder al canal SSL del core de FTS (8089 del core): ADR 0008
    — el core no reenvía CoT a los clientes; los eventos quedarían ingeridos
    pero invisibles en WinTAK.
  - Parchear el feeder para hablar TCP claro y apuntarlo a 8087: fork del
    upstream con mantenimiento propio, rompe la imagen oficial y no aporta
    nada frente al listener TLS del relay (el feeder ya trae TLS y la fase
    producción lo necesita igualmente).