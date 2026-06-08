# Relatorio de arquitetura - Modulo Telefonia

Data: 2026-05-03
Projeto: Auditoria nstech

## Conclusao executiva

Concordo parcialmente com a arquitetura atual. A direcao principal esta correta: o modulo Telefonia atua como camada de coleta e enfileiramento, nao como modulo que decide auditoria sozinho.

Fluxo atual:

```text
Huawei AICC/OBS -> huawei_sync -> midia classificada -> fila de triagem -> automacao/auditoria -> supervisor
```

Esse desenho e saudavel porque separa responsabilidades e reduz o risco de a integracao Huawei pular etapas de validacao da auditoria.

## Pontos fortes

- A busca global na VDN combinada com manifesto OBS e mais adequada do que busca por operador, ja que a Huawei nao se comporta bem com filtro por `agentId`.
- O sync baixa e enfileira; a automacao consome a fila pronta. Essa separacao esta correta.
- Ha deduplicacao por `call_id` em `huawei_sync_logs` e por hash da midia na fila.
- O sync manual roda em background, evitando travar a API.
- O fallback OBS direto e uma boa decisao para os casos em que CC-FS nao entrega a gravacao.
- Limite de downloads por ciclo e concorrencia configuravel deixam o processo mais controlavel.
- A fila de triagem virou o contrato entre Telefonia e Auditoria, o que preserva revisao manual e evita auditoria automatica sem controle.

## Pontos que eu ajustaria

- O status do sync manual ainda fica em memoria no router de Telefonia. Isso e fragil em restart, multiplas instancias e deploy cloud. Eu moveria o status ativo para tabela dedicada.
- Existem dois caminhos de orquestracao: `telefonia/sync` e `automation_engine.run_automation_cycle`. Eles funcionam, mas deveriam compartilhar um servico unico de job/ciclo.
- O lock do sync Huawei usa a tabela `configuracoes` como flag `sync_lock`. Eu substituiria por advisory lock do PostgreSQL ou uma tabela dedicada de jobs.
- O endpoint de auditoria instantanea duplica parte da logica de `automation._audit_single_item`. Melhor expor um servico compartilhado para auditar um item de fila.
- A UI de credenciais mostra apenas parte dos modos suportados pelo backend. O backend ja trabalha com `auth_mode`, credenciais diretas, proxy e OBS, mas isso nao fica totalmente claro na interface.
- O caminho PDF/multimidia parece parcialmente preparado, mas nao esta claramente conectado ao sync principal. Existem helpers para PDF, mas a coleta principal ainda parece focada em audio.

## Bug encontrado

O endpoint de auditoria instantanea em `backend/routers/telefonia.py` chama `load_classified_audio`, mas o router so importa `open_classified_audio_stream`.

Impacto:

- O endpoint `POST /api/telefonia/recordings/{input_hash}/audit` pode falhar em runtime.
- O teste focado `backend.tests.test_telefonia_router` tambem falhou por esse motivo.

Comando executado:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_telefonia_router -q
```

Resultado relevante:

```text
AttributeError: module 'routers.telefonia' has no attribute 'load_classified_audio'
```

## Recomendacao

Nao recomendo desfazer a arquitetura atual. Eu manteria o desenho Telefonia como camada de coleta e fila, mas faria uma limpeza arquitetural em tres etapas:

1. Corrigir o bug de importacao do `load_classified_audio`.
2. Extrair um servico unico para "auditar item de fila", usado tanto pela automacao quanto pela auditoria instantanea.
3. Persistir status/lock de sync em estrutura propria, deixando o estado em memoria apenas como cache.

## Veredito

A arquitetura esta no caminho certo. O problema nao e a ideia central; sao os pontos de acabamento: estado em memoria, duplicacao de logica entre endpoints e automacao, lock improvisado em `configuracoes`, e um bug concreto no endpoint de auditoria instantanea.
