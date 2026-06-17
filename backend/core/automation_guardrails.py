"""Guardrails de elegibilidade da automacao Huawei.

Fonte unica para decidir se um item vindo do sync Huawei pode seguir para
transcricao/auditoria. A mesma regra precisa valer para sync, Telefonia e
automacao: setores fora de telefonia nao auditam; setores de risco auditam
apenas chamadas ativas/outbound; quando a direcao e desconhecida, bloqueia.

Manutencao:
- novos setores entram em `core.huawei_direction`, nao neste modulo;
- para Huawei, use primeiro o setor real do operador no metadata. O setor
  previsto pela IA pode estar errado e nao pode liberar receptiva de risco.
"""

from typing import Optional, Tuple, Dict, Any
from core.huawei_direction import (
    normalize_huawei_sector,
    resolve_huawei_is_call_in,
    OUTBOUND_ONLY_RISK_SECTORS,
    NON_TELEFONIA_SECTORS
)

class AutomationGatekeeper:
    """Valida se um item da fila Huawei pode iniciar a auditoria automatica."""

    @staticmethod
    def _get_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
        """Metadata normalizado; regras de negocio do sync vivem nesse payload."""
        metadata = item.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def check_eligibility(cls, item: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """Retorna None quando o item pode auditar; senao (motivo, setor).

        Ordem dos gates:
        1. Origem: Apenas chamadas da telefonia (Huawei) passam por essa regra.
        2. Setor: Bloqueia imediatamente setores que não pertencem à telefonia.
        3. Risco x Receptiva: Garante que setores de risco não auditem chamadas receptivas.
        """
        metadata = cls._get_metadata(item)
        
        # Uploads manuais e outras origens nao passam pelos bloqueios Huawei.
        if metadata.get("origem") != "huawei_sync":
            return None

        # Para Huawei, o bloqueio de direcao deve usar o setor real do operador
        # (cadastro RH/Huawei). A classificacao IA (`setor_previsto`) pode errar
        # para "cadastro"/"logistica" e nao pode liberar receptiva de risco.
        raw_sector = (
            metadata.get("operator_sector_id")
            or metadata.get("operator_sector_real")
            or item.get("setor_previsto")
            or metadata.get("sector_id")
            or metadata.get("setor")
        )
        sector = normalize_huawei_sector(raw_sector)

        # Setores fora de Telefonia nunca viram auditoria automatica Huawei.
        if sector in NON_TELEFONIA_SECTORS:
            return "setor_nao_telefonia", sector
            
        # Fora dos setores outbound-only, a direcao da chamada nao bloqueia.
        if sector not in OUTBOUND_ONLY_RISK_SECTORS:
            return None

        # Pre-triagem de audio pode bloquear antes da heuristica definitiva.
        audio_pre_triage = str(metadata.get("audio_direction_pre_triage") or "").strip().lower()
        if audio_pre_triage == "inbound_quarantine":
            return "receptiva_pretriagem_audio", sector

        direction = resolve_huawei_is_call_in(metadata)

        if direction is True:
            return "receptiva_setor_risco", sector
            
        if direction is False or audio_pre_triage == "outbound":
            return None
            
        # Fail-closed: setor de risco + direcao desconhecida nao pode auditar.
        return "direcao_desconhecida_setor_risco", sector
