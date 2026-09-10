# GeoSentinel_tak

Simulación ligera de 4 helicópteros de rescate **sintéticos** orbitando sobre el deslizamiento del glaciar **Chamoli (Uttarakhand, India)** — 30.484°N, 79.732°E, 3.900–5.200 m HAE — servida por **FreeTAKServer 2.2.1** en Docker (ARM64, Oracle Cloud Free Tier) y visualizada en **WinTAK 5.8 CIV** con relieve 3D descargada desde https://tak.gov/products/wintak-civ.

- Especificación completa: [`especificaciones.md`](especificaciones.md)
- Glosario y decisiones: [`CONTEXT.md`](CONTEXT.md), [`docs/adr/`](docs/adr/)

```text
simulator.py ──TCP 8087──► cot-relay ◄──TCP 8087── WinTAK ──► relieve 3D
                              ▲
Navegador ──https://fts.…──► NPM ─┘ (UI 5000 · DP 8080 · API 19023 por TLS)

FTS 2.2.1 (core) queda como back-end de UI/API/DP: su imagen EOL no reenvía
CoT a los clientes (ADR 0008), así que el canal CoT lo sirve cot-relay.
```

## Estructura

```text
├── docker-compose.yml    # core + UI + cot-relay + simulador (perfil "sim")
├── .env.example          # plantilla de secretos -> copiar a .env
├── simulator.py          # telemetría CoT (PC o servidor)
├── cot-relay.py          # hub CoT que reenvía a todos los clientes (ADR 0008)
├── start.bat             # arranque del simulador en el PC (Windows)
├── .gitignore            # protege .env, data/ y dted_work/
├── esri_world_imagery.xml # fuente de mapa satélite para WinTAK
└── docs/adr/             # decisiones 0001–0009
```

## Quickstart — servidor (Oracle ARM64)

Requisitos: Docker + compose plugin, NPM ya corriendo en la red Docker externa `proxy_network`, DNS **solo DNS (gris)** para `fts.movilab.es` y `dp.movilab.es` apuntando a la IP pública.

> **ARM64 + imágenes amd64 (ADR 0007):** los tags `freetakserver:v2_2_1` y `ui:master` son amd64-only y corren bajo **emulación qemu** en Oracle ARM64. Sin el registro de binfmt, ambos contenedores caen con `exec format error` (exit 255).

```bash
# 1. Copiar el proyecto al servidor
scp -r . ubuntu@IP_SERVIDOR:~/freetak
ssh ubuntu@IP_SERVIDOR
cd ~/freetak

# 2. Crear la red compartida con NPM (si NPM aún no la creó)
docker network create proxy_network 2>/dev/null || true

# 3. Registrar el emulador qemu (OBLIGATORIO en ARM64; una sola vez por host)
docker run --privileged --rm tonistiigi/binfmt --install all

# 4. Secretos
cp .env.example .env
#   editar .env: reemplazar cada "cambia-esto" por valores largos y aleatorios
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 5. Permisos del bind mount del core: FTS corre como UID 999 (cuenta de
#    sistema, ver ADR 0007), NO 1000. Docker crea data/core como root si no
#    existe; sin el chown el core muere con PermissionError en FTSConfig.yaml.
#    (Hace falta de nuevo cada vez que se borre la carpeta.)
mkdir -p data/core && sudo chown -R 999:999 data/core && sudo chmod -R u+rwX data/core

# 6. Levantar
docker compose up -d
docker compose logs -f cot-relay    # el relay CoT arranca siempre
```

Verificación:

```bash
docker ps                                     # freetakserver + freetakserver-ui + cot-relay Up
docker compose logs freetakserver | tail      # sin PermissionError; wizard headless OK
curl -I http://localhost:5000                 # UI responde (dentro del host)
docker compose logs cot-relay                 # "relay CoT escuchando en 0.0.0.0:8087"
# (no usar `ss` dentro del contenedor: la imagen no lo incluye)
```

> **Por qué cot-relay (ADR 0008):** la imagen oficial de FTS 2.2.1 ingiere CoT
> pero **no lo reenvía a los clientes conectados** — la capa digitalpy del
> reenvío no carga porque falta el paquete `Catalog` (no publicado en ningún
> sitio). El servicio `cot-relay` hace el reenvío (mismo host y puerto 8087),
> y FTS queda como back-end de UI/API/DP.

## Quickstart — escenario (simulador)

En el **servidor** (24/7, canal CoT interno por la red Docker):

```bash
docker compose --profile sim up -d      # arranca
docker compose --profile sim down       # detiene
docker compose logs -f fts-simulator
```

En el **PC** (pruebas manuales, fase humo):

```bat
start.bat                          :: fts.movilab.es:8087
start.bat 192.168.1.50 8087        :: host y puerto dados
```

