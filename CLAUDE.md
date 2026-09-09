# Gyros Agent — scz01 (Santa Cruz)

Agente de automatización RPA que corre en el host `scz01` (Ubuntu 26.04, IP Tailscale
`100.117.246.119`, usuario `agentescz1`). Controla un teléfono Android conectado por USB
para automatizar la app oficial **UNImóvil Plus** del Banco Unión (Bolivia) vía
`uiautomator2`/ADB — no usa ninguna API bancaria, interactúa con la UI real de la app.

Creado el 2026-09-09 como segundo agente de producción, **en paralelo** con `cbb01`
(Cochabamba, antes `agent-01`) — mismo repo, misma base de datos y mismo frontend
(`gyrosfe` en flamenco), cada uno con su propio teléfono y su propio puerto de túnel.
Detalle completo del porqué y cómo en `memory.md`.

Repo: `git@github.com:QuanticaSoft/opt.git` — clon independiente del de `cbb01`, en la
rama `nuevo_agente` (creada desde `main`, sin mergear todavía — ver `memory.md`).

## Qué hace

1. **Consultar saldo** — login en la app + lectura del saldo disponible.
2. **Debitar** — login + transferencia ACH desde la cuenta consultada hacia una "cuenta
   oficina" fija (**la misma cuenta real que usa `cbb01`**, no una propia), con
   verificación de destinatario antes de confirmar.

Expuesto como API HTTP local (Flask, puerto 8080) y publicado hacia el backend central vía
túnel SSH reverso a `flamenco.cnb.net` — a diferencia de `cbb01` (puerto remoto 8080), este
agente tunela al puerto remoto **8081** (`Agent.tunnelPort` en la DB de gyrosfe).

## Stack

- **Automatización Android**: Python + `uiautomator2` + ADB (mismas versiones que
  `cbb01`: `uiautomator2==3.5.0`, `python-dotenv==1.2.2`, `Flask==3.1.3`)
- **Entorno Python**: venv en `.venv/` (`/opt/gyros/agent/.venv`) — **necesario en este
  host** (Ubuntu 26.04 / Python 3.14 exige PEP 668, `pip install` global falla sin esto;
  `cbb01` es Ubuntu 22.04 y no lo necesitaba). `gyros-union-server.service` usa
  `.venv/bin/python3`, no `/usr/bin/python3`.
- **API HTTP**: Flask (`union/server.py`, puerto 8080 local, `threaded=True`)
- **Config/secretos**: `python-dotenv`, archivo `.env` (gitignored, solo
  `BU_OFICINA_ALIAS/CUENTA/BANCO/MONEDA` — copiados directo de `cbb01` por SSH, nunca
  pegados en un chat; `BU_USUARIO/PASSWORD/DISPOSITIVO/NOMBRE_TITULAR` no hacen falta,
  `union/server.py` los recibe por request, solo los usaría `union/main.py` standalone)
- **Watchdogs/reporting**: Perl (`LWP::UserAgent`, `udevadm monitor`) — requiere paquetes
  `libwww-perl` y `libjson-perl` (no vienen por defecto en Ubuntu 26.04, sí en 22.04)
- **Conectividad saliente**: túnel SSH reverso (systemd + `ssh` directo, `Restart=always`,
  llave dedicada `~/.ssh/id_ed25519_flamenco` — **distinta** de la de `cbb01`); socket TCP
  crudo a `flamenco.cnb.net:4000`
- **Orquestación**: systemd
- **VPN/acceso remoto**: Tailscale (ya conectado al mismo tailnet que `cbb01` y demás
  máquinas de QuanticaSoft — al reubicar físicamente este equipo a Santa Cruz basta un
  cable con salida a internet, sin reconfiguración de VPN)

## Estructura de directorios

Igual que `cbb01` (mismo repo) — ver su `CLAUDE.md`/`memory.md` para el detalle de
`union/`, `banco_union/` (legado), scripts Perl, etc. No se repite acá.

## Servicios systemd

| Unit | Script | Rol | Usuario | Estado esperado |
|---|---|---|---|---|
| `gyros-agent.service` | `gyros-agent.pl` | Supervisor: fork+exec de `heartbeat.pl` y `detecta.pl` | root | activo |
| `gyros-usb-monitor.service` | `usb-monitor.pl` | Eventos USB → `flamenco.cnb.net:4000` (TCP crudo) | root | activo |
| `gyros-union-server.service` | `.venv/bin/python3 -m union.server` | API Flask saldo/débito, puerto 8080 local | agentescz1 | activo |
| `gyros-tunnel.service` | `ssh -N -R 127.0.0.1:8081:127.0.0.1:8080 ...` | Túnel SSH reverso hacia flamenco (puerto remoto **8081**, no 8080) | agentescz1 | activo |

Chequeo rápido de salud:
```bash
systemctl status gyros-agent gyros-usb-monitor gyros-union-server gyros-tunnel --no-pager
adb devices
journalctl -u gyros-tunnel -n 20 --no-pager
```

## API (`union/server.py`)

Idéntica a `cbb01` — `POST /consultar-saldo`, `POST /debitar`. Ver su `CLAUDE.md` para el
contrato exacto.

## Variables de entorno (`.env`, gitignored — nunca loguear ni volcar valores)

Solo `BU_OFICINA_ALIAS`, `BU_OFICINA_CUENTA`, `BU_OFICINA_BANCO`, `BU_OFICINA_MONEDA` —
copiados de `cbb01`, misma cuenta real.

## Conectividad externa

- `flamenco.cnb.net:22` — SSH, túnel reverso (`~/.ssh/id_ed25519_flamenco`, propia de este
  agente) + socket TCP de `usb-monitor.pl` (puerto 4000).
- `quanticasoft.com/gyrosfe/agent/{heartbeat,usb_event}.php` — API HTTP de
  `heartbeat.pl`/`detecta.pl`, autenticada con headers `x-agent-id: scz01` /
  `x-agent-token` (token propio, generado con `openssl rand -hex 32`, no compartido con
  `cbb01`).

## Reglas de seguridad para trabajar en este repo

Mismas que `cbb01` (ver su `CLAUDE.md`): nunca mostrar/loguear `.env` ni llaves SSH; no
hacer `git push` ni reiniciar/detener servicios systemd sin confirmación explícita del
usuario; `banco_union/` es legado, no borrar sin confirmar.

## Historial de incidentes y contexto operativo

Ver **`memory.md`** en esta misma carpeta.
