#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
revision_logica: envío de exámenes escaneados a los alumnos para su revisión.

Sirve para cualquier examen (LP, LPO, distintas convocatorias): el asunto y el
texto del correo se cambian en config.toml / mensaje.txt (o con las opciones
--asunto / --plantilla de la fase enviar).

Fases (ver README.md):
  1. preparar  -> Excel de inscripciones (una sola hoja) -> Excel agrupado por aulas
  2. separar   -> PDF del aula (todas las caras) -> carpeta con exam_1.pdf, exam_2.pdf, ...
  3. comprobar -> valida que el par examen-correo es correcto sin enviar nada
  4. enviar    -> manda cada examen a su alumno (por defecto en modo evaluación)
"""

__version__ = "0.2.0"
