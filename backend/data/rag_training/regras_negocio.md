# Regras de Negócio

> Documento gerado automaticamente pelo DB Knowledge Agent.
> Banco: PostgreSQL (local) | Data: 2026-04-17 11:32


Regras extraídas dos documentos oficiais em `instrucoes/` e POPs curados em `rag/sources/procedimentos_operacionais/`.


## Manual Técnico de Qualidade

# OPENTECH — Auditoria de Qualidade

**Processo da Auditoria de Qualidade**

| Campo | Valor |
|-------|-------|
| Revisão | 01 |
| Data Revisão | 02/03/2026 |
| Confidencialidade | INTERNO |

---

## Cronograma de Auditorias

| Semana | Atividade |
|--------|-----------|
| 1ª semana | Envio da listagem via e-mail para os gestores |
| 1ª a 3ª semana | Período para realizar as auditorias |
| 4ª semana | Envio das auditorias aos gestores para realizarem possíveis retificações |
| 1ª semana do mês seguinte | Revisão das auditorias faltantes e das retificações. Relatórios e levantamentos de dados para envio à coordenação e gestores. Envio do fechamento para o setor de Planejamento até o 5º dia útil |

---

## 1. Ementa da Qualidade

São realizadas auditorias mensais de ligações, com a finalidade de identificar falhas operacionais e melhoria dos processos.

## 2. Objetivo / Competência

### 2.1 Objetivo Geral
- Ao final das auditorias são realizados relatórios mensais para avaliar o desempenho operacional geral.

### 2.2 Objetivos Específicos
- Identificar falhas operacionais
- Melhoria de desempenho operacional
- Evidenciar a qualidade do atendimento prestado ao nosso cliente

---

## 3. Setores Auditados

| Setor | Tipo de Auditoria |
|-------|------------------|
| Transferência | 2 ligações efetuadas para motorista, cliente, ponto de apoio ou polícia |
| Fênix | 2 ligações efetuadas para motorista, cliente, ponto de apoio ou polícia |
| Distribuição | 2 ligações efetuadas para motorista, cliente, ponto de apoio ou polícia |
| GRS (UTI) | 2 ligações efetuadas para motorista, cliente, ponto de apoio ou polícia |
| BAS | 2 ligações efetuadas para polícia |
| Logística | 2 ligações efetuadas para motorista ou cliente |
| Logística Unilever | 2 ligações efetuadas para vendedor |
| Logística Mondelez | 2 ligações receptivas |
| Cadastro | 2 ligações receptivas |
| Checklist | 2 atendimentos via WhatsApp |
| Célula de Atendimento | 2 atendimentos via WhatsApp |

---

## 4. Confirmação da Listagem

A primeira etapa é a confirmação da listagem de operadores, normalmente ocorre entre a primeira e segunda semana do mês.

São coletadas informações da planilha de assiduidade dos operadores:
- Nome
- Matrícula
- Turno
- Supervisão
- Operação

As informações são enviadas via e-mail para confirmação e validação de dados. Cada supervisor tem até **2 turnos** para realizar a confirmação.

---

## 5. Processo de Auditoria

Na primeira semana do mês, após a confirmação da listagem, é iniciado o processo de auditoria, onde diariamente são extraídos os relatos atualizados do BI para identificar o volume de relatos, contatos e demais informações pertinentes à auditoria.

Todas as ligações são baixadas e arquivadas na rede para que posteriormente o supervisor possa realizar a consulta. Os critérios são pontuados com **"SIM"** ou **"NÃO"** de acordo com a condução da ligação, cada critério possui um peso que totalizará a média final.

Esse processo demora em média de **2 a 3 semanas** para ser finalizado.

---

## 6. Retificações

Após finalizar todas as auditorias, as informações são enviadas para a planilha de consulta do supervisor, para que ele possa visualizar as notas e solicitar retificação caso discorde de algum item.

- Normalmente ocorre na **última semana do mês**
- Envio de e-mail individual para o supervisor de cada setor
- Cada escala tem **2 turnos** para solicitar retificação via e-mail

---

## 7. Fechamento de Auditorias

O fechamento com as notas finais dos operadores ocorre após o término das retificações e é enviado ao setor do **Planejamento até o 5º dia útil** do mês para a confecção do quartil.

---

## 8. Indicadores da Qualidade

Após o fechamento final, são realizados levantamentos dos indicadores para identificar a performance dos operadores nas auditorias. Através desses levantamentos é identificado os pontos a serem melhorados.


---

## Procedimento de Automação

# Procedimento de Extração e Automação de Ligações

Este documento descreve o fluxo de trabalho desde a coleta dos áudios no sistema de telefonia até o processamento automático pelo sistema de auditoria com Inteligência Artificial.

## 1. Coleta de Dados (Sistema de Telefonia)

A extração das gravações das ligações é feita a partir do painel de controle do sistema de telefonia (ex: Huawei / Weon). O processo requer o preenchimento correto dos filtros na tela **"Contato"** para isolar as amostras a serem auditadas.

Existem duas formas principais de realizar os filtros de busca:

### Busca por Número (Telefone Alvo)
Utilizado para rastrear ocorrências vinculadas a um número específico (ex: placa do veículo, número do motorista).
*   **Período:** Selecionar o intervalo de tempo desejado (ex: `1 dia`).
*   **Número Manipulado:** Inserir o número de telefone a ser investigado.
*   **Ação:** Clicar em **Pesquisar**.

### Busca Avançada por Motivo / Atendimento
Utilizado para amostragens diárias baseadas no tipo de evento logístico e no operador.
*   **Período:** Selecionar `1 dia` (ou outro intervalo pertinente).
*   **Tipo de Chamada:** Selecionar o formato (ex: Receptivo, Ativo).
*   **Tipo de Mídia:** Geralmente "Voz".
*   **Definir o Motivo da Chamada:** Filtrar pela classificação dada na URA ou pelo operador original (ex: Desvio de Rota, Parada Indevida).
*   **ID do Funcionário:** Inserir a matrícula/ID do operador para auditar chamadas específicas de um colaborador (Cruzamento com as matrículas da planilha `01 - LISTAGEM.xlsx`).
*   **Ação:** Clicar em **Pesquisar**.

### Exportação dos Áudios
Após a pesquisa, selecione as ligações listadas e realize o download dos arquivos de áudio em lote.

---

## 2. Organização dos Arquivos Locais

Para que o script de automação possa classificar corretamente o contexto da auditoria (Setor e Motivo), os áudios extraídos devem ser renomeados e colocados nas pastas corretas dentro do diretório `Ligações/` na raiz do projeto.

### Estrutura de Pastas Esperada
Crie subpastas no diretório `Ligações/` seguindo as categorias de negócio, por exemplo:
*   `Ligações/CADASTRO/`
*   `Ligações/LOGÍSTICA/`
*   `Ligações/MONDELEZ/`
*   `Ligações/UNILEVER/`

### Convenção de Nomes dos Arquivos
O nome do arquivo de áudio deve conter palavras-chave para que o sistema infira automaticamente o "Alerta/Critério" (conforme definido no script de importação).
Exemplos de nomenclaturas de arquivos aceitas:
*   `temperatura_motorista_123.wav` (Infera alerta 4.4.5)
*   `atraso_cliente_abc.mp3` (Infera alerta 4.4.8)
*   `antecedente_jose.ogg` (Infera alerta 4.2.1)

