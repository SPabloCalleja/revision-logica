# Revision de Lógica

Envío de exámenes escaneados a los alumnos, por correo, para su revisión.
Sirve para cualquier examen (LP, LPO, varias convocatorias): solo cambian el
asunto y el texto del correo, que se configuran en ficheros externos.

## Instalación (una sola vez)

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -e .
```

Todos los comandos se llaman con `./.venv/bin/revision-logica` (o `./.venv/bin/python -m revision_logica`).

## Cómo debe estar el directorio

```
mi_curso/
├── config.toml               ← servidor SMTP, usuario y contraseña (NO subir a GitHub)
├── mensaje.txt               ← texto del correo (editable)
├── inscripciones.xlsx        ← Excel con TODOS los alumnos inscritos en una hoja (entrada)
├── examenes.xlsx             ← Excel por aulas (lo genera la fase preparar)
├── 3001.pdf  3104.pdf  ...   ← escaneo completo de cada aula (2 caras = 1 examen)
├── 3001/  3104/  ...         ← carpetas con exam_1.pdf, exam_2.pdf, ... (las genera separar)
└── errores_envio.csv         ← fallos del último envío real (si los hubo)
```

- `carpeta_base` en `config.toml` apunta a la carpeta con los PDFs y Excel (por
  defecto `.`).
- Las hojas de `examenes.xlsx` se llaman igual que los PDFs: `3001` ↔ `3001.pdf`.
- **El orden de filas de cada hoja es el orden de los exámenes escaneados:**
  fila 1 → `exam_1.pdf`, fila 2 → `exam_2.pdf`, ...

## Cómo debe ser el Excel original de inscripciones

Es el fichero que pasas a la fase `preparar` (`--entrada`). Reglas:

1. **Columnas en este orden exacto** (la fase 1 no admite otro orden):

   | Columna A | Columna B | Columna C | Columna D | Columna E |
   |---|---|---|---|---|
   | **Nombre** | **Apellidos** | **Correo** | **Grupo** | **Aula de examen** |

2. **Todos los alumnos juntos en una hoja** (la que sea): la fase `preparar`
   es la que los agrupa por aulas y los ordena alfabéticamente. Puede haber
   varias hojas, se concatenan todas.

3. **La fila de cabecera es opcional.** Si la pones (`Nombre | Apellidos |
   Correo | Grupo | Aula de examen`), se detecta y se salta automáticamente.

4. **El correo puede venir con o sin dominio**:
   - `m.inventado` → se completa como `m.inventado@alumnos.upm.es`
     (dominio configurable en `dominio_alumnos`).
   - `m.inventado@alumnos.upm.es` → se deja tal cual.

5. **El aula debe ser el número del aula** (p. ej. `3001`), porque el nombre de
   la hoja del Excel generado debe coincidir con el fichero `3001.pdf` del
   escaneo. No dejes la celda vacía (esas filas se descartan con un aviso).

Ejemplo de contenido (con cabecera):

| Nombre | Apellidos | Correo | Grupo | Aula de examen |
|---|---|---|---|---|
| Alumna1 | Apellido Apellido | m.inventado | PARS | 3001 |
| Alumno2 | Apellido | m.inventado | CDIA | 3001 |
| Alumno3 | Apellido | m.inventado | 2M | 3102 |

Tras ejecutar `preparar`, ese mismo contenido quedará agrupado: hoja `3001`
(Alumna1, Alumno2 ordenadas por apellidos), hoja `3102` (Alumna3), etc.

## Ficheros PDF escaneados

Deben ser ficheros por aula y con el nombre del aula (ej. 3001.pdf) con todos los exámenes de la revisión en ese aula el orden del Excel separado en hojas por aula (tras el paso 1 - Preparación). Cada folio de un alumno son las dos caras (2 hojas del pdf) aunque una esté vacía. La fotocopiadora de la universidad se puede configurar para que escanee por las dos caras.


## Ficheros de configuración

**`config.toml`** (está en `.gitignore`, nunca subirlo a GitHub):

```toml
[smtp]
servidor = "smtp.upm.es"          # servidor y puerto de tu cuenta
puerto = 587
usuario = "tu@upm.es"             # tu cuenta
contrasena = "XXXX"               # tu contraseña
copia_oculta = "otra@upm.es"      # copia de cada envío a ti (oculta)

[correo]
asunto = "..."                    # admite {alumno}, {aula}, {examen}, ...
plantilla = "mensaje.txt"         # fichero con el texto del correo
max_por_minuto = 50               # tope duro de correos por minuto
pausa_entre_envios = 4            # segundos tras cada correo (anti-spam)
pausa_entre_aulas = 60            # segundos de descanso entre aulas (anti-spam)
nombre_adjunto = "Examen_{aula}_{examen}.pdf"

