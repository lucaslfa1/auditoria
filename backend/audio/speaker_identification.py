import json
import logging
import os
import re
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from audio.speaker_models import RawPhrase, SegmentoFormatado, SpeakerStats, DiarizationAnalysis
import audio.speaker_constants as constants
from audio.speaker_constants import LlmSpeakerMapper
from audio.speaker_heuristics import (
    eh_ditado_alfanumerico,
    eh_handoff_interlocutor,
    eh_pergunta,
    eh_pergunta_ou_direcionamento_operador,
    eh_resposta_curta_interlocutor_contextual,
    eh_resposta_curta_motorista,
    eh_resposta_curta_operador,
    eh_segmento_telefonia,
    eh_token_ruido_curto,
    inferir_speaker_sem_diarizacao,
    normalizar_texto,
    pontuar_motorista,
    pontuar_operador,
    tem_indicador_motorista_forte,
    tem_indicador_operador_forte,
    tem_indicador_policial,
    tem_intro_operador,
)
from audio.speaker_normalization import (
    _clamp_confidence,
    _parse_float,
    formatar_timestamp,
    quebrar_texto_em_clausulas,
    unir_textos,
)

logger = logging.getLogger(__name__)

def mapear_speakers_por_id(phrases: List[RawPhrase], operator_label: str, driver_label: str) -> Dict[int, str]:
    return analisar_diarizacao_por_ids(phrases, operator_label, driver_label).speaker_map

def _merge_id_tuples(first: Tuple[int, ...], second: Tuple[int, ...]) -> Tuple[int, ...]:
    return tuple(sorted({sid for sid in first + second if isinstance(sid, int) and sid >= 0}))

def _risk_rank(risk: str) -> int:
    normalized = (risk or "").strip().lower()
    if normalized == "high":
        return 3
    if normalized == "medium":
        return 2
    if normalized == "low":
        return 1
    return 0

def _merge_risk(first: str, second: str) -> str:
    return first if _risk_rank(first) >= _risk_rank(second) else second

def _coletar_stats_por_id(phrases: List[RawPhrase], ids: List[int]) -> Dict[int, SpeakerStats]:
    stats_by_id = {sid: SpeakerStats() for sid in ids}

    for phrase in phrases:
        if phrase.speaker_id < 0 or phrase.speaker_id not in stats_by_id:
            continue
        if eh_segmento_telefonia(phrase.texto_normalizado):
            continue

        stat = stats_by_id[phrase.speaker_id]
        score_op = pontuar_operador(phrase.texto_normalizado)
        score_mot = pontuar_motorista(phrase.texto_normalizado)

        perguntas = 0
        if eh_pergunta_ou_direcionamento_operador(phrase.texto_normalizado):
            score_op += 2
            perguntas = 1

        resposta_curta = 0
        if eh_resposta_curta_motorista(phrase.texto_normalizado):
            score_mot += 1
            resposta_curta = 1

        intro_op = 0
        if tem_intro_operador(phrase.texto_normalizado):
            intro_op = 1
            score_op += 2

        forte_operador = 1 if tem_indicador_operador_forte(phrase.texto_normalizado) else 0
        forte_interlocutor = 1 if (
            tem_indicador_motorista_forte(phrase.texto_normalizado)
            or eh_ditado_alfanumerico(phrase.texto_normalizado)
        ) else 0

        stat.primeira_fala_segundos = min(stat.primeira_fala_segundos, phrase.timestamp.total_seconds())
        stat.score_operador += score_op
        stat.score_interlocutor += score_mot
        stat.perguntas += perguntas
        stat.intro_operador += intro_op
        stat.total_frases += 1
        stat.total_duracao_seconds += max(0.0, phrase.duration_seconds)
        stat.respostas_curtas_interlocutor += resposta_curta
        stat.turnos_operador_fortes += forte_operador
        stat.turnos_interlocutor_fortes += forte_interlocutor

    return stats_by_id

def _avaliar_speaker_por_heuristica(
    speaker_id: int,
    stats: SpeakerStats,
    operator_label: str,
    driver_label: str,
) -> Dict[str, object]:
    bonus_inicio = 2 if stats.primeira_fala_segundos <= 25 and (
        stats.intro_operador > 0 or stats.score_operador >= stats.score_interlocutor + 2
    ) else 0
    score_operador = (
        stats.score_operador
        + (stats.perguntas * 2)
        + (stats.intro_operador * 3)
        + (stats.turnos_operador_fortes * 2)
        + bonus_inicio
    )
    score_interlocutor = (
        stats.score_interlocutor
        + stats.respostas_curtas_interlocutor
        + (stats.turnos_interlocutor_fortes * 2)
    )
    delta = score_operador - score_interlocutor
    confidence = (
        0.54
        + min(0.24, abs(delta) * 0.04)
        + min(0.10, stats.total_frases * 0.02)
        + min(0.10, stats.total_duracao_seconds / 45.0)
    )
    if stats.intro_operador > 0:
        confidence += 0.12
    if stats.turnos_operador_fortes > 0 or stats.turnos_interlocutor_fortes > 0:
        confidence += 0.06

    role = driver_label
    if (
        delta >= 2
        or stats.intro_operador > 0
        or (
            stats.turnos_operador_fortes > stats.turnos_interlocutor_fortes
            and score_operador >= score_interlocutor + 1
        )
    ):
        role = operator_label

    ambiguous = (
        abs(delta) <= 1
        and stats.intro_operador == 0
        and stats.turnos_operador_fortes == stats.turnos_interlocutor_fortes
    )
    if stats.total_frases <= 1 and stats.total_duracao_seconds < 2.2:
        ambiguous = True

    if ambiguous:
        confidence = min(confidence, 0.64)

    return {
        "speaker_id": speaker_id,
        "role": role,
        "confidence": _clamp_confidence(confidence, 0.35, 0.98),
        "ambiguous": ambiguous,
        "operator_score": score_operador,
        "driver_score": score_interlocutor,
        "delta": delta,
    }