---

## 3. Importação para o Banco de Dados

Com os áudios devidamente organizados, o processo de leitura e indexação no banco de dados (PostgreSQL) é feito através de um script automatizado.

Abra o terminal (PowerShell ou CMD) na raiz do projeto e execute:
```powershell
python backend/scripts/importar_ligacoes_auditadas.py
```
*(Se estiver utilizando um ambiente virtual, certifique-se de executar `backend/.venv/Scripts/python.exe`)*

### O que o script faz:
1. Varre todas as pastas e arquivos dentro do diretório `Ligações/`.
2. Infere o **Grupo/Setor** pelo nome da pasta (ex: LOGÍSTICA).
3. Infere o **Alerta de Referência** através de palavras-chave no nome do arquivo (ex: "atraso", "desvio", "temperatura").
4. Calcula o Hash SHA-256 do arquivo para evitar duplicações futuras.
5. Salva todas as referências no banco de dados (tabela `ligacoes_auditadas`).

---

## 4. Auditoria via Sistema (Inteligência Artificial)

Uma vez importadas para o banco de dados, as ligações estão prontas para aparecerem na interface web (Dashboard).
A partir desse ponto, o Backend processara as ligacoes localizadas utilizando o provedor de IA configurado para transcrever o audio, julgar os criterios (baseado nos prompts localizados em `audit-prompt/`) e calcular as penalidades (deflatores) definidos pelas planilhas gerenciais.


---

## Dicionário Logístico

# 📘 DICIONÁRIO COMPLETO DE TERMOS LOGÍSTICOS (A-Z)

Este documento serve como referência técnica para auditoria de operações logísticas (Mondelez, Unilever, Logística Geral, etc.).

---

### **A**
*   **ABC (Classificação):** Método de categorização de estoque baseado na importância (A: alta, B: média, C: baixa), seguindo o Princípio de Pareto (80/20).
*   **Acuracidade:** Grau de precisão entre o estoque físico e o registrado no sistema.
*   **Ad Valorem:** Taxa de seguro cobrada sobre o valor da mercadoria constante na Nota Fiscal.
*   **Aduana:** Repartição governamental (alfândega) responsável pela fiscalização de entrada e saída de mercadorias do país.
*   **ASN (Advanced Shipping Notice):** Notificação antecipada de envio enviada pelo fornecedor ao cliente.

### **B**
*   **Backhaul:** Viagem de retorno de um veículo com carga, evitando o deslocamento vazio e otimizando custos.
*   **Backlog:** Acúmulo de pedidos pendentes ou tarefas não processadas.
*   **Batch Picking:** Separação de pedidos por lotes, onde vários pedidos são coletados simultaneamente.
*   **Blocagem (Block Stacking):** Empilhamento de paletes diretamente uns sobre os outros no chão.

### **C**
*   **CD (Centro de Distribuição):** Unidade estratégica para armazenagem e expedição de produtos para diversos destinos.
*   **CIF (Cost, Insurance and Freight):** Modalidade de frete onde o fornecedor é responsável pelos custos e riscos até a entrega.
*   **Cross-docking:** Sistema de distribuição onde a mercadoria recebida é redirecionada para o transporte de saída com o mínimo tempo de armazenagem.
*   **Cubagem:** Relação entre o peso e o volume ocupado pela carga, usada para calcular o frete.

### **D**
*   **DACTE:** Documento Auxiliar do Conhecimento de Transporte Eletrônico.
*   **Dark Store:** CD fechado ao público, focado exclusivamente no e-commerce.
*   **Desova:** Ato de retirar a carga de dentro de um container.
*   **Dropshipping:** Modelo de venda onde o varejista não mantém estoque, enviando o pedido diretamente do fornecedor para o cliente final.

### **E**
*   **EDI (Electronic Data Interchange):** Troca eletrônica de dados padronizados entre sistemas de diferentes empresas.
*   **ERP (Enterprise Resource Planning):** Sistema de gestão integrada que conecta todos os departamentos de uma empresa.
*   **Estoque de Segurança:** Quantidade mínima mantida para evitar rupturas em caso de variações na demanda ou atrasos.

### **F**
*   **FEFO (First Expired, First Out):** Produto com data de validade mais próxima é o primeiro a sair (PVPS).
*   **FIFO (First In, First Out):** O primeiro produto a entrar no estoque deve ser o primeiro a sair (PEPS).
*   **First Mile:** Primeira etapa do transporte, geralmente da fábrica para o CD.
*   **Fulfillment:** Conjunto de operações que envolvem desde o recebimento do pedido até a entrega final.

### **G**
*   **Gargalo:** Ponto de restrição em um processo que limita a capacidade de toda a cadeia.
*   **Gestão de Pátio (YMS):** Controle do fluxo de veículos e cargas dentro de um CD ou fábrica.
*   **Giro de Estoque:** Indicador que mede quantas vezes o estoque foi renovado em um período.
*   **GRIS:** Taxa de Gerenciamento de Risco (prevenção de roubos e sinistros).

### **H**
*   **Handling:** Manuseio físico das mercadorias durante a armazenagem ou transporte.
*   **Hub:** Ponto central de conexão em uma rede logística.

### **I**
*   **Inbound:** Logística de entrada (suprimentos, recebimento).
*   **Incoterms:** Termos internacionais de comércio (FOB, CIF, EXW, etc.).
*   **Intralogística:** Gestão dos fluxos dentro de um armazém ou planta industrial.

### **J**
*   **Just-in-Time (JIT):** Filosofia de entregar o produto exatamente no momento necessário, reduzindo estoques ao mínimo.

### **K**
*   **Kitting:** Processo de reunir itens individuais para formar um "kit".
*   **KPI (Key Performance Indicator):** Indicadores-chave de desempenho.

### **L**
*   **Last Mile:** Etapa final da entrega do produto ao consumidor final.
*   **Lead Time:** Tempo total decorrido desde o pedido até a entrega efetiva.
*   **Logística Reversa:** Processo de retorno de produtos ou embalagens do consumidor para a origem.
*   **LTL (Less Than Truckload):** Carga fracionada (não ocupa todo o caminhão).

### **M**
*   **MDF-e:** Manifesto Eletrônico de Documentos Fiscais.
*   **Middle Mile:** Etapa intermediária do transporte (entre CDs regionais).
*   **Milk Run:** Coletas programadas em diversos fornecedores com um único veículo.

### **O**
*   **OTIF (On-Time In-Full):** Mede se o pedido foi entregue no prazo e com a quantidade/qualidade correta.
*   **Outbound:** Logística de saída (distribuição para o mercado).

### **P**
*   **Packing:** Processo de embalagem e proteção.
*   **Picking:** Processo de separação e coleta de itens para atender a um pedido.
*   **Paletização:** Agrupamento de mercadorias sobre paletes.

### **R**
*   **RFID:** Identificação por radiofrequência para rastreamento automático.
*   **Roteirização:** Planejamento das melhores rotas de entrega.

### **S**
*   **SKU (Stock Keeping Unit):** Código único que identifica cada item no estoque.
*   **Supply Chain Management (SCM):** Gestão integral da cadeia de suprimentos.

