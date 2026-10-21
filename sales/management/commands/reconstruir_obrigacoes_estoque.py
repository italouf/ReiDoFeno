"""Reconstrói obrigações de estoque por evidência (dry-run por padrão)."""

from django.core.management.base import BaseCommand
from django.db import transaction

from sales.models import ObrigacaoEstoquePedido, Pedido
from sales.obrigacoes import reconstruir_obrigacao_evidencia
from stock.models import MovimentoEstoque


class Command(BaseCommand):
    help = (
        "Recalcula quantidade_baixada/evidência de ObrigacaoEstoquePedido "
        "a partir de movimentos atribuíveis. Use --aplicar para persistir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true")
        parser.add_argument("--pedido", help="Número do pedido (ex.: PF000001)")
        parser.add_argument("--produto", type=int, help="ID do produto")

    def _queryset(self, options):
        obrigacoes = ObrigacaoEstoquePedido.objects.all()
        if options.get("pedido"):
            obrigacoes = obrigacoes.filter(pedido__numero=options["pedido"])
        if options.get("produto"):
            obrigacoes = obrigacoes.filter(produto_id=options["produto"])
        return obrigacoes

    def _antes(self, obrigacao):
        return {
            "status": obrigacao.status,
            "tipo_pendencia": obrigacao.tipo_pendencia,
            "quantidade_baixada": str(obrigacao.quantidade_baixada),
            "evidencia_baixada": str(obrigacao.evidencia_baixada),
            "motivo_pendencia": obrigacao.motivo_pendencia,
        }

    def handle(self, *args, **options):
        obrigacoes = self._queryset(options)
        total = alteradas = 0
        if not options["aplicar"]:
            for obrigacao in obrigacoes.select_related(
                "pedido", "produto", "unidade"
            ).iterator():
                total += 1
                dados = reconstruir_obrigacao_evidencia(
                    obrigacao, Pedido=Pedido, Movimento=MovimentoEstoque
                )
                self._relatar(obrigacao, dados, aplicado=False)
            self.stdout.write(
                f"total={total} alteradas=0 modo=dry-run"
            )
            return

        ids = list(obrigacoes.values_list("pk", flat=True))
        for pk in ids:
            with transaction.atomic():
                try:
                    obrigacao = (
                        ObrigacaoEstoquePedido.objects.select_for_update()
                        .get(pk=pk)
                    )
                except ObrigacaoEstoquePedido.DoesNotExist:
                    continue
                total += 1
                dados = reconstruir_obrigacao_evidencia(
                    obrigacao, Pedido=Pedido, Movimento=MovimentoEstoque
                )
                mudou = any(
                    getattr(obrigacao, campo) != valor
                    for campo, valor in dados.items()
                )
                if dados["status"] == "pendente" and (
                    obrigacao.resolvido_em is not None
                    or obrigacao.resolvido_por_id is not None
                ):
                    mudou = True
                if not mudou:
                    continue
                antes = self._antes(obrigacao)
                for campo, valor in dados.items():
                    setattr(obrigacao, campo, valor)
                if dados["status"] == "pendente":
                    obrigacao.resolvido_em = None
                    obrigacao.resolvido_por = None
                obrigacao.save()
                alteradas += 1
                self._relatar(obrigacao, dados, aplicado=True, antes=antes)
                from core.auditoria import registrar_auditoria

                registrar_auditoria(
                    acao="obrigacao_estoque.reconstruida",
                    instancia=obrigacao.pedido,
                    usuario=None,
                    antes=antes,
                    depois={
                        "status": obrigacao.status,
                        "tipo_pendencia": obrigacao.tipo_pendencia,
                        "quantidade_baixada": str(
                            obrigacao.quantidade_baixada
                        ),
                        "evidencia_baixada": str(
                            obrigacao.evidencia_baixada
                        ),
                        "motivo_pendencia": obrigacao.motivo_pendencia,
                    },
                )
        self.stdout.write(
            f"total={total} alteradas={alteradas} modo=aplicar"
        )

    def _relatar(self, obrigacao, dados, *, aplicado, antes=None):
        prefixo = ""
        if antes is not None:
            prefixo = (
                f"antes=({antes['status']},{antes['tipo_pendencia']},"
                f"{antes['quantidade_baixada']}/{antes['evidencia_baixada']}) "
            )
        self.stdout.write(
            f"{prefixo}{obrigacao.pedido.numero} {obrigacao.produto.nome} "
            f"{obrigacao.unidade.nome}: "
            f"due={obrigacao.quantidade_devida} "
            f"baixada={dados['quantidade_baixada']} "
            f"evidencia={dados['evidencia_baixada']} "
            f"tipo={dados.get('tipo_pendencia', '')} "
            f"status={dados['status']} "
            f"{'(aplicado)' if aplicado else '(dry-run)'}"
        )
