"""Regra rigida de setor (STRICT_RH_SECTOR_ENFORCEMENT, default ON).

Remove o Guardrail D' (margem 'hora extra'): o setor da ligacao e SEMPRE forcado
para o setor oficial do operador no RH/matricula. Se o conteudo nao casa com
nenhum alerta do setor oficial -> 'desconhecido' (triagem manual), em vez de
manter o alerta de outro setor.

Rollback: STRICT_RH_SECTOR_ENFORCEMENT=false volta ao comportamento D'.
"""
import os
import unittest
from unittest.mock import patch

from core.classification import enforce_operator_and_direction_guardrails

FAKE_CATALOG = {
    "cadastro": {"label": "Cadastro", "alerts": [{"id": "CADASTRO-ANTECEDENTES", "label": "Antecedentes"}]},
    "logistica": {"label": "Logistica", "alerts": [{"id": "LOGISTICA-PARADA", "label": "Parada"}]},
}


def _env_without_flag() -> dict:
    env = dict(os.environ)
    env.pop("STRICT_RH_SECTOR_ENFORCEMENT", None)
    return env


class TestStrictRhSectorEnforcement(unittest.TestCase):
    def test_default_forces_rh_sector_and_desconhecido_on_no_match(self):
        # IA classificou logistica com ALTA confianca; operador e cadastro no RH.
        # Default (sem env) = rigido: forca cadastro; sem alerta de cadastro -> desconhecido.
        classification = {
            "sector_id": "logistica",
            "alert_id": "LOGISTICA-PARADA",
            "alert_label": "Parada",
            "confidence": 0.95,
        }
        with patch.dict(os.environ, _env_without_flag(), clear=True), \
             patch("core.classification.load_audit_criteria_catalog", return_value=FAKE_CATALOG), \
             patch("core.classification._resolve_db_sector_alias", side_effect=lambda s: (s or "").strip().lower()), \
             patch("core.classification._get_equivalent_alert_from_context", return_value=None):
            out = enforce_operator_and_direction_guardrails(
                dict(classification), "Operador X", db_sector="cadastro"
            )
        self.assertEqual(out["sector_id"], "cadastro", "deveria forcar o setor oficial do RH")
        self.assertEqual(out["alert_id"], "desconhecido", "sem alerta do setor oficial -> desconhecido")

    def test_flag_off_restores_hora_extra_preservation(self):
        # Rollback STRICT_RH_SECTOR_ENFORCEMENT=false -> D': IA confiante em setor
        # diferente preserva o setor da IA (margem 'hora extra').
        classification = {
            "sector_id": "logistica",
            "alert_id": "LOGISTICA-PARADA",
            "alert_label": "Parada",
            "confidence": 0.95,
        }
        with patch.dict(os.environ, {"STRICT_RH_SECTOR_ENFORCEMENT": "false"}, clear=False), \
             patch("core.classification._resolve_db_sector_alias", side_effect=lambda s: (s or "").strip().lower()):
            out = enforce_operator_and_direction_guardrails(
                dict(classification), "Operador X", db_sector="cadastro"
            )
        self.assertEqual(out["sector_id"], "logistica", "modo D' deveria preservar o setor da IA")
        self.assertEqual(out["alert_id"], "LOGISTICA-PARADA")


if __name__ == "__main__":
    unittest.main()
