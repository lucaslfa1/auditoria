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
`[INSERIR PRINT AQUI - Tela de Autenticação]`

## 2. Módulo "Automação" (Tela Inicial Padrão)
Por padrão, ao logar, o usuário visualiza o status do `automation_engine.py`.
1. **Ação:** Verifique o painel superior para ver se o ciclo está `running` (Executando) ou `idle` (Aguardando).
2. **Ação:** Caso necessite forçar uma sincronização da Huawei manualmente, utilize o botão "Forçar Sincronização".
`[INSERIR PRINT AQUI - Tela de Automação com Dashboard]`

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