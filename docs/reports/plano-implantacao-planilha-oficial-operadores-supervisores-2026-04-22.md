# Plano de Implantação: Planilha Oficial de Operadores e Supervisores

Data: 2026-04-22

## Objetivo

Substituir a base oficial de operadores e supervisores do projeto Auditoria pelos dados da planilha `docs/Lista - Operadores e Supervisores.xlsx`, preservando a estrutura atual do banco de dados.

Escopo confirmado:

- atualizar dados, não alterar o schema;
- alinhar `colaboradores` com a planilha oficial;
- sincronizar os cadastros de supervisores em `users` para manter login, filtros e permissões coerentes;
- preservar histórico operacional e integridade dos vínculos já usados por auditorias e filas.

## Resumo executivo

O banco atual está preparado para absorver a planilha oficial sem mudança estrutural, mas a implantação não deve ser executada em carga direta ainda. A análise encontrou quatro grupos de risco que precisam ser tratados no plano:

1. A planilha possui blocos em que vários supervisores aparecem antes de uma única lista de operadores, sem indicar qual operador pertence a qual supervisor.
2. A própria planilha contém duplicidades de matrícula e de Código Huawei em alguns operadores.
3. Parte da planilha está sem matrícula e/ou sem Código Huawei.
4. O projeto atual usa nomes resumidos para vários supervisores; a planilha usa nomes completos.

Conclusão operacional:

- o alinhamento pode ser feito sem tocar no schema;
- a estratégia correta é migrar por atualização em linha dos registros atuais, não por recriação cega;
- a implantação deve excluir da carga automática 5 cadastros que serão feitos manualmente no sistema.

Cadastros manuais definidos pelo usuário:

- `BRUNA CARDOSO MONTE`
- `CINTIA CRISTINA DOMINGOS RIBEIRO`
- `GABRIELA DIEGO BUSH`
- `NATALI NEIVA DA SILVA`
- `JEAN CARLOS CONTANTINO MIRANDA`

## Fonte oficial analisada

Arquivo:

- `docs/Lista - Operadores e Supervisores.xlsx`

Leitura estrutural:

- 1 aba: `Planilha1`
- 245 linhas úteis
- 226 operadores
- 19 supervisores

Campos presentes na planilha:

- `Matrícula`
- `Código Huawei`
- `Operadores`
- `Setor`
- `Função`

Campos que o sistema usa hoje e não existem na planilha:

- `escala` em formato já normalizado para lookup interno
- `status`
- `auditavel`
- `id_weon`
- `id_telefonia`
- `softphone_number`
- `telefonia_account`
- `organizacao_telefonia`
- `tipo_agente`
- `status_telefonia`
- credenciais/autenticação de supervisores

Implicação:

- a planilha deve virar fonte oficial para equipe, setor e supervisão;
- os campos ausentes precisam ser preservados do cadastro atual ou derivados por regra de implantação;
- a implantação não pode simplesmente apagar e recriar tudo.

## Estado atual do banco

Leitura em modo somente consulta:

- `colaboradores`: 406 registros
- `users`: 12 registros
- `users` com `role='supervisor'`: 9 registros
- supervisores distintos referenciados em `colaboradores`: 21

Contratos ativos no código:

- `colaboradores` é a base operacional usada por lookup, filtros, automação e vínculo com auditorias.
- `users` contém o cadastro de autenticação dos supervisores.
- o portal do supervisor e relatórios recuperam `supervisor` e `escala` por `JOIN` em `colaboradores`.
- várias consultas dependem de atualização em linha para preservar `id`, `matricula`, `id_huawei` e vínculos históricos.

## Diagnóstico de aderência entre planilha e banco atual

### Cobertura de match com a base atual

Cruzamento por prioridade:

1. `matricula`
2. `id_huawei`
3. nome normalizado

Resultado:

- 186 operadores da planilha já existem no banco por `matricula`
- 12 operadores da planilha já existem no banco por nome normalizado
- 28 operadores da planilha não foram encontrados na base atual
- 213 registros atuais de `colaboradores` não aparecem na planilha oficial
- 8 operadores oficiais hoje estão `INATIVO` ou com `auditavel=0` e seriam reativados se a planilha prevalecer
- dos 28 não encontrados, 5 já foram direcionados para cadastro manual e não entram na carga automática inicial

Leitura prática:

- existe base suficiente para migração incremental segura;
- também existe volume relevante de desligamento/inativação de cadastros hoje ativos;
- exclusão física não é recomendada, porque quebraria histórico e auditorias antigas.

### Supervisores

Situação encontrada:

- planilha oficial: 19 supervisores
- contas supervisor atuais: 9

Boa parte da diferença é só nomenclatura, por exemplo:

