"""
Teste end-to-end do pipeline de auditoria.
Exercita: imports -> schemas -> result_from_raw -> exports -> app startup -> analytics -> re-avaliacao.
Resultados salvos em tests/e2e_results.txt.
"""
import sys
import os
import traceback
import io
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BASE_DIR))
RESULTS_FILE = Path(__file__).resolve().parent / "e2e_results.txt"
_log = []
PASS = 0
FAIL = 0

def log(msg=""):
    _log.append(msg)

def ok(label):
    global PASS; PASS += 1; log(f"  [OK] {label}")

def fail(label, err):
    global FAIL; FAIL += 1; log(f"  [FAIL] {label}: {err}")

def save():
    RESULTS_FILE.write_text("\n".join(_log), encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=True)

# ---- ETAPA 1: Imports ----
log("=== ETAPA 1: Importacao de modulos ===")
for name, imp in [
    ("schemas", "from schemas import AuditAlert, AuditCriterion, AuditResult, AuditResultDetail, TranscriptionSegment"),
    ("database", "import database"),
    ("services", "from services import transcribe_audio, evaluate_with_ai_priority, result_from_raw"),
    ("core.config", "from core.config import AI_MODEL, AI_AUDIT_MODEL, AI_PROVIDER_PRIORITY"),
    ("core.transcription", "from core.transcription import transcribe_audio, compute_input_hash"),
    ("core.evaluation", "from core.evaluation import evaluate_with_ai_priority, result_from_raw, validate_evaluation"),
    ("core.audit", "from core.audit import process_audit_with_ai, reevaluate_audit, extract_text_from_pdf"),
    ("core.export", "from core.export import generate_excel_report, generate_docx_report, generate_pdf_report, generate_docx_transcription, generate_pdf_transcription"),
    ("text_processing", "from text_processing import deduplicate_transcription_segments, filter_hallucinations, normalize_company_name"),
    ("classification", "from classification import classify_audio, classify_multiple_audios"),
    ("speaker_detection", "from speaker_detection import SpeakerDetectionService"),
    ("transcription_orchestrator", "from transcription_orchestrator import infer_interlocutor_label"),
    ("routers.auth", "from routers.auth import require_authenticated_user, require_admin"),
    ("routers.audit", "from routers.audit import router as audit_router"),
    ("routers.supervisor", "from routers.supervisor import router as supervisor_router"),
    ("routers.admin", "from routers.admin import router as admin_router"),
    ("repositories.analytics_quality", "from repositories.analytics_quality import get_indicators_by_sector, get_indicators_by_supervisor, get_indicators_by_operator, get_monthly_trend, get_top_failures"),
]:
    try:
        exec(imp)
        ok(name)
    except Exception as e:
        fail(name, e)

# ---- ETAPA 2: Config IA ----
log("\n=== ETAPA 2: Configuracao de IA ===")
from core.config import AI_MODEL, AI_AUDIT_MODEL, AI_PROVIDER_PRIORITY, AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT, AZURE_SPEECH_KEY, AI_API_KEY
log(f"  Provider: {AI_PROVIDER_PRIORITY}  Model: {AI_MODEL}  AuditModel: {AI_AUDIT_MODEL}")
log(f"  AZURE_KEY={'SET' if AZURE_OPENAI_KEY else 'NO'}  AZURE_ENDPOINT={'SET' if AZURE_OPENAI_ENDPOINT else 'NO'}  SPEECH={'SET' if AZURE_SPEECH_KEY else 'NO'}  GEMINI={'SET' if AI_API_KEY else 'NO'}")
ok("Config carregada")

# ---- ETAPA 3: result_from_raw ----
log("\n=== ETAPA 3: Construcao de AuditResult ===")
from schemas import AuditAlert, AuditCriterion, AuditResult
from core.evaluation import result_from_raw

criteria = [
    AuditCriterion(id="1", label="Identificacao", weight=10.0, description="Operador se identifica"),
    AuditCriterion(id="2", label="Cordialidade", weight=10.0, description="Operador e cordial"),
    AuditCriterion(id="3", label="Procedimento", weight=15.0, description="Solicita senha/placa"),
]
alert = AuditAlert(id="4.1.1", label="Alerta Prioritario", context="Ligacao de alerta", criteria=criteria)
mock_transcription = [
    {"start": "00:00", "end": "00:05", "text": "Operador: Boa tarde, aqui e o Lucas da central Opentech."},
    {"start": "00:05", "end": "00:08", "text": "Motorista: Boa tarde, aqui e o Joao."},
    {"start": "00:08", "end": "00:15", "text": "Operador: Joao, preciso confirmar. Qual a placa do veiculo?"},
    {"start": "00:15", "end": "00:18", "text": "Motorista: A placa e ABC 1234."},
    {"start": "00:18", "end": "00:28", "text": "Operador: Perfeito. Identificamos um alerta no seu veiculo."},
    {"start": "00:28", "end": "00:33", "text": "Motorista: Entendi, vou parar aqui no posto."},
    {"start": "00:33", "end": "00:40", "text": "Operador: Otimo, confirme quando estiver parado."},
    {"start": "00:40", "end": "00:45", "text": "Motorista: Ja estou parando."},
]
mock_eval = {
    "summary": "Atendimento exemplar.",
    "details": [
        {"criterionId": "1", "label": "Identificacao", "status": "pass", "weight": 10.0, "obtainedScore": 10.0, "comment": "OK"},
        {"criterionId": "2", "label": "Cordialidade", "status": "pass", "weight": 10.0, "obtainedScore": 10.0, "comment": "OK"},
        {"criterionId": "3", "label": "Procedimento", "status": "pass", "weight": 15.0, "obtainedScore": 15.0, "comment": "OK"},
    ],
}
result = None
try:
    result = result_from_raw(mock_eval, criteria, mock_transcription, "Lucas", "001", sector_id="monitoramento")
    assert isinstance(result, AuditResult)
    assert result.score == 35.0, f"Score {result.score} != 35.0"
    assert result.maxPossibleScore == 35.0
    assert len(result.details) == 3
    assert len(result.transcription) == 8
    ok(f"AuditResult: {result.score}/{result.maxPossibleScore}, {len(result.details)} criterios, {len(result.transcription)} segmentos")
