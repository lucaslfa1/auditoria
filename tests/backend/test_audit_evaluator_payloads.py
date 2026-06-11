import json
import os
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.audit_evaluator as audit_evaluator
from core.evaluation import result_from_raw
from schemas import AuditAlert, AuditCriterion


def _build_completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class TestAuditEvaluatorPayloads(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.criteria = [
            AuditCriterion(id="identificacao", label="Identificação Completa", weight=0.3, description=""),
            AuditCriterion(id="despedida", label="Despedida Padrão", weight=0.3, description=""),
        ]
        self.alert = AuditAlert(
            id="4.1.10",
            label="Parada Indevida - Polícia",
            context="Contato policial sobre suspeita de sinistro.",
            criteria=self.criteria,
        )

    def test_normalize_evaluation_payload_accepts_common_alternative_keys(self):
        raw_payload = {
            "resumo": "Resumo normalizado",
            "feedback": "Feedback ao operador",
            "criterios": [
                {
                    "criterio": "Identificação Completa",
                    "resultado": "pass",
                    "justificativa": "O operador se apresentou corretamente.",
                },
                {
                    "criterion_id": "despedida",
                    "status": "fail",
                    "comment": "A despedida foi breve.",
                },
            ],
            "flags_fatais": ["abandono_ligacao"],
        }

        normalized = audit_evaluator._normalize_evaluation_payload(raw_payload, self.criteria)

        self.assertEqual(normalized["summary"], "Resumo normalizado")
        self.assertEqual(normalized["ai_feedback"], "Feedback ao operador")
        self.assertEqual(
            normalized["details"],
            [
                {
                    "criterionId": "identificacao",
                    "status": "pass",
                    "comment": "O operador se apresentou corretamente.",
                    "timestamp": "",
                    "evidence_text": "",
                },
                {
                    "criterionId": "despedida",
                    "status": "fail",
                    "comment": "A despedida foi breve.",
                    "timestamp": "",
                    "evidence_text": "",
                },
            ],
        )
        self.assertEqual(normalized["fatal_flags"], ["abandono_ligacao"])

    async def test_evaluate_with_azure_retries_when_first_payload_is_invalid(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _build_completion(json.dumps({"resumo": "Sem checklist"})),
            _build_completion(
                json.dumps(
                    {
                        "resumo": "Operador conduziu bem a ligação.",
                        "criterios": [
                            {
                                "criterio": "Identificação Completa",
                                "resultado": "pass",
                                "justificativa": "Houve saudação e apresentação.",
                            }
                        ],
                    }
                )
            ),
        ]

        dependencies = audit_evaluator.AuditEvaluationDependencies(
            prompts_config={},
            get_config_value=lambda *_args, **_kwargs: "",
            get_colaboradores_para_prompt=lambda **_kwargs: [],
            parse_json_with_repair=lambda raw_text, _schema_hint: json.loads(raw_text),
            ai_client=None,
            ai_audit_model=None,
            generation_config=None,
            azure_openai_key="test-key",
            azure_openai_endpoint="https://example.openai.azure.com",
            azure_openai_deployment="gpt-4o",
            ai_priority="azure",
            ai_enabled=False,
        )

        with patch("openai.AzureOpenAI", return_value=mock_client):
            result = await audit_evaluator.evaluate_with_azure(
                transcription=[{"start": "00:00", "end": "00:10", "text": "Operador: bom dia."}],
                alert=self.alert,
                criteria_list=self.criteria,
                operator_name="Flávio",
                audio_quality=None,
                sector_id="transferencia",
                dependencies=dependencies,
            )

        self.assertEqual(mock_client.chat.completions.create.call_count, 2)
        self.assertEqual(result["summary"], "Operador conduziu bem a ligação.")
        self.assertEqual(result["details"][0]["criterionId"], "identificacao")
        self.assertEqual(result["details"][0]["status"], "pass")
        self.assertEqual(result["evidence_quality"]["missing_criteria_count"], 1)
        self.assertEqual(result["evidence_quality"]["reason"], "criterios_ausentes_na_resposta")

        first_call_kwargs = mock_client.chat.completions.create.call_args_list[0].kwargs
        response_format = first_call_kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        detail_schema = response_format["json_schema"]["schema"]["properties"]["details"]["items"]
        self.assertEqual(
            detail_schema["properties"]["criterionId"]["enum"],
            ["identificacao", "despedida"],
        )

        second_call_kwargs = mock_client.chat.completions.create.call_args_list[1].kwargs
        self.assertEqual(second_call_kwargs["response_format"]["type"], "json_schema")
        self.assertIn("criterionId", second_call_kwargs["messages"][1]["content"])
        self.assertIn("evidence_text", second_call_kwargs["messages"][1]["content"])
        self.assertIn("timestamp", second_call_kwargs["messages"][1]["content"])

    async def test_weak_evidence_retry_desligado_aceita_payload_valido_com_uma_chamada(self):
        """AUDIT_WEAK_EVIDENCE_RETRY=0: payload VALIDO com evidencia fraca e
        aceito sem a segunda chamada GPT-4o (alavanca de custo v1.3.117)."""
        weak_but_valid = json.dumps(
            {
                "resumo": "Operador conduziu a ligação.",
                "criterios": [
                    {
                        "criterio": "Identificação Completa",
                        "resultado": "pass",
                        "justificativa": "Apresentou-se.",
                    },
                    {
                        "criterio": "Despedida Padrão",
                        "resultado": "pass",
                        "justificativa": "Despediu-se.",
                    },
                ],
            }
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _build_completion(weak_but_valid)

        dependencies = audit_evaluator.AuditEvaluationDependencies(
            prompts_config={},
            get_config_value=lambda *_args, **_kwargs: "",
            get_colaboradores_para_prompt=lambda **_kwargs: [],
            parse_json_with_repair=lambda raw_text, _schema_hint: json.loads(raw_text),
            ai_client=None,
            ai_audit_model=None,
            generation_config=None,
            azure_openai_key="test-key",
            azure_openai_endpoint="https://example.openai.azure.com",
            azure_openai_deployment="gpt-4o",
            ai_priority="azure",
            ai_enabled=False,
        )

        with patch.dict(os.environ, {"AUDIT_WEAK_EVIDENCE_RETRY": "0"}):
            with patch("openai.AzureOpenAI", return_value=mock_client):
                result = await audit_evaluator.evaluate_with_azure(
                    transcription=[{"start": "00:00", "end": "00:10", "text": "Operador: bom dia."}],
                    alert=self.alert,
                    criteria_list=self.criteria,
                    operator_name="Flávio",
                    audio_quality=None,
                    sector_id="transferencia",
                    dependencies=dependencies,
                )

        self.assertEqual(mock_client.chat.completions.create.call_count, 1)
        self.assertEqual(result["summary"], "Operador conduziu a ligação.")

    async def test_weak_evidence_retry_default_mantem_segunda_chamada(self):
        """Sem a env, o comportamento historico (1 retry) e preservado."""
        weak_but_valid = json.dumps(
            {
                "resumo": "Operador conduziu a ligação.",
                "criterios": [
                    {
                        "criterio": "Identificação Completa",
                        "resultado": "pass",
                        "justificativa": "Apresentou-se.",
                    },
                    {
                        "criterio": "Despedida Padrão",
                        "resultado": "pass",
                        "justificativa": "Despediu-se.",
                    },
                ],
            }
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _build_completion(weak_but_valid)

        dependencies = audit_evaluator.AuditEvaluationDependencies(
            prompts_config={},
            get_config_value=lambda *_args, **_kwargs: "",
            get_colaboradores_para_prompt=lambda **_kwargs: [],
            parse_json_with_repair=lambda raw_text, _schema_hint: json.loads(raw_text),
            ai_client=None,
            ai_audit_model=None,
            generation_config=None,
            azure_openai_key="test-key",
            azure_openai_endpoint="https://example.openai.azure.com",
            azure_openai_deployment="gpt-4o",
            ai_priority="azure",
            ai_enabled=False,
        )

        env = dict(os.environ)
        env.pop("AUDIT_WEAK_EVIDENCE_RETRY", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("openai.AzureOpenAI", return_value=mock_client):
                result = await audit_evaluator.evaluate_with_azure(
                    transcription=[{"start": "00:00", "end": "00:10", "text": "Operador: bom dia."}],
                    alert=self.alert,
                    criteria_list=self.criteria,
                    operator_name="Flávio",
                    audio_quality=None,
                    sector_id="transferencia",
                    dependencies=dependencies,
                )

        self.assertEqual(mock_client.chat.completions.create.call_count, 2)
        self.assertEqual(result["summary"], "Operador conduziu a ligação.")

    def test_result_from_raw_marks_weak_evidence_in_audio_quality(self):
        raw_payload = {
            "summary": "Operador conduziu a ligacao.",
            "details": [
                {
                    "criterionId": "identificacao",
                    "status": "pass",
                    "comment": "Identificacao mencionada.",
                    "evidence_text": "",
                    "evidence_validation": {"matched": False, "status": "missing"},
                }
            ],
            "fatal_flags": [],
            "evidence_quality": {
                "quality": "muito_baixa",
                "review_recommended": True,
                "reason": "criterios_sem_evidencia",
                "evaluable_details": 1,
                "matched_evidence": 0,
                "missing_evidence": 1,
                "matched_ratio": 0.0,
            },
        }

        result = result_from_raw(
            raw_payload,
            self.criteria[:1],
            [{"start": "00:00", "end": "00:03", "text": "Operador: bom dia."}],
            operator_name="Flavio",
            audio_quality={"review_recommended": False, "review_priority": "low"},
            sector_id="transferencia",
        )

        self.assertTrue(result.audio_quality["review_recommended"])
        self.assertEqual(result.audio_quality["review_priority"], "high")
        self.assertEqual(result.audio_quality["evidence_quality"]["quality"], "muito_baixa")
        payload = json.dumps(result.model_dump(), ensure_ascii=False)
        self.assertNotRegex(payload, re.compile(r"[Rr]evis[aã]o\s+manual\s+(necess|recom)", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
