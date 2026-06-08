# SQL Server Read-Only Integration Plan

Data de referencia: 2026-03-06

## Decisao atual
- O banco transacional da aplicacao continua local e sob controle do projeto.
- O SQL Server 2022 da empresa entra apenas como fonte externa de leitura.
- Nada da aplicacao deve depender de escrita, alteracao de schema ou job interno no SQL Server corporativo.

## Objetivo seguro
Usar o SQL Server corporativo para consultar dados mestres e operacionais que ja existem na empresa, trazendo esses dados para a base local da aplicacao por sincronizacao controlada.

## Escopo recomendado para a primeira integracao
- Operadores RH
- Supervisores
- Escalas
- IDs de telefonia
- Dados auxiliares de organizacao/setor

## Escopo que nao deve ir para o SQL Server corporativo nesta fase
- Auditorias geradas pela aplicacao
- Feedback de supervisor
- Usuarios e autenticacao do produto
- Fila de classificacao
- Exportacoes do sistema
- Arquivos salvos

## Arquitetura recomendada
1. O sistema consulta o SQL Server apenas por um adaptador dedicado de leitura.
2. O adaptador transforma os dados externos em payload canonico do sistema.
3. O sistema faz `upsert` desses dados na base local.
4. As telas e APIs continuam lendo a base local, nunca o SQL Server diretamente.

## Motivo dessa abordagem
- Remove dependencia online do SQL Server para uso normal do produto.
- Permite operar mesmo sem VPN ou indisponibilidade da rede corporativa.
- Evita espalhar SQL Server por todo o backend.
- Mantem a escrita centralizada em um banco que voce controla.

## Componentes sugeridos para a proxima etapa
- `backend/integrations/sqlserver_readonly/client.py`
- `backend/integrations/sqlserver_readonly/queries.py`
- `backend/services/reference_data_sync.py`
- `scripts/sync_sqlserver_readonly.py`

## Fluxos de sincronizacao recomendados
- `manual`: comando sob demanda, ideal para a primeira entrega
- `scheduled`: sincronizacao periodica posterior
- `bootstrap`: carga inicial para popular operadores e estruturas de apoio

## Contrato minimo esperado do SQL Server
- Um objeto estavel por dominio, de preferencia `view`
- Coluna de chave unica por operador
- Coluna de ultima atualizacao ou timestamp incremental
- Colunas textuais com nomenclatura estavel

## Parametros de ambiente sugeridos
- `SQLSERVER_READONLY_ENABLED`
- `SQLSERVER_READONLY_HOST`
- `SQLSERVER_READONLY_PORT`
- `SQLSERVER_READONLY_DATABASE`
- `SQLSERVER_READONLY_SCHEMA`
- `SQLSERVER_READONLY_USERNAME`
- `SQLSERVER_READONLY_PASSWORD`
- `SQLSERVER_READONLY_DRIVER`
- `SQLSERVER_READONLY_ENCRYPT`
- `SQLSERVER_READONLY_TRUST_SERVER_CERTIFICATE`
- `SQLSERVER_READONLY_OPERATORS_VIEW`
- `SQLSERVER_READONLY_SYNC_MODE`

## Etapas de implementacao recomendadas
1. Validar conectividade e credenciais read-only.
2. Confirmar quais `views` ou tabelas podem ser consultadas.
3. Definir payload canonico por dominio.
4. Implementar importacao manual para `colaboradores`.
5. Registrar metricas de sincronizacao e erros.
6. So depois considerar sincronizacao agendada.
