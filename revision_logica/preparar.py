#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fase 1: generar el Excel agrupado por aulas a partir del Excel de inscripciones.

Entrada: un Excel con las inscripciones en una hoja (o varias), con las columnas
en este orden (sin cabecera o con cabecera, se detecta automáticamente):

    Nombre | Apellidos | Correo | Grupo | Aula de examen

Salida: un Excel con una hoja por aula. Las hojas van ordenadas por número de
aula y los alumnos de cada hoja por orden alfabético (apellidos y nombre).
El orden de las filas de cada hoja es el que se usará para emparejar cada
alumno con exam_1.pdf, exam_2.pdf, ... así que el escaneo debe seguir ese orden.

Si el correo no lleva dominio (p. ej. "m.inventado"), se completa con el
dominio de alumnos configurado ("alumnos.upm.es" por defecto).
"""

import unicodedata

import pandas as pd

# Columnas (por nombre de etiqueta) del Excel de inscripciones.
COL_NOMBRE, COL_APELLIDOS, COL_CORREO, COL_GRUPO, COL_AULA = "0", "1", "2", "3", "4"

CABECERAS_POSIBLES = {"nombre", "nombre,", "apellidos", "correo", "grupo", "aula"}


def _clave_alfabetica(valor) -> str:
    """Clave de ordenación: sin tildes, minúsculas, sin espacios sobrantes."""
    texto = "" if pd.isna(valor) else str(valor)
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.casefold().strip()


def _normalizar_aula(valor) -> str | None:
    """Devuelve el aula como texto limpio ('3001'), o None si la fila no tiene aula."""
    if pd.isna(valor):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _normalizar_correo(correo, dominio: str) -> str:
    texto = "" if pd.isna(correo) else str(correo).strip()
    if texto and "@" not in texto:
        texto = f"{texto}@{dominio}"
    return texto


def _quitar_cabecera_si_hay(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    primera = str(df.iloc[0, 0]).strip().lower()
    if primera in CABECERAS_POSIBLES or primera.startswith("nombre"):
        return df.iloc[1:].reset_index(drop=True)
    return df


def preparar_excel(entrada: str, salida: str, dominio_alumnos: str = "alumnos.upm.es") -> pd.DataFrame:
    """Genera el Excel por aulas y devuelve el DataFrame resumen (aula, n_alumnos)."""
    df = pd.read_excel(entrada, header=None)
    df.columns = [str(col) for col in df.columns]  # etiquetas estables en cualquier pandas
    df = _quitar_cabecera_si_hay(df)
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        raise ValueError(f"El Excel de inscripciones '{entrada}' está vacío.")

    # Aula limpia y fila descartada si falta el dato esencial.
    df["_aula"] = df[COL_AULA].map(_normalizar_aula)
    sin_aula = df["_aula"].isna()
    if sin_aula.any():
        print(f"⚠  {sin_aula.sum()} filas sin 'Aula de examen' se descartan:")
        for _, fila in df[sin_aula].iterrows():
            print(f"   -> {fila.iloc[COL_NOMBRE]} {fila.iloc[COL_APELLIDOS]}")
        df = df[~sin_aula]

    df["_correo"] = df[COL_CORREO].map(lambda c: _normalizar_correo(c, dominio_alumnos))

    # Ordenar aulas numéricamente cuando se pueda; si no, alfabéticamente.
    aulas = sorted(set(df["_aula"]), key=lambda a: (0, int(a)) if a.isdigit() else (1, a))

    resumen = []
    with pd.ExcelWriter(salida, engine="openpyxl") as escritor:
        for aula in aulas:
            sub = df[df["_aula"] == aula].sort_values(
                by=[COL_APELLIDOS, COL_NOMBRE],
                key=lambda col: col.map(_clave_alfabetica),
            )
            tabla = sub[[COL_NOMBRE, COL_APELLIDOS, "_correo", COL_GRUPO, COL_AULA]]
            # Sin cabecera ni índice: la fila i de la hoja es exam_{i+1}.pdf.
            tabla.to_excel(escritor, sheet_name=aula, header=False, index=False)
            resumen.append({"aula": aula, "alumnos": len(sub)})
            print(f"  Hoja {aula}: {len(sub)} alumnos")

    print(f"\nExcel generado: {salida} ({len(resumen)} aulas, "
          f"{sum(r['alumnos'] for r in resumen)} alumnos)")
    return pd.DataFrame(resumen)
