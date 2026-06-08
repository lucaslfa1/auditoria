# Revisao dos Servicos Azure - 2026-04-09

## Escopo

Este documento registra a revisao do fluxo Azure no backend apos a serie recente de ajustes em:

- configuracao base do provider Azure OpenAI;
- tratamento de falhas da auditoria;
- tratamento de falhas da classificacao;
- identificacao auxiliar de speakers via Azure OpenAI;
- transcricao via Azure Speech, Azure OpenAI Whisper e GPT-4o diarize;
- coerencia entre codigo ativo, historico tecnico e cobertura de testes.

## Resumo Executivo

O codigo atual ja estava substancialmente melhor do que o estado anterior, com correcoes reais para as quebras Azure.

As correcoes mais relevantes ja presentes no codigo ativo eram:

- `AZURE_OPENAI_DEPLOYMENT` padronizado para `gpt-4o`;
- erro critico de IA na auditoria convertido em `503` na rota publica;
- classificacao em lote blindada para nao derrubar toda a requisicao por falha individual de IA;
- cobertura automatizada para retry de payload invalido e retry de erro de servidor no provider diarizado.

As lacunas residuais encontradas nesta revisao estavam em dois pontos executaveis com fallback legado `gpt-4.1`:

- a rota [`backend/routers/classifier.py`](C:\users\lucas.afonso\projetos\auditoria\backend\routers\classifier.py) ainda persistia `modelo=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")` ao registrar resultado de classificacao;
- o caminho auxiliar de identificacao de speakers em [`backend/audio/speaker_identification.py`](C:\users\lucas.afonso\projetos\auditoria\backend\audio\speaker_identification.py) ainda resolvia `AZURE_OPENAI_DEPLOYMENT` com default `gpt-4.1`.

Essas lacunas nao pareciam quebrar a chamada principal de auditoria ja corrigida, mas mantinham risco lateral de `404` e rastreabilidade inconsistente em partes do backend que ainda falavam com Azure OpenAI.

## Achados

### 1. Correcao concreta ja existente no codigo

O fallback padrao de deployment em [`backend/core/config.py`](C:\users\lucas.afonso\projetos\auditoria\backend\core\config.py) ja estava corrigido de `gpt-4.1` para `gpt-4o`.

Esse ajuste e diretamente relacionado a falhas `404` por deployment inexistente.

### 2. Tratamento de indisponibilidade melhorado na auditoria

A rota [`backend/routers/audit.py`](C:\users\lucas.afonso\projetos\auditoria\backend\routers\audit.py) ja convertia `RuntimeError` da camada de IA em `HTTP 503`, reduzindo mascaramento como erro interno generico.

### 3. Blindagem de classificacao em lote ja presente

O arquivo [`backend/classification.py`](C:\users\lucas.afonso\projetos\auditoria\backend\classification.py) ja usava `_safe_classify_audio` para isolar falhas por arquivo.

### 4. Inconsistencias residuais corrigidas nesta revisao

Apesar da configuracao central estar correta, ainda existiam dois pontos residuais com fallback legado `gpt-4.1`.

Correcao aplicada:

- `gpt-4.1` -> `gpt-4o`
- na persistencia de classificacao;
- na identificacao auxiliar de speakers com LLM.
- fallback explicito para `gpt-4o` tambem quando `AZURE_OPENAI_DEPLOYMENT` vier vazio no ambiente.

## Historico Tecnico Relevante

Os dois movimentos tecnicos relevantes no historico recente foram:

- introducao do fallback legado `gpt-4.1` na configuracao base Azure;
- correcao posterior desse fallback para `gpt-4o`, explicitamente ligada a falha `404` por deployment inexistente.

## Validacao Executada

Foi executada validacao focada em Azure, sem alterar credenciais nem deployment remoto.

Comando utilizado:

