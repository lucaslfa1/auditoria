import argparse
import json
from pathlib import Path


AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg"}


def infer_interlocutor_label(path: Path) -> str:
    normalized = str(path).lower()
    if "ponto de apoio" in normalized or "posto" in normalized:
        return "Ponto de Apoio"
    if "pol" in normalized and "cia" in normalized:
        return "Policia"
    if "cadastro" in normalized:
        return "Cliente"
    if "mondelez" in normalized or "unilever" in normalized:
        return "Cliente"
    if "\\cliente\\" in normalized or "/cliente/" in normalized:
        return "Cliente"
    if "cliente-" in path.name.lower():
        return "Cliente"
    return "Motorista"


def infer_expected_max_speakers(interlocutor_label: str) -> int:
    return 2


def build_manifest(root: Path) -> list[dict]:
    items: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        interlocutor_label = infer_interlocutor_label(path)
        items.append(
            {
                "path": str(path.resolve()),
                "interlocutor_label": interlocutor_label,
                "expected_max_speakers": infer_expected_max_speakers(interlocutor_label),
            }
        )
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera um manifesto de benchmark de diarizacao a partir de um diretório.")
    parser.add_argument("--root", required=True, help="Diretório raiz dos áudios.")
    parser.add_argument("--output", required=True, help="Arquivo JSON de saída.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    manifest = build_manifest(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Manifesto salvo em: {output}")
    print(f"Áudios listados: {len(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
