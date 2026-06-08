import os
import sys
import json
import uuid
import datetime
import random

# Add backend directory to sys.path since this runs from root/backend generally
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
sys.path.append(backend_dir)

import db.database as database
from schemas import AuditResult, TranscriptionSegment, AuditResultDetail 
import hashlib

def generate_random_date(days_back=7):
    now = datetime.datetime.now()
    random_days = random.randint(0, days_back)
    random_seconds = random.randint(0, 86400)
    fake_date = now - datetime.timedelta(days=random_days, seconds=random_seconds)
    # Format exactly like main backend: YYYY-MM-DD HH:MM:SS
    return fake_date.strftime("%Y-%m-%d %H:%M:%S")

def main():
    print("Iniciando injeção de dados falsos para Piloto...")
    database.init_db()
    
    operadores = [("Carlos Almeida", "9901"), ("Maria Silva", "9902"), ("Joao Pedro", "9903")]
    
    # 30 amostras de demonstração
    for i in range(30):
        operador = random.choice(operadores)
        is_success = random.random() > 0.3 # 70% de aprovacao
        
        score_base = random.randint(70, 100) if is_success else random.randint(20, 65)
        
        result = AuditResult(
            transcription=[TranscriptionSegment(start="00:00:00", end="00:00:01", text="[Audio Simulado para Demonstração]")],
            summary=f"Auditoria Simulada #{i} gerada via script de Seed para Piloto.",
            details=[
                AuditResultDetail(
                    criterionId="sim_1",
                    label="Atendimento Padrão",
                    status="pass" if is_success else "fail",
                    weight=1.0,
                    obtainedScore=1.0 if is_success else 0.0,
                    comment="Evidência gerada via seed."
                )
            ],
            score=score_base,
            maxPossibleScore=100,
            timestamp=generate_random_date(),
            sentiment=None,
            operatorName=operador[0],
            operatorId=operador[1]
        )
        
        database.save_audit(
            result,
            input_hash=hashlib.md5(str(uuid.uuid4()).encode()).hexdigest(),
            alert_id="logistica",
            alert_label="Tratativa de Logística",
            operator_id=operador[1],
            driver_name=None,
            sector_id="operacao_taborda"
        )
        
    print(f"Sucesso! 30 auditorias de demonstração foram inseridas em database.db")

if __name__ == "__main__":
    main()
