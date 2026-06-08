import unittest
from datetime import datetime, timedelta, time
import json
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

# Importar o módulo a ser testado
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.huawei_d_minus_1 import _deve_executar

SP_TZ = ZoneInfo("America/Sao_Paulo")

class TestAutomationTodayFixes(unittest.TestCase):
    """Testes para as correções de automação do dia 27/05/2026."""

    def test_deve_executar_force_ignora_ja_concluido(self):
        """Valida que o parâmetro force=True permite re-executar dias concluídos."""
        # Simula uma execução que já aconteceu agora (last_attempt = now)
        # Sem force, ela seria bloqueada pelo intervalo de retry.
        now_sp = datetime.now(SP_TZ)
        run = {
            "status": "completed", 
            "attempts": 0, 
            "last_attempt_at": now_sp.isoformat()
        }
        horario = now_sp.time()
        
        # 1. Sem force: deve ser bloqueado pelo intervalo
        should_run_normal, reason_normal = _deve_executar(
            run, 
            now_sp=now_sp, 
            horario_execucao=horario,
            max_retries=3,
            retry_intervalo=timedelta(hours=1),
            is_today_d1=True,
            force=False
        )
        self.assertFalse(should_run_normal)
        self.assertEqual(reason_normal, "aguardando_intervalo_retry")

        # 2. Com force: deve ignorar o intervalo e retornar 'ok'
        should_run_force, reason_force = _deve_executar(
            run, 
            now_sp=now_sp, 
            horario_execucao=horario,
            max_retries=3,
            retry_intervalo=timedelta(hours=1),
            is_today_d1=True,
            force=True
        )
        self.assertTrue(should_run_force)
        self.assertEqual(reason_force, "ok")

    def test_deve_executar_completed_nao_bloqueia_mais(self):
        """Valida que o status 'completed' não é mais um estado terminal impeditivo."""
        # Simula um dia que terminou há 2 horas. 
        # O intervalo de retry é de 1 hora, então ele deve estar elegível para novo check automático.
        now_sp = datetime.now(SP_TZ)
        run = {
            "status": "completed", 
            "attempts": 0,
            "last_attempt_at": (now_sp - timedelta(hours=2)).isoformat()
        }
        horario = now_sp.time()
        
        should_run, reason = _deve_executar(
            run, 
            now_sp=now_sp, 
            horario_execucao=horario,
            max_retries=3,
            retry_intervalo=timedelta(hours=1),
            is_today_d1=True,
            force=False
        )
        
        self.assertTrue(should_run)
        self.assertEqual(reason, "ok")

if __name__ == '__main__':
    unittest.main()