- `Larissa Cristina` vs `LARISSA CRISTINA PASQUETTI FONSECA`
- `Carlos Eduardo` vs `CARLOS EDUARDO PEREIRA`
- `Adryan Celso` vs `ADRYAN CELSO MARIA`
- `Geovana Meurer` vs `GEOVANA MEURER DOS SANTOS`
- `Richard Marques` vs `RICHARD WILLIAN AMORIM MARQUES`
- `Giulia Machado` vs `GIULIA MACHADO DE OLIVEIRA`
- `Gustavo Miralha` vs `GUSTAVO FARIA MIRALHA`
- `Gabryelle Marcilio` vs `GABRYELLE MARCILIO SOARES`

Mas também há casos que parecem realmente novos ou fora da planilha atual:

- `Carina Uhlmann`
- `Thiago Alexandre Machado`
- `Kayque Lima Amadeu`

E há supervisores hoje na base que não aparecem como oficiais na planilha:

- `Rodrigo Barros`
- `Douglas de Aguiar`
- `Gustavo Montanari`
- `Lucas Rafael`

### Blocos ambíguos na planilha

Os dois blocos abaixo impedem uma atribuição determinística supervisor -> operador usando apenas a planilha:

1. Distribuição
- 4 supervisores consecutivos:
  - `AMANDA CARLA`
  - `THAYSSA DE ALMEIDA`
  - `BRUNA VIEIRA`
  - `CARINA UHLMANN`
- depois disso, 45 operadores em uma única lista
- o usuário homologou os supervisores oficiais da distribuição por escala:
  - `Amanda Carla` -> escala azul
  - `Thayssa de Almeida` -> escala amarela
  - `Bruna Vieira` -> escala verde
  - `Carina Uhlmann` -> escala cinza
- 5 operadores deste bloco foram explicitamente retirados da automação e serão cadastrados manualmente

2. Logística
- 2 supervisores consecutivos:
  - `GEOVANA MEURER DOS SANTOS`
  - `RICHARD WILLIAN AMORIM MARQUES`
- depois disso, 40 operadores em uma única lista
- a planilha não informa a partição da equipe entre os dois supervisores

Implicação:

- a distribuição já tem regra oficial de supervisão por escala, mas a logística ainda exige homologação complementar;
- os 5 operadores removidos da automação não bloqueiam a carga oficial do restante.

### Duplicidades internas da planilha

Duplicidades por matrícula:

- `11070` em `Distribuição` e `UTI - AZUL`
- `11077` em `Distribuição` e `UTI - AZUL`
- `11259` em `Distribuição` e `UTI - AZUL`
- `11562` em `Distribuição` e `RASTREAMENTO - AZUL`
- `11082` em `Distribuição` e `UTI - VERDE`
- `4235` com dois nomes diferentes em `Fênix`
- `11353` em `Logística` e `Unilever`
- `11349` em `RASTREAMENTO - AMARELA` e `UTI - AZUL - COMBO`

Duplicidades por Código Huawei:

- `2384`
- `2505` usado por mais de um operador
- `2433`
- `2419`
- `2517`

Implicação:

- a carga oficial precisa de regra de desempate antes de gravar supervisor/setor/escala por chave;
- o caso `4235` é crítico, porque uma mesma matrícula está associada a dois nomes diferentes.

### Identificadores ausentes

Na planilha:

- 3 operadores sem matrícula
- 10 operadores sem Código Huawei

Isso não impede a implantação, mas obriga fallback por nome normalizado e aumenta risco de falso positivo.

## Tabelas e cadastros impactados

### `colaboradores`

Será a tabela principal da implantação.

Campos que devem ser tratados como oficiais pela planilha:

- `nome`
- `matricula`
- `id_huawei`
- `supervisor`
- `setor`
- `escala` derivada

Campos que devem ser preservados quando existirem no cadastro atual:

- `id_weon`
- `id_telefonia`
- `softphone_number`
- `telefonia_account`
- `organizacao_telefonia`
- `tipo_agente`
- `status_telefonia`

Campos que devem ser derivados na implantação:

- `status = 'ATIVO'` para operadores confirmados pela planilha
- `auditavel = 1` para operadores oficiais, salvo exceção homologada

Regra para registros atuais fora da planilha:

- não excluir fisicamente;
- marcar como `INATIVO` e `auditavel = 0`;
- preservar `id` e histórico.

### `users`

Será sincronizada apenas para supervisores.

Tratamento recomendado:

- manter contas existentes quando o supervisor atual só mudou de nomenclatura;
- atualizar `supervisor_name` para o nome oficial completo da planilha;
- criar contas para supervisores realmente novos;
- contas de supervisores não oficiais devem ser revisadas depois da homologação, não removidas no primeiro corte.

### `audits` e demais tabelas históricas

Não precisam de alteração estrutural nem migração de massa.

Cuidados:

- preservar o `id` do `colaborador` sempre que houver match para não quebrar `JOIN` histórico;
- evitar recriação de operador quando for possível atualizar o registro existente;
- validar consultas do portal de supervisor e exportações após a sincronização.

## Estratégia de implantação recomendada

### Fase 1: preparação

1. Gerar snapshot antes da mudança:
- export completo de `colaboradores`
- export completo de `users`
- relatório de contagens por supervisor/setor/escala

