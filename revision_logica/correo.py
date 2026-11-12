#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Envío de correos por SMTP (UPM) con PDF adjunto.

Este módulo corrige el problema de los adjuntos que llegaban como ``.bin``:

* Antes se adjuntaba como ``application/octet-stream`` (tipo genérico que
  Outlook/Exchange no sabe abrir y renombra a .bin). Ahora se declara
  ``application/pdf``.
* Antes la cabecera Content-Disposition llevaba la ruta completa
  (``filename=./6106/exam_8.pdf``). Los clientes de correo se lían con la ruta
  y el resultado era un fichero sin extensión reconocible. Ahora solo se envía
  el nombre del fichero, bien codificado.
* Se usa ``email.message.EmailMessage`` + ``send_message``, que genera las
  cabeceras Date/Message-ID y codifica el cuerpo de forma estándar.

La copia oculta se mete en el *sobren* SMTP (envelope) y NO en la cabecera
``Bcc``, que antes viajaba visible en el correo del alumno.
"""

import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

INTENTOS = 3
PAUSA_ENTRE_INTENTOS = 5  # segundos


class EnviadorCorreo:
    """Enviador SMTP configurado a partir de la sección [smtp] de config.toml."""

    def __init__(self, cfg: dict):
        self.smtp = cfg["smtp"]
        self.servidor = self.smtp["servidor"]
        self.puerto = int(self.smtp["puerto"])
        self.usuario = self.smtp["usuario"]
        self.contrasena = self.smtp["contrasena"]
        self.copia_oculta = self.smtp.get("copia_oculta", "")

    def enviar(self, para: str, asunto: str, cuerpo: str, adjunto_path: str,
               nombre_adjunto: str | None = None) -> bool:
        """Envía un correo con un PDF adjunto. Devuelve True si se envió bien.

        Lanza ValueError si el destinatario no es una dirección válida (la
        fase enviar lo captura y lo anota como fallo sin parar el proceso).
        """
        try:
            para.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError(f"El destinatario '{para}' no es una dirección de "
                             f"correo válida (contiene acentos o símbolos).")

        ruta_adjunto = Path(adjunto_path)
        datos = ruta_adjunto.read_bytes()

        if not datos.startswith(b"%PDF-") or len(datos) < 100:
            print(f"⚠  AVISO: '{ruta_adjunto}' no parece un PDF válido "
                  f"({len(datos)} bytes). Revisa el escaneo.")

        mensaje = EmailMessage()
        mensaje["From"] = self.usuario
        mensaje["To"] = para
        mensaje["Subject"] = asunto
        mensaje["Date"] = formatdate(localtime=True)
        mensaje["Message-ID"] = make_msgid(domain=self.usuario.split("@")[-1])
        mensaje.set_content(cuerpo)

        # application/pdf + nombre de fichero limpio: evita el .bin en Outlook.
        mensaje.add_attachment(
            datos,
            maintype="application",
            subtype="pdf",
            filename=nombre_adjunto or ruta_adjunto.name,
        )

        # Copia oculta real: en el sobren SMTP, no como cabecera Bcc visible.
        destinatarios = [para] + ([self.copia_oculta] if self.copia_oculta else [])

        ultimo_error = None
        for intento in range(1, INTENTOS + 1):
            try:
                with smtplib.SMTP(self.servidor, self.puerto, timeout=30) as servidor:
                    servidor.starttls()
                    servidor.login(self.usuario, self.contrasena)
                    servidor.send_message(
                        mensaje, from_addr=self.usuario, to_addrs=destinatarios)
                return True
            except (smtplib.SMTPException, ValueError, OSError) as error:
                ultimo_error = error
                if intento < INTENTOS:
                    time.sleep(PAUSA_ENTRE_INTENTOS * intento)

        print(f"✗  Error enviando a {para} ({ruta_adjunto}): {ultimo_error}")
        return False
