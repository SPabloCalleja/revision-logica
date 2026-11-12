#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interfaz de línea de comandos. Uso general:

    revision-logica [--config ruta/config.toml] <fase> [opciones]

Fases:
    preparar    Excel de inscripciones -> Excel agrupado por aulas (fase 1)
    separar     PDF del aula -> carpeta con exam_1.pdf, exam_2.pdf, ... (fase 2)
    comprobar   validar pares examen-correo sin enviar nada (fase 3)
    enviar      modo evaluación por defecto; --real para enviar de verdad (fase 4)
"""

import argparse

from . import config as modulo_config
from . import enviar as modulo_enviar
from . import preparar as modulo_preparar
from . import separar as modulo_separar


def _anadir_excel_aulas(parser):
    parser.add_argument("--excel", required=True,
                        help="Excel agrupado por aulas (generado en la fase 'preparar')")
    parser.add_argument("--aulas", nargs="*", default=None, metavar="AULA",
                        help="procesar solo estos aulas, p. ej. --aulas 3001 6106")


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="revision-logica",
        description="Envío de exámenes escaneados a los alumnos para su revisión.")
    parser.add_argument("--config", "-c", default=None,
                        help="fichero de configuración (por defecto ./config.toml)")

    sub = parser.add_subparsers(dest="fase", required=True)

    p_preparar = sub.add_parser(
        "preparar", help="fase 1: Excel de inscripciones -> Excel por aulas")
    p_preparar.add_argument("--entrada", required=True,
                            help="Excel de inscripciones (una sola hoja con todos)")
    p_preparar.add_argument("--salida", required=True,
                            help="Excel de salida agrupado por aulas")

    p_separar = sub.add_parser(
        "separar", help="fase 2: dividir el PDF de cada aula en exámenes sueltos")
    p_separar.add_argument("--aulas", nargs="*", default=None, metavar="AULA",
                           help="aulas a separar, p. ej. --aulas 3001 6106; "
                                "si no se indican, se usan las hojas de --excel")
    p_separar.add_argument("--excel", default=None,
                           help="Excel por aulas para deducir las aulas si no se "
                                "pasan con --aulas")

    p_comprobar = sub.add_parser(
        "comprobar", help="fase 3: validar pares examen-correo sin enviar nada")
    _anadir_excel_aulas(p_comprobar)

    p_enviar = sub.add_parser(
        "enviar", help="fase 4: modo evaluación por defecto; --real para enviar")
    _anadir_excel_aulas(p_enviar)
    p_enviar.add_argument("--real", action="store_true",
                          help="envío real (sin esta opción solo se muestra el par)")
    p_enviar.add_argument("--enviarme", action="store_true",
                          help="enviarlo TODO a tu propio correo (prueba con PDF real)")
    p_enviar.add_argument("--plantilla", default=None,
                          help="ruta alternativa del fichero con el texto del correo")
    p_enviar.add_argument("--asunto", default=None,
                          help="asunto del correo para este examen (deja el de "
                               "config.toml para el uso habitual)")
    p_enviar.add_argument("--examen", type=int, default=None, metavar="N",
                          help="procesar solo el examen N (junto a --aulas; para "
                               "reenviar a mano lo que falló)")

    p_reenviar = sub.add_parser(
        "reenviar", help="reenviar los fallos anotados en errores_envio.csv")
    p_reenviar.add_argument("--excel", required=True,
                            help="Excel por aulas (para deducir alumno y PDF de cada fallo)")
    p_reenviar.add_argument("--real", action="store_true",
                            help="reenvío real (sin esta opción solo se listan los pendientes)")
    p_reenviar.add_argument("--enviarme", action="store_true",
                            help="reenviarlo todo a tu propio correo")
    p_reenviar.add_argument("--plantilla", default=None,
                            help="ruta alternativa del fichero con el texto del correo")
    return parser


def main(argv=None):
    args = construir_parser().parse_args(argv)

    if args.fase == "preparar":
        dominio = None
        try:
            cfg = modulo_config.cargar_config(args.config)
            dominio = cfg["general"].get("dominio_alumnos")
        except (FileNotFoundError, ValueError):
            pass  # la fase 1 solo necesita el dominio; usa el de por defecto
        modulo_preparar.preparar_excel(args.entrada, args.salida,
                                       dominio_alumnos=dominio or "alumnos.upm.es")
        return 0

    cfg = modulo_config.cargar_config(args.config)

    if args.fase == "separar":
        aulas = args.aulas
        if not aulas and args.excel:
            aulas = modulo_enviar._aulas_del_excel(args.excel)
        if not aulas:
            raise SystemExit("Indica las aulas con --aulas 3001 6106 ... "
                             "o un --excel del que deducirlas.")
        modulo_separar.separar_aulas(aulas, base=cfg["general"].get("carpeta_base", "."))
        return 0

    if args.fase == "comprobar":
        ok = modulo_enviar.comprobar(args.excel, cfg, aulas=args.aulas)
        return 0 if ok else 1

    if args.fase == "enviar":
        if args.enviarme:
            args.real = True
        if args.examen is not None and not args.aulas:
            raise SystemExit("La opción --examen requiere también --aulas.")
        if not args.real:
            print("== MODO EVALUACIÓN: no se enviará nada. "
                  "Usa --real para el envío definitivo. ==\n")
        plantilla = modulo_config.cargar_plantilla(cfg, args.plantilla)
        if args.asunto:
            cfg["correo"]["asunto"] = args.asunto
        examenes = [args.examen] if args.examen is not None else None
        modulo_enviar.enviar(args.excel, cfg, plantilla,
                             aulas=args.aulas, real=args.real,
                             enviarme=args.enviarme, examenes=examenes)
        return 0

    if args.fase == "reenviar":
        plantilla = modulo_config.cargar_plantilla(cfg, args.plantilla)
        modulo_enviar.reenviar(args.excel, cfg, plantilla,
                               real=args.real, enviarme=args.enviarme)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
