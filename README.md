# 🧵 Silmodas · Fiado — controle de devedores com alertas no celular

Sistema para a loja da minha mãe anotar quem comprou **fiado / a prazo** e **ser avisada no
celular** quando o prazo está acabando:

> 🔔 **Vence hoje: Bruno** — Prazo de Bruno finaliza hoje. Está devendo R$ 300,00.

Nasceu de um problema real e também é um **projeto de portfólio**: o foco não é só o app, e sim
*como ele foi projetado para ser testável* e *como foi testado*.

## O que ele faz

- Anota o fiado com **valor**, **prazo (dias)** e **vencimento** — preencher um calcula o outro
- **Notificação push no celular** todo dia no horário escolhido (padrão 08:00):
  3 dias antes, 1 dia antes, **no dia** e **todo dia enquanto estiver atrasado**
- Nunca avisa duas vezes a mesma coisa no mesmo dia, mesmo que o app reinicie
- Se o computador estava desligado às 8h, **recupera o alerta assim que ligar**
- Pagamentos parciais: a mensagem mostra o **saldo que falta**, não o valor original
- Painel **"Cobrar agora"** e botão **Cobrar no WhatsApp** com mensagem educada pronta
- Botões "Testar no celular" e "Enviar alertas de hoje"

## Rodando

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fiado seed      # (opcional) dados de exemplo para ver o painel cheio
python -m fiado           # abra http://localhost:8000
```

Os dados ficam em `fiado.db` (SQLite). Documentação interativa da API em `/docs`.

## Recebendo os alertas no celular (2 minutos, grátis, sem conta)

O envio usa o [ntfy](https://ntfy.sh), um serviço de push de código aberto.

1. Instale o app **ntfy** no celular (Android / iPhone).
2. Invente um nome de tópico **longo e impossível de adivinhar**, ex.: `silmodas-k29x8f3q-alertas`.
   Quem souber o nome consegue ler os alertas (que trazem nomes e valores), então trate como senha.
3. No app, toque em **+** e assine esse tópico.
4. No computador: `cp .env.example .env` e preencha `FIADO_NTFY_TOPIC=silmodas-k29x8f3q-alertas`.
5. Rode `python -m fiado test` — a notificação de teste deve chegar no celular.

Para privacidade total dá para hospedar o próprio servidor ntfy (`FIADO_NTFY_SERVER`).

### Deixando rodando todo dia

O alerta sai de dentro do próprio app enquanto ele estiver aberto (`python -m fiado`). Se preferir
não deixar o app aberto, agende o comando abaixo no `cron` / Agendador de Tarefas; como ele é
idempotente, rodar mais de uma vez por dia é seguro:

```bash
python -m fiado alerts     # envia os alertas de hoje e sai
```

### Configuração (`.env`)

| Variável | Padrão | Para quê |
|---|---|---|
| `FIADO_NTFY_TOPIC` | — | Tópico do celular. Vazio = alertas só no log |
| `FIADO_ALERT_TIME` | `08:00` | Hora do envio diário |
| `FIADO_WARN_DAYS` | `3,1` | Avisar quando faltam X dias (além do dia do vencimento) |
| `FIADO_TZ` | `America/Sao_Paulo` | Fuso da loja (o "hoje" não depende do servidor) |
| `FIADO_DB` | `fiado.db` | Arquivo do banco |

> **Segurança:** o painel não tem senha e, por padrão, só abre neste computador (`127.0.0.1`).
> Para abrir no celular na mesma rede: `python -m fiado --host 0.0.0.0`. Não exponha na internet
> sem antes colocar autenticação (veja "Próximos passos").

## Arquitetura

```
domain.py      regras puras (status, atraso, pagamento, prazo→vencimento)   ┐
alerts.py      QUANDO avisar e O QUE dizer                                   ┘ sem I/O
scheduling.py  agendador diário (relógio e sleep injetáveis)
notifier.py    Notifier (Protocol) → NtfyNotifier | LogNotifier
service.py     casos de uso; envio idempotente de alertas
repository.py  SQLite (fiados + histórico de alertas enviados)
settings.py    configuração validada do ambiente
api.py         FastAPI + ciclo de vida do agendador   __main__.py  CLI
```

O `Notifier` é uma interface: trocar ntfy por Telegram ou e-mail é escrever uma classe de ~15
linhas, sem tocar em regra de negócio.

## Estratégia de testes

```bash
pytest                # 181 testes, ~2s, falha se cobertura < 95% (hoje 100%)
```

| Camada | Onde | O que valida |
|---|---|---|
| Unitário | `tests/unit/test_domain.py`, `test_alerts.py` | Regras puras: status por data, atraso, pagamento, prazo, texto exato das mensagens |
| Propriedades | `test_domain.py` (Hypothesis) | Invariantes para *qualquer* entrada: `pago + restante == total`, nunca paga a mais |
| Serviço | `tests/unit/test_service.py` | Alertas com banco em memória: sem duplicar, retentativa após falha, contagem regressiva dia a dia |
| Infra | `test_notifier.py`, `test_settings_scheduling.py`, `test_cli.py` | Payload HTTP (mock), config inválida, agendador com relógio falso, CLI |
| API | `tests/api/test_api.py` | Contrato HTTP, códigos 201/204/404/409/422/502, fluxo completo |
| CI | `.github/workflows/ci.yml` | Lint + testes em Python 3.11 / 3.12 / 3.13 |

### Decisões de projeto que tornam o sistema testável

- **Relógio injetável.** "Hoje" é uma dependência (`FakeClock`). O teste "alerta 3 dias antes,
  1 dia antes, no dia" avança os dias sem esperar nada — e não existe teste que "quebra amanhã".
- **Agendador sem `sleep` de verdade nos testes.** `run_daily` recebe `now` e `sleep`; os testes
  verificam que espera 2h às 06:00, que recupera o envio se subir às 09:00 e que um job que
  explode não mata o agendador de amanhã.
- **Idempotência registrada no banco.** `PRIMARY KEY (fiado, tipo, dia)` em `alerts_sent`: rodar
  `alerts` várias vezes, ou reiniciar o app, não repete notificação. (Limite conhecido: duas
  execuções *simultâneas* poderiam enviar antes de gravar; para uma loja com um único processo
  isso não ocorre.)
- **Falha de entrega não perde alerta.** Só marca como enviado depois que o envio deu certo; se o
  celular/servidor estava fora do ar, a próxima execução tenta de novo.
- **Dinheiro em centavos (inteiros).** Evita erro de ponto flutuante (`0.1 + 0.2`).
- **Domínio puro, sem I/O**, e **`create_app(...)` como fábrica**: cada teste sobe uma app nova
  com banco em memória e notificador falso.
- **Banco como última barreira.** `CHECK` no SQLite impede saldo negativo mesmo se a regra falhar.

### Técnicas de teste aplicadas

- **Análise de valor-limite** nas datas: 0/1/2/3/4 dias, ontem, virada de mês e de ano
- **Partição de equivalência** em valores (zero, negativo, 1 centavo), prazos e telefones
- **Teste baseado em propriedades** (Hypothesis)
- **Teste de entradas hostis**: HTML/`<script>`, SQL injection, unicode e emoji, tipos errados,
  prazo de `10**9` dias (estouraria a data)
- **Teste de estado e de falha**: pagar a mais deixa o saldo intacto; entrega que falha é retentada
- **Fluxo ponta a ponta** simulando a passagem dos dias

### Bug real encontrado pelos próprios testes

Um teste de telefone internacional (`+1 415 555 0100`) falhou: os 11 dígitos pareciam
"DDD + celular", e o sistema aceitava um número dos EUA como brasileiro, prefixando `55`. A
validação agora exige DDD válido, 9 iniciando em 9 para celular, 2–5 para fixo, e recusa `+` com
DDI diferente de 55. Os casos ficaram como testes de regressão.

## Próximos passos

- [ ] Autenticação no painel, caso seja exposto fora da rede local
- [ ] Testes E2E de navegador com Playwright (a UI já tem `data-testid`)
- [ ] Teste de mutação (`mutmut`) para medir a qualidade dos testes, não só a cobertura
- [ ] Segundo canal de alerta (Telegram / e-mail) — basta implementar `Notifier`
- [ ] Resumo diário único ("3 vencem hoje, total R$ 850") quando houver muitos devedores

## Stack

Python 3.11+ · FastAPI · SQLite · ntfy (push) · pytest · Hypothesis · Ruff · GitHub Actions
