# Correção da auditoria da Fase 2C

## Objetivo

Corrigir os achados A01–A09 sem reescrever a história financeira nem
transformar aproximações legadas em certeza. A implementação preserva as
garantias das Fases 2A/2B: ledger imutável, reservas vinculadas, status
financeiro separado, constraints e titularidade.

## Contrato de eventos

| Evento | Fonte | Receita produtos | CMV | Estoque |
|---|---|---|---|---|
| Aprovação | `Pagamento.aprovado_em` | + | + | baixa comprovada |
| Estorno/chargeback | `Pagamento.estornado_em` | − | 0 | 0 |
| Retorno físico | `MovimentoEstoque.entrada_devolucao` com obrigação | 0 | − | + quantidade comprovada |
| Registro fiscal de entrada | `NotaFiscal` tipo entrada | 0 | 0 | 0 |

## Oráculo mínimo (sem frete)

Dois itens a R$ 50, custo unitário R$ 30:

| Período/evento | Receita produtos | CMV | Lucro bruto |
|---|---:|---:|---:|
| Janeiro: aprovação integral | 100,00 | 60,00 | 40,00 |
| Fevereiro: chargeback sem retorno | -100,00 | 0,00 | -100,00 |
| Março: retorno físico comprovado | 0,00 | -60,00 | 60,00 |
| Acumulado | 0,00 | 0,00 | 0,00 |

Aprovação + chargeback no mesmo período, sem retorno: receita 0, CMV 60,
lucro bruto -60. Chargeback + retorno físico no mesmo período posterior:
receita -100, CMV -60, lucro bruto -40.

## Invariantes

- Receita financeira inclui frete; receita de produtos não. A diferença é
  exposta como `receita_frete`, sem forçar igualdade entre escopos.
- `lucro_bruto` de produto = `receita_produtos - cmv`.
- Chargeback nunca movimenta estoque nem reverte CMV.
- Devolução após chargeback é permitida sem segundo estorno, desde que exista
  aprovação histórica e estorno confirmado.
- Estoque só é devolvido contra obrigação com baixa comprovada e não
  compensada; ausência de prova gera `Aviso` e nenhum crédito.
- NF-e de entrada é documento distinto da saída; sua conclusão manual não
  repete efeitos de estoque/estorno.
- CFOP de saída autorizada não é reescrito por edição comum; saneamento de
  legado exige motivo e evidência.
- Gráficos usam apenas estáticos locais e JS externo ao HTML, compatíveis com
  `default-src 'self'`.

## Limites

- O registro fiscal de entrada é manual/assistido; não há emissão SEFAZ real
  nesta fase.
- O custo legado preenchido pelo custo corrente continua aproximado.
- Não há devolução parcial de nota fiscal nem motor tributário completo.
- A confirmação externa de cancelamento/reembolso permanece humana.
