# Sistema de Auditoria nstech

## Documentacao

A documentacao canonica do projeto vive em **[`docs/README.md`](docs/README.md)**
(indice da suite 01-12: visao geral, arquitetura, banco, operacao, Huawei,
custos, seguranca, testes, migracao e deploy). Para o handover ao time de
engenharia, comece pelo **[`docs/12-checklist-handover.md`](docs/12-checklist-handover.md)**.

Documentacao atualizada para refletir o estado real do codigo em 2026-03-26.

## Visao Geral

O projeto `auditoria` e uma aplicacao full stack para auditoria operacional de
ligacoes e alguns fluxos documentais. O sistema combina:

- triagem automatica de audio antes da auditoria
- transcricao com fallback entre multiplos provedores
- avaliacao de criterios com IA e regras deterministicas
- fila de aprovacao, supervisao e contestacao
- exportacao de relatorios e historico operacional

Hoje, o produto esta mais proximo de uma plataforma operacional de governanca do
que de um prototipo de IA isolado.

## Stack Atual

| Camada | Tecnologia | Papel atual |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite | Shell da aplicacao, fluxo de auditoria, dashboard e modulos administrativos |
| Backend | FastAPI + Python 3.11 | API principal, orquestracao de IA, auth, workflow e exportacao |
| Persistencia | PostgreSQL | Auditorias, criterios, usuarios, filas, exports e colaboradores |
| IA de transcricao | Azure Speech, Azure Whisper, GPT-4o diarize | Pipeline com fallback e heuristicas de qualidade |
| IA de avaliacao | Azure OpenAI | Avaliacao dos criterios de auditoria |
| Exportacao | Excel, PDF e DOCX | Relatorios da auditoria, transcricao, gestores e planejamento |

Observacao:
- ha restos de compatibilidade com configuracoes antigas de Gemini no codigo
- AssemblyAI foi removido do caminho validado de transcricao
- no caminho principal atual, a avaliacao da auditoria esta orientada a Azure OpenAI

## Arquitetura Atual

### Frontend

O frontend foi organizado por dominio funcional em `src/features/`:

- `audit`: configuracao, upload, resultado, edicao e reauditoria
- `classifier`: triagem de audios antes da auditoria
- `dashboard`: historico e indicadores
- `supervisor`: aprovacao, exportacoes e acompanhamento
- `review`: veredito tecnico de contestacoes
- `saved-files`: artefatos salvos
- `settings`: configuracoes operacionais
- `ai-feedback`: feedbacks e calibracao de IA
- `admin`: administracao de criterios
- `colaboradores`: gestao operacional de pessoas
- `telefonia`: integracao Huawei AICC
- `automacao`: controle do motor hibrido Telefonia -> Triagem -> Auditoria

O arquivo `src/App.tsx` funciona como shell da aplicacao:
- carrega a sessao autenticada
- troca de views
- conecta os hooks principais do fluxo
- lazy-loada modulos secundarios

### Backend

O backend esta distribuido por camadas:

```text
backend/
|-- main.py                    # bootstrap FastAPI, CORS, seguranca, rate-limit, static mount
|-- database.py                # bootstrap do banco e fachada publica
|-- services.py                # re-export de servicos/core legados
|-- core/
|   |-- config.py              # variaveis de ambiente, provedores e criterios por setor
|   |-- transcription.py       # pipeline de transcricao e escolha de provedores
|   |-- evaluation.py          # avaliacao com IA e score deterministico
|   |-- audit.py               # fluxo de auditoria para audio e PDF
|   |-- report_exports.py      # geracao de arquivos exportados
|-- routers/
|   |-- auth.py
|   |-- audit.py
|   |-- classifier.py
|   |-- supervisor.py
|   |-- review.py
|   |-- admin.py
|   |-- analytics.py
|   |-- automation.py
|   |-- saved_files.py
|   |-- ai_feedback.py
|   |-- admin_criteria.py
|-- repositories/             # acesso a dados e regras por agregado
|-- db/                       # runtime schema, migracoes e utilitarios
|-- audio/                    # diarizacao, heuristicas e utilitarios de audio
|-- transcription_providers/  # wrappers de Azure e GPT-4o diarize
```

