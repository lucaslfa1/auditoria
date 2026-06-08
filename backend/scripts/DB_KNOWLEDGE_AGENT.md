# DB Knowledge Agent — Documentação

## O que é?

O **DB Knowledge Agent** é um script Python que **lê o banco de dados e os documentos do projeto**, extrai todo o conhecimento relevante, e **gera documentos Markdown estruturados** em um diretório de treinamento (`backend/data/rag_training/`).

Esses documentos são otimizados para serem consumidos por sistemas de **RAG (Retrieval-Augmented Generation)** — ou seja, uma IA pode consultar esses documentos para responder perguntas sobre colaboradores, setores, critérios de auditoria, e qualquer outra informação do sistema.

---

## Como funciona?

```
┌─────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│   auditoria.db      │     │  DB Knowledge Agent  │     │  data/rag_training/  │
│   (banco de dados)  │────▶│                      │────▶│  (10 documentos .md) │
│                     │     │  Lê → Processa →     │     │                      │
│   instrucoes/       │────▶│  Estrutura → Salva   │────▶│  _INDEX.md (índice)  │
│   (manuais em .md)  │     │                      │     │                      │
└─────────────────────┘     └──────────────────────┘     └──────────────────────┘
```

O agente é **stateless** — cada execução gera um snapshot completo e atualizado. Pode ser executado a qualquer momento sem risco.

---

## Documentos gerados

| Documento | O que contém |
|---|---|
| `colaboradores.md` | Todos os colaboradores agrupados por setor, com nome, supervisor, escala, status e IDs |
| `supervisores.md` | Cada supervisor com sua equipe: quantos operadores, quais setores e escalas |
| `setores_e_escalas.md` | Setores de auditoria oficiais, setores usados nos colaboradores, e escalas com contagens |
| `criterios_auditoria.md` | Todos os critérios de avaliação por tipo de alerta (extraídos do `scoring_rules.yaml`) |
| `configuracoes.md` | Configurações do sistema (RPA habilitado, URLs, modelo IA, etc.) |
| `usuarios.md` | Usuários cadastrados com roles (supervisor, admin, etc.) |
| `estrutura_banco.md` | Schema DDL de todas as tabelas e views do banco |
| `estatisticas.md` | Métricas resumidas: total de colaboradores, % com supervisor, auditorias feitas, etc. |
| `regras_negocio.md` | Manual de Qualidade, Procedimento de Automação, Dicionário Logístico |
| `_INDEX.md` | Índice que lista todos os documentos e suas descrições |

---

## Como usar

### Executar o agente
```bash
cd d:\auditoria\backend
python -m scripts.db_knowledge_agent
```

### Saída
Os documentos são gerados em:
```
d:\auditoria\backend\data\rag_training\
```

### Uso programático
```python
from scripts.db_knowledge_agent import DBKnowledgeAgent

agent = DBKnowledgeAgent()
arquivos = agent.run()  # retorna lista de arquivos gerados
```

### Personalizar caminhos
```python
agent = DBKnowledgeAgent(
    db_path="caminho/para/outro.db",
    output_dir="caminho/para/saida/"
)
```

---

## Execução automática (18:00 diário)

O agente é executado automaticamente **todos os dias às 18:00** (fim do horário comercial).

Isso é gerenciado pelo módulo `scheduler.py`, integrado ao FastAPI:

```
Servidor sobe → scheduler.start() → agenda para 18:00
                     ↓
              Às 18:00 → executa Knowledge Agent → re-agenda para amanhã
                     ↓
Servidor desliga → scheduler.stop() → cancela o timer
```

Não precisa de cron, Task Scheduler, ou dependências externas — funciona via `threading.Timer` nativo do Python.

### Logs
Quando o agente executa, você verá no console:
```
⏰ Executando tarefas diárias agendadas (18:00)
✅ DB Knowledge Agent concluído — 10 documentos gerados
📅 Próxima execução do Knowledge Agent: 2026-03-21 18:00 (em 1440 min)
```

---

## Para que serve o RAG?

O sistema de RAG funciona assim:

1. **O agente gera os documentos** com todo o conhecimento extraído do banco
2. **Um sistema de IA** (como GPT, Gemini, etc.) recebe esses documentos como contexto
3. **Quando alguém faz uma pergunta**, a IA busca nos documentos a resposta relevante

**Exemplos de perguntas que o RAG pode responder:**
- "Quem é o supervisor da escala amarela no rastreamento?" → `supervisores.md`
- "Quais critérios são avaliados em ligações de desvio de rota?" → `criterios_auditoria.md`
- "Quantos operadores auditáveis estão sem supervisor?" → `estatisticas.md`
- "Qual é o processo de retificação de auditorias?" → `regras_negocio.md`

---

## Testes

O agente possui 7 testes automatizados em `tests/test_db_knowledge_agent.py`:

```bash
python -m pytest tests/test_db_knowledge_agent.py -v
```

Os testes verificam:
- Geração de todos os 10 arquivos
- Conteúdo correto dos colaboradores e supervisores
- Integridade do índice (_INDEX.md)
- Estatísticas precisas
- Schema presente
- Idempotência (rodar 2x gera o mesmo resultado)

