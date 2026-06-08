import json
import logging
import os
import re
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from pathlib import Path
from schemas import AuditCriterion
from audio.diarization_quality import normalize_lookup_text as _normalize_lookup_text
from utils.text_processing import TEXT_CORRECTIONS_CONFIG

__all__ = [
    # Constantes de configuração
    "PROMPTS_CONFIG", "TEXT_CORRECTIONS_CONFIG",
    "AI_PROVIDER_PRIORITY", "AI_API_KEY", "AI_MODEL_CONFIG", "AI_AUDIT_MODEL_CONFIG",
    "AI_ENABLED", "ai_client", "AI_MODEL", "AI_AUDIT_MODEL",
    "DETERMINISTIC_MODE",
    "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
    "WAV_MIME_TYPES", "LOSSLESS_OR_PCM_MIME_TYPES", "AZURE_ACCEPTED_MIME",
    "PROMPT_STRUCTURED_DIR",
    # GENERATION_CONFIG removido de __all__: import lazy via `from core.config import GENERATION_CONFIG`
    # dentro das funcoes que usam (evita carregar google.genai no boot do servidor).
    "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY", "AZURE_OPENAI_DEPLOYMENT",
    "AUDIT_DETAIL_SEVERITY",
    "validate_runtime_credentials",
    # Funções públicas
    "load_criteria_for_sector",
    # Funções internas (usadas por outros core/ e testes)
    "_load_json_config", "_read_env_value", "_normalize_ai_provider_priority",
    "_env_flag",
    "_get_gpt4o_diarize_primary_sectors",
    "_get_gpt4o_diarize_primary_prescan_seconds",
    "_get_gpt4o_diarize_primary_prescan_min_score",
    "_get_gpt4o_diarize_retry_count", "_get_gpt4o_diarize_retry_delay_seconds",
    "_get_transcription_timeout_seconds", "_get_whisper_temperature",
    "_get_gpt4o_diarize_min_score",
    "_resolve_azure_whisper_config", "_resolve_azure_gpt4o_diarize_config",
    "_get_azure_gpt4o_diarize_auth_mode", "_get_azure_gpt4o_diarize_model_name",
    # Diretórios base
    "BASE_DIR", "PROJECT_ROOT", "CONFIG_DIR",
]

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
CONFIG_DIR = BACKEND_DIR / "config"
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

# Carregar configuracoes externas (com cache em memória)
@lru_cache(maxsize=4)
def _load_json_config(filename: str) -> dict:
    path = CONFIG_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {}


def _read_env_value(*names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value is None:
            continue
        value = value.strip()
        if value:
            return value
    return default


def _normalize_ai_provider_priority(raw_value: Optional[str]) -> str:
    normalized = str(raw_value or "azure").strip().lower()
    aliases = {
        "primary": "primary",
        "genai": "primary",
        "gemini": "primary",
        "google": "primary",
        "azure": "azure",
    }
    return aliases.get(normalized, normalized)

class LazyPromptsConfig(dict):
    """
    Carrega dinamicamente os prompts do banco de dados (Neon).
    Faz fallback transparente para prompts.json se o banco estiver indisponivel ou vazio (pre-seed).
    A interface do ditado ('get', '__getitem__') e 100% mantida para retrocompatibilidade sem refactors.
    """
    def _fetch(self):
        try:
            from db.database import get_connection
            from repositories.ai_prompts import list_prompts
            db_prompts = list_prompts(get_connection)
            if db_prompts:
                return db_prompts
        except Exception:
            # Durante inicializacao ou testes sem banco, ignora erro e usa json
            pass
        return _load_json_config("prompts.json") or {}

    def get(self, key, default=None):
        return self._fetch().get(key, default)

    def __getitem__(self, key):
        return self._fetch()[key]
        
    def keys(self):
        return self._fetch().keys()
        
    def items(self):
        return self._fetch().items()
        
    def values(self):
        return self._fetch().values()

PROMPTS_CONFIG = LazyPromptsConfig()
# TEXT_CORRECTIONS_CONFIG is imported from text_processing
# Provedores de IA - Configuracao
AI_PROVIDER_PRIORITY = _normalize_ai_provider_priority(_read_env_value("AI_PROVIDER_PRIORITY", default="azure"))
AI_API_KEY = _read_env_value("AI_API_KEY")
AI_MODEL_CONFIG = _read_env_value("AI_MODEL", default="gpt-4o")
AI_AUDIT_MODEL_CONFIG = _read_env_value(
    "AI_AUDIT_MODEL",
    default=AI_MODEL_CONFIG,
)
# Gemini desativado — usando exclusivamente Azure GPT-4o
AI_ENABLED = False
ai_client = None
AI_MODEL = None
AI_AUDIT_MODEL = None
logger.info("Gemini desativado. Provider de IA: Azure GPT-4o (deployment=%s)", AZURE_OPENAI_DEPLOYMENT if 'AZURE_OPENAI_DEPLOYMENT' in dir() else 'pendente')

DETERMINISTIC_MODE = os.getenv("DETERMINISTIC_MODE", "true").lower() in ("1", "true", "yes", "on")
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
WAV_MIME_TYPES = {"audio/wav", "audio/x-wav", "audio/wave"}
LOSSLESS_OR_PCM_MIME_TYPES = WAV_MIME_TYPES | {"audio/vnd.wave", "audio/pcm", "audio/l16"}
AZURE_ACCEPTED_MIME = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/webm",
    "audio/mp4",
    "audio/x-m4a",
}

