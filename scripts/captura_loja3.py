"""Capturas de auditoria da loja v3 (descartável)."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8017"
OUT = ".impeccable/review"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR").new_page()

    pg.goto(BASE + "/")
    pg.wait_for_load_state("networkidle")
    pg.screenshot(path=f"{OUT}/loja3-home-desktop.png", full_page=True)

    href = pg.locator(".card-produto h3 a").first.get_attribute("href")
    pg.goto(BASE + href)
    pg.wait_for_load_state("networkidle")
    pg.screenshot(path=f"{OUT}/loja3-produto-desktop.png", full_page=True)

    # Adiciona ao carrinho e vai para o carrinho
    pg.click('form[action*="adicionar"] button[type="submit"]')
    pg.wait_for_load_state("networkidle")
    pg.goto(BASE + "/carrinho/")
    pg.wait_for_load_state("networkidle")
    pg.screenshot(path=f"{OUT}/loja3-carrinho-desktop.png", full_page=True)

    pg.goto(BASE + "/checkout/")
    pg.wait_for_load_state("networkidle")
    pg.screenshot(path=f"{OUT}/loja3-checkout-desktop.png", full_page=True)

    mob = b.new_context(
        viewport={"width": 390, "height": 844}, locale="pt-BR", is_mobile=True
    ).new_page()
    mob.goto(BASE + "/")
    mob.wait_for_load_state("networkidle")
    mob.screenshot(path=f"{OUT}/loja3-home-mobile.png", full_page=True)
    mob.click("[data-abrir-menu]")
    mob.wait_for_timeout(250)
    mob.screenshot(path=f"{OUT}/loja3-home-mobile-menu.png")
    b.close()

print("ok")
