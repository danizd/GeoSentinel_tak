#!/usr/bin/env python3
"""Feeder ADS-B: aviones REALES en el mapa (datos ADS-B → eventos CoT).

Consulta la API pública de [adsb.lol](https://adsb.lol) — red comunitaria de
receptores ADS-B, datos con licencia ODbL y sin clave de API — alrededor de un
punto, y convierte cada aeronave en un evento Cursor on Target que envía al
relay CoT propio (`cot-relay:8087`, ADR 0008) por la red Docker interna.

Por qué un feeder propio y no uno de terceros: el feeder histórico para ADS-B
(`tak-feeder-adsb-one`) está retirado porque su API se apagó el 01-DIC-2025, y
la alternativa (`adsbcot`) no publica imagen Docker oficial (hay que construirla)
y no documenta el uso de agregadores abiertos. Este script solo usa la librería
estándar, como `cot-relay.py` y `simulator.py`.

Datos REALES: conviven en el mismo mapa con los helicópteros sintéticos de
Chamoli (ficticios, ADR 0004) y con los marcadores de deepstatemap.live; se
distinguen por tipo 2525 (`a-f-A-C-*` aviones, `a-h-G-U-*` unidades) y por zona.

Atribución: datos de adsb.lol (ODbL). No se redistribuyen, solo se consultan.
"""

import json
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---- Fuente de datos (API compatible con la de ADSBExchange v2) ----
API_URL = os.environ.get("ADSB_API_URL", "https://api.adsb.lol/v2/point")
CENTER_LAT = float(os.environ.get("ADSB_LAT", "42.500000"))
CENTER_LON = float(os.environ.get("ADSB_LON", "-8.500000"))
RADIUS_NM = int(os.environ.get("ADSB_RADIUS_NM", "60"))  # la API admite 250 máx.
# adsb.lol pide no pasar de 1 petición/segundo; 10 s deja margen de sobra y el
# mapa va fluido porque el `stale` (60 s) cubre varios ciclos.
POLL_INTERVAL = float(os.environ.get("ADSB_POLL_INTERVAL", "10"))
HTTP_TIMEOUT = float(os.environ.get("ADSB_HTTP_TIMEOUT", "20"))
# Tope de aeronaves por ciclo: sin él, un radio grande inunda el relay y WinTAK
MAX_AIRCRAFT = int(os.environ.get("ADSB_MAX_AIRCRAFT", "150"))

# ---- Destino CoT ----
FTS_HOST = os.environ.get("FTS_HOST", "cot-relay")
FTS_PORT = int(os.environ.get("FTS_PORT", "8087"))

