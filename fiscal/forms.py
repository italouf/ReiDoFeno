from datetime import timedelta

from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone

from core.uploads import validar_arquivo

TAMANHO_MAXIMO_PDF = 5 * 1024 * 1024
JANELA_RETROATIVA_EMISSAO = timedelta(days=730)


def _validar_data_emissao(valor):
    if valor is None:
        return valor
    agora = timezone.now()
    if valor > agora + timedelta(days=1):
        raise forms.ValidationError(
            "Data de emissão não pode estar no futuro."
        )
    if valor < agora - JANELA_RETROATIVA_EMISSAO:
        raise forms.ValidationError(
            "Data de emissão anterior a dois anos exige revisão fiscal."
        )
    return valor


def _validar_pdf(arquivo):
    validar_arquivo(
        arquivo,
        tipos={"application/pdf"},
        extensoes=(".pdf",),
        tamanho_maximo=TAMANHO_MAXIMO_PDF,
    )
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

    def clean_data_emissao(self):
        return _validar_data_emissao(
            self.cleaned_data.get("data_emissao")
        )

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

    def clean_data_emissao(self):
        return _validar_data_emissao(
            self.cleaned_data.get("data_emissao")
        )


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
