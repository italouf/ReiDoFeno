"""Regressão da saída usada pelo smoke para verificar persistência."""
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]


class SmokeShellOutputTests(SimpleTestCase):
    def test_shell_verbosity_zero_emite_somente_o_valor(self):
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.development"
        env.pop("DATABASE_URL", None)

        resultado = subprocess.run(
            [
                sys.executable,
                "manage.py",
                "shell",
                "--verbosity",
                "0",
                "-c",
                "print(1)",
            ],
            cwd=RAIZ,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), "1")