def _tem_dialogo_duas_pessoas_estavel(
    ids: List[int],
    final_map: Dict[int, str],
    stats_by_id: Dict[int, SpeakerStats],
    operator_label: str,
    driver_label: str,
) -> bool:
    if len(ids) != 2:
        return False

    operator_ids = [sid for sid in ids if final_map.get(sid) == operator_label]
    driver_ids = [sid for sid in ids if final_map.get(sid) == driver_label]
    if len(operator_ids) != 1 or len(driver_ids) != 1:
        return False

    operator_stats = stats_by_id[operator_ids[0]]
    driver_stats = stats_by_id[driver_ids[0]]
    if operator_stats.total_frases < 1 or driver_stats.total_frases < 1:
        return False

    operator_evidence = (
        operator_stats.intro_operador > 0
        or operator_stats.turnos_operador_fortes > 0
        or operator_stats.perguntas > 0
        or operator_stats.score_operador >= operator_stats.score_interlocutor + 2
    )
    driver_evidence = (
        driver_stats.turnos_interlocutor_fortes > 0
        or driver_stats.respostas_curtas_interlocutor > 0
        or driver_stats.total_frases >= 2
        or driver_stats.total_duracao_seconds >= 3.0
    )
    return operator_evidence and driver_evidence

def _tem_handoff_ponto_de_apoio(phrases: List[RawPhrase], driver_label: str) -> bool:
    driver_normalizado = normalizar_texto(driver_label)
    if "ponto de apoio" not in driver_normalizado and "posto" not in driver_normalizado:
        return False

    return any(
        eh_handoff_interlocutor(phrase.texto_normalizado)
        for phrase in phrases
        if phrase.speaker_id >= 0 and not eh_segmento_telefonia(phrase.texto_normalizado)
    )

def _normalizar_role_llm(role_raw: object, operator_label: str, driver_label: str) -> Optional[str]:
    normalized = normalizar_texto(str(role_raw or ""))
    operator_norm = normalizar_texto(operator_label)
    driver_norm = normalizar_texto(driver_label)

    if not normalized:
        return None
    if normalized == operator_norm or "operador" in normalized or "central" in normalized:
        return operator_label
    if normalized == driver_norm or driver_norm in normalized or "interlocutor" in normalized or "motorista" in normalized:
        return driver_label
    return None

def _montar_resumo_speakers_para_llm(
    ids: List[int],
    stats_by_id: Dict[int, SpeakerStats],
    heuristic_by_id: Dict[int, Dict[str, object]],
    phrases: List[RawPhrase],
) -> str:
    samples_by_id: Dict[int, List[str]] = {sid: [] for sid in ids}
    for phrase in phrases:
        if phrase.speaker_id not in samples_by_id:
            continue
        if eh_segmento_telefonia(phrase.texto_normalizado):
            continue
        if phrase.texto.strip() and len(samples_by_id[phrase.speaker_id]) < 3:
            samples_by_id[phrase.speaker_id].append(phrase.texto.strip())

    resumo: List[str] = []
    for sid in ids:
        stats = stats_by_id[sid]
        heuristic = heuristic_by_id[sid]
        samples = " | ".join(samples_by_id.get(sid, []))
        resumo.append(
            f"Speaker {sid}: primeira_fala={stats.primeira_fala_segundos:.1f}s; "
            f"frases={stats.total_frases}; duracao={stats.total_duracao_seconds:.1f}s; "
            f"score_operador={heuristic['operator_score']}; score_interlocutor={heuristic['driver_score']}; "
            f"perguntas={stats.perguntas}; intros_operador={stats.intro_operador}; "
            f"heuristica={heuristic['role']} ({heuristic['confidence']:.2f}); "
            f"amostras={samples}"
        )
    return "\n".join(resumo)

def _montar_trecho_llm(phrases: List[RawPhrase]) -> str:
    if not phrases:
        return ""

    inicio = min(
        (
            phrase.timestamp.total_seconds()
            for phrase in phrases
            if phrase.speaker_id >= 0 and not eh_segmento_telefonia(phrase.texto_normalizado)
        ),
        default=0.0,
    )
    trecho: List[str] = []
    for phrase in phrases:
        if phrase.speaker_id < 0:
            continue
        if eh_segmento_telefonia(phrase.texto_normalizado):
            continue
        delta = phrase.timestamp.total_seconds() - inicio
        if trecho and delta > 120 and len(trecho) >= 24:
            break
        if len(trecho) >= 60:
            break
        trecho.append(
            f"[{formatar_timestamp(phrase.timestamp)}] "
            f"Speaker {phrase.speaker_id}: {phrase.texto}"
        )
    return "\n".join(trecho)

