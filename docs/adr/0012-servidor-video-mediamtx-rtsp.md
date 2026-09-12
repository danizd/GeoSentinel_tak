# ADR 0012 — MediaMTX como servidor de vídeo (el vídeo no viaja por CoT)

- **Estado:** Aceptado (2026-09)
- **Contexto:** El operador quiere ver en WinTAK el directo de la cámara de su
  móvil Android (y, como alternativa, el de la webcam del PC). El canal CoT
  **no** sirve para esto: CoT es XML con posición y admite a lo sumo un
  *puntero* al stream (`<__video url="…">`), nunca los fotogramas. El vídeo
  necesita su propio servidor de medios y su propio puerto.
  El cliente TAK no publica por sí solo: ATAK-CIV **reproduce** streams, y para
  emitir la cámara hace falta el plugin **TAK ICU** (TAK Product Center), que
  emite **RTSP** — no RTMP, no RTSPS (tabla de protocolos de TAK ICU; su
  opción "Wowza Server" se configura con IP y **puerto 8554**, que es RTSP).
- **Decisión:**
  - Añadir el servicio **`mediamtx`** (`bluenviron/mediamtx:1.21.0`, imagen
    **multi-arch**: amd64/arm64/arm, nativa en ARM64 sin qemu, ADR 0007) al
    `docker-compose.yml`, publicando **8554/tcp** (RTSP: publicar y ver) y
    **8888/tcp** (HLS, solo para comprobar en el navegador). Tag fijo en vez de
    `latest`, misma política que el resto (ADR 0005).
  - **Sin perfil** (arranca con `docker compose up -d`, como `cot-relay`,
    `deepstate` y `adsb`): un RTSP ocioso no consume nada y el móvil debe poder
    publicar en cuanto el proyecto está arriba. El perfil `sim` del simulador
    (ADR 0004) existe para no inundar el mapa con datos ficticios, no por ser
    opcional.
  - **Configuración versionada** en `mediamtx.yml` (raíz del repo, montada
    `:ro` en `/mediamtx.yml`): autenticación obligatoria (`authInternalUsers`
    con acciones publish/read/playback) y `paths: all_others:` para que
    cualquier alias (`MOVILGALICIA`, `webcam`, `demo`…) se cree al publicar.
  - **Las credenciales no van en el fichero**: MediaMTX permite sobrescribir
    por posición los parámetros de una lista desde el entorno, así que el
    compose define `MTX_AUTHINTERNALUSERS_0_USER=takvideo` y
    `MTX_AUTHINTERNALUSERS_0_PASS=${MEDIAMTX_PASSWORD:?…}`, con la contraseña
    en `.env` (nunca en el repo). Los valores de `mediamtx.yml` son solo el
    respaldo de arranque: siguen exigiendo credenciales, **nunca** dejan el
    8554 abierto.
  - La interpolación usa la forma que **aborta** si falta la variable
    (`${VAR:?mensaje}`): es preferible un error explícito de `docker compose` a
    un servidor de vídeo con la contraseña en blanco publicado a Internet.
  - El vídeo se queda **fuera de NPM**: es RTSP (socket TCP puro), no HTTP; el
    8554 se publica directamente en Oracle Security List.
- **Verificación:**
  - `bluenviron/mediamtx:1.21.0` consultado en el registro de Docker Hub:
    publica las arquitecturas `amd64`, `arm64` y `arm` (por eso este servicio
    no necesita el `platform: linux/amd64` ni el qemu del core y la UI).
  - `docker compose config` con `MEDIAMTX_PASSWORD` definida → **válido**; sin
    ella → error explícito `required variable MEDIAMTX_PASSWORD is missing a
    value`, sin arrancar nada. El servicio renderizado monta `mediamtx.yml`
    (`read_only: true`) en `/mediamtx.yml` y publica 8554 y 8888.
  - `mediamtx.yml` se contrastó con el fichero de configuración oficial de la
    **v1.21.0** (`mediamtx.yml` del repo upstream): `paths: all_others:` sin
    valor es exactamente la forma que trae de fábrica, y la estructura de
    `authInternalUsers` (`user`/`pass`/`ips`/`permissions`) coincide campo a
    campo con la documentada.
  - Mecanismo de entorno: la documentación de MediaMTX describe literalmente
    este caso de uso —«particularmente útil si quieres usar los usuarios
    internos pero definir las credenciales por variables de entorno:
    `MTX_AUTHINTERNALUSERS_0_USER`, `MTX_AUTHINTERNALUSERS_0_PASS`»— porque los
    parámetros de una lista se sobrescriben usando su posición como clave
    adicional.
  - **Pendiente de comprobar en el servidor** (requiere publicar de verdad):
    que el móvil con TAK ICU publica en 8554 con el alias como ruta y que
    WinTAK lo reproduce con *Reliable P2P Connection* activado. El paso a paso
    está en el README ("Vídeo en directo").
- **Consecuencias:**
  - Un canal de vídeo más en la demo, desacoplado del CoT: si MediaMTX se cae,
    el mapa y los feeders siguen intactos (y al contrario).
  - Nuevo puerto publicado (8554) y una credencial más que gestionar en `.env`;
    a cambio, publicar o ver el vídeo exige autenticación desde el primer día
    (§6 de `especificaciones.md` ya documenta la lección de las credenciales
    por defecto).
  - El vídeo **no** aparece como icono de cámara en el mapa: eso exigiría un
    evento CoT `b-i-v` que nada del proyecto emite. TAK ICU puede anotar el
    stream con KLV, lo que sí lo sitúa en el mapa; queda como prueba pendiente.
  - El 8554 admite también RTMP (1935) y WebRTC (8889) si en el futuro se
    publica desde otras apps (Larix, navegador); hoy no se publican esos
    puertos para no ampliar la superficie.
- **Alternativas descartadas:**
  - **Anunciar el vídeo por CoT** (`<__video>`): no transporta fotogramas; sirve
    para el icono del mapa, no para ver el vídeo, y el formato varía entre
    versiones de TAK (más fiable capturar el XML del propio cliente que
    copiarlo de un ejemplo).
  - **Servicio gestionado / cloud de vídeo** (Cloudflare Stream, api.video…):
    ninguno entrega una URL RTSP nativa a ATAK/WinTAK; seguiría haciendo falta
    un puente RTSP, así que no quitan el MediaMTX, solo añaden dependencia.
  - **Proxear el vídeo por NPM (443)**: NPM solo habla HTTP; para pasar por 443
    habría que servir HLS/WebRTC, que los clientes TAK nativos no reproducen
    como fuente de vídeo.
  - **Configuración en `data/mediamtx/mediamtx.yml`** (como los certificados de
    `data/certs/`): reproduce el patrón de los certs, pero obliga a un fichero
    manual extra y deja la configuración sin versionar. Se prefirió
    `mediamtx.yml` en el repo + contraseña en `.env`.
  - **Perfil `video`** (arrancar solo cuando se quiera): el vídeo es una función
    de la demo, no un generador de datos ficticios; un perfil solo añadiría la
    trampa de "arranco todo y el móvil publica contra un servidor ausente".
  - **KLV/CoT para el icono en el mapa**: pospuesto, no descartado (ver
    consecuencias).
