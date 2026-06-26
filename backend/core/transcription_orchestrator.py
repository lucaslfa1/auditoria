"""Orquestracao pura (sem I/O) do pipeline de transcricao multi-estrategia.

Papel no fluxo: concentra a logica deterministica que decide COMO transcrever um
audio — em que ordem tentar as estrategias (fast / whisper / gpt4o_diarize / sdk
/ hybrid_dual), se um resultado e "valido o suficiente" e como prepara o audio
para o Azure. As chamadas pagas (Azure OpenAI / Speech) ficam encapsuladas nos
callbacks injetados (`execute_strategy`, `convert_to_mp3`, etc.) — este modulo em
si NAO faz rede/disco diretamente, so coordena.

CUSTO DE API: indireto. Este modulo nao chama Azure por conta propria, mas
`run_transcription_pipeline` invoca o callback `execute_strategy`, que tipicamente
dispara a transcricao paga (Azure Fast Transcription / Whisper / GPT-4o-transcribe
/ Speech SDK). O custo depende de quantas estrategias da ordem sao tentadas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional
import unicodedata

from schemas import AuditAlert


TranscriptionSegments = list[dict]
StrategyExecutor = Callable[[str], TranscriptionSegments]
Deduplicator = Callable[[TranscriptionSegments], TranscriptionSegments]
SegmentsValidator = Callable[[TranscriptionSegments], bool]
SegmentsScorer = Callable[[TranscriptionSegments], int]
TextNormalizer = Callable[[str], str]
LogFn = Callable[[str], None]
ShouldPreprocessAudio = Callable[[int, str], bool]
Mp3Converter = Callable[[bytes, str], bytes]
WavConverter = Callable[[bytes], bytes]


_BAS_POLICE_ALERT_IDS = {"BAS-PRIORITARIO-POLICIA", "BAS-POLICIAL"}


def _normalize_alert_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().strip()


def _is_bas_police_interlocutor_alert(alert: Optional[AuditAlert]) -> bool:
    """True somente para o alerta BAS em que o interlocutor real e policial."""
    if not alert:
        return False

    alert_id = _normalize_alert_text(alert.id).replace("_", "-").replace(" ", "-")
    if alert_id in _BAS_POLICE_ALERT_IDS:
        return True

    # O POP 4.1.10 e compartilhado no catalogo oficial; sem uma pista de BAS,
    # ele nao deve trocar a persona da diarizacao para Policia.
    haystack = _normalize_alert_text(f"{alert.id or ''} {alert.label or ''} {alert.context or ''}")
    return alert_id == "4.1.10" and "BAS" in haystack and (
        "POLICIA" in haystack or "POLICIAL" in haystack
    )


@dataclass(frozen=True)
class PreparedAudio:
    """Audio pronto para envio ao Azure: bytes ja convertidos + MIME efetivo."""

    audio_file: bytes
    mime_type: str


def infer_interlocutor_label(alert: Optional[AuditAlert], explicit_label: Optional[str] = None) -> str:
    """Deduz o rotulo do interlocutor (segundo falante) a partir do alerta.

    Se `explicit_label` for fornecido, vence sempre. Caso contrario, casa
    palavras-chave no id/label/contexto do alerta e mapeia para um rotulo de
    negocio ("Ponto de Apoio", "Transportadora", "Cliente", etc.). A persona
    "Policia" fica restrita ao alerta BAS policial; nos demais setores,
    alertas com contexto policial continuam com interlocutor "Motorista".
    Default "Motorista" quando nada casa. Sem efeitos colaterais.
    """
    if explicit_label:
        return explicit_label

    haystack = ""
    if alert:
        haystack = _normalize_alert_text(f"{alert.id or ''} {alert.label or ''} {alert.context or ''}").lower()

    if "ponto de apoio" in haystack or "posto" in haystack:
        return "Ponto de Apoio"
    if _is_bas_police_interlocutor_alert(alert):
        return "Policia"
    if "antecedentes" in haystack:
        return "Interlocutor"
    if "transportadora" in haystack or "cadastro" in haystack:
        return "Transportadora"
    if "cliente" in haystack:
        return "Cliente"
    return "Motorista"


def _parse_timestamp_seconds(value: str) -> Optional[float]:
    """Converte timestamp em string para segundos (float).

    Aceita "HH:MM:SS", "MM:SS" ou um numero puro de segundos; tolera colchetes
    em volta (ex.: "[00:12]"). Retorna None quando nao consegue parsear.
    """
    raw = str(value or "").strip().strip("[]")
    if not raw:
        return None

    parts = raw.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)
        if len(parts) == 2:
            minutes, seconds = parts
            return (int(minutes) * 60) + float(seconds)
        return float(raw)
    except Exception:
        return None


def transcription_looks_valid(
    segments: TranscriptionSegments,
    normalize_for_dedupe: TextNormalizer,
) -> bool:
    """Heuristica de "validacao forte": True quando a transcricao parece util.

    Aplica varios filtros anti-lixo: rejeita resultados vazios ou curtos demais
    (<=2 segmentos e <180 chars), com repeticao dominante (>=70% de um mesmo
    texto normalizado, sinal de alucinacao em loop) ou com timestamps degenerados
    (poucos starts distintos / maioria perto de zero). `normalize_for_dedupe` e
    o normalizador de texto injetado, usado na deteccao de repeticao. Funcao pura.
    """
    if not isinstance(segments, list) or not segments:
        return False

    texts: list[str] = []
    starts: list[float] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if text:
            texts.append(text)
        parsed_start = _parse_timestamp_seconds(str(segment.get("start", "")).strip())
        if parsed_start is not None:
            starts.append(parsed_start)

    if not texts:
        return False

    total_chars = sum(len(text) for text in texts)
    if len(texts) <= 2 and total_chars < 180:
        return False

    normalized: list[str] = []
    for text in texts:
        normalized_text = normalize_for_dedupe(text)
        if normalized_text:
            normalized.append(normalized_text)
    if len(normalized) >= 8:
        counts: dict[str, int] = {}
        for text in normalized:
            counts[text] = counts.get(text, 0) + 1
        dominant_count = max(counts.values()) if counts else 0
        if dominant_count / len(normalized) >= 0.70:
            return False

    if len(starts) >= 10:
        unique_starts = len(set(starts))
        if unique_starts <= max(2, int(len(starts) * 0.15)):
            return False
        near_zero = sum(1 for timestamp in starts if timestamp <= 1.0)
        if near_zero / len(starts) >= 0.60:
            return False

    return True


def score_transcription_segments(segments: TranscriptionSegments) -> int:
    """Pontua segmentos para escolher o "melhor candidato" entre estrategias.

    Score = total de caracteres de texto + (numero de starts distintos * 20).
    Quanto maior, melhor. Usado como criterio de desempate quando nenhuma
    estrategia passa na validacao forte. Funcao pura.
    """
    if not isinstance(segments, list):
        return 0
    total_chars = 0
    unique_starts = set()
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        total_chars += len(text)
        start = str(segment.get("start", "")).strip()
        if start:
            unique_starts.add(start)
    return total_chars + (len(unique_starts) * 20)


import logging
logger = logging.getLogger(__name__)

def prepare_audio_for_azure(
    audio_file: bytes,
    mime_type: str,
    *,
    preprocess_enabled: bool,
    should_preprocess_audio: ShouldPreprocessAudio,
    convert_to_mp3: Mp3Converter,
    convert_to_wav: WavConverter,
    accepted_mime_types: set[str],
    log: LogFn = None,
) -> PreparedAudio:
    """Prepara o audio para o Azure: pre-processa e garante MIME aceito.

    Quando o pre-processamento esta ligado e `should_preprocess_audio` aprova,
    tenta converter para MP3 via `convert_to_mp3` (so adota o resultado se ficou
    MENOR que o original). Se o MIME resultante nao estiver em
    `accepted_mime_types`, faz fallback convertendo para WAV via `convert_to_wav`.

    Toda conversao real (e seu eventual custo de CPU) acontece nos callbacks
    injetados; este modulo so decide quando aplica-los. `log` recebe mensagens de
    progresso (default: logger do modulo). Retorna `PreparedAudio` com os bytes e
    o MIME efetivos. Falhas no pre-processamento sao logadas e ignoradas (mantem
    o audio original).
    """
    azure_mime = (mime_type or "audio/wav").strip().lower() or "audio/wav"
    azure_audio = audio_file
    log_fn = log if log else logger.info

    if preprocess_enabled and should_preprocess_audio(len(azure_audio), azure_mime):
        try:
            optimized_audio = convert_to_mp3(azure_audio, azure_mime)
            if optimized_audio and len(optimized_audio) > 0 and len(optimized_audio) < len(azure_audio):
                reduction_pct = 100.0 - ((len(optimized_audio) / len(azure_audio)) * 100.0)
                log_fn(
                    f"[Transcription] Audio otimizado para Azure: {len(azure_audio)//1024}KB -> "
                    f"{len(optimized_audio)//1024}KB ({reduction_pct:.1f}% menor)"
                )
                azure_audio = optimized_audio
                azure_mime = "audio/mpeg"
        except Exception as exc:
            logger.error(f"[Transcription] Falha no pre-processamento de audio: {exc}")

    if azure_mime not in accepted_mime_types:
        azure_audio = convert_to_wav(audio_file)
        azure_mime = "audio/wav"

    return PreparedAudio(audio_file=azure_audio, mime_type=azure_mime)


def build_strategy_order(
    engine: str,
    *,
    include_sdk: bool,
    include_whisper: bool,
    include_gpt4o_diarize: bool,
) -> list[str]:
    """Monta a ordem de estrategias a tentar, conforme a engine configurada.

    `engine` ("fast", "sdk", "gpt4o_diarize", "whisper", "hybrid_dual" ou outro)
    define a preferencia; o default atual do sistema e "fast". As flags
    `include_*` removem estrategias indisponiveis (dependencia ausente, recurso
    desligado). "hybrid_dual" so entra se gpt4o_diarize E whisper estiverem
    disponiveis. Retorna a lista de estrategias deduplicada, na ordem de tentativa.
    Funcao pura.
    """
    if engine == "hybrid_dual":
        preferred_order = ["hybrid_dual"]
    elif engine == "sdk":
        preferred_order = ["sdk", "fast", "gpt4o_diarize", "whisper"]
    elif engine == "gpt4o_diarize":
        preferred_order = ["gpt4o_diarize", "fast", "whisper", "sdk"]
    elif engine == "whisper":
        preferred_order = ["whisper", "fast", "gpt4o_diarize", "sdk"]
    elif engine == "fast":
        preferred_order = ["fast", "whisper", "gpt4o_diarize", "sdk"]
    else:
        preferred_order = ["fast", "gpt4o_diarize", "whisper", "sdk"]

    run_order: list[str] = []
    for strategy in preferred_order:
        if strategy == "sdk" and not include_sdk:
            continue
        if strategy == "whisper" and not include_whisper:
            continue
        if strategy == "gpt4o_diarize" and not include_gpt4o_diarize:
            continue
        if strategy == "hybrid_dual" and not (include_gpt4o_diarize and include_whisper):
            continue
        if strategy not in run_order:
            run_order.append(strategy)
    return run_order


def run_transcription_pipeline(
    run_order: list[str],
    *,
    execute_strategy: StrategyExecutor,
    deduplicate_segments: Deduplicator,
    looks_valid: SegmentsValidator,
    score_segments: SegmentsScorer,
    log: LogFn = print,
    return_metadata: bool = False,
    allow_best_candidate_fallback: bool = False,
) -> TranscriptionSegments | tuple[TranscriptionSegments, dict[str, Any]]:
    """Executa as estrategias de `run_order` em sequencia ate uma ser valida.

    Para cada estrategia chama `execute_strategy` (que faz a transcricao real, em
    geral chamada paga ao Azure), depois `deduplicate_segments`, pontua com
    `score_segments` e valida com `looks_valid`. Retorna o primeiro resultado que
    passa na validacao forte. Erros por estrategia (ImportError = dependencia
    ausente; demais excecoes) sao capturados e registrados em `attempts`, sem
    interromper as proximas tentativas.

    Params/efeitos:
    - log: callback de log (default `print`).
    - return_metadata: quando True, retorna `(segments, metadata)` com a
      estrategia escolhida, o provedor e a lista de `attempts`; quando False,
      retorna so os segmentos.
    - allow_best_candidate_fallback: quando True e nenhuma estrategia passa na
      validacao forte, devolve o candidato de maior score em vez de falhar.

    Levanta RuntimeError quando nenhuma estrategia produz resultado aceitavel e o
    fallback de melhor candidato esta desligado (ou nao ha candidatos).
    """
    strategy_messages = {
        "sdk": "Speech SDK ConversationTranscriber",
        "whisper": "Azure Whisper",
        "gpt4o_diarize": "GPT-4o-transcribe-diarize",
        "fast": "Azure Fast Transcription",
    }

    candidates: list[tuple[str, TranscriptionSegments]] = []
    errors: list[str] = []
    attempts: list[dict[str, Any]] = []

    def _build_metadata(selected_strategy: str, selected_reason: str) -> dict[str, Any]:
        return {
            "selected_strategy": selected_strategy,
            "selected_provider": strategy_messages.get(selected_strategy, selected_strategy),
            "selected_reason": selected_reason,
            "attempts": attempts,
        }

    for strategy in run_order:
        try:
            log(f"[Transcription] Tentando {strategy_messages.get(strategy, strategy)}")
            result = deduplicate_segments(execute_strategy(strategy))
            candidate_score = score_segments(result)
            is_valid = looks_valid(result)
            candidates.append((strategy, result))
            attempts.append(
                {
                    "strategy": strategy,
                    "provider": strategy_messages.get(strategy, strategy),
                    "status": "accepted" if is_valid else "insufficient",
                    "score": candidate_score,
                }
            )
            if is_valid:
                metadata = _build_metadata(strategy, "accepted")
                return (result, metadata) if return_metadata else result

            errors.append(f"{strategy}: resultado insuficiente")
            log(f"[Transcription] {strategy} retornou resultado insuficiente")
        except ImportError:
            if strategy == "sdk":
                errors.append(f"{strategy}: azure-cognitiveservices-speech nao instalado")
            else:
                errors.append(f"{strategy}: dependencia ausente")
            attempts.append(
                {
                    "strategy": strategy,
                    "provider": strategy_messages.get(strategy, strategy),
                    "status": "error",
                    "error": errors[-1],
                }
            )
        except Exception as exc:
            errors.append(f"{strategy}: {exc}")
            attempts.append(
                {
                    "strategy": strategy,
                    "provider": strategy_messages.get(strategy, strategy),
                    "status": "error",
                    "error": str(exc),
                }
            )
            log(f"[Transcription] Falha no modo {strategy}: {exc}")

    if candidates and allow_best_candidate_fallback:
        best_strategy, best_result = max(candidates, key=lambda item: score_segments(item[1]))
        log(f"[Transcription] Nenhum modo passou na validacao forte; usando melhor candidato: {best_strategy}")
        metadata = _build_metadata(best_strategy, "best_candidate")
        return (best_result, metadata) if return_metadata else best_result

    raise RuntimeError(f"Transcription failed: {' | '.join(errors)}")
