import logging
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel
import db.database as database
from repositories import operators
from routers.auth import require_admin
from core.fechamento_service import get_fechamento_rows, save_fechamento_overrides

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fechamento", tags=["fechamento"])

class FechamentoRowInput(BaseModel):
    layout_id: Optional[int] = None
    colab_id: int
    id: int
    mes_str: str
    matricula: str
    nome: str
    operacional: str
    telefonica: str
    desempenho: str
    status: str
    turno: str
    supervisor: str
    setor: str
    nota_mot: float
    nota_pa: float
    nota_cli: float
    nota_policia: float
    processo: str
    final: str
    huawei: str
    weon: str = ""

@router.get("/dados")
async def listar_dados(mes: int = Query(...), ano: int = Query(...), _user: dict = Depends(require_admin)):
    conn = database.get_connection()
    try:
        rows = get_fechamento_rows(conn, mes, ano)
        return rows
    except Exception as e:
        logger.error(f"Erro ao listar dados do fechamento: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar dados")
    finally:
        conn.close()


@router.get("/supervisores")
async def listar_supervisores(_user: dict = Depends(require_admin)):
    try:
        return operators.list_supervisores(database.get_connection)
    except Exception as e:
        logger.error(f"Erro ao listar supervisores do fechamento: {e}")
        raise HTTPException(status_code=500, detail="Erro ao carregar supervisores")


@router.post("/dados")
async def salvar_dados(
    mes: int = Query(...),
    ano: int = Query(...),
    dados: List[FechamentoRowInput] = Body(...),
    _user: dict = Depends(require_admin),
):
    conn = database.get_connection()
    try:
        rows_dict = [item.dict() for item in dados]
        save_fechamento_overrides(conn, mes, ano, rows_dict)
        return {"status": "success", "message": "Overrides salvos com sucesso"}
    except Exception as e:
        conn.rollback()
        logger.error(f"Erro ao salvar overrides do fechamento: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao salvar.")
    finally:
        conn.close()

@router.get("/exportar")
async def exportar_fechamento(mes: int = Query(...), ano: int = Query(...), _user: dict = Depends(require_admin)):
    try:
        from core.export_fechamento import generate_fechamento_excel  # lazy: evita openpyxl no boot
        excel_bytes = generate_fechamento_excel(database.get_connection, mes, ano)
        headers = {
            'Content-Disposition': f'attachment; filename="fechamento_{ano}_{mes:02d}.xlsx"'
        }
        return Response(content=excel_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
    except Exception as e:
        logger.error(f"Erro ao exportar fechamento: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao gerar Excel.")
