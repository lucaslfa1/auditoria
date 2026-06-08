import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

import services  # noqa: E402
from audio.diarization_quality import detect_audio_mime_type, build_diarization_reference, build_diarization_quality


def _detect_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".ogg":
        return "audio/ogg"
    return "application/octet-stream"


def _risk_rank(value: str) -> int:
    normalized = str(value or "").strip().lower()
    return {"low": 0, "medium": 1, "high": 2}.get(normalized, 3)


def _quality_rank(value: str) -> int:
    normalized = str(value or "").strip().lower()
    return {
        "boa": 3,
        "regular": 2,
        "baixa": 1,
        "muito_baixa": 0,
    }.get(normalized, -1)


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("O manifesto deve ser uma lista JSON.")
    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        audio_path = Path(str(item.get("path", "")).strip())
        if not audio_path.is_absolute():
            audio_path = (path.parent / audio_path).resolve()
        normalized.append({**item, "path": str(audio_path)})
    return normalized


def _run_provider(
    provider: str,
    audio_bytes: bytes,
    mime_type: str,
    operator_name: str | None,
    driver_name: str | None,
    interlocutor_label: str,
) -> list[dict]:
    if provider == "azure":
        return services.transcribe_audio_azure(
            audio_bytes,
            "Operador",
            interlocutor_label,
            operator_name=operator_name,
            driver_name=driver_name,
            mime_type=mime_type,
        )
    if provider == "gpt4o_diarize":
        return services.transcribe_audio_gpt4o_diarize(
            audio_bytes,
            mime_type,
            "Operador",
            interlocutor_label,
        )
    if provider == "whisper":
        from core.config import _resolve_azure_whisper_config
        w_endpoint, w_key = _resolve_azure_whisper_config()
        if not w_endpoint or not w_key:
            raise RuntimeError("Azure Whisper nao configurado no .env")
        return services.transcribe_audio_azure(
            audio_bytes,
            "Operador",
            interlocutor_label,
            operator_name=operator_name,
            driver_name=driver_name,
            mime_type=mime_type,
            endpoint_override=w_endpoint,
            api_key_override=w_key,
        )
    if provider == "hybrid_dual":
        import asyncio
        import os
        from core.transcription import transcribe_audio

        # Save original engine and force hybrid_dual
        original_engine = os.environ.get("AZURE_TRANSCRIPTION_ENGINE")
        os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "hybrid_dual"
        try:
            results = asyncio.run(
                transcribe_audio(
                    audio_bytes,
                    mime_type,
                    operator_name=operator_name,
                    driver_name=driver_name,
                )
            )
            return results[0] if isinstance(results, tuple) else results
        finally:
            if original_engine is not None:
                os.environ["AZURE_TRANSCRIPTION_ENGINE"] = original_engine
            else:
                del os.environ["AZURE_TRANSCRIPTION_ENGINE"]

    raise ValueError(f"Provedor nao suportado: {provider}")


def _preview_text(segments: list[dict], max_segments: int = 3) -> list[str]:
    preview: list[str] = []
    for segment in segments[:max_segments]:
        if not isinstance(segment, dict):
            continue
        preview.append(str(segment.get("text", "")).strip()[:220])
    return preview


