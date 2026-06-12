"""
UNImóvil Plus — Pasos 1 a 6
Uso: python -m union.main

Ejecuta el flujo hasta dejar la pantalla de contraseña con el
checkbox de imagen de seguridad ya confirmado (listo para ingresar
la contraseña en el paso 7).
"""

from union.config import load_config
from union.device import get_device
from union.steps import (
    paso1_lanzar_app,
    paso2_esperar_login,
    paso3_ingresar_usuario,
    paso4_clic_iniciar_sesion,
    paso5_esperar_pantalla_password,
    paso6_confirmar_imagen_seguridad,
)


def main() -> None:
    cfg = load_config()
    d = get_device()

    paso1_lanzar_app(d)
    paso2_esperar_login(d)
    paso3_ingresar_usuario(d, cfg.usuario)
    paso4_clic_iniciar_sesion(d)
    paso5_esperar_pantalla_password(d, cfg.nombre_titular)
    paso6_confirmar_imagen_seguridad(d)

    print("\n[OK] Pasos 1-6 completados.")
    print("     Pantalla de contraseña visible con imagen de seguridad confirmada.")
    print("     Listo para el Paso 7: ingresar contraseña y hacer login final.")


if __name__ == "__main__":
    main()