def _parse_llm_persona_mapping(
    payload: object,
    ids: List[int],
    operator_label: str,
    driver_label: str,
) -> Tuple[Dict[int, str], Dict[int, float], Tuple[int, ...]]:
    speaker_map: Dict[int, str] = {}
    confidence_by_id: Dict[int, float] = {}
    ambiguous_ids: set[int] = set()
    allowed_ids = set(ids)

    if not isinstance(payload, dict):
        return speaker_map, confidence_by_id, ()

    personas = payload.get("personas")
    if isinstance(personas, list):
        for persona in personas:
            if not isinstance(persona, dict):
                continue
            role = _normalizar_role_llm(
                persona.get("role"),
                operator_label,
                driver_label,
            )
            if role is None:
                continue
            confidence = _clamp_confidence(
                _parse_float(persona.get("confidence"), 0.78),
                0.0,
                1.0,
            )
            raw_ids = persona.get("speaker_ids", persona.get("speakerIds", []))
            if not isinstance(raw_ids, list):
                continue
            for raw_sid in raw_ids:
                try:
                    sid = int(raw_sid)
                except (TypeError, ValueError):
                    continue
                if sid in allowed_ids:
                    speaker_map[sid] = role
                    confidence_by_id[sid] = confidence

    for key, value in payload.items():
        if not str(key).startswith("speaker_"):
            continue
        try:
            sid = int(str(key).replace("speaker_", ""))
        except ValueError:
            continue
        if sid not in allowed_ids:
            continue
        role = _normalizar_role_llm(value, operator_label, driver_label)
        if role is None:
            continue
        speaker_map[sid] = role
        confidence_by_id.setdefault(sid, 0.76)

    raw_ambiguous = payload.get("ambiguous_ids", payload.get("ambiguousIds", []))
    if isinstance(raw_ambiguous, list):
        for raw_sid in raw_ambiguous:
            try:
                sid = int(raw_sid)
            except (TypeError, ValueError):
                continue
            if sid in allowed_ids:
                ambiguous_ids.add(sid)

    return speaker_map, confidence_by_id, tuple(sorted(ambiguous_ids))

def _tentar_mapear_speakers_com_llm(
    phrases: List[RawPhrase],
    ids: List[int],
    stats_by_id: Dict[int, SpeakerStats],
    heuristic_by_id: Dict[int, Dict[str, object]],
    operator_label: str,
    driver_label: str,
) -> Tuple[Dict[int, str], Dict[int, float], Tuple[int, ...]]:
    if len(ids) <= 1:
        return {}, {}, ()

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    azure_key = os.getenv("AZURE_OPENAI_KEY", "").strip()
    deployment = (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-4o").strip()
    if not azure_endpoint or not azure_key:
        return {}, {}, ()

    trecho = _montar_trecho_llm(phrases)
    if not trecho.strip():
        return {}, {}, ()

    resumo = _montar_resumo_speakers_para_llm(ids, stats_by_id, heuristic_by_id, phrases)
    prompt = f"""
Voce esta mapeando IDs diarizados para apenas duas pessoas reais em uma ligacao telefonica de monitoramento logistico.

Tarefa:
- Agrupe varios speaker_ids na mesma pessoa quando houver fragmentacao.
- Identifique qual persona e '{operator_label}' e qual persona e '{driver_label}'.
- Se algum speaker_id estiver realmente duvidoso, liste-o em ambiguous_ids em vez de inventar.

Regras obrigatorias:
1. Autoidentificacao institucional ("Opentech", "central", "rastreamento", "base de sinistro") vale mais do que quem falou primeiro.
2. Quem pede senha, placa, localizacao, previsao, motivo da parada, orientacoes operacionais ou fala em nome da central tende a ser '{operator_label}'.
3. Reclamar, falar alto ou interromper NAO transforma automaticamente alguem em '{driver_label}'.
4. Um mesmo humano pode aparecer em multiplos speaker_ids quando a diarizacao fragmenta a voz.
5. Nao force um mapeamento 1:1. O correto pode ser, por exemplo, Speaker 1 + Speaker 3 = '{operator_label}'.
6. SEPARACAO DE GENERO: Se a transcricao mostra claramente uma voz feminina (ex: saudacao padrao da central) e uma voz masculina (ex: motorista) misturadas no mesmo speaker_id, a diarizacao falhou. Mantenha a separacao logica baseada no conteudo da frase e mande esse speaker_id para 'ambiguous_ids' se o risco for alto.

Responda APENAS JSON valido neste formato:
{{
  "personas": [
{{"role": "{operator_label}", "speaker_ids": [1, 3], "confidence": 0.93, "evidence": ["motivo"]}},
{{"role": "{driver_label}", "speaker_ids": [0, 2], "confidence": 0.88, "evidence": ["motivo"]}}
  ],
  "ambiguous_ids": [4]
}}

Resumo por speaker:
{resumo}

Trecho inicial:
{trecho}
"""

    try:
        from openai import AzureOpenAI

        from core import cost_guard
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "speaker_mapping")
        with AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version="2025-01-01-preview",
        ) as client:
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=500,
                timeout=30,
            )
        parsed = json.loads(response.choices[0].message.content)
        return _parse_llm_persona_mapping(parsed, ids, operator_label, driver_label)
    except Exception as exc:
        logger.warning("[LLM Speaker Mapping] Falha: %s. Fallback heuristica...", exc)
        return {}, {}, ()

