"""Testes de contrato e execução em sandbox dos scripts de backup."""

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = RAIZ / "infra" / "backup" / "backup.sh"
RETENTION_SCRIPT = RAIZ / "infra" / "backup" / "apply-retention.sh"
RESTORE_SCRIPT = RAIZ / "infra" / "backup" / "restore.sh"
CRON_FILE = RAIZ / "infra" / "backup" / "cron.d" / "reidofeno-backup"


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


def _preparar_sandbox_backup(tmp_path: Path, *, checksum_invalido: bool = False) -> None:
    bin_dir = tmp_path / "bin"
    proj_dir = tmp_path / "proj"
    bin_dir.mkdir()
    (proj_dir / "infra").mkdir(parents=True)
    (proj_dir / "media").mkdir()
    (proj_dir / ".env.docker").write_text("DJANGO_SECRET_KEY=segredo\n", encoding="utf-8")
    (proj_dir / "infra" / ".env").write_text("DB_PASSWORD=123\n", encoding="utf-8")
    (proj_dir / "infra" / "docker-compose.yml").write_text(
        "name: reidofeno\n", encoding="utf-8"
    )
    (proj_dir / "infra" / "Caddyfile").write_text("localhost {}\n", encoding="utf-8")
    (proj_dir / "infra" / "transport.caddy").write_text("# transport\n", encoding="utf-8")
    (proj_dir / "infra" / "crontab").write_text("* * * * * true\n", encoding="utf-8")
    (proj_dir / "media" / "comprovante.pdf").write_bytes(b"%PDF-1.4 ok")

    _criar_binario_fake(
        bin_dir,
        "docker",
        'if [ "$1" = "compose" ]; then\n'
        '  shift\n'
        '  while [ "$1" != "exec" ] && [ $# -gt 0 ]; do shift; done\n'
        '  shift || true\n'
        '  if [ "$1" = "-T" ]; then shift; fi\n'
        '  svc="$1"; shift || true\n'
        '  if [ "$svc" = "db" ]; then\n'
        '    printf "PGDMP-FAKE-DUMP"\n'
        '    exit 0\n'
        '  elif [ "$svc" = "web" ]; then\n'
        '    tar -cz -C "$FAKE_PROJ_DIR" media\n'
        '    exit 0\n'
        '  fi\n'
        'fi\n'
        'exit 1',
    )
    _criar_binario_fake(
        bin_dir,
        "pg_restore",
        'if [ "$1" = "--list" ] && [ -s "$2" ]; then\n'
        '  grep -q "PGDMP-FAKE-DUMP" "$2"\n'
        '  exit $?\n'
        'fi\n'
        'exit 1',
    )
    _criar_binario_fake(
        bin_dir,
        "age",
        'out=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -o) out="$2"; shift 2 ;;\n'
        '    -r) shift 2 ;;\n'
        '    *) src="$1"; shift ;;\n'
        '  esac\n'
        'done\n'
        'printf "age-encryption.org/v1\\n" > "$out"\n'
        'cat "$src" >> "$out"',
    )
    cat_cmd = 'printf "CORROMPIDO"' if checksum_invalido else 'cat "$1"'
    _criar_binario_fake(
        bin_dir,
        "rclone",
        'cmd="$1"; shift\n'
        'if [ "$cmd" = "copy" ]; then\n'
        '  src="$1"; dst="$2"\n'
        '  mkdir -p "$dst"\n'
        '  cp -r "$src"/* "$dst"/\n'
        '  exit 0\n'
        'elif [ "$cmd" = "cat" ]; then\n'
        f'  {cat_cmd}\n'
        '  exit 0\n'
        'fi\n'
        'exit 1',
    )


