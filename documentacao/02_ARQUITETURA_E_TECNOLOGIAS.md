# 2. Arquitetura e Tecnologias

## 2.1. Tecnologias Utilizadas

A Auditoria nstech possui uma arquitetura desacoplada e moderna:

| Camada | Tecnologia | Papel Atual |
|--------|------------|-------------|
| **Frontend** | React 19 + TypeScript + Vite | Interface SPA robusta, gerenciando fluxos de auditoria, dashboard gerencial e gestão de filas de triagem. |
| **Backend** | FastAPI + Python 3.11 | API de alta performance que rege as regras de negócio, a orquestração do pipeline de IA, persistência e exportação de relatórios. |
| **Persistência** | PostgreSQL | Armazenamento relacional e estruturado das auditorias finalizadas, workflow, usuários, critérios e configurações. |
| **Transcrição e IA** | Azure Speech, Azure Whisper, GPT-4o | Diarização e conversão de áudio para texto num pipeline robusto com fallback e detecção de falantes. |
| **Avaliação IA** | Azure OpenAI (GPT-4o) | Verificação semântica dos critérios da auditoria de acordo com a documentação fornecida em prompt. |

## 2.2. Arquitetura em Módulos

### Frontend (`src/features/`)
- `audit/`: Fluxos de envio de áudios/PDF e visualização das pontuações de auditoria.
- `classifier/`: Triagem massiva antes do fluxo principal.
- `supervisor/` & `review/`: Workflows para revisar pontuações, registrar contestações e dar vereditos.
- `admin/` & `settings/`: Gestão de critérios flexíveis, usuários e calibração fina das IAs.

### Backend (`backend/core/`)
- `transcription.py`: Controla o fallback dinâmico para garantir transcrições à prova de falhas na Azure.
- `evaluation.py`: Reparação semântica de JSONs da IA, normalização de métricas e zeragem sistêmica automática de critérios não-negociáveis.
- `audit.py`: A principal esteira da auditoria mesclando áudio ou documentos.

## 2.3. Fluxo Principal de Processamento

1. **Triagem Opcional:** Audios recebem inferência rápida de contexto e setorização.
2. **Ingestão e Transcrição:** O FastAPI recebe o arquivo de mídia. O backend calcula um hash e tenta reuso em cache ou delega ao Azure Speech/Whisper. Em caso de insucesso de diarização nativa, utiliza-se GPT-4o como fallback.
3. **Avaliação Determinística e Semântica:** A transcrição é submetida a um prompt rico para avaliar se os critérios de conformidade da empresa foram seguidos. O backend sobrepõe suas heurísticas para forçar regras determinísticas onde a IA não obteve segurança, corrigindo formatos.
4. **Governança:** A avaliação entra em estado 'Pendente de Aprovação' em um workflow formal na interface do sistema.
