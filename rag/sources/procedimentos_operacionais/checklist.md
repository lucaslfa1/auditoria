---
setor: checklist
alertas_cobertos:
  - processo_checklist_whatsapp
versao: 1.0
ultima_revisao: 2026-04-16
fonte_original: docs/procedimentos_operacionais/Ajustes IA - *.docx
---

# POP — Setor Checklist (WhatsApp)

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.

Particularidades da auditoria do Risco:
Checklist > 2 WhatsApp recebidos > Apenas testes que entram em contato no horário programado.
Evitar mensagens onde não tem agendamento, entrou em contato muito antes do horário agendado.
## CHECKLIST – PROCESSO CHECKLIST – WHATSAPP

### O operador se identificou informando saudação? `peso=0.3`

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Não precisa informar nome, setor ou empresa, já que se trata de um atendimento via WhatApp, onde o contato já cai direto para o operador específico do setor de checklist, por isso não precisa dessas identificações, apenas a saudação.
### Enviou o auto texto perguntando qual o tipo de veículo? `peso=0.5`

Precisa enviar o seguinte texto pronto para identificar qual o tipo de veículo: "Qual o tipo do veículo? 1 - Carreta: Baú 2 - Carreta: Graneleiro - Saider - Contêiner 3 - Toco-Truck: Baú 4 - Toco-Truck: Graneleiro - Saider - Contêiner 5 - Outro: Nos informe o tipo"
### Seguiu corretamente o fluxo do checklist conforme a solicitação inicial? `peso=1.0`

Operador seguiu a conversa informando quais os procedimentos devem ser realizados no veículo para efetuar corretamente o teste, de acordo com o tipo do veículo informado. Não mudando o assunto para coisas que fogem dos procedimentos de checklist.
### Realizou um atendimento cordial, utilizando linguagem apropriada? `peso=0.4`

O operador precisa enviar mensagens respeitosas e profissionais, utilizando linguagem apropriada, sem palavrões ou mensagens ofensivas. Pedindo por favor, por gentileza, agradecendo quando necessário.
### Informou o status final do checklist (aprovado ou reprovado)? `peso=1.3`

Após pedir para o condutor realizar todos os testes no veículo, o operador deve informar se o checklist foi Aprovado ou Reprovado.
### Se reprovado, informou corretamente o motivo da reprovação? `peso=1.3`

Caso o operador informe que o checklist ficou reprovado, ele precisa informar o motivo pelo qual foi reprovado, se foi algum sensor que não gerou, sinal do veículo não está espelhado, etc.
### Anexou imagens dos testes no SIL, correspondentes ao veículo e tecnologia analisada? `peso=2.0`

O operador precisa anexar dentro do sistema SIL imagens ou PDF da tecnologia, comprovando que os testes foram feitos, mostrando que os sensores geraram ou não. Essas imagens precisam constar também a placa do veículo ou número do rastreador, para poder comparar se aquela imagem ou PDF pertencem mesmo ao veículo que foi testado.

### A informação passada no atendimento corresponde ao que foi registrado no SIL? `peso=2.0`

O operador precisa registrar no sistema SIL a mesma informação que repassou no WhatsApp ao condutor, se o veículo ficou aprovado ou reprovado e caso reprovado, qual foi o motivo. Para que o cliente consiga realizar a consulta e acompanhar o status do veículo e nos casos de reprovação, poder realizar as devidas manutenções no veículo.
### Encerrou o checklist no SIL em até 5 minutos após informar o status final? `peso=0.3`

O operador precisa finalizar o checklist no sistema SIL em até 5 minutos após enviar no WhatsApp se o checklist foi aprovado ou reprovado.
### Realizou a despedida padrão com cordialidade? `peso=0.3`

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “agradecemos o contato”.
### Encerrou o atendimento na Huawei em até 5 minutos após informar o status final do checklist? `peso=0.3`

O operador precisa finalizar o contato no WhatsApp da telefonia com o condutor em até 5 minutos após informar o status final do checklist, para poder estar disponível para novos testes.
### Realizou a qualificação correta do atendimento? `peso=0.3`

O operador precisa qualificar a ligação dentro da plataforma de telefonia de forma correta, afim de facilitar a busca pelas mensagens sobre checklist no horário, pois essas conversas são localizadas através da qualificação, ou seja, se não estiver qualificada ou qualificada de forma errada, gera um retrabalho para o auditor, que precisa ficar olhando uma conversa por vez, até identificar uma que possa ser auditada.






