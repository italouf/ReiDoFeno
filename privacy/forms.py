from django import forms

from .models import SolicitacaoTitular


class NovaSolicitacaoForm(forms.Form):
    tipo = forms.ChoiceField(
        label="Tipo de solicitação",
        choices=[
            (SolicitacaoTitular.Tipo.ACESSO, "Acesso aos meus dados"),
            (SolicitacaoTitular.Tipo.CORRECAO, "Correção dos meus dados"),
            (SolicitacaoTitular.Tipo.EXPORTACAO, "Exportação dos meus dados"),
            (SolicitacaoTitular.Tipo.EXCLUSAO, "Exclusão dos meus dados"),
        ],
        widget=forms.RadioSelect,
    )
