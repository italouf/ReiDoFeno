# Rastreabilidade da correção A01–A09

Legenda de estado: **corrigido e verificado** (teste local), **corrigido,
CI pendente**, **bloqueado por dependência**.

| ID | Requisito / invariante | Reprodução inicial | Causa raiz | Correção | Testes | Evidência | Estado |
|---|---|---|---|---|---|---|---|
| A01 | Lucro coerente entre painéis após chargeback | `test_chargeback_deve_manter_lucro_coerente_entre_paineis` | `metricas` usava receita de itens; comparativo usava pagamentos líquidos | Eventos de receita de produto + estorno financeiro; lucro = receita produtos − CMV | `sales/tests/test_auditoria_fase2c.py` | 0, 60, -60 nos dois painéis | corrigido e verificado |
| A02 | CMV histórico estável após chargeback | `test_chargeback_nao_deve_apagar_cmv_de_janeiro` | `_itens_vendidos` excluía cancelado com tipo nulo | Venda histórica não depende do status atual; estorno só afeta receita | `sales/tests/test_auditoria_fase2c.py`, `analytics/tests/test_eventos_relatorios.py` | Janeiro mantém 100/60/40 | corrigido e verificado |
| A03 | Devolução após chargeback sem segundo estorno | `test_devolucao_manual_apos_chargeback_deve_ser_possivel` | Serviço exigia financeiro atual `PAGO` | Aceita aprovação histórica + estorno confirmado; idempotente | `sales/tests/test_auditoria_fase2c.py` | entrada, movimento e um único estorno | corrigido e verificado |
| A04 | Estoque só compensa prova de baixa | `test_cancelamento_legado_sem_evidencia_nao_deve_inflar_estoque`, `test_evidencia_parcial_devolve_somente_quantidade_comprovada` | Fallback usava quantidade pedida | Usa obrigação, baixa comprovada e compensações anteriores; sem prova cria `Aviso` | `sales/tests/test_auditoria_fase2c.py`, `test_adr007_cancelamento.py` | saldo 10→10 sem prova; 10→11 com prova parcial | corrigido e verificado |
| A05 | Emissor conclui NF-e de entrada | `test_emissor_deve_conseguir_registrar_documento_de_entrada` | Só havia rota de saída e exigia financeiro pago | Lista/detalhe de entradas, formulário manual, referência validada, sem repetir efeitos | `fiscal/tests/test_auditoria_fase2c.py` | browser: entrada 77001 autorizada | corrigido e verificado |
| A06 | CSV fiscal com dados | `test_csv_fiscal_com_dados_deve_funcionar` | View acessava `aprovado_em` inexistente | Exporta `evento`/`evento_em`; sanitiza fórmulas em texto | `fiscal/tests/test_auditoria_fase2c.py`, `analytics/tests/test_relatorio_vendas_produto.py` | HTTP 200, linhas e valores | corrigido e verificado |
| A07 | CFOP de autorizada não é reescrito silenciosamente | `test_cfop_de_nota_autorizada_nao_deve_ser_reescrito_silenciosamente` | Comparação de substituição ignorava CFOP | Retificação exige motivo + evidência; saneamento de legado permitido | `fiscal/tests/test_auditoria_fase2c.py`, `test_modelo_fiscal.py` | edição comum bloqueada; saneamento auditado | corrigido e verificado |
| A08 | Gráficos sob CSP padrão | inspeção: CDN + inline sob `default-src 'self'` | Dependência externa e script inline | JS local `static/js/relatorios.js`, sem inline nem CDN | `test_graficos_nao_dependem_de_cdn_nem_script_inline` | browser: dois canvas pintados, 0 erros CSP | corrigido e verificado |
| A09 | Push da branch dispara CI | inspeção do workflow | `push.branches` não incluía a fase | Branch adicionada; PostgreSQL 15/Redis preservados | `core/tests/test_ci_workflow.py` | workflow local válido | corrigido, CI remoto pendente |

## Evidência por nível

- Inspeção: A08, A09.
- Teste automatizado local: A01–A07, A09.
- Navegador: A05, A08 (`docs/audit/fase-2c-comparativo-csp.png`,
  `docs/audit/fase-2c-nota-entrada.png`).
- CI remoto: pendente de push/disparo autorizado.
- Aceite humano: pendente; roteiro em `docs/operacao/fase-2c-aceite.md`.
