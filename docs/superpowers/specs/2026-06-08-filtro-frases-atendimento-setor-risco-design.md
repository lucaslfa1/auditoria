# Filtro de direção por frases de atendimento em setores de risco

**Data:** 2026-06-08
**Branch:** `fix/huawei-receptiva-direcao-setor-risco`
**Relacionado:** investigação do vazamento de receptivas (memória `auditoria-bug-receptivas-setor-risco`)

## Problema

Setores de risco (`uti`, `bas`, `distribuicao`, `fenix`, `transferencia`) só devem auditar ligações **ativas (outbound)**. Receptivas vêm vazando (casos isolados), porque:

1. A direção por **metadados** erra em ligações **transferidas** (a coleta depende do manifesto OBS, que não traz `isCallIn`; a inferência por endpoint vê ramais internos e classifica como ativa).
2. A 2ª defesa, a **pré-triagem por áudio** (`analyze_call_direction`), é **fail-open**: quando a IA responde `AMBIGUOUS`, a chamada é **mantida na fila** — mesmo quando o operador diz **frases de atendimento** ("em que posso ajudar", "central de atendimento") que denunciam receptiva. As frases já existem em `_INBOUND_STRONG_MARKERS`/`_INBOUND_GREETING_MARKERS`, mas só são consultadas no *fallback de exceção*; a IA decide primeiro e a engole.

## Solução — defesa em 2 camadas

**Camada 1 — direção real pela Huawei (metadados).** Para chamada de risco com direção incerta (só-OBS/inferida), consultar a API de detalhe (`querydetailcallinfo`/`querybasiccallinfo`) por `callId` e usar o `isCallIn` real.
*Status:* bloqueada localmente (auth Huawei só de IP autorizado — ver `auditoria-huawei-auth-diagnostico`). Validar em produção com `backend/scripts/diag_huawei_direcao_callid.py`. **Não** altera a precedência atual de `resolve_huawei_is_call_in` (que é defensável).

**Camada 2 — frases de atendimento (conteúdo).** Independe da Huawei; rodável/testável local. É o foco desta implementação:
1. Elevar as **frases de atendimento** a sinal **determinístico** em `analyze_call_direction`: se o operador, no início, diz uma frase de atendimento forte → **receptiva (INBOUND), antes de consultar a IA**. Resolve o `AMBIGUOUS` que hoje vaza.
2. **Ampliar** a lista de frases (parte das existentes; extensível conforme a auditora reportar).
3. Em **setor de risco**, direção **inconclusiva → DESCARTA** (não enfileira). Hoje é fail-open (mantém).

## Decisões (do usuário)

- Frases têm **precedência** sobre a IA.
- Setor de risco + direção inconclusiva → **descarta** (não "triagem manual").
- Vale para **automático + manual** (é coleta/download, não transcrição — sem conflito com a restrição do `hybrid_dual`).

## Arquivos

- `backend/core/pre_triage.py` — detecção determinística de frase + lista (Camada 2.1/2.2).
- `backend/core/huawei_sync.py` (~876-905) — inconclusivo → descarta em setor de risco (Camada 2.3).
- `backend/core/huawei_client.py` + gate — Camada 1 (depois, com validação em produção).

## Testes (TDD)

- `test_pre_triage.py`: detecção determinística da frase; **precedência** sobre a IA (IA mockada dizendo `OUTBOUND`/`AMBIGUOUS` → resultado `INBOUND`).
- `test_huawei_sync.py`: em setor de risco, `analyze_call_direction` inconclusiva → chamada **descartada**, não enfileirada.

## Não-objetivos

- Reverter a precedência de `resolve_huawei_is_call_in` (a Camada 1 a complementa).
- Mexer no engine de transcrição (`hybrid_dual`/`fast`) — assunto separado e pausado.
