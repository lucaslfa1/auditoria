import os
import sys
import unittest
from datetime import timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from audio.speaker_detection import RawPhrase, SegmentoFormatado, SpeakerDetectionService
from audio.speaker_identification import dividir_em_subturnos


class TestSpeakerDetection(unittest.TestCase):
    def _phrase(self, seconds: int, speaker_id: int, text: str) -> RawPhrase:
        return RawPhrase(
            timestamp=timedelta(seconds=seconds),
            duration_seconds=1.5,
            speaker_id=speaker_id,
            texto=text,
            texto_normalizado=SpeakerDetectionService.normalizar_texto(text),
        )

    def test_keeps_support_point_as_interlocutor_when_operator_introduces(self):
        phrases = [
            self._phrase(0, 0, "Ponto de apoio, bom dia."),
            self._phrase(2, 1, "Bom dia, aqui e Lucas da Opentech, estou ligando sobre uma parada indevida."),
            self._phrase(5, 0, "Qual a placa do veiculo?"),
            self._phrase(8, 1, "Me confirma por favor se o motorista ja chegou ai."),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Motorista")

        self.assertEqual(segmentos[0].speaker, "Motorista")
        self.assertEqual(segmentos[1].speaker, "Operador")
        self.assertEqual(segmentos[2].speaker, "Motorista")
        self.assertEqual(segmentos[3].speaker, "Operador")

    def test_receptive_call_center_phrases_stay_with_operator(self):
        phrases = [
            self._phrase(0, 0, "Cadastro"),
            self._phrase(2, 1, "Ola, boa tarde, tudo bem?"),
            self._phrase(4, 0, "Tudo bem, em que posso ajudar?"),
            self._phrase(7, 1, "Eu sou o Fabricio e estou com pendencia na documentacao."),
            self._phrase(12, 0, "So um momento que eu vou verificar."),
            self._phrase(16, 0, "Esta sendo solicitado um processo de 2023."),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Motorista")

        self.assertEqual(segmentos[0].speaker, "Operador")
        self.assertEqual(segmentos[2].speaker, "Operador")
        self.assertEqual(segmentos[3].speaker, "Motorista")
        self.assertEqual(segmentos[4].speaker, "Operador")
        self.assertEqual(segmentos[5].speaker, "Operador")

    def test_promotes_operational_follow_up_after_operator_turn(self):
        phrases = [
            self._phrase(0, 1, "Cadastro"),
            self._phrase(3, 1, "GR.com.br. Beleza."),
            self._phrase(6, 0, "No assunto do e mail voce coloca o seu nome e CPF pra gente saber do que se trata, ta?"),
            self._phrase(10, 0, "Caso ele nao traga essa informacao, precisa da copia do processo."),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Motorista")
        segmentos = SpeakerDetectionService.promover_turnos_operacionais(segmentos, "Operador", "Motorista")

        self.assertEqual(segmentos[2].speaker, "Operador")
        self.assertEqual(segmentos[3].speaker, "Operador")

    def test_promotes_institutional_self_reference_to_operator(self):
        phrases = [
            self._phrase(0, 0, "Estamos com um veiculo no patio do posto."),
            self._phrase(2, 1, "Aqui e a Priscila do rastreamento da Opentech."),
            self._phrase(5, 0, "Nos somos da Opentech, a gente que faz o rastreamento."),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Ponto de Apoio")
        segmentos = SpeakerDetectionService.promover_turnos_operacionais(segmentos, "Operador", "Ponto de Apoio")

        self.assertEqual(segmentos[2].speaker, "Operador")

    def test_normalizes_open_tech_alias_for_operator_scoring(self):
        texto = SpeakerDetectionService.normalizar_texto("Aqui e a Priscila do rastreamento da Open Tech.")

        self.assertIn("opentech", texto)
        self.assertNotIn("open tech", texto)
        self.assertGreaterEqual(SpeakerDetectionService.pontuar_operador("opentech"), 3)

    def test_promotes_short_operator_reply_after_driver_question(self):
        phrases = [
            self._phrase(0, 0, "Eu estou aqui no patio do posto com o veiculo."),
            self._phrase(0, 1, "Aqui e a Priscila do rastreamento da Opentech."),
            self._phrase(4, 0, "Eu posso ligar daqui uns dez minutos dai?"),
            self._phrase(7, 0, "Pode. Uns quinze?"),
            self._phrase(10, 0, "Ta, ta bom. Brigada."),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Ponto de Apoio")
        segmentos = SpeakerDetectionService.promover_turnos_operacionais(segmentos, "Operador", "Ponto de Apoio")

        self.assertEqual(segmentos[2].speaker, "Ponto de Apoio")
        self.assertEqual(segmentos[3].speaker, "Operador")
        self.assertEqual(segmentos[4].speaker, "Ponto de Apoio")

    def test_police_self_identification_stays_interlocutor(self):
        phrases = [
            self._phrase(0, 1, "Alo, bom dia, com quem eu falo?"),
            self._phrase(3, 0, "Com PRF Alves."),
            self._phrase(6, 1, "Quem fala aqui e o Flavio da base de sinistro da Opentech."),
            self._phrase(9, 1, "Eu trabalho com rastreamento de autocarga, tudo bem?"),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Policia")
        segmentos = SpeakerDetectionService.rebalancear_interlocutores_por_turno(segmentos, "Operador", "Policia")
        segmentos = SpeakerDetectionService.promover_turnos_operacionais(segmentos, "Operador", "Policia")

        self.assertEqual(segmentos[1].speaker, "Policia")
        self.assertEqual(segmentos[2].speaker, "Operador")
        self.assertEqual(segmentos[3].speaker, "Operador")

    def test_police_briefing_stays_with_operator_and_reply_with_police(self):
        phrases = [
            self._phrase(0, 1, "Voce fala com a Milaine. Eu falo em nome do rastreamento da Opentech."),
            self._phrase(4, 1, "A gente trabalha com monitoracao de carga e esta atuando numa suspeita de sinistro."),
            self._phrase(8, 1, "Posso so estar deixando os dados com o senhor?"),
            self._phrase(12, 0, "Consegue sim, so um segundo."),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Policia")
        segmentos = SpeakerDetectionService.rebalancear_interlocutores_por_turno(segmentos, "Operador", "Policia")
        segmentos = SpeakerDetectionService.promover_turnos_operacionais(segmentos, "Operador", "Policia")

        self.assertEqual(segmentos[0].speaker, "Operador")
        self.assertEqual(segmentos[1].speaker, "Operador")
        self.assertEqual(segmentos[2].speaker, "Operador")
        self.assertEqual(segmentos[3].speaker, "Policia")

    def test_breaks_mixed_support_point_segment(self):
        segmentos = [
            SegmentoFormatado(
                timestamp=timedelta(seconds=45),
                speaker="Operador",
                texto="Qual que e a empresa la?",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Qual que e a empresa la?"),
                duracao_seconds=2.0,
            ),
            SegmentoFormatado(
                timestamp=timedelta(seconds=48),
                speaker="Operador",
                texto="E, ele e da Compran. Nos somos da Opentech, a gente que faz o rastreamento. Qual que e a placa dele?",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("E, ele e da Compran. Nos somos da Opentech, a gente que faz o rastreamento. Qual que e a placa dele?"),
                duracao_seconds=6.0,
            ),
        ]

        quebrados = SpeakerDetectionService.quebrar_segmentos_hibridos(segmentos, "Operador", "Ponto de Apoio")
        quebrados = SpeakerDetectionService.rebalancear_interlocutores_por_turno(quebrados, "Operador", "Ponto de Apoio")
        quebrados = SpeakerDetectionService.promover_turnos_operacionais(quebrados, "Operador", "Ponto de Apoio")
        quebrados = SpeakerDetectionService.suavizar_troca_isolada_de_speaker(quebrados)

        self.assertEqual(quebrados[1].speaker, "Ponto de Apoio")
        self.assertEqual(quebrados[2].speaker, "Operador")
        self.assertEqual(quebrados[3].speaker, "Operador")

    def test_heuristic_override_marks_diarization_as_ambiguous(self):
        segmentos = [
            SegmentoFormatado(
                timestamp=timedelta(seconds=0),
                speaker="Operador",
                texto="Bom dia, aqui e a central Opentech.",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Bom dia, aqui e a central Opentech."),
                duracao_seconds=2.0,
                source_speaker_ids=(1,),
                persona_speaker_ids=(1,),
                speaker_confidence=0.91,
                diarization_risk="low",
            ),
            SegmentoFormatado(
                timestamp=timedelta(seconds=3),
                speaker="Motorista",
                texto="Qual a placa do veiculo?",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Qual a placa do veiculo?"),
                duracao_seconds=2.0,
                source_speaker_ids=(0,),
                persona_speaker_ids=(0,),
                speaker_confidence=0.91,
                diarization_risk="low",
            ),
        ]

        corrigidos = SpeakerDetectionService.corrigir_perguntas_operacionais(segmentos, "Operador", "Motorista")

        self.assertEqual(corrigidos[1].speaker, "Operador")
        self.assertEqual(corrigidos[1].speaker_confidence, 0.55)
        self.assertEqual(corrigidos[1].diarization_risk, "medium")
        self.assertTrue(corrigidos[1].diarization_ambiguous)
        self.assertEqual(corrigidos[1].source_speaker_ids, (0,))

    def test_does_not_break_high_confidence_low_risk_hybrid_segment(self):
        segmentos = [
            SegmentoFormatado(
                timestamp=timedelta(seconds=45),
                speaker="Operador",
                texto="Qual que e a empresa la?",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Qual que e a empresa la?"),
                duracao_seconds=2.0,
                source_speaker_ids=(1,),
                persona_speaker_ids=(1,),
                speaker_confidence=0.92,
                diarization_risk="low",
            ),
            SegmentoFormatado(
                timestamp=timedelta(seconds=48),
                speaker="Operador",
                texto="E, ele e da Compran. Nos somos da Opentech, a gente que faz o rastreamento. Qual que e a placa dele?",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("E, ele e da Compran. Nos somos da Opentech, a gente que faz o rastreamento. Qual que e a placa dele?"),
                duracao_seconds=6.0,
                source_speaker_ids=(1,),
                persona_speaker_ids=(1,),
                speaker_confidence=0.92,
                diarization_risk="low",
            ),
        ]

        quebrados = SpeakerDetectionService.quebrar_segmentos_hibridos(segmentos, "Operador", "Ponto de Apoio")

        self.assertEqual(len(quebrados), 2)
        self.assertEqual(quebrados[1].speaker, "Operador")
        self.assertEqual(quebrados[1].speaker_confidence, 0.92)
        self.assertEqual(quebrados[1].diarization_risk, "low")
        self.assertFalse(quebrados[1].diarization_ambiguous)

    def test_breaks_mixed_police_segment_with_ack(self):
        segmentos = [
            SegmentoFormatado(
                timestamp=timedelta(seconds=18),
                speaker="Operador",
                texto="Quem fala aqui e o Flavio da base de sinistro da Opentech.",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Quem fala aqui e o Flavio da base de sinistro da Opentech."),
                duracao_seconds=4.0,
            ),
            SegmentoFormatado(
                timestamp=timedelta(seconds=24),
                speaker="Operador",
                texto="A gente esta falando de uma suspeita de sinistro e eu queria deixar os dados desse veiculo com o senhor pra caso tenha informacao na regiao. Pode deixar.",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("A gente esta falando de uma suspeita de sinistro e eu queria deixar os dados desse veiculo com o senhor pra caso tenha informacao na regiao. Pode deixar."),
                duracao_seconds=8.0,
            ),
            SegmentoFormatado(
                timestamp=timedelta(seconds=50),
                speaker="Operador",
                texto="Pode falar.",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Pode falar."),
                duracao_seconds=1.5,
            ),
        ]

        quebrados = SpeakerDetectionService.quebrar_segmentos_hibridos(segmentos, "Operador", "Policia")
        quebrados = SpeakerDetectionService.rebalancear_interlocutores_por_turno(quebrados, "Operador", "Policia")
        quebrados = SpeakerDetectionService.promover_turnos_operacionais(quebrados, "Operador", "Policia")
        quebrados = SpeakerDetectionService.suavizar_troca_isolada_de_speaker(quebrados)

        self.assertEqual(quebrados[1].speaker, "Operador")
        self.assertEqual(quebrados[2].speaker, "Policia")

    def test_breaks_unpunctuated_segment_with_embedded_driver_denial(self):
        import importlib
        import sys
        # Forca recarregamento dos modulos para isolar completamente contra poluicao de estado de outros testes.
        for mod in ["audio.speaker_constants", "audio.speaker_heuristics", "audio.speaker_normalization", "audio.speaker_identification", "audio.speaker_detection"]:
            if mod in sys.modules:
                importlib.reload(sys.modules[mod])

        from audio.speaker_detection import SegmentoFormatado, SpeakerDetectionService

        # O Azure Fast Transcription as vezes funde tres turnos num bloco unico,
        # SEM pontuacao, rotulado como Operador. A negativa de senha do motorista
        # ('a transportadora nao me deu senha') fica colada no turno do operador.
        # O splitter precisa separar para a fala ser atribuida ao Motorista
        # (caso real: audit 185, setor fenix, zerado indevidamente por senha).
        bloco = (
            "alo alo aqui e falo com o senhor jose luiz isso tudo bem senhor jose luiz "
            "aqui e a nete do rastreamento opentech poderia me informar sua senha de seguranca "
            "olha a transportadora nao me deu senha nao eu to colocando os quatro ultimos "
            "numeros do meu telefone o senhor poderia me informar seu cpf para poder validar a ligacao"
        )
        segmentos = [
            SegmentoFormatado(
                timestamp=timedelta(seconds=27),
                speaker="Operador",
                texto=bloco,
                texto_normalizado=SpeakerDetectionService.normalizar_texto(bloco),
                duracao_seconds=28.0,
            ),
            SegmentoFormatado(
                timestamp=timedelta(seconds=57),
                speaker="Motorista",
                texto="02287984852",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("02287984852"),
                duracao_seconds=9.0,
            ),
        ]

        quebrados = SpeakerDetectionService.quebrar_segmentos_hibridos(segmentos, "Operador", "Motorista")

        texto_motorista = " ".join(
            s.texto_normalizado for s in quebrados if s.speaker == "Motorista"
        )
        texto_operador = " ".join(
            s.texto_normalizado for s in quebrados if s.speaker == "Operador"
        )
        # A negativa de senha pertence ao motorista, nao ao operador.
        self.assertIn("nao me deu senha", texto_motorista)
        self.assertNotIn("nao me deu senha", texto_operador)
        # O operador continua dono da saudacao e do pedido de senha/CPF.
        self.assertIn("poderia me informar sua senha", texto_operador)

    def test_dividir_em_subturnos_nao_divide_monologo_sem_marcador(self):
        # Bloco longo sem pontuação mas SEM troca de turno (monólogo do operador
        # orientando o motorista) não deve ser fatiado: nenhuma âncora de início
        # de turno de outro locutor aparece, então retorna o texto inteiro.
        bloco = (
            "entao vou te explicar como funciona o procedimento de rastreamento "
            "voce vai ligar a ignicao esperar um pouquinho e mandar a localizacao "
            "pelo aplicativo que a gente acompanha por aqui tranquilo"
        )
        self.assertEqual(dividir_em_subturnos(bloco), [bloco])

    def test_dividir_em_subturnos_ignora_segmento_curto(self):
        self.assertEqual(dividir_em_subturnos("o senhor pode confirmar"), ["o senhor pode confirmar"])

    def test_maps_multiple_raw_ids_to_same_operator_persona(self):
        phrases = [
            self._phrase(0, 1, "Bom dia, aqui e a central Opentech."),
            self._phrase(3, 0, "Bom dia."),
            self._phrase(6, 3, "Preciso confirmar sua placa e a previsao de descarga."),
            self._phrase(10, 0, "ABC1D23, to aguardando descarga."),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(phrases, "Operador", "Motorista")

        self.assertEqual([segmento.speaker for segmento in segmentos], ["Operador", "Motorista", "Operador", "Motorista"])
        self.assertEqual(segmentos[0].persona_speaker_ids, (1, 3))
        self.assertEqual(segmentos[2].persona_speaker_ids, (1, 3))
        self.assertIn(segmentos[0].diarization_risk, {"medium", "high"})

    def test_detects_telephony_menu_segment(self):
        self.assertTrue(
            SpeakerDetectionService.eh_segmento_telefonia(
                SpeakerDetectionService.normalizar_texto(
                    "Ola, bem-vindo a Torre Mondelez. Digite 1 para devolucao parcial."
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
