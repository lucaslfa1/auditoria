# Análise Completa de Funcionários - nstech Call Center

**Data da Análise:** 2026-03-10
**Versão:** 1.0
**Responsável:** Sistema de Auditoria

---

## Executivo

Este documento consolida a análise dos **18 arquivos Excel** contendo **198 funcionários** distribuídos em **9 setores operacionais** com **17 supervisores** identificados. A estrutura foi mapeada, normalizada e importada para o banco de dados central.

---

## 1. Estatísticas Gerais

| Métrica | Valor |
|---------|-------|
| **Total de Funcionários** | 198 |
| **Setores Operacionais** | 9 |
| **Supervisores** | 17 |
| **Escalas (Turnos)** | 4 (Amarela, Azul, Cinza, Verde) |
| **Arquivos Processados** | 18 |
| **Status Ativo** | ~95% |
| **Status Inativo** | ~5% |

---

## 2. Setores e Estrutura

### 2.1 Setores Encontrados

```
BAS (Base Dedicada de Gerenciamento de Risco)
├─ 4 Supervisores
├─ 28 Funcionários
└─ Escalas: Amarela, Azul, Cinza, Verde

CADASTRO
├─ 1 Supervisor: Larissa Cristina
├─ 9 Funcionários
└─ Escalas: Sem Escala Específica

CHECKLIST (Célula de Atendimento WhatsApp)
├─ 1 Supervisor: Carlos Eduardo
├─ 8 Funcionários
└─ Escalas: Sem Escala Específica

DISTRIBUIÇÃO
├─ 2 Supervisores: Amanda Carla, Thayssa de Almeida
├─ 26 Funcionários
└─ Escalas: Amarela, Azul

LOGÍSTICA
├─ 3 Supervisores: Geovana Meurer, Giulia Machado, Kayque Lima
├─ 32 Funcionários
└─ Escalas: Sem Escala

RECEPTIVO (Suporte)
├─ 1 Supervisor: Carlos Eduardo
├─ 8 Funcionários
└─ Escalas: Sem Escala

TRANSFERÊNCIA (Rastreamento/LP)
├─ 6 Supervisores: Adryan Celso, Ana Caroline, Gabryelle Marcilio, Gustavo Miralha, Gustavo Montanari, Rodrigo Barros
├─ 59 Funcionários
└─ Escalas: Amarela, Azul, Cinza, Verde

UTI (Gerenciamento de Risco)
├─ 4 Supervisores: Geniffer Maciel, Hervert Moreira, Josiane Ceccon, Tanara Vigentin
├─ 20 Funcionários
└─ Escalas: Amarela, Azul, Cinza, Verde

UTI (RJ) (Gerenciamento de Risco - Regional RJ)
├─ 4 Supervisores: Geniffer Maciel, Hervert Moreira, Josiane Ceccon, Tanara Vigentin
├─ 8 Funcionários
└─ Escalas: Amarela, Azul, Cinza, Verde
```

---

## 3. Supervisores e Hierarquia

### 3.1 Hierarquia por Supervisor

| Supervisor | Setores | Total de Funcionários |
|------------|---------|----------------------|
| Larissa Cristina | CADASTRO | 9 |
| Carlos Eduardo | CHECKLIST, RECEPTIVO | 16 |
| Amanda Carla | DISTRIBUIÇÃO | 12 |
| Thayssa de Almeida | DISTRIBUIÇÃO | 14 |
| Adryan Celso | TRANSFERÊNCIA | 10 |
| Ana Caroline | TRANSFERÊNCIA | 11 |
| Gabryelle Marcilio | TRANSFERÊNCIA | 11 |
| Gustavo Miralha | TRANSFERÊNCIA | 13 |
| Gustavo Montanari | CHECKLIST, TRANSFERÊNCIA | 10 |
| Rodrigo Barros | TRANSFERÊNCIA | 14 |
| Geniffer Maciel | BAS, UTI, UTI (RJ) | 18 |
| Hervert Moreira | BAS, UTI, UTI (RJ) | 16 |
| Josiane Ceccon | BAS, UTI, UTI (RJ) | 14 |
| Tanara Vigentin | BAS, UTI, UTI (RJ) | 16 |
| Geovana Meurer | LOGÍSTICA | 19 |
| Giulia Machado | LOGÍSTICA | 9 |
| Kayque Lima | LOGÍSTICA | 4 |

---

## 4. Escalas (Turnos)

As escalas encontradas nos arquivos:

```
Amarela
├─ 18 arquivos com esta escala
└─ 54 funcionários (27%)

Azul
├─ 18 arquivos com esta escala
└─ 48 funcionários (24%)

Cinza
├─ 18 arquivos com esta escala
└─ 43 funcionários (22%)

Verde
├─ 18 arquivos com esta escala
└─ 53 funcionários (27%)

Sem Escala (Setores não-escalados)
├─ CADASTRO, CHECKLIST, RECEPTIVO, LOGÍSTICA
└─ 25 funcionários (13%)
```

**Obs:** Alguns setores operacionais não seguem o modelo de 4 escalas (ex: CADASTRO, LOGÍSTICA).

---

## 5. Identificadores e Telefonia

### 5.1 Campos de Identificação