### **T**
*   **TMS (Transportation Management System):** Software para gestão de transportes.
*   **Transbordo:** Transferência de carga de um veículo para outro durante o trajeto.

### **U**
*   **Unitização:** Agrupamento de volumes menores em uma única unidade de carga.

### **W**
*   **WMS (Warehouse Management System):** Software para gestão de armezéns.

---
*Documento gerado automaticamente para suporte à Auditoria NSTECH.*


---

## Instruções de Padrão de Auditoria

## Critérios de Auditoria da Opentech para IA Auditora

### 1. Confirmação da Listagem de Operadores

*   **Quando ocorre:** Primeira semana de cada mês.
*   **Objetivo:** Verificar os profissionais escalados para a auditoria mensal.
*   **Responsabilidade do Gestor:**
    *   **Inclusão de Novos Colaboradores:** Inserir os dados dos novos colaboradores na Planilha de Assiduidade.
    *   **Verificação de Dados:** Garantir que os dados de cada colaborador estejam completos e corretos na planilha.
    *   **Atualização Contínua:** Manter a planilha sempre atualizada.
*   **Prazo para Confirmação:** 2 turnos.
*   **Consequências do Não Cumprimento do Prazo:** Falha comunicada ao planejamento. Solicitação de reauditoria posterior sem confirmação da listagem não será aceita.
*   **Origem da Listagem:** Planilha de Assiduidade enviada por e-mail aos gestores.
*   **O Que Deve Ser Verificado:**
    *   Nome do operador
    *   Matrícula
    *   ID Weon
    *   Turno/Operação (ênfase nas áreas UTI, UTI RJ e BAS)
    *   Supervisão
*   **Informações Adicionais:** Operadores de férias, afastados ou em funções não auditáveis devem ser sinalizados.
*   **Impacto da Não Confirmação:** Exclusão do operador da auditoria, impactando negativamente sua nota e posicionamento no quartil.

### 2. Processo de Auditoria

*   **Requisitos Necessários para Auditoria:**
    *   O operador deve ter trabalhado pelo menos 7 dias no mês.
    *   Deve ter, no mínimo, 7 ou mais ligações auditáveis no período.
*   **Ferramenta Utilizada:** Arquivo Excel com diversas abas:
    *   Aba onde é realizada as auditorias (matrícula, tipo de alerta, ligação, etc.)
    *   Aba com os dados arquivados de cada auditoria.
    *   Aba com os critérios e pesos.
    *   Aba com os dados dos operadores.
*   **Relatos:** Cruciais para auditorias nos setores de Transferência, Distribuição, UTI e BAS. Devem ser detalhados e completos, incluindo:
    *   Nome da pessoa contatada.
    *   Número de telefone completo (com DDD).
    *   Confirmação de senha ou dados pessoais.
    *   Detalhes relevantes sobre o alerta.
*   **Período da Auditoria:** Começa na segunda semana do mês (após a confirmação da listagem) e vai até a última semana do mês.
*   **Prazo de Entrega e Retificação:**
    *   **Finalização da Auditoria:** Até a última semana do mês.
    *   **Checagem Final:** No primeiro dia do mês seguinte.
    *   **Fechamento Final:** Nos dois primeiros dias do mês seguinte.
*   **Atenção:** O número de telefone é essencial para localizar a gravação da chamada.

### 3. Alertas Auditados por Setor

*   **3.1. Transferência / Distribuição / Fênix / BBM / UTI:**
    *   São auditadas 2 ligações efetuadas, incluindo alertas como:
        *   Alertas prioritários (ex. Botão de Pânico, Perda de Bateria, Interferência por Jammer, Violação de Antena, Teclado Desconectado).
        *   Posição em atraso.
        *   Parada indevida.
        *   Desvio de rota.
*   **3.2. Base de Sinistros (BAS):**
    *   São auditadas 2 ligações efetuadas para a polícia, incluindo alertas como:
        *   Tratativas de ocorrência da BAS
        *   Roubo.
        *   Acidente.
        *   Alertas prioritários.
        *   Posição em atraso.
        *   Parada indevida.
        *   Desvio de rota.
*   **3.3. Cadastro:**
    *   São auditadas 2 ligações receptivas nos alertas:
        *   Antecedentes.
*   **3.4. Logística Unilever:**
    *   São auditadas 2 ligações efetuadas, com alertas relacionados a:
        *   Loss Tree.
        *   Devolução.
        *   Atuação Tratativa.
        *   Cabinets.
        *   Distribuição.
*   **3.5. Logística Opentech:**
    *   São auditadas 2 ligações efetuadas para motorista ou cliente nos alertas:
        *   Controle de temperatura;
        *   Desligamento de temperatura;
        *   Ativação de AE;
        *   Atraso na entrega;
        *   Estadia;
        *   Atraso;
        *   Parada indevida logística;
        *   Desvio de rota logística;
        *   Posição em Atraso;
        *   Taborda.
*   **3.6. Célula de Atendimento (Receptivo):**
    *   São auditados dois atendimentos de WhatsApp (1 e 2) para o alerta "CHATBOT".
*   **3.7. Checklist:**
    *   São auditados dois atendimentos de WhatsApp para o alerta "Processos Checklist".
*   **3.8. Logística Mondelez:**
    *   São auditadas 2 ligações receptivas nos alertas:
        *   Monitoramento I;
        *   Monitoramento II;
        *   Logística reversa.

### 4. Critérios de Auditoria e Peso para Cada Item

(Apresenta-se aqui um resumo. Cada critério tem um peso, uma justificativa ("Por que é importante") e um exemplo do que pode ser dito. Adaptar conforme a necessidade da IA.)

#### 4.1. Setores Transferência / Distribuição / Fênix / BBM / UTI / BAS

*   **4.1.1 Critérios de Auditoria – Alerta Prioritário no Contato com o Motorista:**
    *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,3)
    *   O operador confirmou a senha de segurança antes de prosseguir? (Peso: 2)
    *   O operador informou claramente o motivo do contato? (Peso: 1,03)
    *   O operador confirmou a localização e a condição do motorista? (Peso: 1,7)
    *   O operador identificou o motivo do alerta? (Peso: 1,92)
    *   O operador solicitou vídeo do veículo nos casos necessários? (Peso: 1,7)
    *   Realizou a despedida padrão com cordialidade? (Peso: 0,3)
    *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,3)
    *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
    *   O operador registrou corretamente o contato no sistema? (Peso: 0,2)
    *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,3)
    *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,1)
