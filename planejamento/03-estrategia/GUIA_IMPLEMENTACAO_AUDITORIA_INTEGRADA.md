# Guia de Implementação: Auditoria Integrada com Funcionários

**Data:** 2026-03-11
**Versão:** 1.0
**Objetivo:** Instruções passo-a-passo para integrar dados de funcionários com o sistema de auditoria automatizado

---

## 1. Visão Geral do Fluxo End-to-End

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. CONFIRMAÇÃO DE OPERADORES (Semana 1 do Mês)                   │
│    ├─ Gestores validam: nome, matrícula, ID WEON, turno, setor   │
│    ├─ Fonte: Planilha de Assiduidade                             │
│    └─ Deadline: 2 turnos                                         │
├──────────────────────────────────────────────────────────────────┤
│ 2. SELEÇÃO E COLETA DE CHAMADAS (Semana 2-3)                    │
│    ├─ Buscar no sistema de telefonia (Huawei/Weon)               │
│    ├─ Filtrar por: operador, período, motivo, matrícula          │
│    ├─ Extrair: 2 ligações por operador auditável                 │
│    └─ Download em lote: arquivos WAV/MP3                         │
├──────────────────────────────────────────────────────────────────┤
│ 3. ORGANIZAÇÃO E NOMENCLATURA (Antes da Importação)             │
│    ├─ Estrutura: Ligações/{SETOR}/{ALERTA}_operador.wav          │
│    ├─ Exemplos: Ligações/TRANSFERENCIA/desvio_rota_joao.wav      │
│    └─ Sistema infere: setor (pasta), alerta (nome arquivo)       │
├──────────────────────────────────────────────────────────────────┤
│ 4. IMPORTAÇÃO PARA BANCO DE DADOS                                │
│    ├─ Script: backend/scripts/importar_ligacoes_auditadas.py    │
│    ├─ Processa: Hash SHA-256, índices, metadados                 │
│    └─ Resultado: Tabela ligacoes_auditadas                       │
├──────────────────────────────────────────────────────────────────┤
│ 5. AVALIAÇÃO POR INTELIGÊNCIA ARTIFICIAL (IA)                   │
│    ├─ Transcrição: Azure Speech (ou AssemblyAI fallback)         │
│    ├─ Avaliação: Critérios de auditoria + pesos                  │
│    ├─ Baseado em: Sector-specific rules + operator name          │
│    ├─ Aplicar: Regras de zeragem (não-negociáveis)              │
│    └─ Resultado: Score final (0-100)                             │
├──────────────────────────────────────────────────────────────────┤
│ 6. DASHBOARD E RELATÓRIOS (Semana 4)                             │
│    ├─ Visualizar: Performance por supervisor/setor/escala        │
│    ├─ Alertas: Padrões de erro, operadores em risco              │
│    └─ Feedback: Gerar relatório de retificação                   │
├──────────────────────────────────────────────────────────────────┤
│ 7. RETIFICAÇÃO E FECHAMENTO (Dias 1-2 do Próximo Mês)           │
│    ├─ Supervisores atuam em melhorias                            │
│    ├─ Reauditoria se score < 70                                  │
│    └─ Fechamento: Registrar resultado final                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Passo 1: Confirmação de Operadores (Semana 1)

### 2.1 Responsabilidade do Gestor/Supervisor

**Arquivo de Entrada:** Planilha de Assiduidade (enviada por email)

**O que verificar:**
```
Para cada operador:
├─ Nome (conforme FUNCIONARIOS_CONSOLIDADO.xlsx)
├─ Matrícula (deve existir em colaboradores.matricula)
├─ ID WEON (campo colaboradores.id_weon)
├─ Turno/Operação (Amarela, Azul, Cinza, Verde ou Sem Escala)
├─ Supervisão (confirmar se está correto em colaboradores.supervisor)
│
E sinalar se:
├─ Em férias (usar FUNCIONARIOS_CONSOLIDADO.xlsx, aba "Funcionários")
├─ Afastado (saúde/motivo: verificar com RH)
├─ Função não-auditável (analista, trainee, etc. - não é operador)
└─ Mudança de setor/supervisor desde última auditoria
```

**Prazo:** 2 turnos (tipicamente 2 dias úteis)

**Consequências do não cumprimento:**
- ❌ Operador excluído da auditoria
- ❌ Impacta negativamente a nota
- ❌ Afeta posicionamento no quartil
- ❌ Solicitação de reauditoria não será aceita

