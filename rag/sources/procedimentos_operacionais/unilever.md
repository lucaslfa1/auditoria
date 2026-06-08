---
setor: logistica_unilever
alertas_cobertos:
  - devolucao
  - cabinets
  - atuacao_tratativa
  - distribuicao
  - loss_tree
versao: 1.0
ultima_revisao: 2026-04-16
fonte_original: docs/procedimentos_operacionais/Ajustes IA - *.docx
---

# POP — Setor Logística Unilever

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.

Particularidades da auditoria Unilever:
Unilever > 2 ligações efetuadas > Alertas Atuação tratativa, Devolução, Distribuição, Cabinets e Loss Tree.
## DEVOLUÇÃO – LIGAÇÃO CLIENTE – UNILEVER

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### Informou que a devolução foi confirmada e qual o próximo passo? `peso=0.76`

O operador precisa informar o motivo da devolução, ou que a nota já foi assinada pelo cliente e verificar com o vendedor se vai seguir mesmo com a devolução ou se o vendedor vai tentar reverter.
### Informou o nome do cliente corretamente? `peso=1.6`

O operador precisa falar para o vendedor, qual é o nome do cliente.
### Informou o endereço correto do cliente? `peso=1.6`

O operador precisa falar para o vendedor, qual é o endereço do cliente, informando o nome da rua/avenida, número, bairro e cidade.
### Informou o código do cliente? `peso=1.6`

O operador precisa falar para o vendedor, qual é o código desse cliente, informando numerais.
### Confirmou a quantidade de caixas a serem devolvidas? `peso=0.81`

O operador precisa falar para o vendedor, qual é o número de caixas ou unidades a serem devolvidas, as vezes utilizam a palavra “volumetria”, também está correto.
### Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? `peso=1.58`

O operador precisa informar ao cliente se será enviado um e-mail, ou se ele precisa abrir o template no whatsapp pra ter acesso às informações.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.2`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O operador realizou a qualificação do atendimento corretamente? `peso=0.3`

O operador precisa qualificar a ligação dentro da plataforma de telefonia de forma correta, afim de facilitar a busca pelas ligações sobre devolução para ser auditada, pois essas ligações são localizadas através da qualificação, ou seja, se não estiver qualificada ou qualificada de forma errada, gera um retrabalho para o auditor, que precisa ouvir cada ligação para identificar do que se trata.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.



## CABINETS – LIGAÇÃO CLIENTE – UNILEVER

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### Informou que irá comunicar um insucesso? `peso=1.57`

O operador deve informar que está ligando devido a um insucesso.
### Informou o nome do cliente corretamente? `peso=1.6`

O operador precisa falar para o vendedor, qual é o nome do cliente.
### Informou o endereço correto do cliente? `peso=1.6`

O operador precisa falar para o vendedor, qual é o endereço do cliente, informando o nome da rua/avenida, número, bairro e cidade.
### Informou o código do cliente? `peso=1.6`

O operador precisa falar para o vendedor, qual é o código desse cliente, informando numerais.
### Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? `peso=1.58`

O operador precisa informar ao cliente se será enviado um e-mail, ou se ele precisa abrir o template no whatsapp pra ter acesso às informações.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.2`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O operador realizou a qualificação do atendimento corretamente? `peso=0.3`

O operador precisa qualificar a ligação dentro da plataforma de telefonia de forma correta, afim de facilitar a busca pelas ligações sobre devolução para ser auditada, pois essas ligações são localizadas através da qualificação, ou seja, se não estiver qualificada ou qualificada de forma errada, gera um retrabalho para o auditor, que precisa ouvir cada ligação para identificar do que se trata.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## ATUAÇÃO TRATATIVA – LIGAÇÃO CLIENTE – UNILEVER

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### Informou o motivo do contato? `peso=1.32`

O operador precisa informar ao vendedor que está entrando em contato sobre uma possível devolução e verificar se ele pode auxiliar.
### Informou o nome do cliente corretamente? `peso=1.0`

O operador precisa falar para o vendedor, qual é o nome do cliente.
### Informou o endereço correto do cliente? `peso=1.0`

O operador precisa falar para o vendedor, qual é o endereço do cliente, informando o nome da rua/avenida, número, bairro e cidade.
### Informou o código do cliente? `peso=0.85`

