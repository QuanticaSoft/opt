import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    usuario: str
    password: str
    dispositivo: str
    nombre_titular: str


def load_config() -> Config:
    usuario = os.getenv("BU_USUARIO")
    password = os.getenv("BU_PASSWORD")
    dispositivo = os.getenv("BU_DISPOSITIVO")
    nombre_titular = os.getenv("BU_NOMBRE_TITULAR", "")

    if not all([usuario, password, dispositivo]):
        raise RuntimeError(
            "Faltan variables de entorno. El archivo .env debe tener:\n"
            "  BU_USUARIO, BU_PASSWORD, BU_DISPOSITIVO\n"
            "  BU_NOMBRE_TITULAR (opcional, para verificar pantalla de contraseña)"
        )

    return Config(
        usuario=usuario,
        password=password,
        dispositivo=dispositivo,
        nombre_titular=nombre_titular,
    )
