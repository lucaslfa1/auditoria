# Revisao do Banco Neon para Migracao Portainer

**Data:** 2026-05-22
**Escopo:** revisao read-only antes de qualquer dump
**Banco oficial informado:** Neon `auditoria-nstech-2`
**Projeto Neon confirmado:** `quiet-term-98076087` (`aws-sa-east-1`, PostgreSQL 17)
**Evidencia tecnica:** `export/db_review/auditoria_nstech_2_readonly_review_2026-05-22.json`
**Regra operacional fixa:** a automacao Huawei deve trabalhar sempre em janela D-1 usando
o metodo OBS.

## 1. Resultado executivo

Nenhum dump foi gerado e nenhuma alteracao foi aplicada no banco.

O principal achado e bloqueador para migracao e que o projeto Neon `auditoria-nstech-2`
possui duas branches ativas/relevantes com estados divergentes:

| Branch / compute | Uso observado | Schema | Dados historicos |
|---|---:|---:|---:|
| `br-fancy-glade-ack2qv0l` / `ep-falling-hall-ac2t9rln` | `DATABASE_URL` atual local | 36 tabelas, 47 migrations | `audits=0`, `arquivos_salvos=0`, `fila=20`, `huawei_sync_logs=11179` |
| `br-fragrant-pond-acrhm1k7` / `ep-aged-river-acr5e219` | branch documentada em um relatorio de migracao | 30 tabelas, 34 migrations | `audits=436`, `arquivos_salvos=170`, `fila=2`, `huawei_sync_logs=6504` |

Conclusao: **nao liberar dump nem preparar imagem de banco enquanto a branch canonica nao
for decidida e reconciliada**. A branch atualmente configurada tem o schema mais novo, mas
nao contem as auditorias historicas. A outra branch contem historico operacional, mas esta
atrasada em schema/migrations.

Observacao operacional: qualquer reconciliacao ou migracao precisa preservar a regra de
automacao **D-1 via OBS**. Nao deve haver reprocessamento livre por janelas arbitrarias
ou troca para metodo API/consulta direta sem uma decisao manual separada, porque isso
altera cota, deduplicacao, rastreabilidade de arquivos e interpretacao dos logs Huawei.

## 2. Inventario da branch atualmente configurada

Conexao sanitizada: `ep-falling-hall-ac2t9rln-pooler.sa-east-1.aws.neon.tech`, database
`neondb`, `sslmode=require`, usando host pooler.

Resumo do schema:

- 36 tabelas base, 4 views, 464 colunas, 263 constraints, 122 indexes.
- Extensoes instaladas: `plpgsql`, `vector`.
- Views esperadas presentes: `audits_com_colaborador`, `ligacoes_boas`,
  `ligacoes_ruins`, `ligacoes_zeradas`.
- Nenhuma tabela critica da lista atual ficou ausente.
- Tabelas extras observadas: `audit_alerts_audit_log`, `audit_sectors_audit_log`
  (na pratica, fazem parte da trilha DB-first e devem ser consideradas esperadas).

Contagens principais:

| Tabela | Linhas |
|---|---:|
| `huawei_sync_logs` | 11179 |
| `audit_criteria` | 1051 |
| `colaboradores` | 217 |
| `automation_cycle_runs` | 147 |
| `procedimento_chunks` | 55 |
| `ai_feedback` | 41 |
| `ai_prompts` | 33 |
| `media_files` | 30 |
| `fila_revisao_classificacao` | 20 |
| `huawei_d_minus_1_runs` | 2 |
| `audits` | 0 |
| `arquivos_salvos` | 0 |
| `transcript_candidates` | 0 |
| `ligacoes_auditadas` | 0 |

## 3. Achados criticos

1. **Divergencia de branch no mesmo projeto Neon**
   - `br-fancy-glade` tem schema atual, mas sem auditorias historicas.
   - `br-fragrant-pond` tem dados historicos, mas schema defasado.
   - A documentacao tambem diverge: alguns arquivos apontam para `ep-aged-river`,
     enquanto a configuracao local atual aponta para `ep-falling-hall`.

2. **Historico de auditorias ausente na branch atualmente configurada**
   - `audits=0`, `arquivos_salvos=0`, `transcript_candidates=0`.
   - O relatorio de GCS de 2026-05-22 tambem registrou `audits=0` na base atual.
   - A branch antiga tem `audits=436` e `arquivos_salvos=170`, o que indica que uma
     migracao direta a partir da branch atual perderia o historico operacional.