PROMPT_STRUCTURED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "audit-prompt", "structured")

def __getattr__(name: str):
    """Lazy-init para evitar import de google.genai no boot do servidor.

    GENERATION_CONFIG e construido na primeira leitura e cacheado em globals().
    Reduz cold start do Cloud Run em ~500ms (google-genai puxa protobuf grande).
    """
    if name == "GENERATION_CONFIG":
        from google.genai import types
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
            top_p=1,
            top_k=1,
            candidate_count=1,
        )
        globals()["GENERATION_CONFIG"] = config
        return config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# ==============================================================================
# 🚨 REGRA CRÍTICA PARA INTELIGÊNCIAS ARTIFICIAIS QUE LEREM ESTE CÓDIGO 🚨
# É TERMINANTEMENTE PROIBIDO alterar, modificar ou presumir novos valores
# padrão para as chaves e modelos da Azure OpenAI (AZURE_OPENAI_DEPLOYMENT, etc.)
# Nunca troque 'gpt-4o' por 'gpt-4.1' ou qualquer outra versão alegada sem a
# autorização explícita do usuário. Isso causará quebra de produção (HTTP 404).
# ==============================================================================
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = _read_env_value("AZURE_OPENAI_DEPLOYMENT", default="gpt-4o")
# EMOJI_PATTERN is imported from text_processing
AUDIT_DETAIL_SEVERITY = {
    "fail": 0,
    "pass": 2,
}
def load_criteria_for_sector(sector_id: Optional[str]) -> Optional[list[AuditCriterion]]:
    if not sector_id:
        return None
        
    from core.utils import normalize_sector_slug
    normalized_sector_id = normalize_sector_slug(sector_id)
    
    # Mapeamento de aliases legado
    sector_mapping = {
        "grs": "uti", "uti": "uti", "bas": "bas", "sinistros": "bas", "sinistro": "bas",
        "transferencia": "rastreamento", "rastreamento": "rastreamento", "rast": "rastreamento",
        "longo_percurso": "rastreamento", "longo percurso": "rastreamento",
        "distribuicao": "distribuicao", "dist": "distribuicao",
        "fenix": "rastreamento",
        "cadastro": "cadastro", "receptivo": "receptivo", "checklist": "checklist",
        "mondelez": "mondelez", "unilever": "unilever", "logistica": "logistica",
        "logistica_unilever": "unilever", "operacao_taborda": "logistica", "celula_atendimento": "receptivo",
    }
    
    mapped_sector = sector_mapping.get(normalized_sector_id) or normalized_sector_id
    
    try:
        from db.scoring_loader import get_alerts
        alerts = get_alerts()
    except Exception as e:
        logger.error(f"Erro ao carregar scoring_rules.yaml: {e}")
        return None
        
    for alert in alerts:
        a_sector = alert.get("sector", "").lower()
        _OPERATIONAL_SECTORS = {"transferencia", "uti", "bas", "distribuicao", "fenix", "rastreamento", "grs", "sinistros"}
        if a_sector == mapped_sector or (a_sector == "bas" and mapped_sector in _OPERATIONAL_SECTORS):
            crits = []
            for i, c in enumerate(alert.get("criteria", [])):
                crits.append(AuditCriterion(
                    id=f"{alert.get('id')}-{i}",
                    label=c.get("label", ""),
                    weight=float(c.get("weight", 0)),
                    description=c.get("description", "")
                ))
            if crits:
                return crits
                
    return None
