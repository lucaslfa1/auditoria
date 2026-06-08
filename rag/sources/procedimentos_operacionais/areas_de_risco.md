---
setor: areas_de_risco
alertas_cobertos:
  - alerta_prioritario_motorista
  - alerta_prioritario_cliente
  - posicao_em_atraso_motorista
  - posicao_em_atraso_cliente
  - parada_indevida_motorista
  - parada_indevida_cliente
  - desvio_de_rota_motorista
  - desvio_de_rota_cliente
  - ponto_de_apoio
  - acionamento_policial
versao: 1.0
ultima_revisao: 2026-04-16
fonte_original: docs/procedimentos_operacionais/Ajustes IA - *.docx
---

# POP — Áreas de Risco (Distribuição, Rastreamento, UTI, Fênix)

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.

Particularidades da auditoria do Risco:
Rastreamento > 2 ligações efetuadas (Motorista, Cliente/Transportador, Ponto de Apoio ou Polícia) > Alertas Prioritários, Parada, Desvio e Posição.
Distribuição > 2 ligações efetuadas (Motorista, Cliente/Transportador, Ponto de Apoio ou Polícia) > Alertas Prioritários, Parada, Desvio e Posição.
UTI > 2 ligações efetuadas (Motorista, Cliente/Transportador, Ponto de Apoio ou Polícia) > Alertas Prioritários, Parada, Desvio e Posição.
BAS > 2 acionamentos policiais > Alertas Prioritários, Parada, Desvio, Posição, Acidente e Roubo.
Evitar ligações que falem sobre manutenção, problemas no veículo, oficina, etc, exceto quando está ligando para cobrar algum alerta de violação, aí sim pode pegar ligações nesse sentido, pois está confirmando que essa violação gerada foi devido a esse problema/manutenção/revisão.
Evitar ligações para alertas de parada indevida, onde a informação é que está em alguma filial/garagem da empresa/cliente/trânsito lento/aduana/posto fiscal/policia.
Evitar ligações de fim de viagem.
Evitar ligações de sinal retirado/sem espelhamento.
Evitar ligações onde o condutor/transportador informar que a viagem ainda não foi iniciada.
## ALERTAS PRIORITÁRIOS – CONTATO MOTORISTA – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### O operador confirmou a senha de segurança antes de prosseguir? `peso=2.0`

Após realizar sua identificação o operador deve realizar a confirmação da senha de segurança do motorista, sendo que essa senha na maioria das vezes são apenas 4 dígitos, podendo ser o final do número da Autorização de Embarque, o início ou o final do CPF, vai depender por qual cliente ele está realizando essa viagem. Caso o operador não questione sobre a senha em nenhum momento da ligação, a auditoria deve ser zerada. Se o operador passar qualquer informação referente a viagem ou o alerta gerado, antes de pedir a senha e o motorista confirmar, a auditoria também será zerada. Caso o operador solicitar o CPF no lugar da senha ou pedir a senha de segurança e o motorista confirmar os 11 dígitos do CPF ou algum outro dado que não seja a senha, a auditoria também deve ser zerada. O operador só pode aceitar CPF ou outros dados, caso o motorista informe que não recebeu a senha de segurança ou informe que não consegue confirmar a senha naquele momento, pois está dirigindo, em movimento, ou está longe do veículo e a senha ficou no caminhão. Caso contrário, precisa se confirmada a senha, mesmo que o operador tenha que esperar o motorista encontrar a informação. A auditoria deve ser zerada também, quando o motorista informa uma senha incorreta, que não bate com os 4 últimos dígitos da Autorização de Embarque, 4 primeiros dígitos do CPF ou os 4 últimos dígitos do CPF. Outro item que deve zerar a auditoria é nos casos onde o operador, da dicas sobre qual é a senha do motorista quando ele informa que não sabe, dicas como a quantidade de dígitos que a senha tem ou informa que é o final da AE, enfim, não pode passar nenhum tipo de dica sobre a senha, ao solicitar ela, o condutor deve saber qual é e informar para o operador. O último item que zera a auditoria, é quando o condutor informa uma senha que está errada e o operador já informa logo no início, que aquela senha está incorreta, não confere ou não bate com o que temos no sistema, essa informação que o operador passa, pode colocar em risco a segurança do condutor, do veículo e da carga, já que ele pode ter confirmado a senha errada propositalmente, pois pode estar abordado por meliantes e está tentando de alguma  forma, sinalizar para o operador que algo não está certo. Em casos onde o motorista confirma a senha errada, o operador deve confirmar outros dados como CPF, nome da mãe, origem/destino da viagem, etc, seguir com o atendimento normalmente, realizando a confirmação do alerta e ao final, quando perceber que esta tudo bem e que realmente é o motorista, deve informar que a senha repassada no início da chamada não estava correta e orientar o motorista a entrar em contato com a transportadora e solicitar a senha certa.
### O operador informou claramente o motivo do contato? `peso=1.03`

