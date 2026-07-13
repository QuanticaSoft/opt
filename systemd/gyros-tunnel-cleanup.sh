#!/bin/bash
# Libera el puerto 8080 en flamenco antes de iniciar el tunel.
#
# La sesion de autossh (-N, sin comando ni pty) queda registrada en
# flamenco como "sshd-session: marco" a secas, sin tty asignada
# (columna TTY = "?"). Una sesion interactiva real tendria una pty
# (pts/N); una ejecucion de comando puntual aparece como
# "sshd-session: marco@notty". Filtrar por titulo exacto + tty "?"
# es la unica forma fiable de aislar el tunel huerfano sin arriesgar
# sesiones legitimas de marco, ya que sshd oculta el resto del
# argv por privilege separation (ver memory.md, hallazgo tunel 2026-07-13).
#
# Si no hay nada que matar, no hace nada (OK).
ssh -i /home/robot/.ssh/id_ed25519_flamenco \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=10 \
    -o BatchMode=yes \
    marco@flamenco.cnb.net bash -s 2>/dev/null <<'REMOTE' || true
ps -u marco -o pid=,tty=,args= | while read -r pid tty rest; do
    if [ "$tty" = "?" ] && [ "$rest" = "sshd-session: marco" ]; then
        kill "$pid" 2>/dev/null
    fi
done
REMOTE

# Espera breve para que flamenco libere el puerto
sleep 3
