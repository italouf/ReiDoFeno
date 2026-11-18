from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Unidade
from core.uploads import validar_arquivo
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

    def clean_data_pagamento(self):
        valor = self.cleaned_data["data_pagamento"]
        agora = timezone.now()
        if valor > agora + timedelta(minutes=5):
            raise forms.ValidationError(
                "Data do pagamento não pode estar no futuro."
            )
        if valor < agora - timedelta(days=365):
            raise forms.ValidationError(
                "Data do pagamento anterior a um ano exige revisão."
            )
        return valor

    def clean(self):
        limpo = super().clean()
        metodo = limpo.get("metodo")
        referencia = (limpo.get("referencia") or "").strip()

        if metodo == ComprovantePagamento.Metodo.PIX and not referencia:
            self.add_error("referencia", "PIX exige o ID da transação.")
        if metodo == ComprovantePagamento.Metodo.PIX and referencia:
            if ComprovantePagamento.objects.filter(
                metodo=ComprovantePagamento.Metodo.PIX,
                referencia=referencia,
            ).exists():
                self.add_error(
                    "referencia",
                    "Já existe comprovante PIX com esta referência.",
                )

        arquivo = limpo.get("arquivo")
        if arquivo:
            try:
                validar_arquivo(
                    arquivo,
                    tipos=TIPOS_COMPROVANTE,
                    extensoes=EXTENSOES_COMPROVANTE,
                    tamanho_maximo=TAMANHO_MAXIMO_COMPROVANTE,
                )
            except ValidationError as erro:
                self.add_error("arquivo", erro)
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
