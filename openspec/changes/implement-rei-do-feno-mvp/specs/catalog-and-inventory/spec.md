# Delta: catalog-and-inventory

## Purpose

Definir o cadastro de produtos e categorias e a gestão de estoque por unidade (Feira de Santana e Iaçu) com ledger imutável de movimentações, reserva/bloqueio de quantidade e alerta de estoque baixo.

## ADDED Requirements

### Requirement: Cadastro de produtos

O sistema SHALL permitir cadastro de produto com nome, categoria, NCM, unidade de medida, custo, preço balcão, preço online e flag ativo/inativo. Produto sem nome ou sem unidade de medida MUST ser rejeitado; somente produtos ativos aparecem na vitrine.

#### Scenario: Produto válido é criado
- **WHEN** um administrador/gestor cadastra um produto com todos os campos obrigatórios
- **THEN** o produto fica disponível para consulta e edição nos perfis permitidos

#### Scenario: Produto inválido é rejeitado
- **WHEN** um cadastro de produto é enviado sem nome ou sem unidade de medida
- **THEN** o sistema recusa e indica os campos faltantes

#### Scenario: Inativação remove da vitrine
- **WHEN** um produto ativo é marcado como inativo
- **THEN** ele deixa de aparecer na vitrine pública

### Requirement: Estoque por unidade

O estoque SHALL ser sempre mantido por unidade (Feira de Santana / Iaçu), com quantidade atual, quantidade mínima e quantidade bloqueada/reservada para pedidos em andamento. Saldo efetivo disponível MUST considerar o bloqueio/reserva.

#### Scenario: Saldo inicial por unidade
- **WHEN** um gestor define estoque inicial de um produto em cada unidade
- **THEN** cada unidade passa a ter saldo próprio e independente

### Requirement: Movimentações geram registro imutável

Toda alteração de saldo SHALL gerar um registro de movimento de estoque (tipo entrada/saída/ajuste/transferência, quantidade, motivo, usuário, data e pedido relacionado quando aplicável). Movimentos não podem ser apagados pela aplicação; correções ocorrem por estorno/ajuste.

#### Scenario: Entrada e saída atualizam saldo
- **WHEN** uma entrada ou saída é confirmada para um produto/unidade
- **THEN** o saldo é recalculado e o movimento correspondente fica registrado com autor e data

#### Scenario: Saída acima do saldo é bloqueada
- **WHEN** uma saída excede o saldo disponível da unidade
- **THEN** a operação é recusada e nenhum movimento é gravado

#### Scenario: Movimento não pode ser deletado
- **WHEN** alguém tenta remover um movimento diretamente
- **THEN** a exclusão não é oferecida/não é executada

### Requirement: Ajuste manual exige motivo

Todo ajuste manual de saldo SHALL exigir motivo obrigatório e ser auditado.

#### Scenario: Ajuste sem motivo é rejeitado
- **WHEN** um gestor confirma um ajuste sem preencher o motivo
- **THEN** o sistema recusa a operação indicando a obrigatoriedade

### Requirement: Transferência entre unidades

A transferência de estoque entre unidades SHALL gerar duas movimentações vinculadas: saída na origem e entrada no destino, com o mesmo produto e quantidade.

#### Scenario: Transferência consistente
- **WHEN** uma transferência de N unidades é confirmada da Feira de Santana para Iaçu
- **THEN** o saldo diminui N na origem, aumenta N no destino e dois movimentos vinculados são criados

### Requirement: Alerta de estoque baixo

Quando o saldo de um produto/unidade atingir ou ficar abaixo do mínimo configurado, o sistema SHALL gerar aviso interno de estoque baixo visível aos perfis internos permitidos.

#### Scenario: Saldo atinge o mínimo
- **WHEN** uma saída deixa o saldo igual ou abaixo do mínimo da unidade
- **THEN** um aviso de estoque baixo é criado/exibido no painel de avisos
