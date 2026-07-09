#!/bin/bash
# Libera el puerto 8080 en flamenco antes de iniciar el tunel.
# Si no hay sesiones previas, el pkill falla silenciosamente (OK).
ssh -i /home/robot/.ssh/id_ed25519_flamenco \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=10 \
    -o BatchMode=yes \
    marco@flamenco.cnb.net \
    "pkill -u marco -f 'sshd.*notty' || true" 2>/dev/null || true
# Espera breve para que flamenco libere el puerto
sleep 3
