# Relatorio tecnico - Modulo Fechamento

Data: 2026-04-20

## Fontes verificadas

- `rag/FECHAMENTO DAS AUDITORIAS.docx` extraido como texto.
- `auditoria_criterios/fechamento/03 - FECHAMENTO PLANEJAMENTO.xlsx` lido com `openpyxl`.
- `backend/core/fechamento_service.py`
- `backend/core/export_fechamento.py`
- `backend/routers/fechamento.py`
- `src/features/fechamento/components/FechamentoPage.tsx`
- `backend/db/runtime_schema.py`
- `backend/db/migration_steps/m20260419_001_add_fechamento_cadeia_contatos.py`
- `backend/db/migration_steps/m20260419_002_add_fechamento_overrides.py`

Observacao Neon: o plugin Neon Postgres foi acionado, mas a ferramenta MCP retornou `shared_projects: []`. Nao foi possivel inspecionar o schema remoto via MCP nesta sessao. A reproducao do erro 500 foi local e ocorreu antes da query chegar ao PostgreSQL.

## Correcao aplicada agora

O endpoint `GET /api/fechamento/dados?mes=4&ano=2026` falhava com:

```text
IndexError: tuple index out of range
```

Causa: a query usa placeholders `%s` do psycopg2 e tambem tinha literais `LIKE '%CHECKLIST%'`. Para psycopg2, percentuais literais dentro da query parametrizada precisam ser escapados como `%%`.

Alteracao:

```sql
AND UPPER(c.setor) NOT LIKE '%%CHECKLIST%%'
AND UPPER(c.escala) NOT LIKE '%%CHECKLIST%%'
```

Resultado local apos a correcao:

```text
GET logico de abril/2026: ok, 470 linhas retornadas
```

## Nota de alinhamento - UTI/RJ

Foi confirmado apos extrair as imagens do DOCX que a orientacao inicial sobre UTI/RJ estava incompleta: UTI/RJ faz parte da mesma tabela de fechamento/cadeia de contatos, mas tem criterios diferentes de pontuacao.

A regra correta e:

- UTI usa notas com peso 1 para motorista, PA, cliente e policia.
- UTI/RJ usa notas com peso 1.5 para motorista, cliente e policia, e peso 1 para PA.
- Depois de somar as notas, UTI e UTI/RJ usam a mesma formula oficial da planilha para `PROCESSO - CADEIA DE CONTATOS`.

Formula oficial de `PROCESSO - CADEIA DE CONTATOS` extraida da imagem do DOCX:

- soma = 4 ou soma > 4: `110%`
- soma = 3: `100%`
- soma = 2 ou soma = 2.5: `90%`
- soma = 1: `80%`
- demais casos: `70%`

Formula oficial de `FINAL` extraida da imagem do DOCX:

- `STATUS = INATIVO`: `Adeus`
- `PROCESSO = 70%`: `-4%`
- `PROCESSO > 80%` e `< 100%`: `-2%`
- `PROCESSO = 100%`: `2%`
- `PROCESSO > 100%`: `4%`
- demais casos: vazio

Importante para revisores futuros: nao tratar UTI/RJ como uma tabela/export separado nem reintroduzir escala percentual propria proporcional ate 5.5. UTI/RJ permanece na tabela de cadeia; o que muda sao os criterios/pesos das notas. O teto 5.5 vem desses pesos, mas a formula de conversao para percentual continua sendo a mesma do Excel oficial.

## Como o modulo funciona hoje

### 1. Entrada pela interface

Arquivo: `src/features/fechamento/components/FechamentoPage.tsx`

A tela mantem estado local para:

- mes selecionado;
- ano selecionado;
- linhas retornadas pelo backend;
- estados de loading/salvamento/exportacao.

Chamadas feitas pela tela:

- `GET /api/fechamento/dados?mes={mes}&ano={ano}` carrega as linhas.
- `POST /api/fechamento/dados?mes={mes}&ano={ano}` salva overrides manuais.
- `GET /api/fechamento/exportar?mes={mes}&ano={ano}` baixa o Excel.

A tela mostra colunas auxiliares de notas UTI (`nota_mot`, `nota_pa`, `nota_cli`, `nota_policia`) que nao entram no Excel final; elas alimentam `processo` e `final`.

### 2. Rotas FastAPI

Arquivo: `backend/routers/fechamento.py`

Todas as rotas usam `require_admin`.

- `listar_dados`: abre conexao, chama `get_fechamento_rows`, fecha conexao.
- `salvar_dados`: valida payload com `FechamentoRowInput`, chama `save_fechamento_overrides`, faz rollback em erro.
- `exportar_fechamento`: chama `generate_fechamento_excel`.

### 3. Montagem das linhas

Arquivo: `backend/core/fechamento_service.py`

Fluxo de `get_fechamento_rows`:

