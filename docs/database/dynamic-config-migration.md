# Migração para Configuração DB-First (Auditoria NSTECH)

> **Para a próxima IA que abrir este documento:** Leia esta seção *inteira* antes de tocar
> em qualquer ponto do plano. O arquivo serve como mapa de "onde mora cada coisa hoje" +
> ordem segura de migração para tornar o sistema editável em runtime sem deploy.
> Atualize-o quando concluir uma etapa (mudando o status no checklist).

- **Documento criado:** 2026-05-15
- **Autor:** Claude Opus 4.7 (sessão pós-1.3.66)
- **Projeto Neon:** `auditoria-nstech-2` (id `quiet-term-98076087`, região `aws-sa-east-1`, PG 17)
- **App version base:** 1.3.66
- **Branch alvo:** `main`

---

## 1. TL;DR (4 frases)

1. Quase tudo que MUDA por operação (operadores, usuários, créditos Huawei, automação) já vive
   no Neon — as tabelas estão criadas e os repositórios em `backend/repositories/` cobrem CRUD.
2. O que continua **engessado em arquivo** e bloqueia agilidade: prompts de IA
   (`backend/config/prompts.json`), correções fonéticas (`backend/config/text_corrections.json`),
   mapeamento setor cru→canônico (3 dicionários hardcoded em Python) e — o mais crítico — o
   **catálogo de setores/alertas/critérios** que a classificação lê do YAML
   `backend/db/scoring_rules.yaml`, **não** do banco.
3. Hoje o YAML é seedado pra dentro de `audit_sectors/audit_alerts/audit_criteria` mas a
   classificação relê SEMPRE do YAML em runtime — qualquer edição na UI seria sobrescrita
   no próximo deploy/seed. **Inverter essa direção é o ganho de maior ROI.**
4. O plano abaixo está ordenado por (a) maior agilidade ganha por menor risco; cada item tem
   tabela alvo, repositório, contrato de auditoria (`*_audit_log`) e critério de "pronto".

---

## 2. Estado atual: onde mora cada coisa

### 2.1 Já está em DB (editável via repository)

| Domínio | Tabela | Repositório | Editável via UI? | Volume |
|---|---|---|---|---|
| Usuários do sistema | `users` | `repositories/auth_users.py` | Sim (admin) | 27 linhas |
| Colaboradores (operadores) | `colaboradores` | `repositories/operators.py` | Sim (admin) | 218 linhas |
| Setores auditáveis | `audit_sectors` | `repositories/admin_criteria.py` | **Lido**, mas catálogo real vem do YAML | 13 linhas |
| Alertas por setor | `audit_alerts` | `repositories/admin_criteria.py` | Idem | 77 linhas |
| Critérios por alerta | `audit_criteria` | `repositories/admin_criteria.py` | Idem | 1.159 linhas |
| Configurações chave-valor | `configuracoes` | `repositories/configuration.py` | Sim (parcial — tela admin) | 37 chaves |
| RAG (POPs vetorizados) | `procedimento_chunks` | n/d | Não | n/d |
| Drafts de auditoria | `audit_drafts` | `repositories/audits.py` | Sim (auditor) | n/d |
| Feedback de gestores | `gestor_feedbacks` | `repositories/supervisor_feedback.py` | Sim | n/d |
| Fila de revisão | `fila_revisao_classificacao` | `repositories/classification_review.py` | Sim | n/d |

### 2.2 Configurações genéricas em `public.configuracoes`

Tabela é um KV puro (`chave TEXT PK, valor TEXT, descricao TEXT, atualizado_em TEXT`). Hoje já tem:

- **Credenciais Huawei** (`huawei_ak`, `huawei_sk`, `huawei_app_key`, `huawei_app_secret`,
  `huawei_obs_*`, `huawei_cms_url`, `huawei_fs_url`, `huawei_portal_url`, `huawei_proxy_*`,
  `huawei_ccid`, `huawei_vdn`, `huawei_auth_mode`).
