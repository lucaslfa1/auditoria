import json
import sys
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class HuaweiEvents:
    @staticmethod
    def log_event(event_type: str, call_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None, severity: str = "INFO"):
        """
        Emite um log estruturado em JSON para o stdout, compatível com o GCP Cloud Logging.
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
