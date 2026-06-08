# Esteira observável + sem presos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar itens de automação presos em `pending` (critério passa a ser o alerta, não a confiança) e dar visibilidade mínima da esteira na UI, com auditorias assíncronas limitadas.

**Architecture:** A classificação automática deixa de rebaixar para `pending` por baixa confiança — manda para `auto_resolved` (READY) e a esteira binária existente (`_audit_single_item`) decide: alerta conhecido audita, desconhecido descarta. O laço de auditoria vira assíncrono com semáforo. A UI consome o endpoint de progresso já existente (`GET /automation/status`).

**Tech Stack:** Python/FastAPI (backend), pytest, React+TypeScript+Vitest (frontend). Banco Neon (psycopg2). Feature flags via env (padrão `_*_enabled()`).

**Coordenação:** O GPT está editando o frontend no working tree. **Fases 1 e 2 (backend) podem ir primeiro** — `huawei_sync.py`/`automation.py` não estão nos arquivos dele. **Fase 3 (UI) só após o GPT commitar.** Antes de executar: `git fetch` + ler commits recentes.

**Spec:** `docs/superpowers/specs/2026-06-01-esteira-observavel-sem-presos-design.md`

---

## File Structure

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `backend/core/huawei_sync.py` | Decisão de status da classificação automática (`_aplicar_auto_classificacao`) | Modificar (~1698‑1707) + helper de flag |
| `backend/core/automation.py` | Laço `audit_all_pending` → assíncrono; `AutomationProgress` → lista de itens em voo | Modificar |
| `tests/backend/test_classificacao_status_resolver.py` | Testa a decisão de status (gap) | Criar |
| `tests/backend/test_automation_async.py` | Testa concorrência limitada | Criar |
| `src/features/automacao/components/EsteiraProgressPanel.tsx` | Painel "auditando agora + na fila" | Criar |
| `tests/frontend/EsteiraProgressPanel.test.tsx` | Testa render do painel | Criar |

---

## Fase 1 — Fechar o gap dos `pending` (crítico, isolado)

Extrai a regra de status para uma função pura e testável, e a usa em `_aplicar_auto_classificacao`. Com a flag ON (default), automação nunca mais cai em `pending` por baixa confiança.

### Task 1: Função pura de decisão de status

**Files:**
- Modify: `backend/core/huawei_sync.py` (adicionar helper de flag + função `_resolve_auto_classificacao_status`, perto dos outros helpers de módulo)
- Test: `tests/backend/test_classificacao_status_resolver.py` (criar)

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_classificacao_status_resolver.py
import importlib

hs = importlib.import_module("core.huawei_sync")


def test_skip_pending_baixa_confianca_vira_ready(monkeypatch):
    # flag ON (default): needs_review NAO rebaixa para pending
    monkeypatch.delenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", raising=False)
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="pending") == "auto_resolved"
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="auto_resolved") == "auto_resolved"


def test_flag_off_preserva_pending(monkeypatch):
    monkeypatch.setenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", "false")
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="auto_resolved") == "pending"


def test_status_humano_nao_e_sobrescrito(monkeypatch):
    monkeypatch.delenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", raising=False)
    # reviewed/audited/etc. nunca é mexido
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="reviewed") == "reviewed"
    assert hs._resolve_auto_classificacao_status(needs_review=False, status_atual="audited") == "audited"


def test_sem_review_vai_para_ready(monkeypatch):
    monkeypatch.delenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", raising=False)
    assert hs._resolve_auto_classificacao_status(needs_review=False, status_atual="pending") == "auto_resolved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backend/test_classificacao_status_resolver.py -v`
Expected: FAIL — `AttributeError: module 'core.huawei_sync' has no attribute '_resolve_auto_classificacao_status'`

- [ ] **Step 3: Write minimal implementation**

Em `backend/core/huawei_sync.py`, perto do topo do módulo (junto de outros helpers), adicionar:

