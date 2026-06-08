from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import json
import glob
import time
from uuid import uuid4

router = APIRouter(prefix="/api/golden-dataset", tags=["Exemplos de Treinamento"])

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "rag_training", "exemplos_gabarito")

class GoldenDatasetExample(BaseModel):
    audit_id: Optional[int] = None
    cenario: str
    categoria: str # "boa" or "ruim"
    transcricao_resumida: List[str]
    gabarito_avaliacao: Dict[str, Any]

class GoldenDatasetListItem(BaseModel):
    id: str
    filename: str
    audit_id: Optional[int]
    cenario: str
    categoria: str
    created_at: float

def _ensure_dir():
    os.makedirs(GOLDEN_DIR, exist_ok=True)

@router.get("", response_model=List[GoldenDatasetListItem])
def list_golden_examples():
    _ensure_dir()
    examples = []
    for filepath in glob.glob(os.path.join(GOLDEN_DIR, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                filename = os.path.basename(filepath)
                # Fallbacks for older formats if any
                examples.append(GoldenDatasetListItem(
                    id=filename.replace('.json', ''),
                    filename=filename,
                    audit_id=data.get("audit_id"),
                    cenario=data.get("cenario", "Sem cenário"),
                    categoria=data.get("categoria", "boa"),
                    created_at=os.path.getmtime(filepath)
                ))
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
    
    # Sort newest first
    examples.sort(key=lambda x: x.created_at, reverse=True)
    return examples

@router.post("")
def create_golden_example(example: GoldenDatasetExample):
    _ensure_dir()
    example_id = f"ex_{int(time.time())}_{str(uuid4())[:8]}"
    filename = f"{example_id}.json"
    filepath = os.path.join(GOLDEN_DIR, filename)
    
    data = example.dict()
    data["id"] = example_id
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"success": True, "id": example_id, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar exemplo: {str(e)}")

@router.delete("/{example_id}")
def delete_golden_example(example_id: str):
    _ensure_dir()
    # Basic sanitize to prevent directory traversal
    safe_id = os.path.basename(example_id).replace(".json", "")
    filepath = os.path.join(GOLDEN_DIR, f"{safe_id}.json")
    
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao deletar arquivo: {str(e)}")
    
    raise HTTPException(status_code=404, detail="Exemplo não encontrado")

@router.get("/{audit_id}/extract")
def extract_audit_data_for_training(audit_id: int):
    # This endpoint extracts raw audit data to pre-fill the UI modal
    from db.database import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT operator_name, alert_label, sector_id, summary, transcription_json, details_json
            FROM audits
            WHERE id = %s
        """, (audit_id,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Auditoria não encontrada")
            
        transcription_raw = row[4]
        if isinstance(transcription_raw, str):
            try:
                transcription = json.loads(transcription_raw)
            except:
                transcription = []
        else:
            transcription = transcription_raw or []
            
        # Format transcription into simple lines
        formatted_transcription = []
        for t in transcription:
            speaker = t.get("speaker", "")
            text = t.get("text", "")
            # If text already includes the prefix (e.g. "Operador: hello"), avoid duplicating it
            if speaker and not text.startswith(speaker):
                 formatted_transcription.append(f"{speaker}: {text}")
            else:
                 formatted_transcription.append(text)
                 
        # Format details into gabarito draft
        details_raw = row[5]
        if isinstance(details_raw, str):
            try:
                details = json.loads(details_raw)
            except:
                details = []
        else:
            details = details_raw or []
            
        gabarito = {}
        for d in details:
            gabarito[d.get("criterionId", "unknown")] = d.get("status", "")
            
        return {
            "audit_id": audit_id,
            "operator_name": row[0],
            "alert_label": row[1],
            "sector_id": row[2],
            "summary": row[3],
            "transcricao_resumida": formatted_transcription,
            "gabarito_avaliacao": gabarito
        }
    finally:
        conn.close()
