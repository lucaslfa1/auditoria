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
