"""Remove notas fiscais após o prazo legal de retenção (ADR-012)."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import LogAuditoria
from fiscal.models import NotaFiscal


class Command(BaseCommand):
    help = "Remove notas fiscais cujo prazo de retenção expirou."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Informa quantas notas seriam removidas sem excluir.",
        )

    def handle(self, *args, **options):
        hoje = timezone.localdate()
        notas = (
            NotaFiscal.objects.filter(retido_ate__lt=hoje)
            .select_related("pedido")
            .order_by("pk")
        )
        total = notas.count()
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{total} nota(s) fiscal(is) expirada(s); dry-run sem "
                    "remoção."
                )
            )
            return

        removidas = 0
        agora = timezone.now().isoformat()
        with transaction.atomic():
            for nota in notas:
                dados = {
                    "pedido": nota.pedido.numero,
                    "numero": nota.numero,
                    "serie": nota.serie,
                    "chave_acesso": nota.chave_acesso,
                    "data_emissao": (
                        nota.data_emissao.isoformat()
                        if nota.data_emissao
                        else None
                    ),
                    "retido_ate": (
                        nota.retido_ate.isoformat()
                        if nota.retido_ate
                        else None
                    ),
                }
                nota_id = nota.pk
                nota.delete()
                LogAuditoria.objects.create(
                    usuario=None,
                    acao="fiscal.nota_retencao_expirada",
                    objeto_tipo="fiscal.NotaFiscal",
                    objeto_id=str(nota_id),
                    antes=dados,
                    depois={"excluida_em": agora},
                )
                removidas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{removidas} nota(s) fiscal(is) removida(s) após retenção."
            )
        )
