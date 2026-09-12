#!/usr/bin/env python3
"""Relay CoT mínimo (ADR 0008).

La imagen oficial de FreeTAKServer 2.2.1 ingiere CoT pero NO lo reenvía a los
clientes conectados: la capa digitalpy de la que depende el reenvío
(broadcast_component_responses -> routing proxy) no carga porque falta el
paquete 'Catalog' (no publicado en ningún sitio, ni siquiera en digitalpy
0.3.16). Resultado: WinTAK conecta (verde) pero no recibe nada.

Este relay hace exactamente lo que FTS no consigue: acepta clientes por TCP,
recibe eventos CoT (texto XML terminado en </event>) y los reenvía a TODOS los
clientes conectados — el comportamiento de un hub CoT clásico de TAK. Un evento
entrante por CUALQUIER listener se reenvía a todos los clientes, sea cual sea
su canal.

Además del listener en claro (8087), puede abrir un listener TLS (8089) cuando
se le dan RELAY_TLS_CERT/RELAY_TLS_KEY (ADR 0009): por él se conecta el feeder
deepstatemap.live, que solo habla ssl://. Cualquier certificado autofirmado
sirve: el feeder usa rejectUnauthorized:false. El puerto 8089 queda INTERNO
(solo red Docker) hasta la fase producción de ADR 0002.

FTS sigue corriendo para UI/API/DataPackage; el relay ocupa el canal CoT
publicado (8087) que antes publicaba el core. WinTAK y el simulador no cambian
de configuración: mismo host y puerto.

Uso (compose o manual):
    RELAY_HOST=0.0.0.0 RELAY_PORT=8087 python3 cot-relay.py
    RELAY_TLS_CERT=/certs/server.pem RELAY_TLS_KEY=/certs/server.key python3 cot-relay.py
"""

import os
import socket
import ssl
import struct
import threading
import time

RELAY_HOST = os.environ.get("RELAY_HOST", "0.0.0.0")
RELAY_PORT = int(os.environ.get("RELAY_PORT", "8087"))
# Listener TLS opcional (ADR 0009): lo usa el feeder deepstatemap.live, que
# solo habla ssl://. El puerto 8089 es el que ADR 0002 reservó para la fase
# de producción; aquí queda INTERNO (solo red Docker), hasta que la fase
# producción publique el canal TLS para WinTAK.
RELAY_TLS_PORT = int(os.environ.get("RELAY_TLS_PORT", "8089"))
RELAY_TLS_CERT = os.environ.get("RELAY_TLS_CERT", "")
RELAY_TLS_KEY = os.environ.get("RELAY_TLS_KEY", "")
END_OF_EVENT = b"</event>"
MAX_BUFFER = 1_048_576  # bytes: corta clientes que nunca cierran un evento

# Segundos que el relay espera a que un cliente ACEPTE un evento antes de
# descartarlo. Sin este tope, un cliente que deja de leer (móvil que pierde la
# cobertura, WinTAK cerrado, portátil suspendido) llena su búfer TCP y el
# `sendall` del broadcast se queda bloqueado para siempre. Y como el broadcast
# lo ejecuta el hilo que LEE del emisor, ese hilo no vuelve a leer: TODOS los
# clientes dejan de recibir CoT aunque sigan apareciendo "conectados" y el log
# de eventos se detiene en seco. Un solo cliente muerto congela el hub entero
# (incidente del 12-SEP-2026: "no veo ni los aviones ni Ucrania").
RELAY_SEND_TIMEOUT = float(os.environ.get("RELAY_SEND_TIMEOUT", "5"))

# sock -> (ip, port): permite loguear el origen de cada evento (diagnóstico)
clients: dict[socket.socket, tuple] = {}
# sock -> Lock de ENVÍO: sin él, dos hilos emisores entrelazan bytes de
# eventos distintos en el mismo socket destino y el cliente recibe XML corrupto
send_locks: dict[socket.socket, threading.Lock] = {}
clients_lock = threading.Lock()
event_count = 0


def ts() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


def set_send_timeout(sock: socket.socket) -> None:
    """Acota SOLO los envíos de un cliente (SO_SNDTIMEO).

    No se usa `settimeout()/setblocking()`: son del socket entero y también
    afectarían al `recv` del hilo que atiende a ese cliente, desconectando a
    clientes sanos por estar ociosos. En Windows la opción espera milisegundos
    (DWORD); en Linux, un struct timeval.
    """
    try:
        if os.name == "nt":
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_SNDTIMEO, int(RELAY_SEND_TIMEOUT * 1000)
            )
        else:
            fmt = "ll" if struct.calcsize("l") == 8 else "ii"
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_SNDTIMEO,
                struct.pack(fmt, int(RELAY_SEND_TIMEOUT), 0),
            )
    except OSError:
        # Si el SO no soporta la opción, el relay sigue funcionando como antes.
        pass


