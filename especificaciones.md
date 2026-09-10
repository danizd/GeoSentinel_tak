# Especificaciones GeoSentinel_tak — FTS en Oracle ARM64 con WinTAK 3D

> Estado: agosto 2026. FTS 2.2.1 (última release, mayo 2024) pineada por digest — riesgo EOL documentado en ADR 0005. Decisiones de diseño en `docs/adr/0001`–`0008`; glosario en `CONTEXT.md`. Verificado contra las fuentes oficiales (docs Docker de FTS, compose de referencia de FreeTAKHub-Installation, PyPI).

Escenario: 4 helicópteros de rescate **sintéticos** orbitando sobre el deslizamiento del glaciar **Chamoli, Uttarakhand (India)** — 30.484°N, 79.732°E, altitudes 3.900–5.200 m HAE — visualizados en **WinTAK 5.8 CIV** con relieve 3D, sobre **FreeTAKServer 2.2.1** en Docker (ARM64, Ampere A1 de Oracle Cloud Free Tier), con **Nginx Proxy Manager (NPM)** delante de la administración.

Correcciones aplicadas sobre el spec original (verificadas contra las fuentes oficiales):

1. Las imágenes oficiales son **contenedores separados** core + UI (ADR 0001), sin build propio. Matiz verificado en el despliegue real (ADR 0007): los **tags** `freetakserver:v2_2_1` y `ui:master` son **amd64-only** y corren bajo **emulación qemu/binfmt** en ARM64 (la doc de la imagen anuncia multi-arch para otros builds, pero estos tags no traen variante arm64).
2. Variables de entorno corregidas a las reales del compose oficial (`FTS_COT_TO_DB`, no `SaveCoTToDB`; la UI usa `FTS_IP`/`FTS_API_PORT`/`FTS_UI_PORT`, no `IP`/`APPIP`).
3. Correcciones del simulador: rumbo tangente real (el original daba `θ+90`, que apunta mal en todo el círculo), velocidad por helicóptero coherente con su órbita (el original fijaba 60 m/s), UIDs deterministas (el original regeneraba `uuid4()` en cada arranque → fantasmas en WinTAK) y posición anclada a época (ADR 0004).
4. La etiqueta "Nepal" corregida: Chamoli está en **Uttarakhand, India**. Coordenadas intactas.
5. Añadido el hueco del objetivo 3D: **datos de elevación (DTED/SRTM)** que WinTAK necesita para dibujar el relieve (§4, paso 3).
6. La API 19023 no se publica al host ni necesita proxy host en NPM (el compose oficial la marca "don't expose by default"); la UI la consume por la red Docker interna.
7. Despliegue real en ARM64 (ADR 0007): los tags usados son amd64-only → hace falta registrar qemu/binfmt en el host; FTS corre como UID 999 (no 1000); la UI necesita compartir `/opt/fts` del core (solo lectura); y `FTS_UI_EXPOSED_IP` es el BIND de la UI (debe ser `0.0.0.0`, no el dominio).
8. **La imagen EOL de FTS 2.2.1 no reenvía CoT a los clientes** (ADR 0008): ingiere los eventos (`executing a-f-A-C-H`) pero el reenvío depende de la capa digitalpy, que no carga porque falta el paquete `Catalog` (no publicado en PyPI ni en digitalpy 0.3.13.7/0.3.16). WinTAK conecta (verde) y no recibe nada. Se añade el servicio propio **`cot-relay`** (hub TCP que reenvía a todos los clientes) que ocupa el 8087 publicado; FTS queda como back-end de UI/API/DP.

Puertos FTS (arquitectura oficial): CoT claro **8087**, CoT SSL **8089**, DataPackage **8080/8443**, API/WebSocket **19023**, UI **5000**.

---

## 1. ARCHIVO DOCKER-COMPOSE (ARM64)

Tres servicios con las **imágenes oficiales multi-arch** (ADR 0001), pineadas por digest (ADR 0005), en la red Docker externa `proxy_network` donde ya vive tu NPM (ADR 0003). El simulador viaja como servicio con perfil `sim` (ADR 0004): no consume CPU hasta que lo activas.

Estructura:

```text
freetak/
├── docker-compose.yml
├── .env                  # secretos, fuera del repo
├── simulator.py          # §3
└── data/                 # creada al primer arranque (bind mounts)
```

### `docker-compose.yml`

