from django import forms

from catalog.models import Produto
from core.models import Unidade
from stock.models import MovimentoEstoque


class MovimentoForm(forms.Form):
    """Entrada ou saída de mercadoria."""

    tipo = forms.ChoiceField(
        choices=[
            (MovimentoEstoque.Tipo.ENTRADA, "Entrada"),
            (MovimentoEstoque.Tipo.SAIDA, "Saída"),
        ],
        widget=forms.HiddenInput,
    )
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.filter(ativo=True), label="Produto"
    )
    unidade = forms.ModelChoiceField(queryset=Unidade.objects.all(), label="Unidade")
    quantidade = forms.DecimalField(
        label="Quantidade", min_value=0.01, decimal_places=2, max_digits=12,
        localize=True,
    )


class AjusteForm(forms.Form):
    """Ajuste manual de saldo com sinal e motivo obrigatório."""

    produto = forms.ModelChoiceField(
        queryset=Produto.objects.filter(ativo=True), label="Produto"
    )
    unidade = forms.ModelChoiceField(queryset=Unidade.objects.all(), label="Unidade")
    quantidade = forms.DecimalField(
        label="Quantidade do ajuste",
        help_text="Use valor negativo para reduzir o saldo.",
        decimal_places=2, max_digits=12, localize=True,
    )
    motivo = forms.CharField(
        label="Motivo", max_length=255,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean(self):
        limpo = super().clean()
        if limpo.get("quantidade") == 0:
            self.add_error("quantidade", "O ajuste não pode ser zero.")
        return limpo


class TransferenciaForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.filter(ativo=True), label="Produto"
    )
    unidade_origem = forms.ModelChoiceField(
        queryset=Unidade.objects.all(), label="Unidade de origem"
    )
    unidade_destino = forms.ModelChoiceField(
        queryset=Unidade.objects.all(), label="Unidade de destino"
    )
    quantidade = forms.DecimalField(
        label="Quantidade", min_value=0.01, decimal_places=2, max_digits=12,
        localize=True,
    )

    def clean(self):
        limpo = super().clean()
        origem = limpo.get("unidade_origem")
        destino = limpo.get("unidade_destino")
        if origem and destino and origem == destino:
            self.add_error(
                "unidade_destino",
                "A unidade de destino deve ser diferente da origem.",
            )
        return limpo
