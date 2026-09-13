#!/usr/bin/env python3
"""Puntero CoT de vídeo: el icono de cámara en el mapa (ADR 0013).

El vídeo **no viaja por CoT** (ADR 0012): los fotogramas van por RTSP entre el
publicador (TAK ICU o FFmpeg) y MediaMTX. Lo que sí puede viajar por CoT es un
*puntero* al stream: un evento con `<__video>` en el `<detail>` que hace que
WinTAK/ATAK pinten un icono de cámara en el mapa. Sin ese evento el vídeo se ve
en la herramienta Vídeo, pero **no hay nada que tocar en el mapa** — que es
exactamente el hueco que quedó abierto al aceptar el ADR 0012.

Este script emite ese evento cada `VIDEO_RESEND_SECONDS` (el `stale` caduca, así
que hay que refrescarlo) y lo envía al relay CoT propio (`cot-relay:8087`,
ADR 0008) por la red Docker interna, igual que `simulator.py` y
`adsb-feeder.py`. Solo usa la librería estándar.

Estructura del evento (medida, no copiada de un ejemplo): la del plugin
**TAK ICU**, cuyo hermano de código abierto **OpenTAK ICU** publica el mismo
`__video` con un `ConnectionEntry` anidado:

    <event type="b-i-v" ...>
      <point lat="…" lon="…" hae="…" ce="…" le="…"/>
      <detail>
        <contact callsign="…"/>
        <__video url="rtsp://host:8554/ruta" uid="…">
          <ConnectionEntry address="host" alias="ruta" port="8554"
                           path="ruta" protocol="rtsp" rtspReliable="1"/>
        </__video>
      </detail>
    </event>

`rtspReliable="1"` fuerza RTSP sobre TCP, que es lo que WinTAK llama *Reliable
P2P Connection*: imprescindible con NAT o firewall por medio (nuestro caso).

El tipo del evento es configurable (`VIDEO_COT_TYPE`): por defecto `b-i-v`
(*Bits/Imagery/Video*) y, como alternativa, `b-m-p-s-p-loc` (*Sensor Point of
Interest*), que es el que usan TAK ICU y OpenTAK ICU. Si en el servidor no
aparece el icono, cambiar de uno a otro es una variable de entorno, no un
cambio de código (ver ADR 0013, "Verificación").

Configuración (variables de entorno):
    VIDEO_RTSP_URL        rtsp://IP:8554/MOVILGALICIA  (obligatoria)
    VIDEO_LAT / VIDEO_LON / VIDEO_HAE  posición del icono (por defecto, el
                          centro del escenario de Chamoli)
    VIDEO_COT_TYPE        tipo CoT del evento (por defecto `b-i-v`)
    VIDEO_ALIAS           alias del feed (por defecto, la ruta del URL)
    VIDEO_RTSP_RELIABLE   1 = RTSP por TCP (por defecto), 0 = UDP
    FTS_HOST / FTS_PORT   relay CoT (por defecto cot-relay:8087)

Las credenciales del stream **no se emiten**: el CoT va en claro y lo recibe
todo el mundo, así que la contraseña de MediaMTX no se publica aquí. WinTAK
pide usuario y contraseña la primera vez, al reproducir el feed.
"""

import os
import socket
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from xml.sax.saxutils import quoteattr

# ---- Destino CoT ----
FTS_HOST = os.environ.get("FTS_HOST", "cot-relay")
FTS_PORT = int(os.environ.get("FTS_PORT", "8087"))

# ---- Puntero al stream ----
# URL completa del stream en MediaMTX. Obligatoria: sin ella el evento apuntaría
# a un servidor inventado, y un icono de cámara que no reproduce nada es peor
# que no tener icono.
VIDEO_RTSP_URL = os.environ.get("VIDEO_RTSP_URL", "").strip()
VIDEO_COT_TYPE = os.environ.get("VIDEO_COT_TYPE", "b-i-v").strip()
VIDEO_ALIAS = os.environ.get("VIDEO_ALIAS", "").strip()
# Posición del icono. Por defecto, el centro del escenario (Chamoli), para que
# la demo del vídeo aparezca junto a los RESCUE; el caso real es la posición
# del móvil que publica.
VIDEO_LAT = float(os.environ.get("VIDEO_LAT", "30.484000"))
VIDEO_LON = float(os.environ.get("VIDEO_LON", "79.732000"))
VIDEO_HAE = float(os.environ.get("VIDEO_HAE", "3900.0"))
# 1 = RTSP sobre TCP (Reliable P2P Connection en WinTAK), 0 = UDP.
VIDEO_RTSP_RELIABLE = 1 if os.environ.get("VIDEO_RTSP_RELIABLE", "1") != "0" else 0