*   **4.1.2 Critério da Auditoria - Alerta Prioritário contato com Cliente:**
    *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
    *   Confirmou com quem está falando? (Peso: 0,40)
    *   O operador informou claramente o motivo do contato? (Peso: 1,20)
    *   O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro? (Peso: 2,00)
    *   O operador informou as ações adotadas até o momento? (Peso: 1,15)
    *   O operador informou corretamente o local onde gerou o alerta? (Peso: 1,80)
    *   O operador confirmou os contatos atuais do condutor? (Peso: 1,80)
    *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
    *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
    *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
    *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
    *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
    *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.3 Critério de Auditoria - Alerta de Posição em Atraso no Contato com o Motorista:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   O operador confirmou a senha de segurança antes de prosseguir? (Peso: 2)
        *   O operador informou claramente o motivo do contato? (Peso: 1,03)
        *   O operador confirmou a localização atual do motorista? (Peso: 1,22)
        *   Passou orientações para forçar posicionamento do rastreador? (Peso: 2,00)
        *   O operador procurou identificar o motivo da perda de sinal? (Peso: 1,05)
        *   O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer? (Peso: 1,05)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.4 Critérios de Auditoria – Alerta de Posição em Atraso no Contato com o Cliente:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   Confirmou com quem está falando? (Peso: 0,40)
        *   O operador informou claramente o motivo do contato? (Peso: 1,20)
        *   O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro? (Peso: 1,20)
        *   O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)? (Peso: 1,15)
        *   O operador informou corretamente o local onde perdeu a posição? (Peso: 1,10)
        *   O operador questionou se o conjunto possui equipamento de contingência? (Peso: 1,10)
        *   O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista? (Peso: 1,10)
        *   O operador confirmou os contatos atuais do condutor? (Peso: 1,10)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.5 Critérios de Auditoria – Alerta de Parada Indevida no Contato com o Motorista:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   O operador confirmou a senha de segurança antes de prosseguir? (Peso: 2)
        *   O operador informou claramente o motivo do contato? (Peso: 1,03)
        *   O operador confirmou o motivo pelo qual o motorista parou em local indevido? (Peso: 1,30)
        *   O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento? (Peso: 1,30)
        *   O operador orientou o motorista a reiniciar a viagem e seguir para um local homologado? (Peso: 1,32)
        *   O operador informou os riscos operacionais da parada indevida, incluindo problemas com seguro? (Peso: 1,40)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.6 Critério de Auditoria - Alerta Parada Indevida contato com o Cliente:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   Confirmou com quem está falando? (Peso: 0,40)
        *   O operador informou claramente o motivo do contato? (Peso: 1,20)
        *   O operador informou as ações adotadas até o momento? (Peso: 1,15)
        *   O operador informou corretamente o local da parada? (Peso: 1,40)
        *   O operador confirmou se os pontos de parada autorizada foram passados ao motorista antes do início da viagem? (Peso: 1,40)
        *   O operador informou ao cliente sobre os riscos operacionais e de seguro caso a parada indevida permaneça? (Peso: 1,40)
        *   O operador indicou medidas de segurança ao cliente? (Peso: 1,40)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.7 Critério de Auditoria – Alerta Desvio de Rota contato com o Motorista:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   O operador confirmou a senha de segurança antes de prosseguir? (Peso: 2)
        *   O operador informou claramente o motivo do contato? (Peso: 1,03)
        *   O operador confirmou o motivo do desvio de rota? (Peso: 1,05)
        *   Confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento? (Peso: 1,05)
        *   Orientou o motorista a retornar para a rota ou permanecer parado até confirmação com o cliente? (Peso: 1,05)
        *   Coletou qual itinerário o motorista está realizando? (Peso: 1,05)
        *   O operador informou os riscos operacionais e de seguro caso o motorista continue fora da rota? (Peso: 1,12)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.8 Critério de Auditoria - Alerta Desvio de Rota no Contato com o Cliente:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   Confirmou com quem está falando? (Peso: 0,40)
        *   O operador informou claramente o motivo do contato? (Peso: 1,20)
        *   O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro? (Peso: 1,30)
        *   O operador informou as ações adotadas, resumindo os contatos/tratativas realizados (com ou sem sucesso)? (Peso: 1,15)
        *   O operador informou o trajeto que o motorista está realizando e o que estava programado na rota? (Peso: 1,00)
        *   O operador questionou se o cliente tem conhecimento do motivo do desvio? O motorista informou antecipadamente? (Peso: 1,00)
        *   O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento antes da viagem? (Peso: 1,00)
        *   O operador indicou medidas de segurança ao cliente? (Peso: 1,30)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.9 Critério de Auditoria – Contato com o Ponto de Apoio:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   Confirmou com quem está falando? (Peso: 0,40)
        *   O operador informou claramente o motivo do contato? (Peso: 1,20)
        *   O operador informou os dados e as características do veículo? (Peso: 1,95)
        *   O operador passou detalhes da última posição do veículo? (Peso: 1,60)
        *   O operador solicitou que o atendente verificasse se o conjunto (cavalo/carreta) estava no local sem violações? (Peso: 1,60)
        *   O operador orientou o atendente a chamar o motorista? (Peso: 1,60)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.1.10 Critério da Auditoria – Contato com Acionamento Policial:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   Confirmou com quem está falando? (Peso: 0,40)
        *   O operador passou detalhes do evento que indicam a suspeita? (Peso: 1,30)
        *   O operador informou os dados e as características do conjunto e do motorista? (Peso: 1,35)
        *   O operador passou detalhes do local da ocorrência? (Peso: 1,30)
        *   O operador solicitou deslocamento e/ou reporte da ocorrência para patrulhamento? (Peso: 1,50)
        *   O operador deixou telefone de contato para retorno? (Peso: 1,30)
        *   O operador utilizou o alfabeto fonético ao passar informações? (Peso: 1,20)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   O operador registrou corretamente o contato no sistema? (Peso: 0,20)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)

#### 4.2 Setor Cadastro

*   **4.2.1 Critério da Auditoria – Alerta de Antecedentes no Contato Receptivo:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   O operador solicitou CPF/Placa para iniciar o atendimento? (Peso: 1,60)
        *   O operador enfatizou sobre bloqueio/cadastro negativado? (Peso: 1,70)
        *   O operador informou se o cliente possui inquérito/processo/apontamento? (Peso: 1,70)
        *   O operador informou qual o estado/justiça federal? (Peso: 1,65)
        *   O operador informou qual documento é necessário? (Peso: 1,65)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,30)
        *   O operador realizou a qualificação do atendimento corretamente (Peso: 0,25)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)

#### 4.3 Setor Logística Unilever