Após a identificação e confirmação de senha, o operador deve informar que está ligando para verificar algumas informações sobre a viagem, deve evitar já de início informar qual o alerta, pois em alguns casos o alerta pode ter sido gerado devido a uma abordagem e o operador ao informar que gerou alguma violação, pode acabar revelando aos meliantes que o condutor pressionou o botão de pânico por exemplo, e então coloca em risco a vida do motorista.
### O operador confirmou a localização e a condição do motorista? `peso=1.7`

O operador deve questionar ao condutor sobre sua localização atual, para confirmar se a informação repassada pelo motorista confere com o posicionamento que tem no sistema, precisa saber se está em movimento, parado, qual rodovia, cidade e nome do local onde se encontra caso esteja parado. Também precisa confirmar a condição do motorista, questionando se está tudo bem com ele, como está o andamento da viagem, afim de identificar qualquer situação anormal.
O operador identificou o motivo do alerta? (Sinistro, manutenção, problema técnico, acionamento indevido, etc.) Peso 1,92
O operador deve de alguma forma, confirmar o que aconteceu para ter gerado aquele alerta, se o veículo está passando por alguma manutenção/revisão, se passou com o veículo por algum buraco, quebra molas ou trepidação, se desligou a chave geral, se passou por teste/checklist, se acabou pressionando o botão de pânico sem querer ou propositalmente para chamar a atenção.
### O operador solicitou vídeo do veículo nos casos necessários (Painel violado, Botão de pânico, Perda de Bateria, Teclado Desconectado, Sensor de desengate e baú)? `peso=1.7`

O operador deve solicitar ao condutor, que grave um vídeo de dentro da cabine do veículo, em 360°, mostrando toda parte interna, atrás dos bancos, retrovisores, painel, etc, durante essa gravação ele deve informar a data e horários atuais e senha de segurança ou o CPF caso não tenha senha. Esse vídeo é necessário para confirmarmos a integridade do condutor e veículo, para confirmar que está realmente tudo ok e sem violações, tendo certeza que ele não está abordado por nenhum meliante. O operador além de solicitar que o motorista grave esse vídeo, deve pedir que envie para nós através do WhatsApp.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## POSIÇÃO EM ATRASO – CONTATO MOTORISTA – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### O operador confirmou a senha de segurança antes de prosseguir? `peso=2.0`

Após realizar sua identificação o operador deve realizar a confirmação da senha de segurança do motorista, sendo que essa senha na maioria das vezes são apenas 4 dígitos, podendo ser o final do número da Autorização de Embarque, o início ou o final do CPF, vai depender por qual cliente ele está realizando essa viagem. Caso o operador não questione sobre a senha em nenhum momento da ligação, a auditoria deve ser zerada. Se o operador passar qualquer informação referente a viagem ou o alerta gerado, antes de pedir a senha e o motorista confirmar, a auditoria também será zerada. Caso o operador solicitar o CPF no lugar da senha ou pedir a senha de segurança e o motorista confirmar os 11 dígitos do CPF ou algum outro dado que não seja a senha, a auditoria também deve ser zerada. O operador só pode aceitar CPF ou outros dados, caso o motorista informe que não recebeu a senha de segurança ou informe que não consegue confirmar a senha naquele momento, pois está dirigindo, em movimento, ou está longe do veículo e a senha ficou no caminhão. Caso contrário, precisa se confirmada a senha, mesmo que o operador tenha que esperar o motorista encontrar a informação. A auditoria deve ser zerada também, quando o motorista informa uma senha incorreta, que não bate com os 4 últimos dígitos da Autorização de Embarque, 4 primeiros dígitos do CPF ou os 4 últimos dígitos do CPF. Outro item que deve zerar a auditoria é nos casos onde o operador, dá dicas sobre qual é a senha do motorista quando ele informa que não sabe, dicas como a quantidade de dígitos que a senha tem ou informa que é o final da AE, enfim, não pode passar nenhum tipo de dica sobre a senha, ao solicitar ela, o condutor deve saber qual é e informar para o operador. O último item que zera a auditoria, é quando o condutor informa uma senha que está errada e o operador já informa logo no início, que aquela senha está incorreta, não confere ou não bate com o que temos no sistema, essa informação que o operador passa, pode colocar em risco a segurança do condutor, do veículo e da carga, já que ele pode ter confirmado a senha errada propositalmente, pois pode estar abordado por meliantes e está tentando de alguma  forma, sinalizar para o operador que algo não está certo. Em casos onde o motorista confirma a senha errada, o operador deve confirmar outros dados como CPF, nome da mãe, origem/destino da viagem, etc, seguir com o atendimento normalmente, realizando a confirmação do alerta e ao final, quando perceber que está tudo bem e que realmente é o motorista, deve informar que a senha repassada no início da chamada não estava correta e orientar o motorista a entrar em contato com a transportadora e solicitar a senha certa.
### O operador informou claramente o motivo do contato? `peso=1.03`

