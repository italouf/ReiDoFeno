"""Serviço fiscal: elegibilidade, envio ao ERP e reprocessamento."""
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from analytics.models import Aviso
from customers.validators import DocumentoValidator, normalizar_documento

from .client import ErroFiscal, obter_client
from .models import NotaFiscal

logger = logging.getLogger(__name__)

CFOP_INVERSO = {
    "5.101": "1.201",
    "5.102": "1.202",
    "5.103": "1.203",
    "5.104": "1.204",
    "5.105": "1.205",
    "5.106": "1.206",
    "5.107": "1.207",
    "5.108": "1.208",
    "5.109": "1.209",
    "5.110": "1.210",
    "6.101": "2.201",
    "6.102": "2.202",
    "6.103": "2.203",
    "7.101": "3.101",
    "7.102": "3.102",
}


def calcular_cfop_inverso(cfop: str) -> str:
    """CFOP de devolução para uma operação de saída.

    Somente operações presentes na tabela explícita são aceitas. A regra
    genérica de prefixo não é prova de enquadramento fiscal.
    """
    normalizado = (cfop or "").strip().replace(".", "")
    if len(normalizado) != 4 or not normalizado.isdigit():
        raise ValidationError("CFOP inválido para devolução.")
    if normalizado[0] not in ("5", "6", "7"):
        raise ValidationError("CFOP não é de uma operação de saída.")
    com_ponto = f"{normalizado[0]}.{normalizado[1:]}"
    if com_ponto in CFOP_INVERSO:
        return CFOP_INVERSO[com_ponto]
    raise ValidationError(
        "CFOP de saída sem mapeamento de devolução validado pelo responsável "
        "fiscal."
    )


# Compatibilidade com o nome interno previsto na especificação da Fase 2C.
_calcular_cfop_inverso = calcular_cfop_inverso


@transaction.atomic
def cancelar_nota_fiscal(nota, *, motivo: str, usuario=None, request=None):
    """Cancela uma NF-e autorizada; idempotente e auditado."""
    if not (motivo or "").strip():
        raise ValidationError("Justificativa do cancelamento é obrigatória.")
    nota = NotaFiscal.objects.select_for_update().get(pk=nota.pk)
    if nota.status == NotaFiscal.Status.CANCELADA:
        if nota.tentativa_atual is not None or nota.processando_desde is not None:
            nota.tentativa_atual = None
            nota.processando_desde = None
            nota.save(
                update_fields=[
                    "tentativa_atual",
                    "processando_desde",
                    "atualizado_em",
                ]
            )
        return nota
    if nota.status != NotaFiscal.Status.AUTORIZADA:
        raise ValidationError(
            "Somente NF-e autorizada pode ser cancelada."
        )
    tentativa_cancelada = nota.tentativa_atual
    nota.status = NotaFiscal.Status.CANCELADA
    nota.tentativa_atual = None
    nota.processando_desde = None
    nota.save(
        update_fields=[
            "status",
            "tentativa_atual",
            "processando_desde",
            "atualizado_em",
        ]
    )
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="fiscal.nota_cancelada",
        instancia=nota,
        request=request,
        usuario=usuario,
        depois={
            "status": nota.status,
            "motivo": motivo.strip()[:500],
            "pedido": nota.pedido.numero,
            "tentativa": (
                str(tentativa_cancelada) if tentativa_cancelada else None
            ),
        },
    )
    return nota


