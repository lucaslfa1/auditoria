import argparse
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.automation import cleanup_classified_audio_storage


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Limpa arquivos orfaos de audio classificado da triagem.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Mantem arquivos nao referenciados mais novos que esta janela.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Executa a remocao. Sem esta flag, roda apenas em dry-run.",
    )
    args = parser.parse_args()

    result = cleanup_classified_audio_storage(
        retention_days=args.retention_days,
        dry_run=not args.apply,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
