# Gyros Agent

Agente de automatización RPA que controla un teléfono Android conectado por USB para
automatizar la app oficial **UNImóvil Plus** del Banco Unión (Bolivia) vía
`uiautomator2`/ADB — no usa ninguna API bancaria, interactúa con la UI real de la app.

Este repo se despliega en **más de un host en paralelo** (no es un servidor único): hoy,
`cbb01` (Cochabamba) y `scz01` (Santa Cruz), cada uno con su propio teléfono. Desde
2026-09-10, **todo lo que distingue a un host de otro vive en `.env`** (gitignored) — el
resto del código (Perl, systemd, Python) es idéntico entre hosts. La única excepción
inevitable es `User=` en las unidades systemd (systemd no permite leerlo de
`EnvironmentFile=`), documentada con un comentario en cada unit.

## Hosts desplegados

| Host | Ciudad | Tailscale IP | Usuario systemd | `AGENT_ID` | Puerto túnel remoto |
|---|---|---|---|---|---|
| `agent-01` (hostname OS) | Cochabamba | `100.107.84.95` | `robot` | `cbb01` | 8080 |
| `scz01` | Santa Cruz | `100.117.246.119` | `agentescz1` | `scz01` | 8081 |

Cada uno es un **clon local independiente** de este mismo repo (no hay un working copy
compartido) — commits y ramas pueden divergir levemente entre hosts si alguno necesita un
ajuste puntual, pero el código versionado apunta a mergear limpio a `main` porque ya no
hay valores hardcodeados por host.

## Qué hace

1. **Consultar saldo** — login en la app + lectura del saldo disponible.
2. **Debitar** — login + transferencia ACH desde la cuenta consultada hacia una "cuenta
   oficina" fija (**la misma cuenta real en todos los hosts**, no una propia por host),
   con verificación de destinatario antes de confirmar.

Expuesto como API HTTP local (Flask, puerto 8080 local en todos los hosts) y publicado
hacia el backend central vía túnel SSH reverso a `flamenco.cnb.net` — cada host tunela a
su propio puerto remoto (`Agent.tunnelPort` en la DB de gyrosfe, ver tabla arriba).
`api/consulta_saldo.php`/`debitar.php` en gyrosfe resuelven ese puerto dinámicamente según
qué host tiene conectado el dispositivo del cliente en ese momento (vía
`UsbDeviceState`) — no asumen un solo agente.

## Stack

- **Automatización Android**: Python + `uiautomator2==3.5.0` + ADB
  (`python-dotenv==1.2.2`, `Flask==3.1.3`)
- **Entorno Python**: directo (`/usr/bin/python3`) en hosts sin restricción PEP 668
  (ej. `cbb01`, Ubuntu 22.04), o venv (`.venv/`) en hosts que sí la tienen (ej. `scz01`,
  Ubuntu 26.04 / Python 3.14) — el binario correcto se configura una vez en `.env`
  (`PYTHON_BIN`), el resto del código no cambia.
- **API HTTP**: Flask (`union/server.py`, puerto 8080 local, `threaded=True`)
- **Config/secretos**: `python-dotenv` (lado Python) + parser propio en Perl (`.pl`,
  función `read_kv_file`), ambos leen el mismo `.env` (gitignored)
- **Watchdogs/reporting**: Perl (`LWP::UserAgent`, `JSON`, `udevadm monitor`) — requiere
  paquetes de sistema `libwww-perl`/`libjson-perl` (no vienen por defecto en todas las
  versiones de Ubuntu, ver por host si hace falta instalarlos)
- **Conectividad saliente**: túnel SSH reverso (systemd + `ssh` directo, `Restart=always`,
  llave y puerto propios de cada host vía `.env`); socket TCP crudo a
  `flamenco.cnb.net:4000`
- **Orquestación**: systemd
- **VPN/acceso remoto**: Tailscale (mismo tailnet en todos los hosts — reubicar
  físicamente una máquina solo requiere un cable con salida a internet, sin
  reconfiguración de VPN)

## Estructura de directorios

```
/opt/gyros/agent/
├── union/                    # Flujo vigente (arquitectura de pasos 1-18)
│   ├── main.py                #   CLI: consulta de saldo standalone
│   ├── server.py               #   API Flask: POST /consultar-saldo, POST /debitar
│   ├── config.py               #   Config (BU_*) + OficinaConfig (BU_OFICINA_*)
│   ├── device.py               #   Conexión ADB/uiautomator2 (usa BU_DISPOSITIVO o auto)
│   ├── steps.py                #   Pasos 1-10: login, leer saldo, cerrar sesión/app
│   ├── steps_transferencia.py  #   Pasos 11-18: menú ACH, destinatario, monto, confirmar
│   └── start_server.sh
├── banco_union/               # LEGADO — no lo importa ningún servicio ni union/*.
│   └── ...                    #   Versión previa (login+balance sin pasos). No borrar sin confirmar.
├── gyros-agent.pl             # Supervisor: fork+exec de heartbeat.pl y detecta.pl
├── heartbeat.pl                # Heartbeat HTTP -> quanticasoft.com/gyrosfe/agent/heartbeat.php
├── detecta.pl                  # Detección USB -> quanticasoft.com/gyrosfe/agent/usb_event.php
├── usb-monitor.pl              # Detección USB -> socket TCP crudo a flamenco.cnb.net:4000
├── config.conf                 # BACKEND_HOST, BACKEND_PORT, HEARTBEAT_INTERVAL (igual en todos los hosts)
├── .env                        # gitignored — TODO lo que difiere por host, ver abajo
├── systemd/                    # Unit files versionados, genéricos (leen de .env)
├── memory.md                   # Bitácora operativa compartida: historial de incidentes,
│                                #   hallazgos, checklist de salud, por host cuando aplica.
└── logs/                       # gitignored
```