```python
def _automation_skip_pending_on_low_confidence_enabled() -> bool:
    """Default ON: automação não rebaixa para 'pending' por baixa confiança.
    O item vai para auto_resolved (READY) e a esteira (_audit_single_item) decide:
    alerta conhecido audita, desconhecido descarta. OFF restaura o pending legado."""
    raw = os.getenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_auto_classificacao_status(*, needs_review: bool, status_atual: str) -> str:
    """Decide o status final de um item de classificação AUTOMÁTICA.

    Status já tocado por humano/auditoria (qualquer coisa fora de
    {auto_resolved, pending}) é preservado.
    """
    status_atual = (status_atual or "").strip().lower()
    if needs_review and not _automation_skip_pending_on_low_confidence_enabled():
        return "pending"
    if status_atual in {"auto_resolved", "pending"}:
        return "auto_resolved"
    return status_atual or "auto_resolved"
```

Garantir `import os` no topo do arquivo (provavelmente já existe).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backend/test_classificacao_status_resolver.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add backend/core/huawei_sync.py tests/backend/test_classificacao_status_resolver.py
git commit -m "feat(automation): regra de status nao prende automacao em pending (flag default ON)"
```

### Task 2: Usar a função em `_aplicar_auto_classificacao`

**Files:**
- Modify: `backend/core/huawei_sync.py:1698-1707`

- [ ] **Step 1: Substituir o bloco de decisão de status**

Trocar o bloco atual (linhas ~1698‑1707):

```python
        status_atual = (row["status"] or "").strip().lower()
        # Auto-classificacao com baixa confianca rebaixa para pending; alta confianca
        # permanece em auto_resolved (worker captura via filtro virtual READY_FOR_AUDIT).
        if needs_review:
            novo_status = "pending"
        elif status_atual in {"auto_resolved", "pending"}:
            novo_status = "auto_resolved"
        else:
            # Se ja foi humano-revisado/auditado/cota, nao mexer.
            novo_status = status_atual or "auto_resolved"
```

por:

```python
        status_atual = (row["status"] or "").strip().lower()
        # Automação não prende em pending por baixa confiança (flag default ON):
        # vai para auto_resolved (READY) e a esteira decide (conhecido audita,
        # desconhecido descarta). Ver _resolve_auto_classificacao_status.
        novo_status = _resolve_auto_classificacao_status(
            needs_review=needs_review, status_atual=status_atual
        )
```

- [ ] **Step 2: Rodar a suíte de huawei_sync (sem regressão)**

Run: `python -m pytest tests/backend/test_huawei_sync.py -q`
Expected: PASS (usa um banco de teste — ver guard do conftest; NÃO usar `ALLOW_TESTS_ON_PROD_DB` contra produção)

- [ ] **Step 3: Commit**

```bash
git add backend/core/huawei_sync.py
git commit -m "fix(automation): aplica regra de status nova em _aplicar_auto_classificacao (fecha gap do pending)"
```

### Task 3: Teste de integração do ciclo (conhecido audita / desconhecido descarta)

**Files:**
- Test: `tests/backend/test_automation_discard_unknown.py` (já existe — confirmar que cobre; senão adicionar caso)

- [ ] **Step 1: Confirmar/adicionar asserção** de que um item de automação com alerta `desconhecido` chegando em `auto_resolved` é DESCARTADO por `_audit_single_item` (não vira `pending`). Se o teste existente já cobre via `audit_all_pending`, apenas rodar:

Run: `python -m pytest tests/backend/test_automation_discard_unknown.py -q`
Expected: PASS

- [ ] **Step 2: Commit (se houve mudança no teste)**

```bash
git add tests/backend/test_automation_discard_unknown.py
git commit -m "test(automation): cobre desconhecido em auto_resolved -> descarte"
```

---

## Fase 2 — Auditorias assíncronas com teto (`audit_all_pending`)

Hoje o laço (`backend/core/automation.py:639`) processa os itens **sequencialmente** (`for item in items: ...`). Vira processamento concorrente com `asyncio.Semaphore`, preservando pause/cancel/budget e atualizando uma **lista** de itens em voo.

### Task 4: `AutomationProgress` expõe itens em voo

**Files:**
- Modify: `backend/core/automation.py` (classe `AutomationProgress`, ~231‑270)
- Test: `tests/backend/test_automation_async.py` (criar)

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_automation_async.py
import importlib
automation = importlib.import_module("core.automation")


def test_progress_exposes_in_flight_list():
    p = automation.AutomationProgress()
    assert "current_filenames" in p.to_dict()
    assert p.to_dict()["current_filenames"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backend/test_automation_async.py::test_progress_exposes_in_flight_list -v`