2. Normalizar a planilha em dataset intermediário:
- separar linhas `Supervisor` e `Operador`
- padronizar acentuação e caixa para comparação
- converter matrícula e Huawei para string

3. Resolver pendências antes da carga:
- distribuição individual dos blocos ambíguos
- duplicidades internas
- decisão sobre operadores sem identificador

### Fase 2: carga controlada em staging lógico

1. Gerar dataset consolidado com estas regras:
- match por `matricula`
- fallback por `id_huawei`
- fallback por nome normalizado

2. Derivar `setor` e `escala` para o contrato interno:
- `Cadastro` -> `setor=cadastro`
- `Checklist` -> `setor=checklist`
- `Célula` -> `setor=celula_atendimento`
- `Distribuição` -> `setor=distribuicao`
- `Fênix` -> `setor=fenix`
- `Logística` -> `setor=logistica`
- `Mondelez` -> `setor=mondelez`
- `Unilever` -> `setor=logistica_unilever`
- `RASTREAMENTO - AMARELA/AZUL/CINZA/VERDE` -> `setor=transferencia`, `escala=Amarela/Azul/Cinza/Verde`
- `UTI/BAS - AMARELA/AZUL/CINZA/VERDE` -> `escala=Amarela/Azul/Cinza/Verde`, com subtipo da linha do operador preservado para mapear `setor=uti` ou `setor=bas`

3. Para blocos sem escala explícita na planilha:
- manter escala derivada do bloco quando inequívoca;
- quando a planilha só indica área e não turno/cor, preservar a escala atual até homologação contrária.

4. Operadores excluídos da automação:
- não inserir nem atualizar automaticamente os 5 nomes definidos para cadastro manual;
- validar no pós-carga se o cadastro manual foi concluído com matrícula, Código Huawei, setor, função e supervisor corretos.

### Fase 3: atualização de `colaboradores`

1. Atualizar em linha os operadores com match existente.
2. Inserir operadores novos encontrados apenas na planilha.
3. Inativar registros atuais ausentes da planilha oficial.
4. Reativar operadores oficiais hoje inativos.

Princípio operacional:

- atualizar em linha quando houver match;
- evitar trocar `id` de registro já existente;
- não fazer `truncate` e recarga total.

### Fase 4: sincronização de supervisores em `users`

1. Atualizar nomes oficiais dos supervisores já existentes.
2. Criar contas para supervisores novos.
3. Validar que todos os supervisores oficiais tenham login.
4. Revisar contas fora da planilha somente após homologação.

### Fase 5: validação pós-carga

Validar no banco:

- total de operadores ativos igual ao dataset oficial homologado
- total de supervisores oficiais sincronizado
- ausência de operadores oficiais com `auditavel=0`, salvo exceção aprovada

Validar no sistema:

- lookup de operadores por setor
- filtros de supervisor e escala
- portal de supervisor
- amostra de auditorias históricas com `JOIN` correto em `colaboradores`

## Pendências obrigatórias antes da execução

### Pendência 1: regra final de supervisor por operador em logística

Necessária para:

- `Logística`

Status:

- `Distribuição`: resolvida pelo usuário via supervisor oficial por escala
- `Logística`: ainda exige fechamento da regra de partição supervisor -> operador

### Pendência 2: resolução de duplicidades da própria planilha

Casos mínimos que precisam de decisão:

- matrícula `4235` com dois nomes
- Huawei `2505` associado a operadores diferentes
- operadores repetidos em setores distintos

### Pendência 3: política para operadores ausentes no banco atual

Há 28 operadores oficiais não encontrados na base atual.

Decisão necessária:

- inserir automaticamente os 23 casos elegíveis para carga
- manter os 5 casos definidos pelo usuário como cadastro manual fora da automação inicial

### Pendência 4: política para supervisores fora da planilha

Decidir se no corte inicial será feito:

- apenas desuso funcional;
- remoção do vínculo dos operadores;
- ou exclusão/desativação das contas de acesso.

## Plano de rollback

Rollback recomendado:

1. restaurar snapshot de `colaboradores`;
2. restaurar snapshot de `users`;
3. revalidar contagens por supervisor/setor/escala;
4. reexecutar os testes de lookup e portal supervisor.

Regra de segurança:

- nenhuma exclusão física no primeiro corte;
- rollback deve ser por restauração dos registros anteriores, não por tentativa manual.

## Recomendação final

Status recomendado para hoje:

- pronto para implantação técnica controlada após fechamento da regra de logística.

Minha recomendação prática é executar em duas etapas:

1. fechar a regra de supervisor para `Logística` e manter os 5 operadores separados para cadastro manual;
2. aplicar a carga oficial com atualização incremental de `colaboradores` e sincronização de `users`.

Assim, a planilha passa a ser a fonte oficial do projeto sem alterar a estrutura do banco e sem sacrificar histórico, autenticação ou consultas já em produção.