| Campo | Status | Observações |
|-------|--------|-------------|
| **Matrícula** | ✅ 100% | Identificador principal |
| **ID WEON** | ✅ 100% | Telefonia antiga (descontinuado) |
| **ID HUAWEI** | ✅ 95% | Telefonia atual (alguns faltando em setores específicos) |
| **Nome** | ✅ 100% | Completo com acentuação |

**Recomendação:** Usar **Matrícula + ID HUAWEI** como chave de vinculação com auditorias.

---

## 6. Status dos Funcionários

| Status | Total | Percentual |
|--------|-------|-----------|
| ATIVO | 188 | 94.9% |
| INATIVO | 10 | 5.1% |

**Inativos por Setor:**
- DISTRIBUIÇÃO: 2
- LOGÍSTICA: 3
- UTI: 3
- UTI (RJ): 2

---

## 7. Dados Estruturados no Banco

### Tabela: `colaboradores`

```sql
CREATE TABLE colaboradores (
    id INTEGER PRIMARY KEY,
    nome TEXT,
    matricula TEXT UNIQUE,
    supervisor TEXT,
    setor TEXT,
    escala TEXT,
    status TEXT,
    id_weon TEXT,
    id_huawei TEXT,
    atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    -- Telefonia
    id_telefonia TEXT,
    softphone_number TEXT,
    telefonia_account TEXT,
    organizacao_telefonia TEXT,
    tipo_agente TEXT,
    status_telefonia TEXT
)
```

**Total de Registros:** 183 únicos (alguns funcionários em múltiplas escalas)

---

## 8. Padrões Identificados

### 8.1 Estrutura de Supervisão

- **Supervisores de Gerenciamento de Risco (UTI/BAS):** 4 (gerenciam 3 setores cada)
- **Supervisores de Rastreamento (TRANSFERÊNCIA/LP):** 6 (distribuídos entre escalas)
- **Supervisores de Suporte (CADASTRO, CHECKLIST, RECEPTIVO):** 3
- **Supervisores de Logística:** 3 (distribuídos por especialização)

### 8.2 Concentração por Escala

**Distribuição mais equilibrada em:**
- Rastreamento (TRANSFERÊNCIA): distribuído em todas as 4 escalas
- UTI/BAS: distribuído em todas as 4 escalas

**Setores sem escala:**
- CADASTRO, CHECKLIST, RECEPTIVO, LOGÍSTICA (operação contínua)

### 8.3 Tamanho das Equipes por Supervisor

- **Maior:** Geovana Meurer (19 funcionários)
- **Menor:** Kayque Lima (4 funcionários)
- **Média:** ~11.6 funcionários por supervisor

---

## 9. Oportunidades e Recomendações

### 9.1 Estrutura de Dados

✅ **Concluído:**
- Importação de 198 funcionários
- Mapeamento de supervisores
- Normalização de setores e escalas
- Vinculação matrícula ↔ ramal Huawei

⚠️ **Próximo Passo:**
- [ ] Validar correspondência entre nomes em auditorias e funcionários importados
- [ ] Criar índices para performance em buscas
- [ ] Importar dados históricos de performance por supervisor

### 9.2 Auditorias Integradas

**Vincular operador com:**
1. Supervisor (para feedback direcionado)
2. Setor (para critérios específicos)
3. Escala (para análise temporal)
4. Matrícula + Ramal Huawei (para logs de sistema)

### 9.3 Análises Possíveis

```
Por Supervisor:
├─ Taxa de qualidade média
├─ Distribuição de alertas
├─ Evolução temporal
└─ Relatórios de feedback

Por Setor:
├─ Performance agregada
├─ Padrões de erro
├─ Benchmarking entre escalas
└─ Recomendações de treinamento

Por Escala:
├─ Qualidade por turno
├─ Taxa de erro por horário
├─ Impacto de fadiga
└─ Necessidade de reforço
```

---

## 10. Próximas Ações

### 10.1 Curto Prazo (1-2 semanas)

- [ ] Validar dados com RH (conferir inativos)
- [ ] Conectar auditorias com operadores
- [ ] Gerar primeiro relatório de performance

### 10.2 Médio Prazo (1 mês)

- [ ] Análise de tendências por supervisor
- [ ] Identificar gaps de treinamento
- [ ] Criar dashboard de KPIs

### 10.3 Longo Prazo (Trimestral)

- [ ] Previsão de quality issues
- [ ] Automação de alerts por padrão
- [ ] Integração com RH para planejamento

---

## 11. Anexos

### 11.1 Campos Adicionais Disponíveis no Banco

Além dos dados importados, a tabela `colaboradores` possui campos reservados para:
- `telefonia_account` - Conta de telefonia corporativa
- `organizacao_telefonia` - Departamento de telefonia
- `tipo_agente` - Classificação do tipo de agente
- `status_telefonia` - Status na central telefônica

Estes campos podem ser preenchidos posteriormente com informações de RH/TI.

---

## Conclusão

A estrutura de funcionários foi **successfully mapped** e está pronta para integração com o sistema de auditorias. Os próximos passos envolvem:

1. **Validação:** Conferir com RH e TI
2. **Integração:** Ligar auditorias aos operadores
3. **Análise:** Gerar insights de performance

**Contato:** Lucas (Desenvolvimento) | Data: 2026-03-10
