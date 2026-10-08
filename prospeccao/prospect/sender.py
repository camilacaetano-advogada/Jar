"""Orquestra o envio: fila, janela de horário, limite diário, intervalo e registro."""
import random
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, contacts, gmail_auth, mailer
from .templates import classificar, montar


class Resumo:
    def __init__(self):
        self.enviados = 0
        self.falhas = 0
        self.pulados: dict[str, int] = {}
        self.parou_por = ""

    def pular(self, motivo):
        self.pulados[motivo] = self.pulados.get(motivo, 0) + 1


def _hm(texto):
    h, m = texto.split(":")
    return int(h), int(m)


def agora_no_fuso(cfg):
    return datetime.now(ZoneInfo(cfg["envio"]["horario"]["fuso"]))


def dentro_da_janela(cfg, agora):
    h = cfg["envio"]["horario"]
    ini, fim = _hm(h["inicio"]), _hm(h["fim"])
    return agora.weekday() in h["dias"] and ini <= (agora.hour, agora.minute) < fim


def proxima_janela(cfg, agora):
    h = cfg["envio"]["horario"]
    ini = _hm(h["inicio"])
    for d in range(0, 9):
        cand = (agora + timedelta(days=d)).replace(hour=ini[0], minute=ini[1], second=0, microsecond=0)
        if cand > agora and cand.weekday() in h["dias"]:
            return cand
    return agora + timedelta(hours=1)


def montar_fila(cfg, store, lista, seguir_followup, agora, resumo, tpl=None):
    """Lista de (contato, etapa). Follow-ups primeiro (são mais antigos), depois novos.

    Entre os novos, os segmentos de `prioridade_segmentos` (padrão: hospedagem) saem antes; a ordem da planilha se mantém."""
    followups, novos = [], []
    limite_fu = agora - timedelta(days=cfg["followup"]["dias"])
    for c in lista:
        if store.bloqueado(c.email):
            resumo.pular("na lista de bloqueio/descadastro")
            continue
        e1 = store.envio(c.email, 1)
        if e1 is None:
            novos.append((c, 1))
            continue
        if e1["status"] == "enviando":
            resumo.pular("envio interrompido antes (confira a caixa de Enviados)")
        elif e1["status"] == "erro":
            resumo.pular("deu erro antes (use 'reenviar-erros' se quiser tentar de novo)")
        elif store.relacao(c.email) in ("respondeu", "negociacao"):
            resumo.pular("já respondeu / em negociação")
        elif store.relacao(c.email) == "bounce":
            resumo.pular("e-mail não entregue (bounce)")
        elif store.envio(c.email, 2) is not None:
            resumo.pular("já recebeu e-mail e follow-up")
        elif not seguir_followup or not cfg["followup"]["ativo"]:
            resumo.pular("já recebeu o e-mail")
        elif datetime.fromisoformat(e1["enviado_em"]) <= limite_fu:
            followups.append((c, 2))
        else:
            resumo.pular("já recebeu; follow-up ainda não venceu")
    prioridade = cfg.get("prioridade_segmentos", ["hospedagem"]) if tpl else []

    def rank(item):
        seg = classificar(item[0].segmento, tpl)
        return prioridade.index(seg) if seg in prioridade else len(prioridade)

    return followups + sorted(novos, key=rank)  # sorted é estável


