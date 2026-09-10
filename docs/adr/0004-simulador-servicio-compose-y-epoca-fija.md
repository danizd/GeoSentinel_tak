# ADR 0004 — Simulador: servicio de compose con perfil y anclaje a época fija

- **Estado:** Aceptado (2026-08)
- **Contexto:** El simulador de telemetría CoT debe correr tanto en el PC del operador (pruebas manuales contra el dominio) como en el servidor (escenario 24/7 sin depender de que el PC esté despierto). Además, con UIDs deterministas, un reinicio del simulador no debe mover los helicópteros en el mapa de WinTAK.
- **Decisión:**
  - El simulador es un **servicio de compose con `profiles: ["sim"]`**: mismo `simulator.py`, misma imagen base de Python, activable con `docker compose --profile sim up -d` y apuntando al host interno `freetakserver:8087` por la red Docker (sin salir del host ni atravesar NPM). En el PC corre con el host externo.
  - La posición orbital es **función de la hora UNIX** (época fija), no de un contador desde el arranque: `posición = f(t)`. Un reinicio es invisible en WinTAK y dos instancias concurrentes producen telemetría idéntica.
  - Los **UIDs son deterministas** (derivados del nombre del escenario + callsign, no `uuid4()`), para que WinTAK no acumule contactos fantasma entre reinicios.
- **Consecuencias:** el bucle no lleva estado acumulado (solo `t`), el mismo script sirve PC y servidor cambiando una variable, y el perfil `sim` no consume CPU hasta que se activa.
- **Alternativas descartadas:** systemd con Python del host (duplica el entorno y sale del ecosistema compose), `uuid4()` por ejecución (fantasmas en WinTAK), contador desde el arranque (salto de fase visible en cada reinicio).
