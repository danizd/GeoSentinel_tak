# ADR 0014 — Lectura anónima del vídeo (WinTAK no envía credenciales en RTSP)

- **Estado:** Aceptado (2026-09)
- **Contexto:** El operador ve la cámara del móvil en VLC (`rtsp://takvideo:…@fts.movilab.es:8554/MOVILGALICIA`)
  pero no en WinTAK. El editor de *Video Alias* de WinTAK 5.8 no expone campos de
  usuario/contraseña para RTSP, y pegar la URL con credenciales en el campo
  **Address** dispara *Invalid IP … must be multicast or blank for unicast*: el
  cliente valida ese campo como dirección IP/host y rechaza el `usuario:contraseña@`
  (VLC sí los admite, de ahí que en VLC funcionara). La lectura en MediaMTX exigía
  autenticación desde el ADR 0012 (`takvideo` con publish/read/playback), así que
  WinTAK no tenía forma de ver el feed.
- **Decisión:**
  - **Leer sin credenciales; publicar sigue autenticado.** En `mediamtx.yml` el
    índice 0 de `authInternalUsers` se mantiene intacto (el compose sobrescribe por
    posición con `MTX_AUTHINTERNALUSERS_0_USER/_PASS`, ADR 0012) y se añade en el
    índice 1 un usuario `user: any` (`pass` vacío, que en ese caso no se usa) con
    **solo** `action: read`. MediaMTX **fusiona los permisos de todos los usuarios
    que coinciden** — el propio fichero de fábrica lo demuestra con dos entradas
    `any` (una para publish/read/playback global y otra localhost para
    api/metrics/pprof) —, así que cualquiera puede leer y publicar sigue exigiendo
    `takvideo` + `MEDIAMTX_PASSWORD`.
  - **La ruta del stream pasa a ser el secreto del feed** (el modelo de ArgusTAK:
    nadie teclea credenciales porque el path es lo que protege). El 8554 se publica
    a Internet (ADR 0012); a cambio de poder ver el vídeo desde WinTAK sin
    credenciales, se asume que una ruta adivinable expone el directo mientras haya
    publicador. Mitigación: rutas difíciles de adivinar y rotarlas si se filtran
    (cambiar `VIDEO_RTSP_URL` en `.env` y el *Stream Path* de la app/FFmpeg).
  - El puntero CoT (**ADR 0013**) se queda sin credenciales, como estaba: ahora
    encaja, porque leer ya no las exige y el CoT va en claro por el 8087.
- **Verificación:**
  - `mediamtx.yml` parsea y `docker compose config` sigue siendo válido con las
    variables definidas; el render del servicio conserva
    `MTX_AUTHINTERNALUSERS_0_USER/_PASS` apuntando al índice 0.
  - Durante el incidente del 14-SEP-2026, el log de MediaMTX probó la cadena
    contraria: `no stream is available on path 'MOVILGALICIA'` (sin publicador) y,
    publicando el móvil, `stream is available and online, 2 tracks (H264, MPEG-4
    Audio)` + `is publishing to path 'MOVILGALICIA'`.
  - **Pendiente de comprobar en el servidor:** que WinTAK reproduce con el Address a
    secas (`fts.movilab.es` + 8554 + `MOVILGALICIA`) y el log no muestra
    `authentication failed` al leer.
- **Consecuencias:**
  - WinTAK/ATAK ven el feed con solo dirección + puerto + ruta; los pasos 2A/2B del
    README no cambian (publicar sigue autenticado).
  - Cualquiera en Internet con la ruta puede ver el vídeo mientras alguien publique;
    si la ruta se filtra, se rota como se rota una contraseña.
  - El HLS del 8888 también queda de lectura abierta, coherente con la decisión.
- **Alternativas descartadas:**
  - **Buscar credenciales en la UI de WinTAK:** el editor de Video Alias de WinTAK
    5.8 que usa el operador no expone usuario/contraseña para RTSP, y el campo
    Address rechaza la URL con credenciales.
  - **Credenciales en el puntero CoT** (`ConnectionEntry` con username/password, lo
    que hace TAK ICU con *Send Stream Connection Details*): la contraseña viajaría
    en claro por el relay (8087) y llegaría a todos los clientes conectados; se
    descarta por la misma razón que el ADR 0013 omitió las credenciales.
  - **Restringir la lectura anónima por IP** (`ips:` en el usuario `any`): la IP del
    operador es dinámica, la misma fragilidad que la allowlist descartada en el
    ADR 0002.