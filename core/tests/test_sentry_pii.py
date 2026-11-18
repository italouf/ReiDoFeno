"""Testes de filtragem de PII no Sentry e parâmetros seguros de inicialização."""
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings.base import configurar_sentry
from core.logging_filters import filter_pii_event


class SentryPIIFilterTests(SimpleTestCase):
    def test_filter_pii_event_mascara_cpf_cnpj_e_email(self):
        evento = {
            "message": "Falha para CPF 529.982.247-25 e email cliente@exemplo.com.br",
            "logentry": {"formatted": "CNPJ 11.222.333/0001-81 e alfa 00000000E08G12"},
            "exception": {
                "values": [
                    {
                        "type": "ValueError",
                        "value": "Documento 52998224725 inválido para user@dominio.com",
                    }
                ]
            },
            "breadcrumbs": {
                "values": [
                    {"message": "Post CNPJ 00.000.000/e08g-12"},
                ]
            },
            "request": {
                "data": {"documento": "52998224725", "email": "teste@reidofeno.com"},
                "query_string": "email=busca@teste.com",
            },
            "extra": {"detalhe": "Contato: financeiro@empresa.org"},
        }

        filtrado = filter_pii_event(evento, {})
        serializado = repr(filtrado)
        for sensivel in (
            "529.982.247-25",
            "52998224725",
            "11.222.333/0001-81",
            "00000000E08G12",
            "00.000.000/e08g-12",
            "cliente@exemplo.com.br",
            "user@dominio.com",
            "teste@reidofeno.com",
            "busca@teste.com",
            "financeiro@empresa.org",
        ):
            self.assertNotIn(sensivel, serializado)

    def test_filter_pii_event_preserva_texto_operacional(self):
        evento = {
            "message": "Pedido PF000042 com timeout no Redis",
            "extra": {"unidade": "Feira de Santana"},
        }

        filtrado = filter_pii_event(evento, {})
        self.assertEqual(filtrado["message"], "Pedido PF000042 com timeout no Redis")
        self.assertEqual(filtrado["extra"]["unidade"], "Feira de Santana")

    def test_configurar_sentry_parametros_seguros(self):
        with patch("sentry_sdk.init") as mock_init:
            iniciado = configurar_sentry(
                "https://public@example.ingest.sentry.io/1",
                environment="production",
                release="v1.0.0",
            )

        self.assertTrue(iniciado)
        mock_init.assert_called_once()
        kwargs = mock_init.call_args.kwargs
        self.assertFalse(kwargs["send_default_pii"])
        self.assertEqual(kwargs["traces_sample_rate"], 0.1)
        self.assertEqual(kwargs["profiles_sample_rate"], 0.1)
        self.assertIs(kwargs["before_send"], filter_pii_event)
        self.assertEqual(kwargs["environment"], "production")
        self.assertEqual(kwargs["release"], "v1.0.0")
        nomes_integracoes = {type(item).__name__ for item in kwargs["integrations"]}
        self.assertIn("DjangoIntegration", nomes_integracoes)
        self.assertIn("RedisIntegration", nomes_integracoes)

    def test_configurar_sentry_sem_dsn_nao_inicializa(self):
        with patch("sentry_sdk.init") as mock_init:
            iniciado = configurar_sentry("")

        self.assertFalse(iniciado)
        mock_init.assert_not_called()