def relatorio_fiscal(inicio: date, fim: date) -> dict:
    """Receita fiscal do período, separando internas e interestaduais.

    Aprovações entram positivas na data do pagamento; estornos entram
    negativos na data do evento, alinhados à ANA-01.
    """
    from analytics.services import (
        pagamentos_aprovados,
        pagamentos_estornados,
    )

    aprovados = pagamentos_aprovados(inicio, fim)
    estornos = pagamentos_estornados(inicio, fim)
    totais_aprovados = aprovados.aggregate(
        intrastadual=Sum(
            "valor", filter=Q(pedido__interestadual=False)
        ),
        interestadual=Sum(
            "valor", filter=Q(pedido__interestadual=True)
        ),
    )
    totais_estornos = estornos.aggregate(
        intrastadual=Sum(
            "valor", filter=Q(pedido__interestadual=False)
        ),
        interestadual=Sum(
            "valor", filter=Q(pedido__interestadual=True)
        ),
    )
    linhas = []
    for pagamento in aprovados.order_by("pedido__numero"):
        linhas.append(
            {
                "pedido": pagamento.pedido.numero,
                "pedido_id": pagamento.pedido_id,
                "unidade": pagamento.pedido.unidade.nome,
                "uf_entrega": (
                    pagamento.pedido.uf_entrega or pagamento.pedido.uf
                ),
                "interestadual": pagamento.pedido.interestadual,
                "aliquota_icms": pagamento.pedido.aliquota_icms,
                "valor": pagamento.valor,
                "evento": "aprovacao",
                "evento_em": pagamento.aprovado_em,
                "estorno": False,
            }
        )
    for pagamento in estornos.order_by("pedido__numero"):
        linhas.append(
            {
                "pedido": pagamento.pedido.numero,
                "pedido_id": pagamento.pedido_id,
                "unidade": pagamento.pedido.unidade.nome,
                "uf_entrega": (
                    pagamento.pedido.uf_entrega or pagamento.pedido.uf
                ),
                "interestadual": pagamento.pedido.interestadual,
                "aliquota_icms": pagamento.pedido.aliquota_icms,
                "valor": -pagamento.valor,
                "evento": "estorno",
                "evento_em": pagamento.estornado_em,
                "estorno": True,
            }
        )
    linhas.sort(
        key=lambda linha: (linha["evento_em"], linha["pedido"])
    )
    intrastadual = (
        totais_aprovados["intrastadual"] or Decimal("0.00")
    ) - (totais_estornos["intrastadual"] or Decimal("0.00"))
    interestadual = (
        totais_aprovados["interestadual"] or Decimal("0.00")
    ) - (totais_estornos["interestadual"] or Decimal("0.00"))
    return {
        "inicio": inicio,
        "fim": fim,
        "vendas_intrastaduais": intrastadual,
        "vendas_interestaduais": interestadual,
        "aliquota_interestadual": Decimal("0.1200"),
        "linhas": linhas,
    }


def pedido_elegivel(pedido) -> bool:
    """Pedido com pagamento aprovado e documento válido do cliente."""
    if (
        pedido.status_financeiro != "pago"
        or not pedido.financeiro_conciliado
        or pedido.status == "cancelado"
    ):
        return False
    documento = normalizar_documento(pedido.cliente.documento)
    try:
        DocumentoValidator()(documento)
    except ValidationError:
        return False
    return True


def _aviso_documento_invalido(pedido) -> None:
    Aviso.registrar(
        tipo=Aviso.Tipo.FISCAL_DOCUMENTO,
        mensagem=(
            f"Pedido {pedido.numero} pago com CPF/CNPJ inválido "
            f"({pedido.cliente.nome}); corrija para emitir a NF-e."
        ),
        objeto=pedido,
        severidade=Aviso.Severidade.ERRO,
    )


LEASE_EMISSAO = timedelta(minutes=2)


def _aviso_nota_cancelada(nota) -> None:
    Aviso.registrar(
        tipo=Aviso.Tipo.FISCAL_ERRO,
        mensagem=(
            f"NF-e cancelada do pedido {nota.pedido.numero}; "
            "retry ordinário bloqueado."
        ),
        objeto=nota,
        severidade=Aviso.Severidade.ERRO,
    )