# El puntero no se mueve: se refresca en vez de emitirse a 1 Hz. El `stale` es
# holgado (5 min) para tolerar deriva de reloj entre servidor y PC.
VIDEO_STALE_SECONDS = int(os.environ.get("VIDEO_STALE_SECONDS", "300"))
VIDEO_RESEND_SECONDS = float(os.environ.get("VIDEO_RESEND_SECONDS", "60"))

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
LOG_COT = os.environ.get("LOG_COT", "false").lower() in ("1", "true", "yes")

SCENARIO = "geosentinel-video"  # raíz de los UIDs deterministas (ADR 0004)
PROTOCOLS = ("rtsp", "rtsps", "rtmp", "rtmps", "srt", "http", "https")
DEFAULT_PORTS = {"rtsp": 8554, "rtsps": 8554, "rtmp": 1935, "rtmps": 1935, "srt": 8554}


def parse_stream_url(url: str) -> tuple[str, str, int, str]:
    """Descompone el URL del stream en (protocolo, host, puerto, ruta).

    Las credenciales (`rtsp://usuario:clave@host/…`) se **descartan a
    propósito**: el evento CoT viaja en claro y lo recibe cada cliente
    conectado. El URL que se publica se reconstruye sin ellas.
    """
    parts = urllib.parse.urlsplit(url)
    protocol = (parts.scheme or "").lower()
    if protocol not in PROTOCOLS:
        raise ValueError(
            f"protocolo '{protocol}' no reconocido en VIDEO_RTSP_URL "
            f"(esperado uno de: {', '.join(PROTOCOLS)})"
        )
    host = parts.hostname or ""
    if not host:
        raise ValueError("VIDEO_RTSP_URL no tiene host (ej. rtsp://10.0.0.5:8554/MOVILGALICIA)")
    port = parts.port or DEFAULT_PORTS.get(protocol, 8554)
    path = parts.path.lstrip("/")
    if not path:
        raise ValueError("VIDEO_RTSP_URL no tiene ruta (ej. …:8554/MOVILGALICIA)")
    return protocol, host, port, path


def stream_url(protocol: str, host: str, port: int, path: str) -> str:
    """URL del stream sin credenciales: la que va en el atributo `url`."""
    return f"{protocol}://{host}:{port}/{path}"


def deterministic_uid(path: str) -> str:
    """UID estable por ruta de stream: reiniciar el puntero actualiza el mismo
    contacto en vez de acumular iconos fantasma (ADR 0004)."""
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in path.lower())
    return f"{SCENARIO}.{slug}"


