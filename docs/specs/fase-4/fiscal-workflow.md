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
5. Exige pedido elegível (pago, conciliado, não cancelado) e emissão
   automática não pode estar em andamento.
6. Muda para `autorizada`, preenche `data_emissao` quando ausente, invalida
   claims antigos e grava `fiscal.nota_autorizada_manual` com antes/depois.
7. Série, PDF, número e chave de nota já autorizada são imutáveis por esta
   rota; correção exige fluxo formal com evidência.

## Cancelar

`POST /fiscal/notas/<pk>/cancelar/` com `justificativa`.

- Exige justificativa não vazia (400).
- Usa `fiscal.services.cancelar_nota_fiscal` (somente autorizada; auditado
  como `fiscal.nota_cancelada`).
- Nota já cancelada é idempotente.

## Permissões

- Vendedor não lista nem executa ações (403).
- Superusuário passa.
