"""Contratos estáticos da infraestrutura (rodam sem Docker).

A validação autoritativa de build sobe no job ``docker`` do CI; estes testes
protegem invariantes que não podem regredir silenciosamente no repositório.
"""
import re
from pathlib import Path

import yaml
from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]
DOCKERFILE = RAIZ / "infra" / "Dockerfile"
ENTRYPOINT = RAIZ / "infra" / "scripts" / "entrypoint.sh"
CRON_ENTRYPOINT = RAIZ / "infra" / "scripts" / "cron-entrypoint.sh"
DOCKERIGNORE = RAIZ / ".dockerignore"


class DockerfileTests(SimpleTestCase):
    def setUp(self):
        self.texto = DOCKERFILE.read_text(encoding="utf-8")

    def test_multistage_com_builder_e_runtime(self):
        self.assertIn("AS builder", self.texto)
        self.assertIn("AS runtime", self.texto)
        self.assertIn("FROM builder AS dev", self.texto)

    def test_runtime_nao_roda_como_root(self):
        runtime = self.texto.split("AS runtime", 1)[1]
        self.assertIn("USER 1000:1000", runtime)
        self.assertNotIn("USER root", self.texto)

    def test_collectstatic_acontece_no_build(self):
        builder = self.texto.split("AS builder", 1)[1]
        self.assertIn("config.settings.build", builder)
        self.assertIn("collectstatic", builder)

    def test_healthcheck_usa_proxy_protocol(self):
        self.assertIn("HEALTHCHECK", self.texto)
        self.assertIn("--haproxy-protocol", self.texto)
        self.assertIn("/healthz/", self.texto)

    def test_gunicorn_preserva_ip_real(self):
        self.assertIn("--proxy-protocol=v1", self.texto)
        self.assertIn("--proxy-allow-from=*", self.texto)
        self.assertIn("gunicorn", self.texto)

    def test_supercronic_tem_checksum(self):
        self.assertIn("sha256sum -c -", self.texto)
        self.assertIn("supercronic-linux-", self.texto)

    def test_dockerfile_nao_contem_segredos(self):
        proibidos = ("DJANGO_SECRET_KEY=", "DB_PASSWORD=", "MERCADO_PAGO_ACCESS_TOKEN=")
        for proibido in proibidos:
            self.assertNotIn(proibido, self.texto)


class EntrypointTests(SimpleTestCase):
    def test_scripts_usam_lf(self):
        for caminho in (ENTRYPOINT, CRON_ENTRYPOINT):
            self.assertNotIn(b"\r\n", caminho.read_bytes(), caminho)

    def test_entrypoint_espera_banco_e_faz_exec(self):
        texto = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("DATABASE_URL", texto)
        self.assertIn("psycopg.connect", texto)
        self.assertIn('exec "$@"', texto)

    def test_migrations_sao_opt_out(self):
        texto = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn('RUN_MIGRATIONS:-true', texto)
        self.assertIn("migrate --noinput", texto)


class DockerignoreTests(SimpleTestCase):
    def test_segredos_e_artefatos_locais_ficam_fora_do_contexto(self):
        linhas = {
            linha.strip()
            for linha in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if linha.strip() and not linha.startswith("#")
        }
        for padrao in (".env", ".env.*", ".venv", "db.sqlite3", "media", "staticfiles"):
            self.assertIn(padrao, linhas)
        # Nenhuma negação pode re-incluir segredos no contexto de build.
        self.assertNotIn("!infra/**", linhas)
        self.assertNotIn("!.env", linhas)


class ComposeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.compose = (RAIZ / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
        cls.override = (
            RAIZ / "infra" / "docker-compose.override.yml"
        ).read_text(encoding="utf-8")

    def _bloco(self, nome, texto=None):
        texto = texto or self.compose
        padrao = (
            rf"\n  {re.escape(nome)}:\n(.*?)"
            r"(?=\n  [a-z0-9-]+:\n|\nvolumes:\n|\nnetworks:\n|\Z)"
        )
        encontrado = re.search(padrao, texto, re.DOTALL)
        self.assertIsNotNone(encontrado, nome)
        return encontrado.group(1)

    def test_servicos_obrigatorios(self):
        for servico in ("caddy", "web", "db", "redis", "cron"):
            self.assertIn(f"\n  {servico}:\n", self.compose)

    def test_banco_e_cache_nao_publicam_portas(self):
        for servico in ("db", "redis"):
            self.assertNotIn("ports:", self._bloco(servico))

    def test_rede_back_e_interna(self):
        self.assertIn("internal: true", self.compose)

    def test_todos_os_servicos_de_longa_duracao_tem_healthcheck(self):
        for servico in ("caddy", "web", "db", "redis", "cron"):
            self.assertIn("healthcheck:", self._bloco(servico))

    def test_web_roda_migrations_e_cron_nao(self):
        self.assertIn('RUN_MIGRATIONS: "true"', self._bloco("web"))
        self.assertIn('RUN_MIGRATIONS: "false"', self._bloco("cron"))

    def test_override_usa_stage_dev_e_hot_reload(self):
        self.assertIn("target: dev", self.override)
        self.assertIn("config.settings.development", self.override)
        self.assertIn("..:/app", self.override)
        self.assertIn(
            "${DOCKER_DEV_BIND:-127.0.0.1}:8000:8000", self.override
        )
        self.assertNotIn('"0.0.0.0:8000:8000"', self.override)

    def test_segredos_vem_de_variaveis(self):
        self.assertIn("${DB_PASSWORD:-reidofeno}", self.compose)
        self.assertNotIn("senha_segura", self.compose)
        self.assertNotIn("DJANGO_SECRET_KEY: ", self.compose)

    def test_smoke_override_limita_diagnostico_ao_web(self):
        smoke = (
            RAIZ / "infra" / "docker-compose.smoke.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("SMOKE_DIAGNOSTICS", smoke)
        self.assertNotIn("SENTRY_DSN", smoke)

    def test_smoke_tem_projeto_e_ambiente_proprios(self):
        smoke = yaml.safe_load(
            (RAIZ / "infra" / "docker-compose.smoke.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(smoke["name"], "reidofeno_smoke")
        env_smoke = (
            RAIZ / "infra" / ".env.smoke.example"
        ).read_text(encoding="utf-8")
        self.assertIn("APP_ENV_FILE=.env.docker.smoke", env_smoke)
        self.assertIn("DB_PASSWORD=smoke-only", env_smoke)
        self.assertIn("CADDY_HTTP_PORT=8080", env_smoke)
        self.assertIn("CADDY_HTTPS_PORT=8443", env_smoke)
        env_django = (
            RAIZ / ".env.docker.smoke.example"
        ).read_text(encoding="utf-8")
        self.assertIn("DJANGO_ENVIRONMENT=staging", env_django)
        self.assertIn("MERCADO_PAGO_FAKE=True", env_django)
        self.assertIn("BLING_FAKE=True", env_django)

    def test_base_permite_env_e_portas_do_smoke(self):
        self.assertIn(
            "../${APP_ENV_FILE:-.env.docker}", self.compose
        )
        self.assertIn(
            "${CADDY_HTTP_PORT:-80}:80", self.compose
        )
        self.assertIn(
            "${CADDY_HTTPS_PORT:-443}:443", self.compose
        )

    def test_scripts_de_smoke_nao_reutilizam_projeto_ou_rede_de_dev(self):
        script = (
            RAIZ / "infra" / "scripts" / "smoke-stack.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--project-name", script)
        self.assertIn("reidofeno_smoke", script)
        self.assertIn("--verbosity 0", script)
        self.assertNotIn("reidofeno_front", script)
        self.assertIn('case "$PROJETO_SMOKE" in', script)
        self.assertIn("reidofeno|", script)
        self.assertIn("nome_rede_front", script)


class CaddyTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.caddy = (RAIZ / "infra" / "Caddyfile").read_text(encoding="utf-8")
        cls.transport = (
            RAIZ / "infra" / "transport.caddy"
        ).read_text(encoding="utf-8")

    def test_proxy_protocol_preserva_ip_real(self):
        self.assertIn("reverse_proxy web:8000", self.caddy)
        self.assertIn("import transport.caddy", self.caddy)
        self.assertIn("proxy_protocol v1", self.transport)

    def test_dev_nao_usa_proxy_protocol(self):
        dev = (
            RAIZ / "infra" / "transport-dev.caddy"
        ).read_text(encoding="utf-8")
        self.assertNotIn("proxy_protocol", dev)

    def test_media_servida_diretamente(self):
        self.assertIn("handle_path /media/*", self.caddy)
        self.assertIn("/srv/media", self.caddy)

    def test_headers_de_seguranca(self):
        for header in (
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
            "-Server",
        ):
            self.assertIn(header, self.caddy)

    def test_dominios_sao_parametrizados(self):
        self.assertIn("{$APP_DOMAIN:localhost}", self.caddy)
        self.assertIn("{$STAGING_DOMAIN:staging.localhost}", self.caddy)
        self.assertIn("{$ACME_EMAIL:", self.caddy)

    def test_logs_em_json_no_stdout(self):
        self.assertIn("output stdout", self.caddy)
        self.assertIn("format json", self.caddy)

    def test_sem_tls_internal_global(self):
        # tls internal forçado impediria ACME em produção.
        self.assertNotIn("tls internal", self.caddy)


class WorkflowCaddyTests(SimpleTestCase):
    def test_mounts_do_caddy_resolvem_arquivos_reais(self):
        workflow = yaml.safe_load(
            (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        )
        passos = workflow["jobs"]["docker"]["steps"]
        passo = next(
            passo
            for passo in passos
            if passo.get("name") == "Validar Caddyfile (runtime e dev)"
        )
        run = passo["run"]
        self.assertIn("--mount", run)
        self.assertNotIn("-v ", run)
        fontes = re.findall(r"source=\$PWD/([^,\"]+)", run)
        self.assertTrue(fontes)
        for relativo in fontes:
            self.assertTrue((RAIZ / relativo).is_file(), relativo)
        self.assertIn("infra/transport.caddy", fontes)
        self.assertIn("infra/transport-dev.caddy", fontes)


class EnvExampleTests(SimpleTestCase):
    def test_exemplo_de_staging_e_explicito(self):
        texto = (RAIZ / ".env.docker.example").read_text(encoding="utf-8")
        self.assertIn("DJANGO_ENVIRONMENT=staging", texto)
        self.assertIn("DATABASE_SSL_REQUIRE=False", texto)
        self.assertIn("MERCADO_PAGO_FAKE=True", texto)
        self.assertIn("BLING_FAKE=True", texto)

    def test_env_do_compose_nao_versionado(self):
        gitignore = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env.docker", gitignore)
        self.assertIn("media/", gitignore)
