# Revisao do Modulo de Triagem - 2026-04-08

## Escopo

Este documento consolida:
- restricoes operacionais do modulo de triagem;
- contrato funcional da triagem;
- contrato tecnico da fila de triagem;
- checklist de validacao ponta a ponta;
- achados da analise inicial;
- abertura formal da Prioridade 1.

## Restricoes Operacionais

Estas restricoes foram definidas para qualquer trabalho futuro neste modulo:

- modelos de IA nao devem ser alterados sem autorizacao explicita;
- providers e APIs ja validadas nao devem ser trocados sem autorizacao explicita;
- prompts podem ser ajustados apenas com aviso previo;
- melhorias devem priorizar fluxo, contratos, persistencia, fila, automacao, frontend e testes;
- qualquer proposta que dependa de mudar modelo, provider, API, deployment ou credencial deve ser marcada como dependencia de aprovacao.

## Contrato Funcional da Triagem

### Objetivo

Classificar audios antes da auditoria, identificar casos inseguros e preparar o item para revisao humana ou auditoria direta.

### Entradas

- arquivo de audio suportado;
- usuario autenticado;
- catalogo de setores e alertas;
- dados auxiliares de operador quando houver correspondencia.

### Saidas

- classificacao por setor e alerta;
- dados auxiliares de operador;
- sinalizacao de revisao (`needs_review`, `review_reasons`, `review_priority`);
- registro persistido da classificacao;
- audio armazenado para reaproveitamento posterior.

### Regras funcionais

- a triagem nao deve bloquear o usuario por falha parcial de enriquecimento;
- a triagem pode retornar classificacao imperfeita, mas deve marcar revisao quando a seguranca operacional nao for suficiente;
- a classificacao mostrada na UI e a classificacao persistida precisam ter regra explicita de precedencia;
- a passagem para auditoria deve usar uma versao unica e rastreavel da classificacao;
- duplicidade deve ser sinalizada ao usuario, mas a politica de bloqueio ou reaproveitamento deve ficar definida fora da UI.
- apenas 2 auditorias por operador por mes sao suficientes;
- ao atingir a cota mensal de 2 auditorias, novos itens do operador nao devem seguir para auditoria ate o proximo mes;
- esta regra deve existir como regra funcional oficial do sistema e tambem deve constar no prompt quando houver revisao de prompt autorizada.

### Estados funcionais esperados

- item recebido;
- item classificado automaticamente;
- item pendente de revisao operacional;
- item liberado para auditoria;
- item auditado;
- item invalido ou falho com motivo explicito.

## Contrato Tecnico da Fila de Triagem

### Entidade principal

`fila_revisao_classificacao`

### Campos minimos obrigatorios

- `input_hash`
- `nome_arquivo`
- `setor_previsto`
- `alerta_previsto`
- `confianca`
- `operador_previsto`
- `erro`
- `prioridade`
- `motivos_revisao`
- `metadata`
- `status`
- `criado_em`
- `atualizado_em`

### Contrato de leitura

- o backend deve expor a fila sempre com o mesmo shape publico;
- `metadata` deve sair desserializado e nao alternar semanticamente com `metadata_json`;
- consumidores da fila nao devem depender do formato bruto do banco.

### Contrato de escrita

- apenas camada de servico ou repositorio deve gravar na fila;
- status e prioridade devem ser validados pelo dominio;
- qualquer atualizacao deve preservar rastreabilidade temporal.

### Invariantes

- `input_hash` e unico;
- `status` pertence ao conjunto oficial do dominio;
- `prioridade` pertence ao conjunto oficial do dominio;
- `metadata.classified_audio_path`, quando existir, precisa ser suficiente para reabrir o audio salvo;
- nenhum consumidor deve inventar status fora do contrato oficial.
- itens bloqueados por cota mensal do operador devem ter motivo rastreavel e comportamento consistente entre triagem, fila e automacao.

### Consumidores principais

- UI da triagem;
- dashboard e revisao operacional;
- automacao em lote;
- fluxo de auditoria iniciado pela triagem.

## Checklist de Validacao Ponta a Ponta

