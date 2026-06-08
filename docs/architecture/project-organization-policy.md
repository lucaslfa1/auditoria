# Politica de Organizacao do Projeto

Data de referencia: 2026-05-19

Esta politica define como o repositorio `auditoria` deve ser organizado daqui
para frente. O objetivo e manter uma estrutura simples, navegavel e
reprodutivel, no estilo de engenharia usado em projetos academicos e
laboratorios MIT: fonte canonica clara, fronteiras pequenas, artefatos
derivados fora do codigo e documentacao com dono definido.

## Diagnostico atual

### 1. A raiz mistura naturezas diferentes

A raiz contem codigo de produto, documentacao, planejamento, relatorios,
referencias externas, audios, templates, exports e diretorios locais. Isso
dificulta responder perguntas simples como:

- "Onde esta a documentacao canonica?"
- "O que faz parte do produto?"
- "O que e entrada de referencia?"
- "O que e resultado gerado?"
- "O que pode ser removido sem risco?"

Pelo `git ls-files`, as maiores concentracoes versionadas hoje sao:

| Area | Arquivos rastreados | Observacao |
|---|---:|---|
| `backend/` | 343 | Produto, testes, dados, scripts e arquivos historicos misturados |
| `scripts/` | 143 | Scripts operacionais, diagnosticos e experimentos no mesmo nivel |
| `docs/` | 88 | Boa base canonica, mas ainda concorre com pastas antigas |
| `src/` | 79 | Frontend ja organizado por feature |
| `logs/` | 45 | Historico de versoes versionado |
| `planejamento/` | 34 | Planejamento antigo fora de `docs/` |
| `instrucoes/` | 31 | Referencias operacionais fora de `docs/` |
| `relatorios_atividades/` | 29 | Relatorios fora de `docs/reports/` |
| `ligacoes/` | 51 no disco, 51 aprox. no repo | Amostras de audio no repositorio |

Tambem existem artefatos ignorados localmente que poluem a leitura da arvore:
`node_modules/`, `backend/.venv/`, `dist/`, `backup_auditoria_ia/`,
`backend/storage/` e arquivos `tmp_*`. O `.gitignore` ja cobre boa parte disso,
mas a presenca fisica no workspace ainda atrapalha auditorias manuais.

### 2. Ha documentacao duplicada

Duplicatas exatas encontradas por hash:

| Documento | Copias atuais | Fonte canonica proposta |
|---|---|---|
| `AICC_25.300.1_CC-CMS Interface Reference (RESTful).pdf` | `docs/integracoes/huawei/`, `telefonia/` | `docs/integracoes/huawei/` |
| `AICC_25.300.1_CC-FS Interface Reference (RESTful).pdf` | `docs/integracoes/huawei/`, `telefonia/` | `docs/integracoes/huawei/` |
| `Huawei AICC ... postman_collection.json` | `backend/docs/huawei/`, `docs/`, `telefonia/` | `docs/integracoes/huawei/` |
| `documentacao_funcoes_huawei_aicc.docx` | `export/`, `telefonia/` | `docs/integracoes/huawei/raw/` ou remover se substituido por Markdown |
| `DICIONARIO_LOGISTICO.md` | `instrucoes/`, `planejamento/02-analises/` | `docs/references/operacional/` |
| `MANUAL_AUTOMACAO_RPA.pdf` | `instrucoes/`, `planejamento/04-referencias/` | `docs/references/automacao/` |
| `criterios-nao-negociaveis.txt` | `auditoria_criterios/`, `planejamento/04-referencias/` | `docs/references/auditoria/` |
| `Manual tecnico Qualidade.pdf` | `instrucoes/workflow/`, `planejamento/04-referencias/` | `docs/references/auditoria/` |

Regra: documento duplicado nao deve ser copiado para "ficar perto" de um modulo.
O modulo deve referenciar a fonte canonica.

### 3. Existem arquivos de codigo grandes demais

Arquivos rastreados com maior custo cognitivo:

