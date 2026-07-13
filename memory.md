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

## Hallazgos

1. **[RESUELTO 2026-07-13] Túnel se queda colgado tras un corte de red.**
   Causa raíz confirmada: `flamenco.cnb.net` **no se cae** (826 días de uptime sin reboot).
   Lo que pasa es un corte de red transitorio entre el cliente (`agent-01` o cualquier
   origen) y flamenco; `autossh` detecta la conexión muerta vía `ServerAliveInterval` y
   reconecta del lado del agente, pero la sesión SSH vieja del lado de **flamenco** queda
   huérfana reteniendo el bind de `127.0.0.1:8080` (nadie le avisó que el cliente se fue).
   Los reintentos posteriores fallan con `remote port forwarding failed for listen port 8080`
   hasta que esa sesión muere o se mata a mano.

   Diagnóstico: en flamenco, `sshd` reescribe el título del proceso por privilege
   separation, así que no se puede distinguir la sesión del túnel por su comando. La única
   señal fiable es la columna TTY: la sesión de solo-reenvío (`-N`, sin comando ni pty)
   aparece como `sshd-session: marco` con TTY `?`; una sesión interactiva real tendría una
   pty (`pts/N`); una ejecución de comando puntual aparece como `sshd-session: marco@notty`.

   Fix aplicado: `systemd/gyros-tunnel-cleanup.sh` ahora mata exactamente esa sesión
   (título exacto + tty `?`) en vez del patrón viejo `sshd.*notty`, que nunca coincidía con
   nada real (commit `ad745b3`, pusheado a `origin/develop`).

   **Fix estructural aplicado (2026-07-13, commit `4eebddf`)**: `gyros-tunnel.service`
   reemplazó `autossh` por `ssh` directo bajo `Restart=always` (+ `StartLimitIntervalSec=0`
   para que systemd nunca se rinda, igual que hacía `autossh`). `autossh` corría con
   `-M 0` (su propio monitor-port deshabilitado), así que solo aportaba "reiniciar ssh si
   muere" — algo que systemd ya hacía solo. El problema real era que `ExecStartPre`
   (la limpieza) solo se disparaba al (re)iniciar el *unit* completo, nunca cuando
   `autossh` reconectaba internamente (su proceso padre nunca moría). Con `ssh` directo,
   cualquier caída del proceso hace que systemd reinicie el unit completo y vuelva a
   correr `ExecStartPre` en cada intento — **verificado matando el proceso ssh a la
   fuerza** (`kill -9`): systemd detectó la caída, corrió el cleanup, y reconectó solo en
   ~15s sin intervención manual. Ya no debería requerir un restart manual ante un corte de
   red futuro.

   Alternativa de raíz descartada por ahora: `ClientAliveInterval`/`ClientAliveCountMax`
   en el `sshd_config` de flamenco resolvería esto del lado servidor sin importar el
   cliente. No se aplicó porque **`marco` no tiene sudo en flamenco** (confirmado:
   "marco is not in the sudoers file. This incident has been reported to the
   administrator." — no reintentar sudo ahí sin credenciales de un usuario que sí sea
   sudoer, para no seguir generando alertas de seguridad).

   Chequeo rápido: `journalctl -u gyros-tunnel -n 30 --no-pager`. Si reaparece
   "remote port forwarding failed", correr `systemctl restart gyros-tunnel` (pide sudo).

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
3. `journalctl -u gyros-tunnel -n 20 --no-pager` — el servicio ahora es autosanable
   (hallazgo #1): `ssh` directo + `Restart=always` reejecuta `ExecStartPre` en cada
   reconexión, así que un `remote port forwarding failed` aislado debería resolverse
   solo en ~15s sin intervención. Si el patrón se repite en bucle por más de un par de
   minutos, ahí sí investigar (podría ser flamenco realmente caído, no solo una sesión
   huérfana).
4. `adb devices` — confirmar que el teléfono sigue conectado.
5. `ps aux | grep -E "heartbeat.pl|detecta.pl"` — vigilar acumulación de procesos
   huérfanos (hallazgo #2).
6. `df -h /` — espacio en disco (98G total, ~76G libres a la fecha de esta revisión).
7. Reportar solo lo que cambió respecto a la iteración anterior — evitar ruido si el
   estado es idéntico.
8. No mostrar ni loguear valores de `.env` ni de llaves SSH.
9. No hacer `git push` ni reiniciar servicios sin confirmación explícita del usuario.

## Notas de conexión

- `robot@100.107.84.95` (agent-01): acceso por llave pública ya autorizado en
  `~/.ssh/authorized_keys` (2026-07-13) — no hace falta password para entrar.
- `marco@flamenco.cnb.net`: solo alcanzable con la llave dedicada del túnel
  (`/home/robot/.ssh/id_ed25519_flamenco`, vive en agent-01, no localmente). Para
  diagnosticar flamenco desde una sesión nueva, saltar por agent-01:
  `ssh robot@100.107.84.95 "ssh -i /home/robot/.ssh/id_ed25519_flamenco -o BatchMode=yes marco@flamenco.cnb.net 'comando'"`.
  Este salto es lento (~15-20s por llamada) — agrupar varios chequeos en un solo comando
  remoto en vez de hacer llamadas sueltas.
- **`marco` no tiene sudo en flamenco** (confirmado 2026-07-13: "marco is not in the
  sudoers file. This incident has been reported to the administrator."). No reintentar
  sudo ahí sin credenciales de un usuario que sí sea sudoer real — ya generó una alerta de
  seguridad una vez. Cambios que requieran root en flamenco (p.ej. `sshd_config`) necesitan
  que el usuario los aplique él mismo o dé acceso a otra cuenta con sudo real.
- flamenco tiene otros servicios corriendo para `marco` (PM2, VSCode Server, `php-fpm:
  pool gyros`) — cualquier limpieza de sesiones/procesos ahí debe ser quirúrgica, nunca
  un pattern-match amplio (ver hallazgo #1 sobre por qué `ps`/título de proceso no alcanza
  para distinguir sesiones).
