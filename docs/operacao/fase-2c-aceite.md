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
