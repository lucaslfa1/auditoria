# Estrutura do Banco de Dados

> Documento gerado automaticamente pelo DB Knowledge Agent.
> Banco: PostgreSQL (local) | Data: 2026-04-17 11:32


Total: 18 tabelas, 4 views.


## Tabelas

### ai_feedback

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('ai_feedback_id_seq'::regclass) |
| tipo | text | NO |  |
| setor | text | YES |  |
| criterio_id | text | YES |  |
| situacao | text | NO |  |
| correcao | text | NO |  |
| justificativa | text | NO |  |
| exemplo_transcricao | text | YES |  |
| criado_por | text | NO |  |
| ativo | integer | YES | 1 |
| criado_em | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| atualizado_em | timestamp without time zone | YES | CURRENT_TIMESTAMP |

### arquivos_salvos

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('arquivos_salvos_id_seq'::regclass) |
| tipo | text | NO |  |
| conteudo | text | YES |  |
| arquivo | text | YES |  |
| data_analise | text | YES | CURRENT_TIMESTAMP |
| audit_id | integer | YES |  |
| operator_name | text | YES |  |
| sector_id | text | YES |  |
| alert_label | text | YES |  |
| score | real | YES |  |
| metadata_json | text | YES | '{}'::text |
| criado_por | text | YES |  |

### audit_alerts

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | text | NO |  |
| sector_id | text | NO |  |
| label | text | NO |  |
| context | text | YES |  |

### audit_criteria

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('audit_criteria_id_seq'::regclass) |
| alert_id | text | NO |  |
| label | text | NO |  |
| description | text | YES |  |
| weight | real | YES | 1.0 |
| type | text | YES | 'boolean'::text |
| deflator | real | YES | 0 |
| evaluation_type | text | YES | 'auto'::text |
| chave | text | YES |  |

### audit_sectors

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | text | NO |  |
| label | text | NO |  |
| description | text | YES |  |

### audits

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('audits_id_seq'::regclass) |
| timestamp | text | YES |  |
| operator_name | text | YES |  |
| score | real | YES |  |
| max_score | real | YES |  |
| summary | text | YES |  |
| details_json | text | YES |  |
| transcription_json | text | YES |  |
| input_hash | text | YES |  |
| alert_id | text | YES |  |
| alert_label | text | YES |  |
| operator_id | text | YES |  |
| driver_name | text | YES |  |
| source_type | text | YES | 'audio'::text |
| sector_id | text | YES |  |
| audio_quality | text | YES |  |
| audit_scope | text | YES | 'call_quality'::text |
| status | text | YES | 'pending_approval'::text |
| contestation_reason | text | YES |  |
| contested_criteria | text | YES |  |
| contestation_verdict | text | YES |  |
| review_defense | text | YES |  |
| reviewed_by | text | YES |  |
| reviewed_at | text | YES |  |
| ai_feedback | text | YES |  |
| audio_storage_path | text | YES |  |
| audio_original_filename | text | YES |  |
| audio_mime_type | text | YES |  |
| audio_size_bytes | integer | YES |  |
| audit_date | text | YES |  |
| colaborador_id | integer | YES |  |

### colaboradores

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('colaboradores_id_seq'::regclass) |
| nome | text | NO |  |
| supervisor | text | YES |  |
| setor | text | YES |  |
| escala | text | YES |  |
| status | text | YES |  |
| matricula | text | YES |  |
| id_weon | text | YES |  |
| id_huawei | text | YES |  |
| atualizado_em | text | YES | CURRENT_TIMESTAMP |
| id_telefonia | text | YES |  |
| softphone_number | text | YES |  |
| telefonia_account | text | YES |  |
| organizacao_telefonia | text | YES |  |
| tipo_agente | text | YES |  |
| status_telefonia | text | YES |  |
| tipo_escala | text | YES |  |
| auditavel | integer | YES | 1 |

### configuracoes

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| chave | text | NO |  |
| valor | text | YES |  |
| descricao | text | YES |  |
| atualizado_em | text | YES | CURRENT_TIMESTAMP |

### fila_revisao_classificacao

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('fila_revisao_classificacao_id_seq'::regclass) |
| input_hash | text | NO |  |
| nome_arquivo | text | NO |  |
| setor_previsto | text | YES |  |
| alerta_previsto | text | YES |  |
| confianca | real | YES |  |
| operador_previsto | text | YES |  |
| erro | text | YES |  |
| prioridade | text | NO | 'medium'::text |
| motivos_json | text | YES | '[]'::text |
| metadata_json | text | YES | '{}'::text |
| status | text | NO | 'pending'::text |
| criado_em | text | NO |  |
| atualizado_em | text | NO |  |

### gestor_feedbacks

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('gestor_feedbacks_id_seq'::regclass) |
| audit_id | integer | NO |  |
| gestor_nome | text | NO |  |
| feedback_texto | text | NO |  |
| pontos_melhoria | text | NO |  |
| criado_em | text | YES | CURRENT_TIMESTAMP |