| Arquivo | Linhas | Problema principal |
|---|---:|---|
| `backend/core/huawei_sync.py` | 2111 | Sincronizacao, filtros, persistencia, eventos e politica no mesmo arquivo |
| `backend/classification.py` | 1721 | Logica de classificacao ampla fora de um pacote de dominio |
| `backend/routers/telefonia.py` | 1592 | Router HTTP com regras de negocio demais |
| `backend/database.py` | 1460 | Fachada publica, bootstrap e compatibilidade historica misturados |
| `backend/repositories/audits.py` | 1360 | Repositorio grande com muitos casos de uso |
| `backend/automation_engine.py` | 1264 | Motor operacional concentrado |
| `backend/repositories/operators.py` | 1174 | Normalizacao, consultas e regras de operadores juntas |
| `src/features/supervisor/components/SupervisorPortal.tsx` | 1144 | Pagina, estado e componentes visuais juntos |
| `src/features/saved-files/components/SavedFiles.tsx` | 1127 | UI, estado e acesso a API concentrados |
| `src/features/classifier/components/Classifier.tsx` | 1062 | Fluxo inteiro da feature em um componente |
| `src/features/automacao/components/AuditModal.tsx` | 1016 | Modal com muita regra e estado local |

Regra: arquivos grandes nao sao erro automatico, mas passam a exigir plano de
decomposicao quando recebem mudancas funcionais.

## Principios

1. Uma fonte canonica por assunto.
2. Raiz pequena: apenas bootstrap, configuracao e indices.
3. Codigo de produto separado de referencia, planejamento e artefato gerado.
4. Documentacao ativa em `docs/`; conhecimento usado por RAG em `rag/` ou
   `backend/data/rag_training/`, nunca duplicado sem justificativa.
5. Arquivos grandes devem ser divididos por responsabilidade real, nao por
   tamanho arbitrario.
6. Scripts devem informar se sao operacionais, manutencao, migracao,
   diagnostico ou experimento.
7. Dados pesados e arquivos gerados nao entram no git, salvo fixtures pequenas
   e deliberadas.
8. Cada pasta importante deve ter um `README.md` curto explicando dono,
   conteudo permitido e conteudo proibido.

## Estrutura alvo

```text
/
|-- README.md
|-- package.json
|-- Dockerfile
|-- docker-compose.yml
|-- src/                         # frontend React por dominio
|-- backend/                     # API FastAPI e dominio backend
|-- scripts/                     # automacao operacional e manutencao
|-- tests/                       # testes fora dos pacotes principais, quando aplicavel
|-- docs/                        # documentacao canonica
|   |-- README.md
|   |-- architecture/
|   |-- database/
|   |-- infra/
|   |-- integracoes/
|   |-- manual-gestores/
|   |-- references/
|   |-- reports/
|   |-- reviews/
|   |-- backlog/
|-- rag/                         # fontes efetivamente usadas por recuperacao
|-- templates/                   # modelos fonte versionados
|-- public/                      # assets do frontend
|-- logs/versions/               # changelog operacional versionado
```

Pastas que devem ser migradas ou congeladas:

| Pasta atual | Destino alvo | Politica |
|---|---|---|
| `documentacao/` | `docs/` | Congelar, migrar documentos ainda validos e remover duplicatas |
| `planejamento/` | `docs/backlog/`, `docs/reports/`, `docs/references/` | Nao receber novos arquivos |
| `pendencias/` | GitHub Issues ou `docs/backlog/` | Nao misturar plano vivo com relatorio historico |
| `relatorios_atividades/` | `docs/reports/archive/YYYY-MM/` | Apenas historico; novos relatorios em `docs/reports/` |
| `telefonia/` | `docs/integracoes/huawei/` | Manter uma unica fonte da integracao Huawei |
| `instrucoes/` | `docs/references/` ou `rag/sources/` | Separar referencia humana de fonte RAG |
| `auditoria_criterios/` | `docs/references/auditoria/` | PDFs como referencia; regras executaveis em YAML/DB |
| `export/` | fora do git ou `docs/reports/archive/` | Export gerado nao deve ser fonte primaria |
| `ligacoes/` | `tests/fixtures/audio/` ou storage local ignorado | Versionar so amostras pequenas e anonimizadas |