Após a identificação e confirmação de senha, o operador deve informar que está ligando para verificar algumas informações sobre a viagem, deve evitar já de início informar qual o alerta, pois em alguns casos o alerta pode ter sido gerado devido a uma abordagem e o operador ao informar que perdemos o sinal do veículo e que não estamos conseguindo rastrear ele, caso esteja com um meliante junto, já informou ao mesmo que podem roubar o veículo e a carga, pois não temos a posição dele atualizada.
O operador confirmou a localização atual do motorista? (Em movimento/parado, cidade e referência de local) Peso 1,22
O operador precisa perguntar ao condutor onde ele se encontra no momento, se estiver em movimento, por onde está passando, qual rodovia, KM, cidade, estado. Caso esteja parado, em qual local está, o nome do estabelecimento, a cidade. É essencial sabermos a localização do veículo naquele momento, já que estamos sem a posição atualizada.
Passou orientações para forçar posicionamento do rastreador? (Envio de mensagem, reset de bateria, etc.) Peso 2,0
O operador precisa solicitar ao condutor, que realize alguns procedimentos no veículo, para forçar a comunicação do rastreador, para que o veículo volte a posicionar em nosso sistema e podermos acompanhar a viagem, assegurando que nada aconteça. O que pode ser solicitado ao motorista, é que ligue a ignição do veículo, envie uma mensagem livre no teclado, desligar a chave geral por alguns minutos e ligar novamente, se estiver debaixo de alguma cobertura ou parado por muito tempo, pedir para movimentar o veículo.
O operador procurou identificar o motivo da perda de sinal? (Embaixo de cobertura, área sem sinal de celular, falha no rastreador, etc.) Peso 1,05
O operador precisa identificar porque o veículo perdeu comunicação, questionando ao motorista se aquela região é ruim de sinal, ou se está debaixo de alguma cobertura, está dentro de algum galpão, túnel, ou se o clima está nublado, com muita chuva. Pois tudo isso acaba interferindo no sinal. Por isso é importante o operador realizar esses questionamentos, pois se não tiver nenhum motivo para isso, pode ser que a antena esteja com problemas e aí se faz necessário passar por manutenção.
### O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer? `peso=1.05`

Para evitar prejuízos e demonstrar o risco que é, o veículo ficar sem o posicionamento, o operador precisa informar ao condutor que ele precisa realizar os procedimentos para forçar a comunicação, pois em caso de sinistro com o sinal do veículo desatualizado, pode haver problemas com a cobertura do seguro. Por isso é essencial que o condutor realize os procedimentos para que o veículo volte a posicionar o quanto antes.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## PARADA INDEVIDA – CONTATO MOTORISTA – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### O operador confirmou a senha de segurança antes de prosseguir? `peso=2.0`

Após realizar sua identificação o operador deve realizar a confirmação da senha de segurança do motorista, sendo que essa senha na maioria das vezes são apenas 4 dígitos, podendo ser o final do número da Autorização de Embarque, o início ou o final do CPF, vai depender por qual cliente ele está realizando essa viagem. Caso o operador não questione sobre a senha em nenhum momento da ligação, a auditoria deve ser zerada. Se o operador passar qualquer informação referente a viagem ou o alerta gerado, antes de pedir a senha e o motorista confirmar, a auditoria também será zerada. Caso o operador solicitar o CPF no lugar da senha ou pedir a senha de segurança e o motorista confirmar os 11 dígitos do CPF ou algum outro dado que não seja a senha, a auditoria também deve ser zerada. O operador só pode aceitar CPF ou outros dados, caso o motorista informe que não recebeu a senha de segurança ou informe que não consegue confirmar a senha naquele momento, pois está dirigindo, em movimento, ou está longe do veículo e a senha ficou no caminhão. Caso contrário, precisa se confirmada a senha, mesmo que o operador tenha que esperar o motorista encontrar a informação. A auditoria deve ser zerada também, quando o motorista informa uma senha incorreta, que não bate com os 4 últimos dígitos da Autorização de Embarque, 4 primeiros dígitos do CPF ou os 4 últimos dígitos do CPF. Outro item que deve zerar a auditoria é nos casos onde o operador, dá dicas sobre qual é a senha do motorista quando ele informa que não sabe, dicas como a quantidade de dígitos que a senha tem ou informa que é o final da AE, enfim, não pode passar nenhum tipo de dica sobre a senha, ao solicitar ela, o condutor deve saber qual é e informar para o operador. O último item que zera a auditoria, é quando o condutor informa uma senha que está errada e o operador já informa logo no início, que aquela senha está incorreta, não confere ou não bate com o que temos no sistema, essa informação que o operador passa, pode colocar em risco a segurança do condutor, do veículo e da carga, já que ele pode ter confirmado a senha errada propositalmente, pois pode estar abordado por meliantes e está tentando de alguma  forma, sinalizar para o operador que algo não está certo. Em casos onde o motorista confirma a senha errada, o operador deve confirmar outros dados como CPF, nome da mãe, origem/destino da viagem, etc, seguir com o atendimento normalmente, realizando a confirmação do alerta e ao final, quando perceber que está tudo bem e que realmente é o motorista, deve informar que a senha repassada no início da chamada não estava correta e orientar o motorista a entrar em contato com a transportadora e solicitar a senha certa.
### O operador informou claramente o motivo do contato? `peso=1.03`

