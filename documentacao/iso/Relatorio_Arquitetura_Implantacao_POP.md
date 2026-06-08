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


# Guia de Implantação e Operação (Deployment Guide) - Auditoria nstech

Este documento apresenta o guia completo para inicialização, configuração e entendimento estrutural da plataforma **Auditoria nstech**. Ele serve como um manual técnico para desenvolvedores e analistas de infraestrutura.

---

## 1. Visão Geral de Arquitetura

O sistema é dividido em duas camadas principais:
- **Frontend (React 19 + Vite):** Provê a interface de usuário (SPA), painéis de supervisão e configurações.
- **Backend (Python 3.11 + FastAPI):** Responsável por todas as regras de negócio, pipeline de IA, conexão com serviços de nuvem (Azure) e banco de dados relacional.
- **Banco de Dados (PostgreSQL 15):** Persiste os relatórios de auditorias finalizadas, filas de revisão, usuários e configurações base.

---

## 2. Requisitos de Sistema

- **Docker & Docker Compose** (Recomendado para produção e ambientes de staging)
- **Python 3.11+** (Para execução nativa do backend)
- **Node.js 20+** (Para execução e compilação do frontend)
- Chaves de API ativas para:
  - Azure OpenAI (GPT-4o)
  - Azure Speech Services
  - AssemblyAI (opcional, como modelo de contingência)

---

## 3. Guia de Instalação e Deploy

### 3.1. Usando Docker (Recomendado)

O projeto possui um arquivo `docker-compose.yml` pré-configurado que engloba a aplicação e expõe as portas necessárias.

```yaml
# docker-compose.yml (Resumo da configuração)
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: nstech_audit_app
    ports:
      - "${PORT:-8080}:8080"
    environment:
      - ENVIRONMENT=production
      - TZ=America/Sao_Paulo
    env_file:
      - .env
      - backend/.env
    volumes:
      - audit-data:/app/backend/data
      - ./Ligações:/app/Ligações
      - ./logs:/app/logs
    restart: unless-stopped
```

**Passos para subir os contêineres:**
1. Clone o repositório no seu servidor host.
2. Copie os arquivos de ambiente:
   ```bash
   cp .env.example .env
   cp backend/.env.example backend/.env
   ```
3. Preencha as chaves de API da Azure e do PostgreSQL dentro do arquivo `backend/.env`.
4. Construa e levante a infraestrutura:
   ```bash
   docker-compose up -d --build
   ```

### 3.2. Execução Local (Modo de Desenvolvimento)

**Para o Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # (Linux/Mac) ou .venv\Scripts\activate (Windows)
pip install -r requirements.txt

