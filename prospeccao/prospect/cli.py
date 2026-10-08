"""Linha de comando: python -m prospect <comando>"""
import argparse
import html
import sys
from datetime import datetime
from pathlib import Path

from . import caixa, config, contacts, gmail_auth, mailer, sender, templates
from .store import Store


def _carregar(args):
    config.carregar_env()
    cfg = config.carregar_config(args.config)
    tpl = config.carregar_templates()
    store = Store(config.caminho(cfg, "banco"))
    return cfg, tpl, store


def _ler_planilha(cfg, mostrar_relatorio=True):
    caminho = config.caminho(cfg, "planilha")
    if not caminho.exists():
        raise config.ErroConfig(f"Planilha não encontrada: {caminho}\nCopie seu arquivo para essa pasta ou ajuste 'arquivos.planilha' no config.yaml.")
    lista, rel = contacts.ler_contatos(caminho)
    if mostrar_relatorio:
        ignoradas = rel["sem_email"] + len(rel["invalido"]) + len(rel["duplicado"])
        print(f"Planilha: {rel['total']} linhas · {len(lista)} com e-mail válido · {ignoradas} ignoradas "
              f"({rel['sem_email']} sem e-mail, {len(rel['invalido'])} e-mail inválido, {len(rel['duplicado'])} repetidas)")
        for n, valor in rel["invalido"][:10]:
            print(f"   linha {n}: e-mail inválido -> {valor!r}")
    return lista, rel, caminho


def cmd_autorizar(args):
    config.carregar_env()
    print("Vou abrir o navegador para você autorizar o acesso ao Gmail...")
    print(f"Pronto! Conta autorizada: {gmail_auth.autorizar()}")


def cmd_contatos(args):
    cfg, tpl, store = _carregar(args)
    lista, _, _ = _ler_planilha(cfg)
    contagem = {}
    for c in lista:
        s = templates.classificar(c.segmento, tpl)
        contagem[s] = contagem.get(s, 0) + 1
    print("Segmentos detectados:", ", ".join(f"{k}={v}" for k, v in sorted(contagem.items())))


def cmd_previa(args):
    cfg, tpl, store = _carregar(args)
    lista, _, _ = _ler_planilha(cfg)
    cartoes = []
    for c in lista:
        m = templates.montar(c, cfg, tpl)
        cartoes.append(
            f"<section><h3>{html.escape(c.marca or c.email)} <small>· {m.segmento}</small></h3>"
            f"<p><b>Para:</b> {html.escape(c.email)}<br><b>Assunto:</b> {html.escape(m.assunto)}</p>{m.html}</section>"
        )
    saida = config.RAIZ / "out" / "previa.html"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(
        "<meta charset='utf-8'><title>Prévia</title><style>body{font-family:Arial;max-width:760px;margin:2rem auto;background:#f6f3f7}"
        "section{background:#fff;border-radius:12px;padding:1rem 1.5rem;margin:1rem 0;box-shadow:0 1px 4px #0002}small{color:#999}</style>"
        f"<h1>Prévia dos e-mails ({len(cartoes)})</h1>" + "".join(cartoes), encoding="utf-8")
    print(f"Prévia gerada: {saida}  (abra no navegador)")


def cmd_teste(args):
    cfg, tpl, store = _carregar(args)
    svc = gmail_auth.servico()
    usuario = gmail_auth.email_da_conta(svc)
    lista, _, _ = _ler_planilha(cfg, mostrar_relatorio=False)
    exemplos = lista[: args.quantos] or [contacts.Contato(marca="Marca Exemplo", email="x@x.com", segmento="beleza")]
    for c in exemplos:
        m = templates.montar(c, cfg, tpl)
        m.assunto = "[TESTE] " + m.assunto
        pdf = config.caminho(cfg, "pdf_portfolio") if cfg["arquivos"]["pdf_portfolio"] else None
        mailer.enviar_gmail(mailer.montar_mime(m, usuario, usuario, cfg, pdf), svc)
        print(f"Teste enviado para {usuario} (exemplo: {c.marca}).")


def cmd_enviar(args):
    cfg, tpl, store = _carregar(args)
    lista, _, caminho = _ler_planilha(cfg)
    if args.real:
        print(f"ENVIO REAL · limite diário {cfg['envio']['limite_diario']} · intervalo {cfg['envio']['intervalo_min']}-{cfg['envio']['intervalo_max']}s")
    else:
        print("MODO SIMULAÇÃO (nada será enviado). Use --real para enviar de verdade.")
    try:
        r = sender.executar(cfg, tpl, store, lista, real=args.real, limite=args.limite,
                            seguir_followup=not args.sem_followup, planilha=caminho if args.real else None)
    except KeyboardInterrupt:
        print("\nInterrompido. Nada se perde: rode de novo para continuar de onde parou.")
        return 130
    print("\n=== RESUMO ===")
    print(f"Enviados: {r.enviados} · Falhas: {r.falhas} · Pulados: {sum(r.pulados.values())}")
    for motivo, n in r.pulados.items():
        print(f"   pulados ({n}): {motivo}")
    if r.parou_por:
        print("Parei porque:", r.parou_por)
    return 1 if r.falhas else 0


