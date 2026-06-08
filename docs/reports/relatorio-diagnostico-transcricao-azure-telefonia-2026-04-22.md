## Relatório de Diagnóstico: Erro de Transcrição Azure/Telefonia

Data: 2026-04-22

### Objetivo

Verificar, sem alterar código ou banco, se o erro abaixo ainda persiste por falha de configuração:

`Transcription failed: fast: AZURE_SPEECH_ENDPOINT nao configurado para Fast Transcription | whisper: Azure OpenAI Whisper Transcription failed: 401 Client Error: PermissionDenied ... dummy.openai.azure.com ... | sdk: Speech SDK retornou transcrição vazia`

### Escopo da análise

- Revisão do fluxo de fallback em `backend/core/transcription.py`
- Revisão da resolução de credenciais em `backend/core/config.py`
- Verificação do runtime carregado a partir do `.env`
- Verificação da presença de endpoints/configurações necessários
- Nenhuma transcrição real foi executada nesta etapa
- Nenhuma alteração foi aplicada no projeto

### Evidências verificadas

1. O caminho `fast` exige `AZURE_SPEECH_ENDPOINT` e `AZURE_SPEECH_KEY`.
2. O caminho `whisper` resolve endpoint e chave próprios, com fallback para Azure OpenAI quando aplicável.
3. O caminho `sdk` depende de `AZURE_SPEECH_KEY` e `AZURE_SPEECH_REGION`.
4. A validação de credenciais em runtime retornou sem pendências.
5. O endpoint `dummy.openai.azure.com` não aparece mais na configuração ativa do backend.

### Estado atual encontrado

- `AZURE_SPEECH_ENDPOINT`: presente
- `AZURE_SPEECH_KEY`: presente
- `AZURE_SPEECH_REGION`: presente e consistente com `eastus`
- `AZURE_OPENAI_ENDPOINT`: presente
- `AZURE_OPENAI_KEY`: presente
- Deployment principal Azure OpenAI: `gpt-4o`
- Deployment de transcrição Whisper: `nstech-bas-whisper`
- Endpoint resolvido do Whisper: válido e não mais apontando para `dummy.openai.azure.com`
- `validate_runtime_credentials()`: sem inconsistências

### Disponibilidade operacional inferida no runtime

- `fast_available`: `true`
- `whisper_available`: `true`
- `sdk_available`: `true`
- `gpt4o_diarize_available`: `true`
- `AZURE_SDK_FALLBACK`: habilitado
- `AZURE_WHISPER_FALLBACK`: habilitado
- `AZURE_GPT4O_DIARIZE_FALLBACK`: habilitado

### Conclusão

Pela configuração atualmente carregada, os dois primeiros sintomas do erro original foram corrigidos:

1. O erro `AZURE_SPEECH_ENDPOINT nao configurado para Fast Transcription` não condiz mais com o runtime atual, porque o endpoint agora está preenchido.
2. O erro `401 ... dummy.openai.azure.com` também não condiz mais com a configuração ativa, porque o Whisper agora resolve para um endpoint Azure válido e específico, sem uso do host dummy.

O terceiro sintoma exige cuidado:

3. `Speech SDK retornou transcrição vazia` não é um erro de configuração por si só. Ele ainda pode acontecer por áudio sem fala útil, problema de mídia, timeout, resposta vazia do serviço ou comportamento do próprio conteúdo enviado. Nesta análise, não foi executada uma chamada real de transcrição para confirmar esse ponto fim a fim.

### Parecer

O erro original aparenta estar corrigido no nível de configuração e credenciais carregadas pelo backend.

O que ainda não está provado por esta análise é a homologação fim a fim de uma transcrição real. Em outras palavras:

- configuração: consistente
- resolução de endpoints: consistente
- fallback configurado: consistente
- execução real contra Azure com áudio válido: não validada neste relatório

### Observação operacional registrada

Há uma hipótese operacional plausível de que a falha anterior tenha ocorrido após atualização/publicação feita a partir de ambiente local com variáveis divergentes, incompletas ou sobrescritas.

Os sintomas históricos são compatíveis com esse cenário:

- ausência de `AZURE_SPEECH_ENDPOINT` no runtime
- uso de endpoint placeholder como `dummy.openai.azure.com`
- combinação incorreta entre chave e endpoint Azure, gerando `401`

Portanto, até evidência em contrário, este incidente deve ser tratado como provável problema de sincronização/configuração de ambiente no momento da atualização, e não como quebra estrutural definitiva de credenciais da Azure.

### Próximo passo recomendado

Executar um teste controlado com um áudio real da telefonia e registrar:

- estratégia selecionada
- provedor aceito
- tempo de resposta
- quantidade de segmentos retornados
- eventual fallback acionado

Se esse teste passar, o erro pode ser tratado como corrigido operacionalmente.
