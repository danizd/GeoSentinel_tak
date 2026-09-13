# CONTEXT — Glosario del proyecto GeoSentinel_tak

Escenario: simulación ligera de 4 helicópteros de rescate ficticios orbitando sobre el deslizamiento de Chamoli, visualizada en WinTAK 5.8 CIV con relieve 3D, sobre FreeTAKServer 2.2.1 desplegado en Docker (ARM64) en Oracle Cloud Free Tier, con Nginx Proxy Manager delante de la UI de administración.

> Nota de fecha: estado verificado en agosto 2026. FTS 2.2.1 (mayo 2024) es la última release; el proyecto lleva más de un año sin publicar versiones nuevas. Riesgo EOL documentado en ADR 0001.

## Glosario

### Canales de FTS

**Canal CoT claro (8087)** — Socket TCP en texto claro donde los clientes TAK (WinTAK, ATAK, el simulador) envían y reciben eventos Cursor on Target. Es el canal por defecto para pruebas y para el simulador.

**Canal CoT TLS (8089)** — Socket TCP cifrado con certificados de cliente. Requiere que el cliente importe el certificado del servidor (o un data package de configuración que lo incluya). Es el canal recomendado para producción.

**Servicio DataPackage (8080/8443)** — Servicio HTTP(S) de FTS para descargar data packages (configuración de conexión, certificados, mapas fuera de línea). 8080 es HTTP claro, 8443 HTTPS.

**API de FTS (19023)** — API REST/WebSocket del core. La consume la UI de administración por la red Docker interna; no se publica al host ni necesita proxy host en NPM.

**NPM (Nginx Proxy Manager)** — Reverse proxy ya existente en la infraestructura, que termina TLS con Let's Encrypt y publica la UI de administración por 443. Solo pasa tráfico HTTP(S): el canal CoT (8087/8089) nunca pasa por NPM.

### Escenario de simulación

**Síntesis** — Las entidades del escenario son datos ficticios generados por software. No representan aeronaves reales ni telemetría real. Es una simulación ligera de demostración.

**Órbita** — Trayectoria circular de cada helicóptero sintético alrededor del centro del escenario. Cada helicóptero tiene radio, altitud, periodo y fase propios; el rumbo es siempre tangente a la órbita.

**Centro del escenario** — Punto de referencia de las órbitas: 30.484°N, 79.732°E (deslizamiento del glaciar Chamoli, Uttarakhand, India).

**Terreno 3D** — Relieve que WinTAK dibuja al inclinar la cámara. Requiere datos de elevación importados (DTED o SRTM convertido a DTED) de la región del escenario; sin ellos no hay relieve que inclinar.

### Entidades y datos

**Helicóptero sintético** — Entidad CoT de tipo `a-f-A-M-H` (helicóptero militar amigo, MIL-STD-2525) con callsign `RESCUE-0N`, uid determinista, orbitando alrededor del centro del escenario a altitud HAE fija. Sin `endpoint` ni `__group` en el `<detail>`, WinTAK renderiza el símbolo 2525 en vez del punto genérico de team member.

**UID determinista** — Identificador estable de cada helicóptero sintético (no regenerado por ejecución), para que WinTAK no acumule contactos fantasma al reiniciar el simulador.

**HAE (Height Above Ellipsoid)** — Altitud sobre el elipsoide WGS-84, la que va en el atributo `hae` del `<point>` CoT y la que WinTAK usa para posicionar la entidad en 3D.

**Data package (DP)** — Archivo .zip importable desde WinTAK que puede llevar configuración de conexión y certificados. Vía recomendada para enrolar clientes en 8089.

**Esri World Imagery** — Fuente de mapa satélite de alta resolución importable en WinTAK como custom map source (`esri_world_imagery.xml`). Proporciona basemap visual para complementar el relieve DTED.

### Acceso y publicación

**Dominio de UI** — Subdominio `fts.movilab.es`, que NPM publica por 443 hacia la UI de administración de FTS.

**Dominio de DP** — Subdominio separado `dp.movilab.es`, que NPM publica por 443 hacia el servicio DataPackage (8080), para que los clientes TAK descarguen data packages por TLS sin exponer 8080 al exterior.

