# services.py - Fachada para manter compatibilidade com imports existentes.
# Callers que fazem `from services import X` ou `import services` continuam funcionando.
#
# Cada módulo core/ define __all__ (incluindo nomes com prefixo _), então
# `from X import *` re-exporta tudo que está listado lá.

from core.config import *  # noqa: F401,F403
from core.transcription import *  # noqa: F401,F403
from core.evaluation import *  # noqa: F401,F403
from core.audit import *  # noqa: F401,F403
from core.export import *  # noqa: F401,F403

# Re-exports transitivos: símbolos que callers historicamente importam de services
# mas que são definidos fora de core/.
from utils.text_processing import (  # noqa: F401
    deduplicate_transcription_segments,
    filter_hallucinations,
    normalize_company_name,
    normalize_speaker_prefix,
    remove_emojis,
)
from core.transcription_orchestrator import infer_interlocutor_label  # noqa: F401
from core.audit_evaluator import AuditEvaluationDependencies  # noqa: F401
from schemas import AuditAlert, AuditCriterion  # noqa: F401
