"""Gatekeeper de elegibilidade do download no Sync da Huawei.

Decide, ANTES de baixar uma ligacao recem-descoberta na Huawei, se ela deve
ser processada ou ignorada (quando ignorada, o sync grava `status=skipped`
com o motivo). A decisao e modelada como um pipeline de regras (Strategy +
Chain of Responsibility): a primeira regra que falhar define o `skip_reason`.

Regras aplicadas, na ordem:
1. `HuaweiRegistrationRule` — operador sem ID Huawei registrado.
2. `MondelezExclusionRule` — setor Mondelez (regra de negocio do cliente).
3. `TestOperatorRule` — usuarios/ramais de teste interno.
4. `UnregisteredOperatorRule` — operador desativado para auditoria.
5. `SectorDirectionRule` — setor nao-telefonia e compatibilidade de direcao
   (inbound/outbound) com as AUTOMATION_RULES e setores de risco.

Sem custo de API (so logica/leitura de cadastro em memoria via
`operators`; nao chama Azure nem a rede da Huawei).
"""

from typing import Optional, Dict, Any, List
import logging
import re
from abc import ABC, abstractmethod

from repositories import operators
from core.huawei_direction import (
    NON_TELEFONIA_SECTORS,
    OUTBOUND_ONLY_RISK_SECTORS,
    resolve_huawei_is_call_in,
    resolve_counterpart_number,
    is_brazilian_mobile,
    normalize_huawei_sector,
)

logger = logging.getLogger(__name__)


def _resolve_operator_sector_slug(operador: Dict[str, Any]) -> str:
    """Resolve o slug de setor canônico do operador (setor cru + escala/supervisor).

    Centraliza a lógica usada por SectorDirectionRule e BasOitivaRule: usa o setor
    cru (vários aliases de chave); se já for um setor de risco/não-telefonia
    conhecido devolve direto; senão mapeia via cadastro e normaliza.
    """
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
        """Retorna "operator_huawei_not_registered" se o operador nao tem ID
        Huawei (`id_huawei`/`idHuawei`) ou `huawei_registered` nao e True;
        caso contrario None."""
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
        """Retorna "mondelez" se algum campo de setor do operador contiver
        "mondelez" (apos normalizar acentos/caixa); caso contrario None."""
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
        """Retorna "test_operator" se o nome resolvido contiver "teste" ou
        "op valido" (caixa-insensivel); caso contrario None."""
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
        """Retorna "operator_not_registered" quando `auditavel_db` e
        explicitamente False (operador desativado para auditoria); caso
        contrario None."""
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
        """Resolve o slug de setor canonico do operador (ver _resolve_operator_sector_slug)."""
        return _resolve_operator_sector_slug(operador)

    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        """Avalia setor e direcao da chamada e devolve o motivo de skip, ou None.

        Possiveis retornos:
        - "non_telefonia_sector": setor nao e de telefonia.
        - "direction_unknown": setor de risco / AUTOMATION_RULES com direcao
          fixa, mas a direcao da chamada nao pode ser determinada.
        - "risk_inbound": setor exclusivamente ativo (OUTBOUND_ONLY_RISK) que
          recebeu uma chamada receptiva.
        - "direction_mismatch": direcao da chamada diverge da exigida pela
          AUTOMATION_RULE do setor.
        - "receptiva_setor_desconhecido": setor desconhecido + chamada
          receptiva (fail-safe; ativas/URA passam para cair na triagem).
        - None: chamada aprovada para download.
        """
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


class BasOitivaRule(BaseSyncRule):
    """
    A BAS audita SOMENTE ligação policial. Oitiva (ligação com caminhoneiro), que
    em regra é feita para celular, deve ser descartada. Números institucionais/
    policiais (ex: 011190) e fixos são mantidos; a whitelist `police_numbers`
    permite manter eventuais ligações policiais feitas para celular.
    """

    def __init__(self, police_numbers: Optional[set] = None):
        self.police_digits = {
            re.sub(r"\D+", "", str(number))
            for number in (police_numbers or set())
            if re.sub(r"\D+", "", str(number))
        }

    def check(self, interacao: Dict[str, Any], operador: Dict[str, Any]) -> Optional[str]:
        """Retorna "oitiva_bas" quando a contraparte de uma ligação da BAS é
        celular e não está na whitelist policial; caso contrário None."""
        if _resolve_operator_sector_slug(operador) != "bas":
            return None
        counterpart = resolve_counterpart_number(interacao)
        if not counterpart:
            return None
        counterpart_digits = re.sub(r"\D+", "", counterpart)
        if counterpart_digits and counterpart_digits in self.police_digits:
            return None
        if is_brazilian_mobile(counterpart):
            return "oitiva_bas"
        return None


class SyncDownloadGatekeeper:
    """
    Orquestrador responsável por decidir se uma ligação recém-encontrada na Huawei
    deve ser baixada ou não (se for ignorada, será salva como `status=skipped`).
    Utiliza uma Chain of Responsibility onde a primeira Strategy a falhar define o motivo.
    """

    def __init__(self, automation_rules: dict, police_numbers: Optional[set] = None):
        self.rules: List[BaseSyncRule] = [
            HuaweiRegistrationRule(),
            MondelezExclusionRule(),
            TestOperatorRule(),
            UnregisteredOperatorRule(),
            BasOitivaRule(police_numbers),
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
