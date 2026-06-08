# Plano: Padronização de Classes de Alerta

## Objetivo
Criar uma padronização de "Classes de Alerta" no sistema, utilizando como base as tratativas oficiais já auditadas. O objetivo é abstrair as variações de interlocutor (Motorista, Cliente, Receptivo, Polícia) para permitir relatórios e agrupamentos consolidados por tipo de incidente.

## Estrutura das Classes (Taxonomia Baseada nos Alertas Atuais)
A nova propriedade `class` será inferida a partir dos nomes oficiais (removendo os sufixos de interlocutor):
- **Alerta Prioritário**
- **Posição em Atraso**
- **Parada Indevida**
- **Desvio de Rota**
- **Contato com Ponto de Apoio**
- **Antecedentes**
- **Devolução**
- **Cabinets**
- **Atuação Tratativa**
- **Distribuição**
- **Loss Tree**
- **Estadia**
- **Temperatura**
- **Desligamento Temperatura**
- **Atraso de Entrega**
- **Ativação de AE**
- **Atraso**
- **Taborda**
- **Atraso no Início de Viagem**
- **Logística Reversa**
- **Monitoramento I / II**
- **Checklist**
- **Atendimento ao Cliente**

## Modificações Necessárias

### 1. Banco de Dados (`backend/db/runtime_schema.py`)
- Adicionar a coluna `alert_class TEXT` na tabela `audit_alerts`.

### 2. Configurações (`backend/db/scoring_rules_final.yaml`)
- Para cada bloco de alerta (`alerts:`), adicionar a propriedade explícita `class: "Nome da Classe"`.
  *Exemplo:*
  ```yaml
  alerts:
  - id: UTI-PRIORITARIO-MOT
    sector: uti
    class: Alerta Prioritário
    label: Alerta Prioritário - Motorista
  ```

### 3. Sincronização (`backend/db/scoring_loader.py` e `backend/database.py`)
- Atualizar a função que carrega o YAML para o banco de dados (`scoring_loader.py`), para ler a propriedade `class` e fazer o `INSERT / UPDATE` na coluna `alert_class`.
- Atualizar a query de leitura de alertas no `database.py` para expor a nova classe para os endpoints da API (Dashboards e Relatórios).

## Verificação
- Rodar o carregador de pontuação (`scoring_loader.py`) e verificar se a tabela `audit_alerts` foi atualizada com as novas classes.
- Rodar o conjunto de testes local (`pytest`) para garantir que nenhuma estrutura de payload quebrou.
