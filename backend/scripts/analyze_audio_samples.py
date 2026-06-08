import asyncio
import json
import os

from core.classification import classify_audio
from schemas import AuditAlert, AuditCriterion
from services import process_audit_with_ai


def to_transcription_snippet(transcription_segments, max_chars: int = 200) -> str:
    text = " ".join(segment.text for segment in transcription_segments if getattr(segment, "text", ""))
    return text[:max_chars]


async def analyze_audios():
    base_dir = os.path.join("..", "Ligações", "LOGÍSTICA")
    categories = ["BOAS", "RUINS"]
    criteria_path = os.path.join("..", "src", "features", "audit", "data", "auditCriteria.json")
    results_file = "analysis_results.json"

    with open(criteria_path, "r", encoding="utf-8") as criteria_file:
        criteria_db = json.load(criteria_file)

    results = []

    for category in categories:
        category_dir = os.path.join(base_dir, category)
        if not os.path.exists(category_dir):
            continue

        for filename in os.listdir(category_dir):
            if not filename.lower().endswith((".wav", ".mp3")):
                continue

            filepath = os.path.join(category_dir, filename)
            print(f"Processing: {category} - {filename}")

            with open(filepath, "rb") as audio_file:
                audio_bytes = audio_file.read()

            try:
                print("  -> Classifying...")
                classification = await classify_audio(audio_bytes, filename)
                print(
                    "  -> Result: "
                    f"{classification.sector_label} / {classification.alert_label} / "
                    f"Conf: {classification.confidence}"
                )

                alert_id = classification.alert_id
                normalized_name = filename.upper()
                if alert_id in ["desconhecido", "erro"]:
                    if "ATRASO" in normalized_name:
                        alert_id = "4.4.2"
                    elif "DESVIO" in normalized_name:
                        alert_id = "4.4.10"
                    elif "PARADA" in normalized_name:
                        alert_id = "4.4.9"
                    elif "POSIÇÃO" in normalized_name or "POSICAO" in normalized_name:
                        alert_id = "4.4.11"
                    elif "TEMPERATURA" in normalized_name:
                        alert_id = "4.4.4"

                target_alert = None
                for sector in criteria_db.get("sectors", []):
                    for alert in sector.get("alerts", []):
                        if alert["id"] == alert_id:
                            target_alert = alert
                            break
                    if target_alert:
                        break

                if not target_alert:
                    print(f"  -> Warning: alert {alert_id} not found in DB")
                    continue

                criteria_list = [AuditCriterion(**criterion) for criterion in target_alert["criteria"]]
                alert = AuditAlert(
                    id=target_alert["id"],
                    label=target_alert["label"],
                    criteria=criteria_list,
                    context=target_alert.get("context", ""),
                )

                print("  -> Auditing...")
                audit_result, _, _ = await process_audit_with_ai(
                    audio_bytes,
                    "audio/wav" if filename.lower().endswith(".wav") else "audio/mpeg",
                    alert,
                    classification.operator_name or "Operador Teste",
                    "000",
                    "logistica",
                )

                print(f"  -> Audit Score: {audit_result.score}/{audit_result.maxPossibleScore}")

                failed_criteria = [
                    detail.label for detail in audit_result.criteria_results if detail.status != "pass"
                ]

                results.append(
                    {
                        "category": category,
                        "file": filename,
                        "classification": {
                            "sector_id": classification.sector_id,
                            "alert_id": classification.alert_id,
                            "alert_label": classification.alert_label,
                            "operator": classification.operator_name,
                            "confidence": classification.confidence,
                        },
                        "audit": {
                            "score": audit_result.score,
                            "max_possible_score": audit_result.maxPossibleScore,
                            "summary": audit_result.summary,
                            "failed_criteria": failed_criteria,
                            "transcription_snippet": to_transcription_snippet(audit_result.transcription),
                        },
                    }
                )

                with open(results_file, "w", encoding="utf-8") as output_file:
                    json.dump(results, output_file, ensure_ascii=False, indent=2)

            except Exception as exc:
                print(f"  -> Error: {exc}")


if __name__ == "__main__":
    asyncio.run(analyze_audios())
