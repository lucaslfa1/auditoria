import os
import sys
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from audio.speaker_identification import _tentar_mapear_speakers_com_llm
from audio.speaker_models import RawPhrase, SpeakerStats


class TestSpeakerIdentificationAzureDeployment(unittest.TestCase):
    def test_llm_mapping_uses_gpt4o_as_default_azure_deployment(self):
        phrases = [
            RawPhrase(
                timestamp=timedelta(seconds=0),
                duration_seconds=2.0,
                speaker_id=0,
                texto="Boa tarde, aqui e a central Opentech.",
                texto_normalizado="boa tarde aqui e a central opentech",
            ),
            RawPhrase(
                timestamp=timedelta(seconds=3),
                duration_seconds=2.0,
                speaker_id=1,
                texto="Estou parado no cliente aguardando descarga.",
                texto_normalizado="estou parado no cliente aguardando descarga",
            ),
        ]
        ids = [0, 1]
        stats_by_id = {0: SpeakerStats(), 1: SpeakerStats()}
        heuristic_by_id = {
            0: {
                "role": "Operador",
                "confidence": 0.9,
                "reason": "intro institucional",
                "operator_score": 8,
                "driver_score": 1,
            },
            1: {
                "role": "Motorista",
                "confidence": 0.8,
                "reason": "resposta operacional",
                "operator_score": 1,
                "driver_score": 7,
            },
        }

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"personas": [], "ambiguous_ids": []}'))]
        )

        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_KEY": "test-key",
                "AZURE_OPENAI_DEPLOYMENT": "",
            },
            clear=False,
        ):
            with patch("openai.AzureOpenAI", return_value=mock_client):
                _tentar_mapear_speakers_com_llm(
                    phrases,
                    ids,
                    stats_by_id,
                    heuristic_by_id,
                    operator_label="Operador",
                    driver_label="Motorista",
                )

        self.assertEqual(
            mock_client.chat.completions.create.call_args.kwargs["model"],
            "gpt-4o",
        )


if __name__ == "__main__":
    unittest.main()
