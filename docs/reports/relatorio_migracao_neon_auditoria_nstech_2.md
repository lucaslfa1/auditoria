# Relatório de Migração de Banco de Dados: Neon (auditoria-nstech-2)

**Data:** 13 de Maio de 2026

## Motivação da Migração
O banco de dados anterior (`auditoria-nstech`) atingiu o limite de capacidade imposto pela plataforma Neon. Para garantir a continuidade operacional do sistema de auditoria e suportar o volume crescente de chamadas processadas pela automação híbrida (Huawei AICC e Azure OpenAI), foi criado um novo projeto no Neon, isolado e com limite restaurado, denominado **`auditoria-nstech-2`**.

## Ações Realizadas

1. **Provisionamento:** Um novo projeto `auditoria-nstech-2` foi criado no Neon na região `sa-east-1` (AWS São Paulo).
2. **Atualização de Credenciais:** As variáveis de ambiente (`DATABASE_URL`) foram atualizadas em ambos os arquivos de configuração (na raiz do projeto e dentro de `/backend`) para apontar para o pooler do novo banco de dados:
   - *Host:* `ep-aged-river-acr5e219-pooler.sa-east-1.aws.neon.tech`
   - *Role:* `neondb_owner`
3. **Validação:** A conectividade com o novo banco de dados foi testada e confirmada com sucesso via script Python (`psycopg2`).

## Impacto
* O ambiente de desenvolvimento (e os futuros deploys) agora apontam de forma segura para o novo banco de dados.
* A persistência de dados de triagem, avaliações de IA e transcrições diarizadas agora possuem uma margem de armazenamento restabelecida.

## Próximos Passos (Recomendação)
1. Certificar-se de rodar as *migrations* ou scripts de deploy (`backend/deploy_schema.py`) no novo banco de dados, caso ele tenha sido criado do zero e não a partir de um *branch/fork* do Neon original.
2. Atualizar as variáveis de ambiente na hospedagem do frontend e no Cloud Run (via `gcloud run services update --update-env-vars`), conforme manda o `GEMINI.md` para evitar que a aplicação em nuvem continue tentando conectar no banco lotado.
