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
        self.assertIn("workflow_dispatch", texto)