```powershell
$env:PYTEST_CURRENT_TEST='manual'; & 'backend\.venv\Scripts\python.exe' -m unittest backend.tests.test_auth_api.TestAuthApi.test_classify_returns_review_flags_and_syncs_review_queue backend.tests.test_core_logic backend.tests.test_openai_diarize_provider backend.tests.test_audit_evaluator_payloads backend.tests.test_audit_evaluation_wrappers backend.tests.test_transcription_provider_wrappers backend.tests.test_transcription_orchestrator backend.tests.test_speaker_identification
```

Resultado:

- `76` testes executados
- `OK`

Cobertura relevante confirmada:

- resolucao de configuracao Azure Whisper;
- resolucao de configuracao GPT-4o diarize;
- auth mode para diarize;
- nome padrao do modelo diarizado;
- retry apos erro `500` no provider diarizado;
- retry de payload invalido na avaliacao Azure;
- wrappers e orquestracao de transcricao;
- regressao da persistencia de classificacao com deployment Azure;
- regressao do deployment padrao em identificacao auxiliar de speakers.

## Estado Operacional Observado no Ambiente Local

Quando carregado via `core.config`, o ambiente local resolvia:

- `AZURE_OPENAI_ENDPOINT=SET`
- `AZURE_OPENAI_KEY=SET`
- `AZURE_OPENAI_DEPLOYMENT=SET`
- `AZURE_SPEECH_KEY=SET`
- `AZURE_SPEECH_REGION=SET`
- `AI_PROVIDER_PRIORITY=azure`

E nao resolvia configs dedicadas de fallback de audio:

- `_resolve_azure_whisper_config()` -> ausente
- `_resolve_azure_gpt4o_diarize_config()` -> ausente

Isso significa que a principal correcao de quebra hoje esta no caminho base Azure OpenAI + Azure Speech, enquanto os fallbacks dedicados de audio seguem dependentes de configuracao de ambiente.

## Arquivos Alterados nesta Revisao

- [`backend/routers/classifier.py`](C:\users\lucas.afonso\projetos\auditoria\backend\routers\classifier.py)
- [`backend/audio/speaker_identification.py`](C:\users\lucas.afonso\projetos\auditoria\backend\audio\speaker_identification.py)
- [`backend/tests/test_auth_api.py`](C:\users\lucas.afonso\projetos\auditoria\backend\tests\test_auth_api.py)
- [`backend/tests/test_speaker_identification.py`](C:\users\lucas.afonso\projetos\auditoria\backend\tests\test_speaker_identification.py)
- [`docs/reviews/azure-services-review-2026-04-09.md`](C:\users\lucas.afonso\projetos\auditoria\docs\reviews\azure-services-review-2026-04-09.md)

## Conclusao

Comparado ao codigo anterior, o projeto de fato possui correcoes reais para os servicos Azure.

O que faltava no codigo ativo eram inconsistencias residuais de fallback legado `gpt-4.1` na classificacao e na identificacao auxiliar de speakers. Ambas foram ajustadas nesta revisao.

Depois desta correcao, o estado do codigo fica alinhado com a decisao operacional atual:

- deployment base Azure OpenAI em `gpt-4o`;
- deployment vazio no ambiente deixa de propagar string vazia para chamadas Azure sensiveis;
- auditoria com erro de indisponibilidade corretamente exposto como `503`;
- classificacao com persistencia coerente em metadado de modelo;
- identificacao auxiliar de speakers alinhada ao mesmo deployment base;
- cobertura automatizada focada nos fluxos Azure principais.

## Limite da Garantia

O codigo agora nao mantem mais fallback legado `gpt-4.1` nos caminhos executaveis revisados, o que elimina uma classe concreta de quebra por `404` de deployment.

A garantia final em producao, no entanto, ainda depende de:

- deploy concluido com as variaveis corretas;
- existencia real dos deployments Azure configurados;
- disponibilidade do Azure Speech e do endpoint Azure OpenAI;
- configuracao futura dos fallbacks dedicados de audio, caso se queira resiliencia maior que o caminho base atual.
