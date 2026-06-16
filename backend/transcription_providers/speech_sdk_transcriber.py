"""Azure Speech SDK ConversationTranscriber - Diarização Superior.

Usa o SDK nativo ao invés da Fast Transcription REST API para obter
identificação de speakers muito mais precisa.

Papel no fluxo: backend de transcrição ALTERNATIVO (engine `sdk`), usado como
last-resort no fallback chain — segundo a memória do projeto, o SDK degrada a
qualidade do TEXTO em telefonia, então não é o default. Recebe WAV em bytes,
escreve um arquivo temporário (o SDK exige path), roda o ConversationTranscriber
com phrase hints de domínio e diarização, e devolve os segmentos finais via
finalize_speaker_segments. No Windows há retry no cleanup do .tmp por lock de arquivo.

CUSTO DE API: ALTO — transcrição PAGA no Azure Speech (consumo cobrado pelo SDK).
Diferente dos outros provedores deste pacote, NÃO registra no cost_guard.
"""
import logging
import os
import json
import tempfile
import threading
from datetime import timedelta

logger = logging.getLogger(__name__)
from typing import List, Optional

from audio.speaker_detection import RawPhrase, SpeakerDetectionService


def get_domain_phrases() -> list[str]:
    """Vocabulário de domínio para melhorar reconhecimento."""
    return [
        # Empresa e operação
        "Opentech", "nstech", "BAS", "central de monitoramento", "rastreamento",
        "monitoramento", "cadastro", "sinistro", "base de sinistro",
        # Veículos e logística
        "cavalo mecânico", "carreta", "semirreboque", "placa", "romaneio",
        "roteiro", "manifesto", "CT-e", "nota fiscal",
        # Interlocutores
        "ponto de apoio", "posto de apoio", "motorista", "operador",
        "PRF", "polícia militar", "polícia rodoviária federal",
        "delegado", "sargento", "tenente", "guarnição", "viatura",
        # Ações operacionais
        "botão de pânico", "perdeu o sinal", "autocarga", "isca",
        "espelhamento", "bloqueio", "desbloqueio", "posicionamento",
        "macrozona", "cerca eletrônica", "geofence",
        # Clientes e marcas
        "Mondelez", "Unilever", "Translovato", "BBM", "Fênix",
        # Termos de telefonia
        "CPF", "CNPJ", "alô", "bom dia", "boa tarde", "boa noite",
        # Localização
        "portaria", "recepção", "pátio", "balança", "guarita",
        "posto fiscal", "barreira",
    ]