> Imagen tags verificados en GHCR (agosto 2026): NO existe el tag `2.2.1` para ninguna de las dos imágenes. Para el core usa `ghcr.io/freetakteam/freetakserver:v2_2_1` (build de FTS 2.2.1, digest `sha256:cc6147ba031c03406ff63abe35641cd2f9efb6f507b88617a1c099e0ff87a866`); para la UI usa `ghcr.io/freetakteam/ui:master` (última publicada, digest `sha256:eeaf23ef435068ac90f05a18fbad58db6d350fdc204b4bae4f6f98a42a51b004`). Tras el primer pull, pinea por digest (ADR 0005).

```yaml
services:

  freetakserver:
    # FTS 2.2.1 (v2_2_1 tag); pin by digest after first pull per ADR 0005:
    #   docker buildx imagetools inspect ghcr.io/freetakteam/freetakserver:v2_2_1
    image: ghcr.io/freetakteam/freetakserver:v2_2_1
    # Estos tags GHCR son amd64-only; en ARM64 corren bajo qemu/binfmt (ADR 0007).
    # Registrar el emulador una vez por host:
    #   docker run --privileged --rm tonistiigi/binfmt --install all
    platform: linux/amd64
    container_name: freetakserver
    hostname: freetakserver
    restart: unless-stopped
    networks:
      - proxy_network
    # ADR 0008: la imagen EOL de FTS 2.2.1 NO reenvía CoT a los clientes.
    # El canal CoT publicado lo sirve el servicio cot-relay (abajo); los
    # puertos CoT del core quedan internos y sin uso. 8080/8443/19023/5000
    # siguen internos para NPM (ADR 0003).
    volumes:
      # FTS corre como UID 999 (useradd -r, cuenta de sistema) — NO 1000.
      # data/core debe pertenecer a 999:999 o muere con PermissionError:
      #   sudo chown -R 999:999 data/core
      - ./data/core:/opt/fts
    environment:
      # ---- Secretos (en .env, nunca en el repo) ----
      FTS_FED_PASSWORD: "${FTS_FED_PASSWORD}"
      FTS_CLIENT_CERT_PASSWORD: "${FTS_CLIENT_CERT_PASSWORD}"
      FTS_WEBSOCKET_KEY: "${FTS_WEBSOCKET_KEY}"
      FTS_SECRET_KEY: "${FTS_SECRET_KEY}"
      # ---- Networking: FTS anuncia el dominio público del DP (ADR 0003) ----
      # Las direcciones de ESCUCHA son los defaults del contenedor; lo que se
      # anuncia a los clientes es el dominio público del servicio DataPackage.
      FTS_DP_ADDRESS: "dp.movilab.es"
      FTS_USER_ADDRESS: "dp.movilab.es"
      FTS_API_ADDRESS: "freetakserver"
      FTS_COT_PORT: 8087
      FTS_SSLCOT_PORT: 8089
      FTS_API_PORT: 19023
      FTS_DP_PORT: 8080
      # ---- Retención: demo de estado en vivo, BD plana (decisión Q13) ----
      FTS_COT_TO_DB: "False"
      FTS_LOG_LEVEL: "info"
      FTS_MAINLOOP_DELAY: "100"

  freetakserver-ui:
    # UI current release (master tag). After first pull, pin by digest per ADR 0005:
    #   docker buildx imagetools inspect ghcr.io/freetakteam/ui:master
    image: ghcr.io/freetakteam/ui:master
    # amd64-only; corre bajo qemu/binfmt en ARM64 (ADR 0007).
    platform: linux/amd64
    container_name: freetakserver-ui
    hostname: freetakserver-ui
    restart: unless-stopped
    networks:
      - proxy_network
    volumes:
      # NAMED volume requerido: un bind mount en /home/freetak sombrearía el
      # entrypoint docker-run.sh de la imagen (el contenedor no arranca).
      - fts-ui-data:/home/freetak
      # La UI comparte /opt/fts con el core DE ESCRITURA: LEE FTSConfig.yaml
      # (que genera el core) y ESCRIBE su propia BD (sqlite:////opt/fts/
      # FTSServer-UI.db, default del config.py). Con :ro muere con 'unable to
      # open database file' (ADR 0007).
      - ./data/core:/opt/fts
    environment:
      # La UI usa FTS_IP/PORT/PROTO para sus llamadas server-side al core.
      # Con un hostname interno de la red Docker funciona correctamente;
      # no necesita proxy host en NPM ni publicación de puerto al host.
      FTS_IP: "freetakserver"
      FTS_API_PORT: "19023"
      FTS_API_PROTO: "http"
      FTS_UI_PORT: "5000"
      FTS_UI_WSKEY: "${FTS_WEBSOCKET_KEY}"
      FTS_API_KEY: "Bearer ${FTS_API_TOKEN}"
      # CUIDADO: FTS_UI_EXPOSED_IP es la direccion de BIND de eventlet.listen
      # (config.py de la UI), no el dominio publico. Con un dominio ahi la UI
      # muere con 'Errno 99 Cannot assign requested address' (ADR 0007).
      # Debe escuchar en 0.0.0.0; el dominio fts.movilab.es:443 lo resuelve NPM.
      FTS_UI_EXPOSED_IP: "0.0.0.0"
      FTS_UI_EXPOSED_PROTO: "https"
      FTS_MAP_EXPOSED_IP: "127.0.0.1"
      FTS_MAP_PORT: "8000"
      FTS_MAP_PROTO: "http"

# Nota: la API REST (19023) se consume internamente por la red Docker;
# no necesita proxy host en NPM ni publicacion de puerto al host.

  # ---- Relay CoT (ADR 0008) ----
  # Hub CoT mínimo que SÍ reenvía eventos a todos los clientes conectados,
  # cosa que la imagen de FTS 2.2.1 no consigue. Ocupa el puerto publicado
  # 8087 (fase humo). WinTAK y el simulador no cambian de config: mismo
  # host y puerto, ahora servidos por este contenedor.
  cot-relay:
    image: python:3.11-slim
    container_name: cot-relay
    restart: unless-stopped
    networks:
      - proxy_network
    ports:
      - "8087:8087"   # CoT claro (fase humo; cerrar tras validar)
    volumes:
      - ./cot-relay.py:/cot-relay.py:ro
    environment:
      RELAY_HOST: "0.0.0.0"
      RELAY_PORT: "8087"
    command: ["python", "/cot-relay.py"]

  # ---- Simulador (ADR 0004): perfil "sim", inactivo hasta que lo actives ----
  #   docker compose --profile sim up -d
  simulator:
    image: python:3.11-slim
    container_name: fts-simulator
    profiles: ["sim"]
    restart: unless-stopped
    networks:
      - proxy_network
    volumes:
      - ./simulator.py:/simulator.py:ro
    environment:
      FTS_HOST: "cot-relay"        # el relay reenvía a todos los clientes
      FTS_PORT: "8087"
    command: ["python", "/simulator.py"]
    depends_on:
      - cot-relay

networks:
  proxy_network:
    external: true
    name: proxy_network
```

