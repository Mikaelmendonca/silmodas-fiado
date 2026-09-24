"""Jornadas da dona da loja, no navegador de verdade."""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import em, hoje

pytestmark = pytest.mark.e2e


def preencher(
    page: Page, cliente: str, valor: str, prazo: int | None = None, o_que: str = ""
) -> None:
    page.get_by_label("Cliente").fill(cliente)
    if o_que:
        page.get_by_label("O que levou").fill(o_que)
    page.get_by_label("Valor (R$)").fill(valor)
    if prazo is not None:
        page.get_by_label("Prazo (dias)").fill(str(prazo))


def anotar(
    page: Page, cliente: str, valor: str, prazo: int | None = None, o_que: str = "", ok: bool = True
) -> None:
    """Preenche e envia. Com ok=True espera o envio terminar (o formulário volta limpo);
    sem essa espera o próximo preenchimento poderia ser apagado pelo reset do anterior."""
    preencher(page, cliente, valor, prazo, o_que)
    page.get_by_role("button", name="Anotar fiado").click()
    if ok:
        expect(page.get_by_label("Cliente")).to_have_value("")


def toast(page: Page):
    return page.locator("#msg")


@pytest.fixture
def painel(page: Page, live_server: str) -> Page:
    page.goto(live_server)
    expect(page.get_by_test_id("alert-status")).to_contain_text("ligados")
    return page


# --- Abertura ----------------------------------------------------------------------------------


def test_painel_abre_vazio_e_com_alertas_ligados(painel: Page):
    expect(painel).to_have_title(re.compile("Silmodas"))
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 0,00")
    expect(painel.get_by_test_id("reminders")).to_contain_text("Nada para cobrar hoje")
    expect(painel.get_by_test_id("all-debts")).to_contain_text("Nenhum fiado anotado ainda")
    expect(painel.get_by_test_id("alert-status")).to_contain_text("todo dia às 08:00")


# --- Prazo <-> vencimento ----------------------------------------------------------------------


def test_digitar_o_prazo_calcula_o_vencimento(painel: Page):
    painel.get_by_label("Prazo (dias)").fill("10")
    expect(painel.get_by_label("Vencimento")).to_have_value(em(10).isoformat())


def test_escolher_o_vencimento_calcula_o_prazo(painel: Page):
    painel.get_by_label("Vencimento").fill(em(7).isoformat())
    expect(painel.get_by_label("Prazo (dias)")).to_have_value("7")


def test_vencimento_no_passado_nao_deixa_anotar(painel: Page):
    painel.get_by_label("Cliente").fill("Ana")
    painel.get_by_label("Valor (R$)").fill("50,00")
    painel.get_by_label("Vencimento").fill(em(-1).isoformat())
    painel.get_by_role("button", name="Anotar fiado").click()

    assert painel.eval_on_selector("[name=due_date]", "el => el.validity.rangeUnderflow")
    expect(painel.get_by_test_id("debt-card")).to_have_count(0)


# --- Anotar e cobrar ---------------------------------------------------------------------------


def test_anotar_fiado_com_prazo_aparece_na_lista(painel: Page):
    anotar(painel, "Helena", "300,00", prazo=10, o_que="Vestido de festa")

    expect(toast(painel)).to_have_text("Fiado anotado!")
    card = painel.get_by_test_id("all-debts").get_by_test_id("debt-card")
    expect(card).to_have_count(1)
    expect(card).to_contain_text("Helena")
    expect(card).to_contain_text("Vestido de festa")
    expect(card).to_contain_text("prazo de 10d")
    expect(card).to_contain_text("Falta R$ 300,00")
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 300,00")
    # Ainda faltam 10 dias: não é para cobrar hoje.
    expect(painel.get_by_test_id("reminders")).to_contain_text("Nada para cobrar hoje")
    # E o formulário volta limpo para o próximo cadastro.
    expect(painel.get_by_label("Cliente")).to_have_value("")


def test_fiado_que_vence_hoje_entra_em_cobrar_agora(painel: Page):
    anotar(painel, "Bruno", "300,00", prazo=0)

    cobrar = painel.get_by_test_id("reminders").get_by_test_id("debt-card")
    expect(cobrar).to_have_count(1)
    expect(cobrar).to_contain_text("Bruno")
    expect(cobrar).to_contain_text("Vence hoje")
    expect(painel.get_by_test_id("due-today-count")).to_have_text("1")