# Inicializa o servidor FastAPI (a inicialização do banco de dados ocorrerá no primeiro start)
python main.py
```

**Para o Frontend:**
```bash
# Na raiz do projeto (fora de backend/)
npm install
npm run dev
```

### 3.3. Deploy em Nuvem (Cloud Build / Cloud Run)

A aplicação conta com um script no `package.json` para facilitar o build.
```bash
# Executa a esteira de CI/CD via build
npm run deploy
```

---

## 4. Árvore de Processos e Módulos (Backend)

O backend possui uma estrutura modular estrita em `backend/core/` e `backend/routers/`.

### 4.1. Core Modules (Lógica de Negócios Central)
- **`transcription.py`:** Orquestrador principal da conversão de Áudio para Texto. Ele engloba a tentativa de transcrição rápida via `Azure Speech`, e se a qualidade (Diarização) for baixa, realiza *fallback* para o `Azure Whisper`.
- **`evaluation.py`:** Motor de Inferência GenAI. Constrói os *prompts* dinamicamente baseando-se no setor, alerta e critérios. Submete a transcrição final ao modelo `GPT-4o`, exige resposta em formato JSON, normaliza os campos e zera critérios inegociáveis que o operador não tenha cumprido.
- **`automation_engine.py`:** Serviço operado em *background* ou acionado via CRON que processa a triagem massiva de áudios sem intervenção humana, inserindo as auditorias na fila de supervisão.
- **`audit.py`:** Une os documentos e áudios, coordena com o módulo de avaliação e salva o artefato no PostgreSQL de forma atômica.

### 4.2. API Endpoints Principais (`routers/`)

O FastAPI registra as rotas (Endpoints) para o consumo do Frontend:

- **Auth & System:**
  - `POST /api/auth/login`: Emissão de cookie de sessão HTTP-Only.
  - `GET /api/health`: Monitoria (utilizado pelo Docker Healthcheck).
- **Core da Auditoria (`routers/audit.py`):**
  - `POST /api/audit`: Endpoint onde ocorre o *upload* principal. Aceita `.wav`, `.mp3` ou `.pdf`. É aqui que as trilhas de processamento e chamadas de IA iniciam.
  - `GET /api/audit/{id}`: Resgata o artefato gerado.
- **Triagem e Automação (`routers/classifier.py` & `routers/automation.py`):**
  - `POST /api/classifier/triagem`: Processa lotes de áudios brutos antes da auditoria para determinar o setor de origem (Ex: Mondelez, Unilever).
  - `POST /api/automation/cron/run`: Dispara manualmente as *tasks* assíncronas de captura/avaliação.
- **Governança (`routers/supervisor.py` & `routers/review.py`):**
  - `GET /api/supervisor/queue`: Fila de "Pendentes de Aprovação".
  - `POST /api/review/contest`: Permite que o operador ou supervisor encaminhe uma avaliação indevida para análise humana.
- **Configurações Flexíveis (`routers/admin_criteria.py`):**
  - `PUT /api/admin/criteria`: Permite modificar no banco os pesos e parâmetros de negócio usados pelos modelos GenAI em tempo real.

---

## 5. Automação e Fluxo da Auditoria (Passo a Passo)

1. **Ingestão Automática ou Manual:**
   Os áudios podem ser puxados via sincronização (Huawei) geridos pelo `automation_engine.py` ou imputados manualmente pelo Analista via Frontend (Endpoint `POST /api/audit`).
   > *Nota de Negócio:* A aplicação valida a *Cota Mensal* (máximo 2 auditorias por operador/mês) e barra sincronizações excessivas para o pipeline humano.

2. **Pipeline de Transcrição (`transcription.py`):**
   - Recebe a mídia.
   - Valida cache (`hash` MD5 do arquivo).
   - Envia requisição ao **Azure Speech** usando o perfil acústico `hybrid_dual` para máxima clareza e diarização fina.
   - Caso trechos importantes caiam como "[Inaudível]" em grau alto, ocorre o transbordo (*fallback*) inteligente.

3. **Validação de Critérios com GPT-4o (`evaluation.py`):**
   - Transcrição + Meta-dados de Critérios.
   - Modelo avalia itens como "Confirmou Placa?", "Simpatia?", e reponde com um objeto estruturado de notas.
   - **Correção Sistêmica:** Antes de gravar no banco, o motor de Python lê a saída da IA e caso detecte um item "Inegociável" falho, força o recalculo da nota final do operador.

4. **Status e Workflow:**
   A auditoria recém-gerada é salva no banco na tabela `audits` com status inicial `PENDING_APPROVAL`. Ela agora aparece no painel da Supervisão (Frontend). O supervisor revisa as marcações da IA e emite o Veredito. Caso necessite correção, uma Contestação técnica é aberta e roteada de volta para fila da Qualidade.

---

**Esse arquivo reflete a arquitetura estrutural viva e foi gerado para auxiliar na instalação, documentação e auditoria ISO corporativa.**


# Guia de Implantação e Operação (Deployment Guide) - Auditoria nstech

Este documento apresenta o guia abrangente e completo para inicialização, configuração e aprofundamento arquitetural da plataforma **Auditoria nstech**. Ele serve como o manual técnico definitivo para Engenheiros de Software, Arquitetos de Nuvem e Analistas de Infraestrutura. Ele também contempla o **Procedimento Operacional Padrão (POP)** para usuários finais.

---

# PARTE 1: ARQUITETURA E BACKEND (A Máquina)

## 1. Visão Geral da Arquitetura

O sistema emprega uma arquitetura desacoplada e baseada em eventos controlados, com forte tipagem e tolerância a falhas na integração com IA.

- **Frontend:** Desenvolvido em React 19 com TypeScript, gerenciado pelo Vite, estruturado em conceitos de *Domain-Driven Design* (DDD) para modularizar fluxos de Auditoria, Supervisão e Triagem.
- **Backend:** Construído em Python 3.11 sobre o microframework FastAPI. Responsável pela execução assíncrona de transcrições de áudio, geração de prompts estruturados para IA, verificação determinística e orquestração de workflows.
- **Banco de Dados:** Utiliza PostgreSQL 15, garantindo suporte transacional, constraints rígidas para integridade dos laudos operacionais, e escalabilidade para dados estruturados.
- **Ecossistema de IA (Exclusivo Microsoft Azure):** 
  - **Azure Speech Services / Whisper:** Conversão robusta de fala para texto (Speech-to-Text) com diarização avançada de falantes (operador vs cliente).
  - **Azure OpenAI (GPT-4o):** Validador Semântico de Conformidade. Extrai o significado da conversa transcrita e aponta se os critérios rigorosos da empresa foram atendidos.

---

## 2. Requisitos e Setup de Ambiente

### 2.1. Ambiente Produtivo (Docker / Cloud Run)

A forma recomendada para provisionar o sistema é através de conteinerização. O `docker-compose.yml` raiz agrupa a aplicação em portas nativas, mapeando volumes vitais de armazenamento de arquivos (`.wav`/`.pdf`).

**Passo a passo:**
1. Clone o repositório na máquina Host.
2. Ative as variáveis de ambiente base:
   ```bash
   cp .env.example .env
   cp backend/.env.example backend/.env
   ```
3. O arquivo `backend/.env` **deve** conter as chaves mandatórias da Azure:
   ```ini
   ENVIRONMENT=production
   AZURE_SPEECH_KEY=sua-chave
   AZURE_SPEECH_REGION=eastus
   AZURE_OPENAI_ENDPOINT=https://seurecurso.openai.azure.com/
   AZURE_OPENAI_KEY=sua-chave-gpt4
   AZURE_OPENAI_DEPLOYMENT=gpt-4o
   ```
4. Suba o ambiente:
   ```bash
   docker-compose up -d --build
   ```

### 2.2. Ambiente de Desenvolvimento

**Backend (FastAPI):**
```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

