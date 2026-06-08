import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to PYTHONPATH
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from core.audit import process_audit_with_ai
from schemas import AuditAlert


async def main():
    audio_path = Path(r"D:\auditoria\ligacoes\CADASTRO\BOAS\ANTECEDENTES-agent-11214-5_11_2025_17_13_3-node01-1762373580-26728.wav")
    if not audio_path.exists():
        print(f"File not found: {audio_path}")
        return

    audio_bytes = audio_path.read_bytes()
    mime_type = "audio/wav"
    sector_id = "cadastro"
    alert = AuditAlert(id="mock", placa="XXX-0000", tipo_alerta="TESTE", detalhes="TESTE", criteria=[])

    results = {}

    for engine in ["fast", "hybrid_dual"]:
        print(f"\n--- Running pipeline with engine: {engine} ---")
        os.environ["AZURE_TRANSCRIPTION_ENGINE"] = engine

        try:
            audit_result, _, _ = await process_audit_with_ai(
                audio_file=audio_bytes,
                mime_type=mime_type,
                alert=alert,
                operator_name="Operador Teste",
                operator_id=None,
                sector_id=sector_id,
            )

            # Extract relevant info for comparison
            extracted_text = "\n".join([f"[{s.start}] {s.text}" for s in audit_result.transcription])

            criteria_evaluations = {}
            for detail in audit_result.details:
                criteria_evaluations[detail.label] = {
                    "status": detail.status,
                    "justificativa": detail.comment
                }

            results[engine] = {
                "diarization_score": audit_result.audio_quality.get("diarization", {}).get("score", 0),
                "segment_count": len(audit_result.transcription),
                "transcription_preview": extracted_text[:1000] + "...",
                "full_transcription": extracted_text,
                "criteria_evaluated": criteria_evaluations,
                "quality": audit_result.audio_quality.get("diarization", {}).get("quality", "UNKNOWN"),
                "total_score": audit_result.score,
            }
            print(f"Finished {engine}. Score: {audit_result.score}, Diarization Score: {results[engine]['diarization_score']}")

        except Exception as e:
            print(f"Error with {engine}: {e}")
            results[engine] = {"error": str(e)}

    # Compare output
    output_path = Path("D:/auditoria/backend/tmp/full_pipeline_comparison.json")
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull comparison saved to: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