def _registrar_resultado_externo(
    nota, *, token, tipo, resultado, motivo
) -> bool:
    """Persiste resposta externa obsoleta/conflitante de forma idempotente."""
    dados = dict(nota.resultado_externo or {})
    eventos = list(dados.get("eventos", []))
    token_str = str(token)
    if any(
        evento.get("tentativa") == token_str
        and evento.get("tipo") == tipo
        for evento in eventos
    ):
        return False
    eventos.append(
        {
            "tentativa": token_str,
            "tipo": tipo,
            "resultado": {
                chave: str(valor)
                for chave, valor in (resultado or {}).items()
            },
            "motivo": motivo[:300],
            "em": timezone.now().isoformat(),
        }
    )
    dados["eventos"] = eventos[-20:]
    nota.resultado_externo = dados
    nota.save(update_fields=["resultado_externo", "atualizado_em"])
    Aviso.registrar(
        tipo=Aviso.Tipo.FISCAL_ERRO,
        mensagem=(
            f"Resposta externa conflitante/obsoleta para "
            f"{nota.pedido.numero}; conciliação fiscal necessária."
        ),
        objeto=nota,
        severidade=Aviso.Severidade.ERRO,
    )
    from core.auditoria import registrar_auditoria

    registrar_auditoria(
        acao="fiscal.resultado_externo_obsoleto",
        instancia=nota,
        depois={
            "tentativa": token_str,
            "tipo": tipo,
            "motivo": motivo[:300],
            "resultado": {
                chave: str(valor)
                for chave, valor in (resultado or {}).items()
            },
        },
    )
    return True


@transaction.atomic
def _preparar_emissao(pedido, client):
    """Fase curta: revalida sob lock, cria/claima a nota e libera o lock."""
    pedido = type(pedido).objects.select_for_update().get(pk=pedido.pk)
    if (
        pedido.status_financeiro != "pago"
        or not pedido.financeiro_conciliado
        or pedido.status == "cancelado"
        or not pedido_elegivel(pedido)
    ):
        if pedido.status != "cancelado" and not pedido_elegivel(pedido):
            _aviso_documento_invalido(pedido)
        return pedido, None, False, None

    nota, _criada = NotaFiscal.objects.select_for_update().get_or_create(
        pedido=pedido, tipo=NotaFiscal.Tipo.SAIDA
    )
    if nota.status == NotaFiscal.Status.CANCELADA:
        _aviso_nota_cancelada(nota)
        return pedido, nota, False, None
    if nota.status == NotaFiscal.Status.AUTORIZADA:
        return pedido, nota, False, None

    agora = timezone.now()
    if (
        nota.processando_desde is not None
        and agora - nota.processando_desde < LEASE_EMISSAO
    ):
        logger.info(
            "Emissão já em andamento para o pedido %s; retry ignorado.",
            pedido.numero,
        )
        return pedido, nota, False, None

    if not nota.cfop:
        nota.cfop = "6.102" if pedido.interestadual else "5.102"
    token = uuid.uuid4()
    nota.tentativas += 1
    nota.processando_desde = agora
    nota.tentativa_atual = token
    nota.status = NotaFiscal.Status.PENDENTE
    nota.ultimo_erro = ""
    nota.save(
        update_fields=[
            "tentativas",
            "processando_desde",
            "tentativa_atual",
            "status",
            "ultimo_erro",
            "cfop",
            "atualizado_em",
        ]
    )
    return pedido, nota, True, token


