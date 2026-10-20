"""Cria/verifica fixtures da migração histórica 0001 → HEAD (CI PostgreSQL)."""

import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

CASOS = {
    "PF900001": ("pago", None, "pago"),
    "PF900002": ("aguardando_pagamento", "aprovado", "pago"),
    "PF900003": ("cancelado", None, "cancelado"),
    "PF900004": ("falhou", None, "cancelado"),
    "PF900005": ("aguardando_pagamento", "recusado", "cancelado"),
    "PF900006": ("em_separacao", None, "pago"),
    "PF900007": ("concluido", "recusado", "pago"),
}


class Command(BaseCommand):
    help = "Cria fixtures no schema 0001 ou verifica o resultado após migrar."

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument("--criar", action="store_true")
        grupo.add_argument("--verificar", action="store_true")

    def handle(self, *args, **options):
        if options["criar"]:
            self._criar()
        else:
            self._verificar()

    def _criar(self):
        executor = MigrationExecutor(connection)
        state = executor.loader.project_state(
            [("sales", "0001_initial"), ("stock", "0001_initial")]
        )
        apps = state.apps
        Cliente = apps.get_model("customers", "Cliente")
        Unidade = apps.get_model("core", "Unidade")
        Pedido = apps.get_model("sales", "Pedido")
        Pagamento = apps.get_model("sales", "Pagamento")
        ItemPedido = apps.get_model("sales", "ItemPedido")
        Categoria = apps.get_model("catalog", "Categoria")
        Produto = apps.get_model("catalog", "Produto")
        Estoque = apps.get_model("stock", "Estoque")
        Movimento = apps.get_model("stock", "MovimentoEstoque")

        cliente, _ = Cliente.objects.get_or_create(
            documento="52998224725",
            defaults={
                "nome": "Cliente Migração",
                "tipo_pessoa": "fisica",
                "categoria": "varejo",
            },
        )
        unidade, _ = Unidade.objects.get_or_create(
            nome="Unidade Migração",
            defaults={"cidade": "Feira de Santana", "tipo": "loja"},
        )
        for numero, (status, pagamento_status, _esperado) in CASOS.items():
            pedido, criado = Pedido.objects.get_or_create(
                numero=numero,
                defaults={
                    "token_acesso": uuid.uuid4(),
                    "cliente_id": cliente.pk,
                    "unidade_id": unidade.pk,
                    "canal": "loja",
                    "modalidade": "retirada",
                    "subtotal": "10.00",
                    "frete": "0.00",
                    "total": "10.00",
                    "status": status,
                },
            )
            if criado and pagamento_status:
                Pagamento.objects.create(
                    pedido_id=pedido.pk,
                    provedor="mercadopago",
                    status=pagamento_status,
                    valor="10.00",
                )

        categoria, _ = Categoria.objects.get_or_create(
            nome="Migração 2B", defaults={"ativa": True}
        )
        produto, _ = Produto.objects.get_or_create(
            nome="Feno Migração 2B",
            defaults={
                "categoria_id": categoria.pk,
                "ncm": "12149000",
                "unidade_medida": "fardo",
                "custo": "1.00",
                "preco_balcao": "2.00",
                "preco_online": "3.00",
                "ativo": True,
            },
        )
        _estoque, _ = Estoque.objects.get_or_create(
            produto_id=produto.pk,
            unidade_id=unidade.pk,
            defaults={
                "quantidade": "10.00",
                "quantidade_minima": "0.00",
                "quantidade_bloqueada": "2.00",
            },
        )
        if not Movimento.objects.filter(
            produto_id=produto.pk,
            unidade_id=unidade.pk,
            motivo="Movimento legado de entrada",
        ).exists():
            Movimento.objects.create(
                produto_id=produto.pk,
                unidade_id=unidade.pk,
                tipo="entrada",
                quantidade="5.00",
                motivo="Movimento legado de entrada",
            )
        if not Movimento.objects.filter(
            produto_id=produto.pk,
            unidade_id=unidade.pk,
            motivo="Ajuste legado sem auditoria",
        ).exists():
            Movimento.objects.create(
                produto_id=produto.pk,
                unidade_id=unidade.pk,
                tipo="ajuste",
                quantidade="1.00",
                motivo="Ajuste legado sem auditoria",
            )
        pedido_pendente, _ = Pedido.objects.get_or_create(
            numero="PF900008",
            defaults={
                "token_acesso": uuid.uuid4(),
                "cliente_id": cliente.pk,
                "unidade_id": unidade.pk,
                "canal": "loja",
                "modalidade": "retirada",
                "subtotal": "30.00",
                "frete": "0.00",
                "total": "30.00",
                "status": "aguardando_pagamento",
            },
        )
        if not ItemPedido.objects.filter(
            pedido_id=pedido_pendente.pk, produto_id=produto.pk
        ).exists():
            ItemPedido.objects.create(
                pedido_id=pedido_pendente.pk,
                produto_id=produto.pk,
                produto_nome="Feno Migração 2B",
                quantidade="10.00",
                preco_unitario="3.00",
            )
        self.stdout.write(
            self.style.SUCCESS("Fixtures históricas criadas no schema 0001.")
        )

    def _verificar(self):
        from django.db.models import Sum

        from sales.models import Pedido
        from stock.models import Estoque, MovimentoEstoque, ReservaEstoque

        encontrados = {
            pedido.numero: (pedido.status, pedido.status_financeiro)
            for pedido in Pedido.objects.filter(
                numero__in=CASOS.keys()
            )
        }
        falhas = []
        for numero, (_status, _pagamento, esperado) in CASOS.items():
            atual = encontrados.get(numero)
            if atual is None or atual[1] != esperado:
                falhas.append(
                    f"{numero}: esperado financeiro={esperado}, atual={atual}"
                )

        estoque = Estoque.objects.filter(
            produto__nome="Feno Migração 2B"
        ).first()
        if estoque is None:
            falhas.append("estoque da migração não encontrado")
        else:
            total_ledger = MovimentoEstoque.objects.filter(
                produto=estoque.produto, unidade=estoque.unidade
            ).aggregate(total=Sum("delta"))["total"]
            if total_ledger != estoque.quantidade:
                falhas.append(
                    "ledger divergente: "
                    f"SUM(delta)={total_ledger}, saldo={estoque.quantidade}"
                )
            ativas = ReservaEstoque.objects.filter(
                produto=estoque.produto,
                unidade=estoque.unidade,
                status=ReservaEstoque.Status.ATIVA,
            ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
            if ativas != estoque.quantidade_bloqueada:
                falhas.append(
                    "reservas divergentes: "
                    f"SUM(ativas)={ativas}, bloqueada={estoque.quantidade_bloqueada}"
                )
            reserva = ReservaEstoque.objects.filter(
                pedido__numero="PF900008",
                status=ReservaEstoque.Status.ATIVA,
            ).first()
            if reserva is None or reserva.quantidade != Decimal("2.00"):
                falhas.append(
                    "reserva parcial do pedido PF900008 não foi alocada"
                )
        if MovimentoEstoque.objects.filter(delta__isnull=True).exists():
            falhas.append("existem movimentos com delta nulo após a migração")

        if falhas:
            raise CommandError("; ".join(falhas))
        self.stdout.write(
            self.style.SUCCESS(
                f"Migração validada para {len(CASOS)} cenários, ledger e reservas."
            )
        )
