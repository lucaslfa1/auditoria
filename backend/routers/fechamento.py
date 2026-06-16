"""Router do Fechamento mensal de auditoria (planilha consolidada por operador).

Expõe os endpoints sob ``/api/fechamento`` (somente admin) que alimentam a tela
de Fechamento: listar/editar a planilha do mês, gerenciar quais operadores
aparecem no layout, listar supervisores e exportar o Excel consumido pelo BI.

A lógica de negócio vive em ``core.fechamento_service`` e ``core.export_fechamento``;
este módulo é a fina camada HTTP que abre/fecha conexão e mapeia erros para HTTP.

IMPORTANTE: o formato/labels do arquivo de Fechamento são contrato com o BI — não
alterar (ver memória "Fechamento intocável").

Sem custo de API paga (só PostgreSQL e geração de Excel via openpyxl/CPU).
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel
import db.database as database
from repositories import operators
from routers.auth import require_admin
from core.fechamento_service import (
    add_fechamento_layout_operador,
    get_fechamento_rows,
    remove_fechamento_layout_operador,
    save_fechamento_overrides,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fechamento", tags=["fechamento"])

class FechamentoRowInput(BaseModel):
    """Uma linha editável da planilha de fechamento (um operador no mês).

    Espelha as colunas exibidas/editadas na tela e exportadas para o BI: notas
    (mot/pa/cli/policia), dados cadastrais (matrícula, nome, setor, turno,
    supervisor), status e identificadores de integração (huawei, weon legado).
    """


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
    """Retorna as linhas da planilha de fechamento para o mês/ano informados.

    Lê via ``get_fechamento_rows`` (consolida cadastro + notas + overrides). Só
    admin. HTTP 500 em caso de falha. Efeito: leitura no banco (conexão fechada
    no finally).
    """
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
    """Lista os supervisores cadastrados (para filtros/seleção no fechamento).

    Só admin. HTTP 500 em falha. Efeito: leitura no banco.
    """
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
    """Salva as edições manuais (overrides) da planilha de fechamento do mês.

    Persiste cada linha enviada via ``save_fechamento_overrides``. Só admin. Faz
    rollback e responde HTTP 500 em caso de erro. Efeito: escrita no banco
    (conexão fechada no finally).
    """
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

class FechamentoAddOperadorInput(BaseModel):
    """Corpo para incluir um colaborador no layout do fechamento (por id)."""

    colaborador_id: int


class FechamentoRemoveOperadorInput(BaseModel):
    """Corpo para remover um operador do layout do fechamento.

    Aceita ``layout_id`` (linha do layout) ou ``colaborador_id``; pelo menos um
    deve ser informado (validação feita no service).
    """

    layout_id: Optional[int] = None
    colaborador_id: Optional[int] = None


@router.post("/layout/operadores")
async def adicionar_operador(payload: FechamentoAddOperadorInput, _user: dict = Depends(require_admin)):
    """Inclui (ou reativa) um colaborador na planilha do fechamento."""
    conn = database.get_connection()
    try:
        return add_fechamento_layout_operador(conn, payload.colaborador_id)
    except ValueError as e:
        conn.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        conn.rollback()
        logger.error(f"Erro ao adicionar operador ao fechamento: {e}")
        raise HTTPException(status_code=500, detail="Erro ao adicionar operador.")
    finally:
        conn.close()


@router.post("/layout/operadores/remover")
async def remover_operador(payload: FechamentoRemoveOperadorInput, _user: dict = Depends(require_admin)):
    """Remove um operador da planilha (desativa a linha; reversivel ao adicionar de novo)."""
    conn = database.get_connection()
    try:
        remove_fechamento_layout_operador(
            conn,
            layout_id=payload.layout_id,
            colaborador_id=payload.colaborador_id,
        )
        return {"status": "success"}
    except ValueError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        conn.rollback()
        logger.error(f"Erro ao remover operador do fechamento: {e}")
        raise HTTPException(status_code=500, detail="Erro ao remover operador.")
    finally:
        conn.close()


@router.get("/exportar")
async def exportar_fechamento(mes: int = Query(...), ano: int = Query(...), _user: dict = Depends(require_admin)):
    """Gera e baixa o Excel oficial do fechamento (a partir dos dados do banco).

    Constrói a planilha via ``generate_fechamento_excel`` (import lazy para não
    carregar openpyxl no boot) e retorna como anexo ``.xlsx``. Só admin. HTTP 500
    em falha. Este arquivo é o contrato consumido pelo BI — não alterar formato.
    """
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


@router.post("/exportar")
async def exportar_fechamento_tela_atual(
    mes: int = Query(...),
    ano: int = Query(...),
    dados: List[FechamentoRowInput] = Body(...),
    _user: dict = Depends(require_admin),
):
    """Exporta a tela atual sem persistir edições temporárias no banco."""
    try:
        from core.export_fechamento import generate_fechamento_excel_from_rows

        rows = [item.dict() for item in dados]
        excel_bytes = generate_fechamento_excel_from_rows(rows)
        headers = {
            'Content-Disposition': f'attachment; filename="fechamento_{ano}_{mes:02d}.xlsx"'
        }
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except Exception as e:
        logger.error(f"Erro ao exportar fechamento a partir da tela atual: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao gerar Excel.")
