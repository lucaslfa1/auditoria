# Avaliação técnica - Automação Huawei D-1 após ajuste 3

**Data:** 2026-05-24  
**Autor:** Codex  
**Base analisada:** `automacao_ajuste.md`, `automacao_ajuste_2.md`, `automacao_ajuste_3.md`, `fix_automacao.sql`, código citado no commit `ca706d7` e testes locais relevantes.

## 1. Veredito

A conclusão do `automacao_ajuste_3.md` é tecnicamente consistente: o problema principal não parece ser o Cloud Scheduler nem uma parada total do cron. O comportamento observado é mais compatível com uma automação que continuava sendo acionada, mas sem conseguir produzir coleta efetiva por causa de uma combinação de configuração operacional perigosa:

- `huawei_d1_max_retries = 1`
- `huawei_d1_lookback_dias = 1`
- `huawei_d1_horario_execucao = 02:10`
- janela longa com automação desligada entre `2026-05-22 20:08 UTC` e `2026-05-24 01:40 UTC`

O ajuste de código vai na direção correta, mas a correção ainda não deve ser considerada encerrada enquanto não houver confirmação de:

1. SQL aplicado no Neon.
2. deploy ativo no Cloud Run.
3. recuperação manual das datas `20260522` e `20260523`.
4. pelo menos um ciclo pós-`06:00 BRT` com download real ou evidência de que o OBS segue vazio por causa externa.

## 2. Evidências que sustentam o diagnóstico

### Tracker D-1

O relatório `automacao_ajuste.md` mostra apenas três registros em `huawei_d_minus_1_runs`:

- `20260523`: `empty`, `attempts = 1`
- `20260521`: `partial`, `attempts = 4`
- `20260520`: `partial`, `attempts = 5`

A ausência de `20260522` é importante. Ela combina com o audit log que mostra a automação desligada durante uma janela suficiente para impedir a criação do registro no tracker. Com `lookback_dias = 1`, o cron não teria janela para voltar nessa data depois.

### Configuração no banco

O mesmo relatório mostra que o banco estava com:

- `huawei_d1_max_retries = 1`
- `huawei_d1_lookback_dias = 1`
- `huawei_d1_horario_execucao = 02:10`
- `huawei_d1_enabled = true`
- `huawei_d1_run_lock = false`

Esses valores explicam bem o sintoma: a pipeline podia estar ligada e desbloqueada, mas uma primeira listagem vazia do OBS já encerrava a data como `empty`; e datas perdidas não voltavam a ser avaliadas.

### Audit log

O `automacao_ajuste_2.md` confirma muitas alterações em sequência de horário, retentativas e toggles. Isso torna o incidente menos parecido com um bug único e mais parecido com uma falha composta: configuração instável, janela desligada e parâmetros pouco tolerantes a atraso do fornecedor.

Também é coerente o bug de UI identificado: `telefonia_cron_sync_ativa` apareceu como `"1"` no audit log, e o código anterior realmente podia transformar booleano em número na serialização do frontend.

## 3. Avaliação das mudanças aplicadas

### `backend/core/huawei_d_minus_1.py`

Ponto positivo: os defaults de `PIPELINE_CONFIG_DEFAULTS` foram elevados para uma configuração mais segura:

- `huawei_d1_max_retries`: `8`
- `huawei_d1_retry_intervalo_minutos`: `60`
- `huawei_d1_lookback_dias`: `3`
- `huawei_d1_horario_execucao`: `06:00`

Isso reduz a chance de perda permanente quando o OBS demora a popular ou quando a automação fica temporariamente desligada.

Ponto de atenção: dentro de `executar_d_minus_1_pipeline()`, ainda há fallbacks antigos em caso de valor inválido no banco:

```python
max_retries = max(1, _coerce_int(cfg["huawei_d1_max_retries"], 4))
lookback_dias = max(1, _coerce_int(cfg["huawei_d1_lookback_dias"], 1))
```

