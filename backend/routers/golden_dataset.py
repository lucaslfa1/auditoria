"""Router dos exemplos-gabarito (golden dataset) para treino do RAG da auditoria.

Gerencia exemplos curados de avaliação ("boa"/"ruim") que servem de referência
para a IA. Os exemplos são persistidos como arquivos JSON no disco em
``data/rag_training/exemplos_gabarito`` (um arquivo por exemplo), NÃO no banco.

Endpoints sob ``/api/golden-dataset``: listar, criar, deletar e extrair os dados
crus de uma auditoria existente para pré-preencher o formulário de criação.

Sem custo de API paga (só I/O de arquivo e, no extract, leitura no banco).
"""

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
    """Payload de criação de um exemplo-gabarito.

    ``categoria`` é "boa" ou "ruim"; ``transcricao_resumida`` é a lista de linhas
    da transcrição; ``gabarito_avaliacao`` é o veredito por critério.
    """

    audit_id: Optional[int] = None
    cenario: str
    categoria: str # "boa" or "ruim"
    transcricao_resumida: List[str]
    gabarito_avaliacao: Dict[str, Any]

class GoldenDatasetListItem(BaseModel):
    """Resumo de um exemplo-gabarito na listagem (sem o conteúdo completo)."""

    id: str
    filename: str
    audit_id: Optional[int]
    cenario: str
    categoria: str
    created_at: float

def _ensure_dir():
    """Garante que o diretório de exemplos-gabarito existe (cria se faltar)."""
    os.makedirs(GOLDEN_DIR, exist_ok=True)

@router.get("", response_model=List[GoldenDatasetListItem])
def list_golden_examples():
    """Lista os exemplos-gabarito salvos, do mais novo para o mais antigo.

    Varre os ``*.json`` em ``GOLDEN_DIR``, lê os metadados de cada um (com
    fallbacks para formatos antigos) e ordena por data de modificação do arquivo.
    Arquivos ilegíveis são pulados (apenas logados em stdout). Efeito: leitura de
    arquivos no disco.
    """
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
    """Cria um novo exemplo-gabarito, persistindo-o como arquivo JSON.

    Gera um id único (``ex_<timestamp>_<uuid8>``), grava o JSON em ``GOLDEN_DIR``
    e retorna ``{"success", "id", "filename"}``. HTTP 500 se a gravação falhar.
    Efeito: escrita de arquivo no disco.
    """
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
    """Exclui o arquivo de um exemplo-gabarito pelo id.

    Sanitiza o id com ``os.path.basename`` para evitar directory traversal antes
    de montar o caminho. HTTP 404 se o arquivo não existir; HTTP 500 se a remoção
    falhar. Efeito: remoção de arquivo no disco.
    """
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
    """Extrai os dados crus de uma auditoria para pré-preencher o formulário.

    Lê a auditoria ``audit_id`` no banco e devolve operador, alerta, setor,
    resumo, a transcrição formatada em linhas "Falante: texto" e um rascunho do
    gabarito (mapa criterionId -> status) montado a partir dos detalhes. Não cria
    o exemplo — só monta o material para a UI. HTTP 404 se a auditoria não existir.
    Efeito: leitura no banco (conexão fechada no finally).
    """
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
