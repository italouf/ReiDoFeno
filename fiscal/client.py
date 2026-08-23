"""Adapter do ERP fiscal (Bling) com implementação fake para dev/testes."""
import logging
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.bling.com.br/Api/v3"


class ErroFiscal(Exception):
    """Falha de comunicação ou rejeição da API fiscal."""


def obter_client():
    if getattr(settings, "BLING_FAKE", False):
        return BlingFake()
    if not settings.BLING_API_KEY:
        raise ErroFiscal("BLING_API_KEY não configurada para produção.")
    return BlingClient()


class BlingClient:
    """Cliente real da API v3 do Bling (NFe)."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.BLING_API_KEY

    def criar_nfe(self, pedido) -> dict:
        """Envia o pedido e retorna {'numero','chave','link'}."""
        corpo = {
            "externalId": pedido.numero,
            "numero": pedido.numero,
            "contato": {"nome": pedido.cliente.nome,
                        "tipoPessoa": pedido.cliente.tipo_pessoa,
                        "numeroDocumento": pedido.cliente.documento},
            "itens": [
                {
                    "descricao": item.produto_nome,
                    "quantidade": float(item.quantidade),
                    "valorUnitario": float(item.preco_unitario),
                    "ncm": item.produto.ncm or "5301.00.00",
                    "unidade": "UN",
                }
                for item in pedido.itens.select_related("produto")
            ],
        }
        dados = self._requisicao("POST", "/nfe", corpo)
        return {
            "numero": str(dados.get("numero", "")),
            "chave": str(dados.get("chaveAcesso", "")),
            "link": str(dados.get("linkDanfe", "")),
        }

    def _requisicao(self, metodo, caminho, corpo=None):
        import json

        payload = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(
            f"{API_BASE}{caminho}",
            data=payload,
            method=metodo,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resposta:  # nosec B310 - https fixo
                return json.loads(resposta.read().decode())
        except Exception as erro:
            logger.exception("Erro na API do Bling (%s %s).", metodo, caminho)
            raise ErroFiscal(f"Falha na API fiscal: {erro}") from erro


class BlingFake:
    """Determinístico para dev/testes.

    Falha quando o nome do cliente contém 'ERRO' (útil para simular rejeição).
    """

    def criar_nfe(self, pedido) -> dict:
        if "ERRO" in pedido.cliente.nome.upper():
            raise ErroFiscal("Rejeitado pelo SEFAZ (simulado).")
        return {
            "numero": f"9000{pedido.pk}",
            "chave": f"292608{pedido.numero}0001000000001",
            "link": f"https://fake.bling.com.br/danfe/{pedido.numero}",
        }

    def consultar_status(self, nota) -> dict:
        return {"status": nota.status}
