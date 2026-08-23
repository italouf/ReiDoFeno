"""Captura de telas para a rodada de inspeção visual (descartável)."""
import pathlib

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8017"
OUT = pathlib.Path(".impeccable/review")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("gestao", "/painel/painel/", True),
    ("produtos", "/catalogo/produtos/", True),
    ("loja", "/", False),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR")
    page = ctx.new_page()
    # login (autenticação também é capturada)
    page.goto(BASE + "/accounts/login/")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(OUT / "login-desktop.png"), full_page=True)
    page.fill('input[name="username"]', "demo")
    page.fill('input[name="password"]', "demo-12345")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    for nome, rota, _auth in PAGES:
        page.goto(BASE + rota)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(OUT / f"{nome}-desktop.png"), full_page=True)

    mob = browser.new_context(
        viewport={"width": 390, "height": 844}, locale="pt-BR", is_mobile=True
    )
    mpage = mob.new_page()
    mpage.goto(BASE + "/accounts/login/")
    mpage.wait_for_load_state("networkidle")
    mpage.screenshot(path=str(OUT / "login-mobile.png"), full_page=True)
    mpage.goto(BASE + "/")
    mpage.wait_for_load_state("networkidle")
    mpage.screenshot(path=str(OUT / "loja-mobile.png"), full_page=True)
    mpage.goto(BASE + "/carrinho/")
    mpage.wait_for_load_state("networkidle")
    mpage.screenshot(path=str(OUT / "carrinho-mobile.png"), full_page=True)
    # gestão logado no mobile
    mpage.goto(BASE + "/accounts/login/")
    mpage.fill('input[name="username"]', "demo")
    mpage.fill('input[name="password"]', "demo-12345")
    mpage.click('button[type="submit"]')
    mpage.wait_for_load_state("networkidle")
    mpage.goto(BASE + "/painel/painel/")
    mpage.wait_for_load_state("networkidle")
    mpage.screenshot(path=str(OUT / "gestao-mobile.png"), full_page=True)
    # gaveta aberta
    mpage.click("[data-abrir-gaveta]")
    mpage.wait_for_timeout(300)
    mpage.screenshot(path=str(OUT / "gestao-mobile-gaveta.png"))
    browser.close()

print("capturas:", sorted(x.name for x in OUT.glob("*.png")))