`.env` (junto al compose, fuera del repo):

```text
FTS_FED_PASSWORD=<largo-aleatorio>
FTS_CLIENT_CERT_PASSWORD=<largo-aleatorio>
FTS_WEBSOCKET_KEY=<largo-aleatorio>
FTS_SECRET_KEY=<largo-aleatorio>
FTS_API_TOKEN=<largo-aleatorio>
```

Despliegue:

```bash
mkdir -p ~/freetak && cd ~/freetak
# copiar docker-compose.yml, .env y simulator.py aquí
docker network create proxy_network 2>/dev/null || true   # si NPM aún no la creó
docker compose up -d
docker compose --profile sim up -d    # cuando quieras el escenario en marcha
docker compose logs -f freetakserver
```

Verificación:

```bash
docker ps                                        # freetakserver + freetakserver-ui Up
docker compose logs freetakserver | tail         # sin PermissionError; wizard headless OK
curl -I http://localhost:5000                    # UI responde (dentro del host)
# (no usar `ss` dentro del contenedor: la imagen no lo incluye)
```

Plan B (solo si GHCR fuera inalcanzable desde Oracle): build propio desde `python:3.11-slim-bookworm` con `pip install FreeTAKServer==2.2.1 freetakserver-ui==2.2.1`, **dos contenedores separados** (nunca dos procesos en uno: el `start.sh` del spec original mezclaba shebang `sh` con `wait -n`, exclusivo de bash, y moría al arrancar). Documentado en ADR 0001; no es la ruta primaria.

---

