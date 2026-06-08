"""
Script para validar a paridade byte-a-byte (Fase 3).
Compara o resultado lido do arquivo `prompts.json` com o resultado reconstituído
a partir do banco de dados (tabela `ai_prompts`).
"""

import sys
import os
import json
import logging
from pathlib import Path

# Add backend to path so we can import from core and database
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import _load_json_config
from db.database import get_connection
from repositories.ai_prompts import list_prompts

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def run_parity_check():
    logger.info("Iniciando validacao de paridade da Fase 3 (AI Prompts)...")
    
    # 1. Carrega JSON raiz
    json_data = _load_json_config("prompts.json") or {}
    
    # 2. Carrega do DB
    db_data = list_prompts(get_connection)
    
    # 3. Compara keys raiz
    json_keys = set(json_data.keys())
    db_keys = set(db_data.keys())
    
    if json_keys != db_keys:
        logger.error(f"Diferenca nas chaves raiz! JSON: {json_keys} vs DB: {db_keys}")
        return False
        
    # 4. Compara valores profundamente
    def compare_dicts(d1, d2, path=""):
        diffs = 0
        for k in d1.keys():
            current_path = f"{path}.{k}" if path else k
            v1 = d1[k]
            v2 = d2.get(k)
            
            if isinstance(v1, dict):
                if not isinstance(v2, dict):
                    logger.error(f"Erro em {current_path}: JSON tem dict, DB tem {type(v2)}")
                    diffs += 1
                else:
                    diffs += compare_dicts(v1, v2, current_path)
            else:
                if v1 != v2:
                    logger.error(f"Erro em {current_path}: JSON='{v1}' vs DB='{v2}'")
                    diffs += 1
        return diffs
        
    diffs = compare_dicts(json_data, db_data)
    
    if diffs == 0:
        logger.info(f"SUCESSO! Paridade 100% garantida (verificadas {len(json_keys)} raizes).")
        return True
    else:
        logger.error(f"FALHA! Encontradas {diffs} diferencas profundas.")
        return False

if __name__ == "__main__":
    success = run_parity_check()
    sys.exit(0 if success else 1)