1. Upload de audio valido entra na triagem sem erro de contrato.
2. A classificacao retorna setor, alerta e sinais de revisao de forma consistente.
3. O item e persistido na fila com shape publico estavel.
4. O audio classificado fica recuperavel pelo caminho salvo em `metadata`.
5. A UI reflete corretamente duplicidade, revisao e erro tecnico.
6. A auditoria iniciada pela triagem usa o mesmo contexto exibido ao usuario.
7. A automacao em lote consegue localizar e processar itens elegiveis.
8. Nenhum modulo escreve status fora do dominio.
9. Correcao manual tem regra clara: local-only ou persistida.
10. O fluxo completo falha com mensagem explicita, nunca em silencio.
11. Operador que ja atingiu 2 auditorias no mes nao deve receber nova auditoria ate o proximo mes.

## Achados da Analise Inicial

### Achados prioritarios

1. A automacao da triagem nao consome o mesmo contrato publico da fila. A triagem grava `metadata_json`, o repositorio expoe `metadata`, e a automacao tenta ler `metadata_json` novamente.
2. O contrato de status da fila esta inconsistente entre dominio, triagem e automacao. Existem valores usados operacionalmente fora do conjunto oficial atual.
3. As constantes de baixa confianca existem, mas a politica de revisao por confianca nao esta efetivamente aplicada no fluxo final.
4. A edicao manual na UI da triagem aparenta ser local e nao persiste na fila, o que abre divergencia entre interface, backend e automacao.

### Impacto operacional

- risco de item ficar preso entre triagem e auditoria;
- risco de automacao processar dados incompletos ou nao localizar o audio salvo;
- risco de correcao manual ficar invisivel para consumidores posteriores;
- risco de casos de baixa confianca passarem sem revisao operacional.
- risco de quebra da politica oficial de amostragem se a cota mensal de 2 auditorias por operador nao estiver centralizada.

## Prioridade 1 - Contrato da Fila de Triagem

### Objetivo

Fechar o contrato unico de leitura, escrita e transicao de estados da fila de triagem.

### Escopo

- definir conjunto oficial de status;
- definir transicoes validas;
- alinhar shape publico da fila;
- alinhar leitura e escrita entre triagem, revisao, dashboard e automacao.
- definir como a cota mensal de 2 auditorias por operador aparece na fila com motivo e comportamento rastreaveis.

### Status oficiais definidos na implementacao da Prioridade 1

- `pending`
- `auto_resolved`
- `reviewed`
- `audited`
- `monthly_capped`

### Status de consulta

- `ready_for_audit`
- `all`

### Status a descontinuar do contrato publico

- `classificado`
- `auditado`
- `ignorado`

### Proposta inicial de transicoes

- `pending -> reviewed`
- `pending -> audited`
- `auto_resolved -> audited`
- `reviewed -> audited`
- `auto_resolved -> monthly_capped`
- `reviewed -> monthly_capped`
- `monthly_capped -> audited` no mes seguinte, quando o item voltar a ficar elegivel

### Transicoes invalidas

- retorno para estado anterior sem reprocessamento explicito;
- gravacao de status fora da enum oficial.
- persistencia de `ready_for_audit` ou `all` no banco.

### Pontos mais sensiveis

- `backend/db/domain_constants.py`
- `backend/repositories/classification_review.py`
- `backend/routers/classifier.py`
- `backend/routers/review.py`
- `backend/routers/system.py`
- `backend/automation.py`

### Criterios de aceite da Prioridade 1

- qualquer item criado pela triagem pode ser localizado pelos consumidores seguintes;
- nenhum modulo grava status fora do conjunto oficial;
- o shape publico da fila fica estavel e documentado;
- a automacao deixa de depender de detalhes internos do banco.
- itens bloqueados por cota mensal ficam identificaveis sem ambiguidade e nao seguem para auditoria no mesmo mes.

## Procedimento Iniciado

O procedimento saiu da fase de definicao e entrou em implementacao controlada.

Alteracoes aplicadas na Etapa 1:

1. normalizacao de aliases legados de status;
2. persistencia de itens `auto_resolved` na fila;
3. estabilizacao do shape publico com `metadata`;
4. consumo de `ready_for_audit` pela automacao;
5. representacao rastreavel de `monthly_capped` com reaproveitamento apenas no mes seguinte;
6. cobertura de testes unitarios para contrato da fila e automacao.

## Prioridade 2 - Fluxo Triagem para Automacao

### Objetivo

Fechar o fluxo operacional entre o item classificado na triagem e a auditoria em lote, com reaproveitamento confiavel do audio salvo e sincronizacao correta da fila.

### Problemas corrigidos

