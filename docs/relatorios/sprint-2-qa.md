# Portão de Qualidade e Segurança — Fase 2 (Sprint 2)

Data: 2026-08-22 · Escopo: vitrine, carrinho, checkout, pedidos e pagamento.

## Resultados de QA

- **Testes unitários/integração**: 137 passed + 140 subtests (`reports/junit.xml`), cobertura **87.85%** (`reports/coverage.xml`).
- **E2E Playwright**: fluxo completo em Chromium (viewport mobile 390×844):
  vitrine → página do produto → carrinho (total recalculado) → checkout com CPF válido →
  pedido `aguardando_pagamento` → pagamento simulado aprovado → badge "Pago" →
  estoque baixado definitivamente (50→48, reserva zerada). Suíte: 2 passed.
- **Idempotência de webhook**: reenvio da mesma notificação não duplica baixa de estoque nem e-mail; evento bruto persistido nas duas ocorrências.
- **Isolamento**: cliente vê só os próprios pedidos (`MeusPedidosView`); vendedor só pedidos que criou (lista e detalhe 404 para alheio); cliente final recebe 403 na gestão.
- **Máquina de status**: transições válidas/inválidas cobertas; estados finais travados; falha permite reinício de pagamento.

## Resultados de Segurança

| Verificação | Resultado |
|---|---|
| Bandit (medium/high) | 0 achados após guarda de esquema + `nosec` justificado em `sales/payments.py` |
| pip-audit | Sem vulnerabilidades conhecidas |
| Webhook | Assinatura HMAC (`x-signature`) validada quando `MERCADOPAGO_WEBHOOK_SECRET` configurado; inválida → 403 sem alterar dados e sem gravar evento |
| CSRF | Checkout protegido; webhook `csrf_exempt` por design (autenticado por assinatura) |
| Cartão | Nenhum dado de cartão trafega/armazena (Checkout Pro no provedor) |
| Valores | Preço/total sempre recalculados no servidor; IDs de pedido públicos por token UUID (não enumeráveis) |
| PII em logs | Logger do webhook registra apenas referência externa |

## Checklist de privacidade no checkout

- [x] Coleta mínima: nome, documento, contato e endereço somente quando entrega
- [x] Documento armazenado normalizado (dígitos); exibição formatada na tela
- [x] E-mail usado apenas para transacionais do pedido
- [x] Logs sem documento/telefone/endereço