*   **4.3.1 Critério da Auditoria – Alerta de Devolução no Contato com Cliente:**
    *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
    *   Confirmou com quem está falando? (Peso: 0,40)
    *   Informou que a devolução foi confirmada e qual o próximo passo? (Peso: 0,76)
    *   Informou o nome do cliente corretamente? (Peso: 1,60)
    *   Informou o endereço correto do cliente? (Peso: 1,60)
    *   Informou o código do cliente? (Peso: 1,60)
    *   Confirmou a quantidade de caixas a serem devolvidas? (Peso: 0,81)
    *   Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? (Peso: 1,58)
    *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
    *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
    *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
    *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,20)
    *   O operador realizou a qualificação do atendimento corretamente (Peso: 0,30)
    *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.3.2 Critério da Auditoria – Alerta de Cabinets no Contato com Cliente:**
    *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
    *   Confirmou com quem está falando? (Peso: 0,40)
    *   Informou que irá comunicar um insucesso? (Peso: 1,57)
    *   Informou o nome do cliente corretamente? (Peso: 1,60)
    *   Informou o endereço correto do cliente? (Peso: 1,60)
    *   Informou o código do cliente? (Peso: 1,60)
    *   Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? (Peso: 1,58)
    *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
    *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
    *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
    *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,20)
    *   O operador realizou a qualificação do atendimento corretamente (Peso: 0,30)
    *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.3.3 Critério da Auditoria – Alerta de Atuação Tratativa no Contato com Cliente:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   Confirmou com quem está falando? (Peso: 0,40)
        *   Informou o motivo do contato? (Peso: 1,32)
        *   Informou o nome do cliente corretamente? (Peso: 1,00)
        *   Informou o endereço correto do cliente? (Peso: 1,00)
        *   Informou o código do cliente? (Peso: 0,85)
        *   Informou o motivo da devolução? (Peso: 1,00)
        *   Informou a quantidade de caixas? (Peso: 1,00)
        *   Informou o tempo de espera? (Peso: 1,00)
        *   Ação resultante (e-mail, ligação, mobile). Ação final ao atendimento (Peso: 0,78)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,20)
        *   O operador realizou a qualificação do atendimento corretamente (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.3.4 Critério da Auditoria – Alerta de Distribuição no Contato com Cliente:**
        *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
        *   Confirmou com quem está falando? (Peso: 0,40)
        *   Informou o motivo do contato? (Peso: 1,35)
        *   Informou a Placa do veículo? (Peso: 1,32)
        *   Informou o nome do cliente? (Peso: 1,32)
        *   Informou o endereço do cliente? (Peso: 1,32)
        *   Informou a quantidade de caixas? (Peso: 1,32)
        *   Ação resultante (e-mail, ligação, mobile) foi registrada corretamente? (Peso: 1,32)
        *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
        *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
        *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
        *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,20)
        *   O operador realizou a qualificação do atendimento corretamente (Peso: 0,30)
        *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)
*   **4.3.5 Critério da Auditoria – Alerta de Loss Tree no Contato com Cliente:**
    *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
    *   Confirmou com quem está falando? (Peso: 0,40)
    *   Informou o motivo do contato? (Peso: 1,59)
    *   Informou o nome do cliente? (Peso: 1,59)
    *   Informou a data que ocorreu a devolução? (Peso: 1,59)
    *   Confirmou o motivo que gerou o pedido não solicitado? (Peso: 1,59)
    *   Ação resultante. Registrar o retorno no relatório. (Peso: 1,59)
    *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
    *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
    *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
    *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,20)
    *   O operador realizou a qualificação do atendimento corretamente (Peso: 0,30)
    *   O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? (Peso: 0,10)

#### 4.4 Setor Logística

*   **4.4.1 Critério da Auditoria - Alerta de Estadia no Contato com Motorista:**
    *   O operador se identificou informando saudação, nome, setor e empresa? (Peso: 0,30)
    *   Confirmou com quem está falando? (Peso: 0,40)
    *   Informou o motivo do contato? (Peso: 2,00)
    *   Questionou se há previsão para descarga? (Peso: 2,00)
    *   Confirmou o tempo de espera até o momento? (Peso: 1,95)
    *   Verificou se houve alguma intercorrência no processo? (Peso: 2,00)
    *   Realizou a despedida padrão com cordialidade? (Peso: 0,30)
    *   Utilizou a função mudo corretamente para evitar ruídos externos? (Peso: 0,30)
    *   Evitou silêncios prolongados (mais de 45 segundos sem interação)? (Peso: 0,15)
    *   Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)? (Peso: 0,20)
    *   O operador realizou a qualificação do atendimento corretamente (Peso: 0,30)
    *   O volume de voz, entonação e

---

## Procedimentos Operacionais Padrão (POPs)

Fontes oficiais curadas em `rag/sources/procedimentos_operacionais/`. Cada arquivo cobre um setor ou conjunto de setores com critérios detalhados por alerta/fluxo.


### Fonte: `areas_de_risco.md`

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

---

### Fonte: `cadastro.md`

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



---

### Fonte: `checklist.md`

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








---

### Fonte: `mondelez.md`

---
setor: logistica_mondelez
alertas_cobertos:
  - monitoramento_i
  - monitoramento_ii
  - logistica_reversa
versao: 1.0
ultima_revisao: 2026-04-16
fonte_original: docs/procedimentos_operacionais/Ajustes IA - *.docx
---

# POP — Setor Logística Mondelez

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.


## MONITORAMENTO I – LIGAÇÃO RECEPTIVA – MONDELEZ

### O operador se identificou informando saudação, nome, setor e empresa?

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois. Eles sempre se apresentam como “torre de controle Mondelez”, não tem problema, pode pontuar o critério.

### Confirmou com quem está falando?

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.

### Confirmou se a pessoa é motorista ou transportadora?

O operador precisa questionar se a pessoa que está na linha é o motorista ou se ela é da transportadora.

### Solicitou o número da Nota Fiscal? (Confirmar 2x caso não localize)

O operador precisa solicitar o número da nota fiscal de origem, para conseguir abrir a ocorrência.

Confirmou o nome do cliente que está no nosso sistema? [Informe o cliente]

O operador precisa falar o nome do cliente que está no sistema, para que a pessoa que ligou, confirme se é aquele cliente mesmo.

### Confirmou o telefone do motorista?

O operador pode pedir que a pessoa informe o número de contato ou pode passar o número (completo ou só o final) que vem informado na chamada da telefonia e a pessoa confirmar se é aquele número mesmo.

### Questionou o motivo da ocorrência?

O operador precisa saber qual o motivo da ocorrência, para abrir uma nova ocorrência, podendo ser por estar aguardando descarregamento, canhoto ou conferência.

### Confirmou quanto tempo que foi finalizado a descarga?

O operador precisa questionar se a descarga já foi finalizada, caso não, em quanto tempo acha que finaliza o descarregamento.

### Informou o número da Ocorrência gerada no sistema?

O operador precisa informar para a pessoa em linha, o número da ocorrência que foi gerada no sistema.

### Solicitou que retorne o contato após 2 horas para realizar uma atualização da ocorrência?

O operador deve solicitar para que a pessoa entre em contato novamente após 2 horas, para realizar uma atualização da ocorrência no sistema.

### Realizou a despedida padrão com cordialidade?

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.

### Utilizou a função mudo corretamente para evitar ruídos externos? [avaliação-acústica]

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.

### Evitou silêncios prolongados (mais de 60 segundos sem interação)?

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 60 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 60 segundos e o operador não deu nenhum retorno, o critério é despontuado.

### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.

### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? [avaliação-acústica]

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.


## MONITORAMENTO II – LIGAÇÃO RECEPTIVA – MONDELEZ

### O operador se identificou informando saudação, nome, setor e empresa?

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois. Eles sempre se apresentam como “torre de controle Mondelez”, não tem problema, pode pontuar o critério.

### Confirmou com quem está falando?

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.

### Confirmou se a pessoa é motorista ou transportadora?

O operador precisa questionar se a pessoa que está na linha é o motorista ou se ela é da transportadora.

### Solicitou o número da Nota Fiscal? (Confirmar 2x caso não localize)

O operador precisa solicitar o número da nota fiscal de origem, para conseguir abrir a ocorrência.

Confirmou o nome do cliente que está no nosso sistema? [Informe o cliente]

O operador precisa falar o nome do cliente que está no sistema, para que a pessoa que ligou, confirme se é aquele cliente mesmo.

### Confirmou o telefone do motorista?

