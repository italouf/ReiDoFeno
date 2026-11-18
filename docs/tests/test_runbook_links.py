"""Validação estrutural e de links internos do runbook operacional."""
import re
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import resolve

RAIZ = Path(__file__).resolve().parents[2]
RUNBOOK = RAIZ / "docs" / "runbook.md"


class RunbookLinksTests(SimpleTestCase):
    def setUp(self):
        self.texto = RUNBOOK.read_text(encoding="utf-8")

    def test_secoes_obrigatorias_presentes(self):
        for marcador in (
            "Contatos de Emergência",
            "Árvore de Decisão",
            "Procedimentos de Emergência",
            "Perda de acesso 2FA",
            "Backup falhou",
            "Plano de Fuga",
            "DRILL de Restauração",
            "Checklist",
            "ADR-019",
            "ADR-020",
        ):
            with self.subTest(marcador=marcador):
                self.assertIn(marcador, self.texto)

    def test_links_markdown_locais_resolvem_arquivos(self):
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", self.texto)
        self.assertTrue(links)
        for destino in links:
            if destino.startswith(("http://", "https://", "#", "mailto:")):
                continue
            caminho_relativo = destino.split("#", 1)[0]
            alvo = (RUNBOOK.parent / caminho_relativo).resolve()
            with self.subTest(link=destino):
                self.assertTrue(alvo.exists(), f"Link quebrado no runbook: {destino}")

    def test_rotas_django_citadas_resolvem(self):
        for rota in (
            "/healthz/",
            "/accounts/login/",
            "/accounts/2fa/setup/",
            "/accounts/2fa/verify/",
            "/gestao/pedidos/",
            "/gestao/pedidos/1/",
            "/gestao/conciliacao/",
            "/fiscal/notas/",
            "/fiscal/pedidos/1/nota-anexar/",
        ):
            with self.subTest(rota=rota):
                self.assertIn(rota.replace("/1/", "/<pk>/"), self.texto)
                resolve(rota)
