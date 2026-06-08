# Relatório de Diagnóstico e Resolução de Erros da Telefonia/Huawei e IA
**Data:** 2026-05-12
**Ambiente:** Google Cloud Run (southamerica-east1 / us-central1) & Local .env
**Objetivo:** Restaurar a sincronização em background das chamadas da Huawei AICC e o pipeline de transcrição de IA (Diarização).

## 1. Problema de Sincronização (Fila de Triagem Vazia)
**Sintoma:** O sistema não conseguia baixar chamadas manualmente ("Período retroativo") nem via automação D-1, resultando em listas de execução vazias.
**Diagnóstico:** 
- A URL antiga do Proxy (Nginx) de produção da Teledata (`opentech.teledatabrasil.com.br`) estava bloqueando o IP da nossa Cloud NAT (`35.199.111.152`) com um erro `HTTP 403 Forbidden`.
- Tentativas de autenticação direta com Oauth na Huawei retornavam `HTTP 401 Unauthorized` devido à falta de whitelist ou keys não operacionais para chamada direta.
**Solução Aplicada:**
- Alterado a URL do proxy para o ambiente de laboratório que estava funcionando (`lab.teledatabrasil.com.br/aicc/auth/c2Authorization.php`).
- Restaurada a configuração de autenticação do sistema (`HUAWEI_AUTH_MODE=proxy`), que havia sido previamente forçada para `direct`.
- *Status:* A sincronização foi retomada com sucesso (Teste retornou HTTP 200 e baixou os metadados das chamadas reais).

## 2. Problema de Transcrição Diarizada (GPT-4o Azure)
**Sintoma:** Log de erro durante a pré-triagem: `GPT-4o-transcribe-diarize failed: 401 Client Error: PermissionDenied`. As auditorias saíam, porém perdendo a capacidade de dividir interlocutores.
**Diagnóstico:**
- O serviço de Diarização Principal estava operando com chaves obsoletas (`45q...`) que foram excluídas na Azure, gerando o erro de permissão.
- As auditorias não pararam totalmente porque o modelo de **Fallback (Azure Whisper)** e o modelo de **Avaliação Textual (GPT-4o Geral)** já estavam configurados com as chaves *novas* (`8ZH...` e `APy...`). Assim, o sistema falhava na Diarização, caía silenciosamente para o Whisper, e finalizava a avaliação com sucesso, mas sem a separação de falantes.
**Solução Aplicada:**
- Atualizadas as credenciais exclusivas do serviço de Diarização (`AZURE_GPT4O_DIARIZE_ENDPOINT` e `AZURE_GPT4O_DIARIZE_KEY`) nas variáveis de ambiente do Cloud Run para match com as chaves vigentes presentes no documento `API - KEYS - NSTECH.docx`.
- *Status:* A autenticação do modelo GPT-4o-transcribe-diarize foi restabelecida, evitando que as chamadas caiam no Fallback do Whisper.

## 3. Investigação: Automação D-1 Pulando OBS e Filas de Triagem
**Sintoma:** Automação programada baixou 40 ligações mas registrou 0 tentativas no OBS e elas pararam na fila de Triagem em vez de irem para Auditoria.
**Diagnóstico:**
- **Pulo do OBS:** Existia um mecanismo "Fast-Fail" (`skip_obs_primary`) que desativava o OBS se ele parecesse vazio.
- **Fila de Triagem vs Automação:** Descobrimos que o disparo que preencheu as ligações não foi do Motor de Automação Híbrida (IA), e sim do "Cron de Telefonia", um serviço de background focado apenas em baixar áudios para revisão manual.
**Solução Aplicada:**
- Desabilitado o `skip_obs_primary` no código da `huawei_sync.py`, forçando a automação a sempre tentar o OBS primário e cair para o FS apenas como fallback natural.
- Adicionado um botão "On/Off" (Sincronização Contínua em Segundo Plano) na interface de Configurações para dar controle ao usuário sobre o Cron de Telefonia, separando-o do Motor Híbrido D-1.

## 4. Configuração de Credenciais RPA
**Sintoma:** O sistema possuía a estrutura visual para configurações de RPA (Robotic Process Automation) no módulo "Telefonia", mas as credenciais de acesso humano não estavam preenchidas no cofre do banco de dados, inviabilizando futuras expansões.
**Solução Aplicada:**
- Foi criado e executado um script de injeção direta no banco de dados (`psycopg2`) para popular a tabela de `configuracoes` com as credenciais manuais (URL do Portal, Usuário e Senha).
- *Status:* O frontend agora exibe os campos devidamente preenchidos e de forma segura, pavimentando o terreno para futuras rotinas automáticas de fallback ou scraping.

## Próximos Passos (Infraestrutura)
- Solicitar à infraestrutura da Teledata a liberação (Whitelist) do IP `35.199.111.152` na URL de produção `opentech.teledatabrasil.com.br`. Após liberação, o valor da variável de proxy poderá ser revertido do "lab" para produção sem perdas no sistema.
