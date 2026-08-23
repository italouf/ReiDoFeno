import logging

from django.test import TestCase

from core.logging_filters import SanitizePIIFilter


class HeadersSegurancaTests(TestCase):
    def test_csp_presente_nas_respostas(self):
        resposta = self.client.get("/healthz/")
        self.assertIn(
            "Content-Security-Policy", resposta.headers
        )
        self.assertIn("frame-ancestors 'none'",
                      resposta.headers["Content-Security-Policy"])

    def test_configuracoes_de_producao_harden(self):
        from django.conf import settings

        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        # Flags de produção (validadas em staging no deploy):
        self.assertIn(
            "django.middleware.security.SecurityMiddleware",
            settings.MIDDLEWARE,
        )


class SanitizePIIFilterTests(TestCase):
    def test_mascara_cpf_e_cnpj_em_mensagens(self):
        filtro = SanitizePIIFilter()
        record = logging.LogRecord(
            name="teste", level=logging.INFO, pathname=__file__,
            lineno=1, msg="Cliente 52998224725 e CNPJ 11222333000181 ok",
            args=(), exc_info=None,
        )
        self.assertTrue(filtro.filter(record))
        self.assertNotIn("52998224725", record.msg)
        self.assertIn("[DOC-REMOVIDO]", record.msg)

    def test_preserva_textos_normais(self):
        filtro = SanitizePIIFilter()
        record = logging.LogRecord(
            name="teste", level=logging.INFO, pathname=__file__,
            lineno=1, msg="Pedido PF000001 pago",
            args=(), exc_info=None,
        )
        filtro.filter(record)
        self.assertEqual(record.msg, "Pedido PF000001 pago")

    def test_args_posicionais_tambem_sao_mascarados(self):
        filtro = SanitizePIIFilter()
        record = logging.LogRecord(
            name="teste", level=logging.INFO, pathname=__file__,
            lineno=1, msg="Doc: %s", args=("52998224725",),
            exc_info=None,
        )
        filtro.filter(record)
        self.assertEqual(record.args[0], "[DOC-REMOVIDO]")
