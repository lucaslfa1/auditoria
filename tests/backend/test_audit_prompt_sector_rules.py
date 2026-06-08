import json
import os
import sys
import unittest
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.audit_evaluator as audit_evaluator  # noqa: E402


class TestAuditPromptSectorRules(unittest.TestCase):
    def test_password_rule_is_not_applied_for_logistics_sector(self):
        dependencies = audit_evaluator.AuditEvaluationDependencies(
            prompts_config={"audit_system": {"regra_senha": "REGRA CRITICA - SENHAS"}},
            get_config_value=lambda _key, default="": default,
            get_colaboradores_para_prompt=lambda **_kwargs: [],
            parse_json_with_repair=lambda *_args, **_kwargs: {},
            ai_client=None,
            ai_audit_model="model",
            generation_config=None,
            azure_openai_key=None,
            azure_openai_endpoint=None,
            azure_openai_deployment="deployment",
            ai_priority="azure",
            ai_enabled=False,
        )

        prompt_logistica = audit_evaluator.get_audit_system_prompt(
            "Auditoria de contato com motorista sobre posicao em atraso.",
            "- ID: senha | Peso: 2.0 | Confirmacao de Senha",
            sector_id="logistica",
            dependencies=dependencies,
        )
        prompt_transferencia = audit_evaluator.get_audit_system_prompt(
            "Auditoria de alerta prioritario com motorista.",
            "- ID: senha | Peso: 2.0 | Confirmacao de Senha",
            sector_id="transferencia",
            dependencies=dependencies,
        )

        self.assertNotIn("REGRA CRITICA - SENHAS", prompt_logistica)
        self.assertIn("REGRA CRITICA - SENHAS", prompt_transferencia)

    def test_logistics_motorist_alerts_do_not_require_password(self):
        from db.scoring_loader import load_scoring_rules
        criteria_data = load_scoring_rules()

        logistica = next(sector for sector in criteria_data.get("sectors", []) if sector["id"] == "logistica")
        
        # New IDs used in scoring_rules.yaml
        target_alerts = {"LOGISTICA-POSICAO", "LOGISTICA-PARADA", "LOGISTICA-DESVIO"}

        for alert in criteria_data.get("alerts", []):
            if alert["sector"] == "logistica" and alert["id"] in target_alerts:
                criterion_labels = {str(criterion.get("label", "")).lower() for criterion in alert["criteria"]}
                self.assertFalse(any("senha" in label for label in criterion_labels), f"Alerta {alert['id']} nao deve exigir senha em logistica.")

    def test_prompt_includes_diarization_risk_block_when_available(self):
        dependencies = audit_evaluator.AuditEvaluationDependencies(
            prompts_config={"audit_system": {}},
            get_config_value=lambda _key, default="": default,
            get_colaboradores_para_prompt=lambda **_kwargs: [],
            parse_json_with_repair=lambda *_args, **_kwargs: {},
            ai_client=None,
            ai_audit_model="model",
            generation_config=None,
            azure_openai_key=None,
            azure_openai_endpoint=None,
            azure_openai_deployment="deployment",
            ai_priority="azure",
            ai_enabled=False,
        )

        prompt = audit_evaluator.get_audit_system_prompt(
            "Auditoria de contato com motorista.",
            "- ID: cordialidade | Peso: 1.0 | Cordialidade",
            audio_quality={
                "score": 1.0,
                "quality": "desconhecida",
                "diarization": {
                    "score": 0.51,
                    "quality": "baixa",
                    "swap_risk": "high",
                    "raw_speaker_count": 4,
                    "fragmented": True,
                    "ambiguous_ranges": [{"start": "00:10", "end": "00:12", "speaker": "operador", "text": "Trecho curto"}],
                },
            },
            sector_id="logistica",
            dependencies=dependencies,
        )

        self.assertIn("RISCO DE DIARIZACAO", prompt)
        self.assertIn("RISCO DE TROCA DE FALANTE: high", prompt)
        self.assertIn("Trecho curto", prompt)
        self.assertIn("Telefonia/URA", prompt)


if __name__ == "__main__":
    unittest.main()
