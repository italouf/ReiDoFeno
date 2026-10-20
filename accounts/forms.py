from django import forms
from django.contrib.auth.forms import AuthenticationForm

from customers.models import normalizar_documento
from customers.validators import DocumentoValidator


class LoginForm(AuthenticationForm):
    """Formulário de login padrão com rótulos em português."""

    error_messages = {
        "invalid_login": "Usuário ou senha incorretos. Verifique os dados e tente novamente.",
        "inactive": "Esta conta está desativada. Fale com o administrador.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "placeholder": "Seu usuário"}
        )
        self.fields["password"].widget.attrs.update({"placeholder": "Sua senha"})


class VinculoClienteForm(forms.Form):
    """Documento usado para localizar um cadastro ainda não vinculado."""

    documento = forms.CharField(
        label="CPF/CNPJ do cadastro",
        max_length=18,
        validators=[DocumentoValidator()],
        widget=forms.TextInput(
            attrs={"placeholder": "000.000.000-00", "autocomplete": "off"}
        ),
    )

    def clean_documento(self) -> str:
        return normalizar_documento(self.cleaned_data["documento"])
