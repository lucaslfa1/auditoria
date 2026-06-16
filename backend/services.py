"""Fachada de auditoria — ponto de entrada histórico de transcrição/avaliação.

Este módulo NÃO define lógica própria: ele só re-exporta nomes dos pacotes
``core/`` (config, transcrição, avaliação, auditoria, export) e de alguns utils,
para que código antigo que faz ``from services import X`` ou ``import services``
continue funcionando após a refatoração que moveu a implementação para ``core/``.

Cada módulo de ``core/`` define ``__all__`` (incluindo nomes com prefixo ``_``),
então o ``from core.X import *`` aqui re-exporta exatamente o que está listado lá.
Os imports nomeados no fim cobrem símbolos que callers historicamente importavam
de ``services`` mas que vivem fora de ``core/``.

Sem custo de API próprio (apenas re-exporta). As funções re-exportadas de
transcrição/avaliação é que podem chamar Azure OpenAI/Speech — ver os módulos de
``core/``.
"""

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
