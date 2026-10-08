"""Monta a mensagem MIME e envia pela API do Gmail (login por OAuth, veja gmail_auth.py)."""
import mimetypes
import base64
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


def enviar_gmail(mime: EmailMessage, svc) -> str:
    """Envia pela API do Gmail e devolve o Message-ID. Lança ErroAutenticacao em falha de login/permissão.

    O Gmail não recusa destinatário inexistente na hora: o bounce chega depois e o comando `caixa` detecta.
    """
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    try:
        svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    except RefreshError as e:
        raise ErroAutenticacao("Autorização do Gmail expirou. Rode: python -m prospect autorizar") from e
    except HttpError as e:
        if e.resp.status in (401, 403):
            raise ErroAutenticacao("Gmail negou o envio (permissão ou limite). Rode: python -m prospect autorizar") from e
        if e.resp.status == 400:
            raise DestinatarioRecusado(str(e)) from e
        raise
    return mime["Message-ID"]
