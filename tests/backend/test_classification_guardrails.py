import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.scoring_loader import load_scoring_rules
from core.classification import (
    align_classification_with_catalog,
    build_sectors_and_alerts_prompt,
    enforce_alert_hierarchy_guardrail,
    enforce_context_not_non_auditable_guardrail,
    enforce_parada_desvio_guardrail,
    enforce_temperature_guardrail,
    load_audit_criteria_catalog,
    parse_filename,
)


class TestClassificationGuardrails(unittest.TestCase):
    def test_catalog_alignment_updates_alert_label(self):
        classification = {
            "sector_id": "transferencia",
            "sector_label": "Transferencia",
            "alert_id": "UTI-PRIORITARIO-MOT",
            "alert_label": "Incorreto",
            "confidence": 0.9,
        }

        result = align_classification_with_catalog(classification)

        self.assertEqual(result["sector_id"], "transferencia")
        self.assertEqual(result["alert_id"], "TRANSFERENCIA-PRIORITARIO-MOT")
        self.assertIn("Priorit", result["alert_label"])

    def test_catalog_alignment_preserves_mot_when_remapping_to_distribution(self):
        classification = {
            "sector_id": "distribuicao",
            "sector_label": "Distribuicao",
            "alert_id": "UTI-POSICAO-MOT",
            "alert_label": "Posicao",
            "confidence": 0.9,
        }

        result = align_classification_with_catalog(classification)

        self.assertEqual(result["sector_id"], "distribuicao")
        self.assertEqual(result["alert_id"], "DISTRIBUICAO-POSICAO-MOT")

    def test_catalog_alignment_keeps_valid_sector_and_marks_unknown_alert(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "ALERTA-INEXISTENTE",
            "alert_label": "Algo Incorreto",
            "confidence": 0.72,
        }

        result = align_classification_with_catalog(classification)

        self.assertEqual(result["sector_id"], "logistica")
        self.assertEqual(result["alert_id"], "desconhecido")
        self.assertEqual(result["alert_label"], "Nao Identificado")

    def test_catalog_alignment_marks_unknown_sector_and_alert_when_nothing_matches(self):
        classification = {
            "sector_id": "setor-inexistente",
            "sector_label": "Setor Inexistente",
            "alert_id": "ALERTA-INEXISTENTE",
            "alert_label": "Algo Incorreto",
            "confidence": 0.40,
        }

        result = align_classification_with_catalog(classification)

        self.assertEqual(result["sector_id"], "desconhecido")
        self.assertEqual(result["sector_label"], "Nao Identificado")
        self.assertEqual(result["alert_id"], "desconhecido")
        self.assertEqual(result["alert_label"], "Nao Identificado")

    def test_catalog_alignment_maps_legacy_police_alert_to_canonical_id(self):
        classification = {
            "sector_id": "bas",
            "sector_label": "BAS",
            "alert_id": "BAS-POLICIAL",
            "alert_label": "Acionamento Policial",
            "confidence": 0.95,
        }

        result = align_classification_with_catalog(classification)

        self.assertEqual(result["sector_id"], "bas")
        self.assertEqual(result["alert_id"], "BAS-PRIORITARIO-POLICIA")

    def test_temperature_reclassifies_cadastro_to_logistica(self):
        classification = {
            "sector_id": "cadastro",
            "sector_label": "Setor Cadastro",
            "alert_id": "CADASTRO-ANTECEDENTES",
            "alert_label": "Antecedentes - Receptivo",
            "confidence": 0.42,
        }
        transcription = "Operador informa controle de temperatura e pergunta ao motorista sobre o setpoint."

        result = enforce_temperature_guardrail(classification, transcription, "teste.wav")

        self.assertEqual(result["sector_id"], "logistica")
        self.assertEqual(result["alert_id"], "LOGISTICA-TEMPERATURA-MOT")
        self.assertGreaterEqual(float(result["confidence"]), 0.82)

    def test_maintenance_context_with_parada_is_auditable(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "INFORMATIVO",
            "alert_label": "Nao Auditavel (Manutencao)",
            "confidence": 0.93,
        }
        transcription = "Motorista parou para arrumar o pneu na oficina e ficou parado no caminho."

        aligned = align_classification_with_catalog(dict(classification))
        result = enforce_context_not_non_auditable_guardrail(aligned, transcription, "manutencao.wav")

        self.assertEqual(result["sector_id"], "logistica")
        self.assertEqual(result["alert_id"], "LOGISTICA-PARADA")
        self.assertNotIn("contexto_operacional_sem_alerta_identificado", result.get("review_reasons", []))

    def test_maintenance_context_without_alert_goes_to_manual_review(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "INFORMATIVO",
            "alert_label": "Nao Auditavel (Manutencao)",
            "confidence": 0.93,
        }
        transcription = "Motorista informa apenas que o veiculo esta em manutencao na oficina."

        aligned = align_classification_with_catalog(dict(classification))
        result = enforce_context_not_non_auditable_guardrail(aligned, transcription, "manutencao.wav")

        self.assertEqual(result["alert_id"], "desconhecido")
        self.assertIn("contexto_operacional_sem_alerta_identificado", result.get("review_reasons", []))
        self.assertLess(float(result["confidence"]), 0.5)

    def test_cliente_solto_nao_forca_estadia(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "INFORMATIVO",
            "alert_label": "Informativo",
            "confidence": 0.86,
        }
        transcription = "Operador confirmou dados do cliente e encerrou a ligacao como consulta operacional."

        aligned = align_classification_with_catalog(dict(classification))
        result = enforce_context_not_non_auditable_guardrail(aligned, transcription, "consulta_cliente.wav")

        self.assertEqual(result["sector_id"], "logistica")
        self.assertNotEqual(result["alert_id"], "LOGISTICA-ESTADIA")
        self.assertEqual(result["alert_id"], "desconhecido")

    def test_temperature_shutdown_in_client_context(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logística Geral",
            "alert_id": "LOGISTICA-ATRASO-MOT",
            "alert_label": "Atraso - Motorista",
            "confidence": 0.9,
        }
        transcription = "Cliente relata desligamento de temperatura no baú refrigerado."

        result = enforce_temperature_guardrail(classification, transcription, "cliente_temperatura.wav")

        self.assertEqual(result["sector_id"], "logistica")
        self.assertEqual(result["alert_id"], "LOGISTICA-DESLIG-TEMP-CLI")

    def test_valid_temperature_classification_is_preserved(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logística Geral",
            "alert_id": "LOGISTICA-TEMPERATURA-CLI",
            "alert_label": "Controle de Temperatura - Cliente",
            "confidence": 0.95,
        }
        transcription = "Cliente confirma controle de temperatura em 5 graus."

        result = enforce_temperature_guardrail(classification, transcription, "ok.wav")

        self.assertEqual(result["alert_id"], "LOGISTICA-TEMPERATURA-CLI")
        self.assertEqual(result["confidence"], 0.95)

    def test_temperature_motorista_filename_overrides_client_alert(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica Geral",
            "alert_id": "LOGISTICA-TEMPERATURA-CLI",
            "alert_label": "Controle de Temperatura - Cliente",
            "confidence": 0.91,
        }
        transcription = "Operador questiona a temperatura do bau e pede foto do visor."

        result = enforce_temperature_guardrail(
            classification,
            transcription,
            "TEMPERATURA-MOTORISTA-agent-11426.wav",
        )

        self.assertEqual(result["alert_id"], "LOGISTICA-TEMPERATURA-MOT")
        self.assertIn("Motorista", result["alert_label"])

    def test_temperature_tie_defaults_to_motorista(self):
        classification = {
            "sector_id": "cadastro",
            "sector_label": "Setor Cadastro",
            "alert_id": "CADASTRO-ANTECEDENTES",
            "alert_label": "Antecedentes - Receptivo",
            "confidence": 0.40,
        }
        transcription = "Controle de temperatura em 5 graus."

        result = enforce_temperature_guardrail(classification, transcription, "temperatura.wav")

        self.assertEqual(result["alert_id"], "LOGISTICA-TEMPERATURA-MOT")

    def test_non_temperature_text_does_not_override(self):
        classification = {
            "sector_id": "cadastro",
            "sector_label": "Setor Cadastro",
            "alert_id": "CADASTRO-ANTECEDENTES",
            "alert_label": "Antecedentes - Receptivo",
            "confidence": 0.77,
        }
        transcription = "Ligação de consulta de antecedentes com validação cadastral."

        result = enforce_temperature_guardrail(classification, transcription, "cadastro.wav")

        self.assertEqual(result["sector_id"], "cadastro")
        self.assertEqual(result["alert_id"], "CADASTRO-ANTECEDENTES")

    def test_priority_alert_overrides_parada_when_critical_signal_is_stronger(self):
        classification = {
            "sector_id": "transferencia",
            "sector_label": "Transferencia",
            "alert_id": "UTI-POSICAO-MOT",
            "alert_label": "Posição Indevida - Motorista",
            "confidence": 0.88,
        }
        transcription = (
            "Motorista informa painel violado e sensor de desengate acionado. "
            "Operador reforca que ha violacao no conjunto e pede video do veiculo."
        )

        result = enforce_alert_hierarchy_guardrail(classification, transcription, "alerta.wav")

        self.assertEqual(result["sector_id"], "transferencia")
        self.assertEqual(result["alert_id"], "TRANSFERENCIA-PRIORITARIO-MOT")
        self.assertIn("Priorit", result["alert_label"])

    def test_police_alert_uses_sector_specific_operational_id(self):
        classification = {
            "sector_id": "fenix",
            "sector_label": "Fenix",
            "alert_id": "FENIX-PARADA-MOT",
            "alert_label": "Parada Indevida - Motorista",
            "confidence": 0.88,
        }
        transcription = "Operador fez contato com a policia e pediu apoio da viatura."

        result = enforce_alert_hierarchy_guardrail(classification, transcription, "alerta.wav")

        self.assertEqual(result["sector_id"], "fenix")
        self.assertEqual(result["alert_id"], "FENIX-PRIORITARIO-POLICIA")

    def test_parada_desvio_guardrail_uses_sector_specific_id(self):
        classification = {
            "sector_id": "distribuicao",
            "sector_label": "Distribuicao",
            "alert_id": "DISTRIBUICAO-POSICAO-MOT",
            "alert_label": "Posicao em Atraso - Motorista",
            "confidence": 0.88,
        }
        transcription = "A ligacao trata de parada indevida. O motorista ficou parado e permaneceu parado no trajeto."

        result = enforce_parada_desvio_guardrail(classification, transcription, "alerta.wav")

        self.assertEqual(result["sector_id"], "distribuicao")
        self.assertEqual(result["alert_id"], "DISTRIBUICAO-PARADA-MOT")

    def test_position_alert_overrides_desvio_when_signal_loss_is_emphasized(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "LOGISTICA-ATRASO-INICIO",
            "alert_label": "Atraso inicio - Motorista",
            "confidence": 0.87,
        }
        transcription = (
            "A tratativa e de perda de sinal. O veiculo ficou sem sinal, sem posicao "
            "e o operador pediu para forcar posicionamento."
        )

        result = enforce_alert_hierarchy_guardrail(classification, transcription, "posicao.wav")

        self.assertEqual(result["alert_id"], "LOGISTICA-POSICAO")
        self.assertIn("Posi", result["alert_label"])

    def test_logistica_catalog_includes_missing_auditor_scripts(self):
        rules = load_scoring_rules()
        alert_ids = {alert["id"] for alert in rules["alerts"] if alert["sector"] == "logistica"}

        self.assertIn("LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI", alert_ids)
        self.assertIn("LOGISTICA-PERDA-POSICAO-CLI", alert_ids)
        self.assertIn("LOGISTICA-PARADA-EXCESSIVA-MOT", alert_ids)
        self.assertIn("LOGISTICA-PARADA-EXCESSIVA-CLI", alert_ids)

    def test_filename_parser_detects_viagem_sem_espelhamento_cliente(self):
        parsed = parse_filename(
            "VIAGEM-SEM-ESPELHAMENTO-CLIENTE-20260519090000_Maria_Logistica_Voz.wav"
        )

        self.assertEqual(parsed.sector_hint, "logistica")
        self.assertEqual(parsed.alert_id_hint, "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI")

    def test_logistica_client_position_loss_uses_cliente_script(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "LOGISTICA-ATRASO",
            "alert_label": "Atraso - Cliente",
            "confidence": 0.88,
        }
        transcription = (
            "Contato com cliente sobre perda de posicao. O operador informou que o veiculo "
            "perdeu o sinal e repassou as acoes adotadas ate o momento."
        )

        with patch.dict(os.environ, {"CRITERIA_CATALOG_SOURCE": "yaml"}):
            load_audit_criteria_catalog.cache_clear()
            result = enforce_alert_hierarchy_guardrail(classification, transcription, "perda-posicao-cliente.wav")
        load_audit_criteria_catalog.cache_clear()

        self.assertEqual(result["alert_id"], "LOGISTICA-PERDA-POSICAO-CLI")
        self.assertIn("Perda", result["alert_label"])

    def test_logistica_parada_excessiva_uses_actor_specific_script(self):
        classification = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "LOGISTICA-PARADA",
            "alert_label": "Parada Indevida - Motorista",
            "confidence": 0.88,
        }
        transcription = (
            "A ligacao trata de parada excessiva. O motorista ficou parado por muito tempo "
            "e o operador questionou se ha previsao de reiniciar a viagem."
        )

        with patch.dict(os.environ, {"CRITERIA_CATALOG_SOURCE": "yaml"}):
            load_audit_criteria_catalog.cache_clear()
            result = enforce_parada_desvio_guardrail(classification, transcription, "parada-excessiva-motorista.wav")
        load_audit_criteria_catalog.cache_clear()

        self.assertEqual(result["alert_id"], "LOGISTICA-PARADA-EXCESSIVA-MOT")
        self.assertIn("Excessiva", result["alert_label"])

    def test_prompt_lists_canonical_police_alert_with_operational_pop_ref(self):
        prompt = build_sectors_and_alerts_prompt()

        self.assertIn("UTI-PRIORITARIO-MOT [POP 4.1.1]", prompt)
        self.assertNotIn("BAS-POLICIAL [POP 4.10]", prompt)


if __name__ == "__main__":
    unittest.main()