**Frontend (React/Vite):**
```bash
npm install
npm run dev
```
Para realizar o build de produção integrado: `npm run deploy` (script que consolida a compilação no provedor de nuvem).

---

## 3. Core Modules e Estrutura de Código

Esta seção explora como o código-fonte interage sob o capô, exibindo os trechos vitais de implementação da plataforma.

### 3.1. Pipeline de Transcrição (`backend/core/transcription.py`)

A extração de texto a partir do áudio é o coração inicial do sistema. O módulo utiliza uma estratégia de resiliência e *Diarização* (separação de vozes). O áudio é recebido, hasheado em MD5 (para evitar regravação e custos) e submetido aos serviços cognitivos da Microsoft.

*Trecho da mecânica de hashing e validação do áudio:*
```python
def compute_input_hash(
    audio_file: bytes,
    mime_type: str,
    alert: AuditAlert,
    operator_name: Optional[str],
    operator_id: Optional[str],
    sector_id: Optional[str]
) -> str:
    hasher = hashlib.sha256()
    hasher.update(mime_type.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(audio_file)
    # Hashing inteligente considerando metadados para controle de cache local
    alert_json = json.dumps(alert.model_dump(), sort_keys=True, separators=(",", ":"))
    hasher.update(alert_json.encode("utf-8"))
    return hasher.hexdigest()
```

O sistema impõe um fluxo que busca usar o Azure GPT-4o Diarize ou modelos acústicos de qualidade máxima, e repara alucinações substituindo-as pela string `"[Inaudível]"`.

### 3.2. Avaliação de Conformidade com GenAI (`backend/core/evaluation.py`)

