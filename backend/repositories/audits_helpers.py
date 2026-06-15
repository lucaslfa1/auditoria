"""Helpers de normalização de entrada do repository de auditorias.

Pequenas funções puras compartilhadas entre os módulos de `audits` (CRUD,
cota, fila de revisão, export). Sem I/O, sem estado.

Extraído de `repositories/audits.py` (v1.3.145) sem mudança de comportamento;
os nomes seguem reexportados de `repositories.audits` para compat (alguns testes
chamam os helpers privados diretamente). Módulo próprio para que `audits.py` e
`audits_quota.py` os importem sem criar import circular.
"""

from typing import Optional


def _normalize_binary_detail_status(raw_status: object) -> str:
    """Colapsa o status de um critério para o modelo binário pass/fail.

    `na`/`pending_manual` viram "pass" (não penalizam) e `partial` vira "fail"
    (modelo binário não tem meio-termo). Levanta ValueError para valores fora
    do vocabulário conhecido.
    """
    status = str(raw_status or "").strip().lower()
    if status in {"pass", "na", "n/a", "pending_manual"}:
        return "pass"
    if status in {"fail", "partial"}:
        return "fail"
    raise ValueError("Status de criterio invalido.")


def _normalize_sector_id(sector_id: Optional[str]) -> Optional[str]:
    """Setor em minúsculas sem espaços nas bordas; vazio vira None."""
    normalized = str(sector_id or "").strip().lower()
    return normalized or None


def _normalize_operator_name(operator_name: Optional[str]) -> Optional[str]:
    """Nome do operador sem espaços nas bordas (preserva caixa); vazio vira None."""
    normalized = str(operator_name or "").strip()
    return normalized or None


def _normalize_operator_id(operator_id: Optional[str]) -> Optional[str]:
    """Id de telefonia do operador sem espaços nas bordas; vazio vira None."""
    normalized = str(operator_id or "").strip()
    return normalized or None