O operador pode pedir que a pessoa informe o número de contato ou pode passar o número (completo ou só o final) que vem informado na chamada da telefonia e a pessoa confirmar se é aquele número mesmo.

### Questionou o motivo da ocorrência?

O operador precisa saber qual o motivo da ocorrência, para abrir uma nova ocorrência, podendo ser por estar aguardando descarregamento, canhoto ou conferência.

### Questionou a data de agendamento?

O operador precisa questionar a pessoa, se ele possui data de agendamento.

### Questionou se possui notas de outros clientes?

O operador precisa perguntar se o condutor possui notas de outros clientes ainda.

### Informou o número da Ocorrência gerada no sistema?

O operador precisa informar para a pessoa em linha, o número da ocorrência que foi gerada no sistema.

### Solicitou que retorne o contato após 2 horas para realizar uma atualização da ocorrência?

O operador deve solicitar para que a pessoa entre em contato novamente após 2 horas, para realizar uma atualização da ocorrência no sistema.

### Realizou a despedida padrão com cordialidade?

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.

### Utilizou a função mudo corretamente para evitar ruídos externos? [avaliação-acústica]

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.

### Evitou silêncios prolongados (mais de 60 segundos sem interação)?

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 60 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 60 segundos e o operador não deu nenhum retorno, o critério é despontuado.

### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.

### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? [avaliação-acústica]

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.


## LOGÍSTICA REVERSA – LIGAÇÃO RECEPTIVA – MONDELEZ

### O operador se identificou informando saudação, nome, setor e empresa?

O operador precisa realizar o atendimento inicial com bom dia, boa tarde ou boa noite. Precisa informar seu nome, apenas o primeiro nome já é suficiente, não sendo necessário ser o nome completo, mas também se informar mais de um nome, não tem problema. O operador pode informar o setor ou a empresa, não sendo obrigatório informar os dois, pode ser apenas um deles ou os dois. Eles sempre se apresentam como “torre de controle Mondelez”, não tem problema, pode pontuar o critério.

### Confirmou com quem está falando?

O operador precisa perguntar ao cliente seu nome, para que possa deixar no registro, caso seja necessário realizar algum retorno mais tarde, já sabe com quem falou antes e pode falar novamente com aquela pessoa. Então o operador tem que questionar com quem ele fala, ou se ele já tiver o nome da pessoa, pode perguntar se está falando com o “fulano”. O importante é ter o nome da pessoa com quem falou.

### Confirmou se a pessoa é motorista ou transportadora?

O operador precisa questionar se a pessoa que está na linha é o motorista ou se ela é da transportadora.

### Solicitou o número da Nota Fiscal? (Confirmar 2x caso não localize)

O operador precisa solicitar o número da nota fiscal de origem, para conseguir abrir a ocorrência.

Confirmou o nome do cliente que está no nosso sistema? [Informe o cliente]

O operador precisa falar o nome do cliente que está no sistema, para que a pessoa que ligou, confirme se é aquele cliente mesmo.

### Confirmou o telefone do motorista?

O operador pode pedir que a pessoa informe o número de contato ou pode passar o número (completo ou só o final) que vem informado na chamada da telefonia e a pessoa confirmar se é aquele número mesmo.

### Questionou o motivo da ocorrência?

O operador precisa saber qual o motivo da ocorrência, para abrir uma nova ocorrência, podendo ser por estar aguardando descarregamento, canhoto ou conferência.

### Solicitou o número da NF de devolução?

O operador precisa solicitar o número da nota fiscal de devolução.

### Solicitou informação dos produtos/itens/caixas devolvidos?

O operador precisa questionar sobre os produtos, quantas unidades/caixas, qual é o produto, a gramatura, qual o problema pelo qual o cliente está devolvendo.

### Informou o número da Ocorrência gerada no sistema?

O operador precisa informar para a pessoa em linha, o número da ocorrência que foi gerada no sistema.

### Realizou a despedida padrão com cordialidade?

O operador pode realizar a despedida padrão com “tenha um bom dia, boa tarde ou boa noite”, “tenha um bom trabalho”, “bom descanso”, “bom almoço”, “obrigada igualmente”. Não tem problema responder “amém” quando os motoristas dizem Deus abençoe, ou desejar feliz natal, feliz ano novo ou feliz páscoa em datas comemorativas. Pois além de um atendimento padronizado, precisamos também ter um atendimento humanizado, então é importante responder aos clientes, quando acontecem esses tipos de felicitações ou desejos.

### Utilizou a função mudo corretamente para evitar ruídos externos? [avaliação-acústica]

O operador deve deixar o headset no mudo, quando não está em contato direto com o motorista ou cliente. Para que a ligação fique limpa de ruídos, conversas paralelas, teclas do teclado, respiração. Isso evita interferências e mantém a qualidade da chamada. Importante sempre pedir para a pessoa aguardar um momento/minuto antes de colocar no mudo, para a pessoa saber que o operador “sumiu” pois está verificando/realizando algo.

### Evitou silêncios prolongados (mais de 60 segundos sem interação)?

O operador precisa realizar o preenchimento do silêncio, não deixando a pessoa sem retorno por mais de 60 segundos, esse processo mantém o contato ativo e evita que o cliente/motorista pense que a ligação caiu. Por isso é importante avisar quando vai colocar no mudo, pedindo para a pessoa aguardar um momento e sempre lembrando de pedir para a pessoa continuar em linha, caso o operador ainda esteja verificando algo, ou esperando o sistema carregar. Passou de 60 segundos e o operador não deu nenhum retorno, o critério é despontuado.

### Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?

Assim que o operador realiza a despedida padrão e o cliente/motorista também finaliza e não há mais contato um com o outro, o operador precisa encerrar a chamada, caso não seja encerrada, a ligação continua ativa e gravando. Nesses casos, após ambos fazerem a despedida, o operador tem 10 segundos para desligar e encerrar a gravação da chamada, caso passe desse tempo o critério é despontuado.

### O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias? [avaliação-acústica]

Analisar se o tom de voz está adequado, nem muito alto, nem muito baixo, se está com um tom de voz ríspido, sendo irônico ou sarcástico, se está falando muito próximo ao microfone causando muitos ruídos por conta da respiração. Se está sabendo conduzir a ligação de maneira tranquila, não fugindo do foco inicial. Se utiliza muitas gírias repetidamente. Se está sendo respeitoso, solicito e empático.


---

### Fonte: `processo_localizacao.md`

---
setor: processo_localizacao
alertas_cobertos: []
versao: 1.0
ultima_revisao: 2026-04-16
fonte_original: Ajustes IA/PROCESSO PARA LOCALIZAR LIGAÇÕES E BAIXAR.docx
---

# POP — Processo Localização

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.

PROCESSO PARA LOCALIZAR LIGAÇÕES E BAIXAR NA PLATAFORMA HUAWEI
1 - Em todas as áreas (exceto na Mondelez) o processo inicial é o mesmo, vai ir em História (1°), depois vai ir em Contato (2°), então, vai abrir uma aba de contato, e nessa aba, vai ir na opção de Consulta de contato (3°).
.










Para aparecer todas as opções de filtro, temos que clicar na opção de Mais.







