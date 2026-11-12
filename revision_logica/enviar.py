#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fases 3 y 4: comprobar y enviar los exámenes según el Excel por aulas.

Emparejamiento: en cada hoja (aula), la fila i-ésima (empezando en 1) va con
``{aula}/exam_i.pdf``, que es exactamente el orden en que genera `separar`.

Por defecto todo funciona en *modo evaluación*: no se envía nada, solo se
muestra el par examen -> correo para que verifiques que cada examen le toca a
su alumno. El envío real requiere ``--real``.

Robustez del envío real:
* Los correos se saneann antes de enviarlos: se completa el dominio, se quitan
  espacios y se QUITAN LOS ACENTOS del nombre de usuario (caso típico de error:
  "óscar.zayas@alumnos.upm.es" pasa los filtros simples y luego estalla en el
  SMTP). Si tras sanearlo sigue sin ser ASCII válido, NO se intenta enviar.
* Si el envío de un alumno falla (correo raro, SMTP caído, PDF corrupto...),
  se registra el fallo y el sistema SIGUE con el resto.
* Al terminar se generan dos cosas para reenviar a mano lo que falló:
    1. ``errores_envio.csv`` (abierto con Excel) con aula, examen, fichero,
       alumno, correo y motivo de cada fallo.
    2. El comando exacto para reenviar ese examen en concreto, por ejemplo:
       revision-logica enviar --excel X.xlsx --real --aulas 3001 --examen 7

Se respeta el límite de correos por minuto configurado (``max_por_minuto``):
si se alcanza el máximo en una ventana de 60 segundos, se espera antes de
enviar el siguiente. Además, en envío real hay dos pausas anti-anti-spam
(configurables en config.toml):

* ``pausa_entre_envios``: segundos de espera tras cada correo (por defecto 4 s).
* ``pausa_entre_aulas``: segundos de descanso al pasar de un aula a la
  siguiente (por defecto 60 s). Así el servidor no ve ráfagas de correos.
