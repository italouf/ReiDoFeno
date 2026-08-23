# Portão de Qualidade e Segurança — Fase 3 (Sprint 3)

Data: 2026-08-22 · Escopo: fiscal (Bling), painel completo, métricas do vendedor, avisos e recompra.

## Resultados de QA

- **Testes**: 156 passed + 140 subtests (`reports/junit.xml`), cobertura em `reports/coverage.xml`.
- **Fiscal**: elegível emitido com nº/chave/link; documento inválido bloqueado com aviso; erro de API gera aviso, pedido permanece "pago" e reprocessamento autoriza; nota autorizada nunca duplica; fallback manual auditável.
- **Painel**: vendas/despesas/lucro por período; cancelados fora das métricas; top produtos; aguardando pagamento.
- **Métricas do vendedor**: isoladas por usuário (vendedor A não vê números de B); cancelados fora das vendas totais; interações registradas e listadas na ficha do cliente.

## Resultados de Segurança

| Verificação | Resultado |
|---|---|
| Bandit (medium/high) | 0 achados |
| pip-audit | Sem vulnerabilidades conhecidas |
| Credenciais fiscais | Exclusivamente env vars (`BLING_API_KEY`); token fora dos logs |
| XML/DANFE | Acesso restrito a administrador/gestor (fallback manual e links) |
| Painel × perfis | Vendedor não acessa central de avisos financeira/fiscal nem custos |
| LGPD no painel | Métricas agregadas; sem CPF/CNPJ em texto puro nas telas de indicadores |

## Checklist LGPD dos dados exibidos no painel

- [x] Indicadores agregados (sem lista de documentos)
- [x] Nome do cliente apenas em contextos operacionais legítimos (avisos/pedidos)
- [x] Métricas do vendedor limitadas aos próprios dados
- [x] Avisos sem dados sensíveis além do necessário à operação
