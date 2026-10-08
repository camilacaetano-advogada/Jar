"""Lê a caixa de entrada (IMAP do Gmail) para detectar respostas, pedidos de SAIR e bounces."""
import email
import imaplib
import re
from datetime import datetime, timedelta
from email import policy
from email.utils import parseaddr

BOUNCE_REMETENTES = ("mailer-daemon", "postmaster")
SAIR_RE = re.compile(r"^\W*(sair|descadastrar|remover|nao quero|não quero)\b", re.I)


def classificar_mensagem(raw: bytes, enviados: set[str]) -> list[tuple[str, str]]:
    """Devolve [(tipo, email)] com tipo em: bounce | sair | respondeu."""
    m = email.message_from_bytes(raw, policy=policy.default)
    remetente = parseaddr(str(m.get("From", "")))[1].lower()
    corpo_obj = m.get_body(preferencelist=("plain", "html"))
    corpo = corpo_obj.get_content() if corpo_obj else ""
    if any(b in remetente for b in BOUNCE_REMETENTES):
        falhos = set(re.findall(r"[\w.+\-']+@[\w\-]+(?:\.[\w\-]+)+", (str(m.get("X-Failed-Recipients", "")) + " " + corpo).lower()))
        return [("bounce", e) for e in falhos & enviados]
    if remetente in enviados:
        eventos = [("respondeu", remetente)]
        if SAIR_RE.search(corpo.strip()[:300]):
            eventos.append(("sair", remetente))
        return eventos
    return []


def varrer(usuario: str, senha: str, store, agora_iso: str, dias: int = 14, conexao=None) -> dict:
    enviados = {e.lower() for e in store.todos_enviados()}
    conta = {"respondeu": 0, "sair": 0, "bounce": 0}
    imap = conexao or imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(usuario, senha)
    try:
        imap.select("INBOX", readonly=True)
        desde = (datetime.now() - timedelta(days=dias)).strftime("%d-%b-%Y")
        _, ids = imap.search(None, f'(SINCE "{desde}")')
        for i in ids[0].split():
            _, dados = imap.fetch(i, "(RFC822)")
            for tipo, end in classificar_mensagem(dados[0][1], enviados):
                if tipo == "sair":
                    store.bloquear(end, "pediu SAIR por e-mail", agora_iso)
                elif tipo == "bounce":
                    store.definir_relacao(end, "bounce", agora_iso)
                elif store.relacao(end) not in ("negociacao", "bounce"):
                    store.definir_relacao(end, "respondeu", agora_iso)
                conta[tipo] += 1
    finally:
        imap.logout()
    return conta
