"""Regressões de propriedade/cleanup do harness sentinela (F3-06).

Executam o Bash real com um `docker` simulado. Nenhum recurso Docker real é
criado ou removido; o teste é seguro mesmo com o daemon indisponível.
"""
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "infra" / "scripts" / "test-smoke-isolation.sh"


def _bash():
    encontrado = shutil.which("bash")
    if encontrado:
        return encontrado
    candidato = Path(r"C:\Program Files\Git\bin\bash.exe")
    return str(candidato) if candidato.is_file() else None


BASH = _bash()


@unittest.skipUnless(BASH, "bash não disponível para as regressões do harness")
class SmokeIsolationOwnershipTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "docker.log"
        self.env_smoke = self.tmp / "env.smoke"
        self.env_docker = self.tmp / "env.docker.smoke"
        self.env_smoke.write_text("DB_PASSWORD=smoke-only\n", encoding="utf-8")
        self.env_docker.write_text(
            "DJANGO_ENVIRONMENT=staging\n", encoding="utf-8"
        )
        self.lock = self.tmp / "isolation.lock"
        self._criar_docker_simulado()

    def _criar_docker_simulado(self):
        script = self.bin / "docker"
        script.write_text(
            """#!/usr/bin/env sh
printf '%s\\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$1" in
  volume)
    case "$2" in
      inspect) [ "${FAKE_VOLUME_EXISTS:-0}" = "1" ] && exit 0 || exit 1 ;;
      ls) [ "${FAKE_PROJECT_BUSY:-0}" = "1" ] && echo volume-id; exit 0 ;;
      create) exit "${FAKE_VOLUME_CREATE_EXIT:-0}" ;;
      rm) exit 0 ;;
    esac
    ;;
  container)
    case "$2" in
      inspect) [ "${FAKE_CONTAINER_EXISTS:-0}" = "1" ] && exit 0 || exit 1 ;;
    esac
    ;;
  ps) [ "${FAKE_PROJECT_BUSY:-0}" = "1" ] && echo container-id; exit 0 ;;
  run) exit "${FAKE_RUN_EXIT:-0}" ;;
  exec) echo sentinel; exit 0 ;;
  inspect) echo true; exit 0 ;;
  rm) exit 0 ;;
  compose)
    case "$*" in
      *" config"*)
        if [ "${FAKE_BLOCK_CONFIG:-0}" = "1" ] && [ ! -f "$FAKE_CONFIG_BLOCKED" ]; then
          : > "$FAKE_CONFIG_BLOCKED"
          : > "$FAKE_READY"
          while [ ! -f "$FAKE_RELEASE" ]; do sleep 0.05; done
        fi
        ;;
      *" down "*)
        if [ "${FAKE_REQUIRE_LOCK_AT_DOWN:-0}" = "1" ]; then
          [ -f "${SMOKE_LOCK_DIR:-}/owner" ] || \
            printf '%s\\n' "MISSING_LOCK" >> "$FAKE_DOCKER_LOG"
        fi
        ;;
    esac
    exit 0
    ;;
esac
exit 0
""",
            encoding="utf-8",
            newline="\n",
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

    def _ambiente(self, *, comando=None, usar_hook=True, **fake_env):
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}{os.pathsep}{env.get('PATH', '')}"
        env.update(
            {
                "IMAGE_TAG": "test",
                "FAKE_DOCKER_LOG": self.log.as_posix(),
                "SMOKE_ISOLATION_ENV_SMOKE": self.env_smoke.as_posix(),
                "SMOKE_ISOLATION_ENV_DOCKER": self.env_docker.as_posix(),
                "SMOKE_ISOLATION_LOCK_DIR": self.lock.as_posix(),
                "SMOKE_LOCK_DIR": self.lock.as_posix(),
            }
        )
        if usar_hook:
            env["SMOKE_ISOLATION_COMMAND"] = comando or (
                'if [ "${SMOKE_PROJECT_NAME:-}" = "reidofeno" ]; '
                "then exit 1; fi; "
                'if [ "${SMOKE_TEST_FAIL_AFTER_SEED:-0}" = "1" ]; '
                "then exit 1; fi; exit 0"
            )
        env.update({chave: str(valor) for chave, valor in fake_env.items()})
        return env

    def _executar(self, *, comando=None, **fake_env):
        return subprocess.run(
            [BASH, str(SCRIPT)],
            cwd=RAIZ,
            env=self._ambiente(comando=comando, **fake_env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )

    def _chamadas(self):
        if not self.log.exists():
            return ""
        return self.log.read_text(encoding="utf-8", errors="replace")

    def _assert_sem_destrutivo(self):
        chamadas = self._chamadas()
        self.assertNotIn("volume rm", chamadas)
        self.assertNotIn("rm -f", chamadas)
        self.assertNotIn(" down ", f" {chamadas} ")

    def test_volume_sentinela_preexistente_e_preservado(self):
        resultado = self._executar(FAKE_VOLUME_EXISTS="1")

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("volume sentinela já existe", resultado.stderr)
        self._assert_sem_destrutivo()
        self.assertIn("volume inspect", self._chamadas())

    def test_container_sentinela_preexistente_e_preservado(self):
        resultado = self._executar(FAKE_CONTAINER_EXISTS="1")

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("container sentinela já existe", resultado.stderr)
        self._assert_sem_destrutivo()

    def test_projeto_smoke_ocupado_e_preservado(self):
        resultado = self._executar(FAKE_PROJECT_BUSY="1")

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("já está ocupado", resultado.stderr)
        self._assert_sem_destrutivo()

    def test_execucao_concorrente_nao_executa_docker(self):
        self.lock.mkdir()

        resultado = self._executar()

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("outra execução de isolamento", resultado.stderr)
        self.assertFalse(self.log.exists())

    def test_falha_parcial_remove_apenas_volume_proprio(self):
        resultado = self._executar(FAKE_RUN_EXIT="1")

        self.assertNotEqual(resultado.returncode, 0)
        chamadas = self._chamadas()
        self.assertIn("volume rm reidofeno_sentinel_smoke_test_dados", chamadas)
        self.assertNotIn("rm -f", chamadas)
        self.assertNotIn(" down ", f" {chamadas} ")

    def test_lock_comum_do_smoke_ocupado_e_preservado(self):
        self.lock.mkdir()
        (self.lock / "owner").write_text("smoke-direto-externo", encoding="utf-8")

        resultado = self._executar()

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("outra execução de isolamento", resultado.stderr)
        self._assert_sem_destrutivo()
        self.assertEqual(
            (self.lock / "owner").read_text(encoding="utf-8"),
            "smoke-direto-externo",
        )

    def test_sucesso_limpa_somente_recursos_proprios(self):
        resultado = self._executar(FAKE_REQUIRE_LOCK_AT_DOWN="1")

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        chamadas = self._chamadas()
        self.assertIn("--project-name reidofeno_smoke", chamadas)
        self.assertIn(" down ", f" {chamadas} ")
        self.assertIn("rm -f reidofeno_sentinel_smoke_test", chamadas)
        self.assertIn("volume rm reidofeno_sentinel_smoke_test_dados", chamadas)
        self.assertNotIn("--project-name reidofeno ", chamadas)
        self.assertNotIn("MISSING_LOCK", chamadas)

    def test_falha_inesperada_preserva_exit_e_limpa_proprios(self):
        resultado = self._executar(comando="exit 7")

        self.assertEqual(resultado.returncode, 7)
        chamadas = self._chamadas()
        self.assertIn(" down ", f" {chamadas} ")
        self.assertIn("rm -f reidofeno_sentinel_smoke_test", chamadas)
        self.assertIn("volume rm reidofeno_sentinel_smoke_test_dados", chamadas)

    def test_falha_deliberada_preserva_exit_e_limpa_proprios(self):
        resultado = self._executar()

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        chamadas = self._chamadas()
        self.assertIn("SENTINELA_OK_APOS_FALHA", resultado.stdout)
        self.assertIn(" down ", f" {chamadas} ")
        self.assertIn("volume rm reidofeno_sentinel_smoke_test_dados", chamadas)

    def test_smoke_direto_ocupa_lock_e_harness_nao_derruba(self):
        """Dois scripts reais; sem hook substituindo o filho."""
        ready = self.tmp / "ready"
        blocked = self.tmp / "blocked"
        release = self.tmp / "release"
        env = self._ambiente(usar_hook=False)
        env.update(
            {
                "SMOKE_ENV_SMOKE": self.env_smoke.as_posix(),
                "SMOKE_ENV_DOCKER": self.env_docker.as_posix(),
                "FAKE_BLOCK_CONFIG": "1",
                "FAKE_CONFIG_BLOCKED": blocked.as_posix(),
                "FAKE_READY": ready.as_posix(),
                "FAKE_RELEASE": release.as_posix(),
            }
        )
        processo = subprocess.Popen(
            [BASH, "infra/scripts/smoke-stack.sh"],
            cwd=RAIZ,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            limite = time.monotonic() + 15
            while not ready.exists():
                if processo.poll() is not None:
                    self.fail("smoke direto terminou antes de adquirir a lock")
                if time.monotonic() > limite:
                    self.fail("smoke direto não sinalizou a lock a tempo")
                time.sleep(0.05)

            self.assertTrue((self.lock / "owner").is_file())
            dono = (self.lock / "owner").read_text(encoding="utf-8")

            resultado = subprocess.run(
                [BASH, str(SCRIPT)],
                cwd=RAIZ,
                env=self._ambiente(usar_hook=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )

            self.assertNotEqual(resultado.returncode, 0)
            self.assertIn("outra execução de isolamento", resultado.stderr)
            self.assertNotIn(" down ", f" {self._chamadas()} ")
            self.assertEqual(
                (self.lock / "owner").read_text(encoding="utf-8"), dono
            )
        finally:
            release.write_text("release", encoding="utf-8")
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=5)

        self.assertFalse(self.lock.exists())
