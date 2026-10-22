# Fase 2B — Relatório de conclusão técnica

**Data do encerramento técnico:** 22/10/2026
**Branch:** `fase-2b-integridade-estoque`
**SHA de código validado:** `5ae6bfc0b3ab1fca4789295803aadd07efd0d16b`
**CI do SHA validado:** [run 39774481256](https://github.com/italouf/ReiDoFeno/actions/runs/39774481256)
**Base funcional:** `main` em `f3e3353` (merge da Fase 2A)
**Decisão:** gate técnico da Fase 2B **aprovado no escopo e caminhos de atualização
suportados**. Pronto para revisão por PR e transição ao desenvolvimento da Fase 2C.
Produção permanece sujeita aos gates operacionais descritos no fim deste relatório.

> Este SHA é o código auditado. Um commit posterior apenas documental tem SHA próprio
> e não herda automaticamente a CI deste relatório.

## 1. Objetivo, escopo e critério de aceite

A Fase 2B tinha como objetivo tornar o estoque confiável e o ledger reconstruível,
preservando a Fase 2A. O aceite exigia:

- saldo físico, bloqueios/reservas e ledger reconciliáveis;
- baixa por pedido sem dupla contagem, com evidência atribuível;
- obrigações persistentes bloqueando avanço até cumprimento real;
- resolução manual com ator, justificativa, autorização, atomicidade e auditoria;
- upgrades de bases suportadas sem inventar nem apagar saídas históricas;
- ledger imutável contra mutações ordinárias e atribuição de evidência protegida;
- entregas financeiras, CNPJ alfanumérico, titularidade/LGPD e atacado sem regressão.

O gate foi avaliado pelos testes, migrations, CI e reproduções independentes. Não é
uma certificação de ausência universal de vulnerabilidades nem substitui homologação
operacional.

## 2. Entregas originais

| Entrega | Comportamento final | Código/migrations principais | Testes/evidência |
|---|---|---|---|
| **STO-01** — ledger imutável e reconstruível | `delta` assinado é a fonte de verdade; `quantidade = abs(delta)`; escrita nova passa por serviço; mutações existentes são bloqueadas por instância, QuerySet, bulk e trigger PostgreSQL. Compensação é o caminho de correção. | `stock/models.py`, `stock/services.py`; `stock/0002`–`0006`, `stock/0008`, `stock/0010` | `stock/tests/test_sto01_ledger_imutavel.py`, testes de concorrência; CI PostgreSQL |
| **ADR-003** — reservas vinculadas | Reserva identifica pedido/produto/unidade; consumo/liberação idempotentes; over-reserva não baixa; operações de A não liberam B; bloqueios sem dono vão para quarentena explícita. | `stock.ReservaEstoque`, `stock.BloqueioLegado`; `stock/0003`, `stock/0004`; integração em `sales/services.py` | `test_adr003_*`, `test_b01_*`, `test_b03_contrato_reserva.py`, concorrência PostgreSQL |
| **DAT-01** — constraints financeiras | Totais e quantidades não-negativos; `total = subtotal + frete`; quantidade positiva; valores finitos; NaN/Infinity rejeitados no serviço e no banco. | `sales/models.py`; `sales/0007`, `sales/0008` | `test_dat01_check_constraints.py`, testes PostgreSQL de finitude |
| **CUS-01** — CNPJ alfanumérico | Normalização preserva `A-Z` e `0-9`, converte para maiúsculas e valida o DV oficial; CPF continua numérico; PII alfanumérica é mascarada. | `customers/validators.py`, `customers/models.py`, fiscal e filtro de logs; `customers/0004`/`0005` | `test_cus01_cnpj_alfanumerico.py`, `test_hardening.py`, `test_validators.py` |
| **ADR-005** — titularidade/LGPD | `meus-pedidos` exige vínculo verificado e identidade do pedido; visitante não aparece; exportação sem vínculo retorna 403; não há vazamento entre clientes. | `sales/views.py`, `privacy/services.py`, `privacy/views.py` | `test_adr005_titularidade.py`, `test_checkout_privacidade.py` |
| **Atacado > 50 fardos** | Cliente ATACADO, vínculo comprovado ou vendedor interno, produto em fardo, quantidade estritamente > 50 e preço preenchido; preço congelado no item; 50 usa preço-base. | `catalog.Produto.preco_atacado`; `catalog/0002`; `sales/pricing.py`, checkout | `test_regra_atacado.py`, `test_carrinho.py`; **aceite comercial ainda separado** |

## 3. Rastreabilidade dos achados

| Grupo | Status final | Observação/evidência |
|---|---|---|
| **B01–B05** | Corrigido/testado | Fallback sem dono removido; migração histórica segmentada; contrato de reserva; seed via ledger; evidências/quarentena. |
| **H02–H06** | Corrigido/testado | Ordem de locks, defesa do ledger, PII, finitude e cotação compartilhada. |
| **R01–R07** | Corrigido/testado | Obrigação persistente, locks, seed, reserva após baixa, quarentena, limpeza atômica e finitude. |
| **T01–T03** | Corrigido/testado | Backfill por evidência; resolvedor com vínculo/ator/financeiro/reservas; ator persistido e rollback. |
| **U01** | Corrigido/testado | Reparo transacional por obrigação, com lock, releitura e auditoria antes/depois. |
| **U02** | Corrigido/testado | FK de atribuição imutável; trigger inclui `obrigacao_id`; `PROTECT`; teste SQL. |
| **U03** | Corrigido/testado | `tipo_pendencia` distingue falta/ambígua/excesso; resolvedor recusa decisões incidentais; conciliação explícita. |
| **U04** | Limitação de suporte documentada | Base povoada exatamente na `sales/0001` com separação + pagamento aprovado não tem atualização automática garantida. Não é universalmente suportada. |
| **C01** | Corrigido/testado | `AlocacaoEvidenciaEstoque` com unicidade por movimento; alocação transacional; conversão/diagnóstico de JSON legado; concorrência e CLI cobertas. |
| **I1–I4** | Corrigido/testado | Finitude, cancelamento, limites do GUC/trigger e evidência de baseline. |
| **Minors anteriores** | Não promovidos automaticamente | Permanecem nos seus estados; não foram usados como novos bloqueadores sem reprodução material. |

## 4. Validação por origem/ambiente

| Origem | Ambiente | Resultado | Limites |
|---|---|---|---|
| Agente, suíte integral | SQLite | 501 passed, 15 skipped, 241 subtests | Skips PostgreSQL/cache esperados no SQLite |
| Agente, suíte integral | PostgreSQL 15.8 local + cache ausente | 515 passed, 1 skipped, 241 subtests | O skip é o teste de cache Redis; não é CI |
| Auditoria independente | PostgreSQL 16.2 + Redis 7.4.2 | 516 passed, zero skips, 241 subtests | Ambiente e harness próprios; não é a CI |
| Auditoria independente | SQLite | 501 passed, 15 skipped, 241 subtests | Mesmo recorte de skips |
| Regressões externas | Auditoria independente | 21 passed | Inclui T/U/C01, CLI, concorrência, SQL e upgrades |
| Migração vazia/histórica | PostgreSQL local/CI | Vazia até HEAD e nove cenários históricos passaram | U04 continua fora do suporte automático |
| Upgrades reais | 817d1e8→HEAD e b1cc7d2→HEAD | Passaram com dados gerados pelos serviços antigos, JSON consistente e conflitante | Pontos de partida suportados; não 0001 povoada |
| CI do código | PostgreSQL 15 + Redis do workflow | Run `39774481256` verde: tests, check de produção, migração histórica, lint, security e semgrep | A CI não publicou uma contagem que deva ser confundida com 516/515 |

**Comandos reproduzíveis principais:**

```bash
pytest -q
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py validar_migracao_legado --criar
python manage.py migrate --noinput
python manage.py validar_migracao_legado --verificar
python manage.py reconstruir_obrigacoes_estoque
```

**Avisos e ferramentas:** SQLite/PostgreSQL emitiram avisos conhecidos de
`URLField` e datetime sem timezone. Uma execução intermediária teve aviso de teardown
por conexão remanescente; a execução independente final não o apresentou. Ruff,
Django check, `makemigrations --check` e pip-audit ficaram limpos. Bandit `-ll` não
encontrou medium/high no escopo, mas não revisou individualmente 174 alertas low. O
Semgrep comunitário (`--config auto`) é tolerante a falhas no workflow; o job verde não
é um gate estrito de todas as regras. Cobertura independente: `stock/services.py`
94,61%, `sales/services.py` 84,51%, total 85,31%; migrations são omitidas do recorte e
cobertura não foi usada como substituto das invariantes.

## 5. Decisão do gate

**Fase 2B tecnicamente aprovada no escopo e caminhos de atualização suportados**, com
as ressalvas abaixo. Há evidência de CI no SHA `5ae6bfc` e regressões independentes
para as invariantes centrais. A próxima etapa é revisão por PR e desenvolvimento da
Fase 2C; não há autorização implícita para merge, deploy, alteração de produção,
credenciais ou Neon.

## 6. Pendências e limites remanescentes

| Pendência | Impacto/estado | Responsável/momento |
|---|---|---|
| **U04 — base povoada na `sales/0001`** | Atualização automática não garantida; exige procedimento DBA/importação específico, não validado nesta tarefa. | Responsável não informado; antes de qualquer atualização desse tipo. |
| **Roles runtime/migration e ownership** | Permissões efetivas de produção não inspecionadas; CI com role de teste não prova a configuração real. | Operação/DBA; antes do go-live. |
| **Backup/restore** | Procedimento documentado, mas restore não foi executado nesta tarefa; não há evidência nova em `docs/relatorios/backup-restore.md`. | Operação; antes do go-live. |
| **Atacado > 50 fardos** | Implementação e testes técnicos concluídos; confirmação comercial da regra permanece pendente. | Operação/comercial; decisão de negócio. |
| **Neon QA `twilight-silence-34012623`** | Mantido como QA temporário; não foi acessado nesta tarefa. Finalidade QA; responsável não informado; retenção/exclusão exige decisão operacional autorizada. | Operação; decisão separada do gate técnico. |
| **Minors anteriores** | Não reabertos por falta de reprodução material; permanecem registrados nos documentos de origem. | Conforme priorização futura. |

**Limites de ambiente:** o PostgreSQL local do agente foi 15.8; a auditoria independente
usou 16.2; a CI usa PostgreSQL 15 conforme o workflow. Os números não são intercambiáveis.
Nenhum restore, alteração de produção ou exclusão no Neon faz parte deste encerramento.

## 7. Fontes canônicas

- [Spec consolidado](../specs/fase-2b-spec.md)
- [Remediação e matriz de achados](../specs/fase-2b-remediation.md)
- [ADR-003 — reservas](../adrs/ADR-003-reservas-vinculadas.md)
- [ADR-013 — ledger imutável](../adrs/ADR-013-ledger-imutavel.md)
- [ADR-014 — CNPJ alfanumérico](../adrs/ADR-014-cnpj-alfanumerico.md)
- [ADR-015 — obrigação, evidência e alocação](../adrs/ADR-015-obrigacao-estoque.md)
- [Runbook operacional](../runbook.md)
- [CHANGELOG](../../CHANGELOG.md)
- [CI do código validado](https://github.com/italouf/ReiDoFeno/actions/runs/39774481256)

## 8. Rascunho de PR

**Título:** `Fase 2B: integridade financeira, estoque e rastreabilidade`

**Descrição sugerida:**

> Consolida a Fase 2B com ledger assinado e imutável, reservas por pedido,
> obrigações de baixa, evidência histórica atribuível, alocação global de
> movimentos conciliados, constraints financeiras, CNPJ alfanumérico, titularidade
> LGPD e regra técnica de atacado.
>
> **Comportamento final:** baixas não são inferidas por status financeiro; uma
> saída não pode cumprir dois pedidos; conciliação exige ator/justificativa e não
> cria movimento; a reconstrução é idempotente, transacional e distingue falta,
> ambiguidade e excesso.
>
> **Validação:** CI do SHA `5ae6bfc` (`39774481256`) verde; suíte independente
> PostgreSQL 16.2 + Redis com 516 passed/zero skips e SQLite 501/15; 21 regressões
> externas; upgrades 817d1e8→HEAD e b1cc7d2→HEAD.
>
> **Limites:** base povoada exatamente na `sales/0001` com separação + pagamento
> aprovado não tem atualização automática garantida (U04); roles/ownership,
> backup/restore e homologação de produção não foram verificados; confirmação
> comercial do atacado segue pendente.
>
> Não faz merge/deploy; revisão por PR é o próximo passo.
