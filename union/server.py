"""
HTTP server — consulta de saldo Banco Unión (UNImóvil Plus)

POST /consultar-saldo
  Body JSON: {"usuario": "...", "password": "...", "nombre_titular": "...", "dispositivo": "..."}
  Response:  {"ok": true,  "saldo": "1250.50"}
             {"ok": false, "error": "motivo"}
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

# Un solo dispositivo Android puede atender una solicitud a la vez
_lock = threading.Lock()


@app.route("/consultar-saldo", methods=["POST"])
def consultar_saldo():
    data           = request.get_json(force=True, silent=True) or {}
    usuario        = (data.get("usuario")        or "").strip()
    password       = (data.get("password")       or "").strip()
    nombre_titular = (data.get("nombre_titular") or "").strip()
    dispositivo    = (data.get("dispositivo")    or "").strip()

    if not usuario or not password or not dispositivo:
        return jsonify({"ok": False, "error": "Faltan campos: usuario, password, dispositivo"}), 400

    if not _lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "Dispositivo ocupado, reintente en unos segundos"}), 503

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
        _lock.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