STALE_SECONDS = int(os.environ.get("ADSB_STALE_SECONDS", "60"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
LOG_COT = os.environ.get("LOG_COT", "false").lower() in ("1", "true", "yes")

SCENARIO = "geosentinel-adsb"  # raíz de los UIDs deterministas
FEEDER_UA = "GeoSentinel_tak-adsb-feeder/1.0 (+https://github.com/danizd/GeoSentinel_tak)"

METERS_PER_FOOT = 0.3048
MPS_PER_KNOT = 0.514444

# El tipo CoT distingue avión de ala fija (`a-f-A-C-F`) de helicóptero
# (`a-f-A-C-H`). La categoría ADS-B A7 es rotorcraft; como respaldo, los
# prefijos de designador ICAO más habituales de helicóptero.
ROTORCRAFT_CATEGORY = "A7"
ROTORCRAFT_TYPES = (
    "EC", "AS3", "AS5", "AS6", "R22", "R44", "R66", "B06", "B47", "H47",
    "H60", "UH", "NH", "AW1", "S76", "S92", "MD5", "BK1", "CH4", "A109",
    "A139", "A169",
)


def deterministic_uid(hex_code: str) -> str:
    """UID estable por aeronave: el `hex` ICAO 24 bits no cambia nunca, así que
    WinTAK actualiza el mismo contacto en vez de acumular fantasmas (ADR 0004)."""
    return f"{SCENARIO}.{hex_code.lower()}"


def fetch_aircraft() -> list[dict]:
    """Última foto de las aeronaves dentro del radio (una petición HTTP)."""
    url = f"{API_URL}/{CENTER_LAT:.4f}/{CENTER_LON:.4f}/{RADIUS_NM}"
    request = urllib.request.Request(url, headers={"User-Agent": FEEDER_UA})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        payload = json.load(response)
    return payload.get("ac") or []


def altitude_m(aircraft: dict) -> float | None:
    """Altitud en metros HAE. Prefiere `alt_geom` (geométrica) sobre `alt_baro`.

    Devuelve None para aeronaves en tierra (`alt_baro: "ground"`) o sin dato de
    altitud: no se emiten, para no llenar el mapa de contactos a nivel del suelo
    en los aeropuertos.
    """
    for key in ("alt_geom", "alt_baro"):
        value = aircraft.get(key)
        if isinstance(value, (int, float)):
            return float(value) * METERS_PER_FOOT
    return None


def callsign_of(aircraft: dict) -> str:
    """Callsign de vuelo si lo hay; si no, el hex, para que el contacto se
    identifique siempre (los vuelos sin plan de vuelo llegan sin `flight`)."""
    return (aircraft.get("flight") or "").strip() or str(aircraft.get("hex", "?")).upper()


def cot_type_of(aircraft: dict) -> str:
    if aircraft.get("category") == ROTORCRAFT_CATEGORY:
        return "a-f-A-C-H"
    if str(aircraft.get("t") or "").upper().startswith(ROTORCRAFT_TYPES):
        return "a-f-A-C-H"
    return "a-f-A-C-F"


def remarks_of(aircraft: dict) -> str:
    """Metadatos útiles de la aeronave real (visibles en el detalle del contacto)."""
    bits = ["ADS-B (datos reales, adsb.lol)"]
    if aircraft.get("t"):
        bits.append(f"tipo {aircraft['t']}")
    if aircraft.get("r"):
        bits.append(f"matrícula {aircraft['r']}")
    if aircraft.get("squawk"):
        bits.append(f"squawk {aircraft['squawk']}")
    # Separador ASCII: un '·' (U+00B7) no existe en el code page cp850 de la
    # consola de Windows y `print` muere con OSError [Errno 22].
    return " | ".join(bits)


def cot_timestamp(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def build_cot(
    uid: str,
    callsign: str,
    cot_type: str,
    lat: float,
    lon: float,
    hae: float,
    course: float,
    speed_m_s: float,
    remarks: str,
    now_s: float,
) -> str:
    """Evento CoT de una aeronave. Mismas decisiones que `simulator.py`:

    - Sin prólogo `<?xml?>` por evento (rompe el parser de stream de WinTAK y
      solo se procesaba el primer evento de la conexión).
    - Sin `endpoint` ni `__group` en el `<detail>`, para que WinTAK use el
      símbolo 2525 del `type` en vez del punto genérico de team member.
    """
    now = cot_timestamp(now_s)
    stale = cot_timestamp(now_s + STALE_SECONDS)
    return (
        '<event version="2.0" uid="{uid}" type="{cot_type}"'
        ' time="{now}" start="{now}" stale="{stale}" how="m-g">\n'
        '  <point lat="{lat:.6f}" lon="{lon:.6f}" hae="{hae:.1f}"'
        ' ce="9999.0" le="9999.0"/>\n'
        "  <detail>\n"
        '    <contact callsign="{callsign}"/>\n'
        '    <track course="{course:.1f}" speed="{speed_m_s:.1f}"/>\n'
        "    <remarks>{remarks}</remarks>\n"
        "  </detail>\n"
        "</event>\n"
    ).format(
        uid=uid,
        cot_type=cot_type,
        now=now,
        stale=stale,
        lat=lat,
        lon=lon,
        hae=hae,
        callsign=callsign,
        course=course,
        speed_m_s=speed_m_s,
        remarks=remarks,
    )


def connect() -> socket.socket:
    print(f"Conectando al relay CoT en {FTS_HOST}:{FTS_PORT}...", flush=True)
    sock = socket.create_connection((FTS_HOST, FTS_PORT), timeout=10)
    print("Conectado: el relay reenvía los eventos a todos los clientes.", flush=True)
    return sock


def aircraft_to_cot(aircraft: dict, now_s: float) -> str | None:
    """Convierte una aeronave en CoT, o None si no tiene posición/altitud."""
    lat = aircraft.get("lat")
    lon = aircraft.get("lon")
    if lat is None or lon is None:
        return None
    hae = altitude_m(aircraft)
    if hae is None:
        return None
    track = aircraft.get("track")
    groundspeed = aircraft.get("gs")
    return build_cot(
        uid=deterministic_uid(str(aircraft.get("hex", ""))),
        callsign=callsign_of(aircraft),
        cot_type=cot_type_of(aircraft),
        lat=float(lat),
        lon=float(lon),
        hae=hae,
        course=float(track) if isinstance(track, (int, float)) else 0.0,
        speed_m_s=float(groundspeed) * MPS_PER_KNOT
        if isinstance(groundspeed, (int, float))
        else 0.0,
        remarks=remarks_of(aircraft),
        now_s=now_s,
    )


def main() -> None:
    print(
        f"Feeder ADS-B: {API_URL}/{CENTER_LAT:.4f}/{CENTER_LON:.4f}/{RADIUS_NM} nm"
        f" cada {POLL_INTERVAL:.0f}s ({'DRY RUN' if DRY_RUN else f'{FTS_HOST}:{FTS_PORT}'})",
        flush=True,
    )
    sock: socket.socket | None = None
    http_failures = 0
    while True:
        cycle_start = time.time()
        try:
            aircraft = fetch_aircraft()
            http_failures = 0
        except (urllib.error.URLError, ValueError, OSError) as exc:
            # La API caída o la red del host no deben tumbar el feeder.
            http_failures += 1
            wait = min(30 * http_failures, 300)
            print(f"Sin datos de adsb.lol: {exc} (reintento en {wait}s)", flush=True)
            time.sleep(wait)
            continue

        now_s = time.time()
        sent = 0
        for aircraft in aircraft[:MAX_AIRCRAFT]:
            cot = aircraft_to_cot(aircraft, now_s)
            if cot is None:
                continue
            if DRY_RUN or LOG_COT:
                print(cot, end="", flush=True)
            if DRY_RUN:
                sent += 1
                continue
            try:
                if sock is None:
                    sock = connect()
                sock.sendall(cot.encode("utf-8"))
                sent += 1
            except (ConnectionError, TimeoutError, OSError) as exc:
                print(f"Relay no disponible: {exc}", flush=True)
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                sock = None
                break  # el resto del ciclo se descarta; el siguiente reintenta

        capped = "" if len(aircraft) <= MAX_AIRCRAFT else f" (tope {MAX_AIRCRAFT})"
        print(
            f"{len(aircraft)} aeronaves en el radio{capped}, {sent} enviadas "
            f"({time.strftime('%H:%M:%S')})",
            flush=True,
        )
        elapsed = time.time() - cycle_start
        time.sleep(max(0.0, POLL_INTERVAL - elapsed))


if __name__ == "__main__":
    main()