1. a automacao dependia implicitamente de o `input_hash` da fila coincidir com o `input_hash` da auditoria;
2. a triagem usa hash do arquivo bruto, enquanto a auditoria usa hash contextual calculado com alerta, operador e setor;
3. falhas de reabertura do audio classificado podiam se repetir em toda execucao sem sinalizacao operacional suficiente.

### Implementacoes aplicadas na Prioridade 2

1. a automacao passou a calcular o `audit_input_hash` correto antes de consultar cache de auditoria;
2. a fila continua sendo atualizada pelo `queue_input_hash`, preservando o vinculo com o item de triagem;
3. a automacao grava `audit_input_hash` e `audit_id` no `metadata` da fila quando a auditoria e concluida;
4. quando a auditoria ja existe para o hash operacional calculado, a fila e sincronizada como `audited` sem reprocessar o audio;
5. quando o audio classificado nao pode ser reaberto, o item volta para `pending` com erro e motivo rastreaveis.

### Criterios de aceite da Prioridade 2

- a automacao consegue traduzir corretamente entre hash da fila e hash da auditoria;
- a fila nao perde rastreabilidade apos a auditoria em lote;
- item sem audio classificado nao fica em loop silencioso de falha;
- o fluxo triagem -> automacao fica coberto por testes direcionados.

## Prioridade 3 - Regras de Revisao Operacional

### Objetivo

Fechar a politica que decide quando a triagem precisa encaminhar um item para revisao operacional, com foco em baixa confianca e evidencias estruturais de risco.

### Problema corrigido

As constantes de confianca ja existiam no modulo, mas a decisao final de `needs_review` ainda dependia quase sempre de erro tecnico, setor ou alerta desconhecidos e mismatch de direcao. Com isso, classificacoes validas porem incertas podiam sair como resolvidas sem revisao.

### Politica aplicada na Prioridade 3

- `confidence < 0.8` adiciona `baixa_confianca`;
- `confidence < 0.5` adiciona `confianca_muito_baixa`;
- `error` adiciona `erro_classificacao`;
- `sector_id` igual a `desconhecido` ou `erro` adiciona `setor_nao_identificado`;
- `alert_id` igual a `desconhecido` ou `erro` adiciona `alerta_nao_identificado`;
- `direction_mismatch = true` adiciona `direction_mismatch`.

### Hierarquia de alertas por enfase da fala

- alertas criticos tem prioridade sobre alertas menores;
- em setores operacionais, mencoes fortes a `painel violado`, `violacao`, `botao de panico`, `sensor de desengate` e `bau violado` priorizam `BAS-PRIORITARIO-MOT`;
- em setores operacionais, mencoes fortes a `perda de sinal`, `sem posicao` e `posicao em atraso` priorizam `BAS-POSICAO-MOT`;
- em logistica, mencoes fortes a `perda de sinal`, `sem posicao` e `posicao em atraso` priorizam `LOGISTICA-POSICAO`;
- apenas quando nenhum alerta critico domina, a disputa entre `parada` e `desvio` usa a enfase da transcricao para desempate;
- para `parada` versus `desvio`, a transcricao pesa mais que o nome do arquivo, que entra apenas como pista fraca de apoio.
- quando o catalogo nao confirmar um alerta com seguranca, a triagem nao deve cair no primeiro alerta/setor disponivel; deve retornar `desconhecido` para deixar a incerteza explicita.

### Regra de prioridade

- `needs_review = false` apenas quando nenhuma razao de revisao estiver presente;
- `review_priority = high` para:
  - `erro_classificacao`
  - `setor_nao_identificado`
  - `alerta_nao_identificado`
  - `direction_mismatch`
  - `confianca_muito_baixa`
- `review_priority = medium` para casos de baixa confianca sem razao estrutural grave;
- `review_priority = low` apenas quando o item nao precisa de revisao.

### Criterios de aceite da Prioridade 3

- classificacao com baixa confianca deixa de sair como resolvida sem rastreabilidade;
- casos de confianca muito baixa sobem automaticamente para revisao alta;
- `review_reasons` e `review_priority` ficam coerentes entre si;
- a politica fica coberta por testes direcionados e reproduziveis.

### Validacao aplicada