**Fase humo** — Estado inicial del despliegue: canal CoT claro 8087 restringido en firewall, solo para validar la conectividad de extremo a extremo (WinTAK y simulador ven los 4 helicópteros).

**Fase producción** — Estado final del despliegue: canal CoT TLS 8089 con certificados de cliente; 8087 cerrado en el firewall.

**Canal CoT interno** — Conexión del simulador (cuando corre en el servidor) al servicio CoT por la red Docker interna, sin salir del host ni atravesar NPM.

**Pin por digest** — Fijar la versión de las imágenes oficiales por su digest SHA en vez de por tag, para que el despliegue sea reproducible.

**Perfil sim** — Compose profile (`profiles: ["sim"]`) del servicio del simulador: no consume recursos hasta que se activa con `docker compose --profile sim up -d`.

**Época fija** — Anclaje temporal de las órbitas: la posición es función de la hora UNIX (`posición = f(t)`), no de un contador desde el arranque; los reinicios son invisibles en WinTAK y dos instancias producen telemetría idéntica.

**Fase humo / fase producción** — Ver arriba: 8087 claro restringido para validar; 8089 TLS con certificados de cliente como estado final.

**Enrolamiento** — Proceso por el que WinTAK obtiene certificados y configuración de conexión: vía data package generado por FTS (contiene los certificados), descargado del dominio de DP.

**Retención** — Persistencia de eventos CoT en la BD del core (`FTS_COT_TO_DB`). Para la demo está desactivada: solo estado en vivo, sin crecimiento de la BD.

### Fuentes de datos externas

**Feeder deepstatemap.live** — Servicio `deepstate` (imagen oficial multi-arch, ADR 0009) que saca la última capa de unidades del conflicto de Ucrania desde la API de deepstatemap.live (OSINT, uso autorizado) y la convierte a eventos CoT de tipo `a-h-G-U-*`. Solo habla `ssl://` y exige cert+key de cliente, con `rejectUnauthorized:false`.

**Listener TLS del relay (8089)** — Segundo listener de `cot-relay`, interno a la red Docker, por el que entra el feeder. Comparte el mismo hub que el listener en claro: sus eventos se reenvían a todos los clientes (WinTAK por 8087 incluido). Es el punto de entrada previsto para la fase producción TLS de ADR 0002.

**Feeder ADS-B (adsb.lol)** — Servicio `adsb` del compose (script propio `adsb-feeder.py`, solo librería estándar, ADR 0010) que consulta la API pública de adsb.lol — red comunitaria de receptores ADS-B, **datos reales** con licencia ODbL y sin clave de API — alrededor de un punto (Galicia en la demo) y convierte cada aeronave en un evento CoT `a-f-A-C-F` (ala fija) o `a-f-A-C-H` (helicóptero). Se conecta al listener en claro del relay (8087) por la red Docker interna: **no usa TLS**, porque solo lee la API por HTTPS y escribe CoT local. UID determinista por `hex` ICAO de 24 bits; las aeronaves en tierra se descartan.

**Certificado autofirmado del relay** — Par cert/key generado en `data/certs/` (openssl, CN=cot-relay) que habilita el listener TLS. Vale para el feeder porque este no valida la CA (`rejectUnauthorized:false`).

**Cliente atascado (relay)** — Cliente que deja de leer pero mantiene el socket TCP medio abierto (móvil que pierde cobertura, WinTAK cerrado, portátil suspendido). Antes de ADR 0011 llenaba su ventana TCP y bloqueaba el `sendall` del broadcast, que corre en el hilo lector: el hub entero dejaba de reenviar CoT mientras todos los clientes seguían apareciendo "conectados". El relay ahora lo descarta tras `RELAY_SEND_TIMEOUT` (5 s) y lo registra como `cliente descartado`.

### Vídeo en directo