def executar(cfg, tpl, store, lista, *, real, limite=None, seguir_followup=True,
             enviar_fn=None, usuario=None, dormir=time.sleep, agora_fn=None, mostrar=print, rng=random, planilha=None):
    agora_fn = agora_fn or (lambda: agora_no_fuso(cfg))
    resumo = Resumo()
    fila = montar_fila(cfg, store, lista, seguir_followup, agora_fn(), resumo, tpl)
    if limite is not None:
        fila = fila[:limite]
    if not fila:
        mostrar("Nada para enviar agora.")
        return resumo

    pdf = None
    if real:
        if cfg["arquivos"]["pdf_portfolio"]:
            pdf = config.caminho(cfg, "pdf_portfolio")
            if not pdf.exists():
                raise config.ErroConfig(f"PDF do portfólio não encontrado: {pdf}")
        if enviar_fn is None:
            svc = gmail_auth.servico()
            usuario = gmail_auth.email_da_conta(svc)
            enviar_fn = lambda mime: mailer.enviar_gmail(mime, svc)  # noqa: E731
        usuario = usuario or ""
    erros_seguidos = 0

    for n, (c, etapa) in enumerate(fila):
        original = ""
        if etapa == 2:
            original = store.envio(c.email, 1)["assunto"]
        msg = montar(c, cfg, tpl, etapa, original)

        if not real:
            mostrar(f"\n{'=' * 70}\n[SIMULAÇÃO {n + 1}/{len(fila)}] etapa {etapa} · segmento: {msg.segmento}\n"
                    f"Para: {c.email}\nAssunto: {msg.assunto}\n{'-' * 70}\n{msg.texto}")
            continue

        # janela de horário e limite diário
        while not dentro_da_janela(cfg, agora_fn()):
            prox = proxima_janela(cfg, agora_fn())
            mostrar(f"Fora do horário permitido. Aguardando até {prox:%d/%m %H:%M} (Ctrl+C para parar).")
            dormir(min(600, max(1, (prox - agora_fn()).total_seconds())))
        dia = agora_fn().strftime("%Y-%m-%d")
        if store.enviados_no_dia(dia) >= cfg["envio"]["limite_diario"]:
            resumo.parou_por = f"limite diário de {cfg['envio']['limite_diario']} atingido (rode de novo amanhã para continuar)"
            break

        store.iniciar(c.email, etapa, c.marca, msg.assunto, dia)
        reply_to = store.envio(c.email, 1)["message_id"] if etapa == 2 else ""
        mime = mailer.montar_mime(msg, c.email, usuario, cfg, pdf, em_resposta_a=reply_to or "")
        try:
            mid = enviar_fn(mime)
            store.concluir(c.email, etapa, True, agora_fn().isoformat(timespec="seconds"), message_id=mid)
            resumo.enviados += 1
            erros_seguidos = 0
            mostrar(f"[{n + 1}/{len(fila)}] enviado: {c.marca or c.email} <{c.email}> (etapa {etapa})")
        except mailer.ErroAutenticacao as e:
            store.db.execute("DELETE FROM envios WHERE email=? AND etapa=? AND status='enviando'", (c.email, etapa))
            store.db.commit()
            resumo.parou_por = str(e)
            break
        except Exception as e:  # noqa: BLE001 - registra qualquer falha de envio e segue
            store.concluir(c.email, etapa, False, agora_fn().isoformat(timespec="seconds"), erro=str(e)[:300])
            if isinstance(e, mailer.DestinatarioRecusado):
                store.definir_relacao(c.email, "bounce", agora_fn().isoformat(timespec="seconds"))
            resumo.falhas += 1
            erros_seguidos += 1
            mostrar(f"[{n + 1}/{len(fila)}] ERRO em {c.email}: {e}")
            if erros_seguidos >= 3:
                resumo.parou_por = "3 erros seguidos: parei por segurança. Verifique conexão/conta."
                break

        if planilha:
            sincronizar_planilha(store, planilha, [c.email])

        if n < len(fila) - 1 and store.enviados_no_dia(dia) >= cfg["envio"]["limite_diario"]:
            resumo.parou_por = f"limite diário de {cfg['envio']['limite_diario']} atingido (rode de novo amanhã para continuar)"
            break
        if n < len(fila) - 1:
            espera = rng.uniform(cfg["envio"]["intervalo_min"], cfg["envio"]["intervalo_max"])
            mostrar(f"   aguardando {espera:.0f}s até o próximo...")
            dormir(espera)
    return resumo


def sincronizar_planilha(store, caminho, emails=None):
    pl = contacts.Planilha(caminho)
    ie = pl._col_email()
    alvo = set(emails) if emails else None
    mapa = {}
    for r in pl.linhas:
        for e in (x.lower() for x in re.findall(r"[^\s,;<>]+@[^\s,;<>]+", r[ie] if ie is not None and ie < len(r) else "")):
            if alvo is None or e in alvo:
                st = store.status_planilha(e)
                if st:
                    mapa[e] = st
    try:
        pl.atualizar(mapa)
    except PermissionError:
        print("Aviso: não consegui salvar a planilha (está aberta no Excel?). O registro continua salvo no banco.")
