# Roteiro de aceite — Fase 2C (correção)

Este roteiro deve ser executado com dados sintéticos ou base conciliada
autorizada. Nenhum valor aqui é apuração contábil/tributária.

## 1. Números de referência (sem frete)

Dois itens/unidades a R$ 50, custo R$ 30.

| Cenário | Receita produtos | CMV | Lucro bruto |
|---|---:|---:|---:|
| Janeiro: aprovação integral | 100,00 | 60,00 | 40,00 |
| Fevereiro: chargeback sem retorno | -100,00 | 0,00 | -100,00 |
| Março: retorno físico comprovado | 0,00 | -60,00 | 60,00 |
| Acumulado | 0,00 | 0,00 | 0,00 |

Verificar, no mesmo período/escopo, painel, “Minhas métricas”, relatório por
produto, comparativo e relatório fiscal. Frete deve aparecer separado e não
ser atribuído ao lucro de produto.

## 2. Workflow operacional

1. Venda aprovada em mês diferente da criação; conferir competência.
2. Estorno no mesmo mês e no mês seguinte.
3. Chargeback sem retorno físico; conferir que o CMV não é revertido.
4. Devolução após chargeback; conferir uma entrada, um movimento e um único
   estorno.
5. Cancelamento padrão dentro e fora de 24h.
6. Pedido sem obrigação/evidência; conferir saldo intacto e aviso.
7. Emissor Fiscal localiza a entrada pendente, registra número/chave/link e
   confirma que estoque/estorno não foram repetidos.
8. CFOP confirmado não muda em edição comum; saneamento de legado exige
   motivo/evidência.

## 3. Unidades e vendedores

- Vendedor A e B: cada um vê apenas o próprio recorte.
- Administrador/Gestor veem a soma global.
- FS e Iaçu: comparar receita, CMV, lucro, pedidos e ticket médio.
- Frete: documentar a diferença entre receita financeira e receita de
  produtos.

## 4. Limitações que o aceite deve reconhecer

- Custo legado preenchido pelo custo corrente é aproximado.
- Emissão real de NF-e de entrada é manual/assistida.
- Registro local não prova autorização SEFAZ nem reembolso efetivado.
- Devolução parcial de nota fiscal e motor tributário completo não fazem
  parte desta fase.

## 5. Registro

Para cada cenário, registrar:

- commit testado;
- base/dados usados;
- valores esperados e obtidos;
- screenshots/consultas;
- responsável pelo aceite e data.

Somente o cliente/responsável pode declarar o Gate H aprovado.

## 6. Ficha de aceite — SHA 2a7a300

Esta ficha está pronta para preenchimento pelo responsável humano. Campos de
resultado, evidência e decisão ficam deliberadamente **PENDENTES** até a
execução com o cliente; este documento não presume aprovação.

### 6.1 Identificação

| Campo | Conteúdo |
|---|---|
| Branch | `fase-2c-analytics-fiscal` |
| SHA submetido ao aceite | `2a7a30096f7d3c00b7bba9b5bd7dd12e78894a70` |
| CI vinculada ao SHA | `39953967926` — success |
| Ambiente | Homologação/staging com dados sintéticos ou base conciliada autorizada |
| Data da execução | PENDENTE |
| Responsável do cliente | PENDENTE |
| Responsável técnico | PENDENTE |
| Decisão | PENDENTE: aprovar / aprovar com ressalvas / reprovar |

### 6.2 Cenários e resultados

