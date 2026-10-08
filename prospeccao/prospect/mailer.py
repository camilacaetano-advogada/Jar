"""Monta a mensagem MIME e envia pelo SMTP do Gmail (credenciais vêm do ambiente)."""
import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path


class ErroAutenticacao(Exception):
    pass


class DestinatarioRecusado(Exception):
    pass


def montar_mime(msg, para: str, usuario: str, cfg: dict, pdf: Path | None = None,
                em_resposta_a: str = "") -> EmailMessage:
    m = EmailMessage()
    m["From"] = formataddr((cfg["remetente"]["nome"], usuario))
    m["To"] = para
    m["Subject"] = msg.assunto
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=usuario.split("@")[-1])
    responder = cfg["remetente"].get("responder_para")
    if responder:
        m["Reply-To"] = responder
    m["List-Unsubscribe"] = f"<mailto:{responder or usuario}?subject=SAIR>"
    if em_resposta_a:
        m["In-Reply-To"] = em_resposta_a
        m["References"] = em_resposta_a
    m.set_content(msg.texto)
    m.add_alternative(msg.html, subtype="html")
    if pdf and pdf.exists():
        tipo, _ = mimetypes.guess_type(pdf.name)
        principal, _, sub = (tipo or "application/pdf").partition("/")
        m.add_attachment(pdf.read_bytes(), maintype=principal, subtype=sub, filename=pdf.name)
    return m


def enviar_smtp(mime: EmailMessage, usuario: str, senha: str) -> str:
    """Envia e devolve o Message-ID. Lança ErroAutenticacao / DestinatarioRecusado / SMTPException."""
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
            s.login(usuario, senha)
            s.send_message(mime)
    except smtplib.SMTPAuthenticationError as e:
        raise ErroAutenticacao("Gmail recusou o login. Confira GMAIL_USER e a senha de app no .env.") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise DestinatarioRecusado(str(e)) from e
    return mime["Message-ID"]
