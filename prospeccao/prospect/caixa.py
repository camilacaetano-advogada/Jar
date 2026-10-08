"""Lê a caixa de entrada (API do Gmail) para detectar respostas, pedidos de SAIR e bounces."""
import email
import base64
import re
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


def varrer(svc, store, agora_iso: str, dias: int = 14) -> dict:
    enviados = {e.lower() for e in store.todos_enviados()}
    conta = {"respondeu": 0, "sair": 0, "bounce": 0}
    msgs, token = [], None
    while True:
        r = svc.users().messages().list(userId="me", q=f"in:inbox newer_than:{dias}d", pageToken=token).execute()
        msgs += r.get("messages", [])
        token = r.get("nextPageToken")
        if not token:
            break
    for m in msgs:
        bruto = svc.users().messages().get(userId="me", id=m["id"], format="raw").execute()["raw"]
        for tipo, end in classificar_mensagem(base64.urlsafe_b64decode(bruto + "=="), enviados):
            if tipo == "sair":
                store.bloquear(end, "pediu SAIR por e-mail", agora_iso)
            elif tipo == "bounce":
                store.definir_relacao(end, "bounce", agora_iso)
            elif store.relacao(end) not in ("negociacao", "bounce"):
                store.definir_relacao(end, "respondeu", agora_iso)
            conta[tipo] += 1
    return conta
