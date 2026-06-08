# Relatório de Atividades - Sincronização Huawei e Automação
**Data:** 03 de Maio de 2026 (madrugada do dia 04)

## 1. Configuração do Motor de Automação (Cloud Scheduler)
- **Problema:** A automação em modo "Loop Residente" não é adequada para o Google Cloud Run, pois a infraestrutura "congela" a CPU (CPU Throttling) quando a aplicação não está recebendo requisições HTTP, interrompendo o ciclo de busca de 10 minutos.
- **Solução Aplicada:** 
  - O motor de automação foi migrado para um acionamento por **Gatilho Externo (Google Cloud Scheduler)**.
  - Foi criado o job `auditoria-telefonia-sync` na nuvem que faz uma chamada automática para a rota `/api/telefonia/cron/sync` a cada 10 minutos.
  - **Segurança:** Implementado um `CRON_SECRET_TOKEN` validado no backend para garantir que apenas o serviço legítimo da Google possa ativar a coleta em background.
  - **Lógica de Frequência:** O backend foi instruído a respeitar o intervalo escolhido no painel pelo gestor. Mesmo recebendo a chamada do Scheduler a cada 10 minutos, o sistema verifica no banco de dados a opção `automacao_intervalo_segundos`. Caso o usuário tenha escolhido "2 Horas", o robô rejeitará o processamento até que de fato se passem 2 horas desde a última busca.

## 2. Destravamento de Sincronização (Reset do DB Lock)
- **Problema:** Ao disparar manualmente a coleta de áudios, o painel retornava "Sync Huawei já está em andamento".
- **Solução Aplicada:** Isso ocorreu porque as atualizações (deploys) foram enviadas no meio de uma sincronização ativa, impedindo o código de liberar a trava de segurança (`sync_lock`). Um script forçou o `UPDATE` na tabela `configuracoes` para destrancar a fila e permitir que os novos downloads fluíssem normalmente.

## 3. Refatoração de Custo e Tempo Retroativo
- **Problema:** A configuração global de horas retroativas estava livre para digitação e rodando com "48 horas", o que exigia um custo e tempo de processamento muito alto da IA em cada ciclo de automação (buscando dois dias inteiros a cada 10 minutos).
- **Solução Aplicada:** 
  - O formulário (`HuaweiCredentialsCard.tsx`) foi refatorado. O campo livre virou uma lista suspensa (`<select>`) limitando o gestor a opções seguras e lógicas: 24h, 12h, 6h, 4h, 2h, 1h e 30 minutos.
  - O Core de Telefonia (Python) foi reescrito para aceitar números de `ponto flutuante` (floats). Com isso, a opção de "30 minutos" passa o valor `0.5`, otimizando ao máximo o volume de requisições na API da Huawei e Azure e focando no processamento ultra-recente.
- **Deploy:** Imagem Docker recriada manualmente (manual-3) e consolidada no Google Cloud Run.