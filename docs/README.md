# Documentação — índice canônico

Atualizado em 2026-06-16 (handover). A suíte numerada 01–13 é a documentação
canônica do sistema: leia na ordem para entender, operar e migrar. O restante
da pasta é material complementar ou histórico (ver §3).

## 1. Suíte canônica (01–13)

| Doc | Cobre |
| --- | --- |
| [01-visao-geral.md](01-visao-geral.md) | O que o sistema faz (negócio), quem usa e o fluxo ponta a ponta com diagrama |
| [02-arquitetura.md](02-arquitetura.md) | Mapa do código: backend por subsistema, frontend por feature, o que é legado |
| [03-banco-de-dados.md](03-banco-de-dados.md) | Dicionário do schema (38 tabelas, views, pgvector), mecânica de migrations e seeds |
| [04-variaveis-de-ambiente.md](04-variaveis-de-ambiente.md) | Convenções do `.env.example` (179 vars) e o mínimo para produção |
| [05-operacao-runbook.md](05-operacao-runbook.md) | Ciclo diário, endpoints de diagnóstico, troubleshooting dos problemas comuns |
| [06-integracao-huawei.md](06-integracao-huawei.md) | AICC: autenticação, endpoints, pipeline D-1, filtros de negócio, tombstones, timezone |
| [07-custos-e-guardrails.md](07-custos-e-guardrails.md) | Onde o dinheiro é gasto, o incidente de jun/2026, tetos diários e kill-switch |
| [08-seguranca.md](08-seguranca.md) | Estado de segurança real, segredos comprometidos no histórico git, rotação, Key Vault |
| [09-testes.md](09-testes.md) | Como rodar a suíte (0 falhas toleradas), banco de teste obrigatório, guard de prod |
| [10-migracao-banco.md](10-migracao-banco.md) | Migração Neon → PostgreSQL gerenciado (destino indefinido): requisitos, scripts, janela, rollback |
| [11-deploy.md](11-deploy.md) | O que o sistema exige de qualquer plataforma; mapeamento Cloud Run → Azure |
| [12-checklist-handover.md](12-checklist-handover.md) | Checklist executável do handover, fase a fase, com responsáveis |
| [13-guia-do-codigo.md](13-guia-do-codigo.md) | Mapa do código-fonte para um dev novo: camadas, fluxo→arquivos, convenções (fachada+reexport), onde testar, dívida técnica conhecida |

## 2. Complementares ativos

| Local | Conteúdo |
| --- | --- |
| `manual-gestores/` | Manual operacional em linguagem gerencial (triagem, fluxo, regras de negócio) |
| `infra/HUAWEI_NETWORK_MANIFEST.md` | Whitelist de IPs, modo de autenticação em produção e chaves Huawei no banco — referenciado pelo doc 06 |
| `references/` | Fontes canônicas externas (critérios, dicionário operacional, manuais) |
| `integracoes/huawei/` | Catálogo de funções, guia D-1 e coleção Postman da API Huawei AICC (complementa o doc 06) |
| `../backend/.env.example` | Referência sempre atualizada das variáveis de ambiente |
| `../logs/versions/` | Changelog técnico por versão (x.y.z.md) — histórico de toda mudança relevante |

## 3. Material histórico (movido para fora do repo)

No enxugamento para o handover (2026-06), os documentos de valor apenas histórico
— arquiteturas/planos de fases anteriores, revisões e relatórios datados, planilhas
de anexo, PDFs de referência de API externa — foram **movidos para fora do repo**
(pasta `../auditoria-arquivo/`, espelhando a estrutura). Continuam recuperáveis
também pelo histórico git. O repositório mantém apenas a suíte canônica (01–13) e
os complementares ativos da §2; quando algo histórico conflitar com a suíte, **a
suíte vence**.