## 2. CONFIGURACIÓN EN NGINX PROXY MANAGER (NPM)

Dos proxy hosts (ADR 0003): la UI y el DataPackage. **El CoT (8087/8089) nunca pasa por NPM** — es socket TCP, no HTTP. La API REST (19023) se consume internamente por la red Docker; no necesita proxy host.

Requisito previo: NPM y FTS comparten la red externa `proxy_network` (`docker network connect proxy_network npm` si hace falta). DNS en modo **solo DNS (gris)** para los dos subdominios (decisión Q15): el proxy naranja de Cloudflare rompería 8087/8089 y complica el HTTP-01.

### Proxy Host 1 — UI de administración

Domains: `fts.movilab.es`

```text
Scheme:            http
Forward Hostname:  freetakserver-ui
Forward Port:      5000
```

Opciones:

```text
Block Common Exploits: ON
Websockets Support:    ON     # el tablero en vivo de la UI va por WebSocket
```

SSL:

```text
Request a new SSL Certificate (Let's Encrypt)
Force SSL: ON    HTTP/2: ON    HSTS: ON
```

### Proxy Host 2 — DataPackage (para que WinTAK descargue DPs por TLS)

Domains: `dp.movilab.es`

```text
Scheme:            http
Forward Hostname:  freetakserver
Forward Port:      8080
```

Mismo tratamiento SSL (Websockets irrelevante aquí). Como `FTS_DP_ADDRESS=dp.movilab.es`, los enlaces de data packages que genera FTS ya salen en HTTPS por este host.

### Firewall (Oracle Security List / NSG + ufw)

```text
80/tcp   → Internet            # reto HTTP-01 de Let's Encrypt
443/tcp  → Internet            # NPM: UI + DP por TLS
8087/tcp → SOLO tu IP pública  # fase humo (ADR 0002); cerrar tras validar
8089/tcp → Internet            # fase producción: CoT TLS con cert cliente
```

El resto (8080, 8443, 19023, 5000) **no se abre**: todo pasa por NPM o por la red Docker interna.

Flujo resultante:

```text
Navegador ──https://fts.movilab.es──► NPM ──► freetakserver-ui:5000
WinTAK DP ──https://dp.movilab.es───► NPM ──► freetakserver:8080
WinTAK    ──TCP 8087 (fase humo)───────────► cot-relay:8087
simulador ──TCP 8087 (red Docker interna)──► cot-relay:8087
```

> **ADR 0008:** el CoT no pasa por FTS — el relay lo reenvía a todos los clientes. La fase producción (8089 TLS) añadirá listener TLS al relay.

---

## 3. SCRIPT DE SIMULACIÓN EN PYTHON (TELEMETRÍA CoT)

Un solo `simulator.py` para PC y servidor (ADR 0004): `FTS_HOST`/`FTS_PORT` vienen del entorno. Correcciones sobre el original: rumbo tangente correcto, velocidad real por helicóptero, UIDs deterministas, posición anclada a época (Q12a), altitud HAE por helicóptero, tipo `a-f-A-M-H` (helicóptero militar amigo, MIL-STD-2525), 1 Hz, `stale` 60 s. Sin prólogo XML por evento (causa raíz de que WinTAK solo procesara el primer evento del stream). Sin `endpoint` ni `__group` en `<detail>` (para que WinTAK renderice el símbolo 2525 en vez del punto de team member).