3. **Migrations/metadados inconsistentes**
   - A branch atual tem `schema_migrations=47`.
   - Existem duas entradas para a migration de `media_files`:
     `20260522_001_media_files` e `m20260522_001_media_files`.
   - `schema_metadata.migration.last_applied=20260522_001_media_files`, mas
     `schema_metadata.migration.latest_known=m20260521_001_transcript_candidates`.
   - Causa provavel: nome manual/aplicado divergiu do `MIGRATION_NAME` no arquivo
     `backend/db/migration_steps/m20260522_001_media_files.py`.

4. **Cadastro de colaboradores inconsistente na branch atual**
   - 5 grupos com `id_huawei` duplicado: `2428` (5 linhas), `2505` (3), `665` (3),
     `2533` (2), `2539` (2).
   - 5 grupos com `matricula` duplicada.
   - 5 colaboradores ativos/auditaveis sem `id_huawei`.
   - A branch com historico (`br-fragrant-pond`) nao mostrou duplicidade de `id_huawei`
     no check agregado, mas ainda tem 17 auditorias com operador sem `colaborador_id`.

5. **Rastreamento de midia ainda incompleto**
   - `media_files` tem 30 linhas na branch atual.
   - Relatorio GCS do mesmo dia registra 1858 objetos fisicos e 4.33 GB.
   - Isso confirma que `media_files` ainda e um rastreamento parcial, nao inventario
     completo da midia. Para migracao, o banco sozinho nao representa todos os arquivos.

6. **Regra D-1 via OBS deve ser tratada como contrato, nao configuracao flexivel**
   - A tabela `huawei_d_minus_1_runs` existe para rastrear execucoes por data D-1.
   - O metodo oficial da rotina e OBS: descobrir/listar arquivos no OBS Huawei, baixar
     somente a janela D-1, registrar deduplicacao/cota e entao alimentar triagem/auditoria.
   - A migracao precisa preservar historico, locks e status dessa tabela sem reinterpretar
     os periodos.
   - Variaveis ou configuracoes de lookback devem ser revisadas para nao permitir que a
     automacao regular rode fora de D-1 ou fora do metodo OBS.

## 4. Integridade observada

Branch atual (`br-fancy-glade`):

- `audits`: sem duplicidade ou FK quebrada porque esta vazia.
- `arquivos_salvos`: 0 orfaos, mas tabela vazia.
- `gestor_feedbacks`: 0 orfaos.
- `transcript_candidates`: 0 orfaos, mas tabela vazia.
- `media_files`: 0 `storage_key` vazio e 0 duplicidade de `file_hash`.
- `audit_criteria` e `audit_alerts`: 0 criterios sem alerta e 0 alertas sem setor.
- `huawei_sync_logs`: 0 duplicidade de `call_id`.
- `huawei_d_minus_1_runs`: 2 registros na branch atual, usados como trilha da janela fixa
  D-1 via OBS.

Distribuicao de `huawei_sync_logs` na branch atual:

| Status | Linhas |
|---|---:|
| `skipped_direction` | 5677 |
| `skipped_operator` | 3972 |
| `skipped_non_telefonia` | 1213 |
| `skipped_quota` | 286 |
| `success` | 17 |
| `failed` | 14 |

Branch com historico (`br-fragrant-pond`):

- `audits=436`, `arquivos_salvos=170`.
- Status de auditoria: `awaiting_pair=198`, `pending_approval=121`, `approved=81`,
  `discarded=36`.
- `audits_without_colaborador=17`.
- `duplicate_input_hash_groups=0`, `duplicate_huawei_groups=0`,
  `arquivos_orphans=0`.

## 5. Performance, custo e egress

Sinais de banco:

- `pg_stat_statements` nao esta instalado; portanto nao ha ranking confiavel de queries
  lentas pelo Neon neste momento.
- Maiores objetos na branch atual:
  - `huawei_sync_logs`: ~3.8 MB total.
  - `procedimento_chunks`: ~1.9 MB total, majoritariamente indice vetorial.
  - `audit_criteria`: ~1.0 MB total.
- `procedimento_chunks.idx_procedimento_chunks_embedding` aparece com `idx_scan=0`;
  nao remover ainda, pois estatisticas podem ter sido resetadas e o RAG pode depender
  dele em fluxos especificos.
- `automation_cycle_runs`, `fila_revisao_classificacao`, `ai_feedback` e `schema_metadata`
  tem percentual alto de dead tuples, mas volume absoluto baixo. Nao e bloqueador.

Riscos estaticos no codigo:

- `backend/repositories/analytics.py` busca auditorias aprovadas com `SELECT *` e
  `fetchall()` para calcular metricas. Com historico maior, isso aumenta egress e memoria.
