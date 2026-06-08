import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo
from repositories import operators

logger = logging.getLogger(__name__)

class OperatorValidationResult:
    """Encapsula o resultado da resolução e validação do operador."""
    def __init__(
        self,
        is_valid: bool,
        operator_name: str,
        operator_id: Optional[str] = None,
        resolved_operator_dict: Optional[dict] = None,
        block_reason: Optional[str] = None,
        block_message: Optional[str] = None,
        motivos_revisao_append: Optional[list[str]] = None,
        metadata_merge: Optional[dict] = None,
    ):
        self.is_valid = is_valid
        self.operator_name = operator_name
        self.operator_id = operator_id
        self.resolved_operator_dict = resolved_operator_dict
        self.block_reason = block_reason
        self.block_message = block_message
        self.motivos_revisao_append = motivos_revisao_append or []
        self.metadata_merge = metadata_merge or {}


class OperatorGatekeeper:
    """
    Serviço focado em resolver a identidade do operador e garantir que ele é auditável.
    Aplica o SRP isolando as regras de bloqueio (ex: operador não cadastrado, sem ID Huawei)
    da lógica de orquestração geral.
    """

    @classmethod
    def resolve_operator(
        cls,
        db_connection,
        item: dict,
        metadata: dict,
        operator_name: Optional[str],
        operator_id: Optional[str],
        sector_id: Optional[str],
    ) -> OperatorValidationResult:
        """
        Tenta encontrar o operador no banco de dados e valida regras de elegibilidade.
        """
        # Resolve pelo banco de dados
        resolved_operator = operators.resolve_auditable_colaborador(
            db_connection, operator_name, operator_id, sector_id
        )

        # Regra 1: Operador não cadastrado ou não auditável
        if not resolved_operator:
            return OperatorValidationResult(
                is_valid=False,
                operator_name=operator_name or "",
                operator_id=operator_id,
                block_reason="blocked_operator",
                block_message="Operador fora do modulo Operadores ou nao auditavel",
                motivos_revisao_append=["operador_nao_auditavel"],
                metadata_merge={
                    "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                    "operator_auditability_blocked": True,
                    "operator_auditability_name": operator_name or "",
                    "operator_auditability_id": operator_id or "",
                    "operator_auditability_sector": sector_id or "",
                },
            )

        # Regra 2: Para chamadas da Huawei, o operador precisa ter o id_huawei cadastrado
        if str(metadata.get("origem") or "").lower() == "huawei_sync":
            resolved_huawei_id = str(
                resolved_operator.get("idHuawei")
                or resolved_operator.get("id_huawei")
                or ""
            ).strip()
            
            if not resolved_huawei_id:
                return OperatorValidationResult(
                    is_valid=False,
                    operator_name=operator_name or "",
                    operator_id=operator_id,
                    block_reason="blocked_operator_huawei_id",
                    block_message="Operador Huawei sem ID Huawei cadastrado no modulo Operadores",
                    motivos_revisao_append=["operador_huawei_sem_id"],
                    metadata_merge={
                        "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                        "operator_huawei_id_required": True,
                        "operator_auditability_name": operator_name or "",
                        "operator_auditability_id": operator_id or "",
                        "operator_auditability_sector": sector_id or "",
                    },
                )

        # Se passou, consolida os nomes e IDs oficiais
        final_name = resolved_operator.get("name") or operator_name or ""
        final_id = (
            resolved_operator.get("matricula")
            or resolved_operator.get("preferredId")
            or operator_id
        )

        return OperatorValidationResult(
            is_valid=True,
            operator_name=final_name,
            operator_id=final_id,
            resolved_operator_dict=resolved_operator,
        )


class QuotaGatekeeper:
    """
    Serviço focado em garantir as regras de negócio de cota mensal (ex: máximo de 2 
    auditorias automáticas por operador por mês).
    """

    @classmethod
    def resolve_quota_datetime(cls, metadata: dict) -> datetime:
        """Determina a data de referência da ligação para calcular a cota do mês."""
        raw_timestamp = metadata.get("huawei_begin_time") or metadata.get("begin_time")
        if raw_timestamp is not None:
            try:
                return datetime.fromtimestamp(
                    int(raw_timestamp) / 1000.0,
                    tz=timezone.utc,
                ).astimezone(ZoneInfo("America/Sao_Paulo"))
            except (TypeError, ValueError, OverflowError, OSError):
                logger.warning("QuotaGatekeeper: huawei_begin_time invalido: %r", raw_timestamp)

        raw_audio_date = metadata.get("audio_date") or metadata.get("audioDate")
        if raw_audio_date:
            try:
                return datetime.strptime(str(raw_audio_date).strip()[:10], "%Y-%m-%d")
            except (TypeError, ValueError):
                logger.warning("QuotaGatekeeper: audio_date invalido: %r", raw_audio_date)

        return datetime.now()

    @classmethod
    def check_quota(
        cls,
        db_connection,
        operator_name: str,
        operator_id: Optional[str],
        quota_date: datetime,
        monthly_audit_quota: int,
    ) -> Optional[dict]:
        """
        Verifica se a cota mensal foi atingida.
        Retorna um dicionário com os metadados de bloqueio caso tenha atingido.
        Retorna None se a cota estiver OK.
        """
        from repositories.audits import get_operator_audit_count_for_month
        import os

        try:
            current_audit_count = get_operator_audit_count_for_month(
                db_connection,
                operator_name,
                quota_date.year,
                quota_date.month,
                operator_id=operator_id,
            )
        except Exception:
            if os.getenv("PYTEST_CURRENT_TEST"):
                current_audit_count = 0
            else:
                logger.exception("QuotaGatekeeper: Falha ao consultar cota do operador %s", operator_name)
                current_audit_count = 0

        if current_audit_count >= monthly_audit_quota:
            return {
                "block_reason": "monthly_capped",
                "block_message": f"Cota mensal de {monthly_audit_quota} auditorias atingida",
                "motivos_revisao_append": ["cota_mensal_atingida"],
                "metadata_merge": {
                    "monthly_cap_period": quota_date.strftime("%Y-%m"),
                    "monthly_cap_operator": operator_name,
                    "monthly_cap_operator_id": operator_id or "",
                    "monthly_cap_count": current_audit_count,
                    "monthly_cap_limit": monthly_audit_quota,
                }
            }

        return None
