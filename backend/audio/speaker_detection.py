"""Fachada da detecção/diarização de speakers (operador x interlocutor).

Reúne, sob a classe `SpeakerDetectionService`, as constantes e funções
espalhadas pelos módulos de coesão (`speaker_constants`, `speaker_heuristics`,
`speaker_normalization`, `speaker_identification`). É o ponto de entrada estável
para o resto do backend: o código consumidor chama
`SpeakerDetectionService.<nome>` sem depender de onde cada peça vive.

A maioria das funções é heurística/CPU pura. A exceção é o mapeamento de
speakers via LLM (`_tentar_mapear_speakers_com_llm`, exposto indiretamente por
`mapear_speakers_por_id`/`analisar_diarizacao_por_ids`), que PODE chamar o Azure
OpenAI (custo de API) quando há mais de um speaker_id e as credenciais estão
configuradas; caso contrário cai na heurística.
"""

from audio.speaker_models import RawPhrase, SegmentoFormatado, SpeakerStats, DiarizationAnalysis
import audio.speaker_constants as constants
import audio.speaker_heuristics as heuristics
import audio.speaker_normalization as normalization
import audio.speaker_identification as identification

class SpeakerDetectionService:
    """Fachada estática que reexporta o toolkit de diarização de speakers.

    Todos os atributos são constantes ou `staticmethod` que apontam para as
    funções dos módulos de coesão. Não há estado de instância nem necessidade de
    instanciar a classe; use os membros diretamente (ex.:
    `SpeakerDetectionService.classificar_speakers(...)`). Mantida para preservar
    os import paths antigos durante a refatoração por coesão.
    """
    SPEAKER_OPERADOR = constants.SPEAKER_OPERADOR
    SPEAKER_MOTORISTA = constants.SPEAKER_MOTORISTA
    PERGUNTA_PREFIXOS = constants.PERGUNTA_PREFIXOS
    OPERADOR_FRASES_SUPORTE = constants.OPERADOR_FRASES_SUPORTE
    OPERADOR_FRASES_MUITO_FORTES = constants.OPERADOR_FRASES_MUITO_FORTES
    OPERADOR_FRASES_POLICIA = constants.OPERADOR_FRASES_POLICIA
    OPERADOR_FRASES_INSTITUCIONAIS = constants.OPERADOR_FRASES_INSTITUCIONAIS
    RESPOSTAS_CURTAS_OPERADOR = constants.RESPOSTAS_CURTAS_OPERADOR
    RESPOSTAS_ACK_INTERLOCUTOR = constants.RESPOSTAS_ACK_INTERLOCUTOR
    RESPOSTAS_CURTAS_INTERLOCUTOR = constants.RESPOSTAS_CURTAS_INTERLOCUTOR
    TELEPHONY_MARKERS_STRONG = constants.TELEPHONY_MARKERS_STRONG
    TELEPHONY_MARKERS_SOFT = constants.TELEPHONY_MARKERS_SOFT
    SUPPORT_POINT_HANDOFF_MARKERS = constants.SUPPORT_POINT_HANDOFF_MARKERS

    normalizar_texto = staticmethod(heuristics.normalizar_texto)
    eh_segmento_telefonia = staticmethod(heuristics.eh_segmento_telefonia)
    eh_handoff_interlocutor = staticmethod(heuristics.eh_handoff_interlocutor)
    eh_pergunta = staticmethod(heuristics.eh_pergunta)
    pontuar_operador = staticmethod(heuristics.pontuar_operador)
    tem_indicador_policial = staticmethod(heuristics.tem_indicador_policial)
    pontuar_motorista = staticmethod(heuristics.pontuar_motorista)
    eh_pergunta_ou_direcionamento_operador = staticmethod(heuristics.eh_pergunta_ou_direcionamento_operador)
    inferir_speaker_sem_diarizacao = staticmethod(heuristics.inferir_speaker_sem_diarizacao)
    eh_resposta_curta_motorista = staticmethod(heuristics.eh_resposta_curta_motorista)
    eh_ditado_alfanumerico = staticmethod(heuristics.eh_ditado_alfanumerico)
    tem_intro_operador = staticmethod(heuristics.tem_intro_operador)
    tem_indicador_operador_forte = staticmethod(heuristics.tem_indicador_operador_forte)
    tem_indicador_motorista_forte = staticmethod(heuristics.tem_indicador_motorista_forte)
    eh_resposta_curta_operador = staticmethod(heuristics.eh_resposta_curta_operador)
    eh_resposta_curta_interlocutor_contextual = staticmethod(heuristics.eh_resposta_curta_interlocutor_contextual)
    eh_resposta_social_curta_operador = staticmethod(heuristics.eh_resposta_social_curta_operador)
    eh_token_ruido_curto = staticmethod(heuristics.eh_token_ruido_curto)
    formatar_timestamp = staticmethod(normalization.formatar_timestamp)
    unir_textos = staticmethod(normalization.unir_textos)
    _clamp_confidence = staticmethod(normalization._clamp_confidence)
    _parse_float = staticmethod(normalization._parse_float)
    quebrar_texto_em_clausulas = staticmethod(normalization.quebrar_texto_em_clausulas)
    logger = staticmethod(identification.logger)
    mapear_speakers_por_id = staticmethod(identification.mapear_speakers_por_id)
    _merge_id_tuples = staticmethod(identification._merge_id_tuples)
    _risk_rank = staticmethod(identification._risk_rank)
    _merge_risk = staticmethod(identification._merge_risk)
    _coletar_stats_por_id = staticmethod(identification._coletar_stats_por_id)
    _avaliar_speaker_por_heuristica = staticmethod(identification._avaliar_speaker_por_heuristica)
    _tem_dialogo_duas_pessoas_estavel = staticmethod(identification._tem_dialogo_duas_pessoas_estavel)
    _tem_handoff_ponto_de_apoio = staticmethod(identification._tem_handoff_ponto_de_apoio)
    _normalizar_role_llm = staticmethod(identification._normalizar_role_llm)
    _montar_resumo_speakers_para_llm = staticmethod(identification._montar_resumo_speakers_para_llm)
    _montar_trecho_llm = staticmethod(identification._montar_trecho_llm)
    _parse_llm_persona_mapping = staticmethod(identification._parse_llm_persona_mapping)
    _tentar_mapear_speakers_com_llm = staticmethod(identification._tentar_mapear_speakers_com_llm)
    analisar_diarizacao_por_ids = staticmethod(identification.analisar_diarizacao_por_ids)
    classificar_speakers = staticmethod(identification.classificar_speakers)
    corrigir_perguntas_operacionais = staticmethod(identification.corrigir_perguntas_operacionais)
    rebalancear_interlocutores_por_turno = staticmethod(identification.rebalancear_interlocutores_por_turno)
    promover_turnos_operacionais = staticmethod(identification.promover_turnos_operacionais)
    suavizar_troca_isolada_de_speaker = staticmethod(identification.suavizar_troca_isolada_de_speaker)
    quebrar_segmentos_hibridos = staticmethod(identification.quebrar_segmentos_hibridos)
    filtrar_runs_repetitivos = staticmethod(identification.filtrar_runs_repetitivos)
    compactar_frase_dominante = staticmethod(identification.compactar_frase_dominante)
    remover_duplicatas_contiguas = staticmethod(identification.remover_duplicatas_contiguas)
    mesclar_segmentos_consecutivos = staticmethod(identification.mesclar_segmentos_consecutivos)