- **Knobs da automação D-1** (`huawei_d1_enabled`, `huawei_d1_horario_execucao`,
  `huawei_d1_lookback_dias`, `huawei_d1_limite_ligacoes`, `huawei_d1_max_retries`,
  `huawei_d1_retry_intervalo_minutos`, `huawei_cota_max_por_operador_mes`).
- **Locks/flags** (`automation_engine_lock`, `automacao_is_paused/cancelled`, `sync_lock`,
  `huawei_d1_run_lock`, `telefonia_cron_sync_ativa`, `robo_habilitado`).
- **RPA legado** (`rpa_url_login`, `rpa_usuario`, `rpa_senha`).
- **Prompt global** (`ia_prompt_global`) — **ESTE É O ÚNICO PROMPT JÁ EM DB**.
- **Tema visual** (`tema_visual`).

⚠️ **Limitação:** sem coluna `tipo` (string vs json vs int vs secret), sem versionamento,
sem `audit_log`, sem trail de quem mudou. Isso precisa ser corrigido na primeira fase
(ver §4.1).

### 2.3 Ainda em arquivos (não editável em runtime)

| Arquivo | O que carrega | Lido em | Frequência de mudança |
|---|---|---|---|
| `backend/db/scoring_rules.yaml` | **Setores + alertas + critérios + pesos** (catálogo oficial) | `db/scoring_loader.py` (chamado por `classification.py:load_audit_criteria_catalog` com `@lru_cache`) | Alta — POPs mudam |
| `backend/config/prompts.json` | Prompts do GPT (regras Mondelez, senha, paradas, despedidas, fatal_flags, etc.) + prompt de transcrição + safety nets | `services.py`, `audit_evaluator.py` | Alta — tunagem constante |
| `backend/config/text_corrections.json` | ~150+ regex de correção fonética (Opentech, BAS, Mondelez, etc.) + speaker prefixes | `services.py` (transcrição) | Média — quando aparece nova alucinação |
| `backend/config/huawei_capabilities.md` | Catálogo de endpoints Huawei AICC suportados | doc-only? | Baixa — só doc |
| `backend/data/operadores_seed.json` | Seed inicial de operadores | bootstrap apenas | Histórico (substituído pela tabela) |
| `backend/gcp-key.json` | Service account GCP | runtime (Cloud Run) | Nunca (rotacionar via Secret Manager) |

### 2.4 Hardcoded em Python (não editável sem deploy)

| Constante | Arquivo:linha | Função | O que afeta |
|---|---|---|---|
| `sector_alias_map` | `backend/classification.py:767` | `_resolve_db_sector_alias` | Guardrail de setor (UTI/BAS/etc.) |
| `_SECTOR_ALIASES` | `backend/repositories/operators.py:197` | `_matches_operador_sector` | Match operador↔setor |
| Regras supervisor/escala/setor (Miralha, Taborda, Unilever, Mondelez, Fênix, BBM, RJ→UTI) | `backend/repositories/operators.py:210-267` | `map_db_sector_to_classification_sector` | Resolução canônica do setor a partir do RH |
| `_FILENAME_SECTOR_MAP` | `backend/classification.py:580` | `parse_filename` | Hint de setor por keyword no filename |
| `_NON_NAME_TOKENS` | `backend/classification.py:596` | `parse_filename` | Tokens a ignorar |
| `_ALERT_ID_ALIASES` | `backend/classification.py:66` | Normalização de alertas legados | Compat com IDs antigos |
| `_OPERATIONAL_SECTORS` / `_OPERATIONAL_SIBLINGS` | `backend/classification.py:199,385` | Replicação de alertas BAS para sibling sectors | Catálogo derivado |
| `TEMPERATURE_ALERTS_BY_CONTEXT`, `*_SIGNAL_WEIGHTS` (POSITION, PRIORITY, POLICE, PARADA, DESVIO) | `backend/classification.py:1056-1124` | Heurística pré-IA | Score interno de signals |

### 2.5 Quem é a "fonte da verdade" hoje

```
[scoring_rules.yaml]  ──seed──▶  [audit_sectors / audit_alerts / audit_criteria]
       │                                      ▲
       │                                      │ (admin UI escreve aqui — mas é sobrescrito)
       └─── lru_cache ──▶ classification.py
                                ▼
                         (decide alert_id)
```