## Politica de documentacao

### Tipos permitidos

| Tipo | Pasta | Regra |
|---|---|---|
| Arquitetura viva | `docs/architecture/` | Estado atual do sistema, atualizado junto com codigo |
| Decisao tecnica | `docs/architecture/adr/` | Uma decisao por arquivo, com contexto e consequencias |
| Integracao externa | `docs/integracoes/<fornecedor>/` | Contratos, colecoes Postman, PDFs e runbooks do fornecedor |
| Referencia operacional | `docs/references/` | Material fonte externo ou interno que embasa regras |
| Manual de usuario/gestor | `docs/manual-gestores/` | Linguagem operacional, sem detalhes internos demais |
| Relatorio pontual | `docs/reports/YYYY-MM/` | Resultado datado, nao fonte canonica |
| Revisao tecnica | `docs/reviews/YYYY-MM/` | Achados de revisao, auditoria e fechamento de ciclo |
| Backlog textual | `docs/backlog/` | Somente quando nao houver issue tracker |

### Regras

- Todo documento novo deve responder: dono, validade e relacao com fontes
  existentes.
- Documento novo nao pode duplicar conteudo ja canonico; deve linkar.
- Relatorio datado nao deve virar documentacao de referencia sem ser promovido.
- PDF/DOCX externo deve ficar em `docs/references/` ou `docs/integracoes/`.
- Markdown e preferido para conhecimento operacional editavel.
- Arquivo `.docx`, `.pdf`, `.xlsx` entra no git so quando for fonte externa,
  template ou evidencia historica necessaria.

## Politica de tamanho de arquivos

Limites de alerta:

| Tipo | Alerta | Teto recomendado |
|---|---:|---:|
| Router FastAPI | 400 linhas | 700 linhas |
| Servico/core Python | 500 linhas | 800 linhas |
| Repositorio Python | 500 linhas | 800 linhas |
| Componente React | 300 linhas | 500 linhas |
| Hook React | 250 linhas | 400 linhas |
| Documento ativo Markdown | 500 linhas | 800 linhas |
| Teste unitario | 600 linhas | flexivel com justificativa |
| Migracao historica | sem alerta | sem teto, se imutavel |
| Arquivo gerado | nao versionar | excecao documentada |

Quando um arquivo acima do alerta for alterado, a mudanca deve incluir uma das
decisoes:

- extrair componentes/funcoes no mesmo pacote;
- criar subpacote por dominio;
- mover codigo morto para arquivo historico ou remover;
- registrar por que o arquivo deve permanecer grande.

## Politica backend

### Raiz de `backend/`

Permitido:

- `main.py`
- `prestart.py`
- `requirements*.txt`
- `.env.example`
- arquivos de bootstrap estritamente necessarios

Nao permitido:

- `tmp_*.py`
- scripts de diagnostico soltos
- logs
- bancos locais
- credenciais
- modulos de negocio novos

Destino preferido:

| Natureza | Destino |
|---|---|
| Router HTTP | `backend/routers/` |
| Regra de negocio | `backend/core/` ou subpacote de dominio |
| Acesso a dados | `backend/repositories/` |
| Schema/migracao | `backend/db/` |
| Audio/diarizacao | `backend/audio/` |
| Provider externo | `backend/transcription_providers/` |
| Script interno backend | `backend/scripts/` |
| Script operacional geral | `scripts/` |

### Alvo para Huawei

O conjunto Huawei deve evoluir para um pacote explicito:

```text
backend/core/huawei/
|-- client.py
|-- obs_client.py
|-- sync_service.py
|-- sync_policy.py
|-- sync_state.py
|-- download_chain.py
|-- direction.py
|-- events.py
```

`backend/routers/telefonia.py` deve ficar como camada HTTP fina, chamando
servicos do pacote Huawei/telefonia.

## Politica frontend

O frontend ja segue o melhor eixo: `src/features/<dominio>/`.

Regras daqui para frente:

