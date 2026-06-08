import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from core.huawei_client import HuaweiAICCClient
from core.huawei_sync import _load_config, _normalize_setor_regra
from core.automation_rules import AUTOMATION_RULES, filtrar_chamadas
import database

async def main():
    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    
    horas = 24
    agora = datetime.now(timezone.utc)
    begin_ms = int((agora - timedelta(hours=horas)).timestamp() * 1000)
    end_ms = int(agora.timestamp() * 1000)
    
    chamadas_in = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="INBOUND", limit=100)
    chamadas_out = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="OUTBOUND", limit=100)
    
    todas = chamadas_in + chamadas_out
    print(f"Total na VDN (24h): {len(todas)}")
    
    operadores = database.listar_auditaveis_com_id_huawei()
    print(f"Operadores: {len(operadores)}")
    
    chamadas_por_agente = {}
    for c in todas:
        agent_id = str(c.get("agentId") or c.get("agentid") or "").strip()
        if agent_id:
            chamadas_por_agente.setdefault(agent_id, []).append(c)

    for op in operadores:
        agent_id = op.get("id_huawei")
        nome_op = op.get("nome", "Desconhecido")
        chamadas_op = chamadas_por_agente.get(agent_id, [])
        
        if chamadas_op:
            setor_slug = _normalize_setor_regra(op.get("setor"))
            regra = AUTOMATION_RULES.get(setor_slug)
            
            print(f"\nOperador: {nome_op} ({agent_id}) - Setor: {setor_slug}")
            print(f"Chamadas brutas: {len(chamadas_op)}")
            
            for c in chamadas_op:
                print(f"  - CallID: {c.get('callId')} | Dir: {c.get('isCallIn')} | Dur: {c.get('duration')} | Reason: {c.get('callReason')} | End: {c.get('endTime')}")
                
            if regra:
                direcao_regra = str(regra.get("call_direction") or "").upper()
                if direcao_regra in {"INBOUND", "OUTBOUND"}:
                    is_inbound = direcao_regra == "INBOUND"
                    chamadas_op = [
                        c for c in chamadas_op 
                        if (str(c.get("isCallIn")).lower() == "true") == is_inbound
                    ]
                
                validas = filtrar_chamadas(chamadas_op, regra)
                print(f"Chamadas validas apos filtro ({direcao_regra}): {len(validas)}")
            else:
                print("Sem regra.")

if __name__ == "__main__":
    asyncio.run(main())
