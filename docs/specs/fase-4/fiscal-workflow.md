# FISCAL-WORKFLOW — Fila e status da NF-e assistida

**Fase:** 4
**Depende de:** ADR-006.

## Objetivo

Dar visibilidade operacional às notas fiscais manuais e permitir confirmar a
autorização no IOB ou cancelar com justificativa.

## Listagem

`GET /fiscal/notas/` (Administrador, Gestor, Emissor Fiscal).

- Mostra pedido, cliente, número, série, status, data de emissão e PDF.
- Filtro `?status=` aceita `pendente`, `anexada`, `autorizada`, `erro` e
  `cancelada`; valor inválido retorna 400.
- Ordenação: mais recentes primeiro.

## Autorizar

`POST /fiscal/notas/<pk>/autorizar/`

1. Trava a nota.
2. Nota `cancelada` não pode ser autorizada (400).
3. Nota já `autorizada` é idempotente (302, sem novo log).
4. Exige `numero` e `chave_acesso` com 44 dígitos (400 caso contrário).
5. Muda para `autorizada`, valida e grava `fiscal.nota_autorizada_manual`
   com antes/depois.

## Cancelar

`POST /fiscal/notas/<pk>/cancelar/` com `justificativa`.

- Exige justificativa não vazia (400).
- Usa `fiscal.services.cancelar_nota_fiscal` (somente autorizada; auditado
  como `fiscal.nota_cancelada`).
- Nota já cancelada é idempotente.

## Permissões

- Vendedor não lista nem executa ações (403).
- Superusuário passa.
