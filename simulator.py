#!/usr/bin/env python3
"""Simulación FTS: 4 helicópteros de rescate sintéticos orbitando sobre
Chamoli (Uttarakhand, India). Telemetría CoT por TCP — datos ficticios.

Corre en el PC (apuntando al dominio) o en el servidor como servicio de
compose con perfil "sim" (apuntando a cot-relay:8087 interno, ADR 0008).
"""

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
    ("RESCUE-01", 700.0, 3900.0, 180.0, 0.0),
    ("RESCUE-02", 1000.0, 4300.0, 210.0, math.pi / 2),
    ("RESCUE-03", 1300.0, 4750.0, 240.0, math.pi),
    ("RESCUE-04", 1600.0, 5200.0, 270.0, 3 * math.pi / 2),
    ("RESCUE-05", 1900.0, 5500.0, 300.0, math.pi / 4),
    ("RESCUE-06", 2200.0, 5800.0, 330.0, 5 * math.pi / 4),
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
    uid: str,
    callsign: str,
    lat: float,
    lon: float,
    hae: float,
    heading: float,
    speed: float,
    now_s: float,
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
        uid=uid,
        now=now,
        stale=stale,
        lat=lat,
        lon=lon,
        hae=hae,
        callsign=callsign,
        heading=heading,
        speed=speed,
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
                lat, lon, heading, speed = orbit_position(radius, phase, omega, now_s)
                cot = build_cot(
                    uid=deterministic_uid(callsign),
                    callsign=callsign,
                    lat=lat,
                    lon=lon,
                    hae=hae,
                    heading=heading,
                    speed=speed,
                    now_s=now_s,
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
