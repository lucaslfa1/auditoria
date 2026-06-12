# Relatório de Migração de Banco de Dados (Neon)
**Data:** 13 de Maio de 2026

## Resumo do Problema
O projeto `auditoria-nstech` original hospedado no Neon atingiu 100% da cota mensal de transferência de rede (5 GB). Isso causou a suspensão do banco de dados, bloqueando todas as operações do sistema.

## Solução Adotada
Para restabelecer o funcionamento do sistema sem incorrer em custos de upgrade do plano, realizamos os seguintes passos:

1. **Criação de Novo Projeto:** Foi criado um novo projeto no Neon chamado `auditoria-nstech-2` (Região: AWS sa-east-1).
2. **Importação de Dados:** Utilizamos a ferramenta "Import Data" do Neon no novo projeto para copiar todos os dados, schemas e tabelas diretamente do banco antigo (`ep-frosty-surf-acvn8unb-pooler`).
3. **Identificação da Branch Migrada:** A importação criou os dados em uma branch dedicada no novo projeto (`import-2026-05-13T09:48...` correspondente ao compute `ep-falling-hall-ac2t9rln`), da qual identificamos a string de conexão.
4. **Atualização das Credenciais:** Atualizamos os arquivos `.env` e `backend/.env` para apontarem para a connection string dessa nova branch importada, garantindo que o sistema continue a usar todos os dados históricos sem interrupções.
5. **Reativação da Extensão:** A extensão `pgvector`, utilizada pelo sistema para funcionalidades de IA, não é transferida automaticamente pela ferramenta de importação do Neon. Reativamos a extensão manualmente no novo banco executando `CREATE EXTENSION IF NOT EXISTS vector;`.

## Conclusão
O sistema está novamente operante e apontando para o banco de dados `auditoria-nstech-2`. Nenhuma perda de dados ocorreu.