"""Reconstrói obrigações de estoque por evidência (dry-run por padrão)."""

from django.core.management.base import BaseCommand

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

    def handle(self, *args, **options):
        obrigacoes = ObrigacaoEstoquePedido.objects.select_related(
            "pedido", "produto", "unidade"
        )
        if options.get("pedido"):
            obrigacoes = obrigacoes.filter(pedido__numero=options["pedido"])
        if options.get("produto"):
            obrigacoes = obrigacoes.filter(produto_id=options["produto"])

        total = alteradas = 0
        for obrigacao in obrigacoes.iterator():
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
            if options["aplicar"] and mudou:
                for campo, valor in dados.items():
                    setattr(obrigacao, campo, valor)
                if dados["status"] == "pendente":
                    obrigacao.resolvido_em = None
                    obrigacao.resolvido_por = None
                obrigacao.save()
                alteradas += 1
            if mudou or not options["aplicar"]:
                self.stdout.write(
                    f"{obrigacao.pedido.numero} {obrigacao.produto.nome} "
                    f"{obrigacao.unidade.nome}: "
                    f"due={obrigacao.quantidade_devida} "
                    f"baixada={dados['quantidade_baixada']} "
                    f"evidencia={dados['evidencia_baixada']} "
                    f"status={dados['status']} "
                    f"{'(aplicado)' if options['aplicar'] else '(dry-run)'}"
                )
        self.stdout.write(
            f"total={total} alteradas={alteradas} "
            f"modo={'aplicar' if options['aplicar'] else 'dry-run'}"
        )
