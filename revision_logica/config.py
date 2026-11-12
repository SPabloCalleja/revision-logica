#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga de la configuración externa (config.toml) y de la plantilla del mensaje.

Toda información sensible (usuario y contraseña de correo) vive en ``config.toml``,
que debe estar en el ``.gitignore`` para no subirla a GitHub por accidente.
"""

import tomllib
from pathlib import Path

NOMBRE_CONFIG_DEFECTO = "config.toml"

# Plantilla por defecto si no existe el fichero indicado en [correo] plantilla.
PLANTILLA_DEFECTO = """\
Hola {alumno},

Te adjunto el ejercicio de tu examen escaneado.

Este es un mensaje automático, si hay algún problema respecto a este email,
por favor házmelo saber.

Muchas gracias,

Pablo 
"""

# Valores por defecto de config.toml (se pueden sobrescribir en el fichero).
DEFECTOS = {
    "smtp": {
        "servidor": "smtp.upm.es",
        "puerto": 587,
        "usuario": "",
        "contrasena": "",
        "copia_oculta": "",
    },
    "correo": {
        "asunto": "",  # se define en config.toml
        "plantilla": "mensaje.txt",
        "max_por_minuto": 50,
        "nombre_adjunto": "Examen_{aula}_{examen}.pdf",
        # Pausas anti-spam (solo en envío real)
        "pausa_entre_envios": 4,
        "pausa_entre_aulas": 60,
    },
    "general": {
        "dominio_alumnos": "alumnos.upm.es",
        "carpeta_base": ".",
    },
}


def _profundizar(base: dict, extra: dict) -> dict:
    for clave, valor in extra.items():
        if isinstance(valor, dict):
            base.setdefault(clave, {})
            _profundizar(base[clave], valor)
        else:
            base.setdefault(clave, valor)
    return base


def cargar_config(ruta: str | None = None) -> dict:
    """Carga config.toml (argumento, directorio actual o junto al paquete)."""
    if ruta:
        ruta_config = Path(ruta)
        if not ruta_config.exists():
            raise FileNotFoundError(f"No existe el fichero de configuración: {ruta_config}")
    else:
        candidatos = [Path.cwd() / NOMBRE_CONFIG_DEFECTO,
                      Path(__file__).resolve().parent / NOMBRE_CONFIG_DEFECTO]
        ruta_config = next((c for c in candidatos if c.exists()), None)
        if ruta_config is None:
            raise FileNotFoundError(
                f"No se encontró {NOMBRE_CONFIG_DEFECTO}. Créalo junto a los datos "
                f"o pasa --config /ruta/a/config.toml")

    with open(ruta_config, "rb") as fichero:
        cfg = tomllib.load(fichero)

    _profundizar(cfg, DEFECTOS)

    smtp = cfg["smtp"]
    if not smtp["usuario"] or not smtp["contrasena"]:
        raise ValueError(
            f"Falta 'usuario' o 'contrasena' en la sección [smtp] de {ruta_config}.\n"
            f"(No pongas estas credenciales en el código ni las subas a GitHub.)")

    cfg["_ruta"] = str(ruta_config)
    return cfg


def cargar_plantilla(cfg: dict, ruta: str | None = None) -> str:
    """Lee el fichero externo con el texto del correo.

    En el texto se pueden usar los marcadores:
        {alumno} {apellidos} {nombre_completo} {grupo} {aula} {examen}
    """
    if ruta is None:
        ruta = cfg["correo"].get("plantilla", "mensaje.txt")
    ruta_plantilla = Path(ruta)
    if not ruta_plantilla.is_absolute():
        # Primero junto al config.toml, luego en el directorio actual.
        candidato = Path(cfg["_ruta"]).resolve().parent / ruta_plantilla
        ruta_plantilla = candidato if candidato.exists() else Path.cwd() / ruta_plantilla

    if ruta_plantilla.exists():
        return ruta_plantilla.read_text(encoding="utf-8")

    print(f"⚠  No se encontró la plantilla '{ruta}'. Se usa el texto por defecto.")
    return PLANTILLA_DEFECTO
