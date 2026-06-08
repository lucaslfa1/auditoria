from pathlib import Path


def setup():
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
