"""Adapters de pagamento (Mercado Pago Checkout Pro).

Em desenvolvimento/testes usa-se o cliente fake (determinístico); em
produção o adapter real conversa com a API oficial usando o token de
variável de ambiente. Nenhum dado de cartão passa pela aplicação.
"""
import hashlib
import hmac
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

API_BASE = "https://api.mercadopago.com"


class ErroPagamento(Exception):
    """Falha de comunicação/resposta do provedor."""


def obter_client():
    if getattr(settings, "MERCADO_PAGO_FAKE", False):
        return MercadoPagoFake()
    if not settings.MERCADO_PAGO_ACCESS_TOKEN:
        raise ErroPagamento(
            "MERCADO_PAGO_ACCESS_TOKEN não configurado para produção."
        )
    return MercadoPagoReal()


# --------------------------------------------------------------------------- #
# Clientes
# --------------------------------------------------------------------------- #


class MercadoPagoFake:
    """Determinístico para testes/dev: init_point aponta ao simulador interno."""

    def criar_preferencia(self, pedido) -> tuple[str, str]:
        preferencia_id = f"fake-pref-{pedido.numero}"
        init_point = reverse("sales:simular_pagamento", args=[pedido.token_acesso])
        return preferencia_id, init_point

    @staticmethod
    def consultar_pagamento(id_externo: str) -> dict:
        aprovado = id_externo.endswith("-ok")
        return {
            "id": id_externo,
            "status": "approved" if aprovado else "refused",
            "external_reference": _numero_do_fake(id_externo),
        }


def _numero_do_fake(id_externo: str) -> str:
    # fake-pay-PF000001-ok / fake-pay-PF000002-recusado
    partes = id_externo.split("-")
    for parte in partes:
        if parte.startswith("PF"):
            return parte
    return ""


class MercadoPagoReal:
    def __init__(self, access_token: str | None = None):
        self.token = access_token or settings.MERCADO_PAGO_ACCESS_TOKEN

    # ------------------------------------------------------------------ #
    def _requisicao(self, metodo: str, caminho: str, corpo: dict | None = None) -> dict:
        dados = json.dumps(corpo).encode() if corpo is not None else None
        url = f"{API_BASE}{caminho}"
        if not url.startswith("https://api.mercadopago.com/"):
            raise ErroPagamento("Esquema/destino não permitido pela integração.")
        requisicao = urllib.request.Request(
            url,
            data=dados,
            method=metodo,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(  # nosec B310 - destino https fixo validado acima
                requisicao, timeout=15
            ) as resposta:
                return json.loads(resposta.read().decode())
        except Exception as erro:
            logger.exception("Erro na API do Mercado Pago (%s %s).", metodo, caminho)
            raise ErroPagamento(f"Falha na API do provedor: {erro}") from erro

    def criar_preferencia(self, pedido) -> tuple[str, str]:
        site = settings.SITE_URL.rstrip("/")
        itens = [
            {
                "title": item.produto_nome,
                "quantity": int(item.quantidade),
                "unit_price": float(item.preco_unitario),
                "currency_id": "BRL",
            }
            for item in pedido.itens.all()
        ]
        corpo = {
            "items": itens,
            "external_reference": pedido.numero,
            "back_urls": {
                "success": f"{site}{reverse('sales:pedido_token', args=[pedido.token_acesso])}",
                "pending": f"{site}{reverse('sales:pedido_token', args=[pedido.token_acesso])}",
                "failure": f"{site}{reverse('sales:pedido_token', args=[pedido.token_acesso])}",
            },
            "notification_url": (
                f"{site}{reverse('sales:webhook')}" if not settings.DEBUG else ""
            ),
        }
        resposta = self._requisicao("POST", "/checkout/preferences", corpo)
        init_point = resposta.get("init_point") or resposta.get(
            "sandbox_init_point", ""
        )
        return str(resposta.get("id")), init_point

    def consultar_pagamento(self, id_externo: str) -> dict:
        return self._requisicao("GET", f"/v1/payments/{id_externo}")


# --------------------------------------------------------------------------- #
# Validação de assinatura do webhook
# --------------------------------------------------------------------------- #


def validar_assinatura_webhook(headers, data_id: str) -> bool:
    """Valida 'x-signature' conforme documentação do Mercado Pago.

    Sem segredo configurado (dev/testes), aceita a chamada.
    """
    segredo = getattr(settings, "MERCADO_PAGO_WEBHOOK_SECRET", "")
    if not segredo:
        return True

    assinatura_header = headers.get("x-signature", "")
    request_id = headers.get("x-request-id", "")
    partes = dict(
        fragmento.split("=", 1)
        for fragmento in assinatura_header.split(";")
        if "=" in fragmento
    )
    ts = partes.get("ts", "")
    v1 = partes.get("v1", "")
    if not (ts and v1 and data_id):
        return False

    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    calculado = hmac.new(
        segredo.encode(), manifest.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(calculado, v1)


def extrair_data_id(url_query: str, payload: dict) -> str:
    """Obtém o id do recurso da notificação (body 'data.id' ou query string)."""
    if isinstance(payload, dict):
        data = payload.get("data") or {}
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
    parametros = urllib.parse.parse_qs(url_query)
    valores = parametros.get("data.id") or parametros.get("id")
    if valores:
        return str(valores[0])
    return ""
