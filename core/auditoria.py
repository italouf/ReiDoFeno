"""Helper transversal de auditoria para alterações críticas."""
from django.forms.models import model_to_dict

from .models import LogAuditoria

_CAMPOS_JSON = (str, int, float, bool)


def _ip_da_requisicao(request):
    if request is None:
        return None
    meta = getattr(request, "META", {})
    ip = meta.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    return ip or meta.get("REMOTE_ADDR") or None


def _serializar(instancia, campos=None):
    if instancia is None:
        return None
    dados = model_to_dict(instancia)
    if campos:
        dados = {c: v for c, v in dados.items() if c in campos}
    return {
        chave: valor if isinstance(valor, _CAMPOS_JSON) else str(valor)
        for chave, valor in dados.items()
    }


def registrar_auditoria(
    *,
    acao: str,
    instancia,
    request=None,
    antes=None,
    depois=None,
):
    """Registra uma alteração crítica com autor, IP e estado antes/depois."""
    usuario = None
    if request is not None:
        candidato = getattr(request, "user", None)
        usuario = candidato if (candidato and candidato.is_authenticated) else None

    if antes is None and depois is None and instancia is not None:
        depois = _serializar(instancia)

    return LogAuditoria.objects.create(
        usuario=usuario,
        acao=acao,
        objeto_tipo=f"{instancia._meta.app_label}.{instancia.__class__.__name__}",
        objeto_id=str(instancia.pk),
        antes=antes or None,
        depois=depois or None,
        ip=_ip_da_requisicao(request),
    )


class AuditoriaFormValidMixin:
    """Para CreateView/UpdateView: audita criação e alteração automaticamente.

    Defina ``acao_prefixo`` (ex.: ``"produto"``) e opcionalmente
    ``campos_auditados`` para restringir os campos serializados.
    """

    acao_prefixo: str = ""
    campos_auditados = None

    def form_valid(self, form):
        criado = form.instance.pk is None
        antes = None
        if not criado:
            original = (
                type(form.instance)
                .objects.filter(pk=form.instance.pk)
                .first()
            )
            antes = _serializar(original, self.campos_auditados)

        resposta = super().form_valid(form)

        registrar_auditoria(
            acao=(
                f"{self.acao_prefixo}.{'criado' if criado else 'alterado'}"
                if self.acao_prefixo
                else "objeto.alterado"
            ),
            instancia=form.instance,
            request=self.request,
            antes=antes,
            depois=_serializar(form.instance, self.campos_auditados),
        )
        return resposta