def _build_summary(results: list[dict[str, Any]], providers: list[str]) -> dict[str, Any]:
    provider_summary: dict[str, Any] = {}
    for provider in providers:
        ok_entries = []
        errors = 0
        quality_counts = {"boa": 0, "regular": 0, "baixa": 0, "muito_baixa": 0}
        risk_counts = {"low": 0, "medium": 0, "high": 0}
        total_score = 0.0
        total_segments = 0

        for item in results:
            provider_payload = item.get("providers", {}).get(provider, {})
            if provider_payload.get("status") != "ok":
                errors += 1
                continue
            diarization = provider_payload.get("diarization", {})
            ok_entries.append(provider_payload)
            total_score += float(diarization.get("score") or 0.0)
            total_segments += int(provider_payload.get("segment_count") or 0)
            quality_label = str(diarization.get("quality") or "").strip().lower()
            risk_label = str(diarization.get("swap_risk") or "").strip().lower()
            if quality_label in quality_counts:
                quality_counts[quality_label] += 1
            if risk_label in risk_counts:
                risk_counts[risk_label] += 1

        processed = len(ok_entries)
        provider_summary[provider] = {
            "processed": processed,
            "errors": errors,
            "avg_diarization_score": round(total_score / processed, 3) if processed else 0.0,
            "avg_segment_count": round(total_segments / processed, 1) if processed else 0.0,
            "quality_counts": quality_counts,
            "swap_risk_counts": risk_counts,
        }

    comparisons: dict[str, Any] = {}
    for left, right in itertools.combinations(providers, 2):
        comparable = 0
        left_better = 0
        right_better = 0
        ties = 0
        total_delta = 0.0
        left_risk_better = 0
        right_risk_better = 0
        left_quality_better = 0
        right_quality_better = 0

        for item in results:
            providers_payload = item.get("providers", {})
            left_payload = providers_payload.get(left, {})
            right_payload = providers_payload.get(right, {})
            if left_payload.get("status") != "ok" or right_payload.get("status") != "ok":
                continue

            comparable += 1
            left_diarization = left_payload.get("diarization", {})
            right_diarization = right_payload.get("diarization", {})
            left_score = float(left_diarization.get("score") or 0.0)
            right_score = float(right_diarization.get("score") or 0.0)
            delta = round(right_score - left_score, 3)
            total_delta += delta
            if abs(delta) < 0.015:
                ties += 1
            elif delta > 0:
                right_better += 1
            else:
                left_better += 1

            left_risk = _risk_rank(left_diarization.get("swap_risk"))
            right_risk = _risk_rank(right_diarization.get("swap_risk"))
            if left_risk < right_risk:
                left_risk_better += 1
            elif right_risk < left_risk:
                right_risk_better += 1

            left_quality = _quality_rank(left_diarization.get("quality"))
            right_quality = _quality_rank(right_diarization.get("quality"))
            if left_quality > right_quality:
                left_quality_better += 1
            elif right_quality > left_quality:
                right_quality_better += 1

        comparisons[f"{left}__vs__{right}"] = {
            "comparable": comparable,
            "score_delta_avg": round(total_delta / comparable, 3) if comparable else 0.0,
            f"{left}_better_by_score": left_better,
            f"{right}_better_by_score": right_better,
            "ties_by_score": ties,
            f"{left}_better_by_swap_risk": left_risk_better,
            f"{right}_better_by_swap_risk": right_risk_better,
            f"{left}_better_by_quality_label": left_quality_better,
            f"{right}_better_by_quality_label": right_quality_better,
        }

    return {
        "providers": provider_summary,
        "comparisons": comparisons,
    }


def benchmark_entry(entry: dict[str, Any], providers: list[str]) -> dict[str, Any]:
    path = Path(entry["path"])
    audio_bytes = path.read_bytes()
    mime_type = detect_audio_mime_type(audio_bytes, _detect_mime_type(path))
    operator_name = str(entry.get("operator_name") or "").strip() or None
    driver_name = str(entry.get("driver_name") or "").strip() or None
    interlocutor_label = str(entry.get("interlocutor_label") or "Motorista").strip() or "Motorista"
    expected_max_speakers = entry.get("expected_max_speakers")
    diarization_reference = build_diarization_reference(
        interlocutor_label,
        expected_max_speakers=expected_max_speakers,
    )

    result: dict[str, Any] = {
        "path": str(path),
        "mime_type": mime_type,
        "interlocutor_label": interlocutor_label,
        "expected_max_speakers": diarization_reference.get("expected_max_speakers"),
        "providers": {},
    }

    for provider in providers:
        try:
            segments = _run_provider(
                provider,
                audio_bytes,
                mime_type,
                operator_name,
                driver_name,
                interlocutor_label,
            )
            diarization = build_diarization_quality(
                segments,
                {"diarization_reference": diarization_reference},
            ).get("diarization", {})
            result["providers"][provider] = {
                "status": "ok",
                "segment_count": len(segments),
                "diarization": diarization,
                "preview": _preview_text(segments),
            }
        except Exception as exc:
            result["providers"][provider] = {
                "status": "error",
                "error": str(exc),
            }

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark local de diarizacao para comparar Azure Fast e GPT-4o diarize."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Arquivo JSON com lista de audios. Cada item deve conter 'path' e pode conter 'interlocutor_label', 'operator_name' e 'driver_name'.",
    )
    parser.add_argument(
        "--providers",
        default="azure,gpt4o_diarize",
        help="Lista separada por virgula. Valores suportados: azure, gpt4o_diarize.",
    )
    parser.add_argument(
        "--output",
        default="backend/benchmark_diarization_results.json",
        help="Arquivo JSON de saida.",
    )
    parser.add_argument(
        "--summary-output",
        default="",
        help="Arquivo JSON opcional com resumo agregado do comparativo.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Indice inicial dentro do manifesto.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Quantidade maxima de arquivos a processar. Zero significa todos.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_path = Path(args.output).resolve()
    providers = [item.strip().lower() for item in args.providers.split(",") if item.strip()]

    entries = _load_manifest(manifest_path)
    offset = max(0, int(args.offset or 0))
    limit = max(0, int(args.limit or 0))
    if offset:
        entries = entries[offset:]
    if limit:
        entries = entries[:limit]
    results = [benchmark_entry(entry, providers) for entry in entries]
    summary = _build_summary(results, providers)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.summary_output:
        summary_path = Path(args.summary_output).resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Benchmark salvo em: {output_path}")
    print(f"Arquivos processados: {len(results)}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