Após a identificação e confirmação de senha, o operador deve informar que está ligando para verificar algumas informações sobre a viagem, deve evitar já de início informar qual o alerta, pois em alguns casos o alerta pode ter sido gerado devido a uma abordagem e o operador ao informar que estamos ligando devido a uma parada indevida, pode acabar levantando um alerta aos meliantes, colocando em risco a vida do condutor.
### O operador confirmou o motivo pelo qual o motorista parou em local indevido? `peso=1.3`

O operador precisa deixar claro na ligação o motivo de o condutor ter parado naquele local, ele pode perguntar ao motorista de alguma forma, ou caso o motorista tenha enviado macro informando o motivo da parada, o operador pode confirmar se a parada indevida foi realmente pelo motivo informado por mensagem. É importante ter essa informação, para registro em sistema e para gerar a não conformidade necessária.
### O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento? `peso=1.3`

O operador precisa perguntar ao motorista se o mesmo recebeu o plano de viagem, um documento que deve ser entregue para ele antes do início da viagem, contendo os locais autorizados para paradas e a rota que deve seguir. Importante termos essa informação, para saber se o condutor parou em local indevido por escolha dele, ou se parou pois não tinha a listagem de postos autorizados e não sabia que aquele local era proibido.
### O operador orientou o motorista a reiniciar a viagem e seguir para um local homologado? `peso=1.32`

O operador precisa orientar o condutor a realizar as paradas de acordo com o seu plano de viagem e que o correto é o mesmo sair daquele local indevido, seguindo sua viagem, ou caso necessite permanecer parado, que siga para um posto homologado. Inclusive o operador pode verificar no sistema qual o posto mais próximo e indicar ao motorista que siga para lá. O que não pode é aceitar que o condutor permaneça naquele local, sem realizar as orientações anteriores. O reinício deve ser imediato.
### O operador informou os riscos operacionais da parada indevida, incluindo problemas com seguro? `peso=1.40`

Após todas as orientações, o operador precisa deixar o motorista ciente de que em caso de sinistro naquele local indevido, pode não ter cobertura securitária. Inclusive quando o condutor se recusa a reiniciar viagem ou seguir para um local autorizado. Precisa deixar claro na ligação, essa questão de perda do seguro e que o motorista está assumindo a responsabilidade por não aceitar sair do local.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## DESVIO DE ROTA – CONTATO MOTORISTA – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### O operador confirmou a senha de segurança antes de prosseguir? `peso=2.0`