"""

import csv
import time
import unicodedata
from collections import deque
from pathlib import Path

import re

import pandas as pd

from .correo import EnviadorCorreo

CABECERAS_POSIBLES = {"nombre", "apellidos", "correo", "grupo", "aula"}
FICHERO_CSV_ERRORES = "errores_envio.csv"
# Local de una dirección razonable (no empieza/termina por punto, etc.)
PATRON_LOCAL = re.compile(r"^[a-z0-9_%+-]([a-z0-9._%+-]*[a-z0-9_%+-])?$")


def personalizar(plantilla: str, valores: dict) -> str:
    """Sustituye {alumno}, {apellidos}, ... en la plantilla del mensaje."""
    texto = plantilla
    for clave, valor in valores.items():
        texto = texto.replace("{" + clave + "}", str(valor))
    return texto


class Limitador:
    """Limita el número de envíos por minuto (ventana deslizante de 60 s)."""

    def __init__(self, max_por_minuto: int):
        self.max_por_minuto = max(1, int(max_por_minuto))
        self._marcas: deque[float] = deque()

    def esperar(self):
        ahora = time.monotonic()
        while self._marcas and ahora - self._marcas[0] >= 60:
            self._marcas.popleft()
        if len(self._marcas) >= self.max_por_minuto:
            espera = 60 - (ahora - self._marcas[0]) + 0.5
            print(f"⏳  Alcanzado el máximo de {self.max_por_minuto} correos/minuto. "
                  f"Esperando {espera:.0f} s...")
            time.sleep(max(0.0, espera))
        self._marcas.append(time.monotonic())


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def sanear_correo(correo, dominio: str) -> tuple[str, list[str]]:
    """Limpia una dirección y devuelve (correo_limpio, avisos).

    Avisos típicos: dominio completado, espacios quitados, acentos quitados.
    Si tiene caracteres que no corresponden a tildes (p. ej. nombres en otro
    alfabeto) se marca con el aviso 'correo no válido': no se debe intentar
    enviar; la fase enviar lo anota en errores_envio.csv.
    """
    avisos = []
    texto = "" if correo is None else str(correo).strip()

    if not texto:
        return "", ["sin correo"]

    if "@" not in texto:
        texto = f"{texto}@{dominio}"
        avisos.append("se completó el dominio")

    local, _, parte_dominio = texto.rpartition("@")
    if " " in local or " " in parte_dominio:
        local = local.replace(" ", "")
        parte_dominio = parte_dominio.replace(" ", "")
        avisos.append("se quitaron espacios")

    # ¿Tiene caracteres que NO son simples tildes? (李, @ extra, emoji...)
    descompuesto = unicodedata.normalize("NFKD", local)
    hay_caracteres_raros = any(
        ord(caracter) > 127 and not unicodedata.combining(caracter)
        for caracter in descompuesto)

    local_limpio = _sin_acentos(local)
    if hay_caracteres_raros:
        avisos.append(f"el nombre de usuario '{local}' tiene caracteres no válidos")
        local = local_limpio
    elif local_limpio != local:
        avisos.append(f"acentos quitados: '{local}' -> '{local_limpio}'")
        local = local_limpio

    texto = f"{local}@{parte_dominio}".strip().lower()
    if hay_caracteres_raros or not local or not PATRON_LOCAL.match(local):
        avisos.append("correo no válido")
    return texto, avisos


def _leer_filas(df: pd.DataFrame, dominio: str) -> list[dict]:
    """Normaliza las filas de una hoja: quita cabecera/filas vacías y sanea correos."""
    if not df.empty:
        primera = str(df.iloc[0, 0]).strip().lower()
        if primera in CABECERAS_POSIBLES or primera.startswith("nombre"):
            df = df.iloc[1:].reset_index(drop=True)
    df = df.dropna(how="all").reset_index(drop=True)

    filas = []
    for _, fila in df.iterrows():
        correo_excel = "" if pd.isna(fila.iloc[2]) else str(fila.iloc[2]).strip()
        correo, avisos = sanear_correo(correo_excel, dominio)
        filas.append({
            "nombre": "" if pd.isna(fila.iloc[0]) else str(fila.iloc[0]).strip(),
            "apellidos": "" if pd.isna(fila.iloc[1]) else str(fila.iloc[1]).strip(),
            "correo": correo,
            "correo_excel": correo_excel,
            "avisos": avisos,
            "grupo": "" if pd.isna(fila.iloc[3]) else str(fila.iloc[3]).strip(),
        })
    return filas


def _aulas_del_excel(excel: str) -> list[str]:
    hojas = pd.read_excel(excel, sheet_name=None, header=None)
    return [nombre for nombre in hojas if nombre.strip().isdigit()]


def _texto_fallo(fallo: dict) -> str:
    return (f"aula {fallo['aula']}, exam_{fallo['examen']}.pdf, "
            f"{fallo['alumno']}, correo excel '{fallo['correo_excel']}' -> {fallo['motivo']}")


def _guardar_csv_errores(fallos: list[dict], ruta_csv: Path) -> None:
    """Escribe el CSV de fallos (utf-8-sig para que Excel lo abra bien)."""
    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as fichero:
        columnas = ["aula", "examen", "fichero", "alumno", "correo_excel",
                    "correo_usado", "motivo"]
        escritor = csv.DictWriter(fichero, fieldnames=columnas)
        escritor.writeheader()
        for fallo in fallos:
            escritor.writerow(fallo)


def comprobar(excel: str, cfg: dict, aulas: list[str] | None = None) -> bool:
    """Fase 3: valida pares examen-correo y ficheros, sin enviar nada.

    Devuelve True si todo está bien.
    """
    base = Path(cfg["general"].get("carpeta_base", "."))
    dominio = cfg["general"].get("dominio_alumnos", "alumnos.upm.es")
    hojas = pd.read_excel(excel, sheet_name=None, header=None)

    todo_ok = True
    for nombre_hoja, df in hojas.items():
        if not nombre_hoja.strip().isdigit():
            print(f"— Hoja '{nombre_hoja}': no es un aula, se ignora.")
            continue
        if aulas and nombre_hoja not in aulas:
            continue

        filas = _leer_filas(df, dominio)
        carpeta = base / nombre_hoja
        ficheros = sorted(carpeta.glob("exam_*.pdf")) if carpeta.exists() else []

        print(f"\nAula {nombre_hoja}: {len(filas)} alumnos en el Excel, "
              f"{len(ficheros)} PDFs en {carpeta}/")
        if len(filas) != len(ficheros):
            print("⚠  ¡Atención! El número de alumnos no coincide con el de PDFs.")
            todo_ok = False

        for numero, alumno in enumerate(filas, start=1):
            examen = carpeta / f"exam_{numero}.pdf"
            estado = []
            if not examen.exists():
                estado.append("FALTA EL PDF")
                todo_ok = False
            elif not examen.read_bytes()[:5].startswith(b"%PDF-"):
                estado.append("PDF SOSPECHOSO")
                todo_ok = False
            if not alumno["correo"]:
                estado.append("SIN CORREO")
                todo_ok = False
            elif "correo no válido" in alumno["avisos"]:
                estado.append(f"CORREO CON ACENTOS/SÍMBOLOS: '{alumno['correo_excel']}'")
                todo_ok = False
            elif "se completó el dominio" in alumno["avisos"]:
                estado.append(f"sin dominio en el Excel: '{alumno['correo_excel']}'")
            aviso = f"  [{' | '.join(estado)}] " if estado else ""
            print(f"{aviso}exam_{numero}.pdf -> {alumno['correo']} "
                  f"({alumno['nombre']} {alumno['apellidos']})")
    return todo_ok


def enviar(excel: str, cfg: dict, plantilla: str, aulas: list[str] | None = None,
           real: bool = False, enviarme: bool = False,
           examenes: int | list[int] | None = None,
           guardar_csv: bool = True) -> tuple[int, list[dict]]:
    """Fase 4: modo evaluación (por defecto) o envío real con --real.

    Con ``--enviarme`` todos los correos se mandan a la propia cuenta
    (copia_oculta del config) para revisar el resultado real del envío.
    Con ``examenes`` (p. ej. [7]) solo procesa esos números de examen, útil
    para reenviar lo que falló (ver errores_envio.csv).

    En envío real respeta ``max_por_minuto`` y añade una pausa tras cada correo
    (``pausa_entre_envios``) y otra entre aulas (``pausa_entre_aulas``), para
    que el servidor no detecte ráfagas y marque como spam.

    Devuelve (enviados, fallos). Los fallos también se guardan en
    ``errores_envio.csv`` para reenviarlos manualmente.
    """
    base = Path(cfg["general"].get("carpeta_base", "."))
    dominio = cfg["general"].get("dominio_alumnos", "alumnos.upm.es")
    limite = Limitador(cfg["correo"].get("max_por_minuto", 50))
    asunto_plantilla = cfg["correo"].get("asunto", "")
    nombre_adjunto = cfg["correo"].get("nombre_adjunto", "Examen_{aula}_{examen}.pdf")
    pausa_envios = float(cfg["correo"].get("pausa_entre_envios", 4))
    pausa_aulas = float(cfg["correo"].get("pausa_entre_aulas", 60))
    ruta_csv = base / FICHERO_CSV_ERRORES
    mi_correo = cfg["smtp"].get("copia_oculta") or cfg["smtp"]["usuario"]

    if isinstance(examenes, int):
        examenes = [examenes]
    numeros_examen = set(examenes) if examenes is not None else None

    hojas = pd.read_excel(excel, sheet_name=None, header=None)
    enviador = EnviadorCorreo(cfg)
    total_enviados = 0
    fallos: list[dict] = []

    # Aulas seleccionadas (hojas numéricas), en el orden del Excel.
    seleccion = [(nombre_hoja, df) for nombre_hoja, df in hojas.items()
                 if nombre_hoja.strip().isdigit()
                 and (not aulas or nombre_hoja in aulas)]
    for nombre_hoja in (h for h, _ in hojas.items()):
        if not nombre_hoja.strip().isdigit():
            print(f"— Hoja '{nombre_hoja}': no es un aula, se ignora.")

    for indice, (nombre_hoja, df) in enumerate(seleccion):
        filas = _leer_filas(df, dominio)
        modo = ("ENVÍO REAL" if real else "MODO EVALUACIÓN (no se envía nada)")
        print(f"\n=== Aula {nombre_hoja} — {modo} — {len(filas)} alumnos ===")

        enviaron_en_aula = False
        for numero, alumno in enumerate(filas, start=1):
            if numeros_examen is not None and numero not in numeros_examen:
                continue
            fichero_examen = base / nombre_hoja / f"exam_{numero}.pdf"
            nombre_completo = f"{alumno['nombre']} {alumno['apellidos']}".strip()

            if not real:
                if not fichero_examen.exists():
                    print(f"  ⚠  FALTA {fichero_examen} para {alumno['correo']} "
                          f"({nombre_completo})")
                    continue
                print(f"  [EVALUACIÓN] exam_{numero}.pdf -> {alumno['correo']} "
                      f"({nombre_completo})")
                continue

            # ---- Validación previa: un correo malo nunca debe parar el proceso ----
            if "correo no válido" in alumno["avisos"] or not alumno["correo"]:
                motivo = ("correo con caracteres no válidos (acentos/espacios)"
                          if alumno["correo"] else "sin correo en el Excel")
                print(f"  ✗  exam_{numero}.pdf para {nombre_completo}: {motivo}. "
                      f"Se omite y se anota en {ruta_csv.name}.")
                fallos.append({
                    "aula": nombre_hoja, "examen": numero,
                    "fichero": str(fichero_examen), "alumno": nombre_completo,
                    "correo_excel": alumno["correo_excel"],
                    "correo_usado": alumno["correo"], "motivo": motivo,
                })
                continue
            if not fichero_examen.exists():
                motivo = "no existe el fichero del examen"
                print(f"  ✗  {nombre_completo} ({alumno['correo']}): {motivo}. "
                      f"Se omite y se anota en {ruta_csv.name}.")
                fallos.append({
                    "aula": nombre_hoja, "examen": numero,
                    "fichero": str(fichero_examen), "alumno": nombre_completo,
                    "correo_excel": alumno["correo_excel"],
                    "correo_usado": alumno["correo"], "motivo": motivo,
                })
                continue
            if alumno["avisos"]:
                print(f"  ⚠  Correo saneado ({'; '.join(alumno['avisos'])}): "
                      f"'{alumno['correo_excel']}' -> '{alumno['correo']}'")

            valores = {
                "alumno": alumno["nombre"],
                "apellidos": alumno["apellidos"],
                "nombre_completo": nombre_completo,
                "grupo": alumno["grupo"],
                "aula": nombre_hoja,
                "examen": numero,
            }
            cuerpo = personalizar(plantilla, valores)
            asunto = personalizar(asunto_plantilla, valores)
            adjunto_con_nombre = nombre_adjunto.format(aula=nombre_hoja, examen=numero)

            if enviarme:
                print(f"  [A MÍ MISMO] {fichero_examen.name} -> {mi_correo} "
                      f"(iría a {alumno['correo']})")
                asunto = f"[PRUEBA] {asunto}"
                destino = mi_correo
            else:
                destino = alumno["correo"]

            limite.esperar()
            try:
                ok = enviador.enviar(destino, asunto, cuerpo, str(fichero_examen),
                                     nombre_adjunto=adjunto_con_nombre)
                motivo = "" if ok else "error SMTP (ver mensajes anteriores)"
            except Exception as error:  # noqa: BLE001 — nunca debe parar el envío masivo
                ok = False
                motivo = f"excepción: {type(error).__name__}: {error}"
            if ok:
                total_enviados += 1
                enviaron_en_aula = True
                print(f"  ✓  Enviado exam_{numero}.pdf a {destino} ({nombre_completo})")
                # Pausa tras cada correo: evita ráfagas que el SMTP detecta como spam.
                if pausa_envios > 0:
                    time.sleep(pausa_envios)
            else:
                fallo = {
                    "aula": nombre_hoja, "examen": numero,
                    "fichero": str(fichero_examen), "alumno": nombre_completo,
                    "correo_excel": alumno["correo_excel"], "correo_usado": destino,
                    "motivo": motivo,
                }
                fallos.append(fallo)
                print(f"  ✗  Fallo en {_texto_fallo(fallo)}. Se anota en {ruta_csv.name}.")

        # Descanso entre aulas (no después de la última).
        if real and enviaron_en_aula and pausa_aulas > 0 and indice < len(seleccion) - 1:
            print(f"\n⏳  Pausa de {pausa_aulas:.0f} s antes de pasar al siguiente aula...")
            time.sleep(pausa_aulas)

    # ---------------- Notificación cómoda de los fallos ----------------
    if real and fallos and guardar_csv:
        _guardar_csv_errores(fallos, ruta_csv)
        print(f"\n{'=' * 60}\nFALLOS EN EL ENVÍO ({len(fallos)}): se guardaron en "
              f"{ruta_csv}\n{'=' * 60}")
        for fallo in fallos:
            print(f"  ✗  {_texto_fallo(fallo)}")
        print("\nPara reenviar los fallos automáticamente (corrige antes el correo "
              "del alumno en el Excel si procede):")
        print(f"  revision-logica reenviar --excel {excel} --real")
        ejemplo = fallos[0]
        print(f"  (o uno solo: revision-logica enviar --excel {excel} --real "
              f"--aulas {ejemplo['aula']} --examen {ejemplo['examen']})")

    print(f"\nResumen: {total_enviados} correos enviados, {len(fallos)} fallos.")
    return total_enviados, fallos


def reenviar(excel: str, cfg: dict, plantilla: str, real: bool = False,
             enviarme: bool = False) -> tuple[int, list[dict]]:
    """Reenvía los pares que fallaron, leyéndolos de ``errores_envio.csv``.

    Sin ``--real`` (ni ``--enviarme``) solo muestra los pares pendientes.
    Con ``--real`` los reenvía; si alguno vuelve a fallar se regenera
    ``errores_envio.csv`` con solo esos, y si todos salen bien se borra.
    """
    base = Path(cfg["general"].get("carpeta_base", "."))
    ruta_csv = base / FICHERO_CSV_ERRORES

    if not ruta_csv.exists():
        print(f"No hay {FICHERO_CSV_ERRORES} en {base}: no hay nada que reenviar.")
        return 0, []

    with open(ruta_csv, encoding="utf-8-sig") as fichero:
        filas_csv = list(csv.DictReader(fichero))
    if not filas_csv:
        print(f"{FICHERO_CSV_ERRORES} está vacío: no hay nada que reenviar.")
        return 0, []

    # Pares (aula, examen) pendientes, agrupados por aula y sin duplicados.
    grupos: dict[str, set[int]] = {}
    pendientes = []
    for fila in filas_csv:
        aula, numero = str(fila["aula"]).strip(), int(fila["examen"])
        par = (aula, numero)
        if par not in pendientes:
            pendientes.append(par)
            grupos.setdefault(aula, set()).add(numero)

    print(f"Pendientes de reenvío en {ruta_csv.name}: {len(pendientes)}")
    for aula in sorted(grupos):
        for numero in sorted(grupos[aula]):
            print(f"  aula {aula}, exam_{numero}.pdf")

    if not real:
        print("\n== MODO EVALUACIÓN: no se envía nada. "
              "Usa --real (o --enviarme para probarte a ti mismo). ==")
        return 0, []

    total_enviados = 0
    fallos: list[dict] = []
    for aula, numeros in grupos.items():
        enviados, fallos_aula = enviar(
            excel, cfg, plantilla, aulas=[aula], real=True, enviarme=enviarme,
            examenes=sorted(numeros), guardar_csv=False)
        total_enviados += enviados
        fallos.extend(fallos_aula)

    # El CSV se actualiza: solo quedan en él los fallos de este reintento.
    if fallos:
        _guardar_csv_errores(fallos, ruta_csv)
        print(f"\nSiguen fallando {len(fallos)}: {ruta_csv} actualizado "
              f"(solo con estos).")
    else:
        ruta_csv.unlink(missing_ok=True)
        print(f"\n¡Todo reenviado con éxito! Se ha borrado {ruta_csv.name}.")
    return total_enviados, fallos
