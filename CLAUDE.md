# Gyros Agent

Agente de automatización RPA que corre en el host `agent-01` (Ubuntu 22.04, IP Tailscale
`100.107.84.95`). Controla un teléfono Android conectado por USB para automatizar la app
oficial **UNImóvil Plus** del Banco Unión (Bolivia) vía `uiautomator2`/ADB — no usa ninguna
API bancaria, interactúa con la UI real de la app.

Repo: `git@github.com:QuanticaSoft/opt.git`, rama `develop`.

## Qué hace

1. **Consultar saldo** — login en la app + lectura del saldo disponible.
2. **Debitar** — login + transferencia ACH desde la cuenta consultada hacia una "cuenta
   oficina" fija, con verificación de destinatario antes de confirmar.

Expuesto como API HTTP local (Flask, puerto 8080) y publicado hacia el backend central vía
túnel SSH reverso a `flamenco.cnb.net`.

## Stack

- **Automatización Android**: Python + `uiautomator2` + ADB (`requirements.txt`:
  `uiautomator2>=2.16`, `python-dotenv>=1.0`)
- **API HTTP**: Flask (`union/server.py`, puerto 8080, `threaded=True`)
- **Config/secretos**: `python-dotenv`, archivo `.env` (gitignored)
- **Watchdogs/reporting**: Perl (`LWP::UserAgent`, `udevadm monitor`)
- **Conectividad saliente**: túnel SSH reverso (systemd + `ssh` directo, `Restart=always`);
  socket TCP crudo a `flamenco.cnb.net:4000`
- **Orquestación**: systemd
- **VPN/acceso remoto**: Tailscale

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
├── config.conf                 # AGENT_ID, BACKEND_HOST, BACKEND_PORT, HEARTBEAT_INTERVAL
├── systemd/                    # Unit files versionados (no todos los desplegados están aquí)
├── memory.md                   # Bitácora operativa: historial de incidentes, hallazgos,
│                                #   checklist de salud. Ver abajo — NO es redundante con este archivo.
└── logs/                       # gitignored
```

## Servicios systemd

| Unit | Script | Rol | Usuario | Estado esperado |
|---|---|---|---|---|
| `gyros-agent.service` | `gyros-agent.pl` | Supervisor: fork+exec de `heartbeat.pl` y `detecta.pl` | root | activo |
| `gyros-usb-monitor.service` | `usb-monitor.pl` | Eventos USB → `flamenco.cnb.net:4000` (TCP crudo) | root | activo |
| `gyros-union-server.service` | `python3 -m union.server` | API Flask saldo/débito, puerto 8080 | robot | activo |
| `gyros-tunnel.service` | `ssh -N -R 127.0.0.1:8080:...` | Túnel SSH reverso hacia flamenco | robot | activo |
| `gyros-heartbeat.service` | `heartbeat.pl` | Duplicado — deshabilitado 2026-07-13 | root | **inactive/disabled** |
| `usb-agent.service` (sin prefijo `gyros-`) | `detecta.pl` | Duplicado — deshabilitado 2026-07-13 | root | **inactive/disabled** |

Chequeo rápido de salud:
```bash
systemctl status gyros-agent gyros-usb-monitor gyros-union-server gyros-tunnel --no-pager
systemctl status gyros-heartbeat usb-agent --no-pager   # deben mostrar inactive/disabled
ps -o pid,ppid,cmd -e | grep -E "heartbeat.pl|detecta.pl"   # exactamente 2 procesos, PPID = PID de gyros-agent.pl
adb devices
journalctl -u gyros-tunnel -n 20 --no-pager
```

## API (`union/server.py`)

- `POST /consultar-saldo` — body: `usuario`, `password`, `nombre_titular`, `dispositivo` → `{"ok": true, "saldo": "..."}`
- `POST /debitar` — body: ídem + `monto`, `fecha_pago` (YYYY-MM-DD) → `{"ok": true, "numero_envio": "...", "monto": "..."}`
  - Errores de negocio devuelven HTTP 409: `FueraDeHorarioACH`, `DestinatarioNoCoincide`.
  - Lock por serial ADB: dispositivos distintos corren en paralelo; el mismo dispositivo no atiende dos solicitudes a la vez.

## Variables de entorno (`.env`, gitignored — nunca loguear ni volcar valores)

`BU_USUARIO`, `BU_PASSWORD`, `BU_DISPOSITIVO`, `BU_NOMBRE_TITULAR`, `BU_OFICINA_ALIAS`,
`BU_OFICINA_CUENTA`, `BU_OFICINA_BANCO`, `BU_OFICINA_MONEDA`.

## Conectividad externa

- `flamenco.cnb.net:22` — SSH, túnel reverso (`~/.ssh/id_ed25519_flamenco`) + socket TCP de `usb-monitor.pl` (puerto 4000).
- `quanticasoft.com/gyrosfe/agent/{heartbeat,usb_event}.php` — API HTTP de `heartbeat.pl`/`detecta.pl`, autenticada con headers `x-agent-id`/`x-agent-token`.

## Reglas de seguridad para trabajar en este repo

- **Nunca** mostrar ni loguear valores de `.env` ni de llaves SSH (`~/.ssh/id_ed25519_flamenco`).
- **No** hacer `git push` ni reiniciar/detener servicios systemd sin confirmación explícita del usuario.
- `banco_union/` es legado — no borrar sin confirmar con el usuario aunque no lo use nada.
- El directorio `/opt/gyros/agent` es `root:root` sin escritura para "otros"; el usuario `robot` no tiene sudo sin contraseña — cambios que requieran escritura ahí (o en `/etc/systemd/system/`) necesitan que el usuario los aplique con `sudo` él mismo.

## Historial de incidentes y contexto operativo

Ver **`memory.md`** en esta misma carpeta — bitácora con el diagnóstico completo de incidentes
resueltos (colgado del túnel SSH tras cortes de red, procesos duplicados, token de agente sin
configurar, mecanismos redundantes de reporte USB), notas de conexión a `flamenco.cnb.net` y
checklist detallado para revisiones periódicas. Este `CLAUDE.md` documenta arquitectura/stack
(derivable del código); `memory.md` documenta el **por qué** de decisiones pasadas y hallazgos
que no son reconstruibles solo leyendo el código — se mantienen como archivos separados y
complementarios.
