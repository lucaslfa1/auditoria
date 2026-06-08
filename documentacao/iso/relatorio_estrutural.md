# Relatório Estrutural do Sistema - Auditoria nstech

**Data de Geração:** 24 de maio de 2026  
**Documento:** Relatório Estrutural para Governança e Conformidade (Padrão ISO)  
**Projeto:** Auditoria nstech  

---

## 1. Objetivo do Documento
Este relatório detalha a arquitetura, estrutura modular e o fluxo operacional da plataforma **Auditoria nstech**. O objetivo é fornecer uma visão técnica e estrutural completa para auditorias de TI, documentação de conformidade e planejamento de gestão, garantindo o alinhamento com padrões de qualidade e governança (ISO).

## 2. Visão Geral do Sistema
A **Auditoria nstech** é uma plataforma *full stack* e operacional desenvolvida para realizar a governança e auditoria operacional de ligações e fluxos documentais. O sistema atua como ponto central de qualidade, reduzindo o tempo de supervisão ao integrar automação baseada em Inteligência Artificial avançada com regras sistêmicas determinísticas.

A aplicação gerencia o ciclo de vida completo do artefato operacional: desde a ingestão (triagem), transcrição, avaliação com IA, até a governança da auditoria (fluxos de aprovação, contestação e exportação de resultados).

## 3. Arquitetura e Tecnologias
O sistema adota uma arquitetura Cliente-Servidor desacoplada, utilizando tecnologias de ponta para garantir alta disponibilidade e escalabilidade.

| Camada | Tecnologia | Descrição |
|--------|------------|-------------|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS (v4) | *Single Page Application* (SPA) responsiva para interface operacional e dashboards gerenciais. |
| **Backend** | Python 3.11, FastAPI | API de alta performance para controle de regras de negócio, orquestração de IA e persistência. |
| **Banco de Dados** | PostgreSQL 15 | Banco relacional robusto para persistência das avaliações, workflows, configurações e controle de acesso. |
| **IA & Cognição** | Azure Speech, Whisper, Azure OpenAI (GPT-4o) | Pipeline multimodelo com estratégias de *fallback* para transcrição, diarização e análise semântica. |

## 4. Módulos e Componentes

### 4.1. Camada de Apresentação (Frontend)
Organizada via *Domain-Driven Design* (`src/features/`):
- **`classifier/`:** Módulo para triagem massiva de arquivos antes do fluxo de auditoria principal.
- **`audit/`:** Fluxos centrais de envio de áudios/documentos (PDF) e consulta/edição de resultados de auditorias.
- **`supervisor/` & `review/`:** Fila operacional para gerenciamento de aprovações, pareamentos e revisão técnica de contestações.
- **`dashboard/`:** Painel de indicadores de qualidade e visualização de dados históricos.
- **`settings/` & `admin/`:** Administração de usuários, critérios flexíveis e calibração fina de parâmetros de Inteligência Artificial.

### 4.2. Camada de Lógica de Negócios (Backend)
Estruturado em camadas (`backend/core/`):
- **`transcription.py`:** Gerencia o pipeline de transcrição, aplicando heurísticas para garantir a precisão e acionando *fallbacks* dinâmicos (ex: do Azure Speech para GPT-4o e Whisper).
- **`evaluation.py`:** Responsável pela interface com LLMs para validação de conformidade. Executa reparações em saídas JSON, normalização de notas e aplica regras sistêmicas inegociáveis.
- **`audit.py`:** Orquestra a esteira principal, mesclando e validando mídias (áudio) e documentos, criando os artefatos no banco de dados.

## 5. Fluxo de Dados e Processamento

O ciclo de vida da informação ocorre da seguinte forma:

1. **Ingestão e Triagem (Opcional):**
   - Lotes de áudio recebem inferência preliminar para classificação e setorização antes do detalhamento.
2. **Processamento e Transcrição:**
   - Ao fazer o upload (áudio/PDF), o backend gera um *hash* para evitar reprocessamentos. O áudio é direcionado ao motor de IA em modo `hybrid_dual` para extração de texto em alta qualidade e separação de falantes.
3. **Avaliação Semântica e Determinística:**
   - A transcrição é injetada em um *prompt* estruturado com as documentações da empresa para avaliar os critérios de qualidade. 
   - Regras determinísticas de negócio são aplicadas (ex: zerar avaliações onde ocorreram falhas críticas), mitigando alucinações.
4. **Armazenamento:**
   - Os metadados, o histórico de processamento e os resultados da avaliação são salvos no PostgreSQL (`audits`, `ligacoes_auditadas`, etc.).
   - Os artefatos de áudio são mantidos em volumes controlados (`/app/Ligações`).
5. **Governança Operacional:**
   - A auditoria entra no status 'Pendente de Aprovação', acessível via *workflow* de revisão pela supervisão. Casos discrepantes seguem o fluxo de Contestação e Revisão Técnica.

## 6. Integrações e Serviços Externos
A plataforma depende primariamente dos serviços da **Microsoft Azure** e integrações parceiras para prover capacidades cognitivas:
- **Speech-to-Text:** Azure Speech Service, Azure Whisper, AssemblyAI.
- **Large Language Models (LLM):** Azure OpenAI (GPT-4o) para análises avançadas.

## 7. Implantação e Infraestrutura
O ambiente é configurado para automação e portabilidade:
- **Containerização:** Totalmente isolado via Docker e orquestrado por `docker-compose.yml`, que inclui os serviços da aplicação (`app`) e do banco de dados (`db`).
- **Scripts de Operação:** Implantação ágil via Node (`npm run deploy`) para execução de compilações em nuvem, garantindo a reprodutibilidade dos builds de imagem.

## 8. Governança e Segurança
A solução incorpora as seguintes premissas de governança:
- **Controle de Cota Mensal:** A aplicação bloqueia automaticamente processamentos excessivos, garantindo previsibilidade de custos.
- **Restrição a Alucinações:** Modelos são instruídos a utilizar marcadores explícitos ("[Inaudível]") no lugar de interpolações arriscadas.
- **Segurança de APIs:** O FastAPI garante *rate limiting*, cabeçalhos de segurança estritos e tipagem forte nos tráfegos de carga (*schemas*).
- **Rastreabilidade de Tempo:** Padronização absoluta do fuso horário (`America/Sao_Paulo`) no front e backend, mitigando divergências nos logs de auditorias.