**MediaMTX** — Servicio `mediamtx` del compose (`bluenviron/mediamtx:1.21.0`, imagen multi-arch, ADR 0012): recibe el directo de una cámara por **RTSP** (8554) y lo re-sirve a los clientes TAK; el 8888 publica el mismo stream por **HLS** para comprobarlo en el navegador. Autenticación obligatoria (`authInternalUsers`: publish/read/playback); el usuario es `takvideo` y la contraseña vive en `.env` como `MEDIAMTX_PASSWORD`, no en `mediamtx.yml`.

**Ruta del stream** — Nombre con el que se publica un directo en MediaMTX (`MOVILGALICIA`, `webcam`…): es el alias de TAK ICU en el móvil y el *Path* en la herramienta Vídeo de WinTAK. Cualquier ruta se crea al publicar (`paths: all_others:`), sin declararlas una a una.

**TAK ICU** — Plugin de ATAK (TAK Product Center) que convierte la cámara del móvil en un stream **RTSP**; no va incluido en ATAK-CIV, que por sí solo solo **reproduce** vídeo. Su opción *Destination Type: Wowza Server* se configura con IP del servidor y **puerto 8554** (es RTSP, no RTMP), y el *Broadcast Alias* debe ser **una sola palabra sin espacios** porque es la ruta del stream. Exige **fix GPS**.

**El vídeo NO viaja por CoT** — CoT transporta a lo sumo un puntero (la URL del feed, en un evento con `<__video>`), nunca los fotogramas: el vídeo va por RTSP entre el publicador y MediaMTX. Sin ese evento CoT se ve el vídeo en el reproductor, pero **no aparece icono de cámara en el mapa**.

**Puntero CoT de vídeo** — Evento CoT de tipo `b-i-v` (*Bits/Imagery/Video*) cuyo `<detail>` lleva `<__video url="…">` con un `ConnectionEntry` anidado (address/alias/port/path/protocol y `rtspReliable="1"` = *Reliable P2P Connection* de WinTAK, RTSP sobre TCP). Es lo que pinta el **icono de cámara** en el mapa y crea la entrada del feed en la herramienta Vídeo. Lo emite el servicio `video-cot` (`video-pointer.py`, ADR 0013) cada 60 s, porque el `stale` caduca. **No lleva credenciales**: el CoT va en claro y lo recibe todo el mundo; WinTAK las pide al reproducir.

**Reliable P2P Connection** — Opción de la herramienta Vídeo de WinTAK que fuerza el transporte **TCP** del RTSP. Imprescindible cuando hay NAT o firewall entre el PC y el servidor (el caso del despliegue).

## Decisiones registradas

Ver `docs/adr/` para los ADRs: 0001 (imágenes oficiales multi-arch en vez de build propio), 0002 (fase TLS: humo en 8087, producción en 8089), 0003 (subdominios NPM: UI y DataPackage), 0004 (simulador: servicio compose con perfil + época fija + UIDs deterministas), 0005 (pin por digest + actualizaciones manuales ante el EOL de FTS), 0007 (despliegue ARM64: qemu, UID 999, binds), 0008 (**el canal CoT lo sirve el servicio propio `cot-relay`**: la imagen EOL de FTS 2.2.1 no reenvía CoT a los clientes por falta del paquete `Catalog` de digitalpy; FTS queda como back-end de UI/API/DP) 0009 (feeder deepstatemap.live por listener TLS interno del relay, 8089) 0010 (feeder ADS-B propio sobre adsb.lol: el feeder de terceros está retirado desde el 01-DIC-2025) y 0011 (**el relay descarta clientes que no leen**: `SO_SNDTIMEO` por cliente para que uno atascado no congele el hub, el incidente del 12-SEP-2026 en el que dejaron de verse aviones y Ucrania con el servidor aparentemente sano) 0012 (**servidor de vídeo MediaMTX**: el vídeo no viaja por CoT, así que entra un servidor RTSP propio en 8554, autenticado y con la configuración versionada en `mediamtx.yml` y la contraseña en `.env`) y 0013 (**puntero CoT de vídeo**: `video-pointer.py` emite el evento con `<__video>` para que WinTAK pinte el icono de cámara; cierra el "pendiente" del ADR 0012).
