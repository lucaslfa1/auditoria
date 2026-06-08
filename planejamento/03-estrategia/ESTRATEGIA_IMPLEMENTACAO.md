# Estratégia de Implementação - Sistema de Auditoria

**Data:** 2026-03-10
**Fase:** 1 - Consolidação de Dados
**Status:** ✅ Concluído | 🔄 Em Progresso | ⏳ Planejado

---

## 1. Visão Geral

### Objetivo Principal
Integrar dados estruturados de 198 funcionários distribuídos em 9 setores com 17 supervisores ao sistema de auditoria para análise de qualidade de atendimento granular por operador, supervisor e setor.

### Marcos Principais
```
[✅] FASE 1: Consolidação de Dados (CONCLUÍDO)
     ├─ Extração de 18 arquivos Excel
     ├─ Normalização de 198 funcionários
     ├─ Mapeamento de supervisores (17)
     ├─ Vinculação matrícula ↔ ramal Huawei
     └─ Importação para banco de dados

[🔄] FASE 2: Integração com Auditorias (EM PROGRESSO)
     ├─ Vincular nomes de auditorias com matrícula
     ├─ Validar correspondência
     ├─ Criar índices para performance
     └─ Implementar API de consulta

[⏳] FASE 3: Análises e Relatórios (PLANEJADO)
     ├─ Dashboard de performance
     ├─ Alertas por padrão
     ├─ Análises preditivas
     └─ Integração com RH

[⏳] FASE 4: Otimizações (FUTURO)
     ├─ Machine Learning para previsão
     ├─ Automação de feedback
     ├─ Planejamento de treinamento
     └─ Integração com sistema de folha
```

---

## 2. Detalhamento por Fase

### 2.1 FASE 1: Consolidação ✅ CONCLUÍDO

**Atividades Executadas:**
- [x] Analisar 18 arquivos Excel (estrutura, consistência)
- [x] Extrair 198 funcionários com dados completos
- [x] Normalizar nomes de setores (9 setores mapeados)
- [x] Identificar 17 supervisores únicos
- [x] Mapear escalas (Amarela, Azul, Cinza, Verde)
- [x] Criar tabela `colaboradores` com 17 campos
- [x] Gerar relatório técnico (este documento)

**Arquivos Gerados:**
- ✅ `FUNCIONARIOS_CONSOLIDADO.xlsx` - 4 sheets com análises
- ✅ `planejamento/02-analises/ANALISE_FUNCIONARIOS.md` - Relatorio detalhado
- ✅ `colaboradores` - Tabela no banco de dados

**Próximo:** Validação com RH/TI

---

### 2.2 FASE 2: Integração com Auditorias 🔄 EM PROGRESSO

#### 2.2.1 Vincular Auditorias com Operadores

**Problema:**
- Atualmente: `audits.operator_name` contém apenas o nome do operador
- Necessário: Vincular com `colaboradores.matricula` e `colaboradores.id_huawei`

**Solução:**
```sql
-- View para ligar auditorias com operadores
CREATE VIEW audits_com_operador AS
SELECT
    a.id,
    a.timestamp,
    a.operator_name,
    o.matricula,
    o.id_huawei,
    o.supervisor,
    o.setor,
    o.escala,
    o.status,
    a.score,
    a.sector_id,
    a.alert_id
FROM audits a
LEFT JOIN colaboradores o
    ON LOWER(TRIM(a.operator_name)) = LOWER(TRIM(o.nome))
WHERE a.operator_name IS NOT NULL;
```

**Passos:**
- [ ] Implementar view de vinculação
- [ ] Criar índices em `colaboradores.nome` e `audits.operator_name`
- [ ] Testar correspondência com amostra de auditorias
- [ ] Implementar fallback para busca por matrícula/ramal
- [ ] Criar relatório de matching quality

**Timeline:** 1 semana

---

#### 2.2.2 Criar APIs de Consulta

**Endpoints necessários:**

```
GET /api/operadores/
  Query: ?supervisor=, ?setor=, ?escala=, ?status=
  Response: Lista de operadores com suas auditorias

GET /api/operadores/{id_operador}/auditorias
  Response: Auditorias do operador com scores e feedback

GET /api/supervisores/{id_supervisor}/equipe
  Response: Todos os operadores sob um supervisor + KPIs

GET /api/setores/{id_setor}/analise
  Response: Análise agregada do setor (qualidade, alertas)

GET /api/escalas/{escala}/performance
  Response: Performance por escala (distribuição de scores)
```

**Implementação:** FastAPI Python
**Timeline:** 2 semanas

---

### 2.3 FASE 3: Análises e Relatórios ⏳ PLANEJADO

#### 3.1 Análises por Supervisor

