# Relatório de Atualizações do Módulo de Automação e Triagem
**Data:** 12 de Maio de 2026

## 1. Ajustes na Triagem (LLM Triage)
- **Filtro de Duração:** O tempo mínimo de duração para que uma ligação de um setor convencional (Cadastro, Logística, Logística Unilever) seja elegível para a IA foi elevado de 60/90 segundos para **120 segundos**. Isso visa garantir que apenas ligações com chance real de tratativa passem pela peneira de custos da IA.
- **Remoção de Ordenação por Duração:** A lógica antiga que ordenava as ligações da mais longa para a mais curta antes de enviar ao GPT-4o foi removida. Essa ordenação tendia a viciar a amostra com ligações "vazias" (onde o operador ficava aguardando em caixa postal ou música de espera). O lote agora envia até 30 chamadas com duração >= 120s para que a IA escolha as melhores puramente com base no contexto/palavras-chave do setor.

## 2. Automação de Ponta a Ponta (End-to-End)
- **Diagnóstico:** As chamadas baixadas pelo Motor de Automação no ciclo D-1 ficavam presas na etapa "Triagem" (Pendente) aguardando uma pessoa clicar no botão "Classificar".
- **Resolução:** O motor de automação (`backend/automation_engine.py`) foi ajustado para injetar e forçar a variável de ambiente `HUAWEI_SYNC_ENABLE_CLASSIFY="true"` de forma isolada durante sua execução automática. Isso garante o fluxo 100% autônomo (Telefonia -> Triagem Automática -> Auditoria) sem afetar a performance do clique manual da tela, que continua apenas baixando as chamadas.

## 3. Correção de Label "Origem Desconhecida"
- **Diagnóstico:** As auditorias feitas pelo sistema de automação apareciam com a tag de "Origem desconhecida" em vez de "Auto", porque o salvamento inicial gravava a origem vazia e a tarefa assíncrona falhava ao tentar atualizá-la posteriormente.
- **Resolução:** A função base de persistência de artefatos (`database.save_audit` e `database.persist_audit_artifacts`) foi refatorada para receber obrigatoriamente a origem (`criado_por="automacao"`) desde o momento da criação do registro, evitando a necessidade de atualizações posteriores (`race condition`).
- **Backfill de Dados:** Foi executado um script de correção diretamente no banco de dados para retroagir e corrigir os registros que já haviam sido salvos com a origem nula ou vazia.

## 4. Testes e Deploy
- Todos os mais de 130 testes automatizados dos pipelines afetados passaram com sucesso.
- O código foi versionado, e o pipeline de CI/CD para o Google Cloud Run foi disparado e finalizado na branch `main`.

---
*Relatório gerado automaticamente após a manutenção e melhorias efetuadas pelo agente IA.*