### 2.2 Query SQL para Validação

```sql
-- Listar operadores ativos por supervisor para confirmação
SELECT nome, matricula, id_weon, supervisor, setor, escala, status
FROM colaboradores
WHERE supervisor = 'NOME_DO_SUPERVISOR'
  AND status = 'ATIVO'
ORDER BY setor, escala, nome;

-- Identificar operadores inativos que podem ser sinalizados
SELECT nome, matricula, supervisor, setor, status
FROM colaboradores
WHERE status = 'INATIVO'
ORDER BY supervisor;
```

---

## 3. Passo 2: Seleção e Coleta de Chamadas (Semana 2-3)

### 3.1 Critérios de Elegibilidade

```
Para auditar um operador:
├─ Deve ter trabalhado MÍNIMO 7 DIAS no mês
└─ Deve ter MÍNIMO 7 LIGAÇÕES AUDITÁVEIS no período
```

### 3.2 Busca no Sistema de Telefonia

**Tipo 1: Busca por Número (Telefone Alvo)**
```
Ferramenta: Painel Huawei/Weon
├─ Período: Selecionar 1 dia (ou intervalo)
├─ Número Manipulado: Inserir número do motorista/veículo
├─ Ação: Clicar "Pesquisar"
└─ Resultado: Ligações relacionadas àquele número
```

**Tipo 2: Busca Avançada por Motivo/Atendimento** (RECOMENDADO)
```
Ferramenta: Painel Huawei/Weon
├─ Período: 1 dia (ou intervalo pertinente)
├─ Tipo de Chamada: Receptivo / Ativo
├─ Tipo de Mídia: Voz
├─ Motivo da Chamada: Filtrar por tipo
│  ├─ Transferência: "Desvio de Rota", "Parada Indevida", "Prioritário"
│  ├─ BAS: "Roubo", "Acidente", "Prioritário"
│  ├─ Cadastro: "Antecedentes"
│  ├─ Logística: "Temperatura", "Atraso", "Estadia"
│  └─ Checklist: "CHATBOT"
├─ ID do Funcionário: MATRÍCULA do operador (conforme colaboradores)
├─ Ação: Clicar "Pesquisar"
└─ Resultado: Ligações daquele operador com motivo específico
```

### 3.3 Seleção de Amostra

```
Para cada operador auditável:
├─ Selecionar EXATAMENTE 2 LIGAÇÕES
│  └─ Preferencialmente: 1 com cliente, 1 com motorista/suporte
│
├─ Documentar para cada ligação:
│  ├─ Timestamp (data/hora da chamada)
│  ├─ Duração
│  ├─ Nome do operador
│  ├─ Motivo/Alerta
│  ├─ Contato (motorista, cliente, polícia, etc.)
│  └─ Matrícula do operador (cruzar com colaboradores)
│
└─ Relato (OBRIGATÓRIO):
   ├─ Nome da pessoa contatada
   ├─ Telefone completo (com DDD)
   ├─ Confirmação de senha/dados pessoais
   └─ Detalhes relevantes do alerta
```

### 3.4 Exportação em Lote

```
1. Selecionar ligações na lista de resultados
2. Clicar "Download em Lote" ou "Exportar"
3. Formato: WAV (preferido) ou MP3
4. Salvar localmente com nomes temporários
5. Organizar conforme próximo passo
```

---

## 4. Passo 3: Organização e Nomenclatura

### 4.1 Estrutura de Pastas Esperada

```
Ligações/
├─ TRANSFERENCIA/
│  ├─ desvio_rota_joao_silva.wav
│  ├─ parada_indevida_maria_santos.wav
│  ├─ prioritario_carlos_oliveira.wav
│  └─ ...
├─ BAS/
│  ├─ acidente_roberto_dias.wav
│  ├─ roubo_patricia_gomes.wav
│  └─ ...
├─ CADASTRO/
│  ├─ antecedente_paulo_costa.wav
│  └─ ...
├─ LOGISTICA/
│  ├─ temperatura_motorista_123.wav
│  ├─ atraso_cliente_abc.mp3
│  ├─ estadia_antonio_silva.wav
│  └─ ...
├─ CHECKLIST/
│  ├─ chatbot_alicia_santos.wav
│  └─ ...
└─ MONDELEZ/
   ├─ monitoramento_i_operador.wav
   └─ ...
```

### 4.2 Convenção de Nomenclatura de Arquivos

