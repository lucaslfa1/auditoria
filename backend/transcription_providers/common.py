from __future__ import annotations

from datetime import timedelta
from typing import Callable

from audio.speaker_detection import RawPhrase, SpeakerDetectionService

TextNormalizer = Callable[[str], str]
Deduplicator = Callable[[list[dict]], list[dict]]
PhraseTextExtractor = Callable[[dict], str]
PhraseTimingExtractor = Callable[[dict], tuple[float, float]]


def normalize_transcribed_text(
    text: str,
    *,
    normalize_company_name: TextNormalizer,
    filter_hallucinations: TextNormalizer,
    remove_emojis: TextNormalizer,
) -> str:
    normalized = normalize_company_name(str(text or "").strip())
    normalized = remove_emojis(normalized)
    normalized = filter_hallucinations(normalized)
    return normalized.strip()


def build_azure_domain_phrases(
    text_corrections_config: dict,
    operator_name: str | None,
    driver_name: str | None,
) -> list[str]:
    phrase_list: list[str] = []
    for correction in text_corrections_config.get("corrections", []):
        target = correction.get("target")
        if target:
            phrase_list.append(target)

    domain_phrases = [
        "Opentech",
        "nstech",
        "BAS",
        "Base de Sinistros",
        "central de monitoramento",
        "rastreamento",
        "monitoramento",
        "cadastro",
        "sinistro",
        "base de sinistro",
        "CEAGESP",
        "cavalo mecanico",
        "carreta",
        "semirreboque",
        "placa",
        "roubo",
        "furto",
        "tombamento",
        "colisao",
        "avaria",
        "salvado",
        "perda total",
        "romaneio",
        "roteiro",
        "manifesto",
        "CT-e",
        "nota fiscal",
        "ponto de apoio",
        "posto de apoio",
        "motorista",
        "operador",
        "transportadora",
        "oitiva",
        "regulacao",
        "PRF",
        "PRE",
        "B.O.",
        "boletim de ocorrencia",
        "policia militar",
        "policia rodoviaria federal",
        "gerenciadora de risco",
        "GR",
        "delegado",
        "sargento",
        "tenente",
        "guarnicao",
        "viatura",
        "jammer",
        "vassourinha",
        "rastreador",
        "botao de panico",
        "perdeu o sinal",
        "autocarga",
        "isca",
        "espelhamento",
        "bloqueio",
        "desbloqueio",
        "posicionamento",
        "macrozona",
        "cerca eletronica",
        "geofence",
        "Mondelez",
        "Unilever",
        "Translovato",
        "BBM",
        "Fenix",
        "CPF",
        "CNPJ",
        "alo",
        "bom dia",
        "boa tarde",
        "boa noite",
        "portaria",
        "recepcao",
        "patio",
        "balanca",
        "guarita",
        "posto fiscal",
        "barreira",
    ]

    for target in phrase_list:
        if target not in domain_phrases:
            domain_phrases.append(target)

    for full_name in [operator_name, driver_name]:
        if full_name:
            first_name = full_name.strip().split()[0]
            if first_name and first_name not in domain_phrases:
                domain_phrases.append(first_name)

    return domain_phrases


def build_transcription_domain_prompt(
    text_corrections_config: dict,
    operator_name: str | None = None,
    driver_name: str | None = None,
    *,
    max_phrases: int = 80,
) -> str:
    phrases = build_azure_domain_phrases(
        text_corrections_config,
        operator_name,
        driver_name,
    )
    limited_phrases = phrases[: max(1, max_phrases)]
    
    # Prepara menção direta aos locutores no prompt
    locutores = []
    if operator_name:
        locutores.append(f"Operador(a) {operator_name.strip()}")
    if driver_name:
        locutores.append(f"Motorista/Cliente/Transportadora {driver_name.strip()}")
    
    contexto_locutores = f" Locutores esperados na chamada: {' e '.join(locutores)}." if locutores else ""

    return (
        f"Contexto: ligacao telefonica de monitoramento logistico e auditoria de qualidade da Opentech.{contexto_locutores} "
        "Transcreva literalmente em portugues brasileiro, preserve numeros, senhas, CPFs, placas, codigos, "
        "siglas e nomes proprios. Se um trecho estiver inaudivel, use [Inaudivel]. "
        "Vocabulario esperado: "
        + ", ".join(limited_phrases)
        + "."
    )


