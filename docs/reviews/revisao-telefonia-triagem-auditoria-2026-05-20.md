# Revisao parcial - Telefonia, Triagem e Auditoria - 2026-05-20

## Escopo

Revisao iniciada nos modulos Telefonia, Triagem e Auditoria antes de uma janela curta de trabalho. Este documento registra o estado verificado e os achados iniciais; nao representa uma revisao completa do fluxo.

## Estado do repositorio

- Branch local verificada: `main`.
- Remoto verificado: `origin https://github.com/lucaslfa84/auditoria`.
- Comando executado: `git pull --ff-only`.
- Resultado: `Already up to date.`
- Arquivos nao rastreados ja presentes e nao relacionados a esta revisao: `check_space.py`, `cleanup.py`.
- Nenhuma alteracao funcional foi feita durante a revisao inicial.

## Testes executados

Comando:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_telefonia_router.py backend\tests\test_triagem_e2e_flow.py backend\tests\test_audit_flow_fixes.py backend\tests\test_pre_triage.py -q
```

Resultado observado:

- `32 passed`
- `11 skipped`
- `2 failed`

Falhas observadas:

1. `backend/tests/test_telefonia_router.py::TestTelefoniaRouter::test_get_huawei_queue_item_rejects_pdf_report_as_recording`
   - O teste tenta mockar `telefonia.database.obter_fila_revisao_classificacao_por_hash`, mas a implementacao atual chama `classification_review.obter_fila_revisao_classificacao_por_hash` diretamente em `backend/routers/telefonia.py`.
   - Como o mock nao intercepta a chamada real, o teste tenta abrir conexao com o Neon.

2. `backend/tests/test_triagem_e2e_flow.py::TestTriagemE2EFlow::test_triagem_upload_flows_into_automation_and_marks_queue_as_audited`
   - O teste entra em `automation.audit_all_pending()`, que chama `database.get_config_value("huawei_cota_max_por_operador_mes", "2")`.
   - Essa chamada nao esta mockada no teste e tambem tenta conectar ao Neon real.

Conclusao dos testes: as falhas apontam principalmente para testes nao hermeticos. A suite direcionada nao deve depender de banco externo para validar fluxo de unidade/integracao local.

## Achados iniciais

### 1. Testes podem tocar banco real durante revisao local

Os testes direcionados tentaram acessar o Neon real quando mocks ficaram desalinhados com os caminhos atuais de importacao. Isso aumenta o risco de falsos negativos, lentidao e dependencia de rede/credenciais em validacoes que deveriam ser locais.

Recomendacao:

- Ajustar os mocks para interceptar os simbolos realmente usados pelo codigo em teste.
- Adicionar protecao nos testes para falhar cedo caso uma conexao real de banco seja tentada sem fixture explicita.

### 2. Frontend de Auditoria referencia rotas sem correspondencia clara no backend

Foram encontrados usos no frontend para:

- `GET /api/audit/draft/{input_hash}`
- `PUT /api/audit/draft/{input_hash}`
- `GET /api/audit/pending-dispatch`

Os repositorios possuem funcoes de draft e fila pendente, mas as rotas equivalentes nao apareceram em `backend/routers/audit.py` durante a busca inicial. Isso sugere desalinhamento entre UI e API.

Recomendacao:

- Confirmar se essas rotas foram movidas para outro router ou ficaram pendentes.
- Implementar os endpoints ou remover/ajustar a UI que depende deles.
- Cobrir com teste de contrato HTTP.

### 3. Cancelamento da auditoria Telefonia -> Auditoria parece apenas visual

O endpoint `DELETE /api/telefonia/recordings/{input_hash}/audit` atualiza a metadata da fila para `audit_task_status = canceled`, mas a auditoria foi agendada via `BackgroundTasks`. Esse mecanismo nao oferece cancelamento real da task ja em execucao.

Risco:

- O usuario pode cancelar na UI, mas a task em background ainda terminar, persistir a auditoria e marcar o item como auditado depois.

Recomendacao:

- Introduzir um token/flag de cancelamento consultado pela task antes de persistir resultado e antes de atualizar a fila como concluida.
- Registrar teste cobrindo: inicia auditoria, cancela, task termina depois, item nao deve virar `audited`.

### 4. Possivel reclassificacao indevida de audio ja auditado

No fluxo de `/api/classify`, quando uma auditoria existente e encontrada diretamente na tabela `audits`, o codigo marca `duplicate_info[idx] = already_audited`, mas nao interrompe o processamento daquele arquivo. Isso sugere que o arquivo ainda pode seguir para classificacao e persistencia na fila.

Recomendacao:

- Confirmar o comportamento com teste dedicado.
- Se confirmado, aplicar `continue` apos detectar `audit_row`, retornando payload de duplicidade sem reprocessar.

## Proximo passo sugerido

Retomar com uma revisao focada em:

1. Corrigir hermeticidade dos testes de Telefonia/Triagem.
2. Validar e corrigir contratos HTTP da Auditoria.
3. Endurecer o cancelamento real do fluxo Telefonia -> Auditoria.
4. Adicionar testes de regressao para duplicidade em `/api/classify`.
