"""Login no Gmail por OAuth (substitui a senha de app, que o Google descontinuou).

Primeira vez: `python -m prospect autorizar` abre o navegador, você aprova e o app guarda um token
em data/token.json. Depois disso não pede mais nada. Nenhuma senha é guardada.
"""
import os
from pathlib import Path

from . import config

ESCOPOS = [
    "https://www.googleapis.com/auth/gmail.send",       # enviar e-mails
    "https://www.googleapis.com/auth/gmail.readonly",   # ler respostas, SAIR e bounces
]


def _arquivo_cliente() -> Path:
    p = Path(os.environ.get("GOOGLE_CLIENT_SECRET_FILE") or "credentials.json")
    return p if p.is_absolute() else config.RAIZ / p


def _arquivo_token() -> Path:
    p = Path(os.environ.get("GOOGLE_TOKEN_FILE") or "data/token.json")
    return p if p.is_absolute() else config.RAIZ / p


def autorizar() -> str:
    """Fluxo interativo (navegador). Devolve o e-mail autorizado."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    cliente = _arquivo_cliente()
    if not cliente.exists():
        raise config.ErroConfig(
            f"Não achei {cliente}. Baixe o JSON do cliente OAuth (tipo 'App para computador') "
            "no Google Cloud e salve com esse nome. Veja o passo a passo no README."
        )
    cred = InstalledAppFlow.from_client_secrets_file(str(cliente), ESCOPOS).run_local_server(port=0)
    token = _arquivo_token()
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(cred.to_json(), encoding="utf-8")
    try:
        token.chmod(0o600)
    except OSError:
        pass
    return email_da_conta(_servico(cred))


def _servico(cred):
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=cred, cache_discovery=False)


def credenciais():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token = _arquivo_token()
    if not token.exists():
        raise config.ErroConfig("Gmail ainda não autorizado. Rode primeiro: python -m prospect autorizar")
    cred = Credentials.from_authorized_user_file(str(token), ESCOPOS)
    if not cred.valid:
        try:
            cred.refresh(Request())
        except RefreshError as e:
            raise config.ErroConfig(
                "A autorização do Gmail expirou ou foi revogada. Rode de novo: python -m prospect autorizar"
            ) from e
        token.write_text(cred.to_json(), encoding="utf-8")
    return cred


def servico():
    """Cliente da API do Gmail pronto para uso."""
    return _servico(credenciais())


def email_da_conta(svc) -> str:
    return svc.users().getProfile(userId="me").execute()["emailAddress"]
