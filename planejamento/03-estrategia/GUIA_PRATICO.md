# Guia Prático - Usando os Dados de Funcionários

**Para:** Gestores, Supervisores, Equipe de RH, Desenvolvimento
**Data:** 2026-03-10

---

## 1. Acessando os Dados

### 1.1 Arquivo Excel Consolidado

📁 **Local:** `instrucoes/lista-de-funcionarios/FUNCIONARIOS_CONSOLIDADO.xlsx`

**Contém 4 abas:**

```
1. Funcionários (198 linhas)
   ├─ Nome completo
   ├─ Matrícula
   ├─ Ramal Huawei (para telefonia)
   ├─ Supervisor responsável
   ├─ Setor
   ├─ Escala (turno)
   ├─ Status (Ativo/Inativo)
   └─ Observações

2. Resumo Setor
   ├─ Total por setor
   ├─ Quantos ativos
   └─ Quantos inativos

3. Resumo Supervisor
   ├─ Qual supervisor
   ├─ Quantos funcionários
   ├─ Setores que gerencia
   └─ Quantos ativos

4. Resumo Escala
   ├─ Distribuição por turno
   ├─ Ativos por turno
   └─ Inativos por turno
```

---

## 2. Consultas Rápidas

### 2.1 Como Encontrar um Funcionário

**Situação:** Você tem o nome de um operador de uma auditoria

**Ação:**
1. Abra `FUNCIONARIOS_CONSOLIDADO.xlsx`
2. Vá para a aba "Funcionários"
3. Use `Ctrl+F` para procurar pelo nome
4. Encontrará: Matrícula, Ramal, Supervisor, Setor, Escala

---

### 2.2 Qual Supervisor de um Operador?

**Situação:** Precisa saber quem é o supervisor de um operador para dar feedback

**Ação:**
1. Abra `FUNCIONARIOS_CONSOLIDADO.xlsx`
2. Aba "Funcionários", coluna "Supervisor"
3. Use `Ctrl+F` para procurar o nome do operador
4. Veja quem é o supervisor na linha dele

**Exemplo:**
```
Ana Caroline Alves dos Santos
├─ Supervisor: Ana Caroline [confira]
├─ Setor: Transferência
└─ Escala: Verde
```

---

### 2.3 Quantos Operadores tem um Supervisor?

**Situação:** Saber o tamanho da equipe de um supervisor

**Ação:**
1. Abra `FUNCIONARIOS_CONSOLIDADO.xlsx`
2. Vá para "Resumo Supervisor"
3. Procure o supervisor

**Exemplo:**
```
Geniffer Maciel
├─ Total Funcionários: 18
├─ Setores: BAS, UTI, UTI (RJ)
├─ Ativos: 17
└─ Inativos: 1
```

---

### 2.4 Qual a Distribuição de uma Escala?

**Situação:** Saber quantos operadores trabalham na escala Amarela (ou outra)

**Ação:**
1. Abra `FUNCIONARIOS_CONSOLIDADO.xlsx`
2. Vá para "Resumo Escala"
3. Veja a distribuição

**Exemplo:**
```
Amarela
├─ Total: 54 funcionários (27%)
├─ Ativos: 53
└─ Inativos: 1
```

---

## 3. Banco de Dados

### 3.1 Acessando via SQL

**Tabela:** `colaboradores`

**Campos principais:**
```sql
SELECT
    nome,                    -- Nome completo
    matricula,              -- Matrícula (ID único)
    id_huawei,              -- Ramal Huawei (telefonia)
    supervisor,             -- Supervisor
    setor,                  -- Setor
    escala,                 -- Amarela, Azul, Cinza, Verde
    status,                 -- ATIVO ou INATIVO
    tipo_escala             -- Tipo de turno/operação
FROM colaboradores;
```

---

### 3.2 Queries Úteis

#### Query 1: Encontrar um Operador

```sql
SELECT *
FROM colaboradores
WHERE LOWER(nome) LIKE '%ana%'
AND setor = 'TRANSFERENCIA';
```

#### Query 2: Listar Equipe de um Supervisor

```sql
SELECT nome, matricula, setor, escala, status
FROM colaboradores
WHERE supervisor = 'Geniffer Maciel'
ORDER BY setor, nome;
```

#### Query 3: Contar Operadores por Setor

```sql
SELECT setor, COUNT(*) as total,
       SUM(CASE WHEN status = 'ATIVO' THEN 1 ELSE 0 END) as ativos
FROM colaboradores
GROUP BY setor
ORDER BY total DESC;
```

#### Query 4: Supervisores e Seus KPIs

```sql
SELECT supervisor,
       COUNT(*) as total_operadores,
       COUNT(DISTINCT setor) as setores_gerenciados,
       SUM(CASE WHEN status = 'ATIVO' THEN 1 ELSE 0 END) as ativos,
       ROUND(100.0 * SUM(CASE WHEN status = 'ATIVO' THEN 1 ELSE 0 END) / COUNT(*), 1) as percentual_ativo
FROM colaboradores
GROUP BY supervisor
ORDER BY total_operadores DESC;
```

#### Query 5: Operadores Inativos (Revisar com RH)

```sql
SELECT nome, matricula, supervisor, setor, escala
FROM colaboradores
WHERE status = 'INATIVO'
ORDER BY supervisor, setor;
```

---

## 4. Análises por Perfil

### 4.1 Para Gestão/Coordenação

**Perguntas que pode fazer:**

1. **Qual é o tamanho da equipe por setor?**
   - Vá para: Resumo Setor
   - Encontrará: Totais por setor

2. **Quem são meus supervisores?**
   - Vá para: Resumo Supervisor
   - Encontrará: 17 supervisores com teams

