---
setor: cadastro
alertas_cobertos:
  - antecedentes_receptivo
versao: 1.0
ultima_revisao: 2026-04-16
fonte_original: docs/procedimentos_operacionais/Ajustes IA - *.docx
---

# POP — Setor Cadastro (Antecedentes)

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.

Particularidades da auditoria do Risco:
Cadastro > 2 ligações receptivas > Alerta Antecedentes.
Evitar ligações onde a pessoa já saiba quais os documentos que precisa enviar, ou que já saiba do processo. Precisa ser ligações onde a pessoa não tenha conhecimento do processo, para o operador pode falar de onde é, o ano, quais documentos são necessários.
Evitar ligações onde a pessoa quer saber de retorno sobre a documentação enviada, se já foi analisada e como ficou.
Evitar ligações que a pessoa só quer saber para qual e-mail precisa enviar as documentações solicitadas.
## CADASTRO – ANTECEDENTES

### O operador se identificou informando saudação, nome, setor e empresa? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois.
### O operador solicitou CPF/Placa para iniciar o atendimento? `peso=1.6`

O operador precisa solicitar o CPF do profissional ou a placa do veículo, para poder consultar o cadastro e verificar o que está sendo solicitado.
### O operador enfatizou sobre bloqueio/cadastro negativado? `peso=1.7`

O operador não pode informar que o cadastro foi reprovado, ou está bloqueado, que não pode realizar carregamentos, ou qualquer tipo de informação que de a entender que estamos proibindo o motorista de trabalhar. Pode apenas informar que a Opentech não proíbe ninguém de trabalhar, apenas que realizamos a análise dos documentos e enviamos essa análise para o cliente, e quem decide se o condutor vai carregar ou não, é o próprio cliente. Caso o operador informe que o cadastro está bloqueado, reprovado, condutor não pode carregar, a auditoria deve ser zerada, pois é considerado uma falha crítica, e ao passar esse tipo de informação ao condutor, estamos sujeitos a receber um processo judicial por parte do motorista.
### O operador informou se o cliente possui inquérito/processo/apontamento? `peso=1.7`

O operador precisa informar que foi localizado um processo, inquérito, carta precatória, certidão de objeto e pé, certidão de homonímia ou apontamento no nome do motorista ou proprietário do veículo. Ou qualquer outra coisa que seja relacionada a antecedentes criminais. Importante que o operador informe também de qual ano seria esse documento.
### O operador informou qual o estado/justiça federal? `peso=1.7`

O operador precisa informar que esse processo, inquérito, carta precatória, certidão de objeto e pé, certidão de homonímia ou apontamento, é referente a alguma comarca/munícipio, citando qual é a cidade ou estado, ou que esse documento é da justiça federal.

### O operador informou qual documento é necessário? `peso=1.65`

O operador precisa informar qual ou quais documentos são necessários para regularizar o cadastro do profissional ou do proprietário. Geralmente são solicitados a cópia do processo, cópia da denúncia, cópia da sentença, carta de recomendação de trabalho, inquérito, certidão de objeto e pé, certidão de homonímia, carta precatória, ou qualquer outro documento relacionado a antecedentes criminais.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.
### Utilizou a função mudo corretamente para evitar ruídos externos? `peso=0.3`

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.
### Evitou silêncios prolongados (mais de 60 segundos sem interação)? `peso=0.15`

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 60 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 60 segundos e o operador não deu nenhum retorno, o critério é despontuado.
### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? `peso=0.2`

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.
### O operador realizou a qualificação do atendimento corretamente? `peso=0.3`

O operador precisa qualificar a ligação dentro da plataforma de telefonia de forma correta, afim de facilitar a busca pelas ligações sobre antecedentes para ser auditada, pois essas ligações são localizadas através da qualificação, ou seja, se não estiver qualificada ou qualificada de forma errada, gera um retrabalho para o auditor, que precisa ouvir cada ligação para identificar do que se trata.
### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? `peso=0.1`

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.

