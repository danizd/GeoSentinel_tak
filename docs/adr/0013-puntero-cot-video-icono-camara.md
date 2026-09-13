# ADR 0013 — Puntero CoT del vídeo (el icono de cámara en el mapa)

- **Estado:** Aceptado (2026-09)
- **Contexto:** El ADR 0012 dejó abierto un hueco explícito: con MediaMTX ya se
  *ve* el vídeo en WinTAK, pero **no hay nada en el mapa** (ni icono, ni dónde
  pulsar). El canal CoT no transporta fotogramas, sí un *puntero*: un evento
  cuyo `<detail>` lleva `<__video>` con la URL del stream. Nada del proyecto lo
  emitía, y ese era el único trabajo funcional pendiente de la lista del
  ADR 0012 (`"quedará como prueba pendiente"`).
  Además el proyecto arrastraba una hipótesis sin verificar: el ADR 0012 llamó
  a ese evento `b-i-v` *por el catálogo de tipos CoT*, sin comprobar la
  estructura real del `<detail>`. El propio ADR avisaba: «el formato varía entre
  versiones de TAK (más fiable capturar el XML del propio cliente que copiarlo
  de un ejemplo)».
- **Decisión:**
  - **Script propio `video-pointer.py`** (solo librería estándar, como
    `cot-relay.py`, `simulator.py` y `adsb-feeder.py`): construye el evento y lo
    manda al relay por la red Docker interna (`cot-relay:8087`, ADR 0008). No
    hace falta ningún servicio nuevo de terceros: el puntero es texto CoT.
  - **Servicio `video-cot` en el compose**, sin perfil (arranca con
    `docker compose up -d`, como `mediamtx`): un puntero que no existe deja al
    operador con un directo que no puede pulsar en el mapa.
  - **Estructura del `<detail>` medida, no inventada** — la del plugin
    **TAK ICU**, cuyo hermano de código abierto **OpenTAK ICU** es de donde se
    copió (mismo código base):
    ```xml
    <detail>
      <contact callsign="MOVILGALICIA"/>
      <__video url="rtsp://host:8554/MOVILGALICIA" uid="geosentinel-video.movilgalicia">
        <ConnectionEntry address="host" alias="MOVILGALICIA" port="8554"
                         path="MOVILGALICIA" protocol="rtsp" bufferTime="-1"
                         roverPort="-1" ignoreEmbeddedKLV="false"
                         rtspReliable="1" networkTimeout="5000"/>
      </__video>
    </detail>
    ```
    `rtspReliable="1"` fuerza **RTSP sobre TCP**, que es lo que WinTAK llama
    *Reliable P2P Connection*: el ADR 0012 ya lo marcó como imprescindible con
    NAT o firewall por medio (nuestro caso), así que va en `1` por defecto (la
    variable `VIDEO_RTSP_RELIABLE` permite volver a UDP).
  - **Tipo del evento configurable** (`VIDEO_COT_TYPE`), por defecto **`b-i-v`**
    (*Bits/Imagery/Video*, el nombre que usan el ADR 0012 y esta decisión), con
    **`b-m-p-s-p-loc`** (*Sensor Point of Interest*) como alternativa
    documentada: es el tipo que **emiten TAK ICU y OpenTAK ICU** en el mismo
    evento que lleva el `__video`. Si en el servidor un tipo no pinta el icono,
    el cambio es una variable de entorno, no un `git revert`.
  - **`VIDEO_RTSP_URL` obligatoria en `.env`** (`${VAR:?mensaje}` en el
    compose, misma política que `MEDIAMTX_PASSWORD`): un icono de cámara que
    apunta a un servidor inventado es peor que un arranque que falla con un
    mensaje claro. Es el único costo de esta decisión para un despliegue ya en
    marcha: hay que añadir la línea (`.env.example` ya la trae).
  - **Las credenciales no se emiten**: el CoT va en claro por 8087 y lo recibe
    cada cliente conectado, así que la contraseña de MediaMTX **no** viaja en el
    evento. Si el URL trae `usuario:clave@`, el script las **descarta** del
    evento y avisa por consola. WinTAK pide usuario y contraseña la primera vez
    que se reproduce el feed (es lo que ya describe el README, paso 3).
  - **Posición del icono configurable** (`VIDEO_LAT`/`VIDEO_LON`/`VIDEO_HAE`),
    por defecto el centro del escenario de Chamoli para que la demo del vídeo
    caiga junto a los `RESCUE-0N`; el caso real es la posición del móvil que
    publica. Los `ce`/`le` se emiten enormes (9999999): la posición no viene de
    un GPS y no queremos que WinTAK dibuje un círculo de error.
  - **Refresco en vez de 1 Hz**: el puntero no se mueve. Se reemite cada
    `VIDEO_RESEND_SECONDS` (60 s) con un `stale` de `VIDEO_STALE_SECONDS`
    (300 s, margen 5× para tolerar deriva de reloj servidor/PC).
  - **UID determinista** (`geosentinel-video.<ruta>`, ADR 0004): reiniciar el
    servicio actualiza el mismo contacto en vez de acumular iconos fantasma.
