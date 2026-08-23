"""E2E: fluxo completo de compra (vitrine → carrinho → checkout → pagamento)."""
import re
import uuid

import pytest
from playwright.sync_api import expect, sync_playwright

from sales.models import Pedido
from stock.models import Estoque

pytestmark = [pytest.mark.django_db(transaction=True)]


def test_compra_completa_ate_estoque_baixado(live_server):
    from catalog.factories import ProdutoFactory
    from core.factories import UnidadeFactory
    from stock.factories import EstoqueFactory

    produto = ProdutoFactory(nome="Feno Tifton 85", preco_online="10.00")
    unidade = UnidadeFactory(nome="Feira de Santana")
    EstoqueFactory(
        produto=produto,
        unidade=unidade,
        quantidade="50.00",
        quantidade_minima="10.00",
    )

    base = live_server.url

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})

        # Página do produto (mobile-first)
        page.goto(f"{base}/produto/{produto.pk}/")
        page.fill("input[name='quantidade']", "2")
        page.get_by_role("button", name="Adicionar ao carrinho").click()

        # Carrinho
        expect(page.locator("h1")).to_have_text("Carrinho")
        expect(page.locator("tbody")).to_contain_text("20")
        page.get_by_role("link", name="Finalizar pedido").click()

        # Checkout
        page.fill("input[name='nome']", "João Fazendeiro")
        page.fill("input[name='documento']", "529.982.247-25")
        page.fill("input[name='email']", "joao@example.com")
        page.check("input[value='retirada']")
        option_value = page.eval_on_selector(
            "select[name='unidade']",
            "sel => Array.from(sel.options).find(o => o.value).value",
        )
        page.select_option("select[name='unidade']", option_value)
        botao_pagar = page.get_by_role("button", name="Revisar e pagar")
        trafego = []
        page.on("response", lambda r: trafego.append(f"{r.status} {r.url}"))
        botao_pagar.click()
        page.wait_for_timeout(1500)
        if "Finalizar pedido" in page.locator("h1").inner_text():
            erros = page.locator(".erro-lista").all_text_contents()
            browser.close()
            raise AssertionError(
                f"POST não navegou. URL={page.url} erros={erros} trafego={trafego}"
            )

        # Página do pedido: aguardando pagamento
        expect(page.locator("h1")).to_contain_text("PF")
        expect(page.locator(".badge")).to_contain_text("Aguardando pagamento")
        url_pedido = page.url

        # Pagamento (simulador em modo fake)
        page.get_by_role("link", name="Ir para o pagamento").click()
        page.get_by_role("button", name="Aprovar pagamento").click()

        expect(page.locator(".badge")).to_contain_text("Pago")
        browser.close()

    # Asserções de banco FORA do event loop do Playwright.
    token = uuid.UUID(
        re.search(r"/pedido/([0-9a-f-]{36})/", url_pedido).group(1)
    )
    pedido = Pedido.objects.get(token_acesso=token)
    assert pedido.status == Pedido.Status.PAGO

    estoque = Estoque.objects.get(produto=produto, unidade=unidade)
    assert str(estoque.quantidade) == "48.00"      # 50 - 2 baixados
    assert str(estoque.quantidade_bloqueada) == "0.00"
