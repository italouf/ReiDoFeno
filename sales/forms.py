from django import forms

from core.models import Unidade
from customers.validators import DocumentoValidator
from sales.models import ComprovantePagamento, Pedido

TIPOS_COMPROVANTE = frozenset(
    {"image/jpeg", "image/png", "application/pdf"}
)
EXTENSOES_COMPROVANTE = (".jpg", ".jpeg", ".png", ".pdf")
TAMANHO_MAXIMO_COMPROVANTE = 5 * 1024 * 1024


class CheckoutForm(forms.Form):
    nome = forms.CharField(max_length=120)
    documento = forms.CharField(
        label="CPF/CNPJ", max_length=18, validators=[DocumentoValidator()]
    )
    email = forms.EmailField()
    telefone = forms.CharField(max_length=20, required=False)
    modalidade = forms.ChoiceField(
        choices=Pedido.Modalidade.choices, widget=forms.RadioSelect
    )
    unidade = forms.ModelChoiceField(label="Unidade", queryset=None)

    logradouro = forms.CharField(max_length=120, required=False)
    numero_endereco = forms.CharField(label="Número", max_length=10, required=False)
    bairro = forms.CharField(max_length=60, required=False)
    cidade = forms.CharField(max_length=60, required=False)
    uf = forms.CharField(max_length=2, required=False)
    cep = forms.CharField(max_length=9, required=False)
    aceita_marketing = forms.BooleanField(
        label="Quero receber novidades e ofertas (opcional)",
        required=False,
        help_text="Consentimento separado, revogável em 'Minha privacidade'.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unidade"].queryset = Unidade.objects.filter(ativa=True)

    def clean(self):
        limpo = super().clean()
        if limpo.get("modalidade") == Pedido.Modalidade.ENTREGA:
            for campo in ("logradouro", "numero_endereco", "cidade", "uf"):
                if not limpo.get(campo):
                    self.add_error(campo, "Informe o endereço completo para entrega.")
        return limpo


class ComprovantePagamentoForm(forms.ModelForm):
    class Meta:
        model = ComprovantePagamento
        fields = [
            "metodo",
            "valor",
            "data_pagamento",
            "referencia",
            "observacao",
            "arquivo",
        ]
        widgets = {
            "data_pagamento": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, pedido=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pedido = pedido
        self.fields["data_pagamento"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ]

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if valor is None or valor <= 0:
            raise forms.ValidationError("Valor deve ser positivo.")
        if self.pedido is not None and valor > self.pedido.saldo_devedor:
            raise forms.ValidationError(
                f"Valor excede o saldo devedor de "
                f"R$ {self.pedido.saldo_devedor}."
            )
        return valor

    def clean(self):
        limpo = super().clean()
        metodo = limpo.get("metodo")
        referencia = (limpo.get("referencia") or "").strip()

        if metodo == ComprovantePagamento.Metodo.PIX and not referencia:
            self.add_error("referencia", "PIX exige o ID da transação.")

        arquivo = limpo.get("arquivo")
        if arquivo:
            if arquivo.size > TAMANHO_MAXIMO_COMPROVANTE:
                self.add_error(
                    "arquivo", "Arquivo muito grande (máximo 5 MB)."
                )
            content_type = getattr(arquivo, "content_type", "") or ""
            nome = (arquivo.name or "").lower()
            if content_type:
                tipo_valido = content_type in TIPOS_COMPROVANTE
            else:
                tipo_valido = nome.endswith(EXTENSOES_COMPROVANTE)
            if not tipo_valido:
                self.add_error(
                    "arquivo",
                    "Apenas imagens (JPG/PNG) ou PDF são aceitos.",
                )
            if arquivo.size == 0:
                self.add_error("arquivo", "Arquivo vazio.")
        return limpo


class CancelamentoForm(forms.Form):
    tipo = forms.ChoiceField(
        label="Caminho",
        choices=Pedido.TipoCancelamento.choices,
        widget=forms.RadioSelect,
    )
    justificativa = forms.CharField(
        label="Justificativa",
        min_length=5,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