Após realizar sua identificação o operador deve realizar a confirmação da senha de segurança do motorista, sendo que essa senha na maioria das vezes são apenas 4 dígitos, podendo ser o final do número da Autorização de Embarque, o início ou o final do CPF, vai depender por qual cliente ele está realizando essa viagem. Caso o operador não questione sobre a senha em nenhum momento da ligação, a auditoria deve ser zerada. Se o operador passar qualquer informação referente a viagem ou o alerta gerado, antes de pedir a senha e o motorista confirmar, a auditoria também será zerada. Caso o operador solicitar o CPF no lugar da senha ou pedir a senha de segurança e o motorista confirmar os 11 dígitos do CPF ou algum outro dado que não seja a senha, a auditoria também deve ser zerada. O operador só pode aceitar CPF ou outros dados, caso o motorista informe que não recebeu a senha de segurança ou informe que não consegue confirmar a senha naquele momento, pois está dirigindo, em movimento, ou está longe do veículo e a senha ficou no caminhão. Caso contrário, precisa se confirmada a senha, mesmo que o operador tenha que esperar o motorista encontrar a informação. A auditoria deve ser zerada também, quando o motorista informa uma senha incorreta, que não bate com os 4 últimos dígitos da Autorização de Embarque, 4 primeiros dígitos do CPF ou os 4 últimos dígitos do CPF. Outro item que deve zerar a auditoria é nos casos onde o operador, dá dicas sobre qual é a senha do motorista quando ele informa que não sabe, dicas como a quantidade de dígitos que a senha tem ou informa que é o final da AE, enfim, não pode passar nenhum tipo de dica sobre a senha, ao solicitar ela, o condutor deve saber qual é e informar para o operador. O último item que zera a auditoria, é quando o condutor informa uma senha que está errada e o operador já informa logo no início, que aquela senha está incorreta, não confere ou não bate com o que temos no sistema, essa informação que o operador passa, pode colocar em risco a segurança do condutor, do veículo e da carga, já que ele pode ter confirmado a senha errada propositalmente, pois pode estar abordado por meliantes e está tentando de alguma  forma, sinalizar para o operador que algo não está certo. Em casos onde o motorista confirma a senha errada, o operador deve confirmar outros dados como CPF, nome da mãe, origem/destino da viagem, etc, seguir com o atendimento normalmente, realizando a confirmação do alerta e ao final, quando perceber que está tudo bem e que realmente é o motorista, deve informar que a senha repassada no início da chamada não estava correta e orientar o motorista a entrar em contato com a transportadora e solicitar a senha certa.

### O operador informou claramente o motivo do contato? `peso=1.03`

Após a identificação e confirmação de senha, o operador deve informar que está ligando para verificar algumas informações sobre a viagem, deve evitar já de início informar qual o alerta, pois em alguns casos o alerta pode ter sido gerado devido a uma abordagem e o operador ao informar que estamos ligando devido a um desvio de rota, pode acabar levantando um alerta aos meliantes, colocando em risco a vida do condutor.
### O operador confirmou o motivo do desvio de rota? `peso=1.05`

O operador precisa confirmar se algo aconteceu para que ele esteja seguindo por aquele caminho, se precisou ir até algum posto, ir até alguma garagem/filial da empresa, precisou desviar devido algum acidente, obras na pista, porque o veículo grande não pode passar por dentro da cidade ou recebeu alguma orientação pra ir por esse caminho, recebeu um plano de viagem diferente. É preciso entender o motivo do desvio, para realizar as devidas orientações, para que não aconteça novamente.
### Confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento? `peso=1.05`

O operador precisa perguntar ao motorista se o mesmo recebeu o plano de viagem, um documento que deve ser entregue para ele antes do início da viagem, contendo os locais autorizados para paradas e a rota que deve seguir. Importante termos essa informação, para saber se o condutor desviou da rota por escolha dele, ou se desviou pois não tinha o plano de viagem com a rota e não sabia por onde deveria seguir.
### Orientou o motorista a retornar para a rota ou permanecer parado até confirmação com o cliente? `peso=1.05`

O operador precisa orientar o motorista a retornar para a rota correta o quanto ates, podendo verificar no mapa um caminho que faça ele retornar para a rota cadastrada no sistema, e caso não consiga retornar, pois está muito longe, ou aquela rota não é autorizado passar veículos grandes/pesados, o operador precisa pedir ao motorista, para parar no próximo local autorizado e entrar em contato com a transportadora para solicitar ajuste da rota. Mas precisa orientar a parar, não somente ligar e pedir ajuste. Caso não tenha a orientação de retornar para a rota ou de parar e solicitar ajuste, o critério é despontuado.
### Coletou qual itinerário o motorista está realizando? `peso=1.05`

O operador precisa verificar junto ao condutor, por qual caminho ele vai seguir a viagem, coletando qual/quais rodovias e cidades vai passar.
### O operador informou os riscos operacionais e de seguro caso o motorista continue fora da rota? `peso=1.12`

Após todas as orientações, o operador precisa deixar o motorista ciente de que em caso de sinistro estando fora de rota, pode não ter cobertura securitária. Por isso ele precisa voltar para a rota ou parar e entrar em contato com a transportadora, deve deixar claro na ligação, essa questão de perda do seguro e que o motorista está assumindo a responsabilidade por não retornar a rota correta ou parar e solicitar ajuste.


### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.20`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.


## ALERTAS PRIORITÁRIOS – CONTATO CLIENTE – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### O operador informou claramente o motivo do contato? `peso=1.2`

O operador precisa informar ao cliente o motivo pelo qual está entrando em contato, nesse caso, informar que gerou algum alerta prioritário, como acionamento do botão de pânico, violação de painel, teclado desconectado, perda de bateria, violação de antena ou interferência por jammer.
### O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)? `peso=1.15`