Uma vez transcrito, o texto passa pelo crivo do GPT-4o da Azure. O script Python constrói as dependências, lê as tabelas de auditoria do Banco de Dados e injeta as regras de negócio em um prompt restrito que obriga a IA a responder em JSON puro.

*Lógica Estrutural de Notas Sistêmicas (Deflatores e Falhas):*
```python
def _resolve_audit_detail_scores(weight: float, status: str, deflator: Optional[float] = None) -> tuple[float, float]:
    """Calcula (score_obtido, score_maximo) para um critério seguindo a lógica estrita.
    A nota final é reduzida por penalidades em falhas (fail).
    """
    if status in {"na", "pending_manual"}:
        return 0.0, 0.0
    
    d = abs(deflator) if deflator is not None else 0.0
    
    if status == "pass":
        return weight, weight
    if status == "partial":
        # Perde metade da penalidade total
        return weight - ((weight + d) / 2), weight
    if status == "fail":
        # Falha fatal abate o deflator completo
        return -d, weight
        
    return -d, weight # Fallback
```

Adicionalmente, se o GPT-4o entregar um JSON quebrado (ex: truncado por tokens limite), o sistema possui uma esteira resiliente de reparo (`_try_parse_json_locally` e `_build_azure_json_repair_client`) para reconstruir o laudo antes de causar falha na operação.

### 3.3. Integração com Telefonia Huawei (`backend/core/huawei_sync.py`)

O sistema conta com um orquestrador específico para se conectar à infraestrutura telefônica da Huawei (AICC).

*   **Fluxo de Sincronização:** Carrega credenciais da tabela de configurações -> Busca na VDN globalmente -> Combina com o OBS Contact_Record -> Deduplica e baixa a mídia.
*   **Regra de D-1:** O sistema processa massivamente as ligações apenas no modelo `D-1` (ligaçoes do dia anterior).
*   **Direção e Setores:** Identifica se a ligação foi `inbound` ou `outbound`, permitindo barrar a IA caso a regra diga "Este setor audita apenas chamadas Saintes".

### 3.4. Motores Autônomos e Automação (`backend/automation_engine.py`)

A automação unifica o Huawei com a Fila de Triagem. O motor é cíclico e assíncrono.

```python
# Snapshot de controle de saúde do motor em background
_current_status = {
    "is_running": False,
    "is_cycle_running": False,
    "current_stage": "idle",
    "current_message": "Aguardando proximo gatilho.",
    "current_run_source": None,
    # ... tracking para dashboard ...
}
```

A automação:
1. Sincroniza áudios via Huawei_sync.
2. Extrai metadados para classificar o Setor do áudio antes de aplicar IA Profunda.
3. Se enquadra no limiar (ex: tempo máximo/mínimo), adiciona à fila classificada para posterior `audit_all_pending()`.

### 3.5. Camada de Banco de Dados (`backend/database.py`)

A persistência do sistema lida com chaves relacionais sólidas via SQLAlchemy em PostgreSQL. Ele mantém registro granular dos usuários e trilhas de auditoria:

```python
# Trecho de Bootstrap do banco
def _is_production_environment() -> bool:
    return is_production_environment()

def _load_auth_seed_users_from_config() -> list[dict]:
    # Inicializa usuários super-admins quando o banco sobe "zerado"
    # Bloqueia vetores de ataque exigindo env variables restritas na produção.
    explicit_users_file = (os.getenv("AUTH_USERS_FILE", "") or "").strip()
    if explicit_users_file:
        with open(explicit_users_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
```

---

# PARTE 2: GUIA DO USUÁRIO E POP (Operação UI)

Esta seção detalha o Procedimento Operacional Padrão de como manusear o Frontend construído em React (`src/App.tsx`).

*(Nota ao redator: insira os respectivos screenshots do sistema abaixo de cada instrução "INSERIR PRINT")*

## 1. Módulo de Login e Acesso
Ao acessar a raiz do sistema, caso a sessão esteja expirada, a tela de autenticação será apresentada. O sistema tem suporte a dois níveis (`admin` e `supervisor`).

1. **Ação:** Preencha suas credenciais fornecidas pela gerência de TI.
2. **Ação:** Clique em 'Entrar'. 
`![Tela de Autenticação](./prints/01_tela_autenticacao.png)`

