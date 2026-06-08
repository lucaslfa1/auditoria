import argparse
import json
from pathlib import Path

from benchmark_diarization_providers import _load_manifest, benchmark_entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa benchmark de diarizacao em batches com checkpoint incremental.")
    parser.add_argument("--manifest", required=True, help="Manifesto JSON.")
    parser.add_argument("--providers", default="azure", help="Lista separada por virgula.")
    parser.add_argument("--output", required=True, help="Arquivo JSON de saida.")
    parser.add_argument("--batch-size", type=int, default=10, help="Arquivos por batch.")
    parser.add_argument("--resume", action="store_true", help="Retoma a partir do arquivo de saida existente.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_path = Path(args.output).resolve()
    providers = [item.strip().lower() for item in args.providers.split(",") if item.strip()]
    batch_size = max(1, int(args.batch_size or 10))

    entries = _load_manifest(manifest_path)
    results: list[dict] = []
    processed_paths: set[str] = set()

    if args.resume and output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if isinstance(existing, list):
            results = existing
            processed_paths = {str(item.get("path")) for item in results if isinstance(item, dict)}

    pending = [entry for entry in entries if str(entry.get("path")) not in processed_paths]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start : batch_start + batch_size]
        for entry in batch:
            results.append(benchmark_entry(entry, providers))
        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Checkpoint: {len(results)}/{len(entries)} arquivos processados")

    print(f"Benchmark salvo em: {output_path}")
    print(f"Arquivos processados: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