Expected: FAIL — `KeyError: 'current_filenames'`

- [ ] **Step 3: Implement**

Em `AutomationProgress` adicionar o campo e expor no `to_dict`:

```python
    current_filenames: list = field(default_factory=list)  # itens em voo (async)
```

No `to_dict()`:

```python
            "current_filenames": list(self.current_filenames),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backend/test_automation_async.py::test_progress_exposes_in_flight_list -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/automation.py tests/backend/test_automation_async.py
git commit -m "feat(automation): AutomationProgress expoe current_filenames (itens em voo)"
```

### Task 5: Helper de concorrência + laço concorrente

**Files:**
- Modify: `backend/core/automation.py` (helper de flag + laço em `audit_all_pending`, ~639‑862)
- Test: `tests/backend/test_automation_async.py`

- [ ] **Step 1: Write the failing test** (concorrência limitada ao teto)

```python
# tests/backend/test_automation_async.py  (acrescentar)
import asyncio
from unittest.mock import patch


def test_concurrency_never_exceeds_limit(monkeypatch):
    monkeypatch.setenv("AUTOMATION_AUDIT_CONCURRENCY", "3")
    in_flight = 0
    peak = 0

    async def fake_audit(item):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return {"status": "audited"}

    items = [{"input_hash": f"h{i}", "nome_arquivo": f"f{i}.wav"} for i in range(12)]

    async def run():
        # _run_audit_batch_concurrent: nova função extraída do laço, recebe items + auditor
        await automation._run_audit_batch_concurrent(items, auditor=fake_audit, deadline=None)

    asyncio.run(run())
    assert peak <= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backend/test_automation_async.py::test_concurrency_never_exceeds_limit -v`
Expected: FAIL — `AttributeError: ... '_run_audit_batch_concurrent'`

- [ ] **Step 3: Implement**

Adicionar o helper de flag:

```python
def _automation_audit_concurrency() -> int:
    raw = os.getenv("AUTOMATION_AUDIT_CONCURRENCY")
    try:
        n = int(raw) if raw is not None else 3
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, 8))
```

Extrair o **corpo de processamento de um item** (hoje inline no `for item in items:`, linhas ~677‑860 — gatekeeper, auditoria, descarte, transitório, atualização de `_progress`) para uma coroutine `async def _process_one_item(item) -> dict`. Dentro dela, ao iniciar, fazer `_progress.current_filenames.append(nome)` sob `_progress_lock`; ao terminar (finally), remover. Manter `current_filename` = primeiro em voo, por compat.

Criar o orquestrador concorrente:

```python
async def _run_audit_batch_concurrent(items, *, auditor, deadline):
    sem = asyncio.Semaphore(_automation_audit_concurrency())

    async def _guarded(item):
        # respeita budget/cancel/pause antes de adquirir o slot
        if deadline is not None and (deadline - time.monotonic()) <= 1:
            return None
        async with sem:
            if _config_flag("automacao_is_cancelled"):
                return None
            return await auditor(item)

    return await asyncio.gather(*[_guarded(it) for it in items], return_exceptions=True)
```

