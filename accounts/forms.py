from django.contrib.auth.forms import AuthenticationForm


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