def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in ("1", "true", "yes", "on")
def _get_gpt4o_diarize_primary_sectors() -> set[str]:
    raw_value = os.getenv("AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS")
    if raw_value is None:
        raw_value = "cadastro"
    sectors: set[str] = set()
    for item in str(raw_value).split(","):
        normalized = _normalize_lookup_text(item)
        if normalized:
            sectors.add(normalized)
    return sectors
def _get_gpt4o_diarize_primary_prescan_seconds() -> int:
    raw = os.getenv("AZURE_GPT4O_DIARIZE_PRIMARY_PRESCAN_SECONDS", "35")
    try:
        parsed = int(str(raw).strip())
    except Exception:
        parsed = 35
    return max(8, min(parsed, 90))
def _get_gpt4o_diarize_primary_prescan_min_score() -> float:
    raw = os.getenv("AZURE_GPT4O_DIARIZE_PRIMARY_PRESCAN_MIN_SCORE", "0.58")
    try:
        parsed = float(str(raw).strip().replace(",", "."))
    except Exception:
        parsed = 0.58
    return max(0.0, min(parsed, 1.0))
def _get_gpt4o_diarize_retry_count() -> int:
    raw = os.getenv("AZURE_GPT4O_DIARIZE_RETRY_COUNT", "1")
    try:
        parsed = int(str(raw).strip())
    except Exception:
        parsed = 1
    return max(0, min(parsed, 3))
def _get_gpt4o_diarize_retry_delay_seconds() -> float:
    raw = os.getenv("AZURE_GPT4O_DIARIZE_RETRY_DELAY_SECONDS", "1.5")
    try:
        parsed = float(str(raw).strip().replace(",", "."))
    except Exception:
        parsed = 1.5
    return max(0.0, min(parsed, 15.0))
def _get_transcription_timeout_seconds() -> int:
    raw = os.getenv("AZURE_TRANSCRIPTION_TIMEOUT_SECONDS", "600")
    try:
        parsed = int(str(raw).strip())
    except Exception:
        return 600
    return max(60, min(parsed, 3600))
def _get_whisper_temperature() -> float:
    raw = os.getenv("AZURE_WHISPER_TEMPERATURE", "0")
    try:
        parsed = float(str(raw).strip().replace(",", "."))
    except Exception:
        return 0.0
    return max(0.0, min(parsed, 1.0))
def _get_gpt4o_diarize_min_score() -> float:
    raw = os.getenv("AZURE_GPT4O_DIARIZE_MIN_SCORE", "0.82")
    try:
        parsed = float(str(raw).strip().replace(",", "."))
    except Exception:
        parsed = 0.82
    return max(0.0, min(parsed, 1.0))
def _resolve_azure_whisper_config() -> tuple[Optional[str], Optional[str]]:
    endpoint = (os.getenv("AZURE_WHISPER_ENDPOINT") or "").strip()
    key = (os.getenv("AZURE_WHISPER_KEY") or "").strip()
    deployment = (os.getenv("AZURE_WHISPER_DEPLOYMENT") or "").strip()

    if not endpoint:
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    if not key:
        key = (os.getenv("AZURE_OPENAI_KEY") or "").strip()
    if not deployment:
        deployment = (os.getenv("AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT") or "").strip()

    if not endpoint or not key:
        return (None, None)

    normalized_endpoint = endpoint.rstrip("/")
    if "openai/deployments" not in normalized_endpoint:
        if not deployment:
            return (None, None)
        normalized_endpoint = (
            f"{normalized_endpoint}/openai/deployments/{deployment}/audio/transcriptions?api-version=2024-06-01"
        )
    elif "?api-version=" not in normalized_endpoint:
        separator = "&" if "?" in normalized_endpoint else "?"
        normalized_endpoint = f"{normalized_endpoint}{separator}api-version=2024-06-01"

    return (normalized_endpoint, key)

