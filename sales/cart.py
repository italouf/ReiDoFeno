"""Carrinho de compras baseado em sessão.

Preços e totais são SEMPRE recalculados no servidor a partir do banco.
"""
from decimal import Decimal

from django.db.models import Sum

from catalog.models import Produto
from stock.models import Estoque

_CHAVE_SESSAO = "carrinho"


class Carrinho:
    def __init__(self, request):
        self.session = request.session
        self.data: dict[str, str] = dict(self.session.get(_CHAVE_SESSAO, {}))

    # ------------------------------------------------------------------ #
    def salvar(self):
        self.session[_CHAVE_SESSAO] = {k: str(v) for k, v in self.data.items()}
        self.session.modified = True

    def adicionar(self, produto_id, quantidade):
        quantidade = int(quantidade)
        if quantidade <= 0:
            raise ValueError("Quantidade deve ser positiva.")
        chave = str(produto_id)
        atual = int(self.data.get(chave, 0))
        self.data[chave] = atual + quantidade

    def definir(self, produto_id, quantidade):
        quantidade = int(quantidade)
        chave = str(produto_id)
        if quantidade <= 0:
            self.data.pop(chave, None)
        else:
            self.data[chave] = quantidade

    def remover(self, produto_id):
        self.data.pop(str(produto_id), None)

    def limpar(self):
        self.data.clear()
        self.salvar()

    def __len__(self) -> int:
        return sum(int(q) for q in self.data.values())

    # ------------------------------------------------------------------ #
    def itens(self):
        """Lista [(produto, quantidade, subtotal)] apenas com produtos ativos."""
        ids = [int(k) for k in self.data.keys()]
        produtos = {
            p.pk: p
            for p in Produto.objects.filter(pk__in=ids, ativo=True).select_related(
                "categoria"
            )
        }
        itens = []
        for chave, quantidade_str in self.data.items():
            produto = produtos.get(int(chave))
            if produto is None:
                continue  # produto inativo/removido some do carrinho
            quantidade = int(quantidade_str)
            subtotal = produto.preco_online * Decimal(quantidade)
            itens.append(
                {
                    "produto": produto,
                    "quantidade": quantidade,
                    "subtotal": subtotal,
                }
            )
        return itens

    def total(self) -> Decimal:
        return sum((item["subtotal"] for item in self.itens()), Decimal("0.00"))

    @staticmethod
    def disponivel_total(produto) -> Decimal:
        """Saldo somado das unidades ativas (validação antecipada do carrinho)."""
        agregado = Estoque.objects.filter(
            produto=produto, unidade__ativa=True
        ).aggregate(saldo=Sum("quantidade"), bloqueada=Sum("quantidade_bloqueada"))
        saldo = agregado["saldo"] or Decimal("0")
        bloqueada = agregado["bloqueada"] or Decimal("0")
        return saldo - bloqueada