def cmd_status(args):
    cfg, tpl, store = _carregar(args)

    def q(sql):
        return store.db.execute(sql).fetchone()[0]

    print("Enviados (1º e-mail):", q("SELECT COUNT(*) FROM envios WHERE etapa=1 AND status='enviado'"))
    print("Follow-ups enviados: ", q("SELECT COUNT(*) FROM envios WHERE etapa=2 AND status='enviado'"))
    print("Erros:               ", q("SELECT COUNT(*) FROM envios WHERE status='erro'"))
    print("Responderam:         ", q("SELECT COUNT(*) FROM relacao WHERE status IN ('respondeu','negociacao')"))
    print("Bounces:             ", q("SELECT COUNT(*) FROM relacao WHERE status='bounce'"))
    print("Bloqueados:          ", q("SELECT COUNT(*) FROM bloqueio"))
    hoje = sender.agora_no_fuso(cfg).strftime("%Y-%m-%d")
    print(f"Enviados hoje:        {store.enviados_no_dia(hoje)}/{cfg['envio']['limite_diario']}")


def cmd_caixa(args):
    cfg, tpl, store = _carregar(args)
    svc = gmail_auth.servico()
    agora = sender.agora_no_fuso(cfg).isoformat(timespec="seconds")
    c = caixa.varrer(svc, store, agora, dias=args.dias)
    print(f"Respostas: {c['respondeu']} · Pedidos de SAIR: {c['sair']} · Bounces: {c['bounce']}")
    sender.sincronizar_planilha(store, config.caminho(cfg, "planilha"))


def cmd_marcar(args):
    cfg, tpl, store = _carregar(args)
    store.definir_relacao(args.email, args.status, sender.agora_no_fuso(cfg).isoformat(timespec="seconds"))
    sender.sincronizar_planilha(store, config.caminho(cfg, "planilha"), [args.email.lower()])
    print(f"{args.email} marcado como {args.status}.")


def cmd_bloquear(args):
    cfg, tpl, store = _carregar(args)
    store.bloquear(args.email, args.motivo, sender.agora_no_fuso(cfg).isoformat(timespec="seconds"))
    sender.sincronizar_planilha(store, config.caminho(cfg, "planilha"), [args.email.lower()])
    print(f"{args.email} na lista de bloqueio: nunca mais receberá e-mails.")


def cmd_sincronizar(args):
    cfg, tpl, store = _carregar(args)
    sender.sincronizar_planilha(store, config.caminho(cfg, "planilha"))
    print("Planilha atualizada com o status do banco.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="prospect", description="Prospecção de parcerias da Camila")
    ap.add_argument("--config", default=None, help="config.yaml alternativo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("autorizar", help="liga o app ao seu Gmail (só na primeira vez)").set_defaults(f=cmd_autorizar)
    sub.add_parser("contatos", help="valida a planilha e mostra o que foi ignorado").set_defaults(f=cmd_contatos)
    sub.add_parser("previa", help="gera out/previa.html com todos os e-mails").set_defaults(f=cmd_previa)
    p = sub.add_parser("teste", help="manda e-mails de exemplo para o seu próprio Gmail")
    p.add_argument("--quantos", type=int, default=1)
    p.set_defaults(f=cmd_teste)
    p = sub.add_parser("enviar", help="simula (padrão) ou envia (--real)")
    p.add_argument("--real", action="store_true", help="envia de verdade")
    p.add_argument("--limite", type=int, help="máximo de e-mails nesta rodada")
    p.add_argument("--sem-followup", action="store_true")
    p.set_defaults(f=cmd_enviar)
    sub.add_parser("status", help="números gerais").set_defaults(f=cmd_status)
    p = sub.add_parser("caixa", help="lê o Gmail: respostas, SAIR e bounces")
    p.add_argument("--dias", type=int, default=14)
    p.set_defaults(f=cmd_caixa)
    p = sub.add_parser("marcar", help="marca andamento manualmente")
    p.add_argument("email")
    p.add_argument("status", choices=["respondeu", "negociacao", "bounce"])
    p.set_defaults(f=cmd_marcar)
    p = sub.add_parser("bloquear", help="coloca um e-mail na lista de bloqueio")
    p.add_argument("email")
    p.add_argument("--motivo", default="manual")
    p.set_defaults(f=cmd_bloquear)
    sub.add_parser("sincronizar", help="reescreve o status na planilha").set_defaults(f=cmd_sincronizar)

    args = ap.parse_args(argv)
    try:
        return args.f(args) or 0
    except (config.ErroConfig, mailer.ErroAutenticacao, ValueError) as e:
        print("Erro:", e, file=sys.stderr)
        return 2