Para as áreas de Risco (Rastreamento, Distribuição, UTI e BAS) o processo de procura das ligações, é feito pelo relatório de relatos, onde lemos os relatos até encontrar um adequado para auditar, copiamos o número que foi relatado e dentro da plataforma da Huawei, colamos esse número na opção Número Manipulado (1°), depois vai colocar o dia que foi feito o relato, que é possível ver no relatório de relatos, na opção 1 dia (2°), após colocar essas duas informações, vai clicar em Pesquisar (3°), na parte debaixo vai aparecer a ligação ou as ligações realizadas/recebidas desse número, na data filtrada, daí é necessário encontrar a ligação do operador que está sendo auditado (4°), assim que localizar a ligação, vai clicar em Reproduzir (5°), vamos ouvir a ligação, preenchendo nossa planilha de auditoria com os critérios (processo que a IA já está fazendo), se der para auditar essa gravação, clicamos em Baixar (6°).











Depois que o áudio é baixado, vai pra pasta de Dowloads, onde essa ligação é recortada da pasta e vai para um SharePoint da Qualidade, onde os supervisores tem acesso, para ouvirem essas ligações. Dentro desse SharePoint tem uma pasta chamada de AUDITORIA OPERACIONAL, dentro dessa pasta, tem uma pasta para cada área (Distribuição, Fênix, GRS e Transferência), dentro dessas pastas de cada setor tem uma pasta referente ao mês auditado, dentro dessa pasta do mês vai ter outras pastas dividido por escala (Amarela, Azul, Cinza e Verde),  dentro da pasta da escala, vai ter uma pasta para cada operador auditado e dentro da pasta de cada operador, é colocado as duas ligações que foram auditadas, para que o supervisor possa ter acesso ao áudio para ouvir e poder contestar caso necessário. 
Dentro da IA, no módulo do supervisor, precisa ter o áudio da ligação, para que ele possa ouvir a ligação auditada e assim essas pastas todas no SharePoint não serão mais necessárias. 





2 - Para as áreas da Logística e Unilever o processo de procura das ligações, é feito direto pela plataforma da Huawei, na opção 1 dia (1°), vai colocar o período que quer puxar as ligações, do primeiro dia do mês, até a data que está fazendo a auditoria. Depois vai procurar pelo Nome do agente (Funcionário) ou pelo ID do funcionário (2°), na opção de Tipo de mídia (3°), vai colocar a opção de voz para ligações, se for algum operador da Logística da Operação Taborda, vai colocar a opção de Multimídia que é de WhatsApp e depois vai Pesquisar (4°).











Depois de pesquisar, na parte de baixo vai trazer todas as ligações do período filtrado referente ao operador, vai ir para o lado nas colunas, até achar a coluna de Motivo da chamada (1°), nessa coluna vai verificar as qualificações das chamadas e vai procurar por alguma ligação que tenha tido sucesso (2°), geralmente vai estar com o motivo descrito, qual foi o alerta e para quem foi a ligação (motorista ou cliente). Depois de localizar a ligação através do motivo da chamada, vai clicar em Reproduzir (3°), para ouvir a ligação e realizar a auditoria na planilha do auditor (esse processo a IA já realiza), seouvir a ligação e ver que da pra auditar, é só clicar em  Baixar (4°), caso não seja possível auditar essa ligação, precisa procurar outra.










Depois que o áudio é baixado, vai pra pasta de Dowloads, onde essa ligação é recortada da pasta e vai para um SharePoint da Qualidade, onde os supervisores tem acesso, para ouvirem essas ligações. Dentro desse SharePoint tem uma pasta chamada de AUDITORIA OPERACIONAL, dentro dessa pasta, tem uma pasta para cada área (Logística e Unilever), dentro dessas pastas de cada setor tem uma pasta referente ao mês auditado, dentro dessa pasta do mês, no caso da Logística, vai ter uma pasta para o supervisor do dia e uma para o da noite, e dentro delas, vai ter uma pasta para cada operador auditado e dentro da pasta de cada operador, é colocado as duas ligações que foram auditadas, para que o supervisor possa ter acesso ao áudio para ouvir e poder contestar caso necessário. 
Dentro da IA, no módulo do supervisor, precisa ter o áudio da ligação, para que ele possa ouvir a ligação auditada e assim essas pastas todas no SharePoint não serão mais necessárias. 




3 - Para o Cadastro o processo de procura das ligações, é feito direto pela plataforma da Huawei, na opção 1 dia (1°), vai colocar o período que quer puxar as ligações, do primeiro dia do mês, até a data que está fazendo a auditoria. Depois vai no Tipo de chamada (2°), e vai colocar a opção de Chamada recebida (no cadastro é apenas ligações receptivas), daí vai procurar pelo Nome do agente (Funcionário) ou pelo ID do funcionário (3° ou 4°) e depois vai Pesquisar (5°).















Depois de pesquisar, na parte de baixo vai trazer todas as ligações do período filtrado referente ao operador, vai ir para o lado nas colunas, até achar a coluna de Motivo da chamada (1°), nessa coluna vai verificar as qualificações das chamadas e vai procurar por alguma ligação que tenha tido sucesso (2°), no caso do cadastro deve procurar apenas por Antecedentes, pois é o único alerta auditado. Depois de localizar a ligação através do motivo da chamada, vai clicar em Reproduzir (3°), para ouvir a ligação e realizar a auditoria na planilha do auditor (esse processo a IA já realiza), se ouvir a ligação e ver que da pra auditar, é só clicar em  Baixar (4°), caso não seja possível auditar essa ligação, precisa procurar outra.











Depois que o áudio é baixado, vai pra pasta de Dowloads, onde essa ligação é recortada da pasta e vai para um SharePoint da Qualidade, onde os supervisores tem acesso, para ouvirem essas ligações. Dentro desse SharePoint tem uma pasta chamada de AUDITORIA OPERACIONAL, dentro dessa pasta, tem uma pasta para cada área (Cadastro), dentro dessa pasta de cada setor tem uma pasta referente ao mês auditado, dentro dessa pasta do mês, vai ter uma pasta para cada operador auditado e dentro da pasta de cada operador, é colocado as duas ligações que foram auditadas, para que o supervisor possa ter acesso ao áudio para ouvir e poder contestar caso necessário. 
Dentro da IA, no módulo do supervisor, precisa ter o áudio da ligação, para que ele possa ouvir a ligação auditada e assim essas pastas todas no SharePoint não serão mais necessárias. 







4 - Para a área do Receptivo o processo de procura de WhatsApp, é feito direto pela plataforma da Huawei, na opção 1 dia (1°), vai colocar o período que quer puxar as ligações, do primeiro dia do mês, até a data que está fazendo a auditoria, na opção de Tipo de mídia (2°), vai colocar a opção de Multimídia que é de WhatsApp e depois vai procurar pelo Nome do agente (Funcionário) ou pelo ID do funcionário (3°) e por último vai Pesquisar (4°).











Depois de pesquisar, na parte de baixo vai trazer todos os WhatsApps do período filtrado referente ao operador, vai ir para o lado nas colunas, até achar a coluna de Motivo da chamada (1°), nessa coluna vai verificar as qualificações e vai procurar por qualificações que sejam sobre envio de comandos, embarque de macros, fim de viagem (2°), depois vai clicar no número da conversa escolhida, que fica na coluna Chamadas S/N (3°), para ver a conversa e realizar a auditoria na planilha do auditor (esse processo a IA já realiza), se ver a conversa e ver que da pra auditar, depois é só clicar em  Baixar (4°), caso não seja possível auditar esse WhatsApp, precisa procurar outra conversa.











