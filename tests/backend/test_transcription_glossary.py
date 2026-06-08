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

    def test_autotrac_hallucination_patterns(self):
        """Verifica se os novos padrões para Autotrac estão presentes."""
        autotrac_entry = next((c for c in self.config['corrections'] if c['target'] == 'Autotrac'), None)
        self.assertIsNotNone(autotrac_entry)
        
        patterns = autotrac_entry['patterns']
        self.assertIn(r"\b[Aa]lto\s*trac[k]?\b", patterns)
        self.assertIn(r"\bAlto\s+Trac\b", patterns)

if __name__ == '__main__':
    unittest.main()