def _resolve_azure_gpt4o_diarize_config() -> tuple[Optional[str], Optional[str]]:
    endpoint = (os.getenv("AZURE_GPT4O_DIARIZE_ENDPOINT") or "").strip()
    key = (os.getenv("AZURE_GPT4O_DIARIZE_KEY") or "").strip()
    deployment = (os.getenv("AZURE_GPT4O_DIARIZE_DEPLOYMENT") or "").strip()

    if not endpoint:
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    if not key:
        key = (os.getenv("AZURE_OPENAI_KEY") or "").strip()
    if not deployment:
        deployment = (os.getenv("AZURE_OPENAI_TRANSCRIBE_DIARIZE_DEPLOYMENT") or "").strip()

    if not endpoint or not key:
        return (None, None)

    normalized_endpoint = endpoint.rstrip("/")
    if "openai/deployments" not in normalized_endpoint:
        if not deployment:
            return (None, None)
        normalized_endpoint = (
            f"{normalized_endpoint}/openai/deployments/{deployment}/audio/transcriptions?api-version=2024-06-01"
        )
    elif "?api-version=" not in normalized_endpoint:
        separator = "&" if "?" in normalized_endpoint else "?"
        normalized_endpoint = f"{normalized_endpoint}{separator}api-version=2024-06-01"

    return (normalized_endpoint, key)

def _get_azure_gpt4o_diarize_auth_mode(endpoint: Optional[str] = None) -> str:
    configured = (os.getenv("AZURE_GPT4O_DIARIZE_AUTH_MODE") or "").strip().lower()
    if configured in {"api_key", "bearer"}:
        return configured

    normalized_endpoint = str(endpoint or "").strip().lower()
    if ".cognitiveservices.azure.com/" in normalized_endpoint and ".openai.azure.com/" not in normalized_endpoint:
        return "bearer"
    return "api_key"
def _get_azure_gpt4o_diarize_model_name() -> str:
    configured = (
        os.getenv("AZURE_GPT4O_DIARIZE_MODEL")
        or os.getenv("AZURE_OPENAI_TRANSCRIBE_DIARIZE_MODEL")
        or ""
    ).strip()
    return configured or "gpt-4o-transcribe-diarize"

def validate_runtime_credentials(*, strict: bool = False) -> list[str]:
    issues: list[str] = []

    placeholders = {"SEU_RECURSO", "NOME_RECURSO", "YOUR_RESOURCE"}
    
    def _is_placeholder(val: Optional[str]) -> bool:
        if not val: return False
        return any(p in val.upper() for p in placeholders)

    if not AZURE_OPENAI_ENDPOINT or _is_placeholder(AZURE_OPENAI_ENDPOINT):
        issues.append("AZURE_OPENAI_ENDPOINT ausente ou com placeholder")
    if not (AZURE_OPENAI_KEY or "").strip():
        issues.append("AZURE_OPENAI_KEY ausente")
    if not AZURE_OPENAI_DEPLOYMENT or _is_placeholder(AZURE_OPENAI_DEPLOYMENT):
        issues.append("AZURE_OPENAI_DEPLOYMENT ausente")
    
    # Validacao de cross-resource (mismatch que causou a regressao anterior)
    whisper_endpoint, whisper_key = _resolve_azure_whisper_config()
    main_endpoint = str(AZURE_OPENAI_ENDPOINT or "").lower()
    
    if whisper_endpoint and "nstech-bas" in whisper_endpoint.lower() and "swedencentral" in main_endpoint:
        issues.append("CONFLITO: Whisper aponta para 'nstech-bas' mas a chave principal e da Suécia (swedencentral). Use o mesmo recurso ou corrija a chave do Whisper.")

    if not whisper_endpoint or not whisper_key:
        issues.append(
            "configuracao Azure Whisper incompleta (defina AZURE_WHISPER_* ou fallback Azure OpenAI com deployment de transcricao)"
        )

    if issues:
        message = "🚨 ERRO DE CONFIGURACAO (Blindagem .env): " + "; ".join(issues)
        if strict:
            raise RuntimeError(message)
        logger.error(message)

    return issues