| # | Cenário | Resultado esperado | Resultado obtido | Evidência | Decisão |
|---|---|---|---|---|---|
| 1 | Janeiro: aprovação integral | Receita produtos 100,00; CMV 60,00; lucro 40,00; frete separado | PENDENTE | PENDENTE | PENDENTE |
| 2 | Fevereiro: chargeback sem retorno físico | Receita produtos -100,00; CMV 0,00; lucro -100,00; sem novo estorno | PENDENTE | PENDENTE | PENDENTE |
| 3 | Março: retorno físico comprovado | Receita produtos 0,00; CMV -60,00; lucro 60,00; uma entrada e um movimento | PENDENTE | PENDENTE | PENDENTE |
| 4 | Acumulado dos três períodos | Receita 0,00; CMV 0,00; lucro 0,00 | PENDENTE | PENDENTE | PENDENTE |
| 5 | CMV em conciliação financeira | CMV comprovado permanece reconhecido; receita incerta separada | PENDENTE | PENDENTE | PENDENTE |
| 6 | Frete | Frete exposto separado; não negativo; não somado ao lucro de produto | PENDENTE | PENDENTE | PENDENTE |
| 7 | Vendedores A/B | Cada vendedor vê somente seu recorte; gestão vê o global | PENDENTE | PENDENTE | PENDENTE |
| 8 | FS e Iaçu | No cenário sintético de referência: FS 100/60/40 e Iaçu 100/40/60; conferir receita, CMV, lucro, pedidos e ticket médio | PENDENTE | PENDENTE | PENDENTE |
| 9 | Cancelamento dentro de 24h | Cancelamento padrão, estorno e devolução de estoque conforme evidência | PENDENTE | PENDENTE | PENDENTE |
| 10 | Cancelamento fora de 24h | Fluxo de devolução, sem cancelamento padrão indevido | PENDENTE | PENDENTE | PENDENTE |
| 11 | Registro manual de NF-e de entrada | Emissor registra número/chave/link; estoque e estorno não são repetidos | PENDENTE | PENDENTE | PENDENTE |
| 12 | CFOP, chave e terminalidade | CFOP confirmado não muda sem retificação; chave não duplica; cancelada não reautoriza | PENDENTE | PENDENTE | PENDENTE |

### 6.3 Evidência de engenharia

| Evidência | Resultado | Origem |
|---|---|---|
| HEAD remoto/checkout | `2a7a30096f7d3c00b7bba9b5bd7dd12e78894a70` | Git/reauditoria independente |
| CI do SHA | Run `39953967926` success; PostgreSQL 15 + Redis, check de produção e migração histórica | Reauditoria independente |
| Suíte SQLite local do agente | 655 passed, 24 skipped, 240 subtests; cobertura 86,39% | Execução local |
| Suíte PostgreSQL independente | 678 passed, 1 skipped, 240 subtests; cobertura 86,41% | Reauditoria independente |
| L02/L03 | Retry A/B/C, rotação de 20 eventos, legado e replay concorrente aprovados | Reauditoria independente |
| Gate histórico | PostgreSQL 15 na CI e PostgreSQL 16.2 independente aprovados | CI + reauditoria |
| Gate T | Aprovado com observações não bloqueantes | Reauditoria independente |
| Gate C | Aprovado no SHA `2a7a300` | CI `39953967926` |
| Gate H | **PENDENTE** | Cliente/responsável humano |

### 6.4 Limitações que o aceite deve reconhecer

- Custo legado preenchido pelo custo corrente é aproximado.
- Emissão real de NF-e de entrada é manual/assistida.
- Registro local não prova autorização SEFAZ nem reembolso efetivado.
- Devolução parcial de nota fiscal e motor tributário completo não fazem
  parte desta fase.
- Conflitos externos tardios exigem conciliação humana; o sistema preserva a
  evidência e não escolhe silenciosamente um documento vencedor.

Itens não bloqueantes de manutenção estão registrados em
`docs/operacao/fase-2c-backlog.md`.

### 6.5 Assinatura de aceite

Nome do responsável: ______________________________

Data: ____ / ____ / ______

Decisão: ( ) Aprovado  ( ) Aprovado com ressalvas  ( ) Reprovado

Observações: ______________________________________________________________

Somente este preenchimento humano pode encerrar o Gate H.