```python
#!/usr/bin/env python3
"""Simulación FTS: 4 helicópteros de rescate sintéticos orbitando sobre
Chamoli (Uttarakhand, India). Telemetría CoT por TCP — datos ficticios."""

import hashlib
import math
import os
import socket
import time
from datetime import datetime, timezone

FTS_HOST = os.environ.get("FTS_HOST", "fts.movilab.es")
FTS_PORT = int(os.environ.get("FTS_PORT", "8087"))

CENTER_LAT = 30.484000
CENTER_LON = 79.732000
UPDATE_INTERVAL = 1.0
STALE_SECONDS = 60
SCENARIO = "geosentinel-chamoli"  # raíz de los UIDs deterministas

METERS_PER_DEG_LAT = 111_320.0

HELICOPTERS = (
    # callsign, radius_m, altitude_m (HAE), period_s, phase_rad
    ("RESCUE-01",  700.0, 3900.0, 180.0, 0.0),
    ("RESCUE-02", 1000.0, 4300.0, 210.0, math.pi / 2),
    ("RESCUE-03", 1300.0, 4750.0, 240.0, math.pi),
    ("RESCUE-04", 1600.0, 5200.0, 270.0, 3 * math.pi / 2),
)


def deterministic_uid(callsign: str) -> str:
    """UID estable entre ejecuciones (ADR 0004): sin uuid4()."""
    digest = hashlib.sha256(f"{SCENARIO}:{callsign}".encode()).hexdigest()
    return f"{SCENARIO}.{callsign}.{digest[:12]}"


def orbit_position(
    radius_m: float, phase_rad: float, angular_velocity: float, epoch_s: float
) -> tuple[float, float, float, float]:
    """Posición sobre la órbita en función de la época (ADR 0004).

    Devuelve (lat, lon, rumbo_grados, velocidad_m_s). El rumbo es la
    tangente REAL a la órbita: con este=cos θ, norte=sin θ y θ creciente,
    el vector velocidad es (-sin θ, cos θ) → rumbo = (-θ) mod 360.
    """
    angle = phase_rad + angular_velocity * epoch_s
    east_m = radius_m * math.cos(angle)
    north_m = radius_m * math.sin(angle)

    meters_per_deg_lon = METERS_PER_DEG_LAT * math.cos(math.radians(CENTER_LAT))
    lat = CENTER_LAT + north_m / METERS_PER_DEG_LAT
    lon = CENTER_LON + east_m / meters_per_deg_lon

    heading = math.degrees(-angle) % 360.0
    speed = angular_velocity * radius_m  # velocidad tangencial real
    return lat, lon, heading, speed


def cot_timestamp(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def build_cot(
    uid: str, callsign: str, lat: float, lon: float,
    hae: float, heading: float, speed: float, now_s: float,
) -> str:
    now = cot_timestamp(now_s)
    stale = cot_timestamp(now_s + STALE_SECONDS)
    # Sin prólogo <?xml?>: una declaración XML solo es legal al inicio de un
    # documento; repetirla por evento rompe el parser de stream de WinTAK
    # (solo procesaba el primer evento de la conexión).
    return (
        '<event version="2.0" uid="{uid}" type="a-f-A-M-H"'
        ' time="{now}" start="{now}" stale="{stale}" how="m-g">\n'
        '  <point lat="{lat:.6f}" lon="{lon:.6f}" hae="{hae:.1f}"'
        ' ce="10.0" le="20.0"/>\n'
        "  <detail>\n"
        # Sin endpoint ni __group: con ellos WinTAK renderiza un punto de
        # team member (círculo cian); sin ellos usa el símbolo 2525 del type
        # (a-f-A-M-H = helicóptero militar amigo).
        '    <contact callsign="{callsign}"/>\n'
        '    <track course="{heading:.1f}" speed="{speed:.1f}"/>\n'
        "    <remarks>Simulación FTS Chamoli - datos ficticios</remarks>\n"
        "  </detail>\n"
        "</event>\n"
    ).format(
        uid=uid, now=now, stale=stale, lat=lat, lon=lon, hae=hae,
        callsign=callsign, heading=heading, speed=speed,
    )


def connect() -> socket.socket:
    print(f"Conectando a {FTS_HOST}:{FTS_PORT}...")
    sock = socket.create_connection((FTS_HOST, FTS_PORT), timeout=10)
    print("Conectado al servicio CoT de FTS.")
    return sock


def main() -> None:
    sock: socket.socket | None = None
    while True:
        try:
            if sock is None:
                sock = connect()
            now_s = time.time()  # época: reinicio invisible (ADR 0004)
            for callsign, radius, hae, period, phase in HELICOPTERS:
                omega = 2.0 * math.pi / period
                lat, lon, heading, speed = orbit_position(
                    radius, phase, omega, now_s
                )
                cot = build_cot(
                    uid=deterministic_uid(callsign),
                    callsign=callsign, lat=lat, lon=lon, hae=hae,
                    heading=heading, speed=speed, now_s=now_s,
                )
                sock.sendall(cot.encode("utf-8"))
                print(
                    f"{callsign:10s} LAT={lat:.6f} LON={lon:.6f} "
                    f"ALT={hae:.0f}m HDG={heading:6.1f} SPD={speed:4.1f}"
                )
            time.sleep(UPDATE_INTERVAL)
        except (ConnectionError, TimeoutError, OSError) as exc:
            print(f"Conexión perdida: {exc}")
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            sock = None
            time.sleep(5)


if __name__ == "__main__":
    main()
```

