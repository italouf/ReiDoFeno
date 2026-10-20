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

## Alternativas rejeitadas

1. **Quantidade absoluta com flag de sinal (`positivo=True`)**: dois campos para o mesmo
   fato, combinações inválidas possíveis e consultas mais complexas.
2. **Event sourcing completo (replay de eventos para saldo)**: mais poderoso, porém
   amplia o escopo para toda a camada de leitura e relatórios da fase.
3. **Append-only somente na aplicação**: não impede `UPDATE`/`DELETE` via SQL, que é
   exatamente um dos vetores auditados.

## Consequências

- Positivas: saldo auditável (`SUM(delta)`), ajustes com sinal preservado, defesa contra
  mutação direta no PostgreSQL, trilha compatível com relatórios existentes.
- Negativas: correções exigem movimento de compensação; a migração de ajustes legados
  sem auditoria depende de heurística e pode gerar um lançamento de reconciliação;
  o trigger permite duas exceções estreitas (vínculo de par e SET NULL de usuário).
- Banco: trigger criada apenas em PostgreSQL (CI). SQLite mantém a proteção de
  aplicação e os testes de bypass.