except Exception as e:
    fail("result_from_raw", e)

# ---- ETAPA 4: Exports ----
log("\n=== ETAPA 4: Geracao de relatorios ===")
if result:
    from core.export import generate_excel_report, generate_docx_report, generate_pdf_report, generate_docx_transcription, generate_pdf_transcription
    for label, fn in [
        ("Excel report", generate_excel_report),
        ("DOCX report", generate_docx_report),
        ("PDF report", generate_pdf_report),
        ("DOCX transcricao", generate_docx_transcription),
        ("PDF transcricao", generate_pdf_transcription),
    ]:
        try:
            out = fn(result)
            assert out is not None, "Output is None"
            # exports may return BytesIO or bytes
            data = out.getvalue() if hasattr(out, 'getvalue') else out
            assert len(data) > 100, f"Output muito pequeno ({len(data)} bytes)"
            ok(f"{label}: {len(data)} bytes")
        except Exception as e:
            fail(label, e)
else:
    fail("Exports", "sem AuditResult")

# ---- ETAPA 5: FastAPI app ----
log("\n=== ETAPA 5: FastAPI app startup ===")
try:
    from main import app
    ok("main.py importado")
    routes = [r.path for r in app.routes if hasattr(r, 'path')]
    api_routes = [r for r in routes if r.startswith("/api/")]
    ok(f"{len(api_routes)} rotas API registradas")
    for prefix in ["/api/auth", "/api/audit", "/api/analytics", "/api/admin"]:
        matching = [r for r in api_routes if r.startswith(prefix)]
        if matching:
            ok(f"Router '{prefix}' ({len(matching)} endpoints)")
        else:
            fail(f"Router '{prefix}'", "nenhuma rota")
except Exception as e:
    fail("App startup", e)

# ---- ETAPA 6: Analytics ----
log("\n=== ETAPA 6: Database & Analytics ===")
try:
    import db.database as database
    ok("Database connection OK")
    from repositories.analytics_quality import get_indicators_by_sector, get_monthly_trend, get_top_failures
    s = get_indicators_by_sector(database.get_connection, None, None)
    ok(f"indicators_by_sector: {len(s)} setores")
    t = get_monthly_trend(database.get_connection)
    ok(f"monthly_trend: {len(t)} meses")
    f = get_top_failures(database.get_connection, None, None, limit=5)
    ok(f"top_failures: {len(f)} criterios")
except Exception as e:
    fail("Analytics queries", e)

# ---- ETAPA 7: Re-avaliacao binaria ----
log("\n=== ETAPA 7: Re-avaliacao binaria ===")
try:
    binary = {
        "summary": "Operador nao solicitou placa.",
        "details": [
            {"criterionId": "1", "label": "Identificacao", "status": "pass", "weight": 10.0, "obtainedScore": 10.0, "comment": "OK"},
            {"criterionId": "2", "label": "Cordialidade", "status": "fail", "weight": 10.0, "obtainedScore": 0.0, "comment": "Breve"},
            {"criterionId": "3", "label": "Procedimento", "status": "fail", "weight": 15.0, "obtainedScore": 0.0, "comment": "Nao solicitou"},
        ],
    }
    r2 = result_from_raw(binary, criteria, mock_transcription, "Joao", "002")
    assert r2.score == 10.0, f"Score {r2.score} != 10.0"
    assert any(d.status == "fail" for d in r2.details)
    ok(f"Binaria: {r2.score}/{r2.maxPossibleScore}")
    pdf = generate_pdf_report(r2)
    pdf_data = pdf.getvalue() if hasattr(pdf, 'getvalue') else pdf
    assert len(pdf_data) > 100
    ok(f"PDF binario: {len(pdf_data)} bytes")
except Exception as e:
    fail("Re-avaliacao binaria", e)

# ---- RESUMO ----
log(f"\n{'='*50}")
log(f"  RESULTADO: {PASS} passou, {FAIL} falhou")
log(f"{'='*50}")
if FAIL == 0:
    log("  SUCESSO - Pipeline funciona do inicio ao fim!")
else:
    log(f"  ATENCAO - {FAIL} etapa(s) falharam.")
log("")

save()
print(f"Resultados salvos em {RESULTS_FILE}")
print(f"{PASS} OK, {FAIL} FAIL")

if __name__ == "__main__":
    sys.exit(FAIL)
