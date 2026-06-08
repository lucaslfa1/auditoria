"""Pacote de testes do backend.

Os testes legados em `backend/tests/` faziam `sys.path.append("..")` apontando
para `backend/` (parent direto). Apos a reorganizacao em `tests/backend/`, esse
`..` passou a apontar para `tests/`, quebrando todos os `from core.X import`,
`from storage.X import`, etc.

Em vez de editar 97 arquivos para corrigir o path, este `__init__.py` injeta
o `backend/` no `sys.path` quando o package `tests.backend` eh carregado. Isso
funciona tanto sob `pytest` quanto `unittest discover`, pois ambos importam o
package antes de executar os modulos `test_*.py`.
"""
import os
import sys

_BACKEND_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if _BACKEND_PATH not in sys.path:
    sys.path.insert(0, _BACKEND_PATH)