## 2. Módulo "Automação" (Tela Inicial Padrão)
Por padrão, ao logar, o usuário visualiza o status do `automation_engine.py`.
1. **Ação:** Verifique o painel superior para ver se o ciclo está `running` (Executando) ou `idle` (Aguardando).
2. **Ação:** Caso necessite forçar uma sincronização da Huawei manualmente, utilize o botão "Forçar Sincronização".
`![Dashboard de Automação](./prints/02_dashboard_automacao.png)`

## 3. Módulo "Triagem" (Classifier)
Aqui chegam as chamadas baixadas da Huawei que ainda não foram avaliadas profundamente pela IA.
1. **Ação:** Na barra lateral (`Sidebar`), clique em "Triagem".
2. **Ação:** Avalie a tabela. A IA deduziu o "Setor" e o "Alerta" (motivo da ligação).
3. **Ação:** Se a "Confiança" estiver alta, a chamada será enviada para auditoria. Caso esteja baixa, você deve revisar e clicar em "Editar" para apontar o setor correto antes de mandar auditar.
`[INSERIR PRINT AQUI - Tela de Triagem listando chamadas]`

## 4. Módulo de Auditoria (Upload e Análise Avulsa)
Para chamadas recebidas via WhatsApp, PDF de despachantes ou casos críticos fora da telefonia:
1. **Ação:** Vá até "Nova Auditoria".
2. **Ação:** Selecione se o documento é Áudio (`.mp3`/`.wav`) ou Documento PDF.
3. **Ação:** Preencha os metadados manuais: Operador, Setor, e Motivo.
4. **Ação:** Clique em Auditar. A tela ficará em "Processando" enquanto acessa os servidores do Azure.
`[INSERIR PRINT AQUI - Tela de Upload de Auditoria]`

## 5. Módulo "Fila de Aprovação" (Supervisor Portal)
Local onde a IA devolve o resultado final com as "notas". Todas chegam como `Pendente de Aprovação`.
1. **Ação:** Acesse "Fila de Aprovação".
2. **Ação:** Clique sobre a linha de uma chamada recém auditada.
3. **Ação:** A tela exibirá a transcrição (com as partes `[Inaudível]`) à esquerda, e o Formulário de Critérios à direita.
4. **Ação:** Como supervisor, você pode alterar uma nota de "Falha" para "Aprovado" se julgar que a IA foi rigorosa. 
5. **Ação:** Clique em "Aprovar Veredito" para finalizar a tratativa da ligação.
`[INSERIR PRINT AQUI - Tela de Revisão Lado-a-Lado Transcrição/Formulário]`

## 6. Módulo "Arquivos Salvos" e Contestação
O repositório de todas as auditorias que já receberam Veredito e estão finalizadas.
1. **Ação:** Na barra lateral, acesse "Arquivos Salvos".
2. **Ação:** Se um Operador discordar da nota de sua ligação, encontre a chamada e clique em "Abrir Contestação".
3. **Ação:** Isso mandará o laudo para a aba "Revisão Técnica", onde a liderança da Qualidade dará a palavra final.
`[INSERIR PRINT AQUI - Tela da Tabela de Arquivos Salvos]`

## 7. Módulo "Configurações" (Admin Criteria)
Onde a Mágica Acontece. Apenas usuários `admin` têm acesso.
1. **Ação:** Acesse "Configurações" -> "Gerenciar Critérios".
2. **Ação:** É possível adicionar novas perguntas à planilha sem falar com os programadores.
3. **Ação:** Crie uma regra (Ex: "Simpatia?"), defina a regra "Apenas para o Setor SAC", atribua o "Peso" e o valor do "Deflator".
4. **Ação:** Na próxima auditoria, o Motor GPT-4o (`evaluation.py`) já perguntará automaticamente isso para o texto da chamada.
`[INSERIR PRINT AQUI - Tela de Configurações de Critérios da IA]`

---
**Este POP técnico unifica as regras do motor Python com a jornada UX em React, provendo visibilidade ponta-a-ponta na nstech.**