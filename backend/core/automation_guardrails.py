from typing import Optional, Tuple, Dict, Any
from core.huawei_direction import (
    normalize_huawei_sector,
    resolve_huawei_is_call_in,
    OUTBOUND_ONLY_RISK_SECTORS,
    NON_TELEFONIA_SECTORS
)

"""
================================================================================
MÓDULO DE REGRAS DE ROTEAMENTO E GUARDA (GUARDRAILS) DA AUTOMAÇÃO
================================================================================
Este módulo implementa os princípios do SOLID (Single Responsibility Principle),
isolando as regras que definem se uma chamada em fila PODE ou NÃO PODE ser
processada pela automação. 

Anteriormente, essa lógica ficava misturada com a orquestração do banco de 
dados e filas no `automation.py`, o que causava fragilidade (regressões quando
qualquer código vizinho era alterado).

Instruções de Manutenção:
1. Se surgir um novo setor que precise de restrição de automação, atualize
   as constantes em `core.huawei_direction` e não aqui.
2. Se a lógica de bloqueio por direção mudar, adicione um novo método verificador
   nesta classe.
"""

class AutomationGatekeeper:
    """
    Classe responsável por auditar se um item da fila (chamada telefônica)
    está elegível para iniciar o processo de transcrição/avaliação de IA.
    
    Funciona como uma 'corrente de responsabilidade' (Chain of Responsibility) 
    simplificada, onde várias validações independentes ocorrem.
    """

    @staticmethod
    def _get_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrai os metadados da chamada de forma segura, garantindo que
        sempre retornará um dicionário válido.
        
        Instrução: Sempre acesse dados sensíveis do enfileiramento via metadata,
        nunca no topo do JSON, pois as regras de negócio vivem no metadata.
        """
        metadata = item.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def check_eligibility(cls, item: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """
        Método principal que avalia um item da fila.
        Retorna `None` se a chamada está LIBERADA para automação.
        Retorna uma tupla (Motivo do Bloqueio, Setor) se a chamada deve ser BLOQUEADA.
        
        Ordem de Validação (Pipeline):
        1. Origem: Apenas chamadas da telefonia (Huawei) passam por essa regra.
        2. Setor: Bloqueia imediatamente setores que não pertencem à telefonia.
        3. Risco x Receptiva: Garante que setores de risco não auditem chamadas receptivas.
        """
        metadata = cls._get_metadata(item)
        
        # REGRA 1: Filtro de Origem
        # Se a ligação não veio da sincronização automática da Huawei (ex: upload manual),
        # as regras restritivas abaixo não se aplicam e a chamada é liberada.
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

        # REGRA 2: Setores Fora do Escopo de Telefonia (ex: Célula de Atendimento / Receptivo)
        if sector in NON_TELEFONIA_SECTORS:
            return "setor_nao_telefonia", sector
            
        # REGRA 3: Filtro de Direção para Setores de Risco (Apenas Ativas)
        # Se o setor NÃO é um setor de risco, a automação está liberada independente da direção.
        if sector not in OUTBOUND_ONLY_RISK_SECTORS:
            return None

        # Análise de Pré-Triagem de Áudio
        # Se o pipeline de áudio já sinalizou previamente que a chamada cheira a receptiva.
        audio_pre_triage = str(metadata.get("audio_direction_pre_triage") or "").strip().lower()
        if audio_pre_triage == "inbound_quarantine":
            return "receptiva_pretriagem_audio", sector

        # Análise Definitiva de Direção usando a Heurística Correta
        direction = resolve_huawei_is_call_in(metadata)

        # Se for explicitamente receptiva (True), bloqueia.
        if direction is True:
            return "receptiva_setor_risco", sector
            
        # Se for explicitamente outbound (False) ou a pré-triagem confirmou outbound, libera.
        if direction is False or audio_pre_triage == "outbound":
            return None
            
        # Fallback de Segurança: Se não conseguimos definir a direção, preferimos bloquear 
        # (Fail-Safe) para evitar vazamento de chamadas receptivas nos setores de risco.
        return "direcao_desconhecida_setor_risco", sector
