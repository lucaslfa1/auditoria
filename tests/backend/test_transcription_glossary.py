import unittest
import json
import re

# Adicionar o backend ao path para carregar o arquivo de configuração
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

class TestTranscriptionGlossaryToday(unittest.TestCase):
    """Valida as atualizações do dicionário de blindagem fonética (27/05/2026)."""

    def setUp(self):
        # Carrega o arquivo de correções
        with open('backend/config/text_corrections.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def test_opentech_hallucination_patterns(self):
        """Verifica se os novos padrões para Opentech estão presentes."""
        opentech_entry = next((c for c in self.config['corrections'] if c['target'] == 'Opentech'), None)
        self.assertIsNotNone(opentech_entry)
        
        patterns = opentech_entry['patterns']
        
        # Casos relatados hoje (comparação literal do que está no JSON)
        self.assertIn(r"\bAlpen\s+Tech\b", patterns)
        self.assertIn(r"\bAlpentech\b", patterns)
        self.assertIn(r"\bAlpan\s*Tech\b", patterns)
        
        # Teste de matching (simulando a lógica do text_processing.py)
        sample_text = "A Alpen Tech é nossa parceira."
        regex_pattern = r"\bAlpen\s+Tech\b"
        self.assertTrue(re.search(regex_pattern, sample_text, re.IGNORECASE))

    def test_oputec_corrige_para_opentech(self):
        """Regressao (relatado por Lucas em 23/06): 'Oputec' e variantes foneticas
        devem virar 'Opentech' via normalize_company_name (case-insensitive)."""
        from utils.text_processing import normalize_company_name

        for variante in ("Oputec", "oputec", "Oputech", "Opu tec", "Oputeque", "Oputeck", "Oputex"):
            corrigido = normalize_company_name(f"a empresa {variante} monitora a carga")
            self.assertIn("Opentech", corrigido, f"nao corrigiu {variante!r}: {corrigido!r}")
            self.assertNotRegex(corrigido, r"(?i)\boput", f"sobrou 'oput' em {corrigido!r}")

    def test_novas_variantes_opentech(self):
        """Valida se as novas variantes fonéticas adicionadas em 26/06/2026 são devidamente corrigidas."""
        from utils.text_processing import normalize_company_name
        for variante in ("open check", "Open chat", "open tag", "ope tech", "Hope tech", "oculos tec"):
            corrigido = normalize_company_name(f"a empresa {variante} monitora a carga")
            self.assertIn("Opentech", corrigido, f"nao corrigiu {variante!r}: {corrigido!r}")

    def test_autotrac_hallucination_patterns(self):
        """Verifica se os novos padrões para Autotrac estão presentes."""
        autotrac_entry = next((c for c in self.config['corrections'] if c['target'] == 'Autotrac'), None)
        self.assertIsNotNone(autotrac_entry)

        patterns = autotrac_entry['patterns']
        self.assertIn(r"\b[Aa]lto\s*trac[k]?\b", patterns)
        self.assertIn(r"\bAlto\s+Trac\b", patterns)

    def test_pintech_corrige_para_opentech(self):
        """Regressao (relatado por Lucas em 02/07): 'pintech' e variantes devem virar 'Opentech'."""
        from utils.text_processing import normalize_company_name

        for variante in ("pintech", "Pintech", "PINTECH", "pin tech", "Pimtech", "pinteck"):
            corrigido = normalize_company_name(f"a empresa {variante} monitora a carga")
            self.assertIn("Opentech", corrigido, f"nao corrigiu {variante!r}: {corrigido!r}")


class TestFuzzyCorrections(unittest.TestCase):
    """Camada fuzzy fonética: corrige variantes NÃO enumeradas nos regex sem tocar em palavras legítimas."""

    def test_variantes_ineditas_de_opentech(self):
        """Variantes que nunca entraram no dicionário devem casar por fonética + distância."""
        from utils.text_processing import normalize_company_name

        for variante in ("opantech", "Openteki", "opemtek", "open teque", "opentexe"):
            corrigido = normalize_company_name(f"aqui é da {variante}, tudo bem?")
            self.assertIn("Opentech", corrigido, f"nao corrigiu {variante!r}: {corrigido!r}")

    def test_variantes_ineditas_de_outros_alvos(self):
        from utils.text_processing import normalize_company_name

        casos = {
            "mondelez": "Mondelez",
            "omnilinque": "Omnilink",
            "auto trak": "Autotrac",
            "unilever": "Unilever",
        }
        for variante, esperado in casos.items():
            corrigido = normalize_company_name(f"cliente {variante} confirmado")
            self.assertIn(esperado, corrigido, f"nao corrigiu {variante!r}: {corrigido!r}")

    def test_palavras_legitimas_nao_sao_alteradas(self):
        """Palavras comuns do domínio jamais podem ser 'corrigidas' para nomes de empresa."""
        from utils.text_processing import normalize_company_name

        frases = [
            "a gente vai verificar o modelo do veículo",
            "os modelos dos veículos estão no sistema",
            "qual a sigla da transportadora?",
            "vou sacar o dinheiro amanhã",
            "uma fintech de pagamentos",
            "o agente de campo chegou ontem",
            "aumente o volume por favor",
        ]
        for frase in frases:
            corrigido = normalize_company_name(frase)
            self.assertEqual(frase, corrigido, f"alterou frase legítima: {frase!r} -> {corrigido!r}")

    def test_termo_canonico_permanece_intacto(self):
        from utils.text_processing import normalize_company_name

        frase = "a Opentech monitora a carga da Mondelez"
        self.assertEqual(frase, normalize_company_name(frase))


class TestWhisperPromptWindow(unittest.TestCase):
    """O Whisper só considera os últimos 224 tokens do prompt: termos críticos devem ficar no FIM."""

    PRIORIDADE = ["Opentech", "nstech", "BAS"]

    def test_prompt_longo_e_cortado_e_preserva_criticos_no_fim(self):
        from transcription_providers.common import (
            fit_prompt_to_whisper_window,
            estimate_whisper_prompt_tokens,
            WHISPER_PROMPT_TOKEN_BUDGET,
        )

        # Simula o prompt gigante do banco: críticos no INÍCIO (posição que o Whisper descarta).
        prompt = "Opentech, nstech, BAS, " + ", ".join(f"termo{i}" for i in range(400)) + "."
        ajustado = fit_prompt_to_whisper_window(prompt, self.PRIORIDADE)

        self.assertLessEqual(estimate_whisper_prompt_tokens(ajustado), WHISPER_PROMPT_TOKEN_BUDGET)
        self.assertTrue(ajustado.rstrip(".").endswith("BAS"), f"críticos não estão no fim: ...{ajustado[-60:]!r}")
        self.assertIn("Opentech", ajustado)
        self.assertIn("nstech", ajustado)

    def test_prompt_curto_mantem_todos_os_termos(self):
        from transcription_providers.common import fit_prompt_to_whisper_window

        ajustado = fit_prompt_to_whisper_window("motorista, placa, sinistro.", self.PRIORIDADE)
        for termo in ("motorista", "placa", "sinistro", "Opentech", "nstech", "BAS"):
            self.assertIn(termo, ajustado)

    def test_prioridade_ausente_no_prompt_e_adicionada(self):
        from transcription_providers.common import fit_prompt_to_whisper_window

        ajustado = fit_prompt_to_whisper_window("motorista, placa.", ["Opentech"])
        self.assertIn("Opentech", ajustado)

    def test_deduplica_sem_distincao_de_caixa(self):
        from transcription_providers.common import fit_prompt_to_whisper_window

        ajustado = fit_prompt_to_whisper_window("opentech, motorista, OPENTECH.", ["Opentech"])
        self.assertEqual(1, ajustado.lower().count("opentech"))


if __name__ == '__main__':
    unittest.main()
