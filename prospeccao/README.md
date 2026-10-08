# Prospecção de parcerias · Camila Arcanjo

Envia e-mails de parceria personalizados por marca e segmento, com intervalo entre os envios,
limite diário, follow-up, registro de quem já recebeu e status na planilha.

## Passo a passo (primeira vez)

1. **Instale o Python 3.10+** (python.org) e, na pasta `prospeccao`, rode:
   `pip install -r requirements.txt`
2. **Crie a senha de app do Gmail**: Conta Google > Segurança > ative a *Verificação em duas etapas* >
   *Senhas de app* > crie uma. Copie as 16 letras.
3. **Configure o acesso**: copie `.env.example` para `.env` e preencha `GMAIL_USER` e `GMAIL_APP_PASSWORD`.
   O `.env` nunca vai para o Git e nenhuma senha fica no código.
4. **Coloque sua planilha** nesta pasta como `contatos.xlsx` (ou `.csv`). Colunas reconhecidas:
   `Marca`, `E-mail de Contato para Parceria`, `Ramo / Segmento`. Opcionais: `Cidade`, `Nome do contato`,
   `Motivo consumo` (veja abaixo). O app cria sozinho as colunas `Status`, `Enviado em` e `Observações`.
   Feche a planilha no Excel antes de rodar.
5. (Opcional) Salve o PDF do media kit aqui e preencha `arquivos.pdf_portfolio` no `config.yaml`.
   Sem PDF, vai só o link do portfólio.
6. Ajuste `config.yaml` (limite diário, horário, follow-up) e leia/edite os textos em `templates.yaml`.

## Rotina de uso

| O que fazer | Comando |
|---|---|
| Ver quantas linhas valem e quantas foram ignoradas | `python -m prospect contatos` |
| Ver todos os e-mails no navegador | `python -m prospect previa` (abre `out/previa.html`) |
| Simular o envio (nada sai) | `python -m prospect enviar` |
| **Mandar um teste para o seu Gmail** | `python -m prospect teste` |
| **Envio real** | `python -m prospect enviar --real` |
| Ver respostas, pedidos de SAIR e bounces | `python -m prospect caixa` |
| Marcar uma marca como "em negociação" | `python -m prospect marcar email@marca.com negociacao` |
| Bloquear um e-mail para sempre | `python -m prospect bloquear email@marca.com` |
| Números gerais | `python -m prospect status` |

Ordem recomendada: `contatos` > `previa` > `enviar` (simulação) > `teste` > `enviar --limite 5 --real` > `enviar --real`.
Sempre que você rodar `caixa`, ele atualiza a planilha com *Respondeu* e *Erro* (bounce).

## Como o envio se comporta

- 60 a 90 segundos aleatórios entre e-mails (`envio.intervalo_min/max`).
- Só envia dentro do horário (padrão: seg a sex, 9h às 18h, horário de Brasília); fora dele, espera.
- Limite diário (padrão 20). Ao atingir, para; rode de novo no dia seguinte e ele continua de onde parou.
- Nunca manda duas vezes para o mesmo endereço (banco em `data/envios.db`). Se o programa for interrompido
  (Ctrl+C, queda de internet), é só rodar de novo.
- Follow-up engraçadinho 6 dias depois, só para quem não respondeu, não pediu SAIR e não deu bounce. Máximo 1.
- Rodapé de descadastro em todo e-mail; quem responder SAIR (detectado pelo `caixa`) entra na lista de bloqueio.
- No fim: resumo com enviados, falhas e pulados.

## Pontos de atenção (leia antes do envio real)

- **"Só indico marcas que eu já consumo"**: o app só afirma isso quando a coluna `Motivo consumo` está
  preenchida para aquela marca. Sem ela, usa uma frase que não afirma consumo. Preencha só com a verdade.
- **"Não foi escrito por IA, kkk"**: deixe só se você revisar os textos. Desligue em `aviso_humano.ativo`.
- **Sem promessas**: os textos não prometem resultado e não oferecem serviço jurídico nem captam clientes.
  Se for editar, mantenha assim (também por causa das regras de publicidade da advocacia).
- **Números de audiência** só entram se você ligar `audiencia.ativo` e escrever dados reais.
- **Spam**: comece com 5 a 10 por dia, com e-mails que você revisou. Muitos envios iguais para
  desconhecidos podem fazer o Gmail marcar como spam. O app já varia assunto e abertura.
- **LGPD**: contatos comerciais públicos de marcas, com opção clara de saída. Mesmo assim, respeite
  qualquer pedido de remoção imediatamente.

## Testes

`pip install pytest && python -m pytest tests`
