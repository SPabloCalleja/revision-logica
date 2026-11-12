#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fase 2: separar el PDF escaneado de cada aula en exámenes individuales.

Para el fichero ``{aula}.pdf`` (todas las caras del aula, en el mismo orden que
las filas del Excel) genera la carpeta ``{aula}/`` con ``exam_1.pdf``,
``exam_2.pdf``, ... Cada examen son 2 caras (una hoja por doble cara).
Si el número total de páginas es impar, el último examen se queda con 1 cara
y se avisa.
"""

from pathlib import Path
import logging
from contextlib import contextmanager

from pypdf import PdfReader, PdfWriter

CARAS_POR_EXAMEN = 2


class _RecolectorAvisos(logging.Handler):
    """Recoge los mensajes de aviso que pypdf imprime al leer un PDF."""

    def __init__(self):
        super().__init__()
        self.registros: list[str] = []

    def emit(self, record):
        self.registros.append(record.getMessage())


@contextmanager
def _avisos_pypdf():
    """Captura los warnings de pypdf (p. ej. 'Ignoring wrong pointing object')."""
    recolector = _RecolectorAvisos()
    logger = logging.getLogger("pypdf")
    logger.addHandler(recolector)
    nivel_previo = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield recolector
    finally:
        logger.removeHandler(recolector)
        logger.setLevel(nivel_previo)


def separar_pdf(ruta_pdf: Path, carpeta_salida: Path, prefijo: str = "exam") -> list[Path]:
    """Divide el PDF en ficheros de CARAS_POR_EXAMEN páginas. Devuelve las rutas creadas."""
    with _avisos_pypdf() as recolector:
        lector = PdfReader(ruta_pdf)
        total_paginas = len(lector.pages)

        creados = []
        for numero, inicio in enumerate(range(0, total_paginas, CARAS_POR_EXAMEN), start=1):
            escritor = PdfWriter()
            escritor.add_page(lector.pages[inicio])
            if inicio + CARAS_POR_EXAMEN - 1 < total_paginas:
                escritor.add_page(lector.pages[inicio + 1])
            else:
                print(f"⚠  Páginas impares en '{ruta_pdf}': "
                      f"{prefijo}_{numero}.pdf se queda con 1 sola cara.")

            destino = carpeta_salida / f"{prefijo}_{numero}.pdf"
            with open(destino, "wb") as salida:
                escritor.write(salida)
            creados.append(destino)

    if recolector.registros:
        print(f"  ℹ  '{ruta_pdf.name}' tiene {len(recolector.registros)} anomalía(s) "
              f"menor(es) de estructura, típicas de los PDF de escáner "
              f"(p. ej. '{recolector.registros[0]}'). No afecta al resultado: los "
              f"exámenes generados se verifican a continuación.")

    # Verificación: cada examen generado debe abrir bien y tener sus páginas.
    for destino in creados:
        with _avisos_pypdf() as comprobacion:
            try:
                n = len(PdfReader(destino).pages)
                if n != min(CARAS_POR_EXAMEN, total_paginas):
                    print(f"⚠  '{destino.name}' tiene {n} páginas, se esperaban "
                          f"{CARAS_POR_EXAMEN}. Revisa ese examen.")
            except Exception as error:
                print(f"⚠  ¡ATENCIÓN! '{destino}' no se puede leer tras el "
                      f"separado ({error}). Compruébalo a mano.")

    print(f"  {ruta_pdf.name}: {total_paginas} páginas -> "
          f"{len(creados)} exámenes verificados en {carpeta_salida}/")
    return creados


def separar_aula(codigo: str, base: str | Path = ".") -> list[Path]:
    """Separa el PDF de un aula: {base}/{codigo}.pdf -> {base}/{codigo}/exam_N.pdf."""
    ruta_pdf = Path(base) / f"{codigo}.pdf"
    carpeta = Path(base) / str(codigo)
    if not ruta_pdf.exists():
        raise FileNotFoundError(f"No existe el PDF del aula: {ruta_pdf}")
    carpeta.mkdir(parents=True, exist_ok=True)
    return separar_pdf(ruta_pdf, carpeta)


def separar_aulas(codigos, base: str | Path = ".") -> dict[str, list[Path]]:
    """Separa varios aulas; las que fallen se avisan y se continúa con el resto."""
    resultado = {}
    for codigo in codigos:
        try:
            resultado[str(codigo)] = separar_aula(codigo, base)
        except FileNotFoundError as error:
            print(f"⚠  {error}")
    return resultado