O operador precisa informar ao cliente as ações que já realizou até o momento, na tratativa desse alerta, seja o envio de comandos/mensagens, tentativas de contato com ou sem sucesso ao motorista e ponto de apoio, demonstrando ao cliente preocupação e atenção.
O operador informou corretamente o local onde gerou o alerta? (Cidade, estado, referência como rodovia, posto, mecânica, etc.) Peso 1,8
O operador deve informar ao cliente o local onde gerou o alerta, caso o veículo esteja parado, tem que informar o nome do local e cidade, se estava em movimento, informar a rodovia, qual cidade está passando.
### O operador confirmou os contatos atuais do condutor? `peso=1.8`

O operador precisa confirmar com o cliente o número de contato do motorista, caso não tenha conseguido contato com ele pelo número que temos cadastrado. As vezes o condutor mudou de número, ou possui um segundo telefone e realizando essa confirmação com o cliente, podemos atualizar o cadastro do motorista com o telefone correto.
O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro? 2,0
Essa informação é crucial, principalmente quando o operador não conseguiu contato com o condutor, é importante enfatizar para o cliente que está tratando essa situação como uma suspeita de sinistro, já que não temos informação do que pode estar acontecendo no veículo.  E essa informação acaba mostrando para o cliente que se trata de uma situação de risco e deixa ele em alerta e disposto a nos auxiliar, na tentativa de contato com o condutor.

### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.


## POSIÇÃO EM ATRASO – CONTATO CLIENTE – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### O operador informou claramente o motivo do contato? `peso=1.2`

O operador precisa informar ao cliente o motivo pelo qual está entrando em contato, nesse caso, informar que acabamos perdendo o sinal do veículo, que o sinal está desatualizado.
### O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)? `peso=1.15`

O operador precisa informar ao cliente as ações que já realizou até o momento, na tratativa desse alerta, seja o envio de comandos/mensagens, tentativas de contato com ou sem sucesso ao motorista e ponto de apoio, demonstrando ao cliente preocupação e atenção.
O operador informou corretamente o local onde perdeu a posição? (Estado, cidade, parado/movimento, referência como posto, mecânica, rodovia) Peso 1,10
O operador deve informar ao cliente o local onde o veículo perdeu posição, no caso, a última posição que tivemos do veículo no sistema, se o veículo estiver parado, tem que informar o nome do local e cidade, se perdeu a comunicação em movimento, informar a rodovia, qual cidade estava passando.
O operador questionou se o conjunto possui equipamento de contingência? (Ex.: isca, rastreador secundário, bloqueio remoto) Peso 1,1
O operador precisa questionar se o cliente sabe informar se o veículo possui algum equipamento de contingência, como isca ou segundo rastreador, que possa nos auxiliar, trazendo uma posição atualizada de onde o veículo se encontra naquele momento.
O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista? (Ex.: manutenção, revisão, problemas no rastreador) Peso 1,1
O operador precisa perguntar ao cliente se ele possui alguma informação referente a esse condutor e veículo, pois muitas vezes o motorista acaba avisando a transportadora algum problema que o veículo apresentou, manutenção/revisão programada, ou alguma parada que precisou realizar.
### O operador confirmou os contatos atuais do condutor? `peso=1.1`

O operador precisa confirmar com o cliente o número de contato do motorista, caso não tenha conseguido contato com ele pelo número que temos cadastrado. As vezes o condutor mudou de número, ou possui um segundo telefone e realizando essa confirmação com o cliente, podemos atualizar o cadastro do motorista com o telefone correto.
### O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro? `peso=1.2`

Essa informação é crucial, principalmente quando o operador não conseguiu contato com o condutor, é importante enfatizar para o cliente que está tratando essa situação como uma suspeita de sinistro, já que não temos informação do que pode estar acontecendo no veículo.  E essa informação acaba mostrando para o cliente que se trata de uma situação de risco e deixa ele em alerta e disposto a nos auxiliar, na tentativa de contato com o condutor.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## PARADA INDEVIDA – CONTATO CLIENTE – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### O operador informou claramente o motivo do contato? `peso=1.2`

O operador precisa informar ao cliente o motivo pelo qual está entrando em contato, nesse caso, informar que estamos com um veículo que parou ou está parado em um local não homologado pelo cliente.
### O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)? `peso=1.15`

O operador precisa informar ao cliente as ações que já realizou até o momento, na tratativa desse alerta, seja o envio de comandos/mensagens, tentativas de contato com ou sem sucesso ao motorista e ponto de apoio, demonstrando ao cliente preocupação e atenção.
O operador informou corretamente o local da parada? (Cidade, estado, referência como rodovia, posto, mecânica, etc.) Peso 1,4
O operador precisa informar o local onde o motorista realizou a parada indevida, informando se é um posto, oficina, beira da rodovia, dentre outros lugares possíveis. Informar qual a rodovia, cidade e estado. Para que o cliente saiba identificar onde foi essa parada e possa nos informar caso seja algum local que ele conheça ou que o condutor informou que iria parar naquele local.
### O operador confirmou se os pontos de parada autorizada foram passados ao motorista antes do início da viagem? `peso=1.4`

