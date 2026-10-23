# L02/L03 — avisos e identidade durável de eventos externos

Status: verificado localmente, no SHA remoto e por reauditoria independente;
Gate H pendente.

## Contexto

L01 passou a registrar mais de um aviso fiscal não lido para a mesma
`NotaFiscal` quando existem respostas externas distintas. O helper global
`Aviso.registrar()` ainda pressupõe no máximo um aviso não lido por
`(tipo, objeto_tipo, objeto_id)` e usa `get_or_create`, o que produz
`MultipleObjectsReturned` em retries posteriores.

A deduplicação de L01 também procura `(tentativa, tipo)` somente em
`resultado_externo["eventos"]`, mas essa lista é limitada aos 20 eventos mais
recentes. Depois da rotação, o mesmo evento pode ser registrado novamente.

## L02 — avisos agregados e avisos por evento

### Invariantes

1. Avisos agregados são reutilizados enquanto não lidos; uma unicidade
   concorrente forte de agregados não é garantida por constraint nesta fase.
   A busca sempre tolera múltiplos registros sem lançar exceção.
2. Avisos por evento são distintos, identificáveis e não são reutilizados
   como aviso agregado.
3. `Aviso.registrar()` nunca lança `MultipleObjectsReturned` por causa de
   avisos por evento, inclusive quando já existem vários avisos antigos.
4. Um erro comum do provedor encerra a tentativa atual, registra sua
   evidência e libera o claim mesmo que haja avisos por evento anteriores.
5. Avisos e auditoria existentes não são apagados silenciosamente.
6. A mudança do helper global é compatível com os demais chamadores.

### Estratégia

- `Aviso.evento_chave`: vazio para aviso agregado; preenchido com a
  identidade estável do evento para aviso por evento.
- `Aviso.registrar()` filtra `evento_chave=""` e devolve o primeiro aviso
  agregado não lido; se não houver, cria um novo.
- Avisos por evento usam `evento_chave` único e não entram na busca do
  agregado.
- Migração aditiva atribui `legado:<pk>` aos avisos por evento já produzidos
  pelo SHA anterior, com prefixo `Resposta externa `, preservando todos.
- Nenhum aviso/auditoria é apagado, marcado como lido ou escolhido
  silenciosamente como vencedor.

### Aceite L02

- Sequência A/B/C: B falha, A falha obsoleta, C falha; C termina com
  `status=erro`, sem exceção, claim liberado e dois avisos visíveis
  (agregado de B e evento de A).
- Conflito de chave com avisos prévios termina como conflito tratado.
- Avisos múltiplos legados continuam listáveis.

## L03 — identidade durável além da projeção

### Invariantes

1. A identidade de deduplicação é `(nota, tentativa, tipo)` e sobrevive à
   rotação, releitura e nova transação.
2. `resultado_externo["eventos"]` continua sendo apenas a projeção dos 20
   eventos mais recentes.
3. Repetir E depois de 20 outros eventos produz 21 eventos lógicos, não 22
   efeitos.
4. Eventos distintos não são colapsados.
5. Dois replays concorrentes do mesmo evento produzem um único conjunto de
   efeitos.
6. O histórico completo permanece em `LogAuditoria`; nenhum registro é
   reescrito/apagado para corrigir contagem.

### Estratégia

- A `evento_chave` do aviso por evento é a identidade persistente:
  `fiscal.resultado_externo:<nota_id>:<uuid>:<tipo>`.
- Antes de criar evento, o fiscal verifica a chave; se já existe, retorna sem
  novo evento/aviso/auditoria.
- O caminho normal é uma consulta indexada à chave. O fallback de auditoria
  só é consultado após ausência da chave e é restrito à nota, ação, tentativa
  e tipo.
- A verificação e a criação ocorrem na transação que já bloqueia a
  `NotaFiscal`; a constraint condicional de unicidade é a defesa adicional
  contra concorrência.
- Compatibilidade legada: eventos ainda presentes no JSON são reconhecidos;
  eventos apenas na auditoria são reconhecidos por `depois.tentativa` e
  `depois.tipo`. Isso evita duplicar o que o SHA anterior já registrou sem
  exigir reescrever o histórico.
- Nenhuma janela finita é usada como memória de deduplicação.

### Aceite L03

- E + 20 eventos + E: 21 eventos lógicos, 21 auditorias, 21 avisos de evento;
  JSON contém os 20 mais recentes.
- Replay após releitura/nova transação não duplica.
- Replays concorrentes em PostgreSQL produzem um evento lógico.
- Eventos externos distintos continuam com evidências e avisos acessíveis.

## Migração e compatibilidade

- Nova migração `analytics/0004_aviso_evento_chave.py`.
- Adiciona `evento_chave`, faz backfill apenas dos avisos por evento já
  existentes e cria constraint condicional de unicidade.
- Avisos agregados existentes permanecem com chave vazia.
- Nenhuma migração anterior é editada; notas e logs existentes permanecem.

## Testes

- `fiscal/tests/test_auditoria_fase2c.py::L02L03AvisosEventosTests`.
- Teste PostgreSQL de replay concorrente.
- Regressões L01, N01–N03, R01–R05 e A01–A09.
