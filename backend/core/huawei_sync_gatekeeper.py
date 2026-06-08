from typing import Optional, Dict, Any, List
import logging
from abc import ABC, abstractmethod

from repositories import operators
from core.huawei_direction import (
    NON_TELEFONIA_SECTORS,
    OUTBOUND_ONLY_RISK_SECTORS,
    resolve_huawei_is_call_in,
    normalize_huawei_sector,
)

logger = logging.getLogger(__name__)


def _normalize_identity_text(text: object) -> str:
    """Helper genérico para normalizar strings de comparação (ex: Mondelez/Testes)."""
    import unicodedata
    raw = str(text or "").strip().lower()
    return unicodedata.normalize("NFKD", raw).encode("ASCII", "ignore").decode("ASCII")


def _operator_field(operador: Dict[str, Any], *keys: str) -> Optional[Any]:
    for k in keys:
        if k in operador:
            return operador[k]
    return None


def _resolve_operator_name_from_interacao(interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
    """Helper provisório até que todo o pipeline de nomes use um serviço único."""
    return (
        _operator_field(operador, "name", "nome", "agentName")
        or interacao.get("agentName")
        or interacao.get("operator_name")
    )


class BaseSyncRule(ABC):
    """
    Interface base (Strategy) para as regras de download/skip do Sync da Huawei.
    Cada regra deve validar de forma isolada se a ligação deve ser ignorada.
    """
    @abstractmethod
    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        """Retorna uma string (motivo do skip) se deve pular, ou None se pode continuar."""
        pass


class HuaweiRegistrationRule(BaseSyncRule):
    """
    Bloqueia o download se o operador não tiver um ID da Huawei registrado.
    Evita processar chamadas de usuários que não existem no nosso banco (Painel).
    """
    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        if not _operator_field(operador, "id_huawei", "idHuawei"):
            return "operator_huawei_not_registered"
        if operador.get("huawei_registered") is not True:
            return "operator_huawei_not_registered"
        return None


class MondelezExclusionRule(BaseSyncRule):
    """
    Bloqueia qualquer chamada originada pelo setor Mondelez.
    Regra de negócio explícita exigida pelo cliente.
    """
    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        sector_text = " ".join(
            str(operador.get(key) or "")
            for key in ("setor", "sectorId", "displaySector", "sector", "escala")
        )
        if "mondelez" in _normalize_identity_text(sector_text):
            return "mondelez"
        return None


class TestOperatorRule(BaseSyncRule):
    """
    Filtra usuários ou ramais usados para testes internos (ex: 'Teste URA', 'OP VALIDO').
    """
    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        nome = _resolve_operator_name_from_interacao(interacao, operador)
        nome_lower = str(nome or "").lower()
        if "teste" in nome_lower or "op valido" in nome_lower:
            return "test_operator"
        return None


class UnregisteredOperatorRule(BaseSyncRule):
    """
    Rejeita chamadas de operadores que foram explicitamente desativados para auditoria
    (auditavel_db = False) no painel de gestão.
    """
    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        if operador.get("auditavel_db") is False:
            return "operator_not_registered"
        return None


class SectorDirectionRule(BaseSyncRule):
    """
    Centraliza a avaliação de Setores Restritos (ex: Células que não são de Telefonia)
    e a avaliação de direção da chamada (Inbound/Outbound) comparando com as AUTOMATION_RULES.
    """
    def __init__(self, automation_rules: dict):
        self.automation_rules = automation_rules

    def _operator_sector_id(self, operador: Dict[str, Any]) -> str:
        raw_setor = str(
            operador.get("setor")
            or operador.get("sectorId")
            or operador.get("displaySector")
            or operador.get("sector")
            or ""
        ).strip()
        escala = str(operador.get("escala") or "").strip()
        supervisor = str(operador.get("supervisor") or "").strip()
        
        raw_sector_slug = normalize_huawei_sector(raw_setor)
        if raw_sector_slug in OUTBOUND_ONLY_RISK_SECTORS or raw_sector_slug in NON_TELEFONIA_SECTORS:
            return raw_sector_slug

        mapped_sector: Optional[str] = None
        try:
            mapped_sector = operators.map_db_sector_to_classification_sector(
                raw_setor,
                escala,
                supervisor,
            )
        except Exception:
            logger.debug("Sync Huawei: falha ao mapear setor do operador.", exc_info=True)
        return normalize_huawei_sector(mapped_sector or raw_setor)

    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        sector_slug = self._operator_sector_id(operador)
        
        if sector_slug in NON_TELEFONIA_SECTORS:
            return "non_telefonia_sector"

        classified_direction = resolve_huawei_is_call_in(interacao)

        # Regra Dinâmica: Setores de Risco (Exclusivamente Ativos)
        if sector_slug in OUTBOUND_ONLY_RISK_SECTORS:
            if classified_direction is None:
                return "direction_unknown"
            if classified_direction is True:
                return "risk_inbound"
            return None

        # Regra Estática: Compatibilidade com AUTOMATION_RULES legadas
        regra = self.automation_rules.get(sector_slug)
        if regra:
            expected_direction = str(regra.get("call_direction") or "").strip().upper()
            if expected_direction in {"INBOUND", "OUTBOUND"}:
                if classified_direction is None:
                    return "direction_unknown"
                is_inbound = (expected_direction == "INBOUND")
                if classified_direction != is_inbound:
                    return "direction_mismatch"
            return None

        # Fail-Safe: Se o setor é totalmente desconhecido e a ligação é Receptiva, bloqueia preventivamente.
        # Caso seja uma URA/Ativa, deixamos passar para cair na triagem e alertar os supervisores.
        if not sector_slug and classified_direction is True:
            return "receptiva_setor_desconhecido"

        return None


class SyncDownloadGatekeeper:
    """
    Orquestrador responsável por decidir se uma ligação recém-encontrada na Huawei
    deve ser baixada ou não (se for ignorada, será salva como `status=skipped`).
    Utiliza uma Chain of Responsibility onde a primeira Strategy a falhar define o motivo.
    """
    
    def __init__(self, automation_rules: dict):
        self.rules: List[BaseSyncRule] = [
            HuaweiRegistrationRule(),
            MondelezExclusionRule(),
            TestOperatorRule(),
            UnregisteredOperatorRule(),
            SectorDirectionRule(automation_rules),
        ]

    def check_eligibility(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        """
        Executa o pipeline de regras. 
        Retorna uma string (skip_reason) caso rejeitado, ou None se aprovado para download.
        """
        for rule in self.rules:
            skip_reason = rule.check(interacao, operador)
            if skip_reason is not None:
                return skip_reason
        return None
