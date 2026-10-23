# Fase 3 — correção de aceite (F3-01, F3-02, F3-03)

## Contexto

O SHA auditado `07d83de` tem a infraestrutura implementada, mas o job `docker`
falhou no gate de Caddy e os smokes posteriores não executaram. Além disso, a
classe de settings de produção herda variáveis de staging do Compose. Esta
correção não amplia o escopo para VPS/DNS/CD; ela fecha o aceite local/CI e
documenta os limites reais.

## Matriz

| ID | Causa | Contrato | Correção | Teste/evidência |
|---|---|---|---|---|
| F3-01 | Workflow monta `infra/caddy/transport.caddy`, arquivo real em `infra/transport.caddy` | Gate de Caddy precisa resolver arquivos existentes e validar runtime e dev | Usar `--mount` com `source=$PWD/infra/...`, `test -f` antes e duas validações | Teste que extrai e resolve os caminhos do YAML; CI verde |
| F3-02 | `os.environ.copy()` herda staging/fakes/TLS off do `.env.docker` | Cenários de produção devem partir de baseline estrito determinístico | `_executar` monta ambiente explícito, remove herança de contrato e aplica overrides | Classe passa com pai limpo e com pai staging; suíte no container dev |
| F3-03 | Smoke só verifica `/healthz/` e imprime `ps`; não prova stack, IP, cron nem persistência | Aceite executável de saúde, página, estático, SEC-03, cron e volumes | Endpoint de diagnóstico gated por staging, script de smoke e CI com cron/peristência | Script real + logs/limpeza no CI; pendente de execução local sem Docker |

## F3-01 — caminho e gate Caddy

O workflow passa a validar duas variantes:

- runtime: `infra/transport.caddy` (PROXY protocol v1);
- dev: `infra/transport-dev.caddy` (transporte HTTP padrão).

A montagem usa `--mount type=bind,source=...,target=...,readonly`, que falha de
forma explícita quando a origem não existe, em vez de `-v` criar diretório.
Um teste lê o YAML do workflow, extrai cada `source=$PWD/...` do passo e exige
que o caminho seja um arquivo real no repositório.

## F3-02 — ambiente determinístico

`core/tests/test_settings_production.py` deixa de copiar o ambiente inteiro.
Cada subprocesso recebe:

- allowlist mínima do sistema (`PATH`, `SYSTEMROOT`, `TEMP`, `HOME`, etc.);
- baseline de produção estrita (`DJANGO_ENVIRONMENT=production`,
  `DATABASE_SSL_REQUIRE=True`, fakes `False`, collector/live mode válidos);
- somente então os overrides explícitos do cenário.

O teste de staging define `DJANGO_ENVIRONMENT=staging` e
`DATABASE_SSL_REQUIRE=False` explicitamente. Testes adicionais contaminam o
ambiente pai com flags de staging e provam que o baseline de produção continua
valendo.

## F3-03 — aceite integrado

`SMOKE_DIAGNOSTICS` (default `False`; só habilitado em staging) expõe
`/healthz/ip/` retornando apenas `REMOTE_ADDR`, para provar SEC-03. O endpoint
fica 404 em produção estrita.

`infra/docker-compose.smoke.yml` habilita o diagnóstico apenas no cenário
descartável. `infra/scripts/smoke-stack.sh`:

1. sobe `caddy`, `web`, `db`, `redis` e `cron`;
2. exige healthcheck `healthy` de todos;
3. acessa `/`, um CSS com hash e `/healthz/` via HTTPS/Caddy;
4. compara o IP visto por `web` e `cron` com o IP real dos containers e envia
   `X-Forwarded-For` forjado;
5. cria dados sintéticos, executa as três rotinas do cron e confere o PID 1;
6. grava um arquivo em `/app/media`, recria os containers sem remover volumes e
   confere dados + arquivo;
7. limpa somente o projeto descartável.

## Fora de escopo (documentado)

- TLS do PostgreSQL interno do Compose; produção estrita continua exigindo TLS
  e não é considerada provisionada.
- `APP_DOMAIN` e `STAGING_DOMAIN` no mesmo Caddy apontam para o mesmo `web`,
  banco e integrações: são aliases, não ambientes isolados.
- CD, DNS, Let's Encrypt público, VPS e deploy automático.
- Pinning por digest das imagens base fica como melhoria de reprodutibilidade.

## Critério de fechamento desta correção

- F3-01 e F3-02 com regressões locais verdes.
- F3-03 implementado e executável no CI, com pendência explícita se não houver
  Docker local.
- Nenhuma alegação de CI verde, staging público ou deploy sem evidência.

## Estado desta execução

- F3-01 reproduzido (caminho `infra/caddy/transport.caddy` ausente) e corrigido;
  regressão resolve os `source` do workflow para arquivos reais.
- F3-02 reproduzido (7 falhas/4 sucessos com pai staging) e corrigido; a classe
  passa 16/16 com pai limpo e 16/16 com pai staging.
- F3-03 implementado no workflow e em `infra/scripts/smoke-stack.sh`.
- Compose CLI v5.6.1 validou base/dev/cron/smoke sem daemon.
- Docker Engine não está disponível nesta máquina: build, up, HTTPS, IP, cron e
  persistência **não foram executados localmente**. O aceite integrado fica
  pendente até o CI rodar no SHA corrigido.
- Não houve push, PR, deploy, DNS, VPS ou acesso a banco/provedor real.