## Fluxo Principal de Auditoria

### 1. Triagem opcional

O modulo `classifier` pode classificar lote de audios antes da auditoria:
- setor
- alerta
- operador
- confianca
- necessidade de revisao manual

Esse passo alimenta a fila de revisao de classificacao e grava referencias no banco.

### 2. Upload e normalizacao

O endpoint principal e `POST /api/audit`.

Ele recebe:
- arquivo de audio ou PDF
- alerta selecionado
- operador e setor quando disponiveis

### 3. Transcricao

Para audio, o pipeline em `backend/core/transcription.py` tenta provedores em
ordem controlada e valida o resultado por heuristicas:

- Azure Fast Transcription
- GPT-4o diarize
- Azure Whisper

O sistema:
- calcula hash de entrada
- pode reutilizar resultado cacheado em modo deterministico
- normaliza falantes
- calcula qualidade de diarizacao
- escolhe o melhor candidato quando nenhum passa na validacao forte

### 4. Avaliacao

Depois da transcricao, a avaliacao:
- monta o prompt com contexto do alerta e criterios
- exige retorno JSON
- repara JSON invalido quando necessario
- normaliza criterios e status
- calcula score localmente no backend

O score final nao depende apenas da IA. O backend ainda aplica:
- criterios ausentes como `fail`
- safety nets por configuracao
- regras de zeragem para itens nao-negociaveis

### 5. Persistencia e workflow

O resultado pode ser salvo com:
- detalhes da auditoria
- transcricao
- qualidade do audio
- hash de entrada
- metadados do arquivo
- status de aprovacao/revisao
- caminho do audio armazenado

Depois disso, a auditoria entra no fluxo operacional:
- pendente para aprovacao
- aguardando pareamento
- contestada
- em revisao tecnica
- aprovada ou ajustada

## Banco de Dados

O schema runtime atual cobre mais do que auditorias isoladas. Entre os objetos
mais importantes:

- `audits`
- `colaboradores`
- `ligacoes_auditadas`
- `resultados_classificacao`
- `fila_revisao_classificacao`
- `audit_sectors`
- `audit_alerts`
- `audit_criteria`
- `report_exports`
- `arquivos_salvos`
- `gestor_feedbacks`

Isso sustenta:
- workflow de supervisao
- rastreabilidade de exportacoes
- armazenamento de artefatos
- historico operacional

## Autenticacao e Acesso

O backend usa autenticacao baseada em cookie de sessao assinado:
- `bcrypt` para senha
- sessao assinada com HMAC
- TTL configuravel
- rate limit de login
- papeis `admin` e `supervisor`

Endpoints principais:
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

## Endpoints mais relevantes

| Rota | Metodo | Papel |
|---|---|---|
| `/api/auth/login` | POST | login |
| `/api/audit` | POST | auditoria principal de audio ou PDF |
| `/api/audit/reevaluate` | POST | reauditoria de transcricao editada |
| `/api/classify` | POST | triagem de audios |
| `/api/export/*` | POST/GET | exportacoes de auditoria, gestores e planejamento |
| `/api/revisao/*` | GET/POST | contestacoes e veredito tecnico |

## Execucao Local

### Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Observacoes:
- um banco vazio agora exige bootstrap explicito de usuarios via `AUTH_USERS_JSON` ou `AUTH_USERS_FILE`;
- `SESSION_SECRET` deve ser definido em producao e e recomendado tambem localmente quando voce quiser sessoes persistentes entre reinicios.

### Frontend

```bash
npm install
npm run dev
```

### Subir stack local do projeto

```bash
npm run up
```

## Testes

```bash
npm run test
```

Ou separadamente:

```bash
npm run test:frontend
npm run test:backend
```

## Configuracao

Copie `.env.example` para `.env` e ajuste:
- Azure Speech
- Azure OpenAI
- opcoes de diarizacao e fallback
- sessao/autenticacao
- banco e storage local

## Resumo Tecnico

Hoje, o `auditoria` e composto por:
- frontend modular por dominio
- backend FastAPI com routers, core e repositories
- pipeline de transcricao resiliente
- avaliacao hibrida entre IA e regras deterministicas
- persistencia rica para governanca operacional
- fluxo de supervisao e contestacao

