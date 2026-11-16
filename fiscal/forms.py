from django import forms
from django.core.validators import RegexValidator

TAMANHO_MAXIMO_PDF = 5 * 1024 * 1024


def _validar_pdf(arquivo):
    if arquivo is None:
        return arquivo
    if arquivo.size > TAMANHO_MAXIMO_PDF:
        raise forms.ValidationError("PDF muito grande (máximo 5 MB).")
    content_type = getattr(arquivo, "content_type", "") or ""
    nome = (arquivo.name or "").lower()
    if content_type and content_type != "application/pdf":
        raise forms.ValidationError("Envie um arquivo PDF.")
    if not content_type and not nome.endswith(".pdf"):
        raise forms.ValidationError("Envie um arquivo PDF.")
    if arquivo.size == 0:
        raise forms.ValidationError("Arquivo vazio.")
    return arquivo


class NotaManualForm(forms.Form):
    numero = forms.CharField(label="Número da NF-e", max_length=20)
    serie = forms.CharField(
        label="Série", max_length=10, required=False
    )
    chave_acesso = forms.CharField(
        label="Chave de acesso",
        max_length=44,
        validators=[RegexValidator(r"^\d{44}$", "Informe 44 dígitos.")],
    )
    data_emissao = forms.DateTimeField(
        label="Data de emissão",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
    )
    cfop = forms.CharField(
        label="CFOP",
        max_length=10,
        required=False,
        help_text="Preenchido automaticamente quando vazio.",
    )
    motivo_retificacao = forms.CharField(
        label="Motivo da retificação de CFOP",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    evidencia_retificacao = forms.URLField(
        label="Evidência documental da retificação",
        required=False,
    )
    link_documento = forms.URLField(
        label="Link do XML/DANFE", required=False
    )
    pdf = forms.FileField(
        label="PDF da NF-e", required=False,
        help_text="Opcional no registro; use o anexo para o fluxo assistido.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_emissao"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ]

    def clean_pdf(self):
        return _validar_pdf(self.cleaned_data.get("pdf"))

    def clean_cfop(self):
        from .services import calcular_cfop_inverso

        cfop = (self.cleaned_data.get("cfop") or "").strip()
        if not cfop:
            return cfop
        try:
            calcular_cfop_inverso(cfop)
        except Exception as erro:
            raise forms.ValidationError(
                "CFOP de saída sem mapeamento de devolução validado."
            ) from erro
        return cfop


class AnexoNotaFiscalForm(forms.Form):
    numero = forms.CharField(
        label="Número da NF-e", max_length=20, required=False
    )
    serie = forms.CharField(
        label="Série", max_length=10, required=False
    )
    chave_acesso = forms.CharField(
        label="Chave de acesso",
        max_length=44,
        required=False,
        validators=[RegexValidator(r"^\d{44}$", "Informe 44 dígitos.")],
    )
    data_emissao = forms.DateTimeField(
        label="Data de emissão",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
    )
    pdf = forms.FileField(label="PDF da NF-e")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_emissao"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ]

    def clean_pdf(self):
        return _validar_pdf(self.cleaned_data.get("pdf"))


class NotaEntradaManualForm(forms.Form):
    numero = forms.CharField(label="Número da NF-e de entrada", max_length=20)
    chave_acesso = forms.CharField(
        label="Chave de acesso da entrada",
        max_length=44,
        validators=[RegexValidator(r"^\d{44}$", "Informe 44 dígitos.")],
    )
    link_documento = forms.URLField(
        label="Link do XML/DANFE", required=False
    )
