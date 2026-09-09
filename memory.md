# Gyros Agent — memoria del proyecto (scz01)

> Host: `scz01` (Ubuntu 26.04, Python 3.14) — Tailscale IP `100.117.246.119`, usuario
> `agentescz1`. Ruta: `/opt/gyros/agent`. Repo git: `origin git@github.com:QuanticaSoft/opt.git`,
> clon independiente del de `cbb01`, rama `nuevo_agente` (creada desde `main`, sin mergear).
> Este archivo es específico de este host — para el historial de incidentes de `cbb01`
> (túnel colgado, procesos duplicados, etc., previos a que existiera `scz01`), ver el
> `memory.md` de ese repo. Este archivo existe para dar contexto persistente a sesiones
> nuevas que no arrancan con el historial de esta conversación.

## Por qué existe este agente

Pedido del usuario: un segundo agente de producción, en Santa Cruz, corriendo **en
paralelo** con `cbb01` (Cochabamba, antes `agent-01`) — no en reemplazo. Ver el `CLAUDE.md`
de este mismo repo para la arquitectura completa (por qué "misma DB y mismo frontend" ya
está resuelto por diseño sin copiar nada, cómo se resuelve el puerto del agente por
dispositivo vía `Agent.tunnelPort` + `UsbDeviceState`, etc.).

## Cómo se armó (2026-09-09)

1. **Acceso SSH**: llave de gestión (`~/.ssh/id_ed25519_gyros`) generada en `scz01` y
   autorizada en `cbb01` y en `marco@flamenco.cnb.net` — usada para inventariar ambos
   hosts y aplicar cambios remotos durante el setup. Llave separada para el túnel del
   propio agente (`~/.ssh/id_ed25519_flamenco`), y llave separada para el deploy key de
   GitHub (`~/.ssh/id_ed25519_opt_deploy`, lectura+escritura, agregada en
   `github.com/QuanticaSoft/opt/settings/keys`) — tres llaves con propósitos distintos,
   no reusar una para otra cosa.
2. **`/opt/gyros`**: no existía, hubo que crearlo con `sudo mkdir` + `sudo chown
   agentescz1:agentescz1` (este host no tiene sudo sin password para `agentescz1`, cada
   paso que lo necesita lo corre el usuario a mano).
3. **Clon del repo** + `git checkout -b nuevo_agente` (mismo nombre de rama local que en
   `cbb01`, pero son historias de commits distintas — al pushear a GitHub cada uno debe ir
   con sufijo propio, `origin/nuevo_agente-scz01` / `origin/nuevo_agente-cbb01`, para no
   pisarse siendo clones del mismo repo remoto).
4. **Config específica de este agente**: `AGENT_ID=scz01` en `config.conf`, `heartbeat.pl`,
   `detecta.pl` (token propio, generado con `openssl rand -hex 32`, no compartido con
   `cbb01` — cada agente tiene su propia fila en la tabla `Agent`). `.env` con solo
   `BU_OFICINA_*`, copiado de `cbb01` por SSH directo (nunca pegado en el chat).
5. **Python 3.14 / Ubuntu 26.04 exige venv (PEP 668)** — a diferencia de `cbb01` (Ubuntu
   22.04, sin esta restricción). `python3 -m venv .venv` falló la primera vez
   ("ensurepip is not available") porque hace falta el paquete `python3.14-venv`
   específico (no alcanza con `python3-venv` genérico). Con eso instalado, `pip install`
   dentro del venv no necesita sudo (el venv queda bajo un directorio que ya es del
   usuario). `gyros-union-server.service` apunta a `.venv/bin/python3`, no a
   `/usr/bin/python3` — si se reinstala el venv desde cero, hay que mantener ese path.
6. **Perl**: `heartbeat.pl`/`detecta.pl` fallaban con "Can't locate LWP/UserAgent.pm" y
   "Can't locate JSON.pm" — Ubuntu 26.04 no trae esos módulos por defecto (22.04 sí, o ya
   estaban instalados en `cbb01` de antes). Se resolvió con
   `sudo apt install -y libwww-perl libjson-perl`.
7. **`gyros-tunnel-cleanup.sh`**: se intentó identificar la sesión SSH huérfana a matar en
   flamenco por el puerto real que tunela este agente (vía `ss -ltnp` corriendo como
   `marco` en flamenco) — **no funciona en ese servidor**: `ss -ltnp` no expone el PID
   dueño del socket para un usuario sin privilegios, y `lsof -p <pid>` da "Permission
   denied" incluso sobre el propio proceso de uno mismo (mismo privilege separation de
   sshd que ya documentó `cbb01/memory.md`, hallazgo #1). Confirmado en vivo probando
   contra el túnel real de `cbb01` (único candidato en ese momento, `ss -ltnp` sin
   columna Process, `lsof -p` con "Permission denied" en los 4 fds). Mitigación aplicada
   (no es un fix perfecto, ver `CLAUDE.md`/`gyrosfe` para el detalle): solo mata si hay
   exactamente una sesión huérfana candidata en ese momento; con 2+ (ambigüedad real, ya
   que ahora hay más de un agente tuneleando a flamenco) no hace nada.
8. **Teléfono real**: un ZTE Blade A34 (serial `NBA34BOAC5036471`, vendor `19d2`, ya
   cubierto por las reglas udev existentes) fue movido físicamente por el usuario desde
   `cbb01` a `scz01` para esta prueba (confirmado por el usuario, no es la reubicación
   real a Santa Cruz todavía). Ya tenía la app **UNImóvil Plus** instalada. Autorización
   ADB (huella RSA) y `python -m uiautomator2 init <serial>` corridos sin problemas;
   `u2.connect(serial)` devuelve info del dispositivo correctamente. Ya existe un cliente
   real (`Cliente.uuid = a9c0d300-...`) con `dispositivo` apuntando a este serial, así que
   en cuanto el evento USB se reportó como `connected` bajo `scz01`, ese cliente pasó a
   rutearse a este agente (puerto 8081) automáticamente — sin tocar nada de la DB a mano
   más allá de la migración inicial.

## Servicios systemd

Ver tabla completa en `CLAUDE.md`. Las unidades `gyros-agent.service` y
`gyros-usb-monitor.service` no venían versionadas en el repo (tampoco lo estaban en
`cbb01` — se agregaron a `systemd/` como parte de este trabajo, tomando como base las que
ya corrían en `cbb01`, adaptando `User=` y paths).

## Chequeo rápido de salud

```bash
systemctl status gyros-agent gyros-usb-monitor gyros-union-server gyros-tunnel --no-pager
journalctl -u gyros-tunnel -n 20 --no-pager
adb devices -l
```

## Pendiente

- Reubicación física real del equipo a Santa Cruz (hoy está en el mismo lugar que
  `cbb01` para esta prueba, según confirmó el usuario). Tailscale ya está conectado y
  debería reconectar solo con la misma IP tras el traslado — no debería requerir
  reconfiguración, pero no se validó un traslado real todavía.
- Validación end-to-end real (consulta de saldo/débito desde el dashboard de gyrosfe para
  el cliente ya asignado a este dispositivo) — no disparada automáticamente, es una acción
  financiera real, queda para que la corra el usuario.
- Decidir cuándo pushear `nuevo_agente` a `origin/nuevo_agente-scz01` y mergear a
  `main`/`develop` en el repo remoto.
- Igual que en `cbb01`: `banco_union/` es legado, no borrar sin confirmar; no hacer `git
  push` ni reiniciar/detener servicios sin confirmación explícita del usuario; nunca
  volcar valores de `.env` ni de llaves SSH.
