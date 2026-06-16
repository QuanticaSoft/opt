"""
Pasos 11-18 del flujo de transferencia interbancaria ACH (Banco Union -> cuentaOficina).

Reutiliza el login (pasos 1-7 de union.steps) y termina con logout/cierre de app
(pasos 9-10 de union.steps). Este modulo solo cubre la navegacion y el formulario
de Transferencia ACH dentro del dashboard ya logueado.
"""

import re
import time
from datetime import datetime

import uiautomator2 as u2

MENU_TRANSFERENCIAS_INTERBANCARIAS = "Transferencias Interbancarias"
MENU_TRANSFERENCIA_ACH = "Transferencia ACH"


class FueraDeHorarioACH(Exception):
    """La ventana de horario ACH mostrada en pantalla no incluye la hora actual."""


class DestinatarioNoCoincide(Exception):
    """Los datos autocompletados del destinatario no coinciden con BU_OFICINA_*."""


# ---------------------------------------------------------------------------
# Paso 11 - Abrir menu y navegar a Transferencia ACH
# ---------------------------------------------------------------------------

def paso11_abrir_menu_transferencia_ach(d: u2.Device) -> None:
    print("[PASO 11] Abriendo menu...")
    menu_btn = d(className="android.widget.ImageButton", description="Open navigation drawer")
    if not menu_btn.exists:
        # Fallback: boton hamburguesa suele estar en la esquina superior izquierda
        d.click(44, 96)
    else:
        menu_btn.click()
    time.sleep(1)

    item = d(textContains=MENU_TRANSFERENCIAS_INTERBANCARIAS)
    if not item.wait(timeout=8):
        raise RuntimeError("[PASO 11] No se encontro 'Transferencias Interbancarias' en el menu.")
    item.click()
    time.sleep(1)

    ach = d(textContains=MENU_TRANSFERENCIA_ACH)
    if not ach.wait(timeout=8):
        raise RuntimeError("[PASO 11] No se encontro 'Transferencia ACH' tras expandir el submenu.")
    ach.click()
    time.sleep(2)
    print("[PASO 11] En formulario de Transferencia ACH.")


# ---------------------------------------------------------------------------
# Paso 12 - Validar ventana de horario ACH mostrada en pantalla
# ---------------------------------------------------------------------------