1. Calcula inicio/fim do mes (`YYYY-MM-01` ate primeiro dia do mes seguinte).
2. Cria CTE `media_mensal` com media das auditorias aprovadas.
3. Usa `COALESCE(audit_date, timestamp)` para escolher a data da auditoria.
4. Junta `colaboradores` com `fechamento_cadeia_contatos`.
5. Aplica overrides manuais quando existem.
6. Remove operadores de Checklist pelo SQL atual.
7. Ordena por supervisor e nome.
8. Reinicia o ID sequencial quando o supervisor muda.
9. Define se a media vai para `operacional` ou `telefonica`.
10. Calcula `desempenho`, `processo`, `final` e `huawei`.

### 4. Persistencia de overrides

Tabela: `fechamento_cadeia_contatos`

Chave funcional:

- `colaborador_id`
- `mes`
- `ano`

Regra de persistencia:

- salva notas UTI sempre;
- salva campos de texto como override somente quando diferem da linha base recalculada.

Isso evita congelar dados que continuam vindo de `colaboradores` ou `audits`.

### 5. Exportacao Excel

Arquivo: `backend/core/export_fechamento.py`

O exportador gera 14 colunas:

1. ID
2. MES
3. MATRICULA
4. COLABORADOR
5. OPERACIONAL
6. TELEFONICA
7. DESEMPENHO
8. STATUS
9. TURNO / OPERACAO
10. SUPERVISOR
11. SETOR
12. PROCESSO - CADEIA DE CONTATOS
13. FINAL
14. HUAWEI

O arquivo aplica preenchimento laranja e bordas no cabecalho. Operacional e Telefonica sao convertidos para numero quando possivel.

## Verificacao do relatorio anterior

### Pontos corretos

- As 14 colunas do export atual batem com o texto do DOCX.
- O ID sequencial por supervisor existe no servico.
- O mes em tres letras existe (`Jan`, `Fev`, etc.).
- O desempenho usa corte em 7.9.
- Huawei fica vazio para Mondelez.
- Os overrides manuais sao persistidos somente quando diferem da base.
- A diferenciacao UTI vs UTI/RJ realmente nao esta implementada.
- Os inputs de notas realmente permitem maximo 1.5 para todas as quatro notas, o que nao respeita PA maximo 1.
- A regra completa de `FINAL` nao esta confirmada pelo texto extraido do DOCX.
- A separacao de setores receptivos esta fragil: `celula_atendimento` nao cobre todas as variacoes como `celula`, `celula`, `célula` ou `RECEPTIVO`.
- O Excel poderia melhorar freeze panes, larguras e formatos percentuais.

### Pontos que precisam de ajuste no relatorio anterior

1. Checklist como exclusao obrigatoria nao foi confirmado no texto extraido do DOCX.
   - O DOCX menciona Checklist como receptivo e tambem na lista de Turno/Operacao.
   - A planilha de referencia `03 - FECHAMENTO PLANEJAMENTO.xlsx` contem linhas Checklist.
   - O codigo atual exclui Checklist, mas essa regra precisa ser confirmada como decisao de negocio atual, nao como algo comprovado pelo DOCX extraido.

2. A planilha de referencia tem uma coluna extra `WEON` na coluna O.
   - O DOCX exige 14 colunas ate Huawei.
   - O export atual segue o DOCX, nao a coluna extra da planilha.
   - Se Planejamento espera `WEON`, isso precisa ser confirmado separadamente.

3. O item F4 do relatorio anterior e valido apenas para edicoes nao salvas.
   - Hoje o export sempre le o estado persistido no banco.
   - Se o usuario editar e baixar sem salvar, o Excel sai desatualizado.
   - Se o usuario salvar antes, o fluxo esta coerente.

## Regras confirmadas pelo DOCX/texto

- Operacional: media de ligacoes efetuadas.
- Telefonica: media de ligacoes receptivas.
- Desempenho: BOM se nota maior que 7.9, RUIM abaixo de 7.9.
- Processo: preenchimento manual para UTI e UTI/RJ.
- UTI: motorista 1, PA 1, cliente 1, policia 1.
- UTI/RJ: motorista 1.5, PA 1, cliente 1.5, policia 1.5.
- Huawei vazio para Mondelez.

## Regras ainda pendentes de confirmacao

1. Se Checklist deve ser excluido ou mantido no fechamento.
2. Se a coluna extra `WEON` da planilha de referencia deve entrar no export oficial.

## Recomendacao de proximas alteracoes

Prioridade 1:

- Corrigir UTI vs UTI/RJ no backend e frontend.
- Confirmar Checklist antes de manter a exclusao.

Prioridade 2:

- Normalizar setores com remocao de acentos e aliases.
- Converter Processo/Final para numeros percentuais no Excel.
- Ajustar layout do Excel com freeze panes e larguras.

Prioridade 3:

- Transformar Turno/Operacao e Setor em selects canonicos.
- Impedir exportacao quando houver edicoes locais nao salvas, ou salvar antes de exportar.