- **Verificación:**
  - **Fuentes del formato** (no copiado de un blog):
    - `b-i-v` = *Bits/Imagery/Video* en la tabla de tipos CoT conocidos del
      proyecto de referencia [node-CoT](https://github.com/dfpc-coe/node-CoT).
    - La estructura `__video` + `ConnectionEntry` sale del código de
      [OpenTAK ICU](https://github.com/brian7704/OpenTAK_ICU)
      (`cot/__Video.java`, `cot/ConnectionEntry.java`, `cot/Detail.java`), el
      hermano abierto del TAK ICU que documenta el README; `Detail.java` anida
      exactamente `Contact` + `__Video` + `Device` + `Sensor` y
      `Camera2Service.startStream()` construye el evento con esos campos.
    - `b-m-p-s-p-loc` es el valor por defecto del atributo `type` en la clase
      `event` de ese mismo código (`cot/event.java`), es decir, el tipo con el
      que TAK ICU publica su `__video` real.
  - **Pruebas ejecutadas en el PC** (relay real en local, puerto 18087, sin
    Docker):
    - `python -m py_compile` de los cuatro scripts del repo: **OK**.
    - `DRY_RUN=true VIDEO_RTSP_URL=rtsp://198.51.100.7:8554/MOVILGALICIA` →
      evento que **parsea con `xml.etree`** (bien formado), `type="b-i-v"`,
      `uid="geosentinel-video.movilgalicia"`, `<__video url=… uid=…>` y
      `ConnectionEntry` con los 11 atributos esperados
      (`rtspReliable="1"` incluido).
    - **Extremo a extremo contra `cot-relay.py`**: 3 eventos enviados a 2 s,
      el relay registró `cliente conectado` + `evento #1..#3 MOVILGALICIA
      (819 B) … -> broadcast a 0 cliente(s)`. El relay reconoce el evento
      completo (cierra en `</event>`) y extrae el callsign del feed: el puntero
      llega y se reenvía como cualquier otro CoT.
    - Configuración incorrecta → **error explícito y `exit 2`**: sin
      `VIDEO_RTSP_URL`, con ruta que lleva espacios (la lección de TAK ICU del
      README: el alias es la ruta y falla con espacios) y con lat/lon fuera de
      rango.
    - URL con credenciales → el script avisa y **el evento sale sin ellas**
      (comprobado en el XML).
  - **Pendiente de comprobar en el servidor** (requiere WinTAK y el móvil
    publicando): qué tipo pinta el icono en **WinTAK 5.8 CIV** — `b-i-v` o
    `b-m-p-s-p-loc` — y que al pulsar el icono la herramienta Vídeo abre el
    feed y reproduce con `takvideo`/`MEDIAMTX_PASSWORD`. Si con `b-i-v` no
    aparece, la alternativa es una línea de `docker-compose.yml`.
- **Consecuencias:**
  - El mapa gana el icono de cámara y el feed queda a un toque; el vídeo sigue
    siendo un canal aparte (si MediaMTX cae, el icono queda huérfano pero el
    mapa, los feeders y el relay siguen intactos).
  - Un servicio más en el compose (y un `docker compose up -d` que ahora exige
    `VIDEO_RTSP_URL`); a cambio, la configuración del vídeo queda explícita y
    versionada, con la contraseña fuera del repositorio y fuera del CoT.
  - El puntero es **estático**: la posición del icono sale de `.env`, no del
    GPS del móvil. Con TAK ICU publicando de verdad, el plugin emite su propio
    CoT de vídeo con la posición real (y con `sensor`/`device`), así que este
    servicio es la pieza para *demo* y para publicar desde el PC con FFmpeg. Si
    en el futuro se quiere la posición real del móvil en el mapa, hay que leer
    el CoT de ICU, no adivinar la posición por `.env` (queda como trabajo
    futuro, no como deuda silenciosa).
  - Alternar el tipo del evento requiere reiniciar el contenedor
    (`docker compose up -d video-cot`): las variables de entorno se leen al
    arrancar (misma lección que `MEDIAMTX_PASSWORD`, ADR 0012).
- **Alternativas descartadas:**
  - **No emitir nada y documentar el vídeo solo en la herramienta Vídeo**
    (estado tras el ADR 0012): válido para ver el stream, pero deja el mapa sin
    el icono y obliga a teclear dirección/puerto/ruta a mano en cada cliente.
  - **Emitir credenciales en el `url`** (`rtsp://takvideo:CLAVE@host/…`): haría
    el feed reproducible con un toque, a costa de publicar la contraseña de
    MediaMTX en claro a **todos** los clientes CoT (y en los logs del relay).
    Contradice la línea de seguridad del proyecto.
  - **Emitir el evento cada segundo** (como el simulador): el puntero no se
    mueve; multiplicaría por 60 el tráfico de un evento que solo necesita
    refrescar su `stale`.
  - **`<videoConnections><feed …/></videoConnections>`** (el formato con el que
    OpenTAK ICU anuncia sus feeds por TCP): pensado para que el servidor
    publique una *lista* de feeds; aquí hay un único stream conocido y el
    objetivo es el icono **en el mapa**, que es lo que da `__video`.
  - **Un script aparte por cada stream** (uno por `MOVILGALICIA`, otro por
    `webcam`): duplicaría contenedores y `.env` para algo que se resuelve
    cambiando `VIDEO_RTSP_URL`.
  - **Publicar el `__video` desde `mediamtx`** (montar el puntero en el propio
    servidor de vídeo): MediaMTX no habla CoT y no debería: son dos canales
    desacoplados a propósito (ADR 0012).
