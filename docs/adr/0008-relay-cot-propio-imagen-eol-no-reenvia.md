# ADR 0008 — Relay CoT propio: la imagen EOL de FTS 2.2.1 no reenvía CoT a los clientes

- **Estado:** Aceptado (2026-08)
- **Contexto:** Tras validar la fase humo en campo, WinTAK conecta al servidor
  (icono **verde** en `tcp://fts.movilab.es:8087/`) pero **no recibe ningún
  marcador**. El simulador envía telemetría correctamente (`RESCUE-01..04
  LAT=... LON=...` cada segundo) y el core la **ingiere** (log `executing %s
  a-f-A-C-H`), pero un segundo cliente TCP en 8087 recibe **NADA** y un evento
  CoT manual bien formado tampoco se reenvía (`recibido por listener: NADA`).

- **Causa raíz (confirmada en el código y en la imagen):**
  1. En FTS 2.2.1 el reenvío a clientes pasa **solo** por
     `broadcast_component_responses` (`tcp_cot_service_main.py`), que lee las
     respuestas del **routing proxy de digitalpy** (`/routing/response/`).
  2. En el arranque, **todos** los componentes digitalpy fallan al registrarse:
     `failed to register component: ... No module named 'Catalog'` (zmanager,
     health, IAM, persistence, ...) más archivos rotos en la propia imagen
     (`cot_management_facade.py` con tabs/espacios; `network` con `Facade` sin
     definir).
  3. El paquete `Catalog` (la "ASoT" del modelo WCMF) **no está publicado en
     PyPI** (`pypi.org/pypi/Catalog` → 404), no está en el wheel de digitalpy
     0.3.13.7 ni en el de **0.3.16** (ambos importan `from Catalog...`), y no
     está en los repos de FreeTAKTeam. El propio wheel oficial está roto.
  4. Consecuencia: la respuesta de conexión (`Sender: IAMUsersController,
     Action: connection`) produce `None` → `a bytes-like object is required,
     not 'NoneType'` → los clientes **nunca se registran** en la lista de
     reenvío → no reciben nada. Es un fallo de la imagen upstream, no de
     configuración (aparece igual en foros de ATAK con la misma traza).

- **Decisión:**
  - Añadir un servicio **`cot-relay`** propio (~90 líneas de Python, stdlib
    únicamente): un hub CoT TCP que acepta clientes, corta el stream por el
    delimitador `</event>` y **reenvía cada evento a todos los clientes
    conectados** — exactamente el comportamiento de un servidor CoT TAK.
  - El relay ocupa el puerto publicado `8087:8087` que antes publicaba el
    core; FTS sigue corriendo para UI/API/DataPackage (que sí funcionan) y sus
    puertos CoT quedan internos y sin uso.
  - El simulador apunta a `cot-relay` (antes `freetakserver`) por la red
    Docker. **WinTAK no cambia nada**: mismo host y puerto, ahora servidos por
    el relay.
  - No se invierte más tiempo en parchear la imagen EOL: reparar digitalpy
    exigiría reconstruir el paquete `Catalog` inexistente y arreglar archivos
    rotos dentro de un contenedor que se recrea en cada `up` (fragilidad
    permanente y dependencia de paquetes no publicados).
- **Verificación (fase humo):**
  - `docker compose logs -f cot-relay` → líneas `cliente conectado` para el
    simulador y WinTAK, y `evento #N RESCUE-0X ... -> broadcast a N cliente(s)`.
  - WinTAK (conexión verde existente o reconectada) muestra los 4 `RESCUE-0N`
    sobre Chamoli (30.484, 79.732).
- **Consecuencias:**
  - El core de FTS deja de ser el router CoT del escenario; es un
    back-end de UI/API/DP. El relay es el punto único del canal CoT.
  - Fase producción (8089 TLS, ADR 0002): el relay deberá ganar un listener
    TLS con los certificados de cliente de FTS (o CA propia importada en
    WinTAK) y el DataPackage de la UI deberá apuntar al relay. Trabajo
    pendiente, no bloqueado por este ADR.
  - El ruido de escáneres en el log del core (que ya no publica 8087/8089)
    desaparece de la ruta pública; el relay lo recibe y lo reenvía igualmente
    (inofensivo), o se mitiga restringiendo 8087 a la IP de los clientes.
- **Alternativas descartadas:**
  - Parchear la imagen (instalar `Catalog`, arreglar archivos rotos): el
    paquete no existe publicado; arreglo no reproducible ni mantenible.
  - Cambiar de imagen FTS (`update_to_digitalpy_0_3_14`, `latest`, `master`):
    el pyproject de master sigue fijando `digitalpy=0.3.13.7` y digitalpy
    0.3.16 sigue importando `Catalog`; el bug es upstream y no tiene fix
    publicado. Riesgo alto de reconfiguración sin solución garantizada.
  - Usar la UI como canal: no aplica; el canal CoT es TCP y la UI es HTTP.