def analisar_diarizacao_por_ids(
    phrases: List[RawPhrase],
    operator_label: str,
    driver_label: str,
    *,
    llm_mapper: Optional[LlmSpeakerMapper] = None,
) -> DiarizationAnalysis:
    ids = sorted(set(phrase.speaker_id for phrase in phrases if phrase.speaker_id >= 0))
    if not ids:
        return DiarizationAnalysis(
            raw_speaker_count=0,
            swap_risk="high",
            notes=("no_native_diarization",),
        )

    stats_by_id = _coletar_stats_por_id(phrases, ids)
    heuristic_by_id = {
        sid: _avaliar_speaker_por_heuristica(sid, stats_by_id[sid], operator_label, driver_label)
        for sid in ids
    }

    final_map = {sid: str(heuristic_by_id[sid]["role"]) for sid in ids}
    final_conf = {sid: float(heuristic_by_id[sid]["confidence"]) for sid in ids}
    ambiguous_ids = {sid for sid in ids if bool(heuristic_by_id[sid]["ambiguous"])}
    notes: List[str] = []

    if not any(role == operator_label for role in final_map.values()):
        best_operator_sid = max(
            ids,
            key=lambda sid: (
                int(heuristic_by_id[sid]["operator_score"]),
                int(stats_by_id[sid].intro_operador),
                int(stats_by_id[sid].perguntas),
                -stats_by_id[sid].primeira_fala_segundos,
            ),
        )
        final_map[best_operator_sid] = operator_label
        final_conf[best_operator_sid] = max(final_conf.get(best_operator_sid, 0.0), 0.58)
        ambiguous_ids.discard(best_operator_sid)
        notes.append("operator_backfilled_from_heuristic")

    if len(ids) > 1 and not any(role == driver_label for role in final_map.values()):
        fallback_driver_sid = min(
            ids,
            key=lambda sid: (
                int(heuristic_by_id[sid]["delta"]),
                int(heuristic_by_id[sid]["operator_score"]),
                -int(heuristic_by_id[sid]["driver_score"]),
            ),
        )
        final_map[fallback_driver_sid] = driver_label
        final_conf[fallback_driver_sid] = min(final_conf.get(fallback_driver_sid, 0.7), 0.68)
        ambiguous_ids.add(fallback_driver_sid)
        notes.append("driver_backfilled_from_heuristic")

    mapper_fn = llm_mapper if llm_mapper is not None else _tentar_mapear_speakers_com_llm
    llm_map, llm_conf, llm_ambiguous = mapper_fn(
        phrases,
        ids,
        stats_by_id,
        heuristic_by_id,
        operator_label,
        driver_label,
    )
    if llm_map:
        notes.append("llm_many_to_one_mapping")

    for sid, llm_role in llm_map.items():
        heuristic_role = final_map.get(sid)
        heuristic_conf = final_conf.get(sid, 0.55)
        llm_confidence = _clamp_confidence(llm_conf.get(sid, 0.78), 0.0, 1.0)

        if heuristic_role == llm_role:
            final_map[sid] = llm_role
            final_conf[sid] = max(heuristic_conf, (heuristic_conf + llm_confidence) / 2.0)
            ambiguous_ids.discard(sid)
            continue

        if llm_confidence >= 0.82 or heuristic_conf <= 0.62:
            final_map[sid] = llm_role
            final_conf[sid] = max(0.58, (heuristic_conf + llm_confidence) / 2.0)
        else:
            final_map[sid] = heuristic_role or llm_role
            final_conf[sid] = heuristic_conf
        ambiguous_ids.add(sid)

    ambiguous_ids.update(llm_ambiguous)

    for sid in ids:
        final_map.setdefault(sid, driver_label)
        final_conf[sid] = _clamp_confidence(final_conf.get(sid, 0.55), 0.35, 0.98)

    operator_ids = tuple(sorted(sid for sid in ids if final_map.get(sid) == operator_label))
    driver_ids = tuple(sorted(sid for sid in ids if final_map.get(sid) == driver_label))
    fragmented = len(ids) > 2 or len(operator_ids) > 1 or len(driver_ids) > 1
    stable_two_party = _tem_dialogo_duas_pessoas_estavel(
        ids,
        final_map,
        stats_by_id,
        operator_label,
        driver_label,
    )
    support_point_handoff = _tem_handoff_ponto_de_apoio(phrases, driver_label)
    if stable_two_party:
        notes.append("stable_two_party_dialogue")
    if support_point_handoff:
        notes.append("support_point_handoff_detected")

    risk_by_id: Dict[int, str] = {}
    for sid in ids:
        confidence = final_conf[sid]
        risk = "low"
        if len(ids) <= 1 or confidence < 0.52:
            risk = "high"
        elif sid in ambiguous_ids:
            risk = "medium" if stable_two_party or support_point_handoff else "high"
        elif fragmented or confidence < 0.78:
            risk = "medium"

        if stable_two_party and not fragmented and confidence >= 0.72 and risk == "medium":
            risk = "low"
        if support_point_handoff and final_map.get(sid) == driver_label and risk == "high" and confidence >= 0.58:
            risk = "medium"
        risk_by_id[sid] = risk

    if len(ids) <= 1 or any(risk == "high" for risk in risk_by_id.values()):
        swap_risk = "high"
    elif fragmented or any(risk == "medium" for risk in risk_by_id.values()):
        swap_risk = "medium"
    else:
        swap_risk = "low"
    if stable_two_party and not fragmented and swap_risk == "high":
        swap_risk = "medium"

    return DiarizationAnalysis(
        speaker_map=final_map,
        confidence_by_id=final_conf,
        role_speaker_ids={
            operator_label: operator_ids,
            driver_label: driver_ids,
        },
        ambiguous_ids=tuple(sorted(ambiguous_ids)),
        risk_by_id=risk_by_id,
        fragmented=fragmented,
        swap_risk=swap_risk,
        raw_speaker_count=len(ids),
        notes=tuple(notes),
    )