def build_combined_segments(
    phrases: list[dict],
    *,
    extract_phrase_text: PhraseTextExtractor,
    extract_phrase_timing_ms: PhraseTimingExtractor,
    normalize_company_name: TextNormalizer,
    filter_hallucinations: TextNormalizer,
    remove_emojis: TextNormalizer,
    deduplicate_transcription_segments: Deduplicator,
) -> list[dict]:
    combined_segments: list[dict] = []
    for phrase in phrases:
        text = normalize_transcribed_text(
            extract_phrase_text(phrase),
            normalize_company_name=normalize_company_name,
            filter_hallucinations=filter_hallucinations,
            remove_emojis=remove_emojis,
        )
        if not text:
            continue
        offset_ms, duration_ms = extract_phrase_timing_ms(phrase)
        start_td = timedelta(milliseconds=offset_ms)
        end_td = timedelta(milliseconds=offset_ms + duration_ms)
        combined_segments.append(
            {
                "start": SpeakerDetectionService.formatar_timestamp(start_td),
                "end": SpeakerDetectionService.formatar_timestamp(end_td),
                "text": text,
            }
        )
    return deduplicate_transcription_segments(combined_segments)


def finalize_speaker_segments(
    raw_phrases: list[RawPhrase],
    *,
    operator_label: str,
    driver_label: str,
    deduplicate_transcription_segments: Deduplicator,
) -> list[dict]:
    raw_phrases.sort(key=lambda phrase: phrase.timestamp.total_seconds())

    segmentos = SpeakerDetectionService.classificar_speakers(raw_phrases, operator_label, driver_label)
    segmentos = SpeakerDetectionService.corrigir_perguntas_operacionais(segmentos, operator_label, driver_label)
    segmentos = SpeakerDetectionService.quebrar_segmentos_hibridos(segmentos, operator_label, driver_label)
    segmentos = SpeakerDetectionService.rebalancear_interlocutores_por_turno(segmentos, operator_label, driver_label)
    segmentos = SpeakerDetectionService.promover_turnos_operacionais(segmentos, operator_label, driver_label)
    segmentos = SpeakerDetectionService.suavizar_troca_isolada_de_speaker(segmentos)
    
    segmentos = SpeakerDetectionService.filtrar_runs_repetitivos(segmentos)
    segmentos = SpeakerDetectionService.compactar_frase_dominante(segmentos)
    segmentos = SpeakerDetectionService.remover_duplicatas_contiguas(segmentos)
    segmentos = SpeakerDetectionService.mesclar_segmentos_consecutivos(segmentos)
    segmentos = SpeakerDetectionService.remover_duplicatas_contiguas(segmentos)

    final_segments: list[dict] = []
    for segment in segmentos:
        if not segment.texto or not segment.texto.strip():
            continue
        is_telephony = SpeakerDetectionService.eh_segmento_telefonia(segment.texto_normalizado)
        speaker_label = "Telefonia" if is_telephony else segment.speaker
        final_segments.append(
            {
                "start": SpeakerDetectionService.formatar_timestamp(segment.timestamp),
                "end": SpeakerDetectionService.formatar_timestamp(
                    segment.timestamp + timedelta(seconds=segment.duracao_seconds)
                ),
                "text": f"{speaker_label}: {segment.texto}",
                "speaker_source_ids": list(segment.source_speaker_ids),
                "speaker_persona_ids": list(segment.persona_speaker_ids),
                "speaker_confidence": round(segment.speaker_confidence, 3),
                "speaker_risk": "low" if is_telephony else segment.diarization_risk,
                "speaker_ambiguous": False if is_telephony else segment.diarization_ambiguous,
            }
        )

    return deduplicate_transcription_segments(final_segments)
