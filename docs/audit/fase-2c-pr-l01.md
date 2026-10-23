# PR preparada — correção L01

Não publicar sem autorização.

## Título

`fix(fiscal): condiciona conclusão da emissão à autoridade da tentativa (L01)`

## Corpo

### Contexto

A reauditoria independente do SHA `47f75eb7ce6ca87395f777600d75c157cf44306b`
reproduziu quatro falhas de finalização fiscal:

- sucesso de uma tentativa antiga substituía confirmação manual;
- erro antigo rebaixava nota autorizada;
- erro antigo desfazia cancelamento;
- tentativa expirada limpava o resultado de uma tentativa mais nova.

### Correção

- `NotaFiscal.tentativa_atual` identifica a tentativa dona do lease.
- A conclusão relê o documento sob lock e só aplica sucesso/erro se o token
  ainda for o mesmo.
- Registro manual é bloqueado durante lease ativo; após expiração pode
  assumir o claim, invalida o token antigo e audita a assunção.
- Cancelamento invalida o claim e permanece terminal.
- Respostas tardias/conflitantes ficam em `resultado_externo`, com `Aviso` e
  auditoria, sem reabrir pedido, repetir estoque/estorno ou inventar
  cancelamento externo.
- `fiscal/0006_tentativa_emissao.py` é aditiva e passou no gate histórico.

### Testes

- 12 cenários L01 em `fiscal/tests/test_auditoria_fase2c.py`.
- Quatro interleavings PostgreSQL em
  `fiscal/tests/test_concurrency_postgres.py`.
- Controle de retry ativo e N01–N03/R01–R05 preservados.
- Local: SQLite 648 passed, 22 skipped, 240 subtests; cobertura total 86,38%;
  `fiscal/services.py` 93,94%; Node 2/2; Ruff, `check`, `check --deploy`,
  `makemigrations --check`, Bandit e `pip-audit` limpos.

### Gates

- Gate T: correção local validada; PG + Redis e revisão independente no SHA
  final pendentes.
- Gate C: pendente; a CI verde `39880437864` pertence ao SHA anterior.
- Gate H: aceite do cliente pendente.

### Fora de escopo

Sem push, PR remota, merge, deploy, Neon/dados reais, SEFAZ/Bling real ou
reembolso.
