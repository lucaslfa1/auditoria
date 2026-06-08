# Revisao de operadores, supervisores e transcricao

Data local: 2026-04-19

## Objetivo

Registrar a revisao feita no projeto Auditoria apos a retomada da sessao, cobrindo tres pontos:

- Incorporacao e endurecimento das alteracoes propostas pelo Claude para triagem Huawei.
- Ajuste da gestao de operadores e supervisores em Configuracoes.
- Investigacao da diferenca de qualidade entre as transcricoes do Auditoria e do Sentinel.

## Contexto

O projeto estava com alteracoes locais relacionadas a automacao Huawei e selecao de chamadas para auditoria. Em seguida, foi identificado um problema de sincronismo conceitual entre supervisores cadastrados em Configuracoes e supervisores usados na lista de colaboradores.

Durante a conversa, a decisao de produto foi alterar o nome visivel de "Colaboradores" para "Operadores" e manter o cadastro/remocao de supervisores somente em Configuracoes. Depois disso, foi investigada a diferenca de qualidade de transcricao entre o Sentinel e o Auditoria.

## Alteracoes revisadas do Claude

Foram revisadas as alteracoes de automacao Huawei, especialmente:

- Regras de selecao em `backend/core/automation_rules.py`.
- Integracao de triagem no fluxo Huawei em `backend/core/huawei_sync.py`.
- Novo modulo de triagem por LLM em `backend/core/llm_triage.py`.

Principais riscos encontrados na revisao:

- Fallback de LLM precisava falhar fechado para nao auditar chamadas indevidas.
- A chamada de LLM precisava ter limite de tempo.
- A resposta do LLM precisava validar IDs retornados contra os candidatos reais.
- A integracao precisava de testes isolados, sem chamada real de rede.

Correcoes aplicadas:

- A triagem LLM seleciona no maximo 2 chamadas entre as 10 mais longas.
- Se Azure OpenAI nao estiver configurado, falhar, retornar JSON invalido ou IDs desconhecidos, o resultado fica vazio.
- A chamada usa `timeout=30`, `temperature=0` e `max_tokens=200`.
- Foram adicionados testes focados para garantir selecao, validacao e falha fechada.
- A documentacao da automacao foi atualizada para registrar que Cadastro, Logistica e Unilever usam triagem LLM.

## Operadores e supervisores

Problema identificado:

- Supervisores eram administrados em Configuracoes, mas a tela de colaboradores permitia digitar supervisores livremente.
- Isso criava duas fontes de verdade: usuarios supervisores e nomes soltos na base de colaboradores.
- A lista de colaboradores tambem carregava um nome de modulo que ja nao refletia bem a operacao.

Decisao aplicada:

- O nome visivel "Colaboradores" foi trocado para "Operadores".
- A criacao e remocao de supervisores ficou centralizada em Configuracoes.
- A tela de operadores passou a buscar `/api/admin/users` e listar somente usuarios com role `supervisor` como opcoes validas de supervisor.
- O campo Supervisor no cadastro/edicao de operador virou um seletor.
- Quando um operador antigo aponta para supervisor que nao existe mais em Configuracoes, o valor ainda aparece como legado, marcado como fora das configuracoes, para nao ocultar historico.

Arquivos principais alterados:

- `src/features/settings/components/OperadorManagement.tsx`
- `src/shared/components/Sidebar.tsx`
- `src/App.tsx`
- `src/features/settings/components/AutomationSettings.tsx`
- `src/features/telefonia/components/SyncPanel.tsx`

Observacao tecnica:

- As rotas, nomes internos e endpoints continuam usando `colaboradores` para evitar um refactor maior e arriscado neste momento.
- A mudanca feita foi de comportamento e nomenclatura visivel para o usuario.

## Investigacao de transcricao

Comparacao feita:

