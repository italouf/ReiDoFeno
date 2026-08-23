# Portão de Qualidade e Segurança — Fase 1 (Sprint 1)

Data: 2026-08-22 · Escopo: cadastros, estoque por unidade, custos e clientes.

## Resultados de QA

- **Testes**: 86 passed + 138 subtests (`reports/junit.xml`).
  - Modelos e validadores de CPF/CNPJ.
  - Serviço de estoque: entrada/saída/ajuste/transferência, reserva, imutabilidade do ledger, concorrência (threads).
  - CRUDs com matriz de permissões por perfil em todas as URLs diretas (119 subtests na bateria consolidada).
  - Auditoria: antes/depois com IP; registros imutáveis.
  - Painel inicial com dados reais e estados vazios.
- **Cobertura** (`reports/coverage.xml`): **91.02%** (meta ≥ 80%).

## Resultados de Segurança

| Verificação | Resultado |
|---|---|
| Bandit (medium/high) | 0 achados medium/high |
| pip-audit | Sem vulnerabilidades conhecidas |
| Semgrep | Executa no job `semgrep` do CI (não suportado localmente no Windows); regras `p/default`, ERROR bloqueia pipeline |
| Autorização por perfil | Matriz consolidada verde (cliente/vendedor/gestor/admin × todas as URLs) |
| XSS | Escapado por templates Django (sem `|safe`) |
| SQL injection | Exclusivamente ORM; nenhuma query raw |
| Stack trace em produção | `DEBUG=False` + templates de erro padrão |

## Checklist de segurança de CRUD/estoque

- [x] Entrada validada em todos os formulários (limites de campo, DecimalField com min/max)
- [x] Saldo negativo impossível (constraint de banco + serviço transacional)
- [x] Movimentos append-only (save/delete bloqueados no modelo)
- [x] Ajuste manual exige motivo (formulário + serviço)
- [x] Transferência gera par vinculado auditável
- [x] Alterações críticas geram LogAuditoria (antes/depois/IP/usuário)
- [x] Vendedor/cliente sem acesso a estoque administrativo, custos ou gestão de clientes
