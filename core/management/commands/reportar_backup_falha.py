"""Comando para registrar falha de backup via logger crítico (visível no Sentry)."""

from django.core.management.base import BaseCommand

from core.backup import notificar_falha_backup


class Command(BaseCommand):
    help = "Emite log CRITICAL BACKUP_FAILED para observabilidade."

    def add_arguments(self, parser):
        parser.add_argument(
            "--motivo",
            default="unknown",
            help="Identificador curto da causa da falha de backup.",
        )
        parser.add_argument(
            "--detalhe",
            default="",
            help="Contexto adicional não sensível sobre a falha.",
        )

    def handle(self, *args, **options):
        mensagem = notificar_falha_backup(
            reason=options["motivo"],
            detail=options["detalhe"],
        )
        self.stdout.write(mensagem)
