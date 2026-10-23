# Fase 3 — TAREFA 3: Caddy com TLS automático

> **Escopo:** o TLS público, DNS e Let's Encrypt não foram provisionados nem
> executados nesta entrega. A validação local usa a CA interna do Caddy em
> `localhost`; o aceite integrado depende do CI/no ambiente descartável.

## Objetivo

Colocar o Django atrás de um reverse proxy com HTTPS automático
(Let's Encrypt), headers de segurança, mídia servida diretamente do disco e
preservação do IP real do cliente para auditoria/rate limiting (SEC-03).

## Decisões

### Domínios parametrizados

O Caddyfile usa placeholders de ambiente:

| Variável | Default local | Produção |
|---|---|---|
| `APP_DOMAIN` | `localhost` | `reidofeno.com.br` |
| `STAGING_DOMAIN` | `staging.localhost` | `staging.reidofeno.com.br` |
| `ACME_EMAIL` | `admin@reidofeno.com.br` | e-mail operacional |
| `HSTS_MAX_AGE` | `0` (compose local) | `31536000` |

Com domínios `localhost`/`*.localhost`, o Caddy usa a CA interna
automaticamente — não há tentativa de ACME público em desenvolvimento. Em
produção, os domínios reais acionam o Let's Encrypt sem configuração extra.

`APP_DOMAIN` gera também `www.APP_DOMAIN`. `STAGING_DOMAIN` não pode ser igual
a `APP_DOMAIN` (o Caddy recusaria dois sites no mesmo endereço).

### PROXY protocol (SEC-03)

O compose publica apenas o Caddy. O proxy envia PROXY protocol v1 ao Gunicorn:

```caddyfile
# infra/transport.caddy (produção)
transport http {
    proxy_protocol v1
}
```

O `Caddyfile` importa esse snippet; o override de desenvolvimento monta
`transport-dev.caddy` no mesmo caminho, que deixa o transporte HTTP
padrão para o `runserver`.

O Gunicorn sobe com `--proxy-protocol=v1` e `--proxy-allow-from=*`; assim
`REMOTE_ADDR` no Django é o IP do cliente, sem confiar em `X-Forwarded-For`
enviado pelo cliente. A porta `8000` do `web` não é publicada no compose base.
O healthcheck usa `curl --haproxy-protocol` para exercitar o mesmo caminho do
proxy (o Gunicorn aceita conexões sem o cabeçalho, mas o Caddy sempre o envia).

### TLS e headers

- HSTS configurável (`HSTS_MAX_AGE`), com `includeSubDomains; preload` em
  produção.
- `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, CSP e remoção de `Server`.
- CSP compatível com o app: scripts apenas same-origin, estilos inline
  permitidos (há `style="..."` em templates), imagens `self`/`data:`/`https:`.
- O Django mantém `SecurityHeadersMiddleware` como defesa em profundidade;
  atrás do Caddy, o header do proxy prevalece.

### Mídia

`handle_path /media/*` serve `/srv/media` diretamente, com o volume `media`
montado read-only. O Django não gasta worker com uploads. Arquivos estáticos
de aplicação continuam no WhiteNoise (manifest hash).

### Logs

Access logs em JSON no stdout, coletados e rotacionados pelo driver
`json-file` do Docker (10 MB × 3). Não há volume de log nem permissão extra.
A URI registrada pode conter tokens de acesso a pedidos; a retenção curta do
driver limita a exposição, e o acesso ao host/daemon deve ser restrito.

### Execução não-root

O Caddy roda como uid 1000, com `cap_drop: ALL`, `cap_add:
NET_BIND_SERVICE`, `read_only`, `no-new-privileges` e `tmpfs` em `/tmp`. O
`caddy-init` é o único processo root, one-shot, para ajustar a ownership dos
volumes `caddy_data`/`caddy_config`.

### SEC-03 no smoke

Para provar que o IP real atravessa o proxy, `/healthz/ip/` retorna somente
`REMOTE_ADDR` quando `SMOKE_DIAGNOSTICS=True` **e** `DJANGO_ENVIRONMENT=staging`.
Fora desse cenário a rota responde 404; produção estrita nunca habilita o
diagnóstico. O smoke compara o IP visto por `web` e `cron` com o IP real dos
containers e envia `X-Forwarded-For: 203.0.113.99` para confirmar que o header
forjado é ignorado.

## Critérios de aceite

- [ ] `caddy validate --config infra/Caddyfile` retorna `Valid configuration`.
- [ ] HTTPS automático quando `APP_DOMAIN`/`STAGING_DOMAIN` apontarem para a VPS.
- [ ] Redirecionamento HTTP → HTTPS automático.
- [ ] HSTS, CSP, `nosniff`, `DENY` e `Permissions-Policy` presentes.
- [ ] `/media/...` servido pelo Caddy, sem proxy para o Gunicorn.
- [ ] `REMOTE_ADDR` no Django é o IP do cliente (PROXY protocol).
- [ ] Logs de acesso em JSON no stdout.

## Validação local

```text
$ caddy validate --config infra/Caddyfile --adapter caddyfile
Valid configuration
```

O JSON adaptado confirma `"proxy_protocol": "v1"` nas duas rotas,
`handle_path` para mídia e os headers de segurança. Testes de contrato em
`core/tests/test_infra_contract.py` protegem a configuração no CI.

## Operação

```bash
# desenvolvimento (CA interna): aceitar o certificado no navegador ou usar -k
curl -k https://localhost/healthz/

# produção: DNS de APP_DOMAIN e STAGING_DOMAIN apontando para a VPS,
# portas 80/443 liberadas, volumes caddy_data/caddy_config preservados.
docker compose -f infra/docker-compose.yml logs -f caddy
```

Renovar certificados é automático. Não remova `caddy_data`: ele guarda a
conta ACME e os certificados; recriá-lo força nova emissão e pode esbarrar
nos rate limits do Let's Encrypt.
