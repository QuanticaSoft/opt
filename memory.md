# Gyros Agent — memoria del proyecto

> Host: `agent-01` (Ubuntu 22.04, kernel 5.15) — Tailscale IP `100.107.84.95`, usuario `robot`.
> Ruta: `/opt/gyros/agent`. Repo git: `origin git@github.com:QuanticaSoft/opt.git`, rama `develop`.
> Este archivo existe para dar contexto persistente a sesiones de `/loop` (u otras sesiones
> nuevas) que no arrancan con el historial de esta conversación. Mantenerlo actualizado tras
> cada hallazgo relevante — es más barato leer esto que re-explorar todo el proyecto.

## Qué hace este agente

Gyros Agent corre en una máquina física con un teléfono Android conectado por USB
(Alcatel/ZTE, ver `systemd/51-android.rules`). Automatiza la app **UNImóvil Plus** del
Banco Unión (Bolivia) vía `uiautomator2` para:

1. Consultar saldo de una cuenta (`union/main.py`, `POST /consultar-saldo`).
2. Debitar esa cuenta hacia una "cuenta oficina" fija por transferencia ACH
   (`POST /debitar`), usado por el flujo `debitar` del sistema de gestión financiera-logística.

El resultado se expone vía HTTP (Flask, puerto 8080) y se tuneliza por SSH inverso hacia
`flamenco.cnb.net` para que el backend central pueda invocarlo.

## Inventario de servicios (systemd)

| Unit | Script | Rol | Usuario |
|---|---|---|---|
| `gyros-agent.service` | `gyros-agent.pl` | Proceso supervisor: hace `fork()+exec` de `heartbeat.pl` y `detecta.pl`, loguea "alive" cada 60s | root |
| `gyros-heartbeat.service` | `heartbeat.pl` | Heartbeat HTTP a `quanticasoft.com/gyrosfe/agent/heartbeat.php` cada 60s | root |
| `gyros-usb-monitor.service` | `usb-monitor.pl` | Escucha `udevadm monitor`, envía eventos USB por socket TCP crudo a `BACKEND_HOST:BACKEND_PORT` (`config.conf` → `flamenco.cnb.net:4000`) | root |
| `gyros-union-server.service` | `python3 -m union.server` | Servidor Flask (saldo/débito), puerto 8080 local | robot |
| `gyros-tunnel.service` | `autossh` | Túnel SSH inverso `agent-01 → flamenco.cnb.net`, expone el puerto 8080 local en `127.0.0.1:8080` de flamenco | robot |

Comando rápido de salud:
```
systemctl status gyros-agent gyros-heartbeat gyros-usb-monitor gyros-union-server gyros-tunnel --no-pager
```

## Flujo funcional (`union/steps.py`, `union/steps_transferencia.py`)

Pasos 1–10: login + lectura de saldo + cierre de sesión/app (usados tanto por
`consultar-saldo` como como prefijo de `debitar`).
Pasos 11–18: apertura de menú ACH, validación de horario (`FueraDeHorarioACH`),
búsqueda/verificación de destinatario (`DestinatarioNoCoincide`), selección de cuenta
origen, monto/glosa, confirmación y lectura de número de envío.

Cada paso loguea `[PASO N] ...` a stdout → journal de `gyros-union-server`, útil para
diagnosticar en qué punto de la UI se atoró la automatización.

## Conectividad externa

- `flamenco.cnb.net:22` — SSH, usado por el túnel inverso (`id_ed25519_flamenco`) y por
  `usb-monitor.pl` (socket TCP a puerto 4000, no HTTP).
- `quanticasoft.com/gyrosfe/agent/{heartbeat,usb_event}.php` — API HTTP usada por
  `heartbeat.pl` y `detecta.pl`, autenticada con headers `x-agent-id` / `x-agent-token`.

## Secretos (no volcar valores en este archivo ni en el repo)

- `.env` (gitignored): `BU_USUARIO`, `BU_PASSWORD`, `BU_DISPOSITIVO`, `BU_NOMBRE_TITULAR`,
  `BU_OFICINA_ALIAS`, `BU_OFICINA_CUENTA`, `BU_OFICINA_BANCO`, `BU_OFICINA_MONEDA`.
