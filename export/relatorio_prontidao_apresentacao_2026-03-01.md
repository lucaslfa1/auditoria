# Relatório de prontidão para apresentação

Data: 2026-03-01
Projeto: Sistema de Auditoria nstech
Status executivo: Não considero o sistema pronto para apresentação formal sem ajustes rápidos.

## Escopo da revisão

- Estudo de arquitetura do frontend, backend e persistência.
- Leitura dos fluxos principais: autenticação, auditoria, dashboard, classificação e configurações.
- Execução de testes automatizados já existentes.
- Smoke tests locais de inicialização, health check, entrega do frontend e autenticação.

## Resumo da arquitetura

- Frontend em React + TypeScript + Vite.
- Backend em FastAPI.
- Banco local SQLite (`backend/auditoria.db`).
- Integrações externas com Gemini e Azure/OpenAI para transcrição, classificação e auditoria.
- Exportações em Excel, PDF e Word.

## Testes executados

### 1) Testes automatizados do projeto

Comando:

```powershell
npm run test
```

Resultado:

- Frontend regression checks: OK
- Backend unit tests: 11 testes aprovados, 1 falha

Falha observada:

- `backend/tests/test_auth_api.py`
- O teste espera retorno `Lucas`, mas no ambiente atual a API retornou `lucas`.
- Isso indica fragilidade do teste em relação à configuração/local `.env`, não necessariamente quebra funcional completa do login.

### 2) Build de produção

Comando:

```powershell
npm run build
```

Resultado:

- Build concluído com sucesso.
- O frontend gerou bundle de produção sem erro.

### 3) Lint

Comando:

```powershell
npm run lint
```

Resultado:

- Falhou com grande volume de erros.
- O comando está varrendo `.venv`, `backup/` e outros arquivos fora do escopo principal do app.
- Na prática, o pipeline de lint está inadequado para uso como critério de qualidade do projeto atual.

### 4) Smoke tests locais

Comandos principais:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

e chamadas HTTP locais em `http://127.0.0.1:8000`.

Resultado:

- Backend sobe com sucesso.
- `/api/health`: OK
- `/`: OK, frontend servido corretamente
- Login retorna 200, porém a sessão não se mantém no modo local iniciado por `start-local.ps1`

Diagnóstico:

- O script sobe o backend com `ENVIRONMENT=production`.
- Nesse modo o cookie de sessão é emitido com flag `Secure`.
- Como o teste local usa HTTP e não HTTPS, o cookie não volta nas chamadas seguintes.
- Consequência prática: login local empacotado fica inviável para demo via `http://localhost:8000`.

## Achados principais

### Bloqueadores

1. **Autenticação falha no modo local de apresentação**
   - O fluxo de demo local atual não preserva sessão após login.
   - Para apresentação local isso é bloqueador.

2. **Dashboard injeta dados mockados quando não há base real**
   - O dashboard preenche métricas e histórico fictícios se o backend retornar vazio.
   - Isso é arriscado para apresentação porque pode mascarar ausência de dados reais.

3. **Credenciais padrão hardcoded no backend**
   - Há usuários e senhas default embutidos no código.
   - Isso é inadequado para qualquer ambiente de apresentação minimamente controlado.

### Riscos importantes

4. **Lint não é confiável como gate de qualidade**
   - O comando atual acusa centenas de erros majoritariamente fora do app principal.
   - Isso impede usar lint como sinal real de estabilidade.

5. **Documentação principal está incompleta**
   - O `README.md` ainda está no texto padrão do template Vite.
   - Falta material simples para operação, demo e troubleshooting.

6. **Fluxos com IA externa não foram validados end-to-end nesta revisão**
   - O ambiente desta revisão não foi usado para chamadas reais aos provedores externos.
   - O pipeline interno e testes mockados dão confiança parcial, não validação total de produção.

## Sinais positivos

- Arquitetura coerente para MVP/apresentação técnica.
- Build de produção funcionando.
- Health check e serving do frontend funcionando.
- Testes de regressão frontend passando.
- Cobertura básica de backend para auth, guardrails de classificação e lógica central.
- Fluxo mockado de auditoria passou com sucesso.

## Veredito

### Conclusão objetiva

**Hoje, em 2026-03-01, eu classificaria o sistema como “quase apresentável tecnicamente”, mas “ainda não pronto para apresentação formal”.**

Ele pode sustentar uma demonstração controlada **somente se** houver:

- ambiente ajustado para autenticação funcional;
- base real carregada ou remoção explícita dos mocks do dashboard;
- remoção/gestão segura das credenciais default;
- roteiro de demo validado antes da apresentação.

Sem isso, há risco real de:

- falha de login ao vivo;
- exibição de métricas fictícias;
- questionamentos de segurança e maturidade.

## Recomendação prática antes de apresentar

1. Corrigir o fluxo de sessão do modo local ou apresentar em HTTPS real.
2. Remover/desativar mocks automáticos do dashboard.
3. Remover credenciais default do código.
4. Ajustar `eslint` para ignorar diretórios externos ao app real.
5. Atualizar README com instruções reais de subida e roteiro de demo.
6. Rodar um ensaio final com uma base e arquivos reais.

## Resultado final

Status recomendado: **NÃO APRESENTAR ainda para público formal/cliente**.

Status alternativo: **APRESENTAR apenas em demo interna controlada, após correção rápida dos bloqueadores acima**.