[general]
dominio_alumnos = "alumnos.upm.es"
carpeta_base = "."
```

**`mensaje.txt`** — texto libre del correo. Marcadores disponibles (también en
el asunto): `{alumno}` nombre de pila, `{apellidos}`, `{nombre_completo}`,
`{grupo}`, `{aula}`, `{examen}`. Ejemplo: `Hola {alumno},` → "Hola Marta,".

## Comandos y argumentos

`revision-logica [--config ruta/config.toml] <fase> [opciones]`

### 1. `preparar` — del Excel de inscripciones al Excel por aulas

```bash
revision-logica preparar --entrada inscripciones.xlsx --salida examenes.xlsx
```

| Argumento | Obligatorio | Qué hace |
|---|---|---|
| `--entrada` | sí | Excel de inscripciones (una hoja con todos: `Nombre, Apellidos, Correo, Grupo, Aula de examen`) |
| `--salida` | sí | Excel resultante: una hoja por aula, aulas ordenadas y alumnos por orden alfabético |

Completa el dominio del correo si falta (`m.inventado` → `m.inventado@alumnos.upm.es`).

### 2. `separar` — del PDF escaneado a exámenes sueltos

```bash
revision-logica separar --aulas 3001 3104            # aulas concretas
revision-logica separar --excel examenes.xlsx        # todas las del Excel
```

| Argumento | Obligatorio | Qué hace |
|---|---|---|
| `--aulas` | o `--excel` | aulas a separar (p. ej. `--aulas 3001 3104`) |
| `--excel` | o `--aulas` | deduce las aulas de las hojas del Excel |

Genera `{aula}/exam_1.pdf, exam_2.pdf, ...` (2 páginas por examen) y verifica
que cada PDF generado abre correctamente. Avisa si el número de páginas es impar.

### 3. `comprobar` — validar pares examen-correo (sin enviar nada)

```bash
revision-logica comprobar --excel examenes.xlsx
revision-logica comprobar --excel examenes.xlsx --aulas 3001
```

| Argumento | Obligatorio | Qué hace |
|---|---|---|
| `--excel` | sí | Excel por aulas |
| `--aulas` | no | comprobar solo esos aulas |

Comprueba: PDFs presentes y válidos, número de PDFs = número de alumnos,
correos con dominio y sin acentos/símbolos raros. Devuelve error si algo falla.

### 4. `enviar` — modo evaluación o envío real

```bash
revision-logica enviar --excel examenes.xlsx                       # MODO EVALUACIÓN
revision-logica enviar --excel examenes.xlsx --aulas 3001          # solo un aula
revision-logica enviar --excel examenes.xlsx --enviarme            # prueba: todo a tu correo
revision-logica enviar --excel examenes.xlsx --real                # envío definitivo
```

| Argumento | Qué hace |
|---|---|
| `--excel` (obligatorio) | Excel por aulas |
| `--aulas` | enviar solo esos aulas (p. ej. `--aulas 3001 3104`) |
| `--examen N` | enviar solo el examen N (junto a `--aulas`; reenvío manual) |
| `--real` | envío real (sin esto NO se envía nada, solo se lista el par examen→correo) |
| `--enviarme` | prueba real: todo llega a `copia_oculta` con asunto `[PRUEBA]` |
| `--asunto "..."` | asunto para este envío (p. ej. otro examen) |
| `--plantilla ruta.txt` | fichero de texto alternativo para el cuerpo del correo |

En envío real respeta `max_por_minuto` y añade `pausa_entre_envios` tras cada
correo y `pausa_entre_aulas` entre aulas — así el SMTP no detecta ráfagas como spam.

### 5. `reenviar` — recuperar lo que falló

Cuando un envío real termina, los fallos quedan en `errores_envio.csv` (se abre
con Excel: aula, examen, fichero, alumno, correo y motivo). Corrige lo que
haga falta en el Excel y luego:

```bash
revision-logica reenviar --excel examenes.xlsx          # lista los pendientes
revision-logica reenviar --excel examenes.xlsx --real   # los reenvía todos
```

| Argumento | Qué hace |
|---|---|
| `--excel` (obligatorio) | Excel por aulas |
| `--real` | reenvío real (sin esto solo lista los pendientes) |
| `--enviarme` | prueba: los reenvía a tu correo |

Al reenviar, si algo vuelve a fallar el CSV se actualiza con solo esos fallos;
si todo sale bien, el CSV se borra.

## Errores habituales y cómo los gestiona el programa

- **Correo con acentos** (`óscar.petras`): se sanea automáticamente quitando
  tildes y espacios, y se avisa en pantalla de la corrección.
- **Correo sin arreglo** (vacío o con caracteres de otro alfabeto): no se
  intenta enviar; queda anotado en `errores_envio.csv` y el proceso sigue.
- **Error SMTP**: 3 reintentos por correo; si no, se anota y continúa con el
  siguiente alumno. Nunca se detiene el envío masivo por un alumno.
- **PDF sospechoso** (no empieza por `%PDF-`): se avisa antes de enviarlo.