```
Métrica                    | Tipo      | Frequência
---------------------------|-----------|----------
Quality Score Médio        | Agregado  | Semanal
Taxa de Alertas            | Contagem  | Semanal
Distribuição de Severidade | Histograma| Mensal
Tendência (melhoria/piora) | Temporal  | Mensal
Comparação com Peers       | Benchmark | Mensal
```

#### 3.2 Análises por Setor

```
CADASTRO:
├─ KPI: Precisão de cadastro
├─ Benchmark: 98% (padrão da indústria)
└─ Alert: Se < 95% por 2 semanas

DISTRIBUIÇÃO:
├─ KPI: Entregas no prazo informado
├─ Benchmark: 99.5%
└─ Alert: Se < 99% por semana

LOGÍSTICA:
├─ KPI: Acurácia de rastreamento
├─ Benchmark: 99.8%
└─ Alert: Se < 99.5% por semana

UTI (Gerenciamento de Risco):
├─ KPI: Resolução de sinistros
├─ Benchmark: 95% taxa de resolução
└─ Alert: Se < 90% por semana
```

#### 3.3 Dashboard de Performance

**Componentes principais:**

```
┌─────────────────────────────────────────┐
│  DASHBOARD DE PERFORMANCE               │
├─────────────────────────────────────────┤
│                                         │
│  [KPI Cards]                            │
│  ┌──────────┬──────────┬──────────┐    │
│  │ Avg Qtd  │ % Alertas│ Trending │    │
│  │  87.5    │   12.3%  │    ↑ +2% │    │
│  └──────────┴──────────┴──────────┘    │
│                                         │
│  [Gráficos]                             │
│  ┌─────────────────────────────────┐   │
│  │ Score Distribution by Supervisor │   │
│  │ ▯ Geniffer (avg: 88)             │   │
│  │ ▯ Rodrigo  (avg: 85)             │   │
│  │ ▯ Geovana  (avg: 91)             │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [Tabelas]                              │
│  Supervisores com Mais Alertas Este Mês│
│  ...                                    │
│                                         │
└─────────────────────────────────────────┘
```

**Stack:** React + Recharts + Tailwind
**Timeline:** 3 semanas

---

### 2.4 FASE 4: Otimizações ⏳ FUTURO (Q2 2026)

#### 4.1 Machine Learning

**Modelo 1: Previsão de Alertas**
```
Input:  Histórico de 30 dias do operador
Output: Probabilidade de alerta nos próximos 5 dias
Usar:   Regressão Logística ou RandomForest
```

**Modelo 2: Recomendação de Treinamento**
```
Input:  Padrões de erro, supervisor, setor
Output: Top 3 tópicos para treinamento
Usar:   Clustering + Rule-based
```

#### 4.2 Automação

- [ ] Auto-gerar feedback por supervisor (via IA)
- [ ] Notificações em tempo real de anomalias
- [ ] Sugestões de rearranjo de escala baseado em performance

---

## 3. Estrutura de Dados Necessária

### 3.1 Tabelas Existentes

| Tabela | Status | Uso |
|--------|--------|-----|
| `colaboradores` | ✅ Pronta | Dados mestres de funcionários |
| `audits` | ✅ Pronta | Auditorias com scores |
| `operators` | ⚠️ Vazia | Legacy (considerar descontinuar) |

### 3.2 Tabelas a Criar

```sql
-- Feedback consolidado por supervisor
CREATE TABLE supervisor_feedback (
    id INTEGER PRIMARY KEY,
    supervisor_id TEXT,
    operador_id INTEGER,
    periodo_inicio DATE,
    periodo_fim DATE,
    score_medio REAL,
    total_auditorias INTEGER,
    taxa_alertas REAL,
    pontos_melhoria TEXT,
    criado_em TIMESTAMP
);

-- Histórico de performance (série temporal)
CREATE TABLE performance_historico (
    id INTEGER PRIMARY KEY,
    operador_id INTEGER,
    data DATE,
    score_dia REAL,
    auditorias_dia INTEGER,
    alertas_dia INTEGER,
    FOREIGN KEY(operador_id) REFERENCES colaboradores(id)
);

-- Sugestões de treinamento
CREATE TABLE recomendacoes_treinamento (
    id INTEGER PRIMARY KEY,
    operador_id INTEGER,
    supervisor_id TEXT,
    tema TEXT,
    motivo TEXT,
    data_sugestao TIMESTAMP,
    data_completado TIMESTAMP,
    status TEXT
);
```

---

## 4. Métricas de Sucesso

### 4.1 Curto Prazo (Fase 2)

| Métrica | Meta | Status |
|---------|------|--------|
| Matching Rate (nomes) | ≥ 95% | ⏳ A medir |
| API Latency | < 500ms | ⏳ A medir |
| Data Consistency | 100% | ⏳ A validar |