def transcribe_with_conversation_transcriber(
    audio_wav_bytes: bytes,
    operator_label: str,
    driver_label: str,
    speech_key: Optional[str] = None,
    speech_region: Optional[str] = None,
    language: str = "pt-BR",
    timeout_seconds: int = 300,
) -> list[dict]:
    """
    Transcreve áudio WAV usando Azure Speech SDK ConversationTranscriber.

    Grava o WAV em arquivo temporário (o SDK precisa de path), habilita diarização
    e word-level timestamps, adiciona phrase hints de domínio e aguarda a sessão
    terminar (timeout em `timeout_seconds`). Mapeia os speaker_id ("Guest-1"...) para
    inteiros, normaliza o texto (services.normalize_company_name/remove_emojis/
    filter_hallucinations) e finaliza com a detecção de speakers.

    Params: `audio_wav_bytes` (deve ser WAV), `operator_label`/`driver_label` rótulos
    dos turnos, `speech_key`/`speech_region` sobrescrevem env (AZURE_SPEECH_KEY/
    AZURE_SPEECH_REGION, default eastus2), `language` (default pt-BR).

    Efeitos: chamada de REDE PAGA ao Azure Speech, escreve/apaga arquivo temporário
    em disco. Levanta RuntimeError se a key faltar, em timeout/erro do SDK ou se não
    sobrar transcrição/segmento válido. Retorna lista de segmentos no formato
    [{"start": "MM:SS", "end": "MM:SS", "text": "Speaker: texto"}].
    """
    import azure.cognitiveservices.speech as speechsdk

    key = speech_key or os.getenv("AZURE_SPEECH_KEY")
    region = speech_region or os.getenv("AZURE_SPEECH_REGION", "eastus2")

    if not key:
        raise RuntimeError("AZURE_SPEECH_KEY não configurada")

    # Salvar WAV em arquivo temporário (SDK precisa de path)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_wav_bytes)
            tmp_path = tmp.name

        # Configurar Speech SDK
        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        speech_config.speech_recognition_language = language

        # Habilitar diarização em resultados intermediários
        speech_config.set_property(
            property_id=speechsdk.PropertyId.SpeechServiceResponse_DiarizeIntermediateResults,
            value="true",
        )

        # Word-level timestamps para fronteiras de speaker mais precisas
        speech_config.request_word_level_timestamps()

        # Audio config do arquivo
        audio_config = speechsdk.audio.AudioConfig(filename=tmp_path)

        # Criar ConversationTranscriber
        transcriber = speechsdk.transcription.ConversationTranscriber(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        # Adicionar phrase hints de domínio
        phrase_list = speechsdk.PhraseListGrammar.from_recognizer(transcriber)
        for phrase in get_domain_phrases():
            phrase_list.addPhrase(phrase)

        # Estado de coleta de resultados
        raw_results: list[dict] = []
        errors: list[str] = []
        done = threading.Event()

        def on_transcribed(evt):
            r = evt.result
            if r.reason == speechsdk.ResultReason.RecognizedSpeech and r.text.strip():
                raw_results.append({
                    "speaker_id": r.speaker_id or "Unknown",
                    "text": r.text.strip(),
                    "offset_ticks": r.offset,
                    "duration_ticks": r.duration,
                })

        def on_session_stopped(evt):
            done.set()

        def on_canceled(evt):
            details = evt.cancellation_details
            if details.reason == speechsdk.CancellationReason.Error:
                errors.append(f"{details.error_code}: {details.error_details}")
            done.set()

        # Conectar eventos
        transcriber.transcribed.connect(on_transcribed)
        transcriber.session_stopped.connect(on_session_stopped)
        transcriber.canceled.connect(on_canceled)

        # Iniciar transcrição e aguardar conclusão
        transcriber.start_transcribing_async()
        completed = done.wait(timeout=timeout_seconds)
        transcriber.stop_transcribing_async().get()

        if not completed:
            raise RuntimeError(f"Speech SDK timeout após {timeout_seconds}s")
        if errors:
            raise RuntimeError(f"Speech SDK error: {'; '.join(errors)}")
        if not raw_results:
            raise RuntimeError("Speech SDK retornou transcrição vazia")

        # Converter speaker_id "Guest-1", "Guest-2" para inteiros
        speaker_id_map: dict[str, int] = {}
        next_id = 0
        for r in raw_results:
            sid = r["speaker_id"]
            if sid not in speaker_id_map:
                speaker_id_map[sid] = next_id
                next_id += 1

        logger.info("[SpeechSDK] %d frases, %d speakers detectados: %s", len(raw_results), len(speaker_id_map), list(speaker_id_map.keys()))

        # Importar funções de pós-processamento
        from services import normalize_company_name, filter_hallucinations, remove_emojis

        # Converter para RawPhrase para o pipeline de detecção de speakers
        raw_phrases: list[RawPhrase] = []
        for r in raw_results:
            text = r["text"]
            text = filter_hallucinations(remove_emojis(normalize_company_name(text)))
            if not text.strip():
                continue

            offset_s = r["offset_ticks"] / 10_000_000
            duration_s = r["duration_ticks"] / 10_000_000

            raw_phrases.append(RawPhrase(
                timestamp=timedelta(seconds=offset_s),
                duration_seconds=duration_s,
                speaker_id=speaker_id_map.get(r["speaker_id"], -1),
                texto=text,
                texto_normalizado=SpeakerDetectionService.normalizar_texto(text),
            ))

        if not raw_phrases:
            raise RuntimeError("Nenhuma frase válida após pós-processamento")

        from transcription_providers.common import finalize_speaker_segments
        from utils.text_processing import deduplicate_transcription_segments

        final_segments = finalize_speaker_segments(
            raw_phrases,
            operator_label=operator_label,
            driver_label=driver_label,
            deduplicate_transcription_segments=deduplicate_transcription_segments
        )

        logger.info("[SpeechSDK] Output: %d segmentos finais", len(final_segments))
        return final_segments

    finally:
        # Destruir instâncias C++ do SDK para liberar o lock no arquivo imediatamente
        if 'transcriber' in locals(): del transcriber
        if 'audio_config' in locals(): del audio_config
        # Windows: tentar cleanup com retry caso lock persista
        if tmp_path and os.path.exists(tmp_path):
            import time
            for attempt in range(3):
                try:
                    os.unlink(tmp_path)
                    break
                except PermissionError:
                    time.sleep(0.5)

