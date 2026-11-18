"""Testes de notificação crítica para falhas de backup."""

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase


class BackupNotificationTests(SimpleTestCase):
    """Notificações de falha de backup."""

    def test_backup_falha_loga_critico(self):
        """Falha de backup gera log crítico visível no Sentry."""
        from core.backup import notificar_falha_backup

        with self.assertLogs("reidofeno.backup", level="CRITICAL") as cm:
            notificar_falha_backup(reason="rclone_failed")
        self.assertTrue(any("BACKUP_FAILED" in msg for msg in cm.output))
        self.assertTrue(any("rclone_failed" in msg for msg in cm.output))

    def test_comando_reportar_backup_falha_loga_critico(self):
        """Management command reportar_backup_falha emite log CRITICAL."""
        out = StringIO()
        with self.assertLogs("reidofeno.backup", level="CRITICAL") as cm:
            call_command(
                "reportar_backup_falha",
                motivo="checksum_mismatch",
                stdout=out,
            )
        self.assertTrue(any("BACKUP_FAILED" in msg for msg in cm.output))
        self.assertIn("BACKUP_FAILED", out.getvalue())