En el PC:

```powershell
$env:FTS_HOST = "fts.movilab.es"; py simulator.py
```

En el servidor: `docker compose --profile sim up -d` (usa `FTS_HOST=cot-relay` interno, ADR 0008).

Salida esperada (velocidades coherentes con cada órbita: 2πr/T):

```text
RESCUE-01  LAT=30.484xxx LON=79.732xxx ALT=3900m HDG=  xxx.x SPD=24.4
RESCUE-02  LAT=30.484xxx LON=79.732xxx ALT=4300m HDG=  xxx.x SPD=29.9
RESCUE-03  LAT=30.484xxx LON=79.732xxx ALT=4750m HDG=  xxx.x SPD=34.0
RESCUE-04  LAT=30.484xxx LON=79.732xxx ALT=5200m HDG=  xxx.x SPD=37.2
```

---

## 4. CONEXIÓN EN WINTAK (CLIENTE WINDOWS) Y TERRENO 3D

WinTAK y el simulador son clientes del mismo servicio CoT:

```text
simulator.py ──TCP 8087──► cot-relay ◄──TCP 8087── WinTAK ──► relieve 3D
```

> El canal CoT lo sirve **cot-relay** (ADR 0008): la imagen de FTS 2.2.1 no reenvía CoT a los clientes.

### Paso 0 — Prueba previa de conectividad (fase humo)

```powershell
Test-NetConnection fts.movilab.es -Port 8087   # TcpTestSucceeded : True
```

### Paso 1 — Conexión CoT en WinTAK

```text
Settings → Network Preferences → Network Connections → Add
  Name:            FTS Chamoli Simulation
  Connection Type: TCP
  Host:            fts.movilab.es
  Port:            8087          # fase humo (claro)
```

Guardar y activar. Los cuatro `RESCUE-0N` aparecen en el mapa en segundos.

### Paso 2 — Fase producción: enrolamiento TLS por data package (8089)

1. Entra en la UI (`https://fts.movilab.es`).
2. Genera el **data package de conexión** del cliente (sección de conexión/clientes): FTS empaqueta el certificado del servidor y la configuración del cliente (decisión Q14a).
3. Descarga el `.zip` desde `https://dp.movilab.es/...` (el enlace ya sale en HTTPS porque `FTS_DP_ADDRESS=dp.movilab.es`).
4. En WinTAK: **Import Manager → Import Data Package**, elige el zip — los certificados caen en `cert/` y la conexión se registra.
5. Edita la conexión: **Connection Type: TCP SSL, Port 8089**. Actívala.
6. Cierra `8087/tcp` en Oracle Security List (ADR 0002): a partir de aquí solo 8089 TLS.

### Paso 3 — Datos de elevación (el relieve que se puede inclinar)

Sin DTED cargado, WinTAK inclina un plano vacío — no hay montañas. Importa el terreno de la región (decisión Q7a):

1. Descarga SRTM 30 m de la zona (p. ej. desde EarthExplorer, tiles que cubran 30.0–31.0°N / 79.2–80.2°E) o un DTED ya preparado de la región.
2. Si viene como SRTM `.hgt`, conviértelo a DTED con GDAL:
   ```bash
   gdal_translate -of DTED N30E079.hgt dted/e079/n30.dt1
   # Un tile por grado; DTED nivel 1 (.dt1) tiene 90 m de resolución.
   # La carpeta debe seguir la estructura DTED: dted/<eNNN>/<nXX.dt1>
   ```
