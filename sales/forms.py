from django import forms

from core.models import Unidade
from customers.validators import DocumentoValidator
from sales.models import Pedido


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