def test_valor_invalido_mostra_erro_e_nao_anota(painel: Page):
    anotar(painel, "Ana", "abc", prazo=5, ok=False)

    expect(toast(painel)).to_contain_text("Valor inválido")
    expect(painel.get_by_test_id("debt-card")).to_have_count(0)


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("1.250,50", "1.250,50"),  # padrão brasileiro
        ("1250,50", "1.250,50"),  # sem separador de milhar
        ("1250.50", "1.250,50"),  # ponto como decimal (teclado numérico do celular)
        ("R$ 1.250,50", "1.250,50"),  # colado com o símbolo
        ("1.250", "1.250,00"),  # ponto seguido de 3 dígitos = milhar
        ("300", "300,00"),
        ("0,5", "0,50"),
        ("12.5", "12,50"),
    ],
)
def test_formatos_de_valor_digitados(painel: Page, digitado: str, esperado: str):
    """Regressão: '1250.50' virava R$ 125.050,00 (100x mais)."""
    anotar(painel, "Carla", digitado, prazo=5)
    expect(painel.get_by_test_id("total-open")).to_have_text(
        re.compile(rf"R\$\s{re.escape(esperado)}")
    )


def test_clique_duplo_em_anotar_nao_duplica_o_fiado(painel: Page):
    """Regressão: com o botão ativo durante o envio, dois cliques criavam dois fiados."""
    preencher(painel, "Bruno", "300,00", prazo=5)
    painel.get_by_role("button", name="Anotar fiado").dblclick()

    expect(painel.get_by_label("Cliente")).to_have_value("")
    expect(painel.get_by_test_id("all-debts").get_by_test_id("debt-card")).to_have_count(1)
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 300,00")


# --- Pagamentos --------------------------------------------------------------------------------


def test_pagamento_parcial_reduz_o_saldo(painel: Page):
    anotar(painel, "Bruno", "300,00", prazo=0)
    painel.once("dialog", lambda d: d.accept("100,00"))
    painel.get_by_test_id("reminders").get_by_role("button", name="Registrar pagamento").click()

    expect(toast(painel)).to_have_text("Pagamento registrado.")
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 200,00")
    cobrar = painel.get_by_test_id("reminders").get_by_test_id("debt-card")
    expect(cobrar).to_contain_text("Falta R$ 200,00")
    expect(cobrar.locator(".bar")).to_be_visible()  # barra de progresso do que já foi pago


def test_pagamento_total_quita_e_sai_de_cobrar_agora(painel: Page):
    anotar(painel, "Bruno", "300,00", prazo=0)
    sugerido = []

    def aceitar_sugestao(d):
        sugerido.append(d.default_value)
        d.accept(d.default_value)

    painel.once("dialog", aceitar_sugestao)
    painel.get_by_test_id("reminders").get_by_role("button", name="Registrar pagamento").click()

    expect(painel.get_by_test_id("reminders")).to_contain_text("Nada para cobrar hoje")
    assert sugerido == ["300,00"]  # o valor sugerido já é o saldo todo
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 0,00")
    expect(painel.get_by_test_id("all-debts").get_by_test_id("debt-card")).to_contain_text("Pago")


def test_nao_deixa_pagar_mais_que_o_saldo(painel: Page):
    anotar(painel, "Bruno", "300,00", prazo=0)
    painel.once("dialog", lambda d: d.accept("999,00"))
    painel.get_by_test_id("reminders").get_by_role("button", name="Registrar pagamento").click()

    expect(toast(painel)).to_contain_text("excede o saldo")
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 300,00")  # nada mudou


def test_cancelar_o_pagamento_nao_altera_nada(painel: Page):
    anotar(painel, "Bruno", "300,00", prazo=0)
    painel.once("dialog", lambda d: d.dismiss())
    painel.get_by_test_id("reminders").get_by_role("button", name="Registrar pagamento").click()
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 300,00")


# --- Apagar ------------------------------------------------------------------------------------


def test_apagar_pede_confirmacao(painel: Page):
    anotar(painel, "Bruno", "300,00", prazo=3)
    card = painel.get_by_test_id("all-debts").get_by_test_id("debt-card")

    painel.once("dialog", lambda d: d.dismiss())
    card.get_by_role("button", name="Apagar").click()
    expect(card).to_have_count(1)  # cancelou: continua lá

    painel.once("dialog", lambda d: d.accept())
    card.get_by_role("button", name="Apagar").click()
    expect(card).to_have_count(0)
    expect(painel.get_by_test_id("all-debts")).to_contain_text("Nenhum fiado anotado ainda")


# --- Alertas no celular: a funcionalidade principal, de ponta a ponta -------------------------


def test_botao_enviar_alertas_manda_a_notificacao_certa_uma_unica_vez(painel: Page, notifier):
    anotar(painel, "Bruno", "300,00", prazo=0)

    painel.get_by_role("button", name="Enviar alertas de hoje").click()
    expect(toast(painel)).to_contain_text("1 alerta(s) enviado(s)")
    assert [a.message for a in notifier.sent] == [
        "Prazo de Bruno finaliza hoje. Está devendo R$ 300,00."
    ]

    painel.get_by_role("button", name="Enviar alertas de hoje").click()
    expect(toast(painel)).to_contain_text("Nada novo para avisar agora")
    assert len(notifier.sent) == 1  # não repete no mesmo dia