- `/home/robot/.ssh/id_ed25519_flamenco` — llave del túnel inverso.
- `AGENT_TOKEN` hardcodeado en `heartbeat.pl` y `detecta.pl` (ver hallazgo #3).

## Hallazgos abiertos (revisión 2026-07-13)

1. **Túnel inestable ahora mismo**: `gyros-tunnel.service` reinicia en bucle cada 1-4 min
   alternando `remote port forwarding failed for listen port 8080` y
   `Connection timed out` hacia `flamenco.cnb.net:22`. El backend probablemente no puede
   alcanzar el agente durante estas ventanas. Revisar en `flamenco` si otro proceso ocupa
   el puerto 8080 remoto o si hay pérdida de conectividad intermitente hacia esa IP.
   Chequeo: `journalctl -u gyros-tunnel -n 50 --no-pager`.
2. **Procesos duplicados**: `heartbeat.pl` y `detecta.pl` corren dos veces cada uno — una
   copia como hijos forkeados de `gyros-agent.pl` (vía `gyros-agent.service`) y otra
   independiente (`gyros-heartbeat.service`; `detecta.pl` no tiene unit propio pero el
   segundo proceso probablemente es un huérfano de un restart anterior). Causa:
   `gyros-agent.service` es `Type=simple` pero hace fork interno — systemd solo trackea el
   PID del padre, así que al reiniciar el servicio los hijos quedan huérfanos (adoptados
   por PID 1) sin limpiarse. Efecto: heartbeats duplicados al backend. Confirmar con
   `ps aux | grep -E "heartbeat.pl|detecta.pl"`.
3. **Token de agente sin configurar**: `AGENT_TOKEN = 'TOKEN_SECRETO'` en ambos scripts
   Perl parece un placeholder nunca reemplazado por un valor real. Verificar con el backend
   si de verdad valida este header o si el agente está efectivamente sin autenticar.
4. **Dos mecanismos de reporte USB redundantes**: `detecta.pl` (POST a
   `quanticasoft.com/.../usb_event.php`) y `usb-monitor.pl` (socket TCP crudo a
   `flamenco.cnb.net:4000`). No está claro cuál es el vigente/autoritativo — revisar con el
   dueño del backend antes de tocar cualquiera de los dos.
5. **`banco_union/` es código legado**: módulo anterior a `union/` (login+balance sin
   arquitectura de pasos), no lo importa ningún servicio systemd ni `union/*`. Solo
   `setup.py` lo referencia. Candidato a eliminar, pero no borrar sin confirmar con el
   usuario.
6. Repo remoto estaba 2 commits adelante de `origin/develop` sin pushear al momento de esta
   revisión (`29a2db3` es el HEAD local).
7. Backups sueltos en la raíz (`detecta.pl.bak.*`) — ya cubiertos por `.gitignore`
   (`*.bak*`), no se trackean, pero conviene limpiarlos del filesystem.

## Checklist para iteraciones de `/loop` sobre este agente

1. `git -C /opt/gyros/agent status && git -C /opt/gyros/agent log --oneline -5` — detectar
   cambios de otra persona antes de tocar nada.
2. `systemctl status gyros-agent gyros-heartbeat gyros-usb-monitor gyros-union-server gyros-tunnel --no-pager`
3. `journalctl -u gyros-tunnel -n 20 --no-pager` — confirmar si el túnel sigue
   reconectando en bucle (hallazgo #1).
4. `adb devices` — confirmar que el teléfono sigue conectado.
5. `ps aux | grep -E "heartbeat.pl|detecta.pl"` — vigilar acumulación de procesos
   huérfanos (hallazgo #2).
6. `df -h /` — espacio en disco (98G total, ~76G libres a la fecha de esta revisión).
7. Reportar solo lo que cambió respecto a la iteración anterior — evitar ruido si el
   estado es idéntico.
8. No mostrar ni loguear valores de `.env` ni de llaves SSH.
9. No hacer `git push` ni reiniciar servicios sin confirmación explícita del usuario.

## Notas de conexión

Acceso actual por password vía `sshpass`. Para trabajo recurrente con `/loop` conviene
autorizar una llave pública en `~/.ssh/authorized_keys` de `robot@100.107.84.95` y evitar
reutilizar la contraseña en cada sesión.
