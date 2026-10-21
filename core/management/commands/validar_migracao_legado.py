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
        if not Movimento.objects.filter(
            produto_id=produto.pk,
            unidade_id=unidade.pk,
            motivo="Transferência legada ambígua",
        ).exists():
            Movimento.objects.create(
                produto_id=produto.pk,
                unidade_id=unidade.pk,
                tipo="transferencia",
                quantidade="1.00",
                motivo="Transferência legada ambígua",
            )

        produto_quarentena, _ = Produto.objects.get_or_create(
            nome="Feno Quarentena 2B",
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
        Estoque.objects.get_or_create(
            produto_id=produto_quarentena.pk,
            unidade_id=unidade.pk,
            defaults={
                "quantidade": "5.00",
                "quantidade_minima": "0.00",
                "quantidade_bloqueada": "3.00",
            },
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
        from stock.models import (
            BloqueioLegado,
            Estoque,
            MovimentoEstoque,
            ReconciliacaoEstoqueLegado,
            ReservaEstoque,
        )

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

        for nome in ("Feno Migração 2B", "Feno Quarentena 2B"):
            estoque = Estoque.objects.filter(produto__nome=nome).first()
            if estoque is None:
                falhas.append(f"estoque {nome} não encontrado")
                continue
            total_ledger = MovimentoEstoque.objects.filter(
                produto=estoque.produto, unidade=estoque.unidade
            ).aggregate(total=Sum("delta"))["total"]
            if total_ledger != estoque.quantidade:
                falhas.append(
                    f"{nome}: ledger divergente: "
                    f"SUM(delta)={total_ledger}, saldo={estoque.quantidade}"
                )
            ativas = ReservaEstoque.objects.filter(
                produto=estoque.produto,
                unidade=estoque.unidade,
                status=ReservaEstoque.Status.ATIVA,
            ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
            quarentena = BloqueioLegado.objects.filter(
                produto=estoque.produto,
                unidade=estoque.unidade,
                resolvido_em__isnull=True,
            ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0.00")
            if ativas + quarentena != estoque.quantidade_bloqueada:
                falhas.append(
                    f"{nome}: bloqueio divergente: "
                    f"ativas={ativas} + quarentena={quarentena} != "
                    f"bloqueada={estoque.quantidade_bloqueada}"
                )
            if nome == "Feno Migração 2B" and quarentena != Decimal("0.00"):
                falhas.append("bloqueio identificado foi parar na quarentena")
            if nome == "Feno Quarentena 2B" and quarentena != Decimal("3.00"):
                falhas.append(
                    "bloqueio sem dono não foi colocado em quarentena"
                )

        reserva = ReservaEstoque.objects.filter(
            pedido__numero="PF900008",
            status=ReservaEstoque.Status.ATIVA,
        ).first()
        if reserva is None or reserva.quantidade != Decimal("2.00"):
            falhas.append(
                "reserva parcial do pedido PF900008 não foi alocada"
            )

        from sales.models import ObrigacaoEstoquePedido

        obrigacao = ObrigacaoEstoquePedido.objects.filter(
            pedido__numero="PF900008",
            produto__nome="Feno Migração 2B",
        ).first()
        if (
            obrigacao is None
            or obrigacao.quantidade_devida != Decimal("10.00")
            or obrigacao.quantidade_baixada != Decimal("0.00")
            or obrigacao.status != ObrigacaoEstoquePedido.Status.PENDENTE
        ):
            falhas.append(
                "obrigação de estoque do pedido PF900008 não foi criada "
                "como pendente"
            )

        tipos = set(
            ReconciliacaoEstoqueLegado.objects.values_list("tipo", flat=True)
        )
        for tipo in (
            "ajuste_sem_prova",
            "transferencia_ambigua",
            "baseline",
            "reserva_parcial",
            "bloqueio_quarentena",
        ):
            if tipo not in tipos:
                falhas.append(f"evidência ausente: {tipo}")

        if MovimentoEstoque.objects.filter(delta__isnull=True).exists():
            falhas.append("existem movimentos com delta nulo após a migração")
        if MovimentoEstoque.objects.filter(delta=0).exists():
            falhas.append("existem movimentos com delta zero após a migração")

        if falhas:
            raise CommandError("; ".join(falhas))
        self.stdout.write(
            self.style.SUCCESS(
                f"Migração validada para {len(CASOS)} cenários, ledger, "
                "reservas, quarentena e evidências."
            )
        )