**Formato Esperado:**
```
{ALERTA}_{OPERADOR_NOME_OU_MATRICULA}.{wav|mp3}
```

**Exemplos Válidos:**
```
desvio_rota_joao_silva.wav          → Alerta: desvio de rota
temperatura_motorista_12345.wav     → Alerta: temperatura
atraso_cliente_abc.mp3              → Alerta: atraso
antecedente_paulo.wav               → Alerta: antecedentes
parada_indevida_maria.wav           → Alerta: parada indevida
acidente_roberto.wav                → Alerta: acidente
roubo_patricia.wav                  → Alerta: roubo
chatbot_alicia.wav                  → Alerta: chatbot
monitoramento_i_operador.wav        → Alerta: monitoramento I
monitoramento_ii_operador.wav       → Alerta: monitoramento II
estadia_antonio.wav                 → Alerta: estadia
```

### 4.3 Mapeamento Automático de Alertas

O sistema infere automaticamente:

| Palavra no Nome | Alerta Inferido | Setor(es) |
|-----------------|-----------------|-----------|
| `desvio` | Desvio de Rota | TRANSFERENCIA, BAS, UTI, LOGISTICA |
| `parada` | Parada Indevida | TRANSFERENCIA, BAS, UTI, LOGISTICA |
| `posicao`, `atraso` | Posição em Atraso | TRANSFERENCIA, BAS, UTI, LOGISTICA |
| `prioritario` | Alerta Prioritário | TRANSFERENCIA, BAS, UTI |
| `temperatura` | Controle de Temperatura | LOGISTICA |
| `estadia` | Estadia | LOGISTICA |
| `antecedente` | Antecedentes | CADASTRO |
| `devolucao` | Devolução | LOGISTICA, UNILEVER |
| `acidente` | Acidente | BAS, UTI |
| `roubo` | Roubo | BAS, UTI |
| `chatbot` | CHATBOT | CHECKLIST, RECEPTIVO |
| `monitoramento` | Monitoramento | MONDELEZ |

---

## 5. Passo 4: Importação para Banco de Dados

### 5.1 Executar Script de Importação

```bash
# Na raiz do projeto, executar:
python backend/scripts/importar_ligacoes_auditadas.py

# Ou com ambiente virtual (Windows):
backend\.venv\Scripts\python.exe backend/scripts/importar_ligacoes_auditadas.py
```

### 5.2 O que o Script Faz

```
Para cada arquivo em Ligações/:
├─ 1. Identifica a PASTA (setor)
│     └─ Exemplo: "TRANSFERENCIA" → setor_id = 1
├─ 2. Identifica o ALERTA pelo nome do arquivo
│     └─ Exemplo: "desvio" → alerta_id = "desvio_rota"
├─ 3. Extrai NOME DO OPERADOR
│     └─ Exemplo: "joao_silva" → busca em colaboradores.nome
├─ 4. Calcula HASH SHA-256
│     └─ Evita duplicações futuras
├─ 5. Obtém METADADOS
│     ├─ Duração do arquivo
│     ├─ Data/hora de modificação
│     └─ Tamanho em bytes
└─ 6. Insere na tabela ligacoes_auditadas
    ├─ Campos: setor, alerta, operador_id, hash, arquivo, timestamp
    └─ Índices: operador_id, setor, alerta (para queries rápidas)
```

### 5.3 Verificar Importação

```sql
-- Contar ligações importadas por setor
SELECT setor, COUNT(*) as total
FROM ligacoes_auditadas
GROUP BY setor
ORDER BY total DESC;

-- Ver ligações de um operador específico
SELECT * FROM ligacoes_auditadas
WHERE operador_id = (
    SELECT id FROM colaboradores WHERE nome LIKE '%joao%'
);

-- Identificar arquivos sem correspondência (nome não encontrado)
SELECT arquivo, nome_extraido
FROM ligacoes_auditadas
WHERE operador_id IS NULL
ORDER BY arquivo;
```

---

## 6. Passo 5: Avaliação por Inteligência Artificial

### 6.1 Fluxo de Processamento IA