### 4.2 Médio Prazo (Fase 3)

| Métrica | Meta | Status |
|---------|------|--------|
| Dashboard Uptime | ≥ 99% | ⏳ A implementar |
| Usuários Ativos | ≥ 50 | ⏳ A medir |
| Insights Acionáveis | ≥ 10/mês | ⏳ A medir |

### 4.3 Longo Prazo (Fase 4)

| Métrica | Meta | Status |
|---------|------|--------|
| Redução de Alertas | -20% | ⏳ A medir |
| Melhoria de Score | +5 pts | ⏳ A medir |
| ROI do Sistema | +300% | ⏳ A projetar |

---

## 5. Riscos e Mitigação

### 5.1 Risco: Qualidade de Dados

**Problema:** Dados incompletos ou inconsistentes
**Probabilidade:** Média
**Impacto:** Alto

**Mitigação:**
- [x] Validação inicial dos 198 funcionários
- [ ] Verificação mensal com RH
- [ ] Alerts para dados faltantes

### 5.2 Risco: Matching Ruim

**Problema:** Nomes em auditorias não correspondem a `colaboradores`
**Probabilidade:** Média
**Impacto:** Alto

**Mitigação:**
- [ ] Implementar busca fuzzy (SoundEx/Levenshtein)
- [ ] Fallback para matrícula/ramal Huawei
- [ ] Manual review sheet para não-matches

### 5.3 Risco: Performance

**Problema:** Queries lentas com muitos dados
**Probabilidade:** Baixa (atual: 198 ops)
**Impacto:** Médio

**Mitigação:**
- [ ] Criar índices em campos-chave
- [ ] Implementar caching
- [ ] Particionamento temporal de auditorias

---

## 6. Cronograma Geral

```
Março 2026:
  └─ W1: [✅] Consolidação de dados concluída
  └─ W2: [🔄] Iniciar integração com auditorias
  └─ W3: [🔄] Implementar views de vinculação
  └─ W4: [🔄] Testar APIs preliminares

Abril 2026:
  └─ W1: Finalizar APIs de consulta
  └─ W2: Implementar dashboard básico
  └─ W3: Testes de performance e stress
  └─ W4: Deploy em produção (Fase 2)

Maio-Junho 2026:
  └─ Fase 3: Análises avançadas e Machine Learning

Julho+ 2026:
  └─ Fase 4: Otimizações e automação
```

---

## 7. Recursos Necessários

| Recurso | Quantidade | Alocação | Timeline |
|---------|-----------|----------|----------|
| Engenheiro Backend | 1 | 50% | 4 semanas |
| Engenheiro Frontend | 1 | 40% | 3 semanas |
| Data Analyst | 1 | 30% | 2 semanas |
| DBA/DevOps | 0.5 | 20% | Contínuo |

---

## 8. Comunicação e Stakeholders

### 8.1 Relatórios

```
Semanal (seg):
└─ Status técnico (equipe desenvolvimento)

Quinzenal (2ª, 15h):
└─ Checkpoint com PM (produto)

Mensal:
└─ Apresentação com stakeholders (RH, Operações, Gestão)
```

### 8.2 Documentação

- [x] Relatorio tecnico: `planejamento/02-analises/ANALISE_FUNCIONARIOS.md`
- [ ] Manual de API (quando implementado)
- [ ] Guia de uso do Dashboard (quando implementado)
- [ ] Data Dictionary (estrutura de campos)

---

## 9. Próximas Ações Imediatas

**👉 Esta Semana (Até 2026-03-14):**

1. [ ] Revisar `FUNCIONARIOS_CONSOLIDADO.xlsx` com equipe
2. [ ] Validar dados com RH (conferir inativos)
3. [ ] Criar plano detalhado para Fase 2
4. [ ] Iniciar implementação de views SQL

**👉 Próximas 2 Semanas:**

1. [ ] Implementar view `audits_com_operador`
2. [ ] Criar índices de performance
3. [ ] Desenvolver primeiras APIs
4. [ ] Testes de correspondência nome/matrícula

**👉 Mês de Abril:**

1. [ ] Finalizar integração
2. [ ] Implementar dashboard MVP
3. [ ] Testes com usuários reais
4. [ ] Refinar conforme feedback

---

## Conclusão

O sistema de auditoria está agora **data-driven** com estrutura sólida de 198 funcionários mapeados e prontos para análises profundas. As próximas fases enfocam na integração contínua e na entrega de insights acionáveis para supervisores, gestores e RH.

**Status Geral:** ✅ **ON TRACK**

**Contato:** Lucas (Desenvolvimento) | Última atualização: 2026-03-10