def cot_timestamp(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def build_cot(
    uid: str,
    alias: str,
    url: str,
    address: str,
    port: int,
    path: str,
    protocol: str,
    lat: float,
    lon: float,
    hae: float,
    now_s: float,
    stale_seconds: int = VIDEO_STALE_SECONDS,
    cot_type: str = VIDEO_COT_TYPE,
) -> str:
    """Evento CoT del puntero de vídeo.

    Mismas reglas que `simulator.py` y `adsb-feeder.py`: sin prólogo `<?xml?>`
    por evento (rompe el parser de stream de WinTAK) y sin `endpoint` ni
    `__group` en el `<detail>`. Aquí el `<contact>` sí lleva callsign: es el
    nombre con el que el icono (y el feed) aparece en el mapa.

    Los `ce`/`le` son enormes (9999999) a propósito: la posición del icono no
    viene de un GPS, no queremos que WinTAK dibuje un círculo de error.
    """
    now = cot_timestamp(now_s)
    stale = cot_timestamp(now_s + stale_seconds)
    return (
        '<event version="2.0" uid={uid} type={cot_type}'
        " time={now} start={now} stale={stale} how=\"m-g\">\n"
        "  <point lat=\"{lat:.6f}\" lon=\"{lon:.6f}\" hae=\"{hae:.1f}\""
        ' ce="9999999.0" le="9999999.0"/>\n'
        "  <detail>\n"
        "    <contact callsign={alias}/>\n"
        "    <__video url={url} uid={uid}>\n"
        "      <ConnectionEntry address={address} alias={alias} uid={uid}"
        " port=\"{port}\" path={path} protocol={protocol}"
        " bufferTime=\"-1\" roverPort=\"-1\" ignoreEmbeddedKLV=\"false\""
        " rtspReliable=\"{reliable}\" networkTimeout=\"5000\"/>\n"
        "    </__video>\n"
        "    <remarks>Directo RTSP (MediaMTX) - el video no viaja por CoT"
        " (ADR 0012); puntero CoT con __video (ADR 0013)</remarks>\n"
        "  </detail>\n"
        "</event>\n"
    ).format(
        uid=quoteattr(uid),
        cot_type=quoteattr(cot_type),
        now=quoteattr(now),
        stale=quoteattr(stale),
        lat=lat,
        lon=lon,
        hae=hae,
        alias=quoteattr(alias),
        url=quoteattr(url),
        address=quoteattr(address),
        port=port,
        path=quoteattr(path),
        protocol=quoteattr(protocol),
        reliable=VIDEO_RTSP_RELIABLE,
    )


def connect() -> socket.socket:
    print(f"Conectando al relay CoT en {FTS_HOST}:{FTS_PORT}...", flush=True)
    sock = socket.create_connection((FTS_HOST, FTS_PORT), timeout=10)
    print("Conectado: el relay reenvía el puntero a todos los clientes.", flush=True)
    return sock


def validate_config() -> tuple[str, str, int, str]:
    """Comprueba la configuración al arrancar y aborta con un mensaje claro.

    Es preferible un error explícito a un icono de cámara apuntando a un stream
    que no existe o a un puerto equivocado (misma política que el
    `${VAR:?…}` del compose para `MEDIAMTX_PASSWORD`, ADR 0012).
    """
    if not VIDEO_RTSP_URL:
        raise ValueError(
            "falta VIDEO_RTSP_URL (ej. rtsp://TU_IP_PUBLICA:8554/MOVILGALICIA). "
            "El móvil publica con el alias como ruta (TAK ICU, README \"Vídeo en directo\")"
        )
    protocol, host, port, path = parse_stream_url(VIDEO_RTSP_URL)
    if " " in path:
        raise ValueError(
            f"la ruta del stream ('{path}') tiene espacios: TAK ICU falla al "
            "publicar y el URL queda roto; usa una sola palabra (ej. MOVILGALICIA)"
        )
    if not (-90.0 <= VIDEO_LAT <= 90.0 and -180.0 <= VIDEO_LON <= 180.0):
        raise ValueError(f"posición del icono fuera de rango: {VIDEO_LAT}, {VIDEO_LON}")
    return protocol, host, port, path


def main() -> None:
    try:
        protocol, host, port, path = validate_config()
    except ValueError as exc:
        print(f"Configuración incorrecta: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)

    alias = VIDEO_ALIAS or path
    uid = deterministic_uid(path)
    url = stream_url(protocol, host, port, path)
    if urllib.parse.urlsplit(VIDEO_RTSP_URL).username:
        print(
            "Aviso: VIDEO_RTSP_URL lleva credenciales; se descartan del evento "
            "(el CoT va en claro y lo recibe todo el mundo)",
            flush=True,
        )

    print(
        f"Puntero de vídeo: {alias} -> {url} ({VIDEO_COT_TYPE},"
        f" rtspReliable={VIDEO_RTSP_RELIABLE}) en {VIDEO_LAT:.6f},{VIDEO_LON:.6f}"
        f" cada {VIDEO_RESEND_SECONDS:.0f}s"
        f" ({'DRY RUN' if DRY_RUN else f'{FTS_HOST}:{FTS_PORT}'})",
        flush=True,
    )

    sock: socket.socket | None = None
    while True:
        cycle_start = time.time()
        cot = build_cot(
            uid=uid,
            alias=alias,
            url=url,
            address=host,
            port=port,
            path=path,
            protocol=protocol,
            lat=VIDEO_LAT,
            lon=VIDEO_LON,
            hae=VIDEO_HAE,
            now_s=cycle_start,
        )
        if DRY_RUN or LOG_COT:
            print(cot, end="", flush=True)
        if DRY_RUN:
            return
        try:
            if sock is None:
                sock = connect()
            sock.sendall(cot.encode("utf-8"))
            print(
                f"puntero {alias} enviado ({time.strftime('%H:%M:%S')})",
                flush=True,
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            print(f"Relay no disponible: {exc}", flush=True)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            sock = None
        elapsed = time.time() - cycle_start
        time.sleep(max(0.0, VIDEO_RESEND_SECONDS - elapsed))


if __name__ == "__main__":
    main()