**Resultado prático:** se um auditor edita um critério na tela admin, a mudança vai pro DB
mas a IA continua usando o YAML em memória. No próximo deploy, o seed reaplica o YAML.
Isso é a **causa raiz da percepção de "sistema engessado"**.

---

## 3. Padrão de auditoria de mudanças (PRÉ-REQUISITO universal)

Antes de migrar qualquer coisa, criar o padrão. Toda tabela editável em runtime deve ter
uma tabela espelho `*_audit_log`:

```sql
CREATE TABLE configuracoes_audit_log (
  id            BIGSERIAL PRIMARY KEY,
  chave         TEXT NOT NULL,
  valor_antes   TEXT,
  valor_depois  TEXT,
  alterado_por  TEXT NOT NULL,         -- users.username
  alterado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  motivo        TEXT,                   -- preenchido pela UI ("ajuste pós-incidente X")
  origem        TEXT NOT NULL DEFAULT 'ui'  -- 'ui' | 'seed' | 'api' | 'script'
);
CREATE INDEX idx_configuracoes_audit_chave_em ON configuracoes_audit_log (chave, alterado_em DESC);
```

E um trigger ou (preferencialmente) wrapper no repository:

```python
def update_config(get_connection, chave: str, valor: str, *, alterado_por: str, motivo: str = ""):
    # 1. SELECT valor_atual
    # 2. INSERT no audit_log
    # 3. UPDATE configuracoes
    # tudo na mesma transação
```

**Regra:** nenhum endpoint admin pode modificar tabela "viva" sem passar pelo wrapper que
grava no audit_log. A revisão de PR vai exigir isso.

---

## 4. Plano de migração (ordenado por ROI/risco)

> Cada fase é independente, deployável separada e tem critério de "pronto" verificável.

### Fase 0 — Infraestrutura de auditoria (PRÉ-REQUISITO, ~1 dia)

**Por que primeiro:** sem audit_log, qualquer mudança em runtime fica invisível. Já tivemos
incidentes onde "alguém mexeu no prompt" sem trail.

- [ ] Criar `configuracoes_audit_log` (DDL acima).
- [ ] Adicionar coluna `tipo TEXT NOT NULL DEFAULT 'string'` em `configuracoes` com CHECK em
      `('string','int','float','bool','json','secret')`.
- [ ] Adicionar coluna `is_secret BOOLEAN DEFAULT false` (mascarar no GET de listagem).
- [ ] Refatorar `repositories/configuration.py:update_config` para exigir `alterado_por`
      e gravar no audit_log na mesma transação.
- [ ] Adicionar middleware no router admin que injeta `current_user.username` em todas as
      chamadas de mutate.
- **Pronto quando:** UPDATE direto no DB sem `alterado_por` é rejeitado por NOT NULL no
  audit_log; UI mostra "última alteração: Lucas, 14/05 14:32".

### Fase 1 — Inverter direção: DB como fonte para catálogo de critérios (ALTO ROI, MÉDIO RISCO)

**Por que segundo:** é o item de maior impacto operacional. Auditor mestre quer ajustar peso
de critério ou adicionar alerta sem PR. **Concluída em 2026-05-15 (1.3.68 + 1.3.69).**

- [x] Migrar `db/seed_data.py` para rodar **uma única vez** (idempotente, com `ON CONFLICT
      DO NOTHING`), nunca sobrescrever em deploys subsequentes. — **Fase 1.2 / 1.3.69**
- [x] Substituir `classification.py:load_audit_criteria_catalog` para ler de
      `audit_sectors + audit_alerts + audit_criteria` em vez de `scoring_rules.yaml`.
      Manter o `@lru_cache(maxsize=1)` mas adicionar invalidação via endpoint
      `POST /api/admin/criteria/cache/invalidate`. — **Fase 1.1 / 1.3.68**
