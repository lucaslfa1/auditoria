"""Logging estruturado de eventos da integracao Huawei.

Centraliza a emissao de eventos do pipeline de download/sync da Huawei em
formato JSON para o stdout, no padrao consumido pelo GCP Cloud Logging (Cloud
Run). Cada evento carrega `event_type`, `call_id`, `severity` e um `context`
livre, permitindo filtrar/agrupar no Cloud Logging por categoria de problema
(ex.: `DOWNLOAD_FAILED` vs `OBS_VOICE_DIR_EMPTY`).

Sem custo de API (so escreve em stdout e no logger padrao do processo).
"""

import json
import sys
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class HuaweiEvents:
    """Emissor de eventos estruturados da integracao Huawei (so logging)."""

    @staticmethod
    def log_event(event_type: str, call_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None, severity: str = "INFO"):
        """Emite um evento estruturado em JSON no stdout (e tambem no logger).

        Params:
        - event_type: nome da categoria do evento (ex.: "DOWNLOAD_FAILED",
          "DOWNLOAD_RECOVERED", "OBS_VOICE_DIR_EMPTY").
        - call_id: callId da Huawei relacionado, ou None (vira "N/A" no log).
        - context: dict livre com dados auxiliares (metodo, erro, data, bucket,
          etc.); serializado dentro do evento.
        - severity: "INFO", "WARNING" ou "ERROR" — define tanto o campo
          `severity` do JSON quanto o nivel usado no logger padrao.

        Efeitos colaterais: escreve uma linha JSON em `sys.stdout` (com flush,
        para o Cloud Run capturar como log estruturado) e tambem registra uma
        mensagem textual no logger do modulo para debug local. Nao retorna nada.
        """
        log_entry = {
            "severity": severity,
            "event_type": event_type,
            "call_id": call_id or "N/A",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "context": context or {}
        }
        
        # Escreve no stdout para o Cloud Run capturar como log estruturado
        sys.stdout.write(json.dumps(log_entry) + "\n")
        sys.stdout.flush()

        # Também mantém o log textual no logger padrão para debug local facilitado
        msg = f"HUAWEI_EVENT: {event_type} | CallID: {call_id} | Context: {context}"
        if severity == "ERROR":
            logger.error(msg)
        elif severity == "WARNING":
            logger.warning(msg)
        else:
            logger.info(msg)
