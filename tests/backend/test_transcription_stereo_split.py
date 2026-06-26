import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import timedelta
import sys
import os

# Adiciona o backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.transcription import transcribe_audio

class TestTranscriptionStereoSplit(unittest.IsolatedAsyncioTestCase):
    
    @patch('core.transcription.split_stereo_audio')
    @patch('core.transcription.transcribe_audio', new_callable=AsyncMock)
    async def test_stereo_split_orchestration_and_merging(self, mock_transcribe_audio, mock_split_stereo_audio):
        # Configura o mock do split de áudio para simular que o áudio de entrada é estéreo
        # e retorna dois bytes fictícios (left e right)
        mock_split_stereo_audio.return_value = (b"left_channel_bytes", b"right_channel_bytes")
        
        # Configura o mock de transcribe_audio recursivo.
        # Na primeira chamada (left channel/operador), retorna segmentos do operador.
        # Na segunda chamada (right channel/motorista), retorna segmentos do motorista.
        left_segments = [
            {"start": "00:00", "end": "00:05", "text": "Operador: Bom dia, central de monitoramento."},
            {"start": "00:10", "end": "00:15", "text": "Operador: Qual a placa do veículo?"}
        ]
        
        right_segments = [
            {"start": "00:06", "end": "00:09", "text": "Motorista: Bom dia, tudo bem."},
            {"start": "00:16", "end": "00:20", "text": "Condutor: A placa é ABC1234."}
        ]
        
        # Definimos o side_effect para as duas chamadas recursivas.
        mock_transcribe_audio.side_effect = [
            (left_segments, {"strategy": "fast"}),
            (right_segments, {"strategy": "fast"})
        ]
        
        # Chama a função principal com um áudio fictício que simula ser estéreo
        final_segments, metadata = await transcribe_audio(
            b"fake_stereo_audio_bytes",
            "audio/wav",
            operator_name="Nete",
            driver_name="Jose",
            return_metadata=True
        )
        
        # Assegura que split_stereo_audio foi chamado
        mock_split_stereo_audio.assert_called_once_with(b"fake_stereo_audio_bytes")
        
        # Assegura que transcribe_audio foi chamado recursivamente para ambos os canais
        self.assertEqual(mock_transcribe_audio.call_count, 2)
        mock_transcribe_audio.assert_any_call(
            b"left_channel_bytes",
            "audio/wav",
            "Nete",
            "Jose",
            None,
            None,
            return_metadata=True,
            allow_degraded_hybrid_fallback=False,
            audio_quality_score=None
        )
        mock_transcribe_audio.assert_any_call(
            b"right_channel_bytes",
            "audio/wav",
            "Nete",
            "Jose",
            None,
            None,
            return_metadata=True,
            allow_degraded_hybrid_fallback=False,
            audio_quality_score=None
        )
        
        # Valida os metadados do Stereo Split
        self.assertTrue(metadata.get("stereo_split"))
        self.assertEqual(metadata.get("selected_strategy"), "stereo_split_dual_channel")
        
        # Valida a ordenação temporal e formatação
        self.assertEqual(len(final_segments), 4)
        
        # Verifica se o speaker_label foi limpo e atribuído corretamente
        self.assertEqual(final_segments[0]["text"], "Operador: Bom dia, central de monitoramento.")
        self.assertEqual(final_segments[0]["start"], "00:00.000")
        
        self.assertEqual(final_segments[1]["text"], "Jose: Bom dia, tudo bem.")
        self.assertEqual(final_segments[1]["start"], "00:06.000")
        
        self.assertEqual(final_segments[2]["text"], "Operador: Qual a placa do veículo?")
        self.assertEqual(final_segments[2]["start"], "00:10.000")
        
        self.assertEqual(final_segments[3]["text"], "Jose: A placa é ABC1234.")
        self.assertEqual(final_segments[3]["start"], "00:16.000")
        
        # Confiança deve ser forçada a 1.0 para o Stereo Split de canais isolados
        for seg in final_segments:
            self.assertEqual(seg["speaker_confidence"], 1.0)
            self.assertEqual(seg["speaker_risk"], "low")

if __name__ == '__main__':
    unittest.main()