def classificar_speakers(phrases: List[RawPhrase], operator_label: str, driver_label: str) -> List[SegmentoFormatado]:
    analysis = analisar_diarizacao_por_ids(phrases, operator_label, driver_label)
    speaker_map = analysis.speaker_map
    segmentos: List[SegmentoFormatado] = []
    ultimo_speaker = operator_label
    ultimo_texto_normalizado = ""
    aguardando_resposta = False

    for phrase in phrases:
        source_ids: Tuple[int, ...] = ()
        persona_ids: Tuple[int, ...] = ()
        speaker_confidence = 0.0
        diarization_risk = "high"
        diarization_ambiguous = False

        if phrase.speaker_id >= 0:
            speaker = speaker_map.get(phrase.speaker_id, ultimo_speaker)
            source_ids = (phrase.speaker_id,)
            persona_ids = analysis.role_speaker_ids.get(speaker, source_ids) or source_ids
            speaker_confidence = analysis.confidence_by_id.get(phrase.speaker_id, 0.55)
            diarization_risk = analysis.risk_by_id.get(phrase.speaker_id, "medium")
            diarization_ambiguous = phrase.speaker_id in analysis.ambiguous_ids
        else:
            score_op = pontuar_operador(phrase.texto_normalizado)
            score_mot = pontuar_motorista(phrase.texto_normalizado)
            speaker, aguardando_resposta = inferir_speaker_sem_diarizacao(
                phrase.texto_normalizado,
                score_op,
                score_mot,
                ultimo_speaker,
                aguardando_resposta,
                ultimo_texto_normalizado,
                operator_label,
                driver_label,
            )
            speaker_confidence = _clamp_confidence(
                0.48 + min(0.30, abs(score_op - score_mot) * 0.08),
                0.35,
                0.80,
            )
            diarization_risk = "high" if speaker_confidence < 0.68 else "medium"

        segmentos.append(SegmentoFormatado(
            timestamp=phrase.timestamp,
            speaker=speaker,
            texto=phrase.texto,
            texto_normalizado=phrase.texto_normalizado,
            duracao_seconds=phrase.duration_seconds,
            source_speaker_ids=source_ids,
            persona_speaker_ids=persona_ids,
            speaker_confidence=speaker_confidence,
            diarization_risk=diarization_risk,
            diarization_ambiguous=diarization_ambiguous,
        ))
        ultimo_speaker = speaker
        ultimo_texto_normalizado = phrase.texto_normalizado
        if phrase.speaker_id >= 0:
            aguardando_resposta = (
                speaker == operator_label
                and eh_pergunta_ou_direcionamento_operador(phrase.texto_normalizado)
            )

    return segmentos

def _aplicar_override_heuristico(seg: SegmentoFormatado, novo_speaker: str) -> None:
    """Aplica o override do speaker e penaliza a confiança/risco da diarização para refletir a dúvida textual sobreposta à acústica."""
    if seg.speaker != novo_speaker:
        seg.speaker = novo_speaker
        seg.speaker_confidence = min(seg.speaker_confidence, 0.55)
        seg.diarization_risk = _merge_risk(seg.diarization_risk, "medium")
        seg.diarization_ambiguous = True

def corrigir_perguntas_operacionais(segmentos: List[SegmentoFormatado], operator_label: str, driver_label: str) -> List[SegmentoFormatado]:
    """Corrige perguntas operacionais que Azure rotulou como interlocutor.
    Quando Azure divide o operador em múltiplos speaker_ids, perguntas
    direcionadas (Qual placa? Que caminhão?) ficam como interlocutor.
    Também reclassifica ditados alfanuméricos após perguntas como interlocutor."""
    if len(segmentos) < 2:
        return segmentos

    res = list(segmentos)
    for i, seg in enumerate(res):
        t = seg.texto_normalizado
        score_op = pontuar_operador(t)
        score_mot = pontuar_motorista(t)

        # Perguntas operacionais rotuladas como interlocutor → promover a Operador
        if (seg.speaker == driver_label
            and eh_pergunta_ou_direcionamento_operador(t)
            and score_op >= 2 and score_op > score_mot
            and not tem_indicador_policial(t)
            and not any(x in t for x in ["ponto de apoio", "posto de apoio"])):
            # Verificar contexto: há um operador próximo antes ou depois?
            tem_op_proximo = False
            for k in range(max(0, i - 3), min(len(res), i + 3)):
                if k != i and res[k].speaker == operator_label:
                    tem_op_proximo = True
                    break
            if tem_op_proximo:
                _aplicar_override_heuristico(res[i], operator_label)

        # Ditados alfanuméricos rotulados como Operador após pergunta → rebaixar a interlocutor
        if (seg.speaker == operator_label
            and eh_ditado_alfanumerico(t)
            and not tem_indicador_operador_forte(t)):
            # Verificar se há uma pergunta do operador recente (dentro de 30s)
            for k in range(i - 1, max(-1, i - 5), -1):
                prev = res[k]
                delta = (seg.timestamp - prev.timestamp).total_seconds()
                if delta > 30:
                    break
                if (prev.speaker == operator_label
                    and eh_pergunta_ou_direcionamento_operador(prev.texto_normalizado)):
                    _aplicar_override_heuristico(res[i], driver_label)
                    break

    return res