Substituir o `for item in items:` em `audit_all_pending` por `await _run_audit_batch_concurrent(items, auditor=_audit_single_item_with_timeout, deadline=deadline)`, e mover a contabilização de `completed/discarded/failed` para dentro de `_process_one_item`/`_guarded` conforme o `status` retornado.

> **Cuidado na execução (ler o laço 639‑862 inteiro antes):** preservar a semântica de pause (`await asyncio.sleep(1)` enquanto pausado), cancel (interrompe novos), budget (não inicia item após deadline) e os incrementos de `_progress` sob `_progress_lock`. Os checks que hoje são por-iteração passam a ser por-coroutine.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/backend/test_automation_async.py -v`
Expected: PASS

- [ ] **Step 5: Rodar a suíte de automação (sem regressão)**

Run: `python -m pytest tests/backend/ -q -k "automation"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/core/automation.py tests/backend/test_automation_async.py
git commit -m "feat(automation): auditorias assincronas com teto AUTOMATION_AUDIT_CONCURRENCY (default 3)"
```

### Task 6: Atualizar docstring do endpoint

**Files:**
- Modify: `backend/routers/automation.py:138-141`

- [ ] **Step 1:** Trocar "Processa 1 por vez em sequência com progresso rastreável." por "Processa em paralelo (até AUTOMATION_AUDIT_CONCURRENCY itens) com progresso rastreável."

- [ ] **Step 2: Commit**

```bash
git add backend/routers/automation.py
git commit -m "docs(automation): endpoint audit-all agora processa em paralelo"
```

---

## Fase 3 — UI: painel "auditando + na fila" (APÓS o GPT commitar)

> **Pré-condição:** `git fetch` + confirmar que o GPT terminou no frontend. Ler `src/features/automacao/` para achar o componente da aba Automação onde o painel será plugado (1 import + 1 render). O componente abaixo é **novo e autocontido** — não conflita.

### Task 7: Componente `EsteiraProgressPanel`

**Files:**
- Create: `src/features/automacao/components/EsteiraProgressPanel.tsx`
- Test: `tests/frontend/EsteiraProgressPanel.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// tests/frontend/EsteiraProgressPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { EsteiraProgressPanel } from "../../src/features/automacao/components/EsteiraProgressPanel";

test("rodando: mostra auditando agora e na fila", () => {
  render(<EsteiraProgressPanel status={{
    is_running: true, total: 45, completed: 28, discarded: 4,
    current_filenames: ["ligacao_natalia.wav", "ligacao_pedro.wav"],
    queued: 13,
  }} />);
  expect(screen.getByText(/Auditando agora/i)).toBeInTheDocument();
  expect(screen.getByText(/ligacao_natalia\.wav/)).toBeInTheDocument();
  expect(screen.getByText(/Na fila/i)).toBeInTheDocument();
  expect(screen.getByText(/13/)).toBeInTheDocument();
});

