import argparse
import hashlib
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=True)

from database import init_db, upsert_ligacao_auditada  # noqa: E402

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".m4a", ".webm"}

QUALIDADE_MAP = {
    "boa": "boa",
    "boas": "boa",
    "ruim": "ruim",
    "ruins": "ruim",
    "zerada": "zerada",
    "zeradas": "zerada",
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized


def normalize_path_parts(path: Path) -> list[str]:
    return [normalize_text(part) for part in path.parts]


def infer_quality(path_parts: list[str]) -> str:
    for part in path_parts:
        if part in QUALIDADE_MAP:
            return QUALIDADE_MAP[part]
    return "indefinida"


def infer_group(path_parts_original: list[str]) -> str:
    return path_parts_original[0] if path_parts_original else ""


def infer_subgroup(path_parts_original: list[str]) -> str | None:
    if len(path_parts_original) < 2:
        return None
    for part in path_parts_original[1:]:
        if normalize_text(part) in QUALIDADE_MAP:
            continue
        return part
    return None


def infer_sector_reference(path_parts_normalized: list[str]) -> str | None:
    if not path_parts_normalized:
        return None
    first = path_parts_normalized[0]
    if "cadastro" in first:
        return "cadastro"
    if "logistica" in first:
        return "logistica"
    if "unilever" in first:
        return "logistica_unilever"
    if "mondelez" in first:
        return "mondelez"
    return None


def infer_alert_reference(filename_without_extension: str, sector_reference: str | None) -> str | None:
    name = normalize_text(filename_without_extension)

    if "temperatura" in name and "motorista" in name:
        return "4.4.5"
    if "temperatura" in name and "cliente" in name:
        return "4.4.4"
    if "desligamento" in name and "temperatura" in name and "motorista" in name:
        return "4.4.7"
    if "desligamento" in name and "temperatura" in name and "cliente" in name:
        return "4.4.6"
    if "antecedente" in name:
        return "4.2.1"

    if sector_reference == "cadastro":
        return "4.2.1"

    if sector_reference == "logistica":
        if "atraso" in name and "cliente" in name:
            return "4.4.8"
        if "atraso" in name:
            return "4.4.2"
        if "parada" in name:
            return "4.4.9"
        if "desvio" in name:
            return "4.4.10"
        if "posicao" in name:
            return "4.4.11"
        if "temperatura" in name and "desligamento" in name:
            return "4.4.6"
        if "temperatura" in name:
            return "4.4.4"

    if sector_reference in {"mondelez", "logistica_unilever"}:
        if "devolucao" in name:
            return "4.3.1"
        if "cabinets" in name:
            return "4.3.2"
        if "loss tree" in name:
            return "4.3.3"
        if "atuacao tratativa" in name:
            return "4.3.4"

    return None


def compute_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as file_stream:
        while True:
            chunk = file_stream.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def import_calls(base_path: Path) -> dict:
    init_db()
    counters = Counter()
    for file_path in base_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        relative_path = file_path.relative_to(base_path)
        parts_original = list(relative_path.parts[:-1])
        parts_normalized = normalize_path_parts(Path(*parts_original))

        quality = infer_quality(parts_normalized)
        group = infer_group(parts_original)
        subgroup = infer_subgroup(parts_original)
        sector_reference = infer_sector_reference(parts_normalized)
        alert_reference = infer_alert_reference(file_path.stem, sector_reference)
        file_hash = compute_hash(file_path)

        upsert_ligacao_auditada(
            nome_arquivo=file_path.name,
            caminho_relativo=str(relative_path).replace("\\", "/"),
            hash_arquivo=file_hash,
            grupo=group,
            subgrupo=subgroup,
            setor_referencia=sector_reference,
            alerta_referencia=alert_reference,
            qualidade_referencia=quality,
            observacao="importacao_inicial_ligacoes",
        )

        counters["total"] += 1
        counters[f"qualidade_{quality}"] += 1
        if sector_reference:
            counters[f"setor_{sector_reference}"] += 1
        else:
            counters["setor_indefinido"] += 1

    return dict(counters)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa arquivos de audio da pasta Ligacoes para a tabela ligacoes_auditadas.")
    parser.add_argument(
        "--pasta",
        default=str(ROOT_DIR / "Ligações"),
        help="Caminho da pasta com os arquivos de ligacoes.",
    )
    args = parser.parse_args()
    base_path = Path(args.pasta)

    if not base_path.exists():
        raise FileNotFoundError(f"Pasta nao encontrada: {base_path}")

    result = import_calls(base_path)
    print("Importacao concluida")
    for key, value in sorted(result.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
