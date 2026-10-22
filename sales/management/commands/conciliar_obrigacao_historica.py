"""Conciliação explícita de ambiguidade/excesso histórico (por obrigação)."""

from django.core.management.base import BaseCommand, CommandError
from django.shortcuts import get_object_or_404

from accounts.models import Usuario
from sales.models import ObrigacaoEstoquePedido
from sales.services import conciliar_obrigacao_historica


class Command(BaseCommand):
    help = (
        "Atribui, descarta ou aceita excesso de evidência de uma obrigação "
        "pendente. Sem --confirmar apenas descreve a operação."
    )

    def add_arguments(self, parser):
        parser.add_argument("obrigacao", type=int)
        parser.add_argument(
            "--decisao",
            required=True,
            choices=("atribuir", "descartar", "aceitar_excesso"),
        )
        parser.add_argument("--movimento", type=int)
        parser.add_argument("--usuario", required=True, help="username")
        parser.add_argument("--justificativa", required=True)
        parser.add_argument("--confirmar", action="store_true")

    def handle(self, *args, **options):
        obrigacao = get_object_or_404(
            ObrigacaoEstoquePedido, pk=options["obrigacao"]
        )
        try:
            usuario = Usuario.objects.get(username=options["usuario"])
        except Usuario.DoesNotExist as erro:
            raise CommandError("Usuário não encontrado.") from erro
        if not options["confirmar"]:
            self.stdout.write(
                f"dry-run: obrigação={obrigacao.pk} "
                f"tipo={obrigacao.tipo_pendencia} "
                f"decisao={options['decisao']}; use --confirmar para aplicar."
            )
            return
        resultado = conciliar_obrigacao_historica(
            obrigacao,
            decisao=options["decisao"],
            movimento_id=options["movimento"],
            usuario=usuario,
            justificativa=options["justificativa"],
        )
        self.stdout.write(
            f"obrigação={resultado.pk} status={resultado.status} "
            f"tipo={resultado.tipo_pendencia} "
            f"baixada={resultado.quantidade_baixada} "
            f"evidencia={resultado.evidencia_baixada}"
        )