- Auditoria: `backend/core/transcription.py`, `backend/transcription_orchestrator.py`, `backend/transcription_providers/azure.py`, `backend/audio/audio_utils.py`.
- Sentinel: `Backend/Services/TranscricaoOrquestradorService.cs`, `Backend/Services/AzureFastTranscricaoService.cs`, `Backend/Services/AzureWhisperService.cs`, `sentinel-cortex/services/audio_processor.py`.

Principais diferencas encontradas:

- O Sentinel tenta Azure Speech-to-Text primeiro e, quando o resultado parece fraco, usa Azure Whisper como fallback automatico.
- O Auditoria tem fallback Whisper controlado por `AZURE_WHISPER_FALLBACK`, com default ativo no codigo atual.
- Qualquer mudanca nesse roteamento deve ser tratada como sensivel por envolver comportamento de provider.
- O Auditoria usa GPT-4o diarize como fallback quando configurado, mas no ambiente atual as variaveis especificas de GPT-4o diarize estavam vazias.
- O Auditoria estava recomprimindo audio para MP3 em 48 kbps antes de enviar para Azure quando o arquivo era WAV/PCM ou grande.
- O Sentinel usa MP3 128 kbps no processamento de audio, com comentario explicito de preservacao de fonemas e inteligibilidade.

Hipotese principal:

- A qualidade inferior em ligacoes curtas pode estar ligada a perda de informacao antes da transcricao, causada por recompressoes agressivas em 48 kbps.
- Em ligacoes curtas, ha menos contexto para o modelo recuperar palavras por contexto; qualquer perda de fonema pesa mais.

Correcao aplicada:

- `backend/audio/audio_utils.py` passou a exportar MP3 em 128 kbps em vez de 48 kbps.
- Essa mudanca nao troca provider, modelo, prompt, API ou credencial.
- A alteracao apenas preserva mais qualidade no audio enviado para o provedor ja validado.

Teste adicionado:

- `backend/tests/test_audio_utils.py` agora verifica que `convert_audio_to_mp3` usa `128k`, alem de preservar os testes existentes de conversao em memoria.

## Validacoes executadas

Backend:

- `pytest backend/tests/test_llm_triage.py -q`
- `pytest backend/tests/test_review_queue_contract.py -q`
- `pytest backend/tests/test_audio_utils.py backend/tests/test_transcription_orchestrator.py -q`
- `pytest backend/tests/test_core_logic.py -q`
- `python -m py_compile backend/audio/audio_utils.py backend/tests/test_audio_utils.py`
- `python -m py_compile backend/core/llm_triage.py backend/core/huawei_sync.py backend/core/automation_rules.py`

Frontend:

- `npm run build`

Resultado:

- Todos os testes e builds executados passaram.
- O pytest exibiu apenas aviso de cache em `.pytest_cache`, sem falhar a validacao.

## Pendencias e proximos passos recomendados

1. Testar a transcricao com amostras reais curtas antes e depois da mudanca para 128 kbps.
2. Verificar se o ganho resolve o problema sem mexer em provider.
3. Se ainda houver erro relevante, avaliar com autorizacao explicita:
   - ajustar ou restringir fallback Azure Whisper em cenarios controlados;
   - ajustar a regra de roteamento para GPT-4o diarize;
   - comparar a mesma chamada entre Auditoria e Sentinel com logs de estrategia selecionada.
4. Evitar alterar prompts de transcricao sem aviso e aprovacao, pois isso afeta diretamente comportamento validado.
5. Caso a nomenclatura "Operadores" precise ser refletida tambem internamente em rotas, tipos e nomes de arquivos, tratar como refactor separado.

## Conclusao

A revisao deixou o fluxo de supervisores com uma fonte de verdade mais clara, melhorou a nomenclatura operacional para "Operadores" e corrigiu uma diferenca objetiva de qualidade de audio entre Auditoria e Sentinel. A mudanca de transcricao aplicada foi conservadora: preserva mais audio antes da Azure, sem trocar modelos, providers ou prompts.
