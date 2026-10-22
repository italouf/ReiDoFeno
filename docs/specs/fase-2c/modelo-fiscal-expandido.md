# Modelo fiscal expandido — NF-e de entrada/devolução

## Objetivo

Permitir que um pedido tenha a NF-e de saída e, em caso de devolução, uma
NF-e de entrada referenciada, com CFOP inverso e trilha de auditoria.

## Modelo

`NotaFiscal`:

- `tipo` (`saida`/`entrada`);
- `cfop` (10 caracteres, opcional para saída);
- `chave_referenciada` (44 dígitos, obrigatória para entrada);
- `status` inclui `cancelada`;
- `pedido` passa de `OneToOne` para `ForeignKey` (`notas_fiscais`), pois o
  pedido pode ter uma nota de saída e uma de entrada;
- restrição de unicidade por `(pedido, tipo)`;
- `Pedido.nota_fiscal` permanece como propriedade que retorna a saída.

## CFOP inverso

`fiscal.services.calcular_cfop_inverso`:

- tabela explícita para 5.101–5.110, 6.101–6.103 e 7.101–7.102;
- regra geral: 5→1, 6→2, 7→3;
- CFOP fora dessas operações de saída é rejeitado.

## Testes

- NF-e de entrada sem chave referenciada é inválida;
- chave referenciada curta/não numérica é inválida;
- saída sem chave referenciada é válida;
- mapeamentos de CFOP;
- pedido aceita saída + entrada, com unicidade por tipo;
- cancelamento de NF-e autorizada é auditado e idempotente.

## Critérios de aceite

- [ ] Campos e migração.
- [ ] Validação de chave referenciada.
- [ ] CFOP inverso funcional.
- [ ] Unicidade por pedido/tipo.
- [ ] Compatibilidade de `pedido.nota_fiscal`.
