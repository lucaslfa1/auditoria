# Esteira observável + sem presos — Design

**Data:** 2026-06-01
**Autor:** Claude (brainstorming com Lucas)
**Status:** aprovado para plano de implementação
**Versão alvo:** 1.3.x (definir no plano)

## Problema

Dois sintomas observados em produção, mesma raiz de "esteira opaca":

1. **Itens de automação ficam presos em `pending`.** Exemplo real: item 201 (operadora Natália, `huawei_sync`, alerta `desconhecido`, confiança 0.5) travado em "triagem" com botão retriar. A esteira binária da v1.3.103 converteu os gates **dentro da fase de auditoria** (`audit_all_pending`, que só lê `status=READY_FOR_AUDIT`), mas a **fase de classificação** ainda rebaixa para `pending` por baixa confiança (`huawei_sync.py:1699‑1707`). Esses itens nunca chegam à esteira — nem para auditar, nem para descartar. O backlog reprocessado ficou limpo (script one-shot), mas itens novos voltam a cair no furo.

2. **A esteira roda às cegas.** Não há como saber, pela UI, o que está sendo auditado ou aguardando. A automação processa **1 item por vez em sequência** (`routers/automation.py:140`).

### Dado que orientou a decisão

Medição em produção (`fila_revisao_classificacao` + `huawei_sync_logs`):
- Os **43** itens de automação auditados: **todos** confiança ≥ 0,85, alerta conhecido.
- Os **17** descartados: **100%** por `triagem_sem_alerta_confiavel` (= sem alerta).
- Conclusão: **baixa confiança ≈ alerta desconhecido**. Quando a IA reconhece o alerta, vem com confiança alta; quando a confiança cai, é porque não reconheceu o alerta. O caso "alerta conhecido + confiança baixa" não aparece nos dados.

## Decisões

1. **Critério = alerta** (não confiança). Item de automação com alerta **conhecido** → audita (confiança deixa de travar). **Sem alerta / desconhecido** → descarta. Resultado: **zero item de automação preso**; todo item termina `awaiting_pair` (Arquivos Salvos) ou excluído.
2. **Auditorias assíncronas**, teto de **3 simultâneos** (`AUTOMATION_AUDIT_CONCURRENCY=3`, configurável), respeitando o budget de tempo do lote e o timeout por item que já existem.
3. **UI mínima**: só "auditando agora" + "na fila". Descartado some (excluído), auditado vai para Arquivos. O sistema lida com o resto, sem ruído.
4. **Triagem manual (`is_manual=true`) não muda** — continua indo para `pending`/revisão humana.

## Arquitetura

### Backend — fechar o gap (`huawei_sync.py`, `core/automation.py`)

Abordagem recomendada (mais isolada): **a classificação de automação deixa de usar `pending`.** Em `huawei_sync.py` (~1699‑1707), quando `is_manual=false`, a baixa confiança **não** rebaixa mais para `pending`; o item vai para `auto_resolved` (READY). A esteira binária existente (`_audit_single_item`) então decide com a lógica que já tem: alerta conhecido → audita → `awaiting_pair`; desconhecido → descarta (tombstone). Nada de novo na lógica de descarte; só paramos de prender antes dela.

- **Preserva manual:** o rebaixamento para `pending` continua valendo para `is_manual=true`. A mudança é gated por origem/automação.
- **Alternativa considerada (rejeitada por ser mais invasiva):** `audit_all_pending` passar a recolher também `status=pending` de automação. Muda a query de seleção e mistura responsabilidades.

### Backend — auditorias assíncronas (`core/automation.py:audit_all_pending`)

- Processar o batch com `asyncio.Semaphore(AUTOMATION_AUDIT_CONCURRENCY)` (default 3) em vez de laço sequencial.
- Respeitar `deadline` (budget do lote) e `item_timeout` já existentes — cada tarefa checa o deadline; o semáforo limita o paralelismo.
- `AutomationProgress`: `current_filename` (singular) passa a conviver com **`current_filenames`** (lista dos itens em voo), para a UI mostrar vários "auditando agora". `_progress_lock` já existe; garantir atualização segura sob asyncio.
- Atualizar a docstring do router (`/audit-all`: "até N em paralelo").

### UI — painel + labels (aba Automação)

- **Fonte:** `GET /automation/status` (já existe), via polling (~2 s) enquanto `is_running`.
- **Painel:** barra de progresso (`completed`/`total`); seção "**Auditando agora**" (lista de `current_filenames`); "**Na fila: N**" (derivado: itens READY ainda não em voo). Ocioso (`is_running=false`, fila vazia) → linha discreta "esteira ociosa".
- **Observação por item na lista da esteira:** 🔄 *auditando* (está em `current_filenames`) / ⏳ *em fila* (READY aguardando).
- **Sem** selo de auditado (vai para Arquivos) e **sem** descartados (excluídos).

## Fluxo de dados

```
download (huawei_sync) → classificação
   ├─ is_manual=true  → pending (triagem humana)        [inalterado]
   └─ is_manual=false → auto_resolved (READY)           [muda: não prende mais]
                          │
                   audit_all_pending  (Semaphore=3)
                          ├─ alerta conhecido → audita → awaiting_pair → Arquivos Salvos
                          └─ desconhecido     → descarta → excluído + tombstone

UI: GET /automation/status (poll) → painel (barra, auditando agora, na fila)
```

## Fora de escopo

- Rastro/aba/contador de descartes (decisão explícita do dono: descartado some).
- Qualquer mudança em triagem manual.
- Trabalho do GPT em andamento (binariedade de detalhes de auditoria, tombstone no enfileiramento, guard, senhas) — independente.

## Riscos e mitigações

- **Falso descarte:** só `desconhecido` descarta, condição determinística; o motivo persiste em `huawei_sync_logs.failure_reason` (auditável por query mesmo sem tela).
- **Concorrência do `_progress`:** atualização de contadores/lista sob asyncio precisa ser consistente — reusar `_progress_lock`; testar com várias tarefas.
- **Rate limit Azure (429):** mitigado pelo teto de 3; configurável para baixar se necessário.
- **Sub-caso STRICT_RH:** parte dos "desconhecido" é "alerta fora do setor oficial" (RH trocou setor) — descartado por ora. Se aparecer volume, revisitar `STRICT_RH_SECTOR_ENFORCEMENT`.
- **Coordenação:** GPT está no working tree (frontend). Implementar **depois** que ele commitar; `huawei_sync.py`/`automation.py` não estão na lista de arquivos dele.

## Testes

**Backend**
- Automação, alerta conhecido + confiança baixa → vai para READY e é auditado (não fica `pending`).
- Automação, alerta desconhecido → descartado (tombstone), não preso.
- `is_manual=true` → continua em `pending` (triagem manual intacta).
- Async: N itens auditados com no máximo `AUTOMATION_AUDIT_CONCURRENCY` em voo; budget/timeout respeitados; `current_filenames` reflete os em voo.

**UI**
- Painel renderiza estados rodando (barra + auditando agora + fila) e ocioso.
- Labels por item: auditando vs em fila.

## Verificação end-to-end

1. Suíte backend verde (em banco de teste — ver guard do conftest).
2. Rodar 1 ciclo: nenhum item de automação em `pending`; auditáveis viram `awaiting_pair`; desconhecidos excluídos.
3. Painel mostra até 3 "auditando agora" e a fila decrescendo.
4. Item travado em triagem deixa de ocorrer para automação.