```
Para cada ligação_auditada não processada:

├─ 1. TRANSCRIÇÃO
│    ├─ Provedor: Azure Speech Services (primário)
│    ├─ Fallback: AssemblyAI
│    └─ Resultado: Texto completo + timestamps por speaker
│
├─ 2. PREPARAÇÃO DO PROMPT
│    ├─ Injetar: Nome do operador
│    ├─ Injetar: Setor + tipo de chamada
│    ├─ Injetar: Critérios específicos (com pesos)
│    ├─ Injetar: Regras de zeragem (não-negociáveis)
│    └─ Template: audit-prompt/structured/{SETOR}.json
│
├─ 3. AVALIAÇÃO (Azure OpenAI)
│    ├─ Modelo: gpt-4 ou superior
│    ├─ Critérios: ~12-15 questões por setor
│    ├─ Pesos: Aplicados automaticamente
│    └─ Resultado: Score bruto (0-100)
│
├─ 4. APLICAR REGRAS DE ZERAGEM
│    ├─ Se operador = hostil → score = 0
│    ├─ Se operador = abandono → score = 0
│    ├─ Se setor CADASTRO + sem resposta 45s → score = 0
│    ├─ Se TRANSFERENCIA + falha senha → score = 0
│    └─ Caso contrário → manter score calculado
│
├─ 5. ARMAZEAR RESULTADO
│    └─ Tabela: audits (id, operador_id, score, timestamp, etc.)
│
└─ 6. DISPONIBILIZAR NO DASHBOARD
     └─ Visualizar: Performance por operador/supervisor/setor
```

### 6.2 Critérios de Avaliação por Setor

Referencia: `docs/references/auditoria/criterios-auditoria-opentech.md`

**Exemplo para TRANSFERENCIA/DESVIO_ROTA:**
```json
{
  "criterios": [
    {
      "pergunta": "Operador se identificou com saudação, nome, setor e empresa?",
      "peso": 0.30
    },
    {
      "pergunta": "Operador confirmou a senha de segurança antes de prosseguir?",
      "peso": 2.00
    },
    {
      "pergunta": "Operador informou claramente o motivo do contato?",
      "peso": 1.03
    },
    ...
  ],
  "regras_zeragem": [
    "Se comportamento hostil: score = 0",
    "Se abandono de chamada: score = 0",
    "Se não confirmou senha: score = 0"
  ]
}
```

### 6.3 Injeção de Contexto no Prompt

O prompt para IA inclui:

```
[SECTOR_CONTEXT]
Setor: TRANSFERENCIA
Tipo de Chamada: Ativa (operador → motorista)
Alerta: Desvio de Rota
Operador: João Silva (matrícula: 12345)

[NON_NEGOTIABLE_RULES]
- Falha no manuseio de senha → Zera automaticamente
- Comportamento hostil → Zera automaticamente
- Abandono de chamada → Zera automaticamente

[AUDIT_CRITERIA]
Avalie a ligação segundo estes critérios com pesos:
1. Identificação (peso: 0,30) - "Olá, sou João Silva, setor Transferência, nstech"
2. Confirmação de Senha (peso: 2,00) - "Por favor, confirme sua senha de segurança"
...
```

---

## 7. Passo 6: Dashboard e Relatórios (Semana 4)

### 7.1 Visualizações Disponíveis

**Após importação e avaliação IA, disponíveis:**

```
┌─────────────────────────────────────────────────┐
│ DASHBOARD DE PERFORMANCE                        │
├─────────────────────────────────────────────────┤
│                                                 │
│ [KPI Cards]                                     │
│ ┌──────────┬──────────┬──────────┐             │
│ │ Avg Score│ % Alertas│ Trending │             │
│ │  78.5    │   22.3%  │    ↓ -3% │             │
│ └──────────┴──────────┴──────────┘             │
│                                                 │
│ [Gráfico por Supervisor]                       │
│ Geniffer Maciel   ▯▯▯▯▯▯ 82 pts                │
│ Rodrigo Barros    ▯▯▯▯▯  79 pts                │
│ Geovana Meurer    ▯▯▯▯▯▯▯▯ 85 pts              │
│ ...                                             │
│                                                 │
│ [Tabela: Supervisores com Mais Alertas]        │
│ Supervisor         | Alertas | % Pop. |        │
│ Carlos Eduardo     |    5    |  31%   |        │
│ Adryan Celso       |    3    |  30%   |        │
│ ...                                             │
│                                                 │
│ [Filtros]                                      │
│ [Período ▼] [Setor ▼] [Escala ▼]              │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 7.2 Relatórios por Perfil

**Para GESTORES:**
```
├─ Performance por setor (média, min, max)
├─ Tendência (melhoria/piora ao longo do mês)
├─ Comparação entre supervisores
└─ Alertas críticos (score < 60)
```

**Para SUPERVISORES:**
```
├─ Detalhe de cada operador sua equipe
├─ Alertas por operador
├─ Recomendações de treinamento
├─ Comparação: meu time vs. outros supervisores
└─ Detalhes de cada ligação auditada
```

**Para RH:**
```
├─ Estatísticas de desempenho por operador
├─ Tendências históricas (mês a mês)
├─ Compatibilidade com avaliações anuais
├─ Identificação de operadores em risco
└─ Dados para decisões de promoção/treinamento
```

### 7.3 Alertas Automáticos

```
Disparado quando:
├─ Operador score < 60 (crítico) → email ao supervisor
├─ Setor score < 75 → notificação ao gestor
├─ Padrão detectado (ex: 3 zeros consecutivos) → análise
├─ Taxa de erro acima de threshold → investigação necessária
└─ Comparação com peers (outlier detection)
```

---

## 8. Passo 7: Retificação e Fechamento (Dias 1-2 Próximo Mês)

### 8.1 Ações Esperadas por Supervisor

```
Para cada operador com score < 70:

