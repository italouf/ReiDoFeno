# ADR-013 — Ledger de estoque imutável com delta assinado

**Status:** Aceito
**Data:** 2026-10-20
**Fase:** 2B
**Substitui parcialmente:** decisão implícita da Fase 1 de gravar `quantidade` absoluta

## Contexto

O estoque precisa ser reconstruível a partir de uma trilha imutável. O modelo
`MovimentoEstoque` guardava apenas `quantidade` absoluta; o sinal existia somente no
código que atualizava o saldo. Ajustes negativos ficavam indistinguíveis de positivos e
mutações via `QuerySet.update()`/SQL direto não eram barradas.

## Decisão

Adotar `delta` assinado como fonte de verdade do ledger, com `quantidade = abs(delta)`
mantida para compatibilidade de leitura. A imutabilidade é aplicada em três camadas:
modelo/serviço, QuerySet e trigger PostgreSQL. A correção de um lançamento passa a exigir
um movimento de compensação.

Transferências usam `transferencia_saida`/`transferencia_entrada` com `movimento_par`
recíproco. O vínculo é a única mutação permitida após a criação, e é feita por operação
interna que não altera valor, tipo, produto, unidade ou motivo.

A migração foi dividida para ser segura no PostgreSQL: schema em 0002, reservas em 0003,
quarentena/evidência em 0004, carga de `delta` em 0005 e constraints/trigger em 0006.
Nenhum `ALTER TABLE` ocorre após DML na mesma transação. `delta` entra com default
temporário 0; a 0005 só processa esse sentinela e falha com diagnóstico para movimento de
quantidade zero, em vez de inventar `0,01`. Sinais inferidos e baselines ficam registrados
em `ReconciliacaoEstoqueLegado`.

## Alternativas rejeitadas

1. **Quantidade absoluta com flag de sinal (`positivo=True`)**: dois campos para o mesmo
   fato, combinações inválidas possíveis e consultas mais complexas.
2. **Event sourcing completo (replay de eventos para saldo)**: mais poderoso, porém
   amplia o escopo para toda a camada de leitura e relatórios da fase.
3. **Append-only somente na aplicação**: não impede `UPDATE`/`DELETE` via SQL, que é
   exatamente um dos vetores auditados.

## Consequências

- Positivas: saldo auditável (`SUM(delta)`), ajustes com sinal preservado, defesa contra
  mutação direta no PostgreSQL, trilha compatível com relatórios existentes e evidência
  explícita de inferências/baselines.
- Negativas: correções exigem movimento de compensação; a migração de ajustes legados
  sem auditoria depende de heurística registrada; o trigger permite duas exceções
  estreitas (vínculo de par e SET NULL de usuário) e o `TRUNCATE` é bloqueado fora de
  bancos de teste que habilitam o GUC `stock.permitir_truncate`.
- Banco: trigger criada apenas em PostgreSQL (CI). SQLite mantém a proteção de
  aplicação e os testes de bypass.
