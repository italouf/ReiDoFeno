# Backlog não bloqueante — Fase 2C

Itens registrados pela reauditoria independente no SHA
`2a7a30096f7d3c00b7bba9b5bd7dd12e78894a70`. Nenhum bloqueia o Gate H ou a
homologação.

| ID | Item | Impacto | Encaminhamento |
|---|---|---|---|
| P2-01 | Conexão remanescente no teardown da suíte PostgreSQL | Warning de limpeza; o teste funcional termina aprovado | Fechar conexões de threads em `finally` e revisar o teardown do banco de teste |
| P2-02 | Depreciações de `URLField` para Django 6 | Warning de compatibilidade futura | Migrar para `assume_scheme="https"` ou `FORMS_URLFIELD_ASSUME_HTTPS` em manutenção |
| P2-03 | Unicidade concorrente forte de avisos agregados | A busca tolera múltiplos agregados e não falha; não há constraint para agregados | Alinhar documentação e, se necessário, avaliar constraint/transação própria em tarefa futura |
| P2-04 | Status documental da spec L02/L03 | Risco de o documento parecer ainda em correção | Atualizado nesta rodada para “verificado”; este backlog mantém o histórico |

## Regra

Estes itens não devem ser usados para reabrir L01/L02/L03 nem para adiar o
aceite. Se qualquer um evoluir para falha funcional reproduzível, ele deve
voltar ao fluxo normal de correção com novo teste e novo SHA.
