# Plano de Resposta a Incidente

## Classificação

| Severidade | Definição | Exemplos |
|---|---|---|
| SEV1 | Loja/pagamentos indisponíveis ou suspeita de vazamento de dados | Checkout fora do ar; webhook aceitando assinaturas inválidas; dump exposto |
| SEV2 | Degradação grave com contorno | NF-e parada com fila crescendo; e-mails falhando; lentidão extrema |
| SEV3 | Impacto limitado / cosmético | Aviso duplicado; layout quebrado em navegador específico |

## Fluxo de resposta

1. **Detectar** — Sentry (erro novo), UptimeRobot (downtime), relato interno.
2. **Comunicar** — abrir canal `#inc-<data>`; designar responsável (IC) e anotar timeline.
3. **Contenção**
   - Suspeita de comprometimento: rotacionar `DJANGO_SECRET_KEY`, tokens MP/Bling, senhas admin; revisar `LogAuditoria` e eventos de webhook brutos.
   - Indisponibilidade: Rollback no Render para o build anterior saudável.
4. **Erradicação & recuperação** — corrigir causa-raiz, aplicar fix, restaurar backup se integridade do banco for duvidosa (seguir §4 do runbook).
5. **Comunicação externa** — SEV1 com impacto a titulares: notificar ANPD e titulares conforme LGPD art. 48 (prazo razoável; usar modelo de comunicado aprovado pelo jurídico).
6. **Post-mortem** (obrigatório SEV1/SEV2 em 5 dias): linha do tempo, causa raiz, ações corretivas com dono/prazo, atualização desta documentação.

## Contatos

- IC da semana + responsável técnico: definir na escala da equipe.
- Provedores: suporte Render / Mercado Pago / Bling (credenciais no cofre da equipe).

## Evidências preservadas pela aplicação

- `PagamentoWebhookEvento` guarda payload bruto e resultado do processamento.
- `LogAuditoria` (append-only) registra autor/IP/antes-depois das ações críticas.
- Logs estruturados JSON sem PII (filtro sanitizador ativo).
