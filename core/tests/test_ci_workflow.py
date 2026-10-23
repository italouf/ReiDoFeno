"""A09: o workflow de CI deve cobrir a branch da Fase 2C."""
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOW = RAIZ / ".github" / "workflows" / "ci.yml"


class WorkflowCIBranchTests(SimpleTestCase):
    def test_push_da_fase_2c_dispara_ci(self):
        texto = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("fase-2c-analytics-fiscal", texto)
        self.assertIn("postgres:15", texto)
        self.assertIn("redis", texto.lower())
        self.assertIn("workflow_dispatch", texto)
        self.assertIn("node --test static/js/relatorios.test.mjs", texto)

    def test_fase_3_valida_docker_e_postgres(self):
        texto = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("fase-3-docker-staging", texto)
        self.assertIn("config.settings.test", texto)
        self.assertIn("docker build --target runtime", texto)
        self.assertIn("docker compose", texto)
        self.assertIn("makemigrations --check --dry-run", texto)
        self.assertIn("caddy validate", texto)
