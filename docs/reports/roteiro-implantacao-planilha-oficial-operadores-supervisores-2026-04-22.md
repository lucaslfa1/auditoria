# Roteiro de Implantação: Carga Oficial de Operadores e Supervisores

Data: 2026-04-22

## Objetivo

Aplicar a planilha `docs/Lista - Operadores e Supervisores.xlsx` como fonte oficial dos cadastros de operadores e supervisores, sem alterar a estrutura do banco de dados.

## Premissas homologadas

- a estrutura do banco permanece a mesma;
- a planilha atual substitui o cadastro anterior como fonte oficial;
- registros antigos fora da planilha deixam de ser oficiais;
- os campos prioritários da carga são `matricula`, `Código Huawei`, `Operadores`, `Setor` e `Função`;
- a coluna `Função` define se a linha é `Operador` ou `Supervisor`;
- na distribuição, a supervisão oficial por escala ficou assim:
  - `Amanda Carla` -> azul
  - `Thayssa de Almeida` -> amarela
  - `Bruna Vieira` -> verde
  - `Carina Uhlmann` -> cinza

## Fora da carga automática

Os nomes abaixo devem ficar fora da automação e entrar por cadastro manual no sistema:

- `BRUNA CARDOSO MONTE`
- `CINTIA CRISTINA DOMINGOS RIBEIRO`
- `GABRIELA DIEGO BUSH`
- `NATALI NEIVA DA SILVA`
- `JEAN CARLOS CONTANTINO MIRANDA`

## Sequência de execução

1. Congelar a implantação durante a janela de atualização.
2. Gerar backup completo de `colaboradores` e `users` antes de qualquer alteração.
3. Gerar uma base intermediária a partir da planilha oficial, separando supervisores e operadores.
4. Excluir da base intermediária os 5 nomes definidos para cadastro manual.
5. Atualizar os supervisores oficiais em `users`, mantendo login e permissões já existentes quando houver correspondência.
6. Atualizar os operadores existentes em `colaboradores` por `matricula`, com fallback por `Código Huawei` e nome normalizado.
7. Inserir os operadores oficiais novos que não existirem no banco atual e que não estejam na lista manual.
8. Inativar os cadastros antigos que não aparecem mais na planilha oficial.
9. Reativar operadores oficiais que hoje estejam inativos ou fora de auditoria.
10. Validar supervisor, setor e escala por amostragem, com foco em `Distribuição`, `Logística`, `Rastreamento`, `UTI` e `BAS`.
11. Solicitar o cadastro manual dos 5 nomes excluídos da automação.
12. Executar a validação final no sistema e registrar o aceite.

## Validações obrigatórias

- total de operadores oficiais carregados no banco;
- total de supervisores oficiais com conta ativa em `users`;
- ausência de operador oficial marcado como legado;
- conferência dos vínculos supervisor -> operador em `Distribuição`;
- conferência dos vínculos supervisor -> operador em `Logística` após homologação da regra final;
- conferência manual dos 5 cadastros excluídos da automação.

## Critério de aceite

A implantação só deve ser dada como concluída quando:

- a planilha estiver refletida em `colaboradores` e `users`;
- os registros antigos tiverem sido retirados da base oficial;
- os 5 cadastros manuais tiverem sido inseridos no sistema;
- os relatórios e filtros do sistema retornarem supervisor, setor e escala conforme a regra oficial.

## Rollback

Se a validação falhar:

1. restaurar o backup de `colaboradores`;
2. restaurar o backup de `users`;
3. revalidar as contagens por supervisor, setor e escala;
4. cancelar o aceite e registrar a inconsistência encontrada.
