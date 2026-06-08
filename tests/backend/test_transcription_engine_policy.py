import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.transcription import _resolve_transcription_engine


class TestTranscriptionEngineDefault(unittest.TestCase):
    """Migracao: fast vira o engine padrao em todos os fluxos; hybrid_dual fica
    como LEGADO opt-in (so quando AZURE_TRANSCRIPTION_ENGINE=hybrid_dual)."""

    def test_default_is_fast(self):
        # Sem engine explicito, o padrao agora e fast (antes era hybrid_dual).
        self.assertEqual(_resolve_transcription_engine(None), "fast")
        self.assertEqual(_resolve_transcription_engine(""), "fast")
        self.assertEqual(_resolve_transcription_engine("   "), "fast")

    def test_fast_stays_fast(self):
        # 'fast' nao e mais convertido para hybrid_dual (protecao legada removida).
        self.assertEqual(_resolve_transcription_engine("fast"), "fast")

    def test_hybrid_dual_is_opt_in_legacy(self):
        # hybrid_dual continua disponivel como legado, quando pedido explicitamente.
        self.assertEqual(_resolve_transcription_engine("hybrid_dual"), "hybrid_dual")


if __name__ == "__main__":
    unittest.main()