`start.bat` localiza Python, comprueba la conectividad TCP y arranca `simulator.py` (Ctrl+C para parar).

## Quickstart — WinTAK (cliente Windows)

Antes de nada, NPM debe tener creados los **dos** proxy hosts (ADR 0003), todos con TLS Let's Encrypt y **WebSockets Support ON**, en la red `proxy_network`:

```text
fts.movilab.es → freetakserver-ui:5000   (UI de administración)
dp.movilab.es  → freetakserver:8080      (DataPackage para WinTAK)
```

> La API REST (19023) se consume internamente por la red Docker; no necesita proxy host propio.

1. **Fase humo** — `Settings → Network Preferences → Network Connections → Add`: TCP, `fts.movilab.es`, **8087**. Los cuatro `RESCUE-0N` aparecen en segundos. (El 8087 lo sirve `cot-relay`, ADR 0008; la configuración de WinTAK no cambia.)
2. **Fase producción (TLS)** — desde la UI genera el data package de conexión, descárgalo por `https://dp.movilab.es/...`, impórtalo en WinTAK (`Import Manager → Import Data Package`) y cambia la conexión a **TCP SSL, 8089**. Cierra 8087 en Oracle Security List.
3. **Relieve 3D** — importa SRTM/DTED de la región (`Import Manager → Zipped DTED Directory`) y arrastra el **Tilt Slider** para inclinar la cámara sobre el cañón.
4. **Mapa satélite** — importa `esri_world_imagery.xml` (`Import Manager → Map Source`) para tener imágenes de alta resolución como basemap.

> **Icono de helicóptero:** el simulador usa `type="a-f-A-M-H"` (helicóptero militar amigo, MIL-STD-2525). Sin `endpoint` ni `__group` en el `<detail>`, WinTAK renderiza el símbolo 2525 en vez del punto genérico de team member.

> **Configuración regional de Windows:** WinTAK usa el separador decimal del sistema para parsear coordenadas. Si Windows está en español (coma decimal), el **GoTo** no acepta puntos. Usar comas en GoTo (ej. `30,4840`, `79,7320`) o cambiar el separador decimal a punto en Configuración regional.

Detalle completo (incluida la conversión SRTM→DTED con GDAL): [`especificaciones.md` §4](especificaciones.md).

## Firewall (Oracle Security List / NSG + ufw)

```text
80/tcp   → Internet            # reto HTTP-01 de Let's Encrypt
443/tcp  → Internet            # NPM: UI + DP por TLS
8087/tcp → SOLO tu IP pública  # fase humo; cerrar tras validar
8089/tcp → Internet            # fase producción: CoT TLS con cert cliente
```

Nada más: 5000/8080/8443/19023 quedan internos (NPM o red Docker).

## Añadir más helicópteros

Los helicópteros se definen en la tupla `HELICOPTERS` de `simulator.py`:

```python
HELICOPTERS = (
    # callsign, radius_m, altitude_m (HAE), period_s, phase_rad
    ("RESCUE-01", 700.0, 3900.0, 180.0, 0.0),
    ("RESCUE-02", 1000.0, 4300.0, 210.0, math.pi / 2),
    # ... añadir más aquí
)
```

| Campo | Significado | Ejemplo |
|---|---|---|
| `callsign` | Nombre en WinTAK | `"RESCUE-05"` |
| `radius_m` | Radio de órbita (metros) | `1900.0` |
| `altitude_m` | Altitud HAE (metros) | `5500.0` |
| `period_s` | Segundos por vuelta | `300.0` |
| `phase_rad` | Fase inicial (radianes) | `math.pi / 4` |

- El UID se genera automáticamente desde el callsign (determinista, sin fantasmas en WinTAK al reiniciar).
- Tras editar, reiniciar el simulador: Ctrl+C y `start.bat` (PC) o `docker compose --profile sim restart simulator` (servidor).
- WinTAK muestra los nuevos contactos automáticamente.

## Añadir mapas 3D de otras regiones

WinTAK necesita datos DTED para dibujar relieve. Para cualquier región del mundo:

1. **Descargar SRTM** (`.hgt`, 30 m de resolución) desde [viewfinderpanoramas.org](https://viewfinderpanoramas.org/dem3/) o [EarthExplorer](https://earthexplorer.usgs.gov/).
2. **Convertir a DTED** con GDAL:
   ```bash
   gdal_translate -of DTED -co LEVEL=1 N41W006.hgt dted/w006/n41.dt1
   # Estructura: dted/<wNNN>/<nXX>.dt1  (un archivo por grado)
   ```
3. **Copiar a WinTAK:** los `.dt1` van directamente en `C:\ProgramData\WinTAK\DTED\` manteniendo la estructura `wNNN\nXX.dt1`.
4. **Reiniciar WinTAK** para que cargue el nuevo terreno.

> **Script automático:** `dted_work\build_spain_dted.bat` descarga y convierte automáticamente los tiles de Galicia + Ceuta (14 tiles SRTM). Úsalo como plantilla para otras regiones cambiando la lista de tiles.

> **Resolución:** DTED nivel 1 (`.dt1`) = 90 m. Para 30 m usa `-co LEVEL=2` (archivos `.dt2`, 4× más grandes).

> **Sin GDAL:** si no tienes GDAL instalado: `winget install OSGeo.GDAL` o descarga OSGeo4W.

## Feeder deepstatemap.live (datos OSINT de Ucrania, opcional)

Integra en el mapa los datos **reales** (OSINT) del conflicto de Ucrania desde
[deepstatemap.live](https://deepstatemap.live), vía
[tak-feeder-deepstate](https://github.com/sgofferj/tak-feeder-deepstate)
(GPL-3.0; uso autorizado por el equipo de deepstatemap.live). El feeder saca la
última capa de unidades, la convierte a eventos CoT (`a-h-G-U-*`) y los envía
al relay por un listener TLS **interno** (ADR 0009); WinTAK los recibe por su
conexión normal (8087) porque el relay reenvía a todos los clientes.

> Los marcadores deepstate son datos reales del frente ucraniano y conviven en
> el mismo mapa con los helicópteros sintéticos de Chamoli (datos ficticios).
> Se distinguen por tipo 2525 y por zona; cada entidad mantiene su UID.

Requisitos y arranque en el servidor:

```bash
# 1. Certificado autofirmado del relay (una sola vez; data/ está en .gitignore)
mkdir -p data/certs && cd data/certs
openssl req -x509 -newkey rsa:2048 -nodes -keyout server.key -out server.pem \
  -days 3650 -subj "/CN=cot-relay"
cd ../..

# 2. Levantar (o reiniciar cot-relay si ya estaba arriba)
docker compose up -d cot-relay deepstate
docker compose logs -f deepstate
```

Verificación:

```bash
docker compose logs cot-relay   # "relay CoT TLS ... escuchando"
docker compose logs deepstate   # "Found /certs/server.pem" ... "nameFull ..."
```

El feeder conecta cada `PULL_INTERVAL` (mínimo real: 300 s) y envía un
heartbeat CoT (marcador "DEEPSTATE" en Kyiv) más las unidades de la última
capa. En WinTAK, navega a Ucrania (~49.0, 31.0) y verás los marcadores.

Detalles:

- El feeder (Node.js upstream) **solo habla `ssl://`** y exige cert+key de
  cliente; usa `rejectUnauthorized:false`, por eso vale el certificado
  autofirmado del relay (los mismos ficheros hacen de cert de "cliente").
- El puerto 8089 del relay es **interno** (solo red Docker). Cuando la fase
  producción de ADR 0002 publique el canal TLS para WinTAK, este listener será
  el mismo punto de entrada.
- Imagen oficial multi-arch (`ghcr.io/sgofferj/tak-feeder-deepstate:latest`):
  en ARM64 no necesita qemu (ADR 0007). Pin por digest al primer pull (ADR 0005).
- Para pararlo: `docker compose stop deepstate`.

## Mantenimiento

- **Actualizar**: `docker compose pull && docker compose up -d` tras leer el changelog (manual, nunca automático — ADR 0005).
- **Backup**: `tar czf /backup/fts-$(date +%F).tgz -C ~/freetak data` (cron nocturno, retención 7 días).
- **Monitorización**: ping periódico desde el servidor a healthchecks.io.

## Troubleshooting (WinTAK)

- **Solo aparece el primer RESCUE:** causa raíz era el prólogo `<?xml ...?>` repetido en cada evento CoT del stream TCP. WinTAK solo procesaba el primer evento. Solución: `simulator.py` no incluye prólogo XML por evento.
- **Marcadores desplazados al polo norte:** WinTAK 4.x/5.x con configuración regional española interpreta el punto decimal como separador de miles. Usar comas en GoTo o cambiar la configuración regional de Windows.
- **Los RESCUE no aparecen en Team Members:** es esperado — sin `endpoint` ni `__group` en el `<detail>`, WinTAK los renderiza como símbolos 2525 (no como team members). Aparecen en el mapa como iconos militares.
- **El relay envía eventos pero WinTAK no los muestra:** verificar que el `stale` del evento tenga margen suficiente (60 s en `simulator.py`) para tolerar deriva de reloj entre servidor y PC.

## Seguridad

- Los datos son **ficticios** (síntesis, sin telemetría real).
- `.env` nunca se commitea; `data/` (BD y certificados) tampoco.
- CoT nunca pasa por NPM: es socket TCP, no HTTP.
- **Pendiente:** cambiar credenciales por defecto (`admin`/`password`), rotar `FTS_API_TOKEN` y restringir/cerrar 8087 tras validar (ADR 0002).
