# E2E — Pagamento manual + fiscal assistido em staging

**Fase:** 4
**Estado local:** teste automatizado passando em SQLite/live_server.
**Estado staging:** pendente de execução na VPS e de aceite dos responsáveis.

## Pré-requisitos

- Base com `seed_groups` aplicado.
- Usuários/grupos: `Vendedor`, `Financeiro`, `Emissor Fiscal`.
- Produto com estoque na unidade usada pelo checkout.
- Playwright instalado (`playwright install chromium`).
- PDF de teste (qualquer arquivo PDF válido).

## Execução local

```bash
python -m pytest tests_e2e/test_fluxo_pagamento_manual.py \
  -q -o faulthandler_timeout=120
```

O teste cobre:

1. vendedor cria pedido pela loja;
2. vendedor registra PIX manual com comprovante;
3. financeiro concilia;
4. emissor anexa PDF e autoriza a NF-e;
5. banco confirma pagamento conciliado, estoque baixado, nota autorizada,
   snapshot fiscal e auditoria.

## Execução em staging

1. Criar os três usuários e associar aos grupos.
2. Criar produto/estoque de teste.
3. Exportar `E2E_BASE_URL` e apontar o teste para o staging (o teste atual usa
   `live_server`; para staging, criar um teste/script com `base_url` externo ou
   executar o roteiro manual abaixo).
4. Roteiro manual equivalente:
   - login vendedor → pedido → pagamento manual PIX com comprovante;
   - login financeiro → `/gestao/conciliacao/` → conciliar;
   - login emissor → `/fiscal/notas/` → anexar PDF → autorizar;
   - conferir `/gestao/pedidos/<pk>/` e `/fiscal/notas/`.

## Aceite humano (pendente)

- [ ] Nilton valida conciliação financeira.
- [ ] Neto valida conciliação financeira.
- [ ] Caio valida emissão de NF-e manual.
- [ ] Fluxo completo validado em staging.

Sem essas evidências, a fase não deve ser declarada operacionalmente aceita.
