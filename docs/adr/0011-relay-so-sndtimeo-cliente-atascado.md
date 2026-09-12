# ADR 0011 — El relay descarta clientes que no leen (un cliente muerto no congela el hub)

- **Estado:** Aceptado (2026-09)
- **Contexto:** El 12-SEP-2026, ya con el feeder ADS-B (ADR 0010) desplegado, el
  mapa dejó de mostrar **todos** los contactos remotos: ni las aeronaves, ni
  los puntos de Ucrania del feeder deepstate (ADR 0009). Los datos del servidor
  decían que todo estaba sano:
  - `adsb` registraba `50 aeronaves en el radio, 9 enviadas` cada 10 s.
  - `api.adsb.lol` respondía **HTTP 200** desde el propio servidor.
  - `deepstate` seguía vivo y el relay aceptaba conexiones nuevas (`cliente
    conectado ... (total 5)`, `(total 6)`).
  - Pero el log de eventos del relay **se detenía en seco** (último
    `evento #1544700` a las 14:54:41) mientras el simulador seguía emitiendo
    ~10 eventos/s y el feeder ADS-B seguía enviando cada 10 s. Ningún cliente
    aparecía como desconectado.
  Causa: `broadcast()` enviaba de forma **síncrona** al resto de clientes y lo
  ejecuta el hilo que **lee** del emisor, sin ningún tope de tiempo en el
  envío. Un cliente que deja de leer —móvil que pierde cobertura, WinTAK
  cerrado, portátil suspendido— no cierra el socket: se queda medio abierto,
  su ventana TCP se llena y `sendall` se bloquea **indefinidamente**. Ese hilo
  nunca vuelve a `recv`, así que deja de leer del emisor; los demás hilos que
  hacen broadcast se apilan detrás del mismo socket muerto y el hub entero se
  congela. Los clientes siguen "conectados" (el `accept` va en otro hilo), por
  eso el síntoma engaña: parece un problema de los feeders o de WinTAK.
- **Decisión:**
  - Fijar **`SO_SNDTIMEO`** en cada socket aceptado (`RELAY_SEND_TIMEOUT`,
    por defecto **5 s**): acota **solo los envíos**.
  - Un cliente que no acepta un evento dentro del plazo se **descarta** (se
    cierra el socket y se registra `cliente descartado <addr>: no lee (...)`).
    Se prefiere perder un cliente atascado a congelar el hub.
  - No se usa `settimeout()` ni `setblocking()`: son del socket entero y
    también afectan al `recv` del hilo que atiende a ese cliente, con lo que
    **clientes sanos pero ociosos** se desconectarían por un `recv` que expira.
  - En Windows `SO_SNDTIMEO` espera milisegundos (DWORD); en Linux, un
    `struct timeval`. Se cubren ambos (el relay se ejecuta en Linux dentro de
    Docker, pero el script también puede correrse en el PC para diagnosticar).
- **Verificación:** Prueba con tres clientes contra el relay real, un cliente
  "atascado" (búfer de recepción de 2 KB y **nunca** lee), un cliente sano que
  va leyendo y un emisor de 400 eventos CoT de ~1,2 KB:
  - **Relay sin parche:** el emisor se bloqueó en el evento 249, el cliente
    sano recibió **58** eventos, **0** descartes registrados y el log del relay
    terminó en `evento #58`. Hub congelado: **SÍ** — el incidente reproducido.
  - **Relay parcheado:** **400/400** eventos enviados y **400/400** recibidos
    por el cliente sano, **1** descarte (`no lee (sin aceptar 2s)`), y el log
    siguió hasta `evento #400 ... -> broadcast a 1 cliente(s)` (uno menos tras
    el descarte). Hub congelado: **NO**.
- **Consecuencias:**
  - Un cliente muerto cuesta, como mucho, **un** tiempo de espera
    (`RELAY_SEND_TIMEOUT`) antes de quedar fuera; el hub se auto-recupera sin
    reiniciar el contenedor. Antes no se recuperaba nunca.
  - Un cliente **lento pero vivo** (móvil con mala cobertura) puede ser
    descartado si no acepta un evento en 5 s. Es el compromiso correcto para un
    hub CoT: mejor perder un cliente que a todos. Si en el futuro molesta,
    basta subir `RELAY_SEND_TIMEOUT` en el compose.
  - Sigue habiendo un coste residual: mientras se detecta al cliente atascado,
    el resto de broadcast esperan a ese socket (el descarte ocurre tras el
    primer tiempo de espera agotado, no de inmediato).
  - El diagnóstico queda en el log: `cliente descartado` identifica al culpable
    por IP y puerto, la información que faltaba durante el incidente.
- **Alternativas descartadas:**
  - `settimeout()` / `setblocking(False)`: afectan al socket completo, incluido
    el `recv`; desconectarían clientes sanos ociosos y complicarían el bucle de
    lectura sin resolver nada que `SO_SNDTIMEO` no resuelva.
  - Un hilo escritor con cola por cliente: aísla mejor el bloqueo, pero añade
    estado y complejidad considerables para un hub que mueve eventos de ~450 B.
  - Keepalive TCP (`SO_KEEPALIVE`): detecta al cliente muerto a nivel de red,
    pero **no** desbloquea un `sendall` ya bloqueado con la ventana llena; no
    evita el incidente, solo lo alarga.
  - Reiniciar el relay como rutina: lo desbloquea hasta que vuelve a aparecer
    cualquier cliente atascado, que es cuestión de tiempo en un despliegue con
    móviles por 4G.
