# Agente Especialista — Auditoria NSTECH

Você é o agente especialista do projeto Auditoria NSTECH. Esta pasta (`claude_agent/`) é sua base de operações. O projeto raiz está em `../` (um nível acima).

---

## PROTOCOLO DE INICIALIZAÇÃO — execute sempre ao começar

### Passo 1 — Carregar base de conhecimento

Leia **todos** os arquivos em `knowledge/`:

```
Glob: knowledge/*.md
Read: cada arquivo encontrado
```

Se `knowledge/_index.md` estiver vazio ou não existir arquivos além do índice, prossiga direto ao passo 2.

### Passo 2 — Verificar estado atual do projeto

Leia em paralelo:
- `../pendencias/PENDENCIAS.md` — itens pendentes
- `../logs/versions/` — identifique o arquivo mais recente (maior versão) e leia-o

### Passo 3 — Apresentar ao usuário

Mostre:
1. Versão atual do projeto
2. Pendências abertas de alta prioridade
3. Qualquer insight relevante carregado do `knowledge/`

---

## GESTÃO DA BASE DE CONHECIMENTO (RAG file-based)

Durante a sessão, você deve **criar ou atualizar arquivos em `knowledge/`** sempre que descobrir algo não óbvio, resolver um bug, tomar uma decisão arquitetural ou identificar um padrão recorrente.

### Quando criar um arquivo novo

- Resolveu um bug que não estava documentado
- Tomou uma decisão que afeta comportamento do sistema
- Descobriu um padrão de código que outros agentes precisam saber
- Identificou uma armadilha ou comportamento inesperado
- Documentou um fluxo complexo após explorar o código

### Formato de arquivo de conhecimento

```markdown
---
tipo: bug | decisao | padrao | fluxo | armadilha
area: backend | frontend | banco | audio | infra
criado: YYYY-MM-DD
atualizado: YYYY-MM-DD
---

# Título curto e descritivo

## Contexto
O que levou a este conhecimento.

## Conhecimento
O conteúdo principal — seja específico, com nomes de arquivos e linhas quando relevante.

## Como aplicar
Quando e como usar este conhecimento em futuras sessões.
```

### Regras de nomenclatura

- `knowledge/bug_NNN_descricao.md` — para bugs
- `knowledge/decisao_descricao.md` — para decisões arquiteturais
- `knowledge/padrao_descricao.md` — para padrões de código
- `knowledge/fluxo_descricao.md` — para fluxos documentados
- `knowledge/armadilha_descricao.md` — para comportamentos inesperados

### Atualizar o índice

Após criar ou atualizar qualquer arquivo, atualize `knowledge/_index.md` com uma linha resumindo o arquivo.

---

## CONTEXTO DO PROJETO

### Identidade
- Sistema de auditoria de ligações telefônicas usando IA
- Azure OpenAI GPT-4o (avaliação) + Azure Speech STT (transcrição)
- Compliance corporativo: operadores de atendimento avaliados por critérios por setor

### Stack
- **Backend:** FastAPI (Python), PostgreSQL, psycopg2
- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS (dark mode obrigatório)
- **Auth:** Cookie HMAC-SHA256, bcrypt, roles `admin` / `supervisor`

### Estrutura do projeto (raiz = `../`)
```
backend/
  core/
    audit.py          ← orquestra todo o pipeline de auditoria
    transcription.py  ← cadeia de fallback dos provedores de transcrição
    evaluation.py     ← avaliação IA + cálculo de score
  db/
    connection.py     ← get_connection() — única fonte de conexão PG
    migrations.py     ← runner de migrations
    migration_steps/  ← migrations individuais
  config/
    prompts.json      ← prompts externalizados (NUNCA hardcodar no código)
    text_corrections.json ← correções fonéticas + speaker prefixes
  database.py         ← fachada do banco, persist_audit_artifacts() é central
  automation.py       ← auditoria em lote (tem bug conhecido nos critérios)
  main.py             ← entrypoint FastAPI
src/
  features/           ← features React (organizar aqui, não em components/)
  contexts/           ← contextos globais React
logs/versions/        ← histórico de versões (x.y.z.md)
pendencias/           ← PENDENCIAS.md com itens abertos
```

### Banco de dados
- **PostgreSQL** (migrado do Docker local em 2026-04-08)
- Conexão centralizada: `backend/db/connection.py` → `get_connection()`
- Placeholders: sempre `%s` (psycopg2), NUNCA `?` (sqlite3)
- Introspection: `information_schema.tables` e `information_schema.columns`
- Views: `CREATE OR REPLACE VIEW` (não `CREATE VIEW IF NOT EXISTS`)
- NÃO reintroduzir SQLite — compliance exige PostgreSQL

### Transcrição de áudio — regras críticas
- **Fast Transcription REST API** é superior ao Speech SDK para telefonia — não reverter
- **NÃO usar Whisper** — alucina durante silêncio/URA
- **NÃO aplicar noise reduction** em áudio G.729/GSM — degrada qualidade
- Confiança ~52-53% é normal para codec de telefonia — não tratar como erro
- `headroom` pydub: valor BAIXO = volume ALTO (0.5 = bom)

### Mapeamento de setores
| Nome no sistema | Escala RH | Observação |
|-----------------|-----------|------------|
| LP / Central    | CENTRAL-* | transferencia |
| Fênix           | FÊNIX     | supervisor: Adryan Celso |
| BBM             | —         | transferencia + uti-BBM |
| Diálogo         | —         | uti (100%) |
| GRS             | —         | nome antigo de UTI — normalizar no import |

### Boas práticas invioláveis
- Prompts **sempre** em `backend/config/prompts.json` — nunca no código
- Deduplicação via hash SHA-256 — não contornar
- Zeragem 3 camadas: (1) criterionId=senha/fail → (2) fatal_flags da IA → (3) substring fallback
- Dark mode obrigatório em todos os componentes novos
- Features novas em `src/features/<dominio>/` — não em `src/components/` genérico
- **SEMPRE criar `logs/versions/x.y.z.md`** após alterações importantes

### Bugs conhecidos (verificar `knowledge/` para atualizações)
- ~~`automation.py` ~linha 268: `_build_alert_from_classification` recebe `criteria=[]`~~ — RESOLVIDO em v1.3.73 (canonicalize_alert_id + raise `AlertWithoutOfficialCriteriaError`, fluxo retorna `needs_manual_triage` em vez de `criteria=[]` silencioso). 0 ocorrências em prod nos últimos 30 dias.

### Pendências de compliance abertas
- ~~Regra 2 ligações/operador/mês (v1.3.1)~~ — RESOLVIDO em commit `77299af5` (2026-05-14, "split monthly quota limits AI vs Supervisor"). Gate em `routers/audit.py:479-535` (`promote_audit_to_pending_approval`) + `repositories/audits.py:151` (`get_supervisor_audit_count_for_month`, exclui `awaiting_pair` e `discarded`). Auditor é bloqueado com HTTP 400 ao tentar enviar uma 3ª ligação do mesmo operador ao supervisor no mesmo mês; precisa deletar uma existente pra liberar espaço.
- ~~Validação EFETUADA vs RECEPTIVA (v1.3.1)~~ — RESOLVIDO em v1.3.73 (per-alert keyword via `_expected_direction_for_alert`)
- Exibir `fatal_flags` no frontend — `AuditResultSummaryCard.tsx` (v1.3.2)

---

## COMPORTAMENTO DURANTE A SESSÃO

### Antes de editar qualquer arquivo crítico
Leia-o primeiro. Arquivos que exigem leitura prévia obrigatória:
- `backend/core/audit.py`
- `backend/core/transcription.py`
- `backend/core/evaluation.py`
- `backend/automation.py`
- `backend/database.py`
- `backend/db/connection.py`

### Ao finalizar uma tarefa relevante
Pergunte-se: *"O que aprendi nesta sessão que não estava documentado antes?"*
Se houver algo, crie ou atualize o arquivo correspondente em `knowledge/`.

### Versionamento
Após qualquer alteração importante ao projeto, crie `../logs/versions/x.y.z.md` seguindo o template dos arquivos existentes nessa pasta.

### Sessões
Opcionalmente, ao final de sessões longas ou complexas, crie `sessions/YYYY-MM-DD_resumo.md` com decisões tomadas, arquivos alterados e próximos passos.

---

## COMANDOS ÚTEIS (executar em `../`)

```bash
# Backend
cd .. && python backend/main.py

# Frontend
cd .. && pnpm dev

# Testes
cd .. && pytest tests/

# Migrations
cd .. && python -m backend.db.migrations
```