def rebalancear_interlocutores_por_turno(segmentos: List[SegmentoFormatado], operator_label: str, driver_label: str) -> List[SegmentoFormatado]:
    if len(segmentos) < 3: return segmentos
    
    res = list(segmentos)
    for i in range(len(res) - 1):
        atual = res[i]
        if atual.speaker != operator_label or not eh_pergunta_ou_direcionamento_operador(atual.texto_normalizado):
            continue
            
        for j in range(i + 1, min(i + 2, len(res))):
            cand = res[j]
            delta = (cand.timestamp - atual.timestamp).total_seconds()
            if delta > 35: break
            
            if eh_pergunta_ou_direcionamento_operador(cand.texto_normalizado) and \
               tem_indicador_operador_forte(cand.texto_normalizado):
                break
                
            deve_ser_mot = (eh_resposta_curta_motorista(cand.texto_normalizado) or \
                           eh_resposta_curta_interlocutor_contextual(cand.texto_normalizado) or \
                           tem_indicador_motorista_forte(cand.texto_normalizado) or \
                           eh_ditado_alfanumerico(cand.texto_normalizado) or \
                           not eh_pergunta_ou_direcionamento_operador(cand.texto_normalizado))
            
            if deve_ser_mot and not tem_indicador_operador_forte(cand.texto_normalizado):
                _aplicar_override_heuristico(res[j], driver_label)
                if len(cand.texto_normalizado) >= 30 or cand.duracao_seconds >= 2.2:
                    break
    return res

def promover_turnos_operacionais(segmentos: List[SegmentoFormatado], operator_label: str, driver_label: str) -> List[SegmentoFormatado]:
    if len(segmentos) < 2:
        return segmentos

    res = list(segmentos)
    for i, atual in enumerate(res):
        if atual.speaker != driver_label:
            continue

        t = atual.texto_normalizado
        score_op = pontuar_operador(t)
        score_mot = pontuar_motorista(t)
        prev = res[i - 1] if i > 0 else None
        next_seg = res[i + 1] if i + 1 < len(res) else None

        if (
            eh_resposta_curta_interlocutor_contextual(t)
            and not tem_indicador_operador_forte(t)
        ):
            continue

        if (
            prev and prev.speaker == operator_label and eh_pergunta(prev.texto_normalizado)
            and eh_resposta_curta_interlocutor_contextual(t)
            and not tem_indicador_operador_forte(t)
        ):
            continue

        if tem_indicador_operador_forte(t) and score_op >= score_mot + 1:
            _aplicar_override_heuristico(res[i], operator_label)
            continue

        if prev and prev.speaker == operator_label:
            delta = (atual.timestamp - prev.timestamp).total_seconds()
            if delta <= 20 and (
                score_op >= score_mot + 1
                or any(x in t for x in ("no assunto do e mail", "pra gente saber", "ficamos no aguardo", "caso ele nao traga"))
            ):
                _aplicar_override_heuristico(res[i], operator_label)
                continue

            # Whisper costuma quebrar endereco em segmento separado logo apos fala do operador.
            if (
                delta <= 8
                and not eh_pergunta(prev.texto_normalizado)
                and any(x in prev.texto_normalizado for x in ("na rua", "no endereco", "fica na"))
                and re.search(r"\d{2,}", t)
                and not tem_indicador_motorista_forte(t)
            ):
                _aplicar_override_heuristico(res[i], operator_label)
                continue

        if (
            prev and prev.speaker == driver_label and eh_pergunta(prev.texto_normalizado)
            and eh_resposta_curta_operador(t)
            and not tem_indicador_motorista_forte(t)
        ):
            _aplicar_override_heuristico(res[i], operator_label)
            continue

        if (
            next_seg and next_seg.speaker == driver_label
            and eh_resposta_curta_operador(t)
            and any(x in next_seg.texto_normalizado for x in constants.RESPOSTAS_ACK_INTERLOCUTOR)
        ):
            _aplicar_override_heuristico(res[i], operator_label)
            continue

        if (
            next_seg and next_seg.speaker == driver_label
            and tem_indicador_operador_forte(t)
            and score_op >= score_mot + 1
        ):
            _aplicar_override_heuristico(res[i], operator_label)

    return res

def suavizar_troca_isolada_de_speaker(segmentos: List[SegmentoFormatado]) -> List[SegmentoFormatado]:
    if len(segmentos) < 3: return segmentos
    res = list(segmentos)
    for i in range(1, len(res) - 1):
        ant, atu, prox = res[i-1], res[i], res[i+1]
        if ant.speaker == prox.speaker and atu.speaker != ant.speaker:
            if (
                eh_pergunta_ou_direcionamento_operador(ant.texto_normalizado)
                and not tem_indicador_operador_forte(atu.texto_normalizado)
            ):
                continue
            if (
                eh_resposta_curta_interlocutor_contextual(atu.texto_normalizado)
                or tem_indicador_motorista_forte(atu.texto_normalizado)
            ):
                continue
            if (len(atu.texto_normalizado) <= 32 or atu.duracao_seconds <= 2.2) and \
               not eh_pergunta_ou_direcionamento_operador(atu.texto_normalizado):
                _aplicar_override_heuristico(res[i], ant.speaker)
    return res

