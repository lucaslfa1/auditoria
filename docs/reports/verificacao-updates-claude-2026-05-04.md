# Relatório de Verificação de Atualizações - Versão 1.3.58

**Data:** 2026-05-04
**Responsável:** Gemini CLI
**Status:** APROVADO PARA COMMIT

## 1. Resumo das Alterações (Claude)
As alterações focaram no endurecimento da coleta de ligações da Huawei AICC, melhoria do diagnóstico de falhas e refinamento da Experiência do Usuário (UX) no painel de telefonia.

### Backend (Telefonia & Sync)
- **Huawei Sync (Hardening):** O método de download via **OBS direto** foi promovido a primário, invertendo a lógica anterior que tentava o File Server (FS) primeiro. Isso visa maior estabilidade, dado que o OBS tem se mostrado mais resiliente em produção.
- **Filtro de Risco:** Implementado descarte automático de ligações **receptivas** para setores de risco (`transferencia`, `uti`, `bas`, etc.) diretamente na coleta, economizando recursos e quotas de API.
- **Diagnóstico:** Melhoria significativa nos logs de erro (`backend/core/huawei_client.py`), incluindo a captura da classe da exceção e do corpo da resposta HTTP em caso de falha.
- **API:** O endpoint `/api/telefonia/sync/manual` agora aceita o parâmetro `horas_retroativas`, permitindo disparos manuais com janelas flexíveis (ex: 30min).

### Frontend (UX/UI)
- **Modos de Coleta:** O `SyncPanel` agora permite escolher entre 3 modos persistentes via radio buttons: *Período retroativo*, *Intervalo manual* e *Última sincronização*.
- **Limpeza Visual:** Removido o seletor de horas do cofre de credenciais (onde não pertencia) e o badge de confiança (`ConfidenceBadge`) da listagem de gravações para reduzir ruído visual.
- **Persistência:** As escolhas do usuário no painel de sincronização agora são salvas no `localStorage`.

## 2. Validação Técnica

### Testes de Backend (Automáticos)
- **Huawei Sync:** `python -m pytest backend/tests/test_huawei_sync.py`
  - **Resultado:** 31 PASSOU, 0 FALHOU.
  - **Observação:** Inclui validação do novo filtro de ligações receptivas em setores de risco.
- **Telefonia Router:** `python -m pytest backend/tests/test_telefonia_router.py`
  - **Resultado:** 6 PASSOU, 0 FALHOU.
  - **Observação:** Valida a nova lógica de parâmetros do endpoint de sync manual.

### Integridade do Frontend
- **Type-checking:** `npx tsc -b --noEmit`
  - **Resultado:** 2 erros detectados em `SupervisorPortal.tsx` (ERROS PRÉ-EXISTENTES, não relacionados às mudanças atuais). As novas implementações em `SyncPanel` e `RecordingsList` estão tipadas corretamente.

## 3. Conclusão
As alterações estão tecnicamente sólidas, cobertas por testes e resolvem bugs críticos de UX e eficiência de coleta reportados anteriormente. O bug identificado em `telefonia.py` (importação de `load_classified_audio`) também foi verificado como resolvido.

**Ação:** Procedendo com o commit e push das alterações.
