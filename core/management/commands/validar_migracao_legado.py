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
    # T01-A: pagamento aprovado + baixa por saldo livre sem reserva.
    "PF900009": ("aguardando_pagamento", "aprovado", "pago"),
    # T01-B: pedido avançado no código antigo sem baixa física comprovada.
    # O financeiro pago é derivado do próprio status operacional pelo 0002.
    # U04: uma base povoada exatamente na 0001 com Pagamento aprovado adicional
    # não é suportada; ver docs/specs/fase-2b-remediation.md.
    "PF900010": ("em_separacao", None, "pago"),
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

        # T01: dois produtos com ledger coerente, mas com evidência de baixa
        # distinta. O primeiro teve saída física; o segundo só avançou de status.
        cenarios_t01 = (
            (
                "PF900009",
                "Feno T01 Evidência",
                "7.00",
                (
                    ("entrada", "10.00", "Entrada T01 A"),
                    (
                        "saida",
                        "3.00",
                        "Baixa definitiva por pedido PF900009",
                    ),
                ),
            ),
            (
                "PF900010",
                "Feno T01 Sem Evidência",
                "10.00",
                (("entrada", "10.00", "Entrada T01 B"),),
            ),
        )
        for numero, nome_produto, saldo, movimentos in cenarios_t01:
            produto_t01, _ = Produto.objects.get_or_create(
                nome=nome_produto,
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
                produto_id=produto_t01.pk,
                unidade_id=unidade.pk,
                defaults={
                    "quantidade": saldo,
                    "quantidade_minima": "0.00",
                    "quantidade_bloqueada": "0.00",
                },
            )
            for tipo, quantidade, motivo in movimentos:
                if not Movimento.objects.filter(
                    produto_id=produto_t01.pk,
                    unidade_id=unidade.pk,
                    motivo=motivo,
                ).exists():
                    Movimento.objects.create(
                        produto_id=produto_t01.pk,
                        unidade_id=unidade.pk,
                        tipo=tipo,
                        quantidade=quantidade,
                        motivo=motivo,
                    )
            pedido_t01 = Pedido.objects.get(numero=numero)
            ItemPedido.objects.get_or_create(
                pedido_id=pedido_t01.pk,
                produto_id=produto_t01.pk,
                defaults={
                    "produto_nome": nome_produto,
                    "quantidade": "3.00",
                    "preco_unitario": "3.00",
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

        # T01-A: a baixa histórica por saldo livre deve ser reconhecida sem
        # criar um segundo movimento; T01-B: status avançado sem movimento não
        # pode ser convertido em baixa.
        t01 = {
            "PF900009": (
                "Feno T01 Evidência",
                ObrigacaoEstoquePedido.Status.RESOLVIDA,
                Decimal("3.00"),
                Decimal("3.00"),
                "",
                2,
            ),
            "PF900010": (
                "Feno T01 Sem Evidência",
                ObrigacaoEstoquePedido.Status.PENDENTE,
                Decimal("0.00"),
                Decimal("0.00"),
                "falta",
                1,
            ),
        }
        for numero, (
            nome_produto,
            status_esperado,
            baixada_esperada,
            evidencia_esperada,
            tipo_esperado,
            movimentos_esperados,
        ) in t01.items():
            obrigacao_t01 = ObrigacaoEstoquePedido.objects.filter(
                pedido__numero=numero,
                produto__nome=nome_produto,
            ).first()
            if obrigacao_t01 is None:
                falhas.append(f"obrigação T01 ausente para {numero}")
                continue
            if (
                obrigacao_t01.quantidade_baixada != baixada_esperada
                or obrigacao_t01.evidencia_baixada != evidencia_esperada
                or obrigacao_t01.status != status_esperado
                or obrigacao_t01.tipo_pendencia != tipo_esperado
            ):
                falhas.append(
                    f"T01 {numero}: esperado status={status_esperado} "
                    f"baixada={baixada_esperada} evidência={evidencia_esperada} "
                    f"tipo={tipo_esperado}, atual status={obrigacao_t01.status} "
                    f"baixada={obrigacao_t01.quantidade_baixada} "
                    f"evidência={obrigacao_t01.evidencia_baixada} "
                    f"tipo={obrigacao_t01.tipo_pendencia}"
                )
            produto_t01 = obrigacao_t01.produto
            movimentos = MovimentoEstoque.objects.filter(
                produto=produto_t01,
                unidade=obrigacao_t01.unidade,
            ).count()
            if movimentos != movimentos_esperados:
                falhas.append(
                    f"T01 {numero}: movimentos esperados={movimentos_esperados}, "
                    f"atuais={movimentos}"
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