3. **Como está distribuído por turnos?**
   - Vá para: Resumo Escala
   - Encontrará: Distribuição Amarela/Azul/Cinza/Verde

---

### 4.2 Para RH

**Perguntas que pode fazer:**

1. **Quantos estão inativos?**
   - Query: `SELECT COUNT(*) FROM colaboradores WHERE status = 'INATIVO'`
   - Resultado: 10 inativos

2. **Qual setor tem mais inativos?**
   - Query (veja seção 3.2, Query 3)
   - Resultado: Identificar setor com maior taxa

3. **Qual supervisor tem maior rotatividade?**
   - Cruzar com dados históricos de RH

---

### 4.3 Para Supervisores

**Use para:**

✅ Identificar sua equipe
✅ Conferir ramais Huawei para contato
✅ Distribuir de equipes por escala
✅ Preparar para avaliações

**Exemplo prático:**

Supervisor: Geniffer Maciel

```
Minha equipe:
├─ Escala Amarela (5 operadores)
├─ Escala Azul (4 operadores)
├─ Escala Cinza (5 operadores)
└─ Escala Verde (4 operadores)

Total: 18 operadores
Inativos: 1 (conferir com RH)
```

---

### 4.4 Para Desenvolvimento/TI

**Dados disponíveis:**

- [x] 198 funcionários estruturados
- [x] 17 supervisores mapeados
- [x] 9 setores normalizados
- [x] 4 escalas identificadas
- [x] Matrícula ↔ Ramal Huawei (95% coverage)

**Próximos passos:**

- [ ] Implementar vinculação com auditorias
- [ ] Criar API de consulta
- [ ] Dashboard de performance

---

## 5. Dicas e Boas Práticas

### 5.1 Dados Faltantes

**Campo:** ID HUAWEI
**Afetados:** ~5% dos registros (alguns setores)

**O que fazer:**
- [ ] Verificar com TI
- [ ] Solicitar à Telefonia da empresa
- [ ] Usar Matrícula como fallback

---

### 5.2 Nomes Inconsistentes

Alguns nomes podem ter variações (ex: "Ana Carolina" vs "Ana C. Costa")

**Solução:**
- Use **matrícula** como identificador único
- Use **ramal Huawei** como identificador de telefonia

---

### 5.3 Setores Especiais

**Alguns setores não têm "escala":**
- CADASTRO
- LOGÍSTICA
- CHECKLIST
- RECEPTIVO

Estes operam continuamente, não em turnos.

---

## 6. Troubleshooting

### Problema: Não encontro um operador

**Checklist:**
1. Conferiu a soletração do nome?
2. Tentou procurar por matrícula em vez de nome?
3. Conferiu se está ativo ou inativo?
4. O funcionário pode ser novo (não cadastrado ainda)?

**Solução:**
- Contacte RH
- Forneça: Nome + Data de Admissão + Supervisor

---

### Problema: O ramal Huawei está faltando

**Afeta:** ~5% dos registros

**Ação:**
- [ ] Contactar Telefonia
- [ ] Usar Matrícula + Nome para identificação
- [ ] Atualizar base conforme dados chegam

---

### Problema: Supervisor não está listado

**Causas possíveis:**
- Supervisor é novo (não aparece na base)
- Escrita do nome diferente

**Solução:**
- Contactar RH para validação
- Usar mesma escrita que aparece no Excel

---

## 7. Casos de Uso

### Caso 1: Validar Operador em Auditoria

**Situação:**
Sistema de auditoria tem operador "JOAO SILVA" em uma gravação

**Ação:**
1. Procure no Excel por "JOAO SILVA"
2. Se encontrar: Capture Matrícula + Ramal
3. Se não encontrar: Anote o nome e contacte RH

**Resultado:**
Registro validado e vinculado à auditoria

---

### Caso 2: Dar Feedback a um Operador

**Situação:**
Precisa de contato de um operador para feedback

**Ação:**
1. Abra `FUNCIONARIOS_CONSOLIDADO.xlsx`
2. Procure o nome do operador
3. Note o supervisor
4. Contacte o supervisor com o feedback

**Resultado:**
Feedback direcionado ao supervisor para ação

---

### Caso 3: Analisar Performance por Supervisor

**Situação:**
Quer saber a performance média da equipe de um supervisor

**Ação:**
1. Abra relatórios de auditoria (quando implementados)
2. Filtre por supervisor
3. Calcule média de scores
4. Identifique padrões

**Resultado:**
Insight sobre força/fraqueza da equipe

---

## 8. Próximas Capacidades

**Em desenvolvimento:**

- [ ] **Dashboard Interativo:** Visualizar performance por supervisor/setor/escala
- [ ] **API de Consulta:** Integração com sistemas de terceiros
- [ ] **Alertas Automáticos:** Notificar supervisor de padrões de erro
- [ ] **Recomendações:** Sugestões de treinamento por operador

---

## 9. Contato e Suporte

**Dúvidas sobre dados:**
- Lucas (Desenvolvimento)
- Email: lucas@nstech.com

**Dúvidas sobre operadores:**
- RH
- Email: rh@nstech.com

**Dúvidas sobre ramais Huawei:**
- TI / Telefonia
- Ramal: 2000

---

## Checklist Rápido

- [ ] Identifique seu supervisor
- [ ] Abra `FUNCIONARIOS_CONSOLIDADO.xlsx`
- [ ] Procure por seu nome
- [ ] Anote sua matrícula
- [ ] Anote seu ramal Huawei
- [ ] Confira seu setor e escala
- [ ] Valide com RH

---

**Última atualização:** 2026-03-10
**Status:** ✅ Pronto para usar