3. Copia los `.dt1` directamente a `C:\ProgramData\WinTAK\DTED\` (WinTAK los carga al arrancar) o comprime el directorio DTED en un `.zip` e impórtalo.
4. WinTAK (alternativa zip): **Import Manager → Zipped DTED Directory** y selecciona el zip.
5. Verifica en 2D que el terreno carga (Elevation Profile sobre el cañón).

> **Nota:** WinTAK puede mostrar "No files imported" si el zip no tiene la estructura DTED correcta (`dted/eNNN/nXX.dt1`). La vía más fiable es copiar los `.dt1` directamente a `C:\ProgramData\WinTAK\DTED\`.

### Paso 4 — Vista 3D

```text
Arrastra el Tilt Slider (lateral del mapa) hacia el icono de inclinación
→ la cámara se inclina y el relieve DTED aparece en 3D.
Centra en 30.484 N, 79.732 E, zoom al cañón.
```

Los cuatro helicópteros orbitan a altitudes HAE distintas (3.900–5.200 m) entre las montañas.

### Paso 5 — Mapa satélite (basemap de alta resolución)

El basemap por defecto de WinTAK es de baja resolución. Para mejorar la vista:

1. Importa `esri_world_imagery.xml` desde **Import Manager → Map Source**.
2. Activa la capa ESRI World Imagery como basemap.
3. Combina con el relieve DTED: al inclinar la cámara, el satélite se drapa sobre el terreno 3D.

> **GoTo con configuración regional española:** WinTAK usa el separador decimal del sistema. Si Windows está en español, usar comas en GoTo: `30,4840`, `79,7320` (no puntos).

### Verificación final

```bash
# servidor
docker compose logs -f cot-relay         # clientes conectados + eventos reenviados
```

```powershell
# PC — tras activar la conexión TLS, los RESCUE-0N siguen visibles con 8087 cerrado
```

### Mantenimiento (decisiones Q16–Q18)

- **Actualizaciones**: manuales y programadas — `docker compose pull && docker compose up -d` tras leer el changelog; nunca automáticas.
- **Backup**: cron nocturno del host — `tar czf /backup/fts-$(date +%F).tgz -C ~/freetak data` con retención de 7 días.
- **Monitorización**: ping periódico desde el servidor a healthchecks.io (avisa por email si FTS deja de latir).

---

## 5. TROUBLESHOOTING (WINTAK)

### Solo aparece el primer RESCUE

**Causa raíz:** el prólogo `<?xml version="1.0" ...?>` repetido en cada evento CoT del stream TCP es XML inválido (una declaración XML solo es legal al inicio del documento). WinTAK parsea el primer evento y descarta el resto del stream.

**Solución:** `simulator.py` no incluye prólogo XML por evento. Cada evento empieza directamente con `<event>`.

### Marcadores desplazados al polo norte

**Causa:** WinTAK con configuración regional española interpreta el punto decimal como separador de miles. Al introducir coordenadas con puntos en GoTo (ej. `30.4840`), las parsea mal.

**Solución:** usar comas en GoTo (`30,4840`, `79,7320`) o cambiar el separador decimal a punto en Configuración regional de Windows.

### Los RESCUE no aparecen en Team Members

**Es esperado:** sin `endpoint` ni `__group` en el `<detail>`, WinTAK renderiza los contactos como símbolos MIL-STD-2525 (icono de helicóptero militar amigo) en vez de puntos de team member. Los helicópteros aparecen en el mapa como iconos, no en el panel de Team Members.

### El relay envía eventos pero WinTAK no los muestra

**Causa probable:** el `stale` del evento caduca antes de llegar a WinTAK por deriva de reloj entre servidor y PC.

**Solución:** `STALE_SECONDS = 60` en `simulator.py` da margen suficiente para tolerar hasta ~50 s de deriva. Verificar la hora del sistema en ambos extremos.

### WinTAK muestra "No files imported" al importar DTED

**Causa:** el zip no tiene la estructura DTED correcta (`dted/eNNN/nXX.dt1`).

**Solución:** copiar los archivos `.dt1` directamente a `C:\ProgramData\WinTAK\DTED\` en lugar de importar un zip.

---

## 6. SEGURIDAD PENDIENTE

El servidor está expuesto a Internet. Tareas de endurecimiento pendientes:

1. **Cambiar credenciales por defecto:** `admin`/`password` son públicos y ya se intentaron logins no autorizados. Cambiar desde la UI de administración.
2. **Rotar `FTS_API_TOKEN`:** el valor por defecto (`token`) es público. Generar uno nuevo con `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` y actualizarlo en `.env` y en la BD del core (tabla `SystemUser`/`APIUser`, columna `token`).
3. **Restringir/cerrar 8087:** tras validar la fase humo y migrar a 8089 TLS, cerrar 8087 en Oracle Security List (ADR 0002).
4. **Fase producción TLS 8089:** añadir listener TLS al `cot-relay` (con los certs de FTS o CA propia importada en WinTAK) y que el DataPackage de la UI apunte al relay.