O operador precisa confirmar com o cliente, se o plano de viagem com a lista de locais autorizados foi entregue ao motorista antes de ele iniciar a viagem. Pois muitas vezes a parada indevida foi realizada devido o condutor não ter recebido essa listagem e não sabe quais locais ele pode efetuar paradas.
### O operador informou ao cliente sobre os riscos operacionais e de seguro caso a parada indevida permaneça? `peso=1.4`

O operador precisa deixar o cliente ciente de que caso o condutor permaneça parado nesse local não homologado e acabe acontecendo algum sinistro, pode não haver cobertura securitária do veículo e da carga. O cliente e condutor assumem o risco se o veículo permanecer naquela parada indevida.
O operador indicou medidas de segurança ao cliente? (Ex.: Seguir até posto autorizado, acionar escolta, pronta resposta, etc.) Peso 1,40
O operador deve pedir auxilio ao cliente, para que oriente o condutor a seguir com o plano de viagem, realizando paradas somente em locais que são autorizados, e solicitar para que o condutor reinicie imediatamente dessa parada e siga para um local homologado, caso haja resistência para sair do local, informar que pode ser acionado uma equipe de escolta ou pronta resposta para ir até o veículo e realizar a segurança da carga e que esse custo é direcionado para a transportadora.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## DESVIO DE ROTA – CONTATO CLIENTE – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### O operador informou claramente o motivo do contato? `peso=1.2`

O operador precisa informar ao cliente o motivo pelo qual está entrando em contato, nesse caso, informar que estamos com um veículo que desviou da rota informada no sistema.
### O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)? `peso=1.15`

O operador precisa informar ao cliente as ações que já realizou até o momento, na tratativa desse alerta, seja o envio de comandos/mensagens, tentativas de contato com ou sem sucesso ao motorista e ponto de apoio, demonstrando ao cliente preocupação e atenção.
### O operador informou o trajeto que o motorista está realizando e o que estava programado na rota? `peso=1.0`

O operador precisa informar ao cliente qual a rota esta programada em nosso sistema, informando nome da rua/rodovia, quais cidades ele deveria passar e informar qual a rota que o condutor esta realizando, que está gerando esse desvio, também informando o nome da rua/rodovia e por quais cidade já passou e quais provavelmente vai passar.
### O operador questionou se o cliente tem conhecimento do motivo do desvio? O motorista informou antecipadamente? `peso=1.0`

O operador deve questionar ao cliente se ele possui alguma informação referente a esse desvio, se o condutor avisou com antecedência que precisaria desviar por algum motivo, ou se foram eles que instruíram o condutor a ir por outra rota, por conta de pedágios, ou por ser mais rápido, etc.
### O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento antes da viagem? `peso=1.0`

O operador precisa confirmar com o cliente, se o plano de viagem com a rota programada foi entregue ao motorista antes de ele iniciar a viagem. Pois muitas vezes eles acabam saindo fora de rota, devido ao condutor não ter recebido o plano de viagem, que diz por quais rodovias e cidades ele deve seguir. Nos casos que não recebem o plano, muitos acabam seguindo por rotas que já estão acostumados a fazer ou acabam seguindo o GPS.
O operador indicou medidas de segurança ao cliente? (Ex.: Retornar a rota correta ou realizar o ajuste no sistema) Peso 1,3
O operador deve solicitar auxílio ao cliente para realizar uma orientação junto ao condutor, para que o mesmo siga corretamente o plano de viagem, seguindo pela rota correta, ou o operador deve solicitar ao cliente que o mesmo faça a alteração da rota no sistema SIL, para que coloque a rota que o condutor está realizando e assim não gere mais o alerta de desvio para nós.
### O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro? `peso=1.3`

Essa informação é crucial, principalmente quando o operador não conseguiu contato com o condutor, é importante enfatizar para o cliente que está tratando essa situação como uma suspeita de sinistro, já que não temos informação do que pode estar acontecendo.  E essa informação acaba mostrando para o cliente que se trata de uma situação de risco e deixa ele em alerta e disposto a nos auxiliar, na tentativa de contato com o condutor.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## PONTO DE APOIO – DISTRIBUIÇÃO, RASTREAMENTO, UTI E FÊNIX

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.

### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao atendente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala.
### O operador informou claramente o motivo do contato? `peso=1.2`