O operador precisa falar para o vendedor, qual é o código desse cliente, informando numerais.
### Informou o motivo da devolução? `peso=1.0`

O operador precisa informar que a devolução pode ocorrer devido a excesso de veículos, pedido não solicitado, falta de espaço, cliente fechado, etc. Precisa ter alguma informação sobre o que a frota passou para a operação do porque não conseguiram realizar a entrega.
### Informou a quantidade de caixas? `peso=1.0`

O operador precisa falar para o vendedor, qual é o número de caixas ou unidades que podem ser devolvidas, as vezes utilizam a palavra “volumetria”, também está correto.
### Informou o tempo de espera? `peso=1.0`

O operador precisa informar o horário que a frota chegou ao cliente e que horas o tempo de esperar vai expirar, ou se já expirou.
### Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? `peso=0.78`

O operador precisa informar ao cliente se será enviado um e-mail, ou se ele precisa abrir o template no whatsapp pra ter acesso às informações.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.2`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O operador realizou a qualificação do atendimento corretamente? `peso=0.3`

O operador precisa qualificar a ligação dentro da plataforma de telefonia de forma correta, afim de facilitar a busca pelas ligações sobre devolução para ser auditada, pois essas ligações são localizadas através da qualificação, ou seja, se não estiver qualificada ou qualificada de forma errada, gera um retrabalho para o auditor, que precisa ouvir cada ligação para identificar do que se trata.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## DISTRIBUIÇÃO – LIGAÇÃO CLIENTE – UNILEVER

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.


### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### Informou o motivo do contato? `peso=1.35`

O operador precisa informar ao vendedor que está entrando em contato sobre uma possível devolução e verificar se ele pode auxiliar.
### Informou a Placa do veículo? `peso=1.32`

O operador precisa informar ao vendedor qual a placa do veículo/frota.
### Informou o nome do cliente corretamente? `peso=1.32`

O operador precisa falar para o vendedor, qual é o nome do cliente.
### Informou o endereço correto do cliente? `peso=1.32`

O operador precisa falar para o vendedor, qual é o endereço do cliente, informando o nome da rua/avenida, número, bairro e cidade.
### Informou a quantidade de caixas? `peso=1.32`

O operador precisa falar para o vendedor, qual é o número de caixas ou unidades, as vezes utilizam a palavra “volumetria”, também está correto.
### Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? `peso=1.32`

O operador precisa informar ao cliente se será enviado um e-mail, ou se ele precisa abrir o template no whatsapp pra ter acesso às informações.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.


### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.2`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O operador realizou a qualificação do atendimento corretamente? `peso=0.3`

O operador precisa qualificar a ligação dentro da plataforma de telefonia de forma correta, afim de facilitar a busca pelas ligações sobre devolução para ser auditada, pois essas ligações são localizadas através da qualificação, ou seja, se não estiver qualificada ou qualificada de forma errada, gera um retrabalho para o auditor, que precisa ouvir cada ligação para identificar do que se trata.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

## LOSS TREE – LIGAÇÃO CLIENTE – UNILEVER

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### Confirmou com quem está falando? `peso=0.4`

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.
### Informou o motivo do contato? `peso=1.59`

O operador precisa informar ao vendedor que está entrando em contato sobre uma devolução que já aconteceu.
### Informou o nome do cliente? `peso=1.59`

O operador precisa falar para o vendedor, qual é o nome do cliente.
### Informou a data que ocorreu a devolução? `peso=1.59`

O operador precisa informar o dia e o mês que ocorreu a devolução.
### Confirmou o motivo que gerou o pedido não solicitado? `peso=1.59`

O operador precisa informar ao vendedor o motivo pelo qual houve a devolução.
### Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? `peso=1.59`

O operador precisa informar ao cliente se será enviado um e-mail, ou se ele precisa abrir o template no whatsapp pra ter acesso às informações.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 45 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 45 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 45 segundos e o operador não deu nenhum retorno, o critério é despontuado.


### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.2`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O operador realizou a qualificação do atendimento corretamente? `peso=0.3`

O operador precisa qualificar a ligação dentro da plataforma de telefonia de forma correta, afim de facilitar a busca pelas ligações sobre devolução para ser auditada, pois essas ligações são localizadas através da qualificação, ou seja, se não estiver qualificada ou qualificada de forma errada, gera um retrabalho para o auditor, que precisa ouvir cada ligação para identificar do que se trata.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.