- [x] Mover `pop_ref` para coluna em `audit_alerts`. — **Fase 1.1 / 1.3.68**
- [ ] Mover `_OPERATIONAL_SIBLINGS` ("alertas de BAS replicam pra transferencia/distribuicao/
      fenix/bbm") para uma tabela `audit_alert_sector_aliases` ou coluna `applies_to_sectors
      TEXT[]`. **Adiado**: lógica continua em código (`_apply_operational_siblings` em
      `classification.py`). Mover só quando aparecer demanda real de ajuste.
- [x] Criar 3 `audit_*_audit_log` (sectors/alerts/criteria) com `payload_antes/depois`
      JSONB. — **Fase 1.1 / 1.3.68**
- [x] Criar UI admin para CRUD de critério/alerta/setor com campo `motivo` obrigatório
      + drawer de histórico (diff antes/depois). — **Fase 1.3 / 1.3.70**
- [x] Renomear `scoring_rules.yaml` → `scoring_rules.bootstrap.yaml` e mover pra
      `backend/db/seeds/`. — **Fase 1.2 / 1.3.69**
- **Pronto quando:** auditor altera peso de um critério na UI, IA usa o novo peso na próxima
  triagem (sem deploy), e o audit_log mostra a mudança. **✅ Fase 1 fechada
  (backend + UI).**

### Fase 2 — Mapeamento setor cru→canônico em DB (MÉDIO ROI, BAIXO RISCO, ~1 dia)

**Por que:** todo bug de "operador X foi para o setor errado" hoje precisa de PR em
`classification.py` ou `repositories/operators.py`. RH adiciona escala nova → quebra.

- [x] Criar tabela `sector_aliases` (com pattern_type ampliado: setor_exact/startswith/
      contains, escala_contains, supervisor_contains, organizacao_contains/startswith;
      `canonical_sector_id` TEXT sem FK para preservar divergencia historica
      `celula_atendimento` vs `receptivo`) + `sector_aliases_audit_log` JSONB. — **1.3.71**
- [x] Seed inicial com 52 regras consolidando `sector_alias_map`, `_SECTOR_ALIASES`,
      o ladder de `map_db_sector_to_classification_sector` e o ladder de
      `_map_organizacao_telefonia_to_sector`. — **1.3.71**
- [x] Substituir as 4 funções (3 dicts + 2 ladders) por delegacao a
      `repositories/sector_aliases.resolve_canonical_sector` e `get_setor_exact_aliases`.
      `_matches_operador_sector` mantida (semantica distinta) mas alimentada pelo
      cache DB. — **1.3.71**
- [x] **Cuidado de coerência (validado):** script `validate_sector_aliases_parity.py`
      compara OLD (logica hardcoded copiada) vs NEW (DB-backed) em 78 combinacoes
      `(setor, escala, supervisor)` extraidas de `colaboradores` + 14 alias-dict
      legados + 13 smoke cases. **Zero diff.**
- [x] Backend router `/api/admin/sector-aliases` (GET/POST/PUT/DELETE + audit-log +
      cache invalidate). UI admin frontend e Fase 2.1 (opcional). — **1.3.71**
- **Pronto quando:** ~~adicionar nova escala "RJ-VERDE" via UI faz operadores caírem em UTI~~
  **Backend pronto, edicao via API ja funciona. UI frontend pendente em Fase 2.1.**

### Fase 3 — Prompts da IA em DB (ALTO ROI, MÉDIO RISCO, ~2 dias)

**Por que:** `prompts.json` muda toda semana. Hoje exige PR + deploy + 5min CI.

- [ ] Criar tabela:
  ```sql
  CREATE TABLE ai_prompts (
    id              BIGSERIAL PRIMARY KEY,
    chave           TEXT NOT NULL,           -- "audit_system.regra_senha"
    versao          INTEGER NOT NULL DEFAULT 1,
    conteudo        TEXT NOT NULL,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    descricao       TEXT,
    criado_por      TEXT NOT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chave, versao)
  );
  CREATE INDEX idx_ai_prompts_chave_ativo ON ai_prompts (chave) WHERE ativo;
  ```
  (Versionamento embutido — em vez de update destrutivo, INSERT nova versão e desativa anterior.)
- [ ] Migrar `prompts.json` para seed inicial (versao=1, ativo=true).
- [ ] Refatorar `services.py` / `audit_evaluator.py` para ler de `get_prompt(chave)` em vez
      de `prompts["audit_system"]["regra_senha"]`.
- [ ] UI admin com diff entre versões + botão "rollback".
- [ ] **Cache:** prompts são lidos por requisição — usar `@lru_cache(maxsize=128)` ou
      Redis se virar gargalo. Invalidar no save.
- **Pronto quando:** auditor mestre muda regra_senha pela UI, próxima auditoria usa a nova
  regra; UI mostra "ativa desde 2026-05-15 14:32 por Lucas".

### Fase 4 — Correções fonéticas em DB (BAIXO ROI, BAIXO RISCO, ~0.5 dia)

**Por que:** `text_corrections.json` cresce sempre que aparece nova alucinação. Hoje só Lucas
sabe editar.

- [ ] Tabela `text_corrections (id, target, pattern, ativo, criado_por, criado_em)` —
      lista achatada (sem nesting de target).
- [ ] Migrar JSON em seed.
- [ ] UI admin "adicionar correção" com teste interativo (input de texto + preview do output
      pós-regex) — evita regex quebrada em produção.
- **Pronto quando:** auditor adiciona "\bAupentec\b" → "Opentech" pela UI e a próxima
  transcrição já corrige.

### Fase 5 — Heurísticas de signals e filename map em DB (BAIXO ROI, MÉDIO RISCO, opcional)

**Por que:** afetam pré-IA, mudam pouco. Só mover se aparecer demanda real.

- [ ] Tabelas `signal_weights (categoria, termo, peso)` e `filename_keyword_map (keyword,
      sector_id)`.
- [ ] Migrar constantes (`POSITION_SIGNAL_WEIGHTS`, etc., e `_FILENAME_SECTOR_MAP`).
- **Status:** **NÃO FAZER** até alguém pedir; risco/benefício ruim.

### Fase 6 — Secrets em Secret Manager (PARALELO, qualquer hora)

**Por que:** `huawei_*` e `gcp-key.json` estão em texto puro hoje. Não é issue de
agilidade — é segurança.

- [ ] Mover credenciais Huawei de `configuracoes` para Google Secret Manager (Cloud Run já
      tem service account com acesso).
- [ ] Mover `gcp-key.json` para Workload Identity (eliminar arquivo).
- [ ] Manter chaves não-secret (`huawei_d1_enabled`, etc.) em `configuracoes`.
- **Status:** trilha paralela, não bloqueia as outras fases.

---

## 5. Convenções para evitar regressão

1. **Toda nova config dinâmica passa pelo padrão Fase 0** (audit_log obrigatório, `tipo`,
   `is_secret`, `alterado_por`).
2. **Nunca duplicar fonte da verdade.** Se um valor existe em DB, remover o fallback hardcoded
   no código (não deixar `os.getenv("X") or db_value` — fica ambíguo).
3. **Cache invalidation explícita.** Toda função com `@lru_cache` que lê do DB precisa de
   endpoint para invalidar (POST /api/admin/cache/invalidate?key=...). Senão UI mostra
   "salvo" mas IA continua usando valor antigo até o próximo restart.
4. **Versionamento para o que é crítico** (prompts, critérios). Para o resto (correções
   fonéticas, sector aliases) basta audit_log.
5. **Testes de integração antes de migrar.** Cada fase precisa de teste que rode triagem em
   ligação real e compare resultado antes/depois. Já temos `backend/tests/` —
   adicionar `test_dynamic_config_*` por fase.
6. **Documentar no `MEMORY.md` de toda IA cada fase concluída** — formato:
   `Fase N (DD/MM/AAAA): <tabela X> agora dinâmica, hardcoded removido em <arquivo:linha>.`

---

## 6. Checklist mestre

> Atualize aqui ao concluir cada fase.

- [x] **Fase 0** — Infra de auditoria (`configuracoes_audit_log`, coluna `tipo`, wrapper) — `1.3.67` / commit `8d1c902`
- [x] **Fase 1.1** — Catálogo DB-first (inverter `load_audit_criteria_catalog`, criar
      3 `audit_*_audit_log`, coluna `pop_ref`, CRUD com trail JSONB, cache invalidation) — `1.3.68` / commit `4fc1cb8`
- [x] **Fase 1.2** — Seed do catálogo não-destrutivo (aborta se DB populado, YAML
      movido para `seeds/scoring_rules.bootstrap.yaml`) — `1.3.69` / commit `796c281`
- [x] **Fase 1.3** — UI admin CRUD com campo `motivo` obrigatório + drawer de histórico
      (lê `GET /api/admin/criteria/audit-log`). Frontend only. — `1.3.70`
- [x] **Fase 2** — `sector_aliases` em DB (consolidar 3 dicionarios + 2 ladders);
      52 regras seedadas; backend + script de parity prontos; UI admin frontend
      pendente (Fase 2.1). — `1.3.71`
- [ ] **Fase 3** — `ai_prompts` em DB com versionamento
- [ ] **Fase 4** — `text_corrections` em DB
- [ ] **Fase 5** — Heurísticas de signals em DB *(opcional, só se pedirem)*
- [ ] **Fase 6** — Secrets Huawei + GCP em Secret Manager *(trilha paralela)*

---

## 7. Notas para a próxima IA

- **Antes de implementar qualquer fase**, rode a query abaixo no Neon para confirmar que o
  schema descrito ainda bate com a realidade — refactors podem ter mudado nomes:
  ```sql
  SELECT table_name FROM information_schema.tables
   WHERE table_schema='public' ORDER BY table_name;
  ```
- **Não confunda `auditoria-nstech` (id `lingering-poetry-95255161`) com
  `auditoria-nstech-2` (id `quiet-term-98076087`).** O segundo é a produção atual. O primeiro
  é o legado pré-migração (ver `docs/relatorio_migracao_neon_2026-05-13.md`).
- **`scoring_rules.yaml` tem 3 variantes** (`scoring_rules.yaml`, `scoring_rules_final.yaml`,
  `scoring_rules_updated.yaml`). Só o primeiro é lido pelo código. Os outros dois podem ser
  removidos ao concluir a Fase 1, mas confirme com `grep` antes.
- **Há `worktrees` em `.claude/worktrees/`** com cópias de `auth_users.py` etc. — são
  experimentos de outras sessões, NÃO leia para entender o estado real. Sempre use os
  arquivos em `backend/repositories/`.
- **`configuracoes.atualizado_em` é `text`, não `timestamptz`** — herança da migração SQLite.
  A Fase 0 é uma boa hora para consertar (ALTER COLUMN com USING).
- **Login de teste:** `Lucas` / `admin123` (`role=admin`) — use para testar UIs admin.
- **Versionar log da migração:** ao concluir cada fase, criar `logs/versions/x.y.z.md` no
  formato padrão (BUG-NNN ou FEAT-NNN, severidade, validação) — ver `logs/README.md`.

---

## 8. Apêndice — comandos úteis

```sql
-- Conferir o que está em configuracoes (com preview)
SELECT chave, LEFT(valor, 80) AS valor, descricao, atualizado_em
  FROM configuracoes ORDER BY chave;

-- Conferir contagens das tabelas-base
SELECT
  (SELECT COUNT(*) FROM audit_sectors) AS sectors,
  (SELECT COUNT(*) FROM audit_alerts)  AS alerts,
  (SELECT COUNT(*) FROM audit_criteria) AS criteria,
  (SELECT COUNT(*) FROM colaboradores)  AS colaboradores,
  (SELECT COUNT(*) FROM users)          AS users;

-- Buscar quem mexeu em algo recentemente (depois da Fase 0)
SELECT chave, valor_antes, valor_depois, alterado_por, alterado_em, motivo
  FROM configuracoes_audit_log
 ORDER BY alterado_em DESC LIMIT 50;
```

```bash
# Confirmar branch e tabelas via MCP Neon (de outra sessão)
# project_id=quiet-term-98076087
```
