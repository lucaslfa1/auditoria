# Planejamento Técnico: Módulo de Automação Híbrida

Este documento descreve a arquitetura e os fluxos propostos para o novo módulo de Automação do sistema Auditoria, que integrará os módulos de Telefonia (Huawei), Triagem e Auditoria.

## Visão Geral: O Fluxo Híbrido de Auditoria

O sistema operará como um "motor flexível", permitindo a execução de auditorias em duas vias independentes, mas que convergem para o mesmo ponto: a revisão humana na tela "Arquivos" (com status `awaiting_pair`).

### Caminho 1: A Via Expressa (100% Automática / O Robô)
Essa via roda em background (ex: de madrugada) para processar grandes volumes:
1. **Telefonia Automática:** O robô se conecta à API da Huawei, busca as ligações recentes e faz o download dos áudios.
2. **Triagem Automática:** Os áudios são enviados para o modelo de classificação, que detecta o Operador, o Setor e o Alerta (motivo da ligação).
3. **Auditoria Automática:** As ligações triadas entram na fila da IA (Azure OpenAI) para transcrição, avaliação dos critérios ("Atende" / "Não atende") e geração de justificativas.
4. **Arquivamento (Aguardando Pareamento):** O robô salva silenciosamente a auditoria com status `awaiting_pair`. Quando o Auditor chega, encontra a auditoria pronta para revisão, edição e envio final ao supervisor.

### Caminho 2: A Via Manual (Sob Demanda)
Esta via permite controle pontual e manual por parte do auditor:
1. **Telefonia Manual:** O auditor busca e baixa a ligação específica pela tela de Telefonia.
2. **Triagem Manual:** Na tela de Triagem, o auditor insere o áudio e a IA detecta os metadados. O auditor pode corrigir manualmente caso a IA erre.
3. **Auditoria Manual:** O auditor inicia a avaliação e acompanha a geração das notas pela IA.
4. **Arquivamento (Aguardando Pareamento):** Após revisar e corrigir as notas na tela, o auditor clica em "Arquivar auditoria", enviando-a para a mesma gaveta (`awaiting_pair`).

## Plano de Ação Técnico: 4 Etapas Principais

1. **O "Motor" no Backend (O Orquestrador)**
   - Criar um script/serviço Python (`automation_engine.py`) que roda em loop contínuo.
   - Executar a sequência: Buscar (Huawei) > Triar > Auditar (IA) > Salvar (`awaiting_pair`).

2. **O Banco de Dados (Controle de Tráfego e Limites)**
   - Criar controle para evitar download/auditoria duplicada da mesma ligação.
   - Respeitar a cota mensal de auditorias por operador, evitando custos desnecessários com a API da IA.

3. **A Tela de Controle (O Painel do Módulo)**
   - Criar uma nova interface Frontend (React) "Automação".
   - Recursos: Botão Ligar/Desligar (ON/OFF), Filtros de Regras (Setor, Limite Diário) e Log de Atividades ao vivo.

4. **Testes e Handoff (A Passagem de Bastão)**
   - Garantir que a auditoria gerada pelo robô apareça perfeitamente na tela "Arquivos".
   - Confirmar que auditores podem ler a transcrição, alterar a nota se a IA errar e prosseguir com o fluxo normal (enviar ao supervisor) sem duplicar registros no dashboard.