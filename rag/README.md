# RAG — Retrieval-Augmented Generation

Pasta dedicada ao sistema de aprendizado e recuperação semântica do projeto Auditoria NSTECH.

## Propósito

Centralizar **fontes curadas humanas** (POPs, taxonomias, regras de negócio oficiais) que alimentam o sistema de IA da auditoria — seja como contexto direto nos prompts (injeção por chave) ou como chunks indexados em `pgvector` (busca semântica).

## Estrutura

```
rag/
├── README.md                       # Este arquivo
├── CHANGELOG.md                    # Histórico de versões do knowledge base
├── sources/                        # Fontes oficiais, versionadas em Markdown
│   └── procedimentos_operacionais/ # POPs por setor (Cadastro, Unilever, etc.)
│       ├── _INDEX.md               # Índice com metadata por arquivo
│       ├── cadastro.md
│       ├── checklist.md
│       ├── mondelez.md
│       ├── unilever.md
│       └── areas_de_risco.md
└── schemas/                        # Taxonomias, formatos de chunk e esquemas futuros
```

## Relação com o resto do sistema

```
rag/sources/              instrucoes/
(fonte humana)            (manuais complementares)
      │                           │
      ├───────────┬───────────────┘
                  ▼
       backend/scripts/db_knowledge_agent.py
       (gera knowledge base textual)
                  ▼
       backend/data/rag_training/
       (output gerado — NÃO editar à mão)
                  ▼
       ┌──────────┴───────────┐
       ▼                      ▼
Camada 1: injeção       Camada 2: pgvector
direta no prompt        chunks de POP oficial
(audit_evaluator)       (procedimento_chunks)
```

## Camadas RAG implementadas

### Camada 1 — Injeção direta por chave (`setor`, `alerta`)

Os POPs em `sources/procedimentos_operacionais/` são carregados em memória e o trecho correspondente ao setor/alerta da ligação é injetado no `system_prompt` de `backend/audit_evaluator.get_audit_system_prompt()`.

- **Determinístico**: 100% de recall dos critérios oficiais
- **Rápido**: lookup em dicionário, zero latência
- **Fallback seguro**: se não houver POP para o setor/alerta, cai no prompt atual

### Camada 2 — Busca semântica via pgvector (`procedimento_chunks`)

Infraestrutura adicionada para indexar os POPs oficiais por chunk:

- Migração `m20260416_021_add_procedimento_chunks.py`
- Script `backend/scripts/sync_procedimento_chunks.py`
- Comando `npm run rag:sync-procedimentos`
- Helper `backend/core/rag_triagem.py:buscar_procedimento_chunks`

O sync gera chunks a partir de `rag/sources/procedimentos_operacionais/*.md`.
Se `pgvector` estiver disponível, a coluna `embedding vector(1536)` é criada
pela migração ou pelo sync, e os embeddings usam `text-embedding-3-small` via
Azure OpenAI. Se a extensão ou a chave Azure não estiverem disponíveis, a
tabela continua útil como índice textual e a auditoria mantém o fallback
determinístico da Camada 1.

## Governança

- **Fonte de verdade dos POPs**: `rag/sources/` é canônico para procedimento operacional oficial. `scoring_rules.yaml` segue como fonte ativa de critérios/pesos até reconciliação formal
- **Edição**: arquivos `.md` são editáveis por supervisores; versões rastreadas via Git
- **Deprecação**: itens removidos ficam no `CHANGELOG.md` com motivo; não há soft-delete
- **Metadados por arquivo**: cada POP começa com frontmatter (`setor`, `alertas_cobertos`, `versao`, `ultima_revisao`)

## Como adicionar um novo POP

1. Criar `rag/sources/procedimentos_operacionais/<novo_setor>.md` com frontmatter
2. Adicionar entrada no `_INDEX.md`
3. Registrar em `CHANGELOG.md` com data e descrição
4. Rodar `python -m backend.scripts.db_knowledge_agent` para regenerar o output
5. Rodar `npm run rag:sync-procedimentos` para popular/atualizar `procedimento_chunks`
6. Verificar que `backend/data/rag_training/regras_negocio.md` incluiu o novo conteúdo

## Referências

- `backend/scripts/DB_KNOWLEDGE_AGENT.md` — documentação do agente que consome estas fontes
- `logs/versions/1.3.49-rag-procedimentos-oficiais.md` — versão onde essa estrutura foi criada