Como `get_pipeline_config()` normalmente injeta os defaults novos, isso não quebra o caso comum. Mesmo assim, se o banco tiver valor inválido como string vazia ou texto, o fallback volta para `4` e `1`. Eu ajustaria esses fallbacks para `8` e `3` para manter o comportamento consistente.

### `backend/repositories/configuration.py`

Ponto positivo: a normalização defensiva no backend é uma boa correção. Centralizar `"1"`, `"0"`, `"yes"`, `"no"`, `"sim"`, `"não"`, `"on"` e `"off"` para `"true"`/`"false"` evita que clientes diferentes deixem flags booleanas em formato ambíguo.

Ponto de atenção: não encontrei teste específico para `_normalize_boolean_value()` ou `update_config()` cobrindo esses tokens. Há testes para o toggle atômico gravar `"true"`/`"false"`, mas eu adicionaria cobertura direta para esta normalização porque ela virou uma regra de integridade operacional.

### `src/features/automacao/hooks/useAutomacaoDashboard.ts`

Ponto positivo: `serializeConfigField()` agora trata booleanos antes de `Number(...)`. Isso corrige diretamente o caso `Number(true) = 1` que apareceu no audit log.

Ponto de atenção: não encontrei teste frontend específico para essa serialização. Se houver infraestrutura de testes no frontend, vale cobrir pelo menos `telefonia_cron_sync_ativa: true -> "true"` e `false -> "false"`.

### `src/features/automacao/schemas.ts`

Ponto de atenção: os defaults do schema frontend ainda estão desalinhados com os novos defaults operacionais:

- `max_retries`: `4`
- `retry_intervalo_minutos`: `15`
- `lookback_dias`: `1`

Esses defaults só aparecem em fallback de parse/UI, mas ainda podem confundir a tela em falha de API ou resposta parcial. Eu alinharia para `8`, `60` e `3`.

### `docs/integracoes/huawei/HUAWEI_D1_CONFIG_GUIDE.md`

O guia é útil e ataca a raiz operacional do problema. Porém há um detalhe de SQL na query de audit log:

```sql
WHERE alterado_em >= NOW() - INTERVAL '7 days'
  AND chave LIKE 'huawei_%' OR chave = 'automacao_hibrida_ativa'
```

Por precedência de operadores, isso equivale a:

```sql
(alterado_em >= NOW() - INTERVAL '7 days' AND chave LIKE 'huawei_%')
OR chave = 'automacao_hibrida_ativa'
```

Ou seja, pode trazer `automacao_hibrida_ativa` de qualquer data. Eu corrigiria para:

```sql
WHERE alterado_em >= NOW() - INTERVAL '7 days'
  AND (chave LIKE 'huawei_%' OR chave = 'automacao_hibrida_ativa')
```

## 4. Avaliação do `fix_automacao.sql`

O SQL resolve os três valores principais no banco:

- `huawei_d1_max_retries -> 8`
- `huawei_d1_lookback_dias -> 3`
- `huawei_d1_horario_execucao -> 06:00`

Mas há um problema no audit do horário. O script faz primeiro o `UPDATE` e depois executa:

```sql
INSERT INTO configuracoes_audit_log (...)
SELECT 'huawei_d1_horario_execucao', valor, '06:00', ...
  FROM configuracoes WHERE chave = 'huawei_d1_horario_execucao';
```

Nesse ponto, `valor` já tende a ser `06:00`, então o `valor_antes` do audit pode ficar errado. Eu corrigiria com CTE capturando o valor anterior antes do update, por exemplo:

```sql
WITH anterior AS (
  SELECT valor AS valor_antes
    FROM configuracoes
   WHERE chave = 'huawei_d1_horario_execucao'
),
upd AS (
  UPDATE configuracoes
     SET valor = '06:00', atualizado_em = CURRENT_TIMESTAMP
   WHERE chave = 'huawei_d1_horario_execucao'
   RETURNING chave
)
INSERT INTO configuracoes_audit_log (chave, valor_antes, valor_depois, alterado_por, motivo, origem)
SELECT 'huawei_d1_horario_execucao', anterior.valor_antes, '06:00', 'lucas',
       'fix automacao: rodar apos Huawei finalizar upload D-1', 'script'
  FROM anterior;
```

