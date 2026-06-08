# RAG Knowledge Base — Changelog

Histórico de mudanças nas fontes curadas do RAG (`rag/sources/`). Segue formato inspirado em [Keep a Changelog](https://keepachangelog.com/).

Apenas alterações no **conteúdo das fontes** entram aqui — alterações de código/pipeline vão para `logs/versions/`.

---

## [2026-04-17] — Atualização e Calibração de Procedimentos RAG

### Adicionado

- Novos POPs de calibração extraídos de `Ajustes IA/`:
  - `triagem.md`: Regras de triagem e limites de ligações por operador.
  - `processo_localizacao.md`: Processo para localizar ligações e baixar da plataforma Huawei.
- Atualização dos arquivos `areas_de_risco.md`, `cadastro.md`, `checklist.md`, `unilever.md` com as novas regras extraídas.

## [2026-04-16] — Camadas de consumo RAG

### Adicionado

- Camada 1 conectada ao avaliador de auditoria: `audit_evaluator.get_audit_system_prompt()` injeta o POP oficial correspondente por `setor`/`alerta` antes dos critérios avaliáveis
- Camada 2 preparada para POPs oficiais via tabela `procedimento_chunks`, migração PostgreSQL/pgvector e script de sincronização
- Busca semântica opcional em `backend/core/rag_triagem.py:buscar_procedimento_chunks`
- Reconciliação documentada em `rag/RECONCILIATION.md`

### Corrigido

- Contagem do índice ajustada para 20 fluxos/alertas cobertos nos 5 POPs atuais, mantendo 273 critérios
- BAS passou a ser descrito como pendente de POP próprio, com exceção do acionamento policial `4.1.10`, já coberto por `areas_de_risco.md`

## [2026-04-16] — Estrutura inicial do RAG

### Adicionado

- Pasta `rag/` dedicada ao sistema de RAG, com `sources/`, `schemas/` e documentação
- 5 POPs oficiais convertidos de `.docx` para `.md` UTF-8 em `sources/procedimentos_operacionais/`:
  - `cadastro.md` — Antecedentes (1 fluxo, 12 critérios)
  - `checklist.md` — Processo Checklist via WhatsApp (12 critérios)
  - `mondelez.md` — 3 fluxos: Monitoramento I, Monitoramento II, Logística Reversa
  - `unilever.md` — 5 fluxos: Devolução, Cabinets, Atuação Tratativa, Distribuição, Loss Tree
  - `areas_de_risco.md` — Distribuição, Rastreamento, UTI, Fênix — múltiplos alertas (Prioritário, Posição em Atraso, Parada Indevida, Desvio de Rota, etc.)
- `_INDEX.md` com cobertura por setor/alerta e metadados
- `README.md` explicando o propósito e as duas camadas RAG
- DB Knowledge Agent (`backend/scripts/db_knowledge_agent.py`) passou a consumir `rag/sources/procedimentos_operacionais/*.md` ao gerar `regras_negocio.md`

### Movido

- `docs/procedimentos_operacionais/APIs_Azure_Auditoria_Sentinel.docx` → `docs/arquitetura/APIs_Azure_Auditoria_Sentinel.md` (é documentação de infraestrutura, não POP)

### Removido

- Pasta `docs/procedimentos_operacionais/` (conteúdo migrado para `rag/sources/procedimentos_operacionais/`)
- Arquivo solto `docs/Ajustes IA - Cadastro.docx` (duplicata, conteúdo consolidado no novo markdown)

### Observações

- Caracteres acentuados do `.docx` original estavam em encoding misto (cp1252/UTF-8); conversão foi feita extraindo texto via `python-docx` e salvando em UTF-8 puro
- Critérios marcados no original como "Retirar — não tem como a IA verificar" foram preservados com tag `[não-avaliável-por-ia]` para rastreabilidade
- Critérios acústicos (volume de voz, uso de mudo) foram mantidos mas marcados como `[avaliação-acústica]` por dependerem de análise de áudio, não transcrição
