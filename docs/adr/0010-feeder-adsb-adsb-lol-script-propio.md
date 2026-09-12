# ADR 0010 — Feeder ADS-B propio sobre adsb.lol (el feeder de terceros está retirado)

- **Estado:** Aceptado (2026-09)
- **Contexto:** Se quiere mostrar tráfico aéreo **real** en el mapa, como
  complemento a los helicópteros sintéticos (ADR 0004) y al feeder OSINT
  deepstatemap.live (ADR 0009). El camino natural era reutilizar el patrón ya
  montado: el feeder deepstate es de la familia `sgofferj/tak-feeder-*`, y esa
  familia tiene un hermano específico para ADS-B (`tak-feeder-adsb-one`) que
  encajaría sin tocar nada más que un servicio nuevo.
  Al verificarlo contra el repositorio upstream, ese feeder está **retirado**:
  adsb.one se fusionó con airplanes.live, su API se apagó el **01-DIC-2025** y
  el autor archivó el proyecto (menciona que unificará el soporte de varios
  proveedores, incluidos de pago, en otro proyecto).
  Verificado en el momento de decidir, con peticiones reales:
  - `https://api.airplanes.live/v2/point/...` → **403** con un mensaje pidiendo
    contactar por email (no es utilizable como fuente desatendida).
  - `https://opendata.adsb.fi/api/v2/point/...` → **400**.
  - `https://api.adsb.lol/v2/point/42.5/-8.5/60` → **200 sin clave de API**, y
    desde una IP de datacenter (mismo perfil de red que el Oracle Free Tier del
    despliegue), devolviendo `{"ac":[...]}` con `hex`, `flight`, `t`, `lat`,
    `lon`, `alt_baro`, `alt_geom`, `gs`, `track`, `squawk` y `category`.
  La alternativa "seria" (`adsbcot`, de Sensors & Signals) soporta adsb.lol de
  forma indirecta (es compatible con la API de ADSBExchange v2) pero su
  documentación **no publica imagen Docker**: la sección Docker indica
  construirla desde el repositorio (`docker/Dockerfile`), lo que introduce un
  build propio que ADR 0001 quiere evitar, y su configuración de agregadores
  abiertos no está documentada.
- **Decisión:**
  - Escribir un feeder propio, **`adsb-feeder.py`**, con **solo la librería
    estándar** (como `cot-relay.py` y `simulator.py`): consulta periódica a
    adsb.lol, conversión a CoT y envío por TCP al relay.
  - Añadirlo como servicio **`adsb`** en el compose, apuntando a
    `cot-relay:8087` por la red Docker interna. **Sin TLS**: a diferencia del
    feeder deepstate (que solo habla `ssl://`), este solo lee la API por HTTPS
    y escribe CoT en la red interna, así que no necesita certificados.
  - **UID determinista** por `hex` ICAO de 24 bits (`geosentinel-adsb.<hex>`):
    el identificador de una aeronave no cambia, así que WinTAK actualiza el
    mismo contacto en lugar de acumular fantasmas (ADR 0004).
  - **Tipo CoT** `a-f-A-C-F` (ala fija) o `a-f-A-C-H` (helicóptero), decidido
    por la categoría ADS-B `A7` con respaldo en el designador ICAO de tipo.
  - **Sin `endpoint` ni `__group`** en el `<detail>` y sin prólogo `<?xml?>` por
    evento: las dos decisiones ya documentadas en el simulador (símbolo 2525 en
    vez de team member; stream parseable por WinTAK).
  - Se descartan las aeronaves **en tierra** (`alt_baro: "ground"`) o sin
    altitud, para no llenar el mapa de contactos inmóviles en los aeropuertos.
- **Verificación:**
  - Prueba de extremo a extremo contra un **relay falso local**: 2 eventos
    entregados, **XML válido** (parseado con `xml.etree`), UIDs
    `geosentinel-adsb.4ca80c` y `geosentinel-adsb.407793`, tipo `a-f-A-C-F`,
    con aeronaves reales (p. ej. `RYR421P`, un B738 de Ryanair en descenso
    sobre Vigo a ~1.960 m HAE).
  - Comportamiento ante fallo comprobado de verdad: en las pruebas en ráfaga la
    API devolvió **HTTP 429**; el feeder lo registra, hace backoff exponencial
    (30 s, hasta 300 s) y **no muere** ni deja el socket en mal estado. Una
    petición posterior volvió a dar 200.
  - `ADSB_MAX_AIRCRAFT` acota el ciclo: 49 aeronaves en el radio con tope 2 →
    solo 2 eventos por ciclo.
- **Consecuencias:**
  - Tráfico aéreo real en el mapa con ~50 aeronaves típicas en 60 nm, con el
    ciclo de 10 s cubierto por el `stale` de 60 s (los contactos no parpadean).
  - El despliegue depende de un **servicio comunitario** (adsb.lol, datos ODbL):
    si limita o desaparece, hay que subir `ADSB_POLL_INTERVAL` o cambiar
    `ADSB_API_URL`. Por eso es un servicio **opcional** y aislado: pararlo con
    `docker compose stop adsb` no afecta a nada más.
  - Atribución: los datos son de adsb.lol (ODbL). No se redistribuyen, solo se
    consultan y se muestran en el mapa.
- **Alternativas descartadas:**
  - `tak-feeder-adsb-one` (imagen oficial, encajaría con el patrón ADR 0009):
    **API apagada el 01-DIC-2025 y proyecto retirado** por su autor.
  - `adsbcot` (snstac): sin imagen Docker publicada (build propio desde su
    repositorio) y sin documentación de agregadores abiertos; además obliga a
    `pip install` en el arranque, un patrón que ningún servicio del despliegue
    usa hoy.
  - Airplanes.Live como fuente directa: responde **403** pidiendo contacto
    previo por email, así que no vale para un servicio desatendido.
  - Consultar la API desde el PC y enviar CoT desde allí: añade un componente
    en el cliente, rompe el patrón "feeder en el servidor" y depende de que el
    PC esté encendido.