O operador precisa informar ao atendente o motivo pelo qual está entrando em contato, nesse caso, informar que estamos com um veículo parado naquele local, ou ali próximo, que não conseguimos contato com o condutor para confirmar uma informação da sua viagem e que gostaríamos que ele nos auxiliasse para localizar esse veículo.
O operador informou os dados e as características do veículo? (cor, placa, modelo) Peso 1,95
O operador precisa informar ao atendente os dados e características do veículo, informando a placa, marca e cor do cavalo mecânico, pode também informar a placa da carreta, mas não é obrigatório.
O operador passou detalhes da última posição do veículo? (Referência dentro do posto) Peso 1,6
O operador deve informar ao atendente uma localização aproximada da última posição do veículo. Se ele está parado próximo as bombas de combustível, se está no pátio próximo a algo, como árvore, oficina, restaurante. Uma informação que ajude e facilite para encontrar o veículo no local.
### O operador solicitou que o atendente verificasse se o conjunto (cavalo/carreta) estava no local sem violações? `peso=1.6`

O operador precisa solicitar ao atendente, que caso localize o veículo no local, se ele pode averiguar se o veículo possui alguma violação, se está com a carreta engatada, baú lacrado, tudo certo com o veículo.
### O operador orientou o atendente a chamar o motorista? `peso=1.6`

O operador também precisa pedir ao atendente que caso localize o veículo e o condutor esteja próximo, verifique se o condutor pode ir até o telefone do local, para que quando o operador retornar à ligação, possa falar com esse condutor e confirmar a situação.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “obrigada igualmente”. Não tem problema desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
Evitou silêncios prolongados (mais de 45 segundos sem interação) Peso 0,15
O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## ACIONAMENTO POLICIAL – DISTRIBUIÇÃO, RASTREAMENTO, UTI, FÊNIX E BAS

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao policial seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala.


### O operador passou detalhes do evento que indicam a suspeita? `peso=1.3`

O operador precisa informar ao policial o que está acontecendo, em casos de suspeita, informar os alertas gerados e se houve algum contato com o condutor ou cliente, e em casos de acidente ou roubo confirmado, passar as informações que temos até o momento, de como aconteceu, se temos contato com o condutor, se tem alguém ferido, se os meliantes ainda estão no local, etc.
O operador informou os dados e as características do conjunto e do motorista? (cavalo, carreta, cor, modelo) Peso 1,35
O operador precisa informar ao policial os dados e características do veículo, informando a placa, marca e cor do cavalo mecânico, pode também informar a placa da carreta, marca e cor, informar nome completo e CPF do condutor.
O operador passou detalhes do local da ocorrência? (Rodovia, Referência, KM) Peso 1,3
O operador precisa informar ao policial a rodovia onde consta o último posicionamento do veículo, o km da rodovia, cidade, estado, algum ponto de referência próximo ou caso esteja parado em algum lugar, informar o nome do estabelecimento.
### O operador solicitou deslocamento e/ou reporte da ocorrência para patrulhamento? `peso=1.5`

O operador precisa ver se é possível uma viatura se deslocar até o local para averiguar a situação e caso não seja possível, solicitar então, que repasse a informação para as demais viaturas.
### O operador deixou telefone de contato para retorno? `peso=1.3`

O operador precisa questionar ao policial, se ele pode deixar o telefone de contato caso tenham alguma informação para nos passar. Se o policial aceitar, o operador deve informar o 0800 727 6101 opção 2, base de sinistro. Caso o policial informe que não precisa do número, o operador não deve perder ponto nesse critério, pois não é culpa do operador se o policial não quiser pegar a informação.
### O operador utilizou o alfabeto fonético ao passar informações? `peso=1.2`

O operador ao informar a placa do cavalo e carreta, precisa informar ao policial as letras e números da placa através do alfabeto fonético. A = Alfa, B = Bravo, C=Charlie, D = Delta, E = Eco, F = Fox, G = Golf, H = Hotel, I = Índia, J = Juliett, K = Kilo, L = Lima, M = Mike, N = November, O = Oscar, P = Papa, Q = Quebec, R = Romeu, S = Sierra, T = Tango, U = Uniforme, V = Victor, W = Whiskey, X = Xingu, Y = Yankee e Z = Zulu. 1 = Primeiro, 2 = Segundo, 3 = Terceiro, 4 = Quarto, 5 = Quinto, 6 = Sexto, 7 = Sétimo, 8 = Oitavo, 9 = Nono e 0 = Negativo. Geralmente quando são dois números iguais, é usado o número no fonético acompanhado de “dobrado”.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “obrigada igualmente”. Não tem problema desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.

### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o policial. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa? `peso=0.2`

Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.3`

Assim que o operador realiza a despedida padrão e o policial também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.