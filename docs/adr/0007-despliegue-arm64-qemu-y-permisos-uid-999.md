# ADR 0007 — Despliegue real en ARM64: qemu para amd64, UID 999 y bind de la UI

- **Estado:** Aceptado (2026-08)
- **Contexto:** El primer `docker compose up` real en Oracle ARM64 (host `aarch64`) falló en cascada. La documentación previa (ADR 0001) asumía que las imágenes eran multi-arch con soporte nativo arm64, y eso no se sostuvo en la práctica para los tags elegidos. Errores vistos en campo, en orden:
  1. `exec /home/freetak/docker-run.sh: exec format error` en **ambos** contenedores (exit 255 en bucle).
  2. `PermissionError: [Errno 13]` en `/opt/fts/FTSConfig.yaml` (core).
  3. `FileNotFoundError: /opt/fts/FTSConfig.yaml` (UI): la UI lee la config generada por el core pero no tenía montado ese volumen.
  4. `OSError: [Errno 99] Cannot assign requested address` en `eventlet.listen` (UI): `FTS_UI_EXPOSED_IP` se usó como dirección de **bind** con un nombre de dominio.
- **Verificación:**
  - `docker run --rm --entrypoint id ghcr.io/freetakteam/freetakserver:v2_2_1` → `uid=999(freetak) gid=999(freetak)`. El Dockerfile actual hace `groupadd -r freetak && useradd -m -r -g freetak freetak`: `-r` = cuenta de sistema → **UID 999, no 1000** (el antiguo repo archivado usaba 1000; la imagen actual no).
  - El Dockerfile de la UI también usa `useradd --system ... freetak` → mismo UID 999.
  - En el `config.py` de la UI: `APPIP = environ.get('FTS_UI_EXPOSED_IP', ...)` y `eventlet.listen((app_config.APPIP, app_config.APPPort))`: **`FTS_UI_EXPOSED_IP` es la dirección de escucha/bind**, no el dominio público.
- **Decisión:**
  - Los tags `freetakserver:v2_2_1` y `ui:master` son **amd64-only** (ADR 0006). En ARM64 se ejecutan bajo **emulación qemu/binfmt**, que hay que registrar explícitamente en el host: `docker run --privileged --rm tonistiigi/binfmt --install all`. El compose mantiene `platform: linux/amd64`; sin el registro de binfmt aparece el `exec format error`.
  - El bind mount `./data/core:/opt/fts` debe tener **ownership UID/GID 999** (`sudo chown -R 999:999 data/core`). Docker crea el directorio como root al primer arranque si no existe; si no se ajusta, el core muere con PermissionError.
  - La UI necesita **compartir** el directorio de datos del core: `./data/core:/opt/fts` **de escritura**. Lee `FTSConfig.yaml` (que genera el core) y además escribe su propia BD (`sqlite:////opt/fts/FTSServer-UI.db`, default del `config.py`). Sin el mount muere con FileNotFoundError; con el mount en `:ro` muere con `unable to open database file`.
  - El core debe **publicar los puertos CoT en el host** (`ports: 8087:8087` y `8089:8089`): CoT es TCP puro y NPM no lo proxea (ADR 0002/0003). Sin `ports` en el compose, WinTAK no tiene por dónde conectar.
  - `FTS_UI_EXPOSED_IP` debe ser **`0.0.0.0`** (bind en todas las interfaces del contenedor); el dominio público `fts.movilab.es` lo resuelve NPM. Con un dominio ahí, `eventlet.listen` falla con Errno 99.
- **Consecuencias:**
  - El arranque en ARM64 requiere dos pasos no documentados antes: registrar binfmt y ajustar permisos 999 del bind mount. Quedan documentados en el README (Quickstart) y en este ADR.
  - En un host amd64 nativo no hacen falta qemu ni `platform`; el compose sigue siendo válido igualmente.
  - La UI lee `/opt/fts/FTSConfig.yaml` que genera el core: la dependencia entre servicios es de datos (volumen), no solo de red.
- **Alternativas descartadas:** `chown 1000:1000` (UID equivocado, no resuelve), correr el core como root (`user: root` anularía el diseño no-root del Dockerfile y reabre el riesgo de privilegio), montar la UI con bind en `/home/freetak` (sombrearía el entrypoint `docker-run.sh`, documentado ya en el compose).