def test_alerta_de_amanha_e_de_tres_dias_mas_nao_de_dois(painel: Page, notifier):
    anotar(painel, "Amanha", "100,00", prazo=1)
    anotar(painel, "TresDias", "100,00", prazo=3)
    anotar(painel, "DoisDias", "100,00", prazo=2)

    painel.get_by_role("button", name="Enviar alertas de hoje").click()
    expect(toast(painel)).to_contain_text("2 alerta(s) enviado(s)")
    assert {a.title for a in notifier.sent} == {"Vence amanhã: Amanha", "Vence em 3 dias: TresDias"}


def test_alerta_mostra_o_saldo_depois_de_pagamento_parcial(painel: Page, notifier):
    anotar(painel, "Bruno", "300,00", prazo=0)
    painel.once("dialog", lambda d: d.accept("100,00"))
    painel.get_by_test_id("reminders").get_by_role("button", name="Registrar pagamento").click()
    expect(painel.get_by_test_id("total-open")).to_have_text("R$ 200,00")

    painel.get_by_role("button", name="Enviar alertas de hoje").click()
    expect(toast(painel)).to_contain_text("1 alerta(s)")
    assert notifier.sent[0].message == "Prazo de Bruno finaliza hoje. Está devendo R$ 200,00."


def test_botao_testar_no_celular(painel: Page, notifier):
    painel.get_by_role("button", name="Testar no celular").click()
    expect(toast(painel)).to_have_text("Notificação de teste enviada!")
    assert [a.kind for a in notifier.sent] == ["test"]


def test_falha_no_envio_avisa_e_tenta_de_novo_depois(painel: Page, notifier):
    anotar(painel, "Bruno", "300,00", prazo=0)
    notifier.fail = True
    painel.get_by_role("button", name="Enviar alertas de hoje").click()
    expect(toast(painel)).to_contain_text("0 alerta(s) enviado(s), 1 falha(s)")

    notifier.fail = False
    painel.get_by_role("button", name="Enviar alertas de hoje").click()
    expect(toast(painel)).to_contain_text("1 alerta(s) enviado(s), 0 falha(s)")
    assert len(notifier.sent) == 1


# --- Segurança e responsividade ----------------------------------------------------------------


def test_html_no_nome_do_cliente_e_mostrado_como_texto_e_nao_executado(painel: Page):
    xss = "<img src=x onerror=window.__pwned=1>"
    anotar(painel, xss, "10,00", prazo=1)

    card = painel.get_by_test_id("all-debts").get_by_test_id("debt-card")
    expect(card).to_contain_text(xss)  # aparece literalmente
    assert painel.evaluate("window.__pwned") is None  # e nada foi executado
    expect(card.locator("img")).to_have_count(0)


def test_layout_do_celular_nao_tem_rolagem_horizontal(page: Page, live_server: str):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server)
    anotar(page, "Maria Aparecida dos Santos Oliveira", "1250,00", prazo=0, o_que="Vestido longo")
    expect(page.get_by_test_id("debt-card").first).to_be_visible()

    largura_pagina, largura_tela = page.evaluate(
        "[document.documentElement.scrollWidth, window.innerWidth]"
    )
    assert largura_pagina <= largura_tela


def test_data_de_hoje_do_servidor_bate_com_a_do_navegador(painel: Page):
    """Sem isso, perto da meia-noite o 'vence hoje' apareceria no dia errado."""
    anotar(painel, "Bruno", "10,00", prazo=0)
    card = painel.get_by_test_id("all-debts").get_by_test_id("debt-card")
    expect(card).to_contain_text(f"vence {hoje():%d/%m/%Y}")


# --- Senha do painel (necessária para abrir no celular) ----------------------------------------


def test_painel_protegido_pede_senha_e_funciona_inteiro_depois_de_autenticar(
    browser, live_server_protected: str
):
    # Sem senha o Chrome nem abre a página; pelo cliente HTTP do Playwright vemos o 401.
    sem_senha = browser.new_context()
    assert sem_senha.request.get(live_server_protected).status == 401
    sem_senha.close()

    com_senha = browser.new_context(
        http_credentials={"username": "mae", "password": "segredo1"},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
    )
    page = com_senha.new_page()
    page.goto(live_server_protected)
    expect(page.get_by_test_id("alert-status")).to_contain_text("ligados")
    anotar(page, "Bruno", "300,00", prazo=0)  # o JavaScript reaproveita a senha nas chamadas à API
    expect(page.get_by_test_id("total-open")).to_have_text("R$ 300,00")
    com_senha.close()


def test_senha_errada_nao_entra(browser, live_server_protected: str):
    contexto = browser.new_context(http_credentials={"username": "mae", "password": "errada"})
    assert contexto.request.get(live_server_protected).status == 401
    contexto.close()