class BackupScriptsContractTests(SimpleTestCase):
    def test_scripts_existem_com_lf_e_sintaxe_valida(self):
        for caminho in (BACKUP_SCRIPT, RETENTION_SCRIPT, RESTORE_SCRIPT, CRON_FILE):
            self.assertTrue(caminho.is_file(), f"Ausente: {caminho}")
            self.assertNotIn(b"\r\n", caminho.read_bytes(), f"CRLF em {caminho}")

        if os.name != "nt":
            for script in (BACKUP_SCRIPT, RETENTION_SCRIPT, RESTORE_SCRIPT):
                self.assertTrue(
                    os.access(script, os.X_OK),
                    f"Script sem permissão de execução (+x): {script}",
                )

        bash = _encontrar_bash()
        if not bash:
            self.skipTest("Bash compatível indisponível")

        for script in (BACKUP_SCRIPT, RETENTION_SCRIPT, RESTORE_SCRIPT):
            res = subprocess.run(
                [bash, "-n", str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_dry_run_gera_dump_e_config_criptografada_e_valida_checksum(self):
        bash = _encontrar_bash()
        if not bash:
            self.skipTest("Bash compatível indisponível")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _preparar_sandbox_backup(tmp_path)
            backup_dir = tmp_path / "out"
            log_file = tmp_path / "logs" / "backup.log"
            remote_dir = tmp_path / "remote"

            res = subprocess.run(
                [
                    bash,
                    "-c",
                    'set -euo pipefail\n'
                    'export PATH="$PWD/bin:$PATH"\n'
                    'export FAKE_PROJ_DIR="$PWD/proj"\n'
                    'export PROJECT_DIR="$PWD/proj"\n'
                    'export BACKUP_LOCAL="$PWD/out"\n'
                    'export BACKUP_LOG="$PWD/logs/backup.log"\n'
                    'export BACKUP_AGE_RECIPIENT="age1testrecipient000000000000000"\n'
                    'export BACKUP_REMOTE="$PWD/remote"\n'
                    f'bash "{BACKUP_SCRIPT.as_posix()}" --dry-run\n'
                    'test -f "$PWD/out/db.dump"\n'
                    'test -f "$PWD/out/media.tar.gz"\n'
                    'test -f "$PWD/out/config.tar.gz.age"\n'
                    'test ! -f "$PWD/out/config.tar.gz"\n'
                    'grep -q "age-encryption.org/v1" "$PWD/out/config.tar.gz.age"\n'
                    'export BACKUP_OFFSITE=true\n'
                    'export BACKUP_STAMP=20261117_0230\n'
                    f'bash "{BACKUP_SCRIPT.as_posix()}"\n'
                    'test -f "$PWD/remote/20261117_0230/db-20261117_0230.dump"\n'
                    'grep -q "SUCCESS: backup completo" "$PWD/logs/backup.log"',
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertTrue(backup_dir.exists())
            self.assertTrue(log_file.exists())
            self.assertTrue(remote_dir.exists())

    def test_falha_quando_checksum_remoto_diverge_ou_sem_chave_age(self):
        bash = _encontrar_bash()
        if not bash:
            self.skipTest("Bash compatível indisponível")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _preparar_sandbox_backup(tmp_path, checksum_invalido=True)
            res = subprocess.run(
                [
                    bash,
                    "-c",
                    'export PATH="$PWD/bin:$PATH"\n'
                    'export FAKE_PROJ_DIR="$PWD/proj"\n'
                    'export PROJECT_DIR="$PWD/proj"\n'
                    'export BACKUP_LOCAL="$PWD/out"\n'
                    'export BACKUP_LOG="$PWD/logs/backup.log"\n'
                    'export BACKUP_AGE_RECIPIENT="age1testrecipient000000000000000"\n'
                    'export BACKUP_REMOTE="$PWD/remote"\n'
                    'export BACKUP_OFFSITE=true\n'
                    'export BACKUP_STAMP=20261117_0231\n'
                    f'bash "{BACKUP_SCRIPT.as_posix()}"',
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertNotEqual(res.returncode, 0)
            log_texto = (tmp_path / "logs" / "backup.log").read_text(encoding="utf-8")
            self.assertIn("CRITICAL: BACKUP_FAILED: checksum_mismatch", log_texto)

    def test_retencao_local_mantem_apenas_sete_diarios(self):
        bash = _encontrar_bash()
        if not bash:
            self.skipTest("Bash compatível indisponível")

        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run(
                [
                    bash,
                    "-c",
                    'set -euo pipefail\n'
                    'mkdir -p backups\n'
                    'for i in 0 1 2 3 4 5 6 7 8 9 10; do\n'
                    '  d=$(date -d "$i days ago" +%F)\n'
                    '  touch -d "$i days ago" "backups/db-$d.dump"\n'
                    'done\n'
                    f'bash "{RETENTION_SCRIPT.as_posix()}" "$PWD/backups"\n'
                    'count=$(ls backups/db-*.dump | wc -l)\n'
                    '[ "$count" -le 8 ]',
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