# Marcadores que, no MEIO de um bloco sem pontuação, sinalizam o INÍCIO de um
# novo turno. Servem para separar turnos que o STT fundiu num único segmento sem
# pontuação (ex.: operador pede senha -> motorista nega -> operador pede CPF), caso
# em que quebrar_texto_em_clausulas (que só corta em .!?) devolve uma cláusula só.
# Cada âncora é uma sequência de palavras já normalizadas. Cortes em excesso são
# inofensivos: cláusulas do mesmo locutor recebem o mesmo rótulo e são remescladas
# por mesclar_segmentos_consecutivos mais adiante no pipeline.
_SUBTURN_ANCHORS: Tuple[Tuple[str, ...], ...] = (
    # Reinício de turno do OPERADOR (tratamento formal).
    ("o", "senhor"),
    ("a", "senhora"),
    # Auto-relato / negativa do MOTORISTA encravado no turno do operador.
    ("nao", "me", "deu"),
    ("nao", "tenho"),
    ("nao", "recebi"),
    ("nao", "chegou"),
    ("sem", "senha"),
)

_SUBTURN_MIN_PALAVRAS = 8


def dividir_em_subturnos(texto: str) -> List[str]:
    """Divide um bloco SEM pontuação em sub-turnos por marcadores de início de turno.

    Complementa quebrar_texto_em_clausulas para os casos em que o STT devolve vários
    turnos colados sem pontuação. Retorna [texto] quando não há marcador suficiente
    para um corte seguro (nenhuma divisão é forçada às cegas).
    """
    base = (texto or "").strip()
    if not base:
        return []
    palavras = base.split()
    if len(palavras) < _SUBTURN_MIN_PALAVRAS:
        return [base]

    norm = [normalizar_texto(p) for p in palavras]
    cortes: set[int] = set()
    for i in range(1, len(palavras)):  # nunca corta na posição 0
        for ancora in _SUBTURN_ANCHORS:
            n = len(ancora)
            if i + n <= len(palavras) and tuple(norm[i:i + n]) == ancora:
                cortes.add(i)
                break
    if not cortes:
        return [base]

    pedacos: List[str] = []
    anterior = 0
    for corte in sorted(cortes):
        pedaco = " ".join(palavras[anterior:corte]).strip()
        if pedaco:
            pedacos.append(pedaco)
        anterior = corte
    final = " ".join(palavras[anterior:]).strip()
    if final:
        pedacos.append(final)
    return pedacos or [base]


def quebrar_segmentos_hibridos(segmentos: List[SegmentoFormatado], operator_label: str, driver_label: str) -> List[SegmentoFormatado]:
    """Divide turnos mistos apenas quando a diarização acústica não está confiável."""
    if len(segmentos) < 2:
        return segmentos

    res: List[SegmentoFormatado] = []
    for i, seg in enumerate(segmentos):
        clausulas = quebrar_texto_em_clausulas(seg.texto)
        if len(clausulas) < 2:
            # Fast Transcription às vezes funde turnos num bloco sem pontuação;
            # tenta uma divisão secundária por marcadores de início de turno.
            clausulas = dividir_em_subturnos(seg.texto)
        if len(clausulas) < 2:
            res.append(seg)
            continue

        # Preserva a segmentação acústica quando ela já veio com alta confiança.
        if seg.speaker_confidence >= 0.70 and seg.diarization_risk == "low":
            res.append(seg)
            continue

        prev_seg = segmentos[i - 1] if i > 0 else None
        next_seg = segmentos[i + 1] if i + 1 < len(segmentos) else None
        speakers: List[str] = []

        for j, clausula in enumerate(clausulas):
            norm = normalizar_texto(clausula)
            score_op = pontuar_operador(norm)
            score_mot = pontuar_motorista(norm)
            speaker = seg.speaker
            prev_clause_speaker = speakers[-1] if speakers else None
            prev_clause_norm = normalizar_texto(clausulas[j - 1]) if j > 0 else ""

            if (
                j == 0
                and prev_seg and prev_seg.speaker == operator_label
                and eh_pergunta_ou_direcionamento_operador(prev_seg.texto_normalizado)
                and not tem_indicador_operador_forte(norm)
            ):
                speaker = driver_label

            if (
                eh_resposta_curta_interlocutor_contextual(norm)
                or eh_resposta_curta_motorista(norm)
                or tem_indicador_motorista_forte(norm)
            ) and not tem_indicador_operador_forte(norm):
                speaker = driver_label

            if tem_indicador_operador_forte(norm) and score_op >= score_mot + 1:
                speaker = operator_label

            if (
                prev_clause_speaker == operator_label
                and eh_resposta_curta_interlocutor_contextual(norm)
            ):
                speaker = driver_label

            if (
                prev_clause_speaker == driver_label
                and (
                    tem_indicador_operador_forte(norm)
                    or eh_pergunta_ou_direcionamento_operador(norm)
                )
            ):
                speaker = operator_label

            if (
                next_seg and next_seg.speaker == operator_label
                and j == len(clausulas) - 1
                and eh_resposta_curta_interlocutor_contextual(norm)
                and not tem_indicador_operador_forte(norm)
            ):
                speaker = driver_label

            if (
                prev_clause_speaker == operator_label
                and "deixar os dados" in prev_clause_norm
                and eh_resposta_curta_interlocutor_contextual(norm)
            ):
                speaker = driver_label

            speakers.append(speaker)

        if len(set(speakers)) == 1:
            res.append(seg)
            continue

        total_chars = max(1, sum(max(1, len(c)) for c in clausulas))
        current_start = seg.timestamp
        built_segments: List[SegmentoFormatado] = []
        for j, clausula in enumerate(clausulas):
            clause_chars = max(1, len(clausula))
            duration = seg.duracao_seconds * (clause_chars / total_chars)
            if j == len(clausulas) - 1:
                duration = max(0.0, (seg.timestamp.total_seconds() + seg.duracao_seconds) - current_start.total_seconds())

            novo_speaker = speakers[j]
            mudou = (novo_speaker != seg.speaker)

            built_segments.append(SegmentoFormatado(
                timestamp=current_start,
                speaker=novo_speaker,
                texto=clausula,
                texto_normalizado=normalizar_texto(clausula),
                duracao_seconds=max(0.0, duration),
                source_speaker_ids=seg.source_speaker_ids,
                persona_speaker_ids=seg.persona_speaker_ids,
                speaker_confidence=min(seg.speaker_confidence, 0.55) if mudou else seg.speaker_confidence,
                diarization_risk=_merge_risk(seg.diarization_risk, "medium" if mudou else "high"),
                diarization_ambiguous=True if mudou else seg.diarization_ambiguous,
            ))
            current_start = current_start + timedelta(seconds=max(0.0, duration))

        res.extend(built_segments)

    return res