def enviar_para_emissao(pedido, client=None) -> NotaFiscal | None:
    """Emite em duas fases para não manter lock durante a chamada externa.

    A tentativa recebe um token próprio antes da chamada externa. A conclusão,
    seja sucesso ou erro, só altera o documento se esse token ainda for o dono
    do claim. Resultados de tentativas antigas são preservados em
    ``resultado_externo`` e geram pendência de conciliação, sem sobrescrever
    documento confirmado, cancelado ou resultado de tentativa mais nova.
    """
    client = client or obter_client()
    pedido, nota, reivindicada, token = _preparar_emissao(pedido, client)
    if not reivindicada:
        return nota

    try:
        resultado = client.criar_nfe(pedido)
    except ErroFiscal as erro:
        with transaction.atomic():
            nota = NotaFiscal.objects.select_for_update().get(pk=nota.pk)
            if nota.tentativa_atual != token:
                _registrar_resultado_externo(
                    nota,
                    token=token,
                    tipo="erro",
                    resultado={"erro": str(erro)[:500]},
                    motivo="erro de tentativa que perdeu a autoridade",
                )
                return nota
            if nota.status in (
                NotaFiscal.Status.AUTORIZADA,
                NotaFiscal.Status.CANCELADA,
            ):
                _registrar_resultado_externo(
                    nota,
                    token=token,
                    tipo="erro",
                    resultado={"erro": str(erro)[:500]},
                    motivo="erro de tentativa sobre documento terminal",
                )
                nota.tentativa_atual = None
                nota.processando_desde = None
                nota.save(
                    update_fields=[
                        "tentativa_atual",
                        "processando_desde",
                        "atualizado_em",
                    ]
                )
                return nota
            nota.status = NotaFiscal.Status.ERRO
            nota.ultimo_erro = str(erro)[:500]
            nota.tentativa_atual = None
            nota.processando_desde = None
            nota.save(
                update_fields=[
                    "status",
                    "ultimo_erro",
                    "tentativa_atual",
                    "processando_desde",
                    "atualizado_em",
                ]
            )
            from core.auditoria import registrar_auditoria

            registrar_auditoria(
                acao="fiscal.nota_erro",
                instancia=nota,
                depois={
                    "status": nota.status,
                    "tentativas": nota.tentativas,
                    "erro": nota.ultimo_erro,
                },
            )
            Aviso.registrar(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                mensagem=(
                    f"Falha ao emitir NF-e do pedido {pedido.numero}: {erro}"
                ),
                objeto=nota,
                severidade=Aviso.Severidade.ERRO,
            )
        logger.warning("Falha fiscal no pedido %s: %s", pedido.numero, erro)
        return nota

    with transaction.atomic():
        pedido_atual = type(pedido).objects.select_for_update().get(
            pk=pedido.pk
        )
        nota = NotaFiscal.objects.select_for_update().get(pk=nota.pk)
        if nota.tentativa_atual != token:
            _registrar_resultado_externo(
                nota,
                token=token,
                tipo="sucesso",
                resultado=resultado,
                motivo="sucesso de tentativa que perdeu a autoridade",
            )
            return nota
        if nota.status in (
            NotaFiscal.Status.AUTORIZADA,
            NotaFiscal.Status.CANCELADA,
        ):
            _registrar_resultado_externo(
                nota,
                token=token,
                tipo="sucesso",
                resultado=resultado,
                motivo="sucesso de tentativa sobre documento terminal",
            )
            nota.tentativa_atual = None
            nota.processando_desde = None
            nota.save(
                update_fields=[
                    "tentativa_atual",
                    "processando_desde",
                    "atualizado_em",
                ]
            )
            return nota

        nota.numero = resultado.get("numero", "")
        nota.chave_acesso = resultado.get("chave", "")
        nota.link_documento = resultado.get("link", "")
        nota.tentativa_atual = None
        nota.processando_desde = None
        nota.ultimo_erro = ""
        nota.status = NotaFiscal.Status.AUTORIZADA

        if (
            pedido_atual.status == "cancelado"
            or pedido_atual.status_financeiro != "pago"
        ):
            nota.ultimo_erro = (
                "NF-e autorizada após cancelamento/estorno; "
                "conciliação fiscal necessária."
            )
        try:
            with transaction.atomic():
                nota.save(
                    update_fields=[
                        "numero",
                        "chave_acesso",
                        "link_documento",
                        "tentativa_atual",
                        "processando_desde",
                        "ultimo_erro",
                        "status",
                        "atualizado_em",
                    ]
                )
        except IntegrityError:
            _registrar_resultado_externo(
                nota,
                token=token,
                tipo="conflito_chave",
                resultado=resultado,
                motivo="chave externa já registrada em outra nota",
            )
            nota.status = NotaFiscal.Status.ERRO
            nota.ultimo_erro = "Chave de acesso já registrada em outra nota."
            nota.tentativa_atual = None
            nota.processando_desde = None
            nota.save(
                update_fields=[
                    "status",
                    "ultimo_erro",
                    "tentativa_atual",
                    "processando_desde",
                    "atualizado_em",
                ]
            )
            Aviso.registrar(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                mensagem=(
                    f"Chave duplicada ao emitir NF-e do pedido {pedido.numero}."
                ),
                objeto=nota,
                severidade=Aviso.Severidade.ERRO,
            )
            return nota

        from core.auditoria import registrar_auditoria

        if nota.ultimo_erro:
            Aviso.registrar(
                tipo=Aviso.Tipo.FISCAL_ERRO,
                mensagem=(
                    f"Pedido {pedido_atual.numero}: {nota.ultimo_erro}"
                ),
                objeto=nota,
                severidade=Aviso.Severidade.ERRO,
            )
            registrar_auditoria(
                acao="fiscal.autorizacao_apos_cancelamento",
                instancia=nota,
                depois={
                    "status": nota.status,
                    "numero": nota.numero,
                    "chave": nota.chave_acesso,
                    "pedido_status": pedido_atual.status,
                    "pedido_financeiro": pedido_atual.status_financeiro,
                    "tentativa": str(token),
                },
            )
            return nota

        registrar_auditoria(
            acao="fiscal.nota_autorizada",
            instancia=nota,
            depois={
                "status": nota.status,
                "numero": nota.numero,
                "chave": nota.chave_acesso,
                "tentativas": nota.tentativas,
                "tentativa": str(token),
            },
        )
        return nota