- `backend/repositories/saved_files.py` lista `arquivos_salvos` retornando `conteudo`
  no endpoint de listagem. Se `conteudo` crescer, a tela de lista trafega payload pesado.
- `backend/repositories/audits.py:get_audits_for_export` usa `SELECT a.*` e retorna
  `details_json`/`transcription_json`; precisa ser mantido para export, mas nao deve ser
  reaproveitado por telas de resumo.
- `backend/repositories/classification_review.py` usa casts frequentes
  `metadata_json::jsonb` sobre coluna textual. Funciona hoje, mas para volume maior deve
  migrar `metadata_json` para `JSONB` ou criar colunas/indexes auxiliares.

## 6. Correcoes recomendadas antes de qualquer dump

Ordem obrigatoria:

1. **Congelar a decisao de branch canonica**
   - Escolher explicitamente se a fonte da migracao sera `br-fancy-glade`,
     `br-fragrant-pond` ou uma nova branch reconciliada.
   - Atualizar `.env`, `backend/.env`, Cloud Run/Portainer e documentacao para o mesmo
     compute/branch.

2. **Reconciliar dados historicos vs schema novo**
   - Caminho recomendado: criar branch temporaria a partir da branch com historico,
     aplicar migrations pendentes ate o schema atual e comparar contagens.
   - Alternativa: criar branch temporaria a partir da branch atual e importar apenas
     tabelas historicas da branch antiga (`audits`, `arquivos_salvos`, feedbacks e
     dependencias), com regras claras de conflito.
   - Nao usar dump para Portainer antes dessa reconciliacao.
   - Durante a reconciliacao, preservar `huawei_d_minus_1_runs` e validar que a automacao
     continua calculando somente D-1 via OBS.

3. **Normalizar metadata de migrations**
   - Remover/ignorar a entrada manual duplicada `m20260522_001_media_files` apenas em
     plano separado e aprovado.
   - Corrigir `migration.latest_known` para refletir a ultima migration real conhecida.

4. **Higienizar `colaboradores`**
   - Resolver duplicidades de `id_huawei` e `matricula`.
   - Preencher ou marcar como nao auditavel os ativos/auditaveis sem `id_huawei`.
   - So depois considerar constraints parciais de unicidade para evitar regressao.

5. **Fechar inventario de midia**
   - Decidir se `media_files` deve rastrear todos os 1858 objetos do GCS ou apenas os
     novos arquivos classificados.
   - Documentar que a migracao de banco nao migra bytes de audio; GCS/volume deve ter
     plano separado.

6. **Reduzir egress antes de crescer historico**
   - Trocar consultas de dashboard para agregacoes SQL.
   - Criar endpoints/listagens leves que nao retornem transcricoes completas.
   - Evitar `SELECT *` nos fluxos de lista e analytics.

7. **Fixar contrato D-1 via OBS no deploy Portainer**
   - Documentar no `.env.portainer.example` futuro que a automacao e D-1 via OBS.
   - Validar scheduler/cron para rodar somente a competencia do dia anterior usando OBS.
   - Validar credenciais e variaveis OBS/Huawei antes de considerar a migracao pronta.
   - Bloquear execucoes retroativas amplas como rotina; permitir apenas operacao manual
     controlada e registrada.

## 7. Compatibilidade Portainer futura

Quando a revisao estiver resolvida, o destino deve ser PostgreSQL 17 com suporte a
`pgvector`. O container precisa garantir:

- extensao `vector` disponivel antes do boot da aplicacao;
- volume persistente para dados do Postgres;
- backup/restore testado em ambiente temporario;
- variavel `DATABASE_URL` apontando para o servico Postgres interno;
- volumes separados para logs e midia;
- politica clara para GCS/arquivos antes de desligar Neon.
- scheduler da automacao configurado para D-1 via OBS e validado em homologacao.

O compose atual da aplicacao nao deve ser tratado como imagem completa do banco: ele sobe
somente o app e depende de `DATABASE_URL` externa.

## 8. Estado de pronto para dump

O dump continua bloqueado ate que todos estes itens estejam resolvidos:

- branch canonica definida;
- historico de `audits`/`arquivos_salvos` reconciliado com schema atual;
- migrations/metadados saneados;
- duplicidades de colaboradores tratadas;
- decisao de midia documentada;
- contrato D-1 via OBS documentado e validado;
- consultas pesadas priorizadas ou aceitas formalmente como risco.

Somente depois disso faz sentido planejar `pg_dump`/restore para Portainer.