def broadcast(data: bytes, origin: socket.socket) -> None:
    """Envía un evento CoT completo a todos los clientes salvo el origen
    (un TAK server real no devuelve el evento a quien lo emitió).

    Un cliente que no acepta el evento dentro de RELAY_SEND_TIMEOUT se
    descarta: preferimos perder un cliente atascado a congelar el hub."""
    global event_count
    event_count += 1
    callsign = extract_callsign(data)
    with clients_lock:
        origin_addr = clients.get(origin, ("?", "?"))
        targets = [(s, send_locks[s]) for s in clients if s is not origin]
    dead: list[tuple[socket.socket, str]] = []
    for sock, lock in targets:
        try:
            with lock:
                sock.sendall(data)
        except TimeoutError:
            dead.append((sock, f"no lee (sin aceptar {RELAY_SEND_TIMEOUT:.0f}s)"))
        except OSError as exc:
            dead.append((sock, f"error de envío: {exc}"))
    if dead:
        with clients_lock:
            for sock, reason in dead:
                addr = clients.pop(sock, None)
                send_locks.pop(sock, None)
                log(f"cliente descartado {addr}: {reason}")
                try:
                    sock.close()
                except OSError:
                    pass
    log(
        f"evento #{event_count} {callsign} ({len(data)} B) "
        f"de {origin_addr[0]}:{origin_addr[1]} -> broadcast a {len(targets)} cliente(s)"
    )


def extract_callsign(data: bytes) -> str:
    for key in (b'callsign="', b"callsign=\""):
        start = data.find(key)
        if start != -1:
            start += len(key)
            end = data.find(b'"', start)
            if end != -1:
                return data[start:end].decode(errors="ignore")
    return "(sin callsign)"


def handle_client(sock: socket.socket, addr) -> None:
    log(f"cliente conectado {addr} (total {len(clients)})")
    buffer = b""
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > MAX_BUFFER:
                log(f"cliente {addr} superó {MAX_BUFFER} B sin cerrar evento; se desconecta")
                break
            # Cada evento CoT termina en </event>; puede haber varios por
            # recv() o uno partido en varios recv().
            while END_OF_EVENT in buffer:
                event, buffer = buffer.split(END_OF_EVENT, 1)
                broadcast(event + END_OF_EVENT, sock)
    except (OSError, ConnectionError):
        pass
    finally:
        with clients_lock:
            clients.pop(sock, None)
            send_locks.pop(sock, None)
        try:
            sock.close()
        except OSError:
            pass
        log(f"cliente desconectado {addr} (total {len(clients)})")


def serve(listener: socket.socket, label: str) -> None:
    """Acepta clientes de un listener (claro o TLS) y los registra en el hub
    común: un evento entrante por cualquier listener se reenvía a TODOS los
    clientes, sea cual sea su canal (comportamiento de hub CoT clásico)."""
    log(f"relay CoT {label} escuchando")
    while True:
        sock, addr = listener.accept()
        set_send_timeout(sock)
        with clients_lock:
            clients[sock] = addr
            send_locks[sock] = threading.Lock()
        threading.Thread(target=handle_client, args=(sock, addr), daemon=True).start()


def tcp_listener(port: int) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((RELAY_HOST, port))
    server.listen(32)
    return server


def main() -> None:
    threading.Thread(
        target=serve,
        args=(tcp_listener(RELAY_PORT), f"claro {RELAY_HOST}:{RELAY_PORT}"),
        daemon=True,
    ).start()

    if RELAY_TLS_CERT and RELAY_TLS_KEY:
        if os.path.isfile(RELAY_TLS_CERT) and os.path.isfile(RELAY_TLS_KEY):
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(RELAY_TLS_CERT, RELAY_TLS_KEY)
            listener = ctx.wrap_socket(tcp_listener(RELAY_TLS_PORT), server_side=True)
            threading.Thread(
                target=serve,
                args=(listener, f"TLS {RELAY_HOST}:{RELAY_TLS_PORT}"),
                daemon=True,
            ).start()
        else:
            # No tumbar el canal claro 8087 si faltan los certs: se sigue
            # sirviendo WinTAK/simulador y solo se avisa (ADR 0009).
            log(
                f"listener TLS {RELAY_TLS_PORT} desactivado: no encuentro "
                f"{RELAY_TLS_CERT}/{RELAY_TLS_KEY} (genera data/certs/, ver README; "
                "el feeder deepstate no conectará)"
            )
    else:
        log(
            f"listener TLS {RELAY_TLS_PORT} desactivado: "
            "faltan RELAY_TLS_CERT/RELAY_TLS_KEY (feeder deepstate no conectará)"
        )

    # Hilo principal vivo: los listeners corren en daemons.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
