# ADR-005 — Titularidade sem vazamento de histórico

**Fase:** 2B
**Prioridade:** P1
**Depende de:** Fase 2A (vínculo comprovado)
**Implementa:** `docs/specs/fase-2b-spec.md` §ADR-005

## Contexto observado

A Fase 2A criou `Cliente.vinculo_verificado` e a prova de vínculo por nonce.
`MeusPedidosView` já filtra `cliente__usuario=request.user`,
`cliente__vinculo_verificado=True` e `identidade_verificada=True`. Porém:

- a exportação LGPD (`exportar_dados_do_titular`) não exige vínculo comprovado;
- a tela de pedidos não orienta o usuário quando o vínculo ainda não foi comprovado;
- a tentativa de exportação sem vínculo redireciona em vez de negar explicitamente.

## Decisão

1. `meus-pedidos` lista somente pedidos de cliente com `vinculo_verificado=True` **e**
   `pedido.identidade_verificada=True`, sempre restrito ao `usuario` autenticado.
2. Cliente sem vínculo comprovado vê estado vazio com mensagem orientando a confirmar
   o e-mail pelo fluxo de vínculo (não é erro 500).
3. `exportar_dados_do_titular` levanta `PermissionDenied` sem vínculo comprovado.
4. A view de solicitação de exportação responde **403** quando não há vínculo; os demais
   tipos de solicitação mantêm o redirecionamento com mensagem.
5. Pedidos criados por visitante (`identidade_verificada=False`) nunca aparecem no
   histórico de nenhum usuário, mesmo que o documento coincida.

## Invariantes

- Um usuário nunca vê pedido de `Cliente` que não seja o seu próprio cliente verificado.
- Exportação de dados pessoais exige prova de vínculo.
- Nenhuma resposta 500 para usuário autenticado sem vínculo.

## Critérios de aceite

- [ ] `meus-pedidos` filtra vínculo verificado e identidade do pedido.
- [ ] Estado vazio orienta o usuário sem vínculo.
- [ ] Exportação sem vínculo retorna 403 (view e service).
- [ ] Pedido de outro cliente não aparece.
- [ ] Testes passam em SQLite e PostgreSQL.
