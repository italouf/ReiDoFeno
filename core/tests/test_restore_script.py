"""Testes de contrato e sandbox para infra/backup/restore.sh e template de DRILL."""

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]
RESTORE_SCRIPT = RAIZ / "infra" / "backup" / "restore.sh"
DRILL_TEMPLATE = RAIZ / "docs" / "runbook" / "templates" / "drill-report.md"


def _encontrar_bash() -> str | None:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if os.name == "nt" and git_bash.is_file():
        return str(git_bash)
    candidato = shutil.which("bash")
    if candidato and "WindowsApps" not in candidato:
        return candidato
    return None


def _criar_binario_fake(bin_dir: Path, nome: str, corpo: str) -> None:
    caminho = bin_dir / nome
    caminho.write_text(f"#!/usr/bin/env bash\n{corpo}\n", encoding="utf-8", newline="\n")
    caminho.chmod(caminho.stat().st_mode | stat.S_IEXEC)


class RestoreScriptTests(SimpleTestCase):
    def test_restore_script_e_template_drill_existem(self):
        self.assertTrue(RESTORE_SCRIPT.is_file())
        self.assertNotIn(b"\r\n", RESTORE_SCRIPT.read_bytes())
        self.assertTrue(DRILL_TEMPLATE.is_file())
        conteudo = DRILL_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("RTO", conteudo)
        self.assertIn("RPO", conteudo)
        self.assertIn("Ledger reconciliado", conteudo)

        bash = _encontrar_bash()
        if not bash:
            self.skipTest("Bash compatível indisponível")
        res = subprocess.run(
            [bash, "-n", str(RESTORE_SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_restore_sandbox_restaura_midia_config_e_banco(self):
        bash = _encontrar_bash()
        if not bash:
            self.skipTest("Bash compatível indisponível")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            artifacts = tmp_path / "artifacts"
            target = tmp_path / "target"
            bin_dir.mkdir()
            artifacts.mkdir()

            (artifacts / "db.dump").write_bytes(b"PGDMP-FAKE-DUMP")

            # Cria media.tar.gz e config.tar.gz.age simulado
            src_dir = tmp_path / "src"
            (src_dir / "media").mkdir(parents=True)
            (src_dir / "media" / "nota.pdf").write_bytes(b"%PDF-1.4")
            (src_dir / ".env.docker").write_text("SECRET=1\n", encoding="utf-8")
            (artifacts / "age.key").write_text("AGE-SECRET-KEY-FAKE\n", encoding="utf-8")

            _criar_binario_fake(
                bin_dir,
                "pg_restore",
                'if [ "$1" = "--list" ] && [ -s "$2" ]; then exit 0; fi\nexit 1',
            )
            _criar_binario_fake(
                bin_dir,
                "age",
                'out=""\n'
                'while [ $# -gt 0 ]; do\n'
                '  case "$1" in\n'
                '    --decrypt|-d) shift ;;\n'
                '    -i) shift 2 ;;\n'
                '    -o) out="$2"; shift 2 ;;\n'
                '    *) src="$1"; shift ;;\n'
                '  esac\n'
                'done\n'
                'cp "$src" "$out"',
            )
            _criar_binario_fake(
                bin_dir,
                "docker",
                'cmd="$1"; shift\n'
                'case "$cmd" in\n'
                '  run) echo "fake-container-id"; exit 0 ;;\n'
                '  exec)\n'
                '    if echo "$*" | grep -q "pg_isready"; then exit 0; fi\n'
                '    if echo "$*" | grep -q "pg_restore"; then exit 0; fi\n'
                '    if echo "$*" | grep -q "psql"; then echo "Pedidos: 5"; exit 0; fi\n'
                '    exit 0 ;;\n'
                '  stop|rm) exit 0 ;;\n'
                'esac\n'
                'exit 1',
            )

            res = subprocess.run(
                [
                    bash,
                    "-c",
                    'set -euo pipefail\n'
                    'export PATH="$PWD/bin:$PATH"\n'
                    'tar -czf "$PWD/artifacts/media.tar.gz" -C "$PWD/src" media\n'
                    'tar -czf "$PWD/artifacts/config.tar.gz.age" -C "$PWD/src" .env.docker\n'
                    f'bash "{RESTORE_SCRIPT.as_posix()}" '
                    '--dump "$PWD/artifacts/db.dump" '
                    '--media "$PWD/artifacts/media.tar.gz" '
                    '--config "$PWD/artifacts/config.tar.gz.age" '
                    '--config-key "$PWD/artifacts/age.key" '
                    '--target "$PWD/target"\n'
                    'test -f "$PWD/target/media/nota.pdf"\n'
                    'test -f "$PWD/target/.env.docker"\n'
                    'test ! -f "$PWD/target/config.tar.gz"',
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertTrue(target.exists())
