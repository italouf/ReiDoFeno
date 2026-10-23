# PR final da Fase 2C — pronta para revisão

Não publicar sem autorização. A branch já está publicada; a abertura da PR
depende da governança do projeto.

## Título

`fix(fiscal): conclui autoridade e deduplicação fiscal da Fase 2C`

## Corpo

### Problema resolvido

Esta entrega consolida as correções fiscais e financeiras da Fase 2C:

- L01: conclusão de tentativa fiscal passou a exigir o token UUID da
  tentativa; manual, cancelamento, terminalidade e resultados obsoletos são
  coordenados sob lock.
- L02: avisos agregados e avisos por evento ganharam identidades distintas;
  retries não quebram mais por `MultipleObjectsReturned`.
- L03: a deduplicação de eventos externos sobrevive à rotação da projeção de
  20 eventos e continua idempotente após releitura/nova transação.
- N01–N03, R01–R05 e A01–A09 permanecem preservados, incluindo CMV
  comprovado em conciliação, frete separado e ausência de frete negativo.

### Comportamento final

- Claim fiscal com UUID, lease curto e comparação atômica; chamada externa
  fora dos locks.
- Manual bloqueado durante lease ativo; após expiração pode assumir o claim,
  invalida a tentativa antiga e audita a assunção.
- Documento autorizado/cancelado é terminal para tentativa antiga.
- Respostas externas tardias ficam em `resultado_externo`, com aviso e
  auditoria; não reabrem pedido, não repetem estoque/estorno e não inventam
  cancelamento externo.
- `Aviso.evento_chave` separa agregado e evento; eventos distintos continuam
  visíveis, e avisos legados são preservados.
- A identidade de evento é durável; JSON mantém os 20 eventos recentes, mas
  não é a memória única de deduplicação.

### Migrações

- `fiscal/0006_tentativa_emissao.py`: campos de tentativa e evidência externa.
- `analytics/0004_aviso_evento_chave.py`: identidade de aviso/evento,
  backfill legado e constraint condicional.
- Migrações aditivas; nenhuma migração compartilhada foi reescrita.

### Evidências

- SHA publicado/auditado:
  `2a7a30096f7d3c00b7bba9b5bd7dd12e78894a70`.
- CI `39953967926`: success, incluindo PostgreSQL 15 + Redis, check de
  produção e migração histórica.
- Reauditoria independente: Gate T aprovado com observações não bloqueantes;
  L02/L03 aprovados nos contraexemplos.
- Execução local do agente: SQLite 655 passed, 24 skipped, 240 subtests;
  cobertura 86,39%; Node 2/2; Ruff/check/migrações/Bandit/pip-audit limpos.
- Reauditoria independente: PostgreSQL 16.2 678 passed, 1 skipped; backfill
  sintético com cinco avisos preservados.

### Gates

| Gate | Situação |
|---|---|
| T — técnico | Aprovado com observações não bloqueantes |
| C — remoto | Aprovado no SHA `2a7a300`, CI `39953967926` |
| H — humano | **Pendente**; ficha em `docs/operacao/fase-2c-aceite.md` |

### Observações não bloqueantes

- Limpeza de conexão remanescente no teardown PostgreSQL.
- Depreciações de `URLField` para Django 6.
- Unicidade concorrente forte de avisos agregados não é garantida por
  constraint nesta fase; a busca tolera múltiplos registros.
- Conflitos fiscais externos continuam exigindo conciliação humana.
- Backlog formal: `docs/operacao/fase-2c-backlog.md`.

### Fora de escopo

Sem merge, deploy, emissão/cancelamento fiscal real, reembolso real, acesso a
base real ou SEFAZ/Bling real. O Gate H não é presumido.
