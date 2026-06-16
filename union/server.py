"""
HTTP server — consulta de saldo Banco Unión (UNImóvil Plus)

POST /consultar-saldo
  Body JSON: {"usuario": "...", "password": "...", "nombre_titular": "...", "dispositivo": "..."}
  Response:  {"ok": true,  "saldo": "1250.50"}
             {"ok": false, "error": "motivo"}

Concurrencia: un lock por serial ADB — dispositivos distintos corren en paralelo;
el mismo dispositivo no puede atender dos solicitudes simultáneas.
"""

import threading

import uiautomator2 as u2
from flask import Flask, jsonify, request

from union.steps import (
    paso1_lanzar_app,
    paso2_esperar_login,
    paso3_ingresar_usuario,
    paso4_clic_iniciar_sesion,
    paso5_esperar_pantalla_password,
    paso6_confirmar_imagen_seguridad,
    paso7_ingresar_password,
    paso8_leer_saldo,
    paso9_cerrar_sesion,
    paso10_cerrar_app,
)

app = Flask(__name__)

# Lock por serial ADB: permite consultas paralelas en dispositivos distintos
_device_locks: dict[str, threading.Lock] = {}
_locks_mutex = threading.Lock()


def _get_device_lock(serial: str) -> threading.Lock:
    with _locks_mutex:
        if serial not in _device_locks:
            _device_locks[serial] = threading.Lock()
        return _device_locks[serial]


@app.route("/consultar-saldo", methods=["POST"])
def consultar_saldo():
    data           = request.get_json(force=True, silent=True) or {}
    usuario        = (data.get("usuario")        or "").strip()
    password       = (data.get("password")       or "").strip()
    nombre_titular = (data.get("nombre_titular") or "").strip()
    dispositivo    = (data.get("dispositivo")    or "").strip()

    if not usuario or not password or not dispositivo:
        return jsonify({"ok": False, "error": "Faltan campos: usuario, password, dispositivo"}), 400

    lock = _get_device_lock(dispositivo)
    if not lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": f"Dispositivo {dispositivo} ocupado, reintente en unos segundos"}), 503

    try:
        d = u2.connect(dispositivo)

        paso1_lanzar_app(d)
        paso2_esperar_login(d)
        paso3_ingresar_usuario(d, usuario)
        paso4_clic_iniciar_sesion(d)
        paso5_esperar_pantalla_password(d, nombre_titular)
        paso6_confirmar_imagen_seguridad(d)
        paso7_ingresar_password(d, password)
        saldo = paso8_leer_saldo(d)
        paso9_cerrar_sesion(d)
        paso10_cerrar_app(d)

        return jsonify({"ok": True, "saldo": saldo})

    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    finally:
        lock.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