1. classificacao com confianca alta e sem conflito nao entra em revisao;
2. classificacao com confianca entre `0.5` e `0.8` entra em revisao media por `baixa_confianca`;
3. classificacao com confianca menor que `0.5` entra em revisao alta por `confianca_muito_baixa`;
4. mismatch de direcao continua elevando a revisao para alta;
5. setor ou alerta nao identificados continuam elevando a revisao para alta.

## Prioridade 4 - Correcao Manual na UI

### Objetivo

Fazer a correcao manual da triagem deixar de existir apenas no estado local do frontend e passar a persistir no backend com rastreabilidade.

### Problema corrigido

A UI permitia editar setor e alerta, mas essa alteracao nao chegava ao backend. Com isso, auditoria iniciada pela triagem podia usar uma versao, enquanto fila e automacao continuavam usando outra.

### Implementacao aplicada na Prioridade 4

- a resposta de classificacao passou a devolver `input_hash` para cada item;
- a UI passou a salvar a correcao manual pelo `input_hash`, antes de sair do modo de edicao;
- o backend ganhou endpoint autenticado para correcao manual da classificacao;
- a fila passa a ser atualizada com o novo setor e alerta e muda para `reviewed`;
- a revisao manual limpa a pendencia operacional daquele item e registra a classificacao anterior em `metadata`;
- quando existir ligacao de referencia para o hash, a correcao manual tambem gera novo registro em `resultados_classificacao` como evento manual de triagem.

### Criterios de aceite da Prioridade 4

- a classificacao revisada manualmente fica persistida no backend;
- fila, automacao e auditoria passam a enxergar a mesma classificacao revisada;
- a UI nao sai do modo de edicao sem confirmacao de persistencia;
- a correcao manual fica rastreavel por hash e metadata.

### Validacao aplicada

1. endpoint de correcao manual exige autenticacao;
2. endpoint persiste o item como `reviewed`;
3. a UI compila consumindo o novo contrato com `input_hash`;
4. o frontend salva a correcao antes de sair da edicao.

## Prioridade 5 - Cobertura de Testes

### Objetivo

Consolidar a cobertura do ciclo principal da triagem para reduzir regressao em contrato, automacao, regras de revisao e correcao manual.

### Cobertura consolidada

- contrato da fila e aliases legados;
- consulta `ready_for_audit` com reaproveitamento por mes da cota;
- automacao consumindo `metadata.classified_audio_path`;
- retorno para `pending` quando o audio classificado nao esta disponivel;
- politica de revisao por confianca;
- guardrails de setor, direcao e hierarquia de alertas;
- endpoint autenticado de correcao manual;
- compilacao do frontend com o novo contrato de triagem.

### Validacao aplicada

1. `pytest backend/tests/test_review_queue_contract.py -q`
2. `pytest backend/tests/test_auth_api.py -q -k "manual_classification_correction_requires_auth_and_persists_reviewed_result or classify_returns_review_flags_and_syncs_review_queue or dashboard_review_queue_endpoint_requires_auth_and_returns_payload"`
3. `pytest backend/tests/test_classification_guardrails.py -q`
4. `pytest backend/tests/test_classification_review_policy.py -q`
5. `pytest backend/tests/test_classification_direction_guardrail.py -q`
6. `npm run build`

## Etapa Residual 1 - Reconhecimento de Operador

### Objetivo

Reduzir falso positivo na identificacao de operador quando o nome vier fraco, parcial ou ambiguo na IA ou no nome do arquivo.

### Regra aplicada

- `id_huawei` tem prioridade quando estiver presente e puder resolver o operador no cadastro;
- nome completo consistente do arquivo passa a valer mais que nome fraco vindo da IA;
- nome fraco, parcial ou ambiguo nao deve mais forcar match de RH, nem contaminar setor e operador final;
- enriquecimento de setor pelo cadastro so acontece quando a identidade do operador estiver forte o suficiente.

### Efeito operacional

- menor risco de setor ser puxado por operador errado;
- menor risco de autodeclaracao ou primeiro nome isolado contaminar a classificacao;
- maior confiabilidade quando a resolucao vier por `id_huawei` ou nome completo consistente.

### Validacao aplicada

1. nome curto isolado nao dispara match de RH;
2. nome completo do arquivo prevalece sobre nome fraco da IA;
3. `id_huawei` prevalece sobre nomes conflitantes;
4. guardrails anteriores de setor, direcao e alertas continuam estaveis.

## Etapa Residual 2 - Duplicidade e Reprocessamento

### Objetivo