def paso12_validar_horario_ach(d: u2.Device) -> None:
    """
    Lee el texto informativo ('...horario actual estara disponible desde Hrs.
    HH:MM hasta HH:MM') y aborta si la hora actual del dispositivo/servidor
    esta fuera de ese rango. No asumimos un horario fijo: lo leemos en vivo.
    """
    print("[PASO 12] Validando horario ACH...")
    hierarchy = d.dump_hierarchy()
    match = re.search(
        r"desde\s+Hrs\.?\s*(\d{1,2}:\d{2}).{0,20}hasta\s+Hrs\.?\s*(\d{1,2}:\d{2})",
        hierarchy,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        print("[PASO 12] ADVERTENCIA: no se encontro el texto de horario ACH. Continuando sin validar.")
        return

    inicio_str, fin_str = match.group(1), match.group(2)
    ahora = datetime.now()
    inicio = ahora.replace(hour=int(inicio_str.split(":")[0]), minute=int(inicio_str.split(":")[1]), second=0, microsecond=0)
    fin = ahora.replace(hour=int(fin_str.split(":")[0]), minute=int(fin_str.split(":")[1]), second=0, microsecond=0)

    if not (inicio <= ahora <= fin):
        raise FueraDeHorarioACH(
            f"Fuera de horario ACH: disponible de {inicio_str} a {fin_str}, hora actual {ahora.strftime('%H:%M')}."
        )
    print(f"[PASO 12] Dentro de horario ACH ({inicio_str} - {fin_str}).")


# ---------------------------------------------------------------------------
# Paso 13 - Buscar destinatario por alias y seleccionarlo
# ---------------------------------------------------------------------------

def paso13_buscar_destinatario(d: u2.Device, alias: str) -> None:
    print(f"[PASO 13] Buscando destinatario: {alias}")
    campo_busqueda = d(className="android.widget.EditText")
    if not campo_busqueda.wait(timeout=8):
        raise RuntimeError("[PASO 13] No se encontro el campo 'Buscar Destinatario'.")
    campo_busqueda.click()
    campo_busqueda.set_text(alias)
    time.sleep(1.5)

    resultado = d(textContains=alias)
    if resultado.wait(timeout=8):
        resultado.click()
        time.sleep(1.5)
        print(f"[PASO 13] Destinatario '{alias}' seleccionado.")
    else:
        raise RuntimeError(f"[PASO 13] No aparecio ningun resultado para alias '{alias}'.")


# ---------------------------------------------------------------------------
# Paso 14 - Verificar que el autocompletado coincide con BU_OFICINA_*
# ---------------------------------------------------------------------------

def paso14_verificar_destinatario(d: u2.Device, cuenta_esperada: str, banco_esperado: str) -> None:
    print("[PASO 14] Verificando datos autocompletados del destinatario...")
    time.sleep(1)
    hierarchy = d.dump_hierarchy()

    if cuenta_esperada not in hierarchy:
        raise DestinatarioNoCoincide(
            f"[PASO 14] La cuenta destino en pantalla no contiene '{cuenta_esperada}'. Abortando por seguridad."
        )
    if banco_esperado.upper() not in hierarchy.upper():
        raise DestinatarioNoCoincide(
            f"[PASO 14] El banco en pantalla no coincide con '{banco_esperado}'. Abortando por seguridad."
        )
    print("[PASO 14] Cuenta y banco destino verificados correctamente.")


# ---------------------------------------------------------------------------
# Paso 15 - Seleccionar cuenta de origen
# ---------------------------------------------------------------------------

def paso15_seleccionar_cuenta_origen(d: u2.Device) -> None:
    print("[PASO 15] Seleccionando cuenta de origen...")
    selector_origen = d(textContains="Cuenta Origen")
    if not selector_origen.wait(timeout=8):
        raise RuntimeError("[PASO 15] No se encontro el selector 'Cuenta Origen'.")

    dropdown = d(className="android.widget.Spinner")
    if dropdown.exists:
        dropdown.click()
        time.sleep(1)
        primera_opcion = d(className="android.widget.CheckedTextView")
        if primera_opcion.exists:
            primera_opcion.click()
            time.sleep(1)
    print("[PASO 15] Cuenta de origen seleccionada (unica cuenta propia).")


# ---------------------------------------------------------------------------
# Paso 16 - Ingresar monto, moneda y glosa
# ---------------------------------------------------------------------------

def generar_glosa(fecha_pago) -> str:
    """
    Glosa automatica con formato: 'PAGO CUOTA MM/AAAA - DD/MM/AAAA'
    a partir de la fecha de pago de la cuota (mes/anio + fecha exacta).
    """
    return f"PAGO CUOTA {fecha_pago.month:02d}/{fecha_pago.year} - {fecha_pago.strftime('%d/%m/%Y')}"


def paso16_ingresar_monto_moneda_glosa(d: u2.Device, monto: str, glosa: str, moneda: str = "BOLIVIANOS") -> None:
    print(f"[PASO 16] Ingresando monto={monto}, moneda={moneda}, glosa='{glosa}'")

    campo_monto = d(textContains="Monto a Transferir").right(className="android.widget.EditText")
    if not campo_monto.exists:
        campo_monto = d(className="android.widget.EditText")
    campo_monto.click()
    campo_monto.clear_text()
    campo_monto.set_text(str(monto))
    d.hide_keyboard()
    time.sleep(0.5)

    selector_moneda = d(textContains="Seleccione la Moneda")
    if selector_moneda.exists:
        selector_moneda.click()
        time.sleep(1)
        opcion_moneda = d(text=moneda.upper())
        if not opcion_moneda.wait(timeout=5):
            raise RuntimeError(f"[PASO 16] No se encontro la opcion de moneda '{moneda}'.")
        opcion_moneda.click()
        time.sleep(0.5)

    glosa_field = d(textContains="Glosa")
    if glosa_field.exists:
        glosa_input = glosa_field.right(className="android.widget.EditText")
        if not glosa_input.exists:
            campos = d(className="android.widget.EditText")
            glosa_input = campos[campos.count - 1]
        glosa_input.click()
        glosa_input.set_text(glosa)
        d.hide_keyboard()
        time.sleep(0.5)

    print("[PASO 16] Monto, moneda y glosa ingresados.")


# ---------------------------------------------------------------------------
# Paso 17 - Continuar -> Verificacion de datos -> Confirmar
# ---------------------------------------------------------------------------

def paso17_continuar_y_confirmar(d: u2.Device, cuenta_esperada: str, banco_esperado: str) -> None:
    print("[PASO 17] Tocando CONTINUAR...")
    btn_continuar = d(textContains="CONTINUAR")
    if not btn_continuar.wait(timeout=8):
        raise RuntimeError("[PASO 17] No se encontro el boton CONTINUAR.")
    btn_continuar.click()
    time.sleep(2)

    header_verif = d(textContains="Verificacion de Datos")
    if not header_verif.wait(timeout=10):
        header_verif = d(textContains="Verificación de Datos")
    if not header_verif.exists:
        raise RuntimeError("[PASO 17] No se llego a la pantalla de Verificacion de Datos.")

    # Segunda verificacion de seguridad antes de confirmar (defensa en profundidad)
    hierarchy = d.dump_hierarchy()
    if cuenta_esperada not in hierarchy or banco_esperado.upper() not in hierarchy.upper():
        raise DestinatarioNoCoincide(
            "[PASO 17] La pantalla de Verificacion de Datos no coincide con la cuentaOficina esperada. "
            "Abortando sin confirmar."
        )

    print("[PASO 17] Datos verificados. Tocando CONFIRMAR (clave transaccional ya pre-rellenada)...")
    btn_confirmar = d(textContains="CONFIRMAR")
    if not btn_confirmar.wait(timeout=8):
        raise RuntimeError("[PASO 17] No se encontro el boton CONFIRMAR.")
    btn_confirmar.click()
    time.sleep(3)
    print("[PASO 17] Transferencia confirmada.")


# ---------------------------------------------------------------------------
# Paso 18 - Leer numero de envio del comprobante
# ---------------------------------------------------------------------------

def paso18_leer_numero_envio(d: u2.Device) -> dict:
    print("[PASO 18] Leyendo comprobante de confirmacion...")
    if not d(textContains="OPERACION PENDIENTE DE CONFIRMACION").wait(timeout=10) and \
       not d(textContains="OPERACIÓN PENDIENTE DE CONFIRMACIÓN").wait(timeout=2):
        raise RuntimeError("[PASO 18] No se confirmo la operacion (no aparecio el mensaje esperado).")

    hierarchy = d.dump_hierarchy()
    match_envio = re.search(r'Numero de Envio[^>]*>\s*<[^>]*text="(\d+)"', hierarchy, re.IGNORECASE)
    if not match_envio:
        match_envio = re.search(r'text="(\d{10,})"', hierarchy)

    numero_envio = match_envio.group(1) if match_envio else None
    if not numero_envio:
        raise RuntimeError("[PASO 18] No se pudo extraer el numero de envio del comprobante.")

    print(f"[PASO 18] Numero de envio: {numero_envio}")
    return {"numero_envio": numero_envio}
