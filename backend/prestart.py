"""Script de pré-start do container backend.

Executado uma vez antes de subir o servidor (boot do container), garante que o
sistema de arquivos esteja pronto para o app:

- ``/tmp`` existe (usado para arquivos temporários);
- a pasta ``dist`` existe com um ``index.html`` placeholder, para o mount de
  ``StaticFiles`` em ``main.py`` não falhar quando o build do frontend ainda não
  foi copiado.

Sem custo de API: só I/O local de arquivos. Roda como ``python prestart.py``.
"""

from pathlib import Path


def setup():
    """Prepara o filesystem antes do boot do servidor.

    Cria ``/tmp`` se faltar e cria ``dist/index.html`` placeholder se a pasta
    ``dist`` não existir. Efeito colateral: cria diretórios/arquivos e imprime o
    progresso no stdout. Idempotente (não sobrescreve um ``dist`` já existente).
    """
    print("--- EXECUTANDO PRE-START SETUP ---")

    # Garantir que a pasta /tmp exista (sempre existe, mas por seguranca).
    tmp_path = Path("/tmp")
    if not tmp_path.exists():
        tmp_path.mkdir(parents=True, exist_ok=True)

    # Criar a pasta dist se nao existir para o StaticFiles nao falhar no boot.
    dist_path = Path("dist")
    if not dist_path.exists():
        print("Criando pasta dist temporaria...")
        dist_path.mkdir(exist_ok=True)
        (dist_path / "index.html").write_text("<html><body>Loading...</body></html>")

    print("--- SETUP CONCLUIDO ---")


if __name__ == "__main__":
    setup()
