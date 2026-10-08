"""Monta o e-mail (texto + HTML) de cada contato a partir do templates.yaml."""
import hashlib
import html
import re
from dataclasses import dataclass

from .contacts import Contato, norm


@dataclass
class Mensagem:
    assunto: str
    texto: str
    html: str
    segmento: str


class _Seguro(dict):
    def __missing__(self, chave):
        return ""


def preencher(modelo: str, **vars) -> str:
    """str.format que não quebra com variável ausente e ignora chaves soltas."""
    try:
        return modelo.format_map(_Seguro(**vars)).strip()
    except (ValueError, IndexError):
        return modelo.strip()


def _escolher(opcoes: list, chave: str, salt: str):
    h = int(hashlib.md5(f"{chave}|{salt}".encode()).hexdigest(), 16)
    return opcoes[h % len(opcoes)]


def classificar(segmento: str, tpl: dict) -> str:
    alvo = norm(segmento)
    for nome, bloco in tpl["segmentos"].items():
        if any(p in alvo for p in bloco["palavras"]):
            return nome
    return "lifestyle"


def _variaveis(c: Contato, cfg: dict) -> dict:
    return {
        "nome_marca": c.marca or "vocês",
        "nome_contato": c.contato.split()[0] if c.contato else "",
        "cidade": c.cidade,
        "segmento": c.segmento,
        "motivo_consumo": c.motivo_consumo,
        "portfolio_url": cfg["perfil"]["portfolio_url"],
        "instagram": cfg["perfil"]["instagram"],
        "tiktok": cfg["perfil"]["tiktok"],
    }


def _abertura(c: Contato, tpl: dict, v: dict) -> str:
    chave = "aberturas_com_contato" if v["nome_contato"] else "aberturas_sem_contato"
    return preencher(_escolher(tpl[chave], c.email, "abertura"), **v)


def _html(texto: str) -> str:
    def paragrafo(p):
        seguro = html.escape(p)
        seguro = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', seguro)
        return "<p>" + seguro.replace("\n", "<br>") + "</p>"

    *corpo, rodape = [p for p in texto.split("\n\n") if p.strip()]
    partes = "".join(paragrafo(p) for p in corpo)
    partes += f'<p style="color:#888;font-size:12px">{html.escape(rodape)}</p>'
    return f'<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#222">{partes}</div>'


def montar(c: Contato, cfg: dict, tpl: dict, etapa: int = 1, assunto_original: str = "") -> Mensagem:
    v = _variaveis(c, cfg)
    p = cfg["perfil"]
    seg = classificar(c.segmento, tpl)
    bloco = tpl["segmentos"][seg]
    abertura = _abertura(c, tpl, v)
    rodape = tpl["rodape"]
    assinatura = p["assinatura"].strip()

    if etapa == 2:
        fu = tpl["followup"]
        corpo = [preencher(b, abertura=abertura, **v) for b in fu["corpo"]]
        corpo.append(f"Insta {p['instagram']} · TikTok {p['tiktok']}")
        corpo += [assinatura, rodape]
        assunto = preencher(fu["assunto"], assunto_original=assunto_original, **v)
    else:
        consome = bool(c.motivo_consumo)
        assuntos = tpl["assuntos_consome"] if consome else tpl["assuntos"]
        assunto = preencher(_escolher(assuntos, c.email, "assunto"), **v)
        corpo = [abertura, preencher(bloco["gancho"], **v), preencher(tpl["apresentacao"], **v)]
        corpo.append(preencher(tpl["linha_consome" if consome else "linha_nova"], **v))
        corpo.append(preencher(bloco["encaixe"], **v))
        if c.cidade:
            corpo.append(preencher(tpl["linha_cidade"], **v))
        if cfg["audiencia"]["ativo"] and cfg["audiencia"]["texto"].strip():
            corpo.append(cfg["audiencia"]["texto"].strip())
        if cfg["prova_social"]["ativo"] and cfg["prova_social"]["texto"].strip():
            corpo.append(cfg["prova_social"]["texto"].strip())
        corpo.append(preencher(tpl["formatos"], **v))
        corpo.append(f"Meu portfólio com trabalhos e formatos: {p['portfolio_url']}\nInsta {p['instagram']} · TikTok {p['tiktok']}")
        if cfg["aviso_humano"]["ativo"]:
            corpo.append(tpl["aviso_humano"])
        corpo.append(_escolher(tpl["fechamentos"], c.email, "fechamento"))
        corpo += [assinatura, rodape]

    texto = "\n\n".join(" ".join(b.split()) if "\n" not in b else b.strip() for b in corpo)
    return Mensagem(assunto=assunto, texto=texto, html=_html(texto), segmento=seg)
