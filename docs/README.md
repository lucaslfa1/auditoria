# Docs

Data de referencia: 2026-03-06

## Estrutura
- `architecture/`: arquitetura e organizacao canonica do projeto
- `branding/`: referencia visual e identidade
- `manual-gestores/`: manual operacional em linguagem gerencial
- `references/`: fontes canonicas externas e operacionais usadas como base
- `reviews/`: relatorios de revisao funcional, layout e auditoria
- `reports/`: relatorios operacionais e exportacoes documentadas

## Fonte canonica atual
- `architecture/project-organization-policy.md`: politica de organizacao, documentacao, arquivos grandes e plano de migracao estrutural
- `architecture/system-flow-structure.md`: organizacao do frontend alinhada ao fluxo do sistema
- `references/`: fonte canonica para criterios, dicionario operacional e manuais externos
- `database.md`: operacao local do banco e migracoes
- `database/sqlserver-readonly-integration-plan.md`: plano para integrar SQL Server corporativo apenas como leitura
- `database/sqlserver-dba-checklist.md`: checklist objetivo para o DBA
- `manual-gestores/README.md`: indice do manual gerencial do sistema
- `manual-gestores/03-triagem.md`: resumo operacional da triagem apos a revisao formal
- `reviews/triagem-review-2026-04-08.md`: contrato funcional e tecnico do modulo de triagem, com abertura formal da Prioridade 1
- `../GUIA_AGENTES.md`: diretrizes de colaboracao e design

## Convencoes locais
- `vite.config.ts` e a configuracao canonica do frontend
- `scripts/experiments/` guarda scripts exploratorios
- `tests/manual/` guarda testes manuais e fixtures avulsas
- `tmp/diagnostics/` guarda saidas temporarias de diff e status
- pastas ocultas locais de ferramenta nao fazem parte do runtime da aplicacao
- `tmp/local-secrets/` guarda anotacoes e credenciais locais fora do fluxo normal do projeto
