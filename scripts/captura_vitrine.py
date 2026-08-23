"""Captura da vitrine/produto pós-imagens + validação do redirect pós-login (descartável)."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8017"
OUT = ".impeccable/review"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR").new_page()

    # Redirect pós-login deve cair em /painel/painel/
    pg.goto(BASE + "/accounts/login/")
    pg.fill('input[name="username"]', "demo")
    pg.fill('input[name="password"]', "demo-12345")
    pg.click('button[type="submit"]')
    pg.wait_for_load_state("networkidle")
    print("apos login:", pg.url)

    # Deslogar para ver a vitrine como visitante
    pg.goto(BASE + "/accounts/logout/", reference=None) if False else None
    ctx2 = b.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR")
    v = ctx2.new_page()
    v.goto(BASE + "/")
    v.wait_for_load_state("networkidle")
    v.screenshot(path=f"{OUT}/vitrine-fotos-desktop.png", full_page=True)

    # Primeiro produto da vitrine
    href = v.locator(".produto-cartao h3 a").first.get_attribute("href")
    v.goto(BASE + href)
    v.wait_for_load_state("networkidle")
    v.screenshot(path=f"{OUT}/produto-fotos-desktop.png", full_page=True)

    mob = b.new_context(
        viewport={"width": 390, "height": 844}, locale="pt-BR", is_mobile=True
    ).new_page()
    mob.goto(BASE + "/")
    mob.wait_for_load_state("networkidle")
    mob.screenshot(path=f"{OUT}/vitrine-fotos-mobile.png", full_page=True)
    b.close()
print("ok")