test("ocioso: mostra linha discreta", () => {
  render(<EsteiraProgressPanel status={{
    is_running: false, total: 0, completed: 0, discarded: 0,
    current_filenames: [], queued: 0,
  }} />);
  expect(screen.getByText(/ociosa/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- EsteiraProgressPanel` (ou o runner do projeto em `tests/frontend/`)
Expected: FAIL — módulo não encontrado

- [ ] **Step 3: Implement** (componente puro, recebe `status`; o polling do `GET /automation/status` fica no container da aba)

```tsx
// src/features/automacao/components/EsteiraProgressPanel.tsx
import React from "react";

export interface EsteiraStatus {
  is_running: boolean;
  total: number;
  completed: number;
  discarded: number;
  current_filenames: string[];
  queued: number;
}

export function EsteiraProgressPanel({ status }: { status: EsteiraStatus }) {
  if (!status.is_running && status.queued === 0 && status.current_filenames.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/50 px-3 py-2 text-sm text-neutral-500 text-center">
        Esteira ociosa · nada na fila
      </div>
    );
  }
  const pct = status.total > 0 ? Math.round((status.completed / status.total) * 100) : 0;
  return (
    <div className="rounded-lg border border-neutral-700 bg-neutral-900 p-4">
      <div className="mb-2 flex items-center justify-between">
        <strong className="text-neutral-100">Esteira de automação</strong>
        {status.is_running && <span className="text-xs text-green-400">● rodando</span>}
      </div>
      <div className="mb-3 h-2 overflow-hidden rounded bg-neutral-700">
        <div className="h-2 bg-green-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="mb-1 text-xs uppercase tracking-wide text-neutral-500">Auditando agora</div>
      <ul className="mb-3 flex flex-col gap-1 text-sm text-yellow-300">
        {status.current_filenames.length === 0
          ? <li className="text-neutral-600">—</li>
          : status.current_filenames.map((f) => <li key={f}>🔄 {f}</li>)}
      </ul>
      <div className="border-t border-neutral-800 pt-2 text-sm text-neutral-400">
        ⏳ Na fila: <span className="text-neutral-100">{status.queued}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- EsteiraProgressPanel`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add src/features/automacao/components/EsteiraProgressPanel.tsx tests/frontend/EsteiraProgressPanel.test.tsx
git commit -m "feat(ui): EsteiraProgressPanel (auditando agora + na fila)"
```

### Task 8: Plugar na aba Automação + polling + `queued`

**Files:**
- Modify: container da aba Automação (confirmar caminho pós-GPT em `src/features/automacao/`)
- Modify: `backend/core/automation.py` (derivar `queued` no `audit_all_pending`/status: itens READY ainda não em voo) **ou** expor via `GET /automation/status`

- [ ] **Step 1:** No backend, incluir `queued` no payload de `GET /automation/status` — contar itens `status=READY_FOR_AUDIT` na fila menos os em voo. Teste: `tests/backend/test_automation_async.py` adiciona asserção de que `to_dict()`/status inclui `queued >= 0`.

- [ ] **Step 2:** No container da aba, fazer polling de `GET /automation/status` a cada 2s enquanto `is_running`, e renderizar `<EsteiraProgressPanel status={...} />`. (1 import + 1 bloco de fetch + 1 render.)

- [ ] **Step 3:** Observação por item na lista da esteira: marcar 🔄 *auditando* quando o nome está em `current_filenames`, ⏳ *em fila* quando READY. (Reusa o mesmo `status`.)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(ui): pluga painel da esteira na aba Automacao + queued no status"
```

---

## Self-Review

**Spec coverage:**
- Critério = alerta / zero pending → Fase 1 (Tasks 1‑3). ✓
- Async teto 3 → Fase 2 (Tasks 4‑6). ✓
- UI mínima (auditando + fila) → Fase 3 (Tasks 7‑8). ✓
- Descartado some / auditado→Arquivos → consequência da Fase 1 (esteira existente); UI não mostra descartado. ✓
- Triagem manual intacta → `_aplicar_auto_classificacao` é só automática (documentado na Task 2). ✓

**Placeholders:** Fase 3 depende do estado pós-GPT para o **ponto de plug** (Task 8) — marcado como dependência real, não TODO vago; o componente (Task 7) é código completo.

**Type consistency:** `EsteiraStatus` (Task 7) bate com os campos de `AutomationProgress.to_dict()` (Task 4: `current_filenames`; `queued` adicionado na Task 8). `_resolve_auto_classificacao_status(needs_review, status_atual)` consistente entre Tasks 1 e 2.

## Riscos
- **Async/concorrência do `_progress`:** todos os incrementos sob `_progress_lock`; testar com o teste de pico de concorrência.
- **Pause/cancel/budget no async:** preservar a semântica — ler o laço 639‑862 inteiro antes de extrair (nota na Task 5).
- **Falso descarte:** inalterado vs hoje — só `desconhecido` descarta; motivo persiste em `huawei_sync_logs.failure_reason`.
- **Testes contra prod:** usar banco de teste; o guard do `conftest` bloqueia `ep-aged-river` salvo override consciente.