def filtrar_runs_repetitivos(segmentos: List[SegmentoFormatado]) -> List[SegmentoFormatado]:
    if not segmentos: return []
    res = []
    i = 0
    while i < len(segmentos):
        atual_txt = segmentos[i].texto_normalizado
        j = i + 1
        while j < len(segmentos) and segmentos[j].texto_normalizado == atual_txt:
            j += 1
        
        run_len = j - i
        descartar = (run_len >= 6 and eh_token_ruido_curto(atual_txt)) or \
                   (run_len >= 20 and len(atual_txt) <= 12)
        compactar = run_len >= 4 and not eh_token_ruido_curto(atual_txt) and \
                    not eh_pergunta(atual_txt)
        
        if not descartar and not compactar:
            res.extend(segmentos[i:j])
        elif compactar:
            res.append(segmentos[i])
        i = j
    return res

def compactar_frase_dominante(segmentos: List[SegmentoFormatado]) -> List[SegmentoFormatado]:
    if len(segmentos) < 12: return segmentos
    
    counts = {}
    for s in segmentos:
        counts[s.texto_normalizado] = counts.get(s.texto_normalizado, 0) + 1
        
    frase_dom = max(counts, key=counts.get)
    count_dom = counts[frase_dom]
    
    min_dom = int(len(segmentos) * 0.45)
    if count_dom < 8 or count_dom < min_dom or eh_token_ruido_curto(frase_dom) or \
       eh_pergunta(frase_dom):
        return segmentos
        
    res = []
    mantidos = 0
    for s in segmentos:
        if s.texto_normalizado == frase_dom:
            if mantidos < 2:
                res.append(s)
                mantidos += 1
            continue
        res.append(s)
    return res

def remover_duplicatas_contiguas(segmentos: List[SegmentoFormatado]) -> List[SegmentoFormatado]:
    if len(segmentos) < 2: return segmentos
    res = [segmentos[0]]
    for i in range(1, len(segmentos)):
        atu, ult = segmentos[i], res[-1]
        if atu.texto_normalizado == ult.texto_normalizado and atu.speaker == ult.speaker and \
           abs((atu.timestamp - ult.timestamp).total_seconds()) <= 0.2:
            continue
        res.append(atu)
    return res

def mesclar_segmentos_consecutivos(segmentos: List[SegmentoFormatado]) -> List[SegmentoFormatado]:
    if len(segmentos) < 2: return segmentos
    res = [segmentos[0]]
    for i in range(1, len(segmentos)):
        atu, ult = segmentos[i], res[-1]
        
        gap = (atu.timestamp - (ult.timestamp + timedelta(seconds=ult.duracao_seconds))).total_seconds()
        pode_mesclar = (ult.speaker == atu.speaker and gap <= 3.0 and \
                       not ult.texto.strip().endswith(("?", "!")))
        
        if pode_mesclar:
            if ult.texto.strip().endswith(".") and gap > 1.3:
                pode_mesclar = False
            if (len(ult.texto) + len(atu.texto)) > 380:
                pode_mesclar = False
                
        if pode_mesclar:
            texto_unido = unir_textos(ult.texto, atu.texto)
            fim = max(ult.timestamp.total_seconds() + ult.duracao_seconds, 
                      atu.timestamp.total_seconds() + atu.duracao_seconds)
            res[-1] = SegmentoFormatado(
                timestamp=ult.timestamp,
                speaker=ult.speaker,
                texto=texto_unido,
                texto_normalizado=normalizar_texto(texto_unido),
                duracao_seconds=max(0.0, fim - ult.timestamp.total_seconds()),
                source_speaker_ids=_merge_id_tuples(ult.source_speaker_ids, atu.source_speaker_ids),
                persona_speaker_ids=_merge_id_tuples(ult.persona_speaker_ids, atu.persona_speaker_ids),
                speaker_confidence=min(ult.speaker_confidence, atu.speaker_confidence),
                diarization_risk=_merge_risk(ult.diarization_risk, atu.diarization_risk),
                diarization_ambiguous=ult.diarization_ambiguous or atu.diarization_ambiguous,
            )
        else:
            res.append(atu)
    return res
