"""E2E: pagamento manual → conciliação → NF-e assistida."""

import re

import pytest
from playwright.sync_api import expect, sync_playwright

from core.models import LogAuditoria
from sales.models import ComprovantePagamento, Pagamento, Pedido
from stock.models import Estoque

pytestmark = [pytest.mark.django_db(transaction=True)]

CHAVE = "29260812345678901234567890123456789012345678"


def _criar_usuarios():
    from django.contrib.auth.models import Group
    from django.core.management import call_command

    from accounts.models import Usuario

    call_command("seed_groups", verbosity=0)
    senha = "senha-forte-123"
    usuarios = {}
    for username, grupo in (
        ("vendedor-e2e", "Vendedor"),
        ("financeiro-e2e", "Financeiro"),
        ("emissor-e2e", "Emissor Fiscal"),
    ):
        usuario = Usuario.objects.create_user(
            username=username, password=senha
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        usuarios[username] = senha
    return usuarios


def _login(contexto, base, username, senha):
    page = contexto.new_page()
    page.goto(f"{base}/accounts/login/")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", senha)
    page.click("button[type='submit']")
    return page


def test_fluxo_completo_pagamento_manual(live_server, tmp_path):
    from catalog.factories import ProdutoFactory
    from core.factories import UnidadeFactory
    from stock.factories import EstoqueFactory

    usuarios = _criar_usuarios()
    produto = ProdutoFactory(nome="Feno E2E", preco_online="10.00")
    unidade = UnidadeFactory(nome="Feira de Santana")
    EstoqueFactory(
        produto=produto,
        unidade=unidade,
        quantidade="50.00",
        quantidade_minima="10.00",
    )
    pdf = tmp_path / "nfe.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake e2e")

    base = live_server.url
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 1. Vendedor cria o pedido pela loja.
        contexto_vendedor = browser.new_context()
        page = _login(
            contexto_vendedor, base, "vendedor-e2e", usuarios["vendedor-e2e"]
        )
        page.goto(f"{base}/produto/{produto.pk}/")
        page.fill("input[name='quantidade']", "2")
        page.get_by_role("button", name="Adicionar ao carrinho").click()
        page.get_by_role("link", name="Finalizar compra").click()
        page.fill("input[name='nome']", "Cliente E2E")
        page.fill("input[name='documento']", "529.982.247-25")
        page.fill("input[name='email']", "e2e@example.com")
        page.check("input[value='retirada']")
        option_value = page.eval_on_selector(
            "select[name='unidade']",
            "sel => Array.from(sel.options).find(o => o.value).value",
        )
        page.select_option("select[name='unidade']", option_value)
        page.get_by_role("button", name="Revisar e pagar").click()
        expect(page.locator("h1")).to_contain_text("PF")

        # 2. Vendedor registra PIX manual com comprovante.
        page.goto(f"{base}/gestao/pedidos/")
        page.get_by_role("link", name="Abrir").first.click()
        expect(page.locator("h1")).to_contain_text("PF")
        pedido_pk = int(
            re.search(r"/gestao/pedidos/(\d+)/", page.url).group(1)
        )
        page.get_by_role("link", name="Registrar pagamento manual").click()
        page.select_option("select[name='metodo']", "pix")
        page.fill("input[name='valor']", "20.00")
        page.fill("input[name='data_pagamento']", "2026-11-10T14:30")
        page.fill("input[name='referencia']", "E2E123456789")
        page.set_input_files("input[name='arquivo']", str(pdf))
        page.get_by_role("button", name="Registrar pagamento").click()
        expect(page.locator("body")).to_contain_text("registrado")
        expect(page.locator("body")).to_contain_text("Pago")

        # 3. Financeiro concilia.
        contexto_financeiro = browser.new_context()
        page_financeiro = _login(
            contexto_financeiro,
            base,
            "financeiro-e2e",
            usuarios["financeiro-e2e"],
        )
        page_financeiro.goto(f"{base}/gestao/conciliacao/")
        expect(page_financeiro.locator("body")).to_contain_text("Cliente E2E")
        page_financeiro.get_by_role("button", name="Conciliar").first.click()
        expect(page_financeiro.locator("body")).to_contain_text("conciliado")

        # 4. Emissor anexa PDF e autoriza a NF-e.
        contexto_emissor = browser.new_context()
        page_emissor = _login(
            contexto_emissor, base, "emissor-e2e", usuarios["emissor-e2e"]
        )
        page_emissor.goto(f"{base}/fiscal/pedidos/{pedido_pk}/nota-anexar/")
        page_emissor.fill("input[name='numero']", "123")
        page_emissor.fill("input[name='serie']", "1")
        page_emissor.fill("input[name='chave_acesso']", CHAVE)
        page_emissor.fill("input[name='data_emissao']", "2026-11-10T14:30")
        page_emissor.set_input_files("input[name='pdf']", str(pdf))
        page_emissor.get_by_role("button", name="Anexar PDF").click()
        expect(page_emissor.locator("body")).to_contain_text("anexada")

        page_emissor.goto(f"{base}/fiscal/notas/")
        expect(page_emissor.locator("body")).to_contain_text("Anexada (PDF)")
        page_emissor.get_by_role("button", name="Autorizar").first.click()
        expect(page_emissor.locator("body")).to_contain_text("Autorizada")

        browser.close()

    # Asserções de banco fora do event loop do Playwright.
    pedido = Pedido.objects.get(pk=pedido_pk)
    pedido.refresh_from_db()
    assert pedido.status_financeiro == Pedido.StatusFinanceiro.PAGO
    assert pedido.financeiro_conciliado is True
    assert pedido.comprovantes.count() == 1
    comprovante = pedido.comprovantes.get()
    assert comprovante.status == ComprovantePagamento.Status.CONCILIADO
    assert comprovante.arquivo
    assert Pagamento.objects.get(pedido=pedido).status == Pagamento.Status.APROVADO

    nota = pedido.notas_fiscais.get(tipo="saida")
    assert nota.status == "autorizada"
    assert nota.numero == "123"
    assert nota.chave_acesso == CHAVE
    assert nota.pdf
    assert nota.cliente_nome == "Cliente E2E"
    assert nota.retido_ate is not None

    estoque = Estoque.objects.get(produto=produto, unidade=unidade)
    assert str(estoque.quantidade) == "48.00"
    assert str(estoque.quantidade_bloqueada) == "0.00"

    assert LogAuditoria.objects.filter(
        acao="pagamento_manual_registrado", objeto_id=str(pedido.pk)
    ).exists()
    assert LogAuditoria.objects.filter(
        acao="pedido_conciliado", objeto_id=str(pedido.pk)
    ).exists()
    assert LogAuditoria.objects.filter(
        acao="fiscal.nota_anexada", objeto_id=str(nota.pk)
    ).exists()
    assert LogAuditoria.objects.filter(
        acao="fiscal.nota_autorizada_manual", objeto_id=str(nota.pk)
    ).exists()
