"""Testes de 2FA TOTP (RFC 6238) e códigos de backup para perfis internos."""

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import Usuario
from core.models import LogAuditoria


class TwoFactorAuthTests(TestCase):
    """2FA TOTP para perfis internos."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_groups", verbosity=0)

    def _criar_usuario(self, username: str, grupo: str) -> Usuario:
        usuario = Usuario.objects.create_user(
            username=username, password="senha-forte-123"
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        return usuario

    def test_admin_sem_2fa_nao_acessa_areas_internas(self):
        """Admin sem 2FA configurado é direcionado para /accounts/2fa/setup/."""
        self._criar_usuario("admin_sem_2fa", "Administrador")
        resp_login = self.client.post(
            "/accounts/login/",
            {"username": "admin_sem_2fa", "password": "senha-forte-123"},
        )
        self.assertEqual(resp_login.status_code, 302)
        self.assertIn("/accounts/2fa/setup/", resp_login.url)

        response = self.client.get("/gestao/pedidos/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/2fa/setup/", response.url)

    def test_gestor_emissor_e_financeiro_exigem_2fa(self):
        """Gestor, Emissor Fiscal e Financeiro também exigem 2FA."""
        for idx, grupo in enumerate(("Gestor", "Emissor Fiscal", "Financeiro")):
            username = f"interno_{idx}"
            self._criar_usuario(username, grupo)
            with self.subTest(grupo=grupo):
                self.client.logout()
                resp = self.client.post(
                    "/accounts/login/",
                    {"username": username, "password": "senha-forte-123"},
                )
                self.assertEqual(resp.status_code, 302)
                self.assertIn("/accounts/2fa/setup/", resp.url)

    def test_admin_com_2fa_login_completo(self):
        """Admin com 2FA configurado faz login completo com token TOTP."""
        admin = self._criar_usuario("admin_com_2fa", "Administrador")
        device = TOTPDevice.objects.create(user=admin, confirmed=True)

        response = self.client.post(
            "/accounts/login/",
            {"username": "admin_com_2fa", "password": "senha-forte-123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/2fa/verify/", response.url)

        # Sem verificar token, rota interna continua bloqueada
        bloqueado = self.client.get("/gestao/pedidos/")
        self.assertEqual(bloqueado.status_code, 302)
        self.assertIn("/accounts/2fa/verify/", bloqueado.url)

        totp = TOTP(
            device.bin_key,
            device.step,
            device.t0,
            device.digits,
            device.drift,
        )
        code = f"{totp.token():06d}"
        response = self.client.post("/accounts/2fa/verify/", {"otp_token": code})
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/gestao/pedidos/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/accounts/2fa/setup/")

    def test_vendedor_nao_exige_2fa(self):
        """Vendedor não precisa de 2FA (escopo futuro)."""
        self._criar_usuario("vendedor_2fa", "Vendedor")
        resp = self.client.post(
            "/accounts/login/",
            {"username": "vendedor_2fa", "password": "senha-forte-123"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/accounts/2fa/", resp.url)

        response = self.client.get("/gestao/pedidos/")
        self.assertEqual(response.status_code, 200)

    def test_codigo_2fa_invalido_rejeitado(self):
        """Código TOTP inválido não permite concluir o login."""
        admin = self._criar_usuario("admin_token_invalido", "Administrador")
        TOTPDevice.objects.create(user=admin, confirmed=True)

        self.client.post(
            "/accounts/login/",
            {"username": "admin_token_invalido", "password": "senha-forte-123"},
        )
        response = self.client.post(
            "/accounts/2fa/verify/", {"otp_token": "000000"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "código inválido")
        self.assertEqual(self.client.get("/gestao/pedidos/").status_code, 302)

    def test_setup_qr_code_confirma_totp_e_gera_10_backup_codes(self):
        """Setup exibe QR code SVG, confirma TOTP e gera 10 códigos de backup."""
        admin = self._criar_usuario("admin_setup", "Administrador")
        self.client.post(
            "/accounts/login/",
            {"username": "admin_setup", "password": "senha-forte-123"},
        )
        setup_get = self.client.get("/accounts/2fa/setup/")
        self.assertEqual(setup_get.status_code, 200)
        self.assertContains(setup_get, "data:image/svg+xml;base64,")

        device = TOTPDevice.objects.get(user=admin, confirmed=False)
        totp = TOTP(
            device.bin_key,
            device.step,
            device.t0,
            device.digits,
            device.drift,
        )
        setup_post = self.client.post(
            "/accounts/2fa/setup/", {"otp_token": f"{totp.token():06d}"}
        )
        self.assertEqual(setup_post.status_code, 200)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(len(setup_post.context["backup_codes"]), 10)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="accounts.2fa_ativado", objeto_id=str(admin.pk)
            ).exists()
        )
        self.assertEqual(self.client.get("/gestao/pedidos/").status_code, 200)

    def test_backup_codes_funcionam_e_sao_de_uso_unico(self):
        """Códigos de backup permitem login se TOTP falhar e são consumidos."""
        from accounts.services import gerar_backup_codes

        admin = self._criar_usuario("admin_backup", "Administrador")
        TOTPDevice.objects.create(user=admin, confirmed=True)
        backup_codes = gerar_backup_codes(admin)
        self.assertEqual(len(backup_codes), 10)

        self.client.post(
            "/accounts/login/",
            {"username": "admin_backup", "password": "senha-forte-123"},
        )
        response = self.client.post(
            "/accounts/2fa/verify/",
            {"otp_token": backup_codes[0], "use_backup": "true"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/gestao/pedidos/").status_code, 200)

        # Reuso do mesmo código de backup deve ser rejeitado
        self.client.logout()
        self.client.post(
            "/accounts/login/",
            {"username": "admin_backup", "password": "senha-forte-123"},
        )
        reuso = self.client.post(
            "/accounts/2fa/verify/",
            {"otp_token": backup_codes[0], "use_backup": "true"},
        )
        self.assertEqual(reuso.status_code, 200)
        self.assertContains(reuso, "código inválido")

    def test_apenas_outro_admin_pode_resetar_2fa(self):
        """Apenas outro Administrador pode resetar 2FA; auto-reset e gestor falham."""
        from accounts.services import gerar_backup_codes, resetar_2fa_usuario

        admin1 = self._criar_usuario("admin_reset_1", "Administrador")
        admin2 = self._criar_usuario("admin_reset_2", "Administrador")
        gestor = self._criar_usuario("gestor_reset", "Gestor")
        TOTPDevice.objects.create(user=admin2, confirmed=True)
        gerar_backup_codes(admin2)

        with self.assertRaises(PermissionDenied):
            resetar_2fa_usuario(admin2, ator=gestor, justificativa="teste")
        with self.assertRaises(ValidationError):
            resetar_2fa_usuario(admin2, ator=admin2, justificativa="auto-reset")

        resetar_2fa_usuario(
            admin2, ator=admin1, justificativa="Perda do aparelho autenticador"
        )
        self.assertFalse(TOTPDevice.objects.filter(user=admin2).exists())
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="accounts.2fa_resetado", objeto_id=str(admin2.pk)
            ).exists()
        )
