# Portão de Qualidade e Segurança — Fase 0 (Sprint 0)

Data: 2026-08-22 · Escopo: fundação do projeto Django (login, papéis, healthcheck, CI).

## Resultados de QA

- **Testes**: 16 passed, 3 subtests passed (`pytest`, JUnit XML em `reports/junit.xml`).
- **Cobertura** (`reports/coverage.xml`): 75% geral na fundação; apps de domínio ainda vazios por design nesta fase.
- **Lint**: `ruff check .` sem erros.
- **Segurança estática** (Bandit): 0 medium/high; 8 low — todos senhas fictícias dentro de `accounts/tests/test_auth.py` (fixtures de teste, não segredos). Aceito e documentado.

## Checklist de segurança da Sprint 0

| Item | Status | Evidência |
|---|---|---|
| Login com credenciais válidas/inválidas | ✅ | `accounts/tests/test_auth.py` |
| Mensagem de login não revela existência do usuário | ✅ | mensagem genérica única |
| Bloqueio após tentativas repetidas | ✅ | django-axes, HTTP 429 após limite |
| Recuperação de senha sem enumeração | ✅ | resposta idêntica p/ e-mail inexistente |
| Usuário sem permissão não acessa área interna | ✅ | matriz parametrizada (`core/tests/test_access_matrix.py`) |
| Cliente não acessa painel interno | ✅ | HTTP 403 |
| Gestor acessa estoque, mas não administra usuários | ✅ parcial | estoque chega na Fase 1; `/admin/` já negado ao gestor |
| Vendedor não acessa estoque administrativo | ⏳ | verificação completa na Fase 1 (URLs ainda inexistentes) |
| CSRF em formulários | ✅ | middleware ativo + `{% csrf_token %}` nos templates |
| Hash forte de senha | ✅ | Argon2 como hasher primário |
| Validadores de senha ativos | ✅ | 4 validadores padrão Django |
| `SECRET_KEY` fora do repositório | ✅ | env var obrigatória em produção |
| Cookies seguros em produção | ✅ | `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` em `production.py` |
| pip-audit sem vulnerabilidades | ✅ | "No known vulnerabilities found" (requirements.txt) |
| `/healthz/` responde 200 | ✅ | teste + client manual |
| CI (lint/testes/bandit/pip-audit) | ✅ | `.github/workflows/ci.yml` |

## Pendências para próximas fases

- Completar itens ⏳ quando as URLs de estoque existirem (Fase 1).
- OWASP ZAP baseline na Fase 4.