├─ Revisão: Entender qual critério falhou
├─ Feedback: Conversa com operador sobre melhoria
├─ Treinamento: Se necessário, agendar sessão
├─ Reauditoria: Se score muito baixo, solicitar reavaliação
│  └─ Máx 2 reauditorias por mês por operador
│
└─ Resultado: Documentar ação tomada no sistema
```

### 8.2 Matriz de Decisão

| Score | Ação | Responsável |
|-------|------|-------------|
| 90-100 | ✅ Aprovado | Nada a fazer |
| 75-89 | 📋 Observação | Supervisor acompanha |
| 60-74 | ⚠️ Aviso | Supervisor reúne com operador |
| < 60 | 🔴 Crítico | Treinamento + Reauditoria |

### 8.3 Query para Gerar Relatório de Retificação

```sql
-- Operadores com score baixo que precisam retificação
SELECT
    o.nome,
    o.supervisor,
    o.setor,
    ROUND(AVG(a.score), 1) as score_medio,
    COUNT(*) as auditorias,
    SUM(CASE WHEN a.score < 60 THEN 1 ELSE 0 END) as zerados
FROM colaboradores o
LEFT JOIN audits a ON o.nome = a.operator_name
WHERE a.timestamp > DATE('now', '-30 days')
  AND o.status = 'ATIVO'
GROUP BY o.id
HAVING score_medio < 70
ORDER BY score_medio ASC;
```

---

## 9. Troubleshooting e Perguntas Frequentes

### Q1: Arquivo de áudio foi importado mas não aparece na IA?
```
Checklist:
├─ Verificar se hash SHA-256 já existe (duplicado)
├─ Validar nomeação: {ALERTA}_{OPERADOR}.{wav/mp3}
├─ Confirmar que pasta = setor válido
├─ Checar tamanho do arquivo (mín 10KB, máx 100MB)
└─ Logs: backend/logs/import_ligacoes.log
```

### Q2: Operador não foi encontrado no banco?
```
Solução:
├─ Verificar ortografia no nome (case-sensitive?)
├─ Confirmar se operador existe em colaboradores
├─ Cruzar com matrícula em vez de nome
│  └─ Nomeação alternativa: matrícula_operador.wav
└─ Contactar RH se operador novo (não importado ainda)
```

### Q3: Score da ligação parece incorreto?
```
Verifique:
├─ Se transcrição está correta (revisar no dashboard)
├─ Se prompts/criterios_auditoria estão atualizados
├─ Se regras de zeragem foram aplicadas (score 0 esperado?)
├─ Logs da IA: backend/logs/audit_evaluation.log
└─ Escalação: revisar com gestor de qualidade
```

---

## 10. Próximos Passos: Otimizações Futuras

- [ ] **API de Feedback:** Supervisores deixarem feedback diretamente no sistema
- [ ] **Automação de Retificação:** Gerar planos de ação automáticamente
- [ ] **Machine Learning:** Prever operadores em risco baseado em tendência
- [ ] **Integração RH:** Sincronizar movimentações com sistema de folha
- [ ] **Mobile App:** Supervisores consultarem via smartphone

---

**Documento mantido por:** Lucas (Desenvolvimento)
**Última atualização:** 2026-03-11
**Contato Técnico:** lucas@nstech.com | Ramal: 2050
