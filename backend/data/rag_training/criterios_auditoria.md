# Criterios de Auditoria

> Documento gerado automaticamente a partir de scoring_rules.yaml.
> Fonte unica de verdade: backend/db/scoring_rules.yaml


Total de alertas definidos: 71.


## Setor: uti

### Alerta Prioritário - Motorista (`UTI-PRIORITARIO-MOT`)

- Referencia POP: 4.1.1
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [170%] O operador confirmou a localização e a condição do motorista?
  - [192%] O operador identificou o motivo do alerta? (Sinistro, manutenção, problema técnico, acionamento indevido, etc.)
  - [170%] O operador solicitou vídeo do veículo nos casos necessários (Painel violado, Botão de pânico, Perda de Bateria, Teclado Desconectado, Sensor de desengate e baú)?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Alerta Prioritário - Cliente (`UTI-PRIORITARIO-CLI`)

- Referencia POP: 4.1.2
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [200%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento?
  - [180%] O operador informou corretamente o local onde gerou o alerta? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [180%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Posição em Atraso - Motorista (`UTI-POSICAO-MOT`)

- Referencia POP: 4.1.3
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [122%] O operador confirmou a localização atual do motorista? (Em movimento/parado, cidade e referência de local)
  - [200%] Passou orientações para forçar posicionamento do rastreador? (Envio de mensagem, reset de bateria, etc.)
  - [105%] O operador procurou identificar o motivo da perda de sinal? (Embaixo de cobertura, área sem sinal de celular, falha no rastreador, etc.)
  - [105%] O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Posição em Atraso - Cliente (`UTI-POSICAO-CLI`)

- Referencia POP: 4.1.4
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [120%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)?
  - [110%] O operador informou corretamente o local onde perdeu a posição? (Estado, cidade, parado/movimento, referência como posto, mecânica, rodovia)
  - [110%] O operador questionou se o conjunto possui equipamento de contingência? (Ex.: isca, rastreador secundário, bloqueio remoto)
  - [110%] O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista? (Ex.: manutenção, revisão, problemas no rastreador)
  - [110%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Motorista (`UTI-PARADA-MOT`)

- Referencia POP: 4.1.5
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [130%] O operador confirmou o motivo pelo qual o motorista parou em local indevido?
  - [130%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [132%] O operador orientou o motorista a reiniciar a viagem e seguir para um local homologado?
  - [140%] O operador informou os riscos operacionais da parada indevida, incluindo problemas com seguro?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Cliente (`UTI-PARADA-CLI`)

- Referencia POP: 4.1.6
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [114%] O operador informou as ações adotadas até o momento?
  - [140%] O operador informou corretamente o local da parada? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [140%] O operador confirmou se os pontos de parada autorizada foram passados ao motorista antes do início da viagem?
  - [140%] O operador informou ao cliente sobre os riscos operacionais e de seguro caso a parada indevida permaneça?
  - [140%] O operador indicou medidas de segurança ao cliente? (Ex.: Seguir até posto autorizado, acionar escolta, pronta resposta, etc.)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Motorista (`UTI-DESVIO-MOT`)

- Referencia POP: 4.1.7
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [105%] O operador confirmou o motivo do desvio de rota?
  - [105%] Confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [105%] Orientou o motorista a retornar para a rota ou permanecer parado até confirmação com o cliente?
  - [105%] Coletou qual itinerário o motorista está realizando?
  - [112%] O operador informou os riscos operacionais e de seguro caso o motorista continue fora da rota?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Cliente (`UTI-DESVIO-CLI`)

- Referencia POP: 4.1.8
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [130%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento? (Resumir os contatos/tratativas com ou sem sucesso)
  - [100%] O operador informou o trajeto que o motorista está realizando e o que estava programado na rota?
  - [100%] O operador questionou se o cliente tem conhecimento do motivo do desvio? O motorista informou antecipadamente?
  - [100%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento antes da viagem?
  - [130%] O operador indicou medidas de segurança ao cliente? (Ex.: Retornar a rota correta ou realizar o ajuste no sistema)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Contato com Ponto de Apoio (`UTI-PONTO-APOIO`)

- Referencia POP: 4.1.9
- Contexto: Processo de Auditoria Telefônica – Ponto de Apoio

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [195%] O operador informou os dados e as características do veículo? (cor, placa, modelo)
  - [160%] O operador passou detalhes da última posição do veículo? (Referência dentro do posto)
  - [160%] O operador solicitou que o atendente verificasse se o conjunto (cavalo/carreta) estava no local sem violações?
  - [160%] O operador orientou o atendente a chamar o motorista?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Alerta Prioritario - Policia (`UTI-PRIORITARIO-POLICIA`)

- Referencia POP: 4.1.10
- Contexto: Processo de Auditoria Telefônica – Acionamento Policial

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [130%] O operador passou detalhes do evento que indicam a suspeita?
  - [135%] O operador informou os dados e as características do conjunto e do motorista? (cavalo, carreta, cor, modelo)
  - [130%] O operador passou detalhes do local da ocorrência? (Rodovia, Referência, KM)
  - [150%] O operador solicitou deslocamento e/ou reporte da ocorrência para patrulhamento?
  - [130%] O operador deixou telefone de contato para retorno?
  - [120%] O operador utilizou o alfabeto fonético ao passar informações?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?


## Setor: bas

### Alerta Prioritario - Policia (`BAS-PRIORITARIO-POLICIA`)

- Referencia POP: 4.1.10
- Contexto: Processo de Auditoria Telefônica – Acionamento Policial

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [130%] O operador passou detalhes do evento que indicam a suspeita?
  - [135%] O operador informou os dados e as características do conjunto e do motorista? (cavalo, carreta, cor, modelo)
  - [130%] O operador passou detalhes do local da ocorrência? (Rodovia, Referência, KM)
  - [150%] O operador solicitou deslocamento e/ou reporte da ocorrência para patrulhamento?
  - [130%] O operador deixou telefone de contato para retorno?
  - [120%] O operador utilizou o alfabeto fonético ao passar informações?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?


## Setor: cadastro

### Antecedentes - Receptivo (`CADASTRO-ANTECEDENTES`)

- Referencia POP: 4.2.1
- Contexto: ANTECEDENTES - RECEPTIVA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [160%] O operador solicitou CPF/Placa para iniciar o atendimento?
  - [170%] O operador enfatizou sobre bloqueio/cadastro negativado?
  - [170%] O operador informou se o cliente possui inquérito/processo/apontamento?
  - [170%] O operador informou qual o estado/justiça federal?
  - [165%] O operador informou qual documento é necessário?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 60 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?


## Setor: logistica_unilever

### Devolução - Cliente (`UNILEVER-DEVOLUCAO`)

- Referencia POP: 4.3.1
- Contexto: DEVOLUÇÃO - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [76%] Informou que a devolução foi confirmada e qual o próximo passo?
  - [160%] Informou o nome do cliente corretamente?
  - [160%] Informou o endereço correto do cliente?
  - [160%] Informou o código do cliente?
  - [81%] Confirmou a quantidade de caixas a serem devolvidas?
  - [158%] Ação resultante (e-mail, ligação, mobile) foi registrada corretamente?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Cabinets - Cliente (`UNILEVER-CABINETS`)

- Referencia POP: 4.3.2
- Contexto: CABINETS - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [157%] Informou que irá comunicar um insucesso?
  - [160%] Informou o nome do cliente corretamente?
  - [160%] Informou o endereço correto do cliente?
  - [160%] Informou o código do cliente?
  - [158%] Ação resultante (e-mail, ligação, mobile) foi registrada corretamente?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Atuação Tratativa - Cliente (`UNILEVER-TRATATIVA`)

- Referencia POP: 4.3.3
- Contexto: ATUAÇÃO TRATATIVA - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [132%] Informou o motivo do contato?
  - [100%] Informou o nome do cliente corretamente?
  - [100%] Informou o endereço correto do cliente?
  - [85%] Informou o código do cliente?
  - [100%] Informou o motivo da devolução?
  - [100%] Informou a quantidade de caixas?
  - [100%] Informou o tempo de espera?
  - [78%] Ação resultante (e-mail, ligação, mobile). Ação final ao atendimento
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Distribuição - Cliente (`UNILEVER-DISTRIBUICAO`)

- Referencia POP: 4.3.4
- Contexto: DISTRIBUIÇÃO - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [135%] Informou o motivo do contato?
  - [132%] Informou a Placa do veículo?
  - [132%] Informou o nome do cliente?
  - [132%] Informou o endereço do cliente?
  - [132%] Informou a quantidade de caixas?
  - [132%] Ação resultante (e-mail, ligação, mobile) foi registrada corretamente?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Loss Tree - Cliente (`UNILEVER-LOSSTREE`)

- Referencia POP: 4.3.5
- Contexto: LOSS TREE - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [159%] Informou o motivo do contato?
  - [159%] Informou o nome do cliente?
  - [159%] Informou a data que ocorreu a devolução?
  - [159%] Confirmou o motivo que gerou o pedido não solicitado?
  - [159%] Ação resultante. Registrar o retorno no relatório.
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?


## Setor: logistica

### Estadia - Motorista (`LOGISTICA-ESTADIA`)

- Referencia POP: 4.4.1
- Contexto: ESTADIA - CONTATO MOTORISTA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [200%] Informou o motivo do contato?
  - [300%] Questionou se há previsão para descarga?
  - [295%] Verificou se houve alguma intercorrência no processo?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Temperatura - Motorista (`LOGISTICA-TEMPERATURA-MOT`)

- Referencia POP: 4.4.2
- Contexto: CONTROLE DE TEMPERATURA - CONTATO MOTORISTA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [130%] Informou o motivo do contato?
  - [200%] Questionou a temperatura do aparelho de frio?
  - [200%] Questionou o módulo de ajuste? (Contínuo/Automático)
  - [133%] Orientou a seguir o padrão de temperatura da Unidade?
  - [132%] Perguntou sobre o funcionamento do aparelho?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Temperatura - Cliente (`LOGISTICA-TEMPERATURA-CLI`)

- Referencia POP: 4.4.3
- Contexto: CONTROLE DE TEMPERATURA - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [150%] Informou o motivo do contato?
  - [175%] Informou ações adotadas?
  - [170%] Questionou se possui conhecimento do ajuste?
  - [150%] Verificou se há alguma falha ou motorista reportou algo?
  - [150%] Orientou a seguir o padrão de temperatura da Unidade?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desligamento Temperatura - Motorista (`LOGISTICA-DESLIG-TEMP-MOT`)

- Referencia POP: 4.4.4
- Contexto: Critérios para Contato com Motorista – Desl. Temperatura

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [130%] Informou o motivo do contato?
  - [132%] Confirmou ajuste do aparelho?
  - [132%] Confirmou se houve desligamento?
  - [132%] Confirmou a causa do desligamento?
  - [137%] Reforçou sobre riscos de devolução devido ao desligamento?
  - [132%] Caso esteja desligado, orientou religamento imediato, se necessário?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desligamento Temperatura - Cliente (`LOGISTICA-DESLIG-TEMP-CLI`)

- Referencia POP: 4.4.5
- Contexto: DESLIGAMENTO DE TEMPERATURA - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [150%] Informou o motivo do contato?
  - [155%] Informou ações adotadas?
  - [150%] Questionou se possui conhecimento do ajuste?
  - [170%] Reforçou sobre riscos de devolução devido desligamento?
  - [170%] Orientou religamento imediato, se necessário?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Atraso de Entrega - Motorista (`LOGISTICA-ATRASO-ENTREGA`)

- Referencia POP: 4.4.6
- Contexto: ATRASO - CONTATO MOTORISTA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [190%] Informou o motivo do contato?
  - [204%] Questionou o motivo do atraso?
  - [200%] Questionou se há previsão de chegada? (Caso não tenha chego ainda no cliente)
  - [200%] Confirmou se foi comunicado a base ou cliente sobre o atraso?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Motorista (`LOGISTICA-PARADA`)

- Referencia POP: 4.4.7
- Contexto: PARADA INDEVIDA (LOG) - CONTATO MOTORISTA

  - [30%] O operador se identificou informando nome, setor e empresa?
  - [40%] Confirmou com quem está falando?
  - [195%] Informou o motivo do contato?
  - [300%] O operador confirmou o motivo pelo qual o motorista parou em local indevido?
  - [300%] O operador orientou o motorista a realizar paradas somente em locais homologados?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Motorista (`LOGISTICA-DESVIO`)

- Referencia POP: 4.4.8
- Contexto: DESVIO DE ROTA (LOG) - CONTATO MOTORISTA

  - [30%] O operador se identificou informando nome, setor e empresa?
  - [40%] Confirmou com quem está falando?
  - [195%] Informou o motivo do contato?
  - [300%] O operador confirmou o motivo do desvio de rota?
  - [300%] Orientou o motorista a seguir a rota informada pela transportadora?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Ativação de AE - Cliente (`LOGISTICA-ATIVACAO-AE`)

- Referencia POP: 4.4.9
- Contexto: ATIVAÇÃO DE AE - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [195%] Informou o motivo do contato?
  - [200%] Informou nº da programação ou outra informação semelhante?
  - [100%] Se estiver atrasada, questionou o motivo do atraso na emissão?
  - [100%] Solicitou emissão?
  - [200%] Reforçou com o cliente a importância da emissão dentro do prazo?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Atraso - Cliente (`LOGISTICA-ATRASO`)

- Referencia POP: 4.4.10
- Contexto: ATRASO DE ENTREGA - CONTATO CLIENTE

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] Informou o motivo do contato?
  - [200%] Informou o número da OS, Placa ou AE?
  - [195%] Questionou o motivo do atraso?
  - [140%] Questionou se há previsão de chegada?
  - [140%] Reforçou o impacto do atraso na operação e no cliente?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Posição em Atraso - Motorista (`LOGISTICA-POSICAO`)

- Referencia POP: 4.4.11
- Contexto: POSIÇÃO EM ATRASO (LOG) - CONTATO MOTORISTA

  - [30%] O operador se identificou informando nome, setor e empresa?
  - [40%] Confirmou com quem está falando?
  - [200%] Informou o motivo do contato?
  - [295%] O operador confirmou a localização atual do motorista? (Em movimento/parado, cidade e referência de local)
  - [200%] O operador procurou identificar o motivo da perda de sinal? (Embaixo de cobertura, área sem sinal de celular, falha no rastreador, etc.)
  - [100%] Passou orientações para forçar posicionamento do rastreador? (Envio de mensagem, reset de bateria, etc.)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Taborda - Receptivo (`LOGISTICA-TABORDA`)

- Referencia POP: 4.4.12
- Contexto: OPERAÇÃO TABORDA - WHATSAPP

  - [30%] O operador se identificou informando saudação?
  - [130%] Utilizou linguagem apropriada? (Sem usar gírias ou estereótipos de apoio)
  - [130%] Fluxo do atendimento correspondeu à solicitação inicial? (Foco no atendimento)
  - [140%] Realizou o preenchimento de ociosidade? (Não deixando atendimento sem retorno por mais de 3min)
  - [130%] Realizou um atendimento cordial com educação? (Utilizando "obrigado"/"por favor"/"senhor")
  - [140%] Questionou se podia encerrar o atendimento?
  - [140%] Encerrou somente no tempo ocioso padrão? (3min)
  - [130%] Foi realizado a despedida final padrão?
  - [30%] Foi realizada a qualificação correta do atendimento?

### Atraso no Início de Viagem - Motorista (`LOGISTICA-ATRASO-INICIO`)

- Referencia POP: 4.4.13
- Contexto: ATRASO NO INÍCIO DA VIAGEM - CONTATO MOTORISTA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [200%] Informou o motivo do contato?
  - [200%] Questionou o motivo de não haver iniciado a viagem?
  - [198%] Questionou se há previsão de início?
  - [197%] Confirmou se foi comunicado a base ou cliente sobre o atraso no início?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Viagem Sem Espelhamento - Cliente (`LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI`)

- Referencia POP: 4.4.14
- Contexto: VIAGEM SEM ESPELHAMENTO - CONTATO CLIENTE

  - [30%] O operador se identificou informando saudação, nome, setor e empresa?
  - [40%] Confirmou com quem está falando?
  - [200%] Informou o motivo do contato?
  - [200%] Informou o número da OS, Placa ou AE?
  - [195%] O operador informou que o espelhamento foi retirado da conta da Opentech?
  - [200%] Operador solicitou ao cliente para refazer o espelhamento do veículo?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Perda de Posição - Cliente (`LOGISTICA-PERDA-POSICAO-CLI`)

- Referencia POP: 4.4.15
- Contexto: PERDA DE POSIÇÃO - CONTATO CLIENTE

  - [30%] O operador se identificou informando saudação, nome, setor e empresa?
  - [40%] Confirmou com quem está falando?
  - [200%] Informou o motivo do contato?
  - [200%] Informou o número da OS, Placa ou AE?
  - [200%] O operador informou corretamente o local onde perdeu a posição? (Estado, cidade, parado/movimento, referência como posto, mecânica, rodovia)
  - [100%] O operador informou as ações adotadas até o momento?
  - [195%] O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista? (Ex.: manutenção, revisão, problemas no rastreador)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Parada Excessiva - Motorista (`LOGISTICA-PARADA-EXCESSIVA-MOT`)

- Referencia POP: 4.4.16
- Contexto: PARADA EXCESSIVA - CONTATO MOTORISTA

  - [30%] O operador se identificou informando saudação, nome, setor e empresa?
  - [40%] Confirmou com quem está falando?
  - [245%] Informou o motivo do contato?
  - [250%] O operador confirmou o motivo pelo qual o motorista está parado a tanto tempo?
  - [300%] Questionou se há previsão de reiniciar a viagem?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Parada Excessiva - Cliente (`LOGISTICA-PARADA-EXCESSIVA-CLI`)

- Referencia POP: 4.4.17
- Contexto: PARADA EXCESSIVA - CONTATO CLIENTE

  - [30%] O operador se identificou informando saudação, nome, setor e empresa?
  - [40%] Confirmou com quem está falando?
  - [200%] Informou o motivo do contato?
  - [200%] Informou o número da OS, Placa ou AE?
  - [198%] O operador confirmou se o cliente sabe o motivo pelo qual o motorista está parado a tanto tempo?
  - [197%] Questionou se o cliente sabe se há previsão de reiniciar a viagem?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [30%] O operador realizou a qualificação do atendimento corretamente
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?


## Setor: mondelez

### Logística Reversa - Receptivo (`MONDELEZ-LOGISTICA-REVERSA`)

- Referencia POP: 4.5.1
- Contexto: LOGÍSTICA REVERSA - RECEPTIVA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [40%] Confirmou se a pessoa é motorista ou transportadora?
  - [100%] Solicitou o número da Nota Fiscal? (Confirmar 2x caso não localize)
  - [100%] Confirmou o nome do cliente que está no nosso sistema? [Informe o cliente]
  - [100%] Confirmou o telefone do motorista?
  - [140%] Questionou o motivo da ocorrência?
  - [145%] Solicitou o número da NF de devolução?
  - [100%] Solicitou informação dos produtos/itens/caixas devolvidos?
  - [100%] Informou o número da Ocorrência gerada no sistema?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 60 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Monitoramento I - Receptivo (`MONDELEZ-MONITORAMENTO-I`)

- Referencia POP: 4.5.2
- Contexto: MONITORAMENTO I - RECEPTIVA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [50%] Confirmou se a pessoa é motorista ou transportadora?
  - [100%] Solicitou o número da Nota Fiscal? (Confirmar 2x caso não localize)
  - [100%] Confirmou o nome do cliente que está no nosso sistema? [Informe o cliente]
  - [100%] Confirmou o telefone do motorista?
  - [145%] Questionou o motivo da ocorrência?
  - [100%] Confirmou quanto tempo que foi finalizado a descarga?
  - [130%] Informou o número da Ocorrência gerada no sistema?
  - [100%] Solicitou que retorne o contato após 2 horas para realizar uma atuação da ocorrência?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 60 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Monitoramento II - Receptivo (`MONDELEZ-MONITORAMENTO-II`)

- Referencia POP: 4.5.3
- Contexto: MONITORAMENTO II - RECEPTIVA

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [40%] Confirmou se a pessoa é motorista ou transportadora?
  - [100%] Solicitou o número da Nota Fiscal? (Confirmar 2x caso não localize)
  - [100%] Confirmou o nome do cliente que está no nosso sistema? [Informe o cliente]
  - [100%] Confirmou o telefone do motorista?
  - [100%] Questionou o motivo da ocorrência?
  - [95%] Questionou a data de agendamento?
  - [95%] Questionou se possui notas de outros clientes?
  - [100%] Informou o número da Ocorrência gerada no sistema?
  - [95%] Solicitou que retorne o contato após 2 horas para realizar uma atuação da ocorrência?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 60 segundos sem interação)?
  - [20%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?


## Setor: checklist

### Checklist de Veículo - Receptivo (`CHECKLIST-VEICULO`)

- Referencia POP: 4.6.1
- Contexto: PROCESSO CHECKLIST - WHATSAPP

  - [30%] O operador se identificou informando saudação.
  - [50%] Enviou o auto texto perguntando qual o tipo de veículo?
  - [100%] Seguiu corretamente o fluxo do checklist conforme a solicitação inicial?
  - [40%] Realizou um atendimento cordial, utilizando linguagem apropriada?
  - [130%] Informou o status final do checklist (aprovado ou reprovado)?
  - [130%] Se reprovado, informou corretamente o motivo da reprovação?
  - [200%] Anexou imagens dos testes no SIL, correspondentes ao veículo e tecnologia analisada?
  - [200%] A informação passada no atendimento corresponde ao que foi registrado no SIL?
  - [30%] Encerrou o checklist no SIL em até 5 minutos após informar o status final?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Encerrou o atendimento no Weon em até 5 minutos após informar o status final do checklist?
  - [30%] Realizou a qualificação correta do atendimento?

### Processo Checklist - Receptivo Whatsapp (`CHECKLIST-RECEPTIVO`)

- Referencia POP: 4.6.2
- Contexto: PROCESSO CHECKLIST - WHATSAPP

  - [30%] O operador se identificou informando saudação.
  - [50%] Enviou o auto texto perguntando qual o tipo de veículo?
  - [100%] Seguiu corretamente o fluxo do checklist conforme a solicitação inicial?
  - [40%] Realizou um atendimento cordial, utilizando linguagem apropriada?
  - [130%] Informou o status final do checklist (aprovado ou reprovado)?
  - [130%] Se reprovado, informou corretamente o motivo da reprovação?
  - [200%] Anexou imagens dos testes no SIL, correspondentes ao veículo e tecnologia analisada?
  - [200%] A informação passada no atendimento corresponde ao que foi registrado no SIL?
  - [30%] Encerrou o checklist no SIL em até 5 minutos após informar o status final?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Encerrou o atendimento no Weon em até 5 minutos após informar o status final do checklist?
  - [30%] Realizou a qualificação correta do atendimento?


## Setor: receptivo

### Atendimento ao Cliente - Receptivo (`RECEPTIVO-CHATBOT`)

- Referencia POP: 4.7.1
- Contexto: CHATBOT - RECEPTIVO

  - [30%] O operador se identificou informando saudação?
  - [130%] Utilizou linguagem apropriada? (Sem usar gírias ou estereótipos de apoio)
  - [130%] Fluxo do atendimento correspondeu à solicitação inicial? (Foco no atendimento)
  - [140%] Realizou o preenchimento de ociosidade? (Não deixando atendimento sem retorno por mais de 3min)
  - [130%] Realizou um atendimento cordial com educação? (Utilizando "obrigado"/"por favor"/"senhor")
  - [140%] Questionou se podia encerrar o atendimento?
  - [140%] Encerrou somente no tempo ocioso padrão? (3min)
  - [130%] Foi realizado a despedida final padrão?
  - [30%] Foi realizada a qualificação correta do atendimento?

### Chatbot - Receptivo Whatsapp (`CELULA-RECEPTIVO`)

- Referencia POP: 4.7.2
- Contexto: CHATBOT - RECEPTIVO

  - [30%] O operador se identificou informando saudação?
  - [130%] Utilizou linguagem apropriada? (Sem usar gírias ou estereótipos de apoio)
  - [130%] Fluxo do atendimento correspondeu à solicitação inicial? (Foco no atendimento)
  - [140%] Realizou o preenchimento de ociosidade? (Não deixando atendimento sem retorno por mais de 3min)
  - [130%] Realizou um atendimento cordial com educação? (Utilizando "obrigado"/"por favor"/"senhor")
  - [140%] Questionou se podia encerrar o atendimento?
  - [140%] Encerrou somente no tempo ocioso padrão? (3min)
  - [130%] Foi realizado a despedida final padrão?
  - [30%] Foi realizada a qualificação correta do atendimento?


## Setor: distribuicao

### Alerta Prioritário - Motorista (`DISTRIBUICAO-PRIORITARIO-MOT`)

- Referencia POP: 4.1.1
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [170%] O operador confirmou a localização e a condição do motorista?
  - [192%] O operador identificou o motivo do alerta? (Sinistro, manutenção, problema técnico, acionamento indevido, etc.)
  - [170%] O operador solicitou vídeo do veículo nos casos necessários (Painel violado, Botão de pânico, Perda de Bateria, Teclado Desconectado, Sensor de desengate e baú)?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Alerta Prioritário - Cliente (`DISTRIBUICAO-PRIORITARIO-CLI`)

- Referencia POP: 4.1.2
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [200%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento?
  - [180%] O operador informou corretamente o local onde gerou o alerta? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [180%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Posição em Atraso - Motorista (`DISTRIBUICAO-POSICAO-MOT`)

- Referencia POP: 4.1.3
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [122%] O operador confirmou a localização atual do motorista? (Em movimento/parado, cidade e referência de local)
  - [200%] Passou orientações para forçar posicionamento do rastreador? (Envio de mensagem, reset de bateria, etc.)
  - [105%] O operador procurou identificar o motivo da perda de sinal? (Embaixo de cobertura, área sem sinal de celular, falha no rastreador, etc.)
  - [105%] O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Posição em Atraso - Cliente (`DISTRIBUICAO-POSICAO-CLI`)

- Referencia POP: 4.1.4
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [120%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)?
  - [110%] O operador informou corretamente o local onde perdeu a posição? (Estado, cidade, parado/movimento, referência como posto, mecânica, rodovia)
  - [110%] O operador questionou se o conjunto possui equipamento de contingência? (Ex.: isca, rastreador secundário, bloqueio remoto)
  - [110%] O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista? (Ex.: manutenção, revisão, problemas no rastreador)
  - [110%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Motorista (`DISTRIBUICAO-PARADA-MOT`)

- Referencia POP: 4.1.5
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [130%] O operador confirmou o motivo pelo qual o motorista parou em local indevido?
  - [130%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [132%] O operador orientou o motorista a reiniciar a viagem e seguir para um local homologado?
  - [140%] O operador informou os riscos operacionais da parada indevida, incluindo problemas com seguro?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Cliente (`DISTRIBUICAO-PARADA-CLI`)

- Referencia POP: 4.1.6
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [114%] O operador informou as ações adotadas até o momento?
  - [140%] O operador informou corretamente o local da parada? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [140%] O operador confirmou se os pontos de parada autorizada foram passados ao motorista antes do início da viagem?
  - [140%] O operador informou ao cliente sobre os riscos operacionais e de seguro caso a parada indevida permaneça?
  - [140%] O operador indicou medidas de segurança ao cliente? (Ex.: Seguir até posto autorizado, acionar escolta, pronta resposta, etc.)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Motorista (`DISTRIBUICAO-DESVIO-MOT`)

- Referencia POP: 4.1.7
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [105%] O operador confirmou o motivo do desvio de rota?
  - [105%] Confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [105%] Orientou o motorista a retornar para a rota ou permanecer parado até confirmação com o cliente?
  - [105%] Coletou qual itinerário o motorista está realizando?
  - [112%] O operador informou os riscos operacionais e de seguro caso o motorista continue fora da rota?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Cliente (`DISTRIBUICAO-DESVIO-CLI`)

- Referencia POP: 4.1.8
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [130%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento? (Resumir os contatos/tratativas com ou sem sucesso)
  - [100%] O operador informou o trajeto que o motorista está realizando e o que estava programado na rota?
  - [100%] O operador questionou se o cliente tem conhecimento do motivo do desvio? O motorista informou antecipadamente?
  - [100%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento antes da viagem?
  - [130%] O operador indicou medidas de segurança ao cliente? (Ex.: Retornar a rota correta ou realizar o ajuste no sistema)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Contato com Ponto de Apoio (`DISTRIBUICAO-PONTO-APOIO`)

- Referencia POP: 4.1.9
- Contexto: Processo de Auditoria Telefônica – Ponto de Apoio

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [195%] O operador informou os dados e as características do veículo? (cor, placa, modelo)
  - [160%] O operador passou detalhes da última posição do veículo? (Referência dentro do posto)
  - [160%] O operador solicitou que o atendente verificasse se o conjunto (cavalo/carreta) estava no local sem violações?
  - [160%] O operador orientou o atendente a chamar o motorista?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Alerta Prioritario - Policia (`DISTRIBUICAO-PRIORITARIO-POLICIA`)

- Referencia POP: 4.1.10
- Contexto: Processo de Auditoria Telefônica – Acionamento Policial

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [130%] O operador passou detalhes do evento que indicam a suspeita?
  - [135%] O operador informou os dados e as características do conjunto e do motorista? (cavalo, carreta, cor, modelo)
  - [130%] O operador passou detalhes do local da ocorrência? (Rodovia, Referência, KM)
  - [150%] O operador solicitou deslocamento e/ou reporte da ocorrência para patrulhamento?
  - [130%] O operador deixou telefone de contato para retorno?
  - [120%] O operador utilizou o alfabeto fonético ao passar informações?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?


## Setor: fenix

### Alerta Prioritário - Motorista (`FENIX-PRIORITARIO-MOT`)

- Referencia POP: 4.1.1
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [170%] O operador confirmou a localização e a condição do motorista?
  - [192%] O operador identificou o motivo do alerta? (Sinistro, manutenção, problema técnico, acionamento indevido, etc.)
  - [170%] O operador solicitou vídeo do veículo nos casos necessários (Painel violado, Botão de pânico, Perda de Bateria, Teclado Desconectado, Sensor de desengate e baú)?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Alerta Prioritário - Cliente (`FENIX-PRIORITARIO-CLI`)

- Referencia POP: 4.1.2
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [200%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento?
  - [180%] O operador informou corretamente o local onde gerou o alerta? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [180%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Posição em Atraso - Motorista (`FENIX-POSICAO-MOT`)

- Referencia POP: 4.1.3
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [122%] O operador confirmou a localização atual do motorista? (Em movimento/parado, cidade e referência de local)
  - [200%] Passou orientações para forçar posicionamento do rastreador? (Envio de mensagem, reset de bateria, etc.)
  - [105%] O operador procurou identificar o motivo da perda de sinal? (Embaixo de cobertura, área sem sinal de celular, falha no rastreador, etc.)
  - [105%] O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Posição em Atraso - Cliente (`FENIX-POSICAO-CLI`)

- Referencia POP: 4.1.4
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [120%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)?
  - [110%] O operador informou corretamente o local onde perdeu a posição? (Estado, cidade, parado/movimento, referência como posto, mecânica, rodovia)
  - [110%] O operador questionou se o conjunto possui equipamento de contingência? (Ex.: isca, rastreador secundário, bloqueio remoto)
  - [110%] O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista? (Ex.: manutenção, revisão, problemas no rastreador)
  - [110%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Motorista (`FENIX-PARADA-MOT`)

- Referencia POP: 4.1.5
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [130%] O operador confirmou o motivo pelo qual o motorista parou em local indevido?
  - [130%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [132%] O operador orientou o motorista a reiniciar a viagem e seguir para um local homologado?
  - [140%] O operador informou os riscos operacionais da parada indevida, incluindo problemas com seguro?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Cliente (`FENIX-PARADA-CLI`)

- Referencia POP: 4.1.6
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [114%] O operador informou as ações adotadas até o momento?
  - [140%] O operador informou corretamente o local da parada? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [140%] O operador confirmou se os pontos de parada autorizada foram passados ao motorista antes do início da viagem?
  - [140%] O operador informou ao cliente sobre os riscos operacionais e de seguro caso a parada indevida permaneça?
  - [140%] O operador indicou medidas de segurança ao cliente? (Ex.: Seguir até posto autorizado, acionar escolta, pronta resposta, etc.)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Motorista (`FENIX-DESVIO-MOT`)

- Referencia POP: 4.1.7
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [105%] O operador confirmou o motivo do desvio de rota?
  - [105%] Confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [105%] Orientou o motorista a retornar para a rota ou permanecer parado até confirmação com o cliente?
  - [105%] Coletou qual itinerário o motorista está realizando?
  - [112%] O operador informou os riscos operacionais e de seguro caso o motorista continue fora da rota?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Cliente (`FENIX-DESVIO-CLI`)

- Referencia POP: 4.1.8
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [130%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento? (Resumir os contatos/tratativas com ou sem sucesso)
  - [100%] O operador informou o trajeto que o motorista está realizando e o que estava programado na rota?
  - [100%] O operador questionou se o cliente tem conhecimento do motivo do desvio? O motorista informou antecipadamente?
  - [100%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento antes da viagem?
  - [130%] O operador indicou medidas de segurança ao cliente? (Ex.: Retornar a rota correta ou realizar o ajuste no sistema)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Contato com Ponto de Apoio (`FENIX-PONTO-APOIO`)

- Referencia POP: 4.1.9
- Contexto: Processo de Auditoria Telefônica – Ponto de Apoio

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [195%] O operador informou os dados e as características do veículo? (cor, placa, modelo)
  - [160%] O operador passou detalhes da última posição do veículo? (Referência dentro do posto)
  - [160%] O operador solicitou que o atendente verificasse se o conjunto (cavalo/carreta) estava no local sem violações?
  - [160%] O operador orientou o atendente a chamar o motorista?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Alerta Prioritario - Policia (`FENIX-PRIORITARIO-POLICIA`)

- Referencia POP: 4.1.10
- Contexto: Processo de Auditoria Telefônica – Acionamento Policial

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [130%] O operador passou detalhes do evento que indicam a suspeita?
  - [135%] O operador informou os dados e as características do conjunto e do motorista? (cavalo, carreta, cor, modelo)
  - [130%] O operador passou detalhes do local da ocorrência? (Rodovia, Referência, KM)
  - [150%] O operador solicitou deslocamento e/ou reporte da ocorrência para patrulhamento?
  - [130%] O operador deixou telefone de contato para retorno?
  - [120%] O operador utilizou o alfabeto fonético ao passar informações?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?


## Setor: transferencia

### Alerta Prioritário - Motorista (`TRANSFERENCIA-PRIORITARIO-MOT`)

- Referencia POP: 4.1.1
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [170%] O operador confirmou a localização e a condição do motorista?
  - [192%] O operador identificou o motivo do alerta? (Sinistro, manutenção, problema técnico, acionamento indevido, etc.)
  - [170%] O operador solicitou vídeo do veículo nos casos necessários (Painel violado, Botão de pânico, Perda de Bateria, Teclado Desconectado, Sensor de desengate e baú)?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Alerta Prioritário - Cliente (`TRANSFERENCIA-PRIORITARIO-CLI`)

- Referencia POP: 4.1.2
- Contexto: Critérios de Auditoria – Alerta Prioritário no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [200%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento?
  - [180%] O operador informou corretamente o local onde gerou o alerta? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [180%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?

### Posição em Atraso - Motorista (`TRANSFERENCIA-POSICAO-MOT`)

- Referencia POP: 4.1.3
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [122%] O operador confirmou a localização atual do motorista? (Em movimento/parado, cidade e referência de local)
  - [200%] Passou orientações para forçar posicionamento do rastreador? (Envio de mensagem, reset de bateria, etc.)
  - [105%] O operador procurou identificar o motivo da perda de sinal? (Embaixo de cobertura, área sem sinal de celular, falha no rastreador, etc.)
  - [105%] O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Posição em Atraso - Cliente (`TRANSFERENCIA-POSICAO-CLI`)

- Referencia POP: 4.1.4
- Contexto: Critérios de Auditoria – Alerta Posição em Atraso no Contato com o Cliente

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [120%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)?
  - [110%] O operador informou corretamente o local onde perdeu a posição? (Estado, cidade, parado/movimento, referência como posto, mecânica, rodovia)
  - [110%] O operador questionou se o conjunto possui equipamento de contingência? (Ex.: isca, rastreador secundário, bloqueio remoto)
  - [110%] O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista? (Ex.: manutenção, revisão, problemas no rastreador)
  - [110%] O operador confirmou os contatos atuais do condutor?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Motorista (`TRANSFERENCIA-PARADA-MOT`)

- Referencia POP: 4.1.5
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [130%] O operador confirmou o motivo pelo qual o motorista parou em local indevido?
  - [130%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [132%] O operador orientou o motorista a reiniciar a viagem e seguir para um local homologado?
  - [140%] O operador informou os riscos operacionais da parada indevida, incluindo problemas com seguro?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Parada Indevida - Cliente (`TRANSFERENCIA-PARADA-CLI`)

- Referencia POP: 4.1.6
- Contexto: Critérios de Auditoria – Alerta Parada Indevida no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [114%] O operador informou as ações adotadas até o momento?
  - [140%] O operador informou corretamente o local da parada? (Cidade, estado, referência como rodovia, posto, mecânica, etc.)
  - [140%] O operador confirmou se os pontos de parada autorizada foram passados ao motorista antes do início da viagem?
  - [140%] O operador informou ao cliente sobre os riscos operacionais e de seguro caso a parada indevida permaneça?
  - [140%] O operador indicou medidas de segurança ao cliente? (Ex.: Seguir até posto autorizado, acionar escolta, pronta resposta, etc.)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Motorista (`TRANSFERENCIA-DESVIO-MOT`)

- Referencia POP: 4.1.7
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [200%] O operador confirmou a senha de segurança antes de prosseguir?
  - [103%] O operador informou claramente o motivo do contato?
  - [105%] O operador confirmou o motivo do desvio de rota?
  - [105%] Confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?
  - [105%] Orientou o motorista a retornar para a rota ou permanecer parado até confirmação com o cliente?
  - [105%] Coletou qual itinerário o motorista está realizando?
  - [112%] O operador informou os riscos operacionais e de seguro caso o motorista continue fora da rota?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Desvio de Rota - Cliente (`TRANSFERENCIA-DESVIO-CLI`)

- Referencia POP: 4.1.8
- Contexto: Critérios de Auditoria – Alerta Desvio de Rota no Contato com o Motorista

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [130%] O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?
  - [114%] O operador informou as ações adotadas até o momento? (Resumir os contatos/tratativas com ou sem sucesso)
  - [100%] O operador informou o trajeto que o motorista está realizando e o que estava programado na rota?
  - [100%] O operador questionou se o cliente tem conhecimento do motivo do desvio? O motorista informou antecipadamente?
  - [100%] O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento antes da viagem?
  - [130%] O operador indicou medidas de segurança ao cliente? (Ex.: Retornar a rota correta ou realizar o ajuste no sistema)
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Contato com Ponto de Apoio (`TRANSFERENCIA-PONTO-APOIO`)

- Referencia POP: 4.1.9
- Contexto: Processo de Auditoria Telefônica – Ponto de Apoio

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [120%] O operador informou claramente o motivo do contato?
  - [195%] O operador informou os dados e as características do veículo? (cor, placa, modelo)
  - [160%] O operador passou detalhes da última posição do veículo? (Referência dentro do posto)
  - [160%] O operador solicitou que o atendente verificasse se o conjunto (cavalo/carreta) estava no local sem violações?
  - [160%] O operador orientou o atendente a chamar o motorista?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?

### Alerta Prioritario - Policia (`TRANSFERENCIA-PRIORITARIO-POLICIA`)

- Referencia POP: 4.1.10
- Contexto: Processo de Auditoria Telefônica – Acionamento Policial

  - [10%] Saudação?
  - [10%] Nome?
  - [10%] Setor/Empresa?
  - [40%] Confirmou com quem está falando?
  - [130%] O operador passou detalhes do evento que indicam a suspeita?
  - [135%] O operador informou os dados e as características do conjunto e do motorista? (cavalo, carreta, cor, modelo)
  - [130%] O operador passou detalhes do local da ocorrência? (Rodovia, Referência, KM)
  - [150%] O operador solicitou deslocamento e/ou reporte da ocorrência para patrulhamento?
  - [130%] O operador deixou telefone de contato para retorno?
  - [120%] O operador utilizou o alfabeto fonético ao passar informações?
  - [30%] Realizou a despedida padrão com cordialidade?
  - [30%] Utilizou a função mudo corretamente para evitar ruídos externos?
  - [15%] Evitou silêncios prolongados (mais de 45 segundos sem interação)?
  - [20%] O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?
  - [30%] Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?
  - [10%] O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de girias?