Depois que a conversa é baixada, vai pra pasta de Dowloads, onde essa conversa vem em formato Chrome HTML, é necessário abrir na web e clicar com o botão direito do mouse e selecionar a opção de imprimir, para então conseguir salvar como PDF. Daí é só salvar no SharePoint da Qualidade, onde os supervisores tem acesso, para verem essas conversas. Dentro desse SharePoint tem uma pasta chamada de AUDITORIA OPERACIONAL, dentro dessa pasta, tem uma pasta para cada área, no caso do Receptivo, fica dentro da pasta das Distribuição, dentro dessa pasta de cada setor tem uma pasta referente ao mês auditado, dentro dessa pasta do mês, vai ter uma pasta para cada operador auditado e dentro da pasta de cada operador, é colocado as duas conversas que foram auditadas, para que o supervisor possa ter acesso para ver e poder contestar caso necessário. 
Dentro da IA, no módulo do supervisor, precisa ter o PDF da conversa, para que ele possa ouvir a ver a conversa auditada e assim essas pastas todas no SharePoint não serão mais necessárias. 

5 - Para a área do Checklist o processo de procura de WhatsApp, é feito direto pela plataforma da Huawei, na opção 1 dia (1°), vai colocar o período que quer puxar as ligações, do primeiro dia do mês, até a data que está fazendo a auditoria, na opção de Tipo de mídia (2°), vai colocar a opção de Multimídia que é de WhatsApp e depois vai procurar pelo Nome do agente (Funcionário) ou pelo ID do funcionário (3°) e por último vai Pesquisar (4°).















Depois de pesquisar, na parte de baixo vai trazer todos os WhatsApps do período filtrado referente ao operador, vai ir para o lado nas colunas, até achar a coluna de Motivo da chamada (1°), nessa coluna vai verificar as qualificações e vai procurar pela qualificação Atendimento do Horário (2°), depois vai clicar no número da conversa escolhida, que fica na coluna Chamadas S/N (3°), para ver a conversa e realizar a auditoria na planilha do auditor (esse processo a IA já realiza), se ver a conversa e ver que da pra auditar, depois é só clicar em  Baixar (4°), caso não seja possível auditar esse WhatsApp, precisa procurar outra conversa.











Depois que a conversa é baixada, vai pra pasta de Dowloads, onde essa conversa vem em formato Chrome HTML, é necessário abrir na web e clicar com o botão direito do mouse e selecionar a opção de imprimir, para então conseguir salvar como PDF. Daí é só salvar no SharePoint da Qualidade, onde os supervisores tem acesso, para verem essas conversas. Dentro desse SharePoint tem uma pasta chamada de AUDITORIA OPERACIONAL, dentro dessa pasta, tem uma pasta para cada área (Checklist), dentro dessa pasta de cada setor tem uma pasta referente ao mês auditado, dentro dessa pasta do mês, vai ter uma pasta para cada operador auditado e dentro da pasta de cada operador, é colocado as duas conversas que foram auditadas, para que o supervisor possa ter acesso para ver e poder contestar caso necessário. 
Dentro da IA, no módulo do supervisor, precisa ter o PDF da conversa, para que ele possa ouvir a ver a conversa auditada e assim essas pastas todas no SharePoint não serão mais necessárias. 






PROCESSO PARA LOCALIZAR LIGAÇÕES E BAIXAR NA PLATAFORMA TARIFANDO
Para o setor da Mondelez, as ligações são receptivas e são pegas dentro da plataforma tarifando, após acessar com login e senha, você deve ir em Chamadas (1°), depois Histórico de chamadas (2°) e ao lado já vai trazer os filtros.
No filtro, vai clicar em Extender.

















Após aparecer todas as opções de filtro, você vai colocar o período que quer puxar as ligações, na opção De (1°) e Até (2°), depois vai na opção de Operador (3°) e vai selecionar também a opção de Campanhas (4°), nessa opção você deve colocar Campanha Monitoramento ou Campanha Logística Reversa, pois são auditadas uma ligação de cada, depois é só Filtrar (5°).











Depois de filtrar, na parte de baixo vai trazer todos as ligações do período filtrado referente ao operador, ai precisa identificar a coluna de Duração (1°), para procurar gravações (2°) não tão longas, geralmente entre 3 e 7 minutos, após localizar uma, é só clicar no símbolo de Play ► (3°) para dar início a ouvir a gravação.














Após clicar para ouvir, vai subir uma janelinha com a gravação rodando, daí precisa ouvir a ligação e ir realizando a auditoria na planilha do auditor (esse processo a IA já realiza), se ouvir a ligação e ver que da pra auditar, é só clicar nos três pontinhos no final e vai aparecer a opção de Baixar, caso não seja possível auditar essa ligação, precisa procurar outra.








Depois que o áudio é baixado, vai pra pasta de Dowloads, onde essa ligação é recortada e vai para um SharePoint da Qualidade, onde os supervisores tem acesso, para ouvirem essas ligações. Dentro desse SharePoint tem uma pasta chamada de AUDITORIA OPERACIONAL, dentro dessa pasta, tem uma pasta para cada área (Logística), dentro dessa pasta, tem uma pasta referente ao mês auditado, dentro dessa pasta do mês vai ter outras pastas dividido pelas três operações da Logística, só localiza a da Mondelez,  dentro dessa pasta, vai ter uma pasta para cada operador auditado e dentro da pasta de cada operador, é colocado as duas ligações que foram auditadas, para que o supervisor possa ter acesso ao áudio para ouvir e poder contestar caso necessário. 
Dentro da IA, no módulo do supervisor, precisa ter o áudio da ligação, para que ele possa ouvir a ligação auditada e assim essas pastas todas no SharePoint não serão mais necessárias. 



---

### Fonte: `triagem.md`

---
setor: triagem
alertas_cobertos: []
versao: 1.0
ultima_revisao: 2026-04-16
fonte_original: Ajustes IA/Modulo de Triagem.txt
---

# POP — Triagem

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.

Modulo de Triagem

1 - Existem as ligações que passam pela detecção automática e vão automaticamente pela auditoria (em segundo plano e depois são salvas)

2 - Existem as ligações que falta algum critério, essas ficam ali pendente de revisão, correto? Vamos deixar uma função para que o auditor ouça e avalie o setor que ela é e edite manualmente e possa decidir se ela segue o fluxo e será auditada

3 - Existe também uma regra onde: São duas ligações auditadas por operador então se aquela operador foi já tem duas ligações ele não precisa ser auditado em outras ligações logo ao atingir duas ligações nos devemos: A) Ignorar alegando já ter sido auditada e seguir com os que ainda não foram auditados ou B) Colocar isso em alguma pasta? Preciso da sua opinião sobre

4 - Após fazer um processo de triagem é preciso deixar o sistema em aberto para poder receber mais arquivos, o fluxo não pode travar apos classificações a não ser que chegue no limite de 50 ligações


---

### Fonte: `unilever.md`

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










---