### ligacoes_auditadas

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('ligacoes_auditadas_id_seq'::regclass) |
| nome_arquivo | text | NO |  |
| caminho_relativo | text | NO |  |
| hash_arquivo | text | NO |  |
| grupo | text | YES |  |
| subgrupo | text | YES |  |
| setor_referencia | text | YES |  |
| alerta_referencia | text | YES |  |
| qualidade_referencia | text | NO | 'indefinida'::text |
| observacao | text | YES | ''::text |
| criado_em | text | NO |  |
| atualizado_em | text | NO |  |

### procedimento_chunks

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('procedimento_chunks_id_seq'::regclass) |
| source_path | text | NO |  |
| source_hash | text | NO |  |
| setor | text | YES |  |
| alert_id | text | YES |  |
| alert_label | text | YES |  |
| section_title | text | NO |  |
| chunk_index | integer | NO | 0 |
| content | text | NO |  |
| metadata_json | text | NO | '{}'::text |
| created_at | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| updated_at | timestamp without time zone | YES | CURRENT_TIMESTAMP |

### report_exports

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('report_exports_id_seq'::regclass) |
| created_at | text | YES | CURRENT_TIMESTAMP |
| report_kind | text | NO |  |
| file_format | text | NO |  |
| filename | text | YES |  |
| media_type | text | YES |  |
| generated_by | text | YES |  |
| operator_name | text | YES |  |
| operator_id | text | YES |  |
| alert_id | text | YES |  |
| alert_label | text | YES |  |
| sector_id | text | YES |  |
| score | real | YES |  |
| max_score | real | YES |  |
| source_type | text | YES |  |
| audit_timestamp | text | YES |  |
| file_size_bytes | integer | YES |  |
| metadata_json | text | YES | '{}'::text |

### resultados_auditoria

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('resultados_auditoria_id_seq'::regclass) |
| ligacao_id | integer | NO |  |
| nota | real | YES |  |
| nota_maxima | real | YES |  |
| resumo | text | YES |  |
| detalhes_json | text | YES | '[]'::text |
| executado_em | text | NO |  |

### resultados_classificacao

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('resultados_classificacao_id_seq'::regclass) |
| ligacao_id | integer | NO |  |
| setor_previsto | text | YES |  |
| alerta_previsto | text | YES |  |
| confianca | real | YES |  |
| operador_previsto | text | YES |  |
| modelo | text | YES |  |
| versao_prompt | text | YES |  |
| acertou_setor | integer | YES |  |
| acertou_alerta | integer | YES |  |
| erro | text | YES |  |
| metadata_json | text | YES | '{}'::text |
| executado_em | text | NO |  |

### schema_metadata

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| key | text | NO |  |
| value | text | YES |  |
| updated_at | timestamp without time zone | YES | CURRENT_TIMESTAMP |

### schema_migrations

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| name | text | NO |  |
| applied_at | text | YES | CURRENT_TIMESTAMP |

### users

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('users_id_seq'::regclass) |
| username | text | NO |  |
| password_hash | text | NO |  |
| role | text | YES | 'admin'::text |
| supervisor_name | text | YES |  |

## Views

### audits_com_colaborador

```sql
 SELECT a.id,
    a."timestamp",
    a.operator_name,
    a.score,
    a.max_score,
    a.summary,
    a.sector_id,
    a.alert_id,
    a.alert_label,
    a.source_type,
    a.status,
    a.ai_feedback,
    a.colaborador_id,
    c.nome AS colaborador_nome,
    c.matricula,
    c.id_huawei,
    c.supervisor,
    c.setor,
    c.escala,
    c.status AS colaborador_status
   FROM (audits a
     LEFT JOIN colaboradores c ON ((a.colaborador_id = c.id)));
```

### ligacoes_boas

```sql
 SELECT id,
    nome_arquivo,
    caminho_relativo,
    hash_arquivo,
    grupo,
    subgrupo,
    setor_referencia,
    alerta_referencia,
    qualidade_referencia,
    observacao,
    criado_em,
    atualizado_em
   FROM ligacoes_auditadas
  WHERE (qualidade_referencia = 'boa'::text);
```

### ligacoes_ruins

```sql
 SELECT id,
    nome_arquivo,
    caminho_relativo,
    hash_arquivo,
    grupo,
    subgrupo,
    setor_referencia,
    alerta_referencia,
    qualidade_referencia,
    observacao,
    criado_em,
    atualizado_em
   FROM ligacoes_auditadas
  WHERE (qualidade_referencia = 'ruim'::text);
```

### ligacoes_zeradas

```sql
 SELECT id,
    nome_arquivo,
    caminho_relativo,
    hash_arquivo,
    grupo,
    subgrupo,
    setor_referencia,
    alerta_referencia,
    qualidade_referencia,
    observacao,
    criado_em,
    atualizado_em
   FROM ligacoes_auditadas
  WHERE (qualidade_referencia = 'zerada'::text);
```