## Servicios systemd

| Unit | Script | Rol | Usuario | Estado esperado |
|---|---|---|---|---|
| `gyros-agent.service` | `gyros-agent.pl` | Supervisor: fork+exec de `heartbeat.pl` y `detecta.pl` | root | activo |
| `gyros-usb-monitor.service` | `usb-monitor.pl` | Eventos USB → `flamenco.cnb.net:4000` (TCP crudo) | root | activo |
| `gyros-union-server.service` | `${PYTHON_BIN} -m union.server` (vía `/usr/bin/env`) | API Flask saldo/débito, puerto 8080 local | *(host)* | activo |
| `gyros-tunnel.service` | `ssh -N -R 127.0.0.1:${TUNNEL_REMOTE_PORT}:127.0.0.1:8080 ...` | Túnel SSH reverso hacia flamenco | *(host)* | activo |

`User=` en `gyros-union-server.service`/`gyros-tunnel.service` es la única línea que se
edita a mano por host (systemd no permite leerla de `EnvironmentFile=`) — cada unit trae
un comentario recordándolo.

Chequeo rápido de salud:
```bash
systemctl status gyros-agent gyros-usb-monitor gyros-union-server gyros-tunnel --no-pager
adb devices
journalctl -u gyros-tunnel -n 20 --no-pager
```

## API (`union/server.py`)

- `POST /consultar-saldo` — body: `usuario`, `password`, `nombre_titular`, `dispositivo` → `{"ok": true, "saldo": "..."}`
- `POST /debitar` — body: ídem + `monto`, `fecha_pago` (YYYY-MM-DD) → `{"ok": true, "numero_envio": "...", "monto": "..."}`
  - Errores de negocio devuelven HTTP 409: `FueraDeHorarioACH`, `DestinatarioNoCoincide`.
  - Lock por serial ADB: dispositivos distintos corren en paralelo; el mismo dispositivo no atiende dos solicitudes a la vez.

## Variables de entorno (`.env`, gitignored — nunca loguear ni volcar valores)

Todo lo que antes estaba hardcodeado en código, ahora vive acá — es lo único que hace
falta cambiar para desplegar este repo en un host nuevo:

| Variable | Qué es | Ejemplo |
|---|---|---|
| `AGENT_ID` | Identificador del agente (tabla `Agent` de gyrosfe) | `cbb01`, `scz01` |
| `AGENT_TOKEN` | Token de autenticación de `heartbeat.pl`/`detecta.pl` (debe coincidir con `Agent.token` en la DB) | generado con `openssl rand -hex 32` |
| `TUNNEL_SSH_KEY` | Ruta a la llave privada del túnel reverso hacia flamenco | `/home/robot/.ssh/id_ed25519_flamenco` |
| `TUNNEL_REMOTE_PORT` | Puerto remoto en flamenco (debe coincidir con `Agent.tunnelPort` en la DB) | `8080`, `8081` |
| `PYTHON_BIN` | Binario de Python para `gyros-union-server.service` | `/usr/bin/python3` o `/opt/gyros/agent/.venv/bin/python3` |
| `BU_OFICINA_ALIAS`/`CUENTA`/`BANCO`/`MONEDA` | Cuenta oficina destino del débito ACH — **misma cuenta real en todos los hosts** | — |
| `BU_USUARIO`/`PASSWORD`/`DISPOSITIVO`/`NOMBRE_TITULAR` | Solo para `union/main.py` (CLI standalone); el flujo real vía `server.py` los recibe por request | opcional |

## Conectividad externa

- `flamenco.cnb.net:22` — SSH, túnel reverso (llave de `TUNNEL_SSH_KEY`) + socket TCP de
  `usb-monitor.pl` (puerto 4000, `config.conf`).
- `quanticasoft.com/gyrosfe/agent/{heartbeat,usb_event}.php` — API HTTP de
  `heartbeat.pl`/`detecta.pl`, autenticada con headers `x-agent-id`/`x-agent-token`
  (de `.env`).

## Reglas de seguridad para trabajar en este repo

- **Nunca** mostrar ni loguear valores de `.env` ni de llaves SSH.
- **No** hacer `git push` ni reiniciar/detener servicios systemd sin confirmación
  explícita del usuario.
- `banco_union/` es legado — no borrar sin confirmar con el usuario aunque no lo use nada.
- `/opt/gyros/agent` suele ser `root:root` sin escritura para "otros"; el usuario de
  servicio no siempre tiene sudo sin contraseña — cambios que requieran escritura en
  `/etc/systemd/system/` o instalar paquetes necesitan que el usuario los aplique con
  `sudo` él mismo.

## Historial de incidentes y contexto operativo

Ver **`memory.md`** en esta misma carpeta — bitácora compartida entre hosts con el
diagnóstico completo de incidentes resueltos, notas de conexión, y checklist para
revisiones periódicas. Este `CLAUDE.md` documenta arquitectura/stack (derivable del
código); `memory.md` documenta el **por qué** de decisiones pasadas y hallazgos que no
son reconstruibles solo leyendo el código.
