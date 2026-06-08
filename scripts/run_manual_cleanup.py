import sys
import os

# Ensure we are running from the backend directory context
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import database

def run_cleanup():
    try:
        result = database.limpar_fila_revisao_classificacao_antiga(24)
        print(f"Cleanup successful. Deleted items: {result.get('deleted', 0)}")
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    run_cleanup()
