"""Carrega config.yaml e o .env (credenciais ficam só no .env / variáveis de ambiente)."""
import copy
import os
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


class ErroConfig(Exception):
    pass


def carregar_env(caminho: Path = RAIZ / ".env") -> None:
    """Lê KEY=VALOR do .env sem sobrescrever variáveis já definidas no ambiente."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(chave.strip(), valor)


def _mesclar(base: dict, extra: dict) -> dict:
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mesclar(base[k], v)
        else:
            base[k] = v
    return base


def carregar_config(caminho: Path | None = None) -> dict:
    caminho = Path(caminho) if caminho else RAIZ / "config.yaml"
    padrao = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    if caminho.exists() and caminho != RAIZ / "config.yaml":
        _mesclar(padrao, yaml.safe_load(caminho.read_text(encoding="utf-8")))
    return copy.deepcopy(padrao)


def carregar_templates() -> dict:
    return yaml.safe_load((RAIZ / "templates.yaml").read_text(encoding="utf-8"))


def credenciais() -> tuple[str, str]:
    usuario = os.environ.get("GMAIL_USER", "").strip()
    senha = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not usuario or not senha:
        raise ErroConfig(
            "Faltam GMAIL_USER e/ou GMAIL_APP_PASSWORD. Copie .env.example para .env e preencha."
        )
    return usuario, senha


def caminho(cfg: dict, chave: str) -> Path:
    p = Path(cfg["arquivos"][chave])
    return p if p.is_absolute() else RAIZ / p