Parar de retrabalhar a mesma ligacao na triagem quando o mesmo audio ja existir na fila, preservando correcao manual e classificacao vigente.

### Regra aplicada

- mesma ligacao volta com marcador operacional `Ligacao repetida`;
- se o hash bruto do audio ja existir na fila de triagem, a resposta reaproveita o item existente em vez de reclassificar;
- a triagem nao sobrescreve item ja `reviewed`, `pending`, `auto_resolved`, `monthly_capped` ou `audited` so porque o mesmo audio foi enviado de novo;
- quando houver sinal legado de auditoria pelo mesmo hash, a UI continua recebendo o marcador de duplicidade sem misturar isso ao `alert_label`.

### Efeito operacional

- evita custo desnecessario de IA para audio repetido;
- evita pisar em correcao manual ja feita na triagem;
- separa classificacao de negocio do marcador operacional de repeticao.

### Validacao aplicada

1. item repetido da fila volta com `duplicate_label = Ligacao repetida`;
2. item repetido reaproveita a classificacao persistida;
3. nova classificacao e sincronizacao da fila nao rodam para o mesmo hash quando o item ja existe.

## Etapa Residual 3 - Ciclo de Vida do Audio Salvo

### Objetivo

Dar governanca ao armazenamento de audio classificado da triagem, evitando crescimento sem controle e permitindo limpeza segura de arquivos orfaos.

### Regra aplicada

- o diretorio de audio classificado passou a ser configuravel por ambiente;
- arquivos ainda referenciados pela fila de triagem sao preservados;
- arquivos nao referenciados so entram em limpeza depois da janela de retencao definida;
- a limpeza pode rodar em `dry-run` antes de qualquer remocao real.

### Implementacao aplicada

- helper centralizado para localizar o storage de audio classificado;
- levantamento dos `classified_audio_path` ainda referenciados pela fila;
- rotina `cleanup_classified_audio_storage(retention_days, dry_run)` no backend;
- script operacional `backend/scripts/cleanup_classified_audio_storage.py`.

### Efeito operacional

- menor risco de acumulo de arquivos sem uso;
- limpeza mais segura, sem remover audio ainda vinculado a item da fila;
- base pronta para rotina agendada de manutencao futura.

### Validacao aplicada

1. arquivo referenciado permanece preservado;
2. arquivo orfao antigo vira candidato e pode ser removido;
3. `dry-run` mostra o impacto antes da execucao real.

## Fechamento - E2E da Triagem

### Objetivo

Executar um fluxo integrado da triagem ate a automacao, sem depender de provider externo, para validar o encadeamento principal do modulo.

### Escopo validado

1. upload autenticado de audio para `/api/classify`;
2. classificacao retornada ao frontend;
3. sincronizacao do item na fila de triagem;
4. reaproveitamento do `classified_audio_path`;
5. consumo do item pela automacao;
6. persistencia da auditoria;
7. sincronizacao final da fila como `audited`.

### Resultado

- o fluxo principal da triagem ficou coberto por teste integrado direcionado;
- o modulo passa a ter validacao automatizada do encadeamento `triagem -> fila -> automacao -> auditoria`.

## Fechamento por modulo - Diretriz operacional adicionada em 2026-04-09

Para reduzir ambiguidade entre triagem, auditoria, supervisor e contestacao, o sistema passa a ser fechado por modulo.

### Modulo 1 - Triagem

Este modulo deve ser considerado fechado quando estiverem estaveis:

- upload e classificacao;
- persistencia da fila;
- correcao manual;
- regras de revisao;
- duplicidade e reprocessamento;
- storage do audio classificado;
- entrega correta para a fronteira da auditoria.

Este modulo nao exige, para aceite:

- aprovacao do supervisor;
- contestacao;
- revisao tecnica;
- dashboard final.

### Fluxo oficial apos a triagem

Depois que a triagem termina sua parte:

1. itens elegiveis seguem para auditoria;
2. a automacao do modulo seguinte audita o caso;
3. a auditoria concluida e entregue ao supervisor;
4. apenas se o supervisor contestar o caso ele entra em `contestation_pending_review`;
5. o dashboard final depende da etapa posterior de aprovacao.

### Checklist operacional vigente

O acompanhamento corrente do aceite do modulo 1 passa a usar:

- [05-checklist-triagem.md](/C:/users/lucas.afonso/projetos/auditoria/docs/manual-gestores/05-checklist-triagem.md)
