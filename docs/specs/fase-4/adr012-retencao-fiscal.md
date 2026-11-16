# ADR-012 — Retenção de dados fiscais

**Fase:** 4
**Relaciona-se a:** ADR-006, LGPD.

## Regra

- `NotaFiscal.retido_ate = data_emissao + 5 anos` (calendário, não 5×365
  dias).
- O snapshot fiscal é imutável após o primeiro preenchimento.
- Anonimização do cliente não altera o snapshot.
- A limpeza é feita apenas por comando operacional, com `--dry-run` e
  auditoria por nota removida.
- Notas com `retido_ate` nulo (sem data de emissão) ficam fora da limpeza
  automática.

## Fluxo LGPD

1. Cliente solicita exclusão.
2. Se há notas fiscais: anonimiza cadastro, preserva pedidos e notas,
   registra `cliente_anonimizado_com_notas`.
3. Se há apenas pedidos: anonimiza e registra
   `cliente_anonimizado_com_pedidos`.
4. Sem pedidos/notas: exclui o cadastro.

## Operação

```bash
python manage.py limpar_notas_expiradas --dry-run
python manage.py limpar_notas_expiradas
```

O comando remove apenas `retido_ate < hoje`. Cada remoção grava
`LogAuditoria` com número, chave, pedido e data de retenção.