- Paginas coordenam fluxo; componentes filhos renderizam UI.
- Hooks concentram estado assincromo e efeitos.
- `lib/` dentro da feature guarda transformacoes puras e helpers de dominio.
- `schemas.ts` guarda validacao/tipos quando forem locais da feature.
- Componentes compartilhados ficam em `src/shared/components/` somente quando
  usados por mais de uma feature.
- Nao promover componente para `shared/` por antecipacao.

Exemplo alvo:

```text
src/features/telefonia/
|-- components/
|-- hooks/
|-- lib/
|-- schemas.ts
|-- types.ts
```

## Politica de scripts

`scripts/` deve ser subdividido por intencao:

```text
scripts/
|-- ops/             # iniciar/parar/status, rotinas usadas por operadores/devs
|-- db/              # migracoes, imports, health checks do banco
|-- maintenance/     # reconciliacao, limpeza, scheduler, watchdog
|-- diagnostics/     # probes e investigacoes temporarias com README
|-- experiments/     # codigo exploratorio com prazo de validade
```

Scripts temporarios devem ter validade explicita no cabecalho e nao devem ser
referenciados por `package.json`.

## Politica de dados e arquivos pesados

- `node_modules/`, `.venv/`, `dist/`, `backend/storage/`, backups e exports
  gerados permanecem fora do git.
- Audio versionado deve ser excecao: fixture pequena, anonimizada e com teste
  que justifique sua existencia.
- Grandes conjuntos de audio devem ir para storage externo ou pasta local
  ignorada.
- Planilhas oficiais podem ser versionadas apenas quando forem fonte de verdade
  e nao puderem ser substituidas por YAML/JSON estruturado.

## Ordem de migracao recomendada

### Fase 0 - Congelamento

- Declarar `docs/` como fonte canonica.
- Nao adicionar arquivos novos em `documentacao/`, `planejamento/`,
  `pendencias/`, `relatorios_atividades/`, `telefonia/` ou `export/`.
- Antes de criar documento, buscar duplicatas em `docs/README.md`.

### Fase 1 - Duplicatas exatas

- Manter as copias canonicas em `docs/integracoes/` e `docs/references/`.
- Remover ou substituir copias antigas por um pequeno `README.md` apontando para
  o destino.
- Atualizar referencias em scripts e docs.

### Fase 2 - Limpeza local

- Remover do workspace os diretorios ignorados que nao sao necessarios no
  momento, ou move-los para fora do repositorio.
- Garantir que `git status --ignored` mostre somente artefatos esperados.

### Fase 3 - Backend grande

Prioridade:

1. `backend/core/huawei_sync.py`
2. `backend/routers/telefonia.py`
3. `backend/classification.py`
4. `backend/database.py`
5. `backend/repositories/audits.py`

Cada refatoracao deve preservar endpoints e testes.

### Fase 4 - Frontend grande

Prioridade:

1. `SupervisorPortal.tsx`
2. `SavedFiles.tsx`
3. `Classifier.tsx`
4. `AuditModal.tsx`
5. `OperadorManagement.tsx`

Extrair primeiro subcomponentes e hooks, sem mudar comportamento.

### Fase 5 - Scripts

- Classificar scripts por pasta.
- Remover duplicatas como `check_db.py` em locais diferentes.
- Promover scripts realmente usados para comandos em `package.json`.

## Checklist para qualquer nova pasta

- A pasta tem dono claro?
- Existe `README.md` curto?
- O conteudo e fonte, referencia, runtime, teste ou artefato gerado?
- Ja existe uma pasta canonica para isso?
- Os arquivos entram no git por necessidade real?
- Ha risco de duplicar documento existente?

## Checklist para qualquer arquivo grande

- O arquivo tem mais de uma responsabilidade?
- Existe estado de UI misturado com apresentacao?
- Existe regra de negocio dentro de router?
- Existe SQL/acesso a dados misturado com regra de dominio?
- Existe codigo morto ou compatibilidade antiga?
- A extracao pode ser feita sem alterar contrato publico?

## Regra de ouro

Se um arquivo ou pasta nao consegue explicar por que existe em uma frase, ele
nao deve crescer. Deve ser renomeado, movido, dividido ou arquivado.
