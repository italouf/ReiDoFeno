"""Serviços LGPD: consentimento, exportação e exclusão condicionada."""
import json
import logging
import uuid

from django.utils import timezone

from customers.models import Cliente

from .models import ConsentimentoLGPD, SolicitacaoTitular

logger = logging.getLogger(__name__)

VERSAO_POLITICA = "1.0"


def registrar_consentimento(
    *, cliente: Cliente, finalidade: str, aceito: bool = True, ip=None
) -> ConsentimentoLGPD:
    """Registra (ou registra a revogação de) um consentimento versionado."""
    return ConsentimentoLGPD.objects.create(
        cliente=cliente,
        finalidade=finalidade,
        versao_politica=VERSAO_POLITICA,
        aceito=aceito,
        ip=ip,
    )


def tem_consentimento_ativo(cliente: Cliente, finalidade: str) -> bool:
    """Último registro da finalidade define o estado do consentimento."""
    ultimo = (
        ConsentimentoLGPD.objects.filter(
            cliente=cliente, finalidade=finalidade
        )
        .order_by("-criado_em")
        .first()
    )
    return bool(ultimo and ultimo.aceito)


def abrir_solicitacao(*, cliente: Cliente, tipo: str) -> SolicitacaoTitular:
    prazo = (timezone.now() + timezone.timedelta(days=15)).date()
    return SolicitacaoTitular.objects.create(
        cliente=cliente, tipo=tipo, prazo_limite=prazo
    )


def exportar_dados_do_titular(cliente: Cliente) -> dict:
    """Agrega todos os dados pessoais do titular em estrutura portável."""
    pedidos = []
    for pedido in cliente.pedidos.prefetch_related("itens"):
        pedidos.append(
            {
                "numero": pedido.numero,
                "status": pedido.status,
                "modalidade": pedido.modalidade,
                "unidade": pedido.unidade.nome,
                "criado_em": pedido.criado_em.isoformat(),
                "total": str(pedido.total),
                "endereco": {
                    "logradouro": pedido.logradouro,
                    "numero": pedido.numero_endereco,
                    "bairro": pedido.bairro,
                    "cidade": pedido.cidade,
                    "uf": pedido.uf,
                    "cep": pedido.cep,
                },
                "itens": [
                    {
                        "produto": item.produto_nome,
                        "quantidade": str(item.quantidade),
                        "preco_unitario": str(item.preco_unitario),
                        "subtotal": str(item.subtotal),
                    }
                    for item in pedido.itens.all()
                ],
            }
        )
    return {
        "cliente": {
            "nome": cliente.nome,
            "documento": cliente.documento,
            "tipo_pessoa": cliente.tipo_pessoa,
            "categoria": cliente.categoria,
            "telefone": cliente.telefone,
            "email": cliente.email,
            "endereco": {
                "logradouro": cliente.logradouro,
                "numero": cliente.numero,
                "bairro": cliente.bairro,
                "cidade": cliente.cidade,
                "uf": cliente.uf,
                "cep": cliente.cep,
            },
            "preferencia": cliente.preferencia,
            "criado_em": cliente.criado_em.isoformat(),
        },
        "consentimentos": [
            {
                "finalidade": c.finalidade,
                "versao": c.versao_politica,
                "aceito": c.aceito,
                "data": c.criado_em.isoformat(),
            }
            for c in cliente.consentimentos.all()
        ],
        "pedidos": pedidos,
    }


def anonimizar_cliente(cliente: Cliente) -> bool:
    """Anonimiza dados pessoais preservando registros fiscais.

    Retorna True quando houve anonimização; False quando o cadastro foi
    excluído por completo (nenhuma retenção legal aplicável).
    """
    tem_retencacao = cliente.pedidos.exists()

    if not tem_retencacao:
        logger.info(
            "Cliente %s sem registros fiscais: excluído integralmente.",
            cliente.pk,
        )
        cliente.delete()
        return False

    sufixo = uuid.uuid4().hex[:10]
    cliente.nome = f"Titular removido ({sufixo})"
    # Documento pseudonimizado apenas com dígitos (save() normaliza).
    cliente.documento = f"999{uuid.uuid4().int % 10**11:011d}"
    cliente.telefone = ""
    cliente.email = ""
    cliente.logradouro = ""
    cliente.numero = ""
    cliente.bairro = ""
    cliente.cidade = ""
    cliente.uf = ""
    cliente.cep = ""
    cliente.preferencia = ""
    cliente.usuario = None
    cliente.save()

    logger.info("Cliente %s anonimizado com retenção fiscal.", cliente.pk)
    return True


def payload_json_exportacao(dados: dict) -> bytes:
    return json.dumps(dados, ensure_ascii=False, indent=2).encode()