Se o SQL já foi aplicado, isso não invalida a correção funcional, mas deixa a trilha de auditoria menos precisa para esse campo.

## 5. Validação local executada

Rodei os testes Python relevantes para D-1 e automação com `sys.path` apontando para `backend`:

```bash
backend\.venv\Scripts\python.exe -c "import sys,unittest; sys.path.insert(0,'backend'); suite=unittest.defaultTestLoader.loadTestsFromNames(['tests.test_huawei_d_minus_1','tests.test_automation_cron']); result=unittest.TextTestRunner(verbosity=2).run(suite); raise SystemExit(0 if result.wasSuccessful() else 1)"
```

Resultado:

- `19` testes executados
- `19` passaram

Não rodei `npm run build` nem a suíte completa nesta avaliação, porque o objetivo aqui foi revisar o relatório e os pontos diretamente associados ao incidente.

## 6. Riscos restantes

1. **Banco ainda tem precedência sobre o código.** Se o SQL não for aplicado, o commit novo não muda o comportamento operacional da produção.
2. **Datas perdidas exigem recuperação manual.** `20260522` não deve reaparecer sozinho no tracker; `20260523` pode estar preso como `empty` com uma tentativa.
3. **Deploy precisa ser confirmado.** A normalização booleana e o fix de UI só valem em produção depois da revisão nova do Cloud Run.
4. **OBS pode continuar vazio por causa externa.** Se após `06:00 BRT` os ciclos continuarem sem arquivos, a próxima hipótese deve ser disponibilidade/entrega no bucket Huawei, não Scheduler.
5. **Defaults ainda desalinhados em alguns fallbacks.** Backend e frontend têm pontos secundários que ainda preservam `4/1/15`, apesar dos novos defaults recomendados.
6. **Cobertura de teste incompleta para a regressão principal de booleano.** O risco foi mitigado em duas camadas, mas falta teste direto para impedir retorno do bug.

## 7. Próxima sequência recomendada

1. Corrigir o trecho de audit do `fix_automacao.sql` antes de aplicar, caso ainda não tenha sido executado.
2. Aplicar o SQL no Neon e verificar:

```sql
SELECT chave, valor, atualizado_em
  FROM configuracoes
 WHERE chave IN (
   'huawei_d1_max_retries',
   'huawei_d1_lookback_dias',
   'huawei_d1_horario_execucao',
   'huawei_d1_enabled',
   'telefonia_cron_sync_ativa',
   'automacao_hibrida_ativa'
 );
```

3. Confirmar no Cloud Run que o commit `ca706d7` foi implantado.
4. Recuperar manualmente `20260522` e `20260523` com `force=true`.
5. Monitorar por 24 horas:

```sql
SELECT date_str, status, attempts, last_attempt_at, last_error
  FROM huawei_d_minus_1_runs
 ORDER BY date_str DESC
 LIMIT 10;
```

6. Depois do incidente estabilizado, fazer um pequeno hardening:

- alinhar fallbacks de `executar_d_minus_1_pipeline()` para `8/60/3`;
- alinhar defaults de `PipelineConfigSchema` para `8/60/3`;
- adicionar testes para normalização booleana em `configuration.update_config`;
- adicionar teste para serialização booleana no frontend;
- corrigir a query do guia com parênteses no `AND/OR`.

## 8. Conclusão

Minha avaliação é que o diagnóstico do ajuste 3 está correto e que o commit `ca706d7` resolve uma parte importante do problema, principalmente no código novo e na defesa contra booleanos ambíguos. O ponto crítico é operacional: sem atualizar os valores já persistidos no Neon e sem recuperar as datas afetadas, a produção pode continuar aparentando que a automação roda, mas sem baixar os lotes esperados.

Eu classificaria o estado atual como **correção de código aplicada, mas incidente ainda pendente de fechamento operacional**.