def processar_fila_fiscal() -> int:
    """Varre pedidos pagos sem NF-e autorizada e tenta emitir (idempotente)."""
    from django.db.models import Exists, OuterRef

    from sales.models import Pedido

    autorizada = NotaFiscal.objects.filter(
        pedido=OuterRef("pk"),
        tipo=NotaFiscal.Tipo.SAIDA,
        status__in=(
            NotaFiscal.Status.AUTORIZADA,
            NotaFiscal.Status.CANCELADA,
        ),
    )
    pedidos = (
        Pedido.objects.filter(
            status_financeiro="pago", financeiro_conciliado=True
        )
        .exclude(status="cancelado")
        .exclude(Exists(autorizada))
        .select_related("cliente")
    )
    enviados = 0
    for pedido in pedidos:
        resultado = enviar_para_emissao(pedido)
        if resultado is not None and resultado.status == NotaFiscal.Status.AUTORIZADA:
            enviados += 1
    return enviados


def avisar_pagos_sem_nfe(horas_limite: int = 24) -> int:
    """Avisa sobre pedidos pagos há mais de X horas sem NF-e autorizada."""
    from datetime import timedelta

    limite = timezone.now() - timedelta(hours=horas_limite)
    from django.db.models import Exists, OuterRef

    from sales.models import Pedido

    autorizada = NotaFiscal.objects.filter(
        pedido=OuterRef("pk"),
        tipo=NotaFiscal.Tipo.SAIDA,
        status=NotaFiscal.Status.AUTORIZADA,
    )
    pendentes = (
        Pedido.objects.filter(
            status_financeiro="pago",
            financeiro_conciliado=True,
            atualizado_em__lt=limite,
        )
        .exclude(status="cancelado")
        .exclude(Exists(autorizada))
    )
    total = 0
    for pedido in pendentes.select_related("cliente"):
        Aviso.registrar(
            tipo=Aviso.Tipo.PAGO_SEM_NFE,
            mensagem=(
                f"Pedido {pedido.numero} segue pago sem NF-e emitida."
            ),
            objeto=pedido,
        )
        total += 1
    return total
