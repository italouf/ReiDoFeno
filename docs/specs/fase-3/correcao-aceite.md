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
| F3-04 | Smoke usava o mesmo projeto/volumes do dev (`reidofeno`) e semeava/removia recursos compartilhados | Projeto descartável próprio, sem fallback, com volumes/credenciais isolados e recusa antes da primeira mutação | `reidofeno_smoke`, `--project-name`, `.env.smoke`/`.env.docker.smoke`, portas 8080/8443, validação de config e teste de sentinela | Teste de isolamento e CI; execução Docker pendente |
| F3-05 | `manage.py shell -c` imprime banner de importações; comparação exata com `1` falha | Saída de máquina determinística e exit code propagado | `shell --verbosity 0` nas consultas e regressão com Django 5.2.17 | Reprodução: sem flag imprime banner+1; com flag imprime somente `1` |
| F3-06 | Trap antes dos guards e lock diferente entre harness/smoke; pai marcava `OWN_SMOKE=1` antes de o filho adquirir o projeto | Lock comum com token de owner herdado e verificado; harness mantém a autoridade até o último teardown; guards antes de mutação | 10 regressões com Bash real + Docker simulado, incluindo os dois scripts reais no cenário de lock ocupado | **10 passed** localmente; integração real pendente no CI |


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

## F3-04 — isolamento do smoke

O smoke usa um projeto Compose próprio (`reidofeno_smoke`), passado
explicitamente por `--project-name` em todas as operações, e arquivos de
ambiente exclusivos:

- `infra/.env.smoke` (interpolação: porta 8080/8443, domínio local, senha
  sintética, `APP_ENV_FILE=.env.docker.smoke`);
- `.env.docker.smoke` (staging, simuladores, console, sem credenciais reais).

A base não faz fallback para `reidofeno`: o script recusa projeto habitual,
arquivo ausente ou modelo que não tenha os volumes prefixados
`reidofeno_smoke_*` **antes** de subir/semear/remover. As portas do Caddy são
parametrizadas (`CADDY_HTTP_PORT`/`CADDY_HTTPS_PORT`) e o smoke publica
8080/8443, sem disputar 80/443 da stack de desenvolvimento. A rede `_front` é
descoberta via `docker inspect`, sem hardcode de `reidofeno_front`.

`infra/scripts/test-smoke-isolation.sh` cria um projeto/volume/container
sentinela descartável, executa o smoke no projeto separado e confere que o
sentinela permanece intacto após sucesso e após falha deliberada. O cleanup
remove somente `reidofeno_smoke` e o sentinela criado pelo próprio teste.

## F3-05 — persistência determinística

`contar_produto` usa `manage.py shell --verbosity 0 -c`, que no Django 5.2.17
imprime somente o valor (sem o banner de importações). Falha do comando,
produto ausente ou contagem diferente de 1 reprovam a verificação; não há
`tail -1`, filtro permissivo ou `|| true` na assertion. Uma regressão executa a
forma real de invocação e exige stdout exato.

## F3-06 — propriedade no cleanup do sentinela

Harness e smoke direto usam o MESMO lock (`SMOKE_LOCK_DIR`, default
`/tmp/reidofeno_smoke.lock`). O harness cria a lock e grava um token no arquivo
`owner`; o filho só aceita herdar a autoridade se `SMOKE_LOCK_OWNER_TOKEN`
corresponder ao owner. O filho não readquire nem libera a lock. Assim a
autoridade cobre guards, criação, execução e todos os teardowns, sem janela
entre filho e pai.

Recusas por lock ocupado, volume/container preexistente ou projeto de smoke
ocupado não executam comandos destrutivos; apenas a lock de quem a criou é
removida. Smoke direto concorrente e harness não se sobrepõem.

Ownership é explícita: `OWN_SENTINELA_VOLUME` só é marcado após
`docker volume create`; `OWN_SENTINELA_CONTAINER` após `docker run`;
`OWN_SMOKE` só depois dos guards e antes do smoke. O cleanup remove
exatamente as flags ativas, preserva o exit code original e nunca usa
`down -v`/`rm` em recursos preexistentes. Uma falha parcial remove só o volume
já criado. Uma segunda execução concorrente é recusada pela lock sem tocar na
primeira.

Regressões em `core/tests/test_smoke_isolation.py` executam o Bash real com
`docker` simulado e cobrem: volume preexistente, container preexistente,
projeto ocupado, lock concorrente, falha parcial, sucesso, falha inesperada
(exit 7), falha deliberada, lock comum preexistente e os dois scripts reais
com o smoke direto ocupando a lock (sem hook no harness).

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
- F3-04 implementado com projeto `reidofeno_smoke`, envs próprios, portas
  alternativas e validação pré-mutação; teste de sentinela preparado para CI.
- F3-05 reproduzido (banner + `1`) e corrigido com `--verbosity 0`; regressão
  preparada.
- F3-06 reproduzido com Docker simulado; guards de propriedade, lock comum
  (token verificado), cleanup seletivo e preservação de exit code
  implementados; 10 regressões de comportamento passam.
- Compose CLI v5.6.1 validou base/dev/cron/smoke sem daemon e o modelo smoke
  isolado (`reidofeno_smoke`, volumes, portas 8080/8443).
- Suíte local: 709 passed, 24 skipped, 240 subtests; 64 testes focados.
- Docker Engine não está disponível nesta máquina: build, up, HTTPS, IP, cron e
  persistência **não foram executados localmente**. O aceite integrado fica
  pendente até o CI rodar no SHA corrigido.
- Não houve push, PR, deploy, DNS, VPS ou acesso a banco/provedor real.
