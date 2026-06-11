from repositories import operators
import unittest
import os
import sys
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.classification import (
    enforce_operator_and_direction_guardrails,
    load_audit_criteria_catalog,
    resolve_operator_identity,
)

class TestClassificationDirectionGuardrail(unittest.TestCase):
    def test_registered_distribution_operator_overrides_rastreamento_signal(self):
        """Operador cadastrado em distribuicao força o sector_id mesmo com sinal de
        rastreamento (transferencia) vindo da IA.

        O sector_label NÃO é mais asserido contra string fixa: desde a v1.3.106
        (setores editáveis) o label de `audit_sectors` é dado mutável de admin
        (em prod, p.ex., distribuicao = 'PSL - TRANSFERÊNCIA'); o contrato é o
        id interno. Aqui validamos que o label cascateia do catálogo oficial."""
        classification = {
            "sector_id": "transferencia",
            "sector_label": "Transferencia",
            "direction": "efetivada",
        }

        from unittest.mock import patch

        with patch("repositories.operators.buscar_colaborador_por_nome") as mock_busca:
            mock_busca.return_value = {"name": "Carlos Distribuicao", "setor": "distribuicao"}

            result = enforce_operator_and_direction_guardrails(classification, "Carlos Distribuicao")

        self.assertEqual(result["sector_id"], "distribuicao")
        catalog = load_audit_criteria_catalog()
        self.assertEqual(result["sector_label"], str(catalog["distribuicao"]["label"]))

    def test_operator_sector_override_preserves_alert_type_and_actor(self):
        classification = {
            "sector_id": "uti",
            "sector_label": "UTI",
            "alert_id": "UTI-POSICAO-MOT",
            "alert_label": "Posição em Atraso - Motorista",
            "direction": "efetivada",
        }

        result = enforce_operator_and_direction_guardrails(
            classification,
            "Carlos Distribuicao",
            db_sector="distribuicao",
        )

        self.assertEqual(result["sector_id"], "distribuicao")
        self.assertEqual(result["alert_id"], "DISTRIBUICAO-POSICAO-MOT")

    def test_receptive_audio_mapped_to_risk_operator_does_not_flag_mismatch(self):
        classification = {
            "sector_id": "transferencia",
            "direction": "receptiva"
        }
        
        import db.database as database
        from unittest.mock import patch
        
        with patch('repositories.operators.buscar_colaborador_por_nome') as mock_busca:
            mock_busca.return_value = {"name": "Joao Transferencia", "setor": "transferencia"}
            
            result = enforce_operator_and_direction_guardrails(classification, "Joao Transferencia")
            
            self.assertFalse(result.get("_direction_mismatch", False))

    def test_outbound_audio_mapped_to_receptive_operator_does_not_flag_mismatch(self):
        classification = {
            "sector_id": "receptivo",
            "direction": "efetivada"
        }
        
        from unittest.mock import patch
        
        with patch('repositories.operators.buscar_colaborador_por_nome') as mock_busca:
            mock_busca.return_value = {"name": "Maria Receptivo", "setor": "receptivo"}
            
            result = enforce_operator_and_direction_guardrails(classification, "Maria Receptivo")
            
            self.assertFalse(result.get("_direction_mismatch", False))

    def test_matching_directions_do_not_flag(self):
        classification1 = {"sector_id": "transferencia", "direction": "efetivada"}
        classification2 = {"sector_id": "celula_atendimento", "direction": "receptiva"}
        
        from unittest.mock import patch
        with patch('repositories.operators.buscar_colaborador_por_nome') as mock_busca:
            mock_busca.return_value = {"name": "Joao Transferencia", "setor": "transferencia"}
            res1 = enforce_operator_and_direction_guardrails(classification1, "Joao Transferencia")
            self.assertFalse(res1.get("_direction_mismatch", False))

            mock_busca.return_value = {"name": "Maria Atendimento", "setor": "celula_atendimento"}
            res2 = enforce_operator_and_direction_guardrails(classification2, "Maria Atendimento")
            self.assertFalse(res2.get("_direction_mismatch", False))

    def test_weak_single_name_does_not_force_db_operator_match(self):
        from unittest.mock import patch

        with patch("repositories.operators.buscar_colaborador_por_nome") as mock_busca:
            resolved = resolve_operator_identity("Ana", None, None)

        self.assertIsNone(resolved.operator_name)
        mock_busca.assert_not_called()

    def test_filename_full_name_is_trusted_more_than_weak_ai_name(self):
        from unittest.mock import patch

        with patch("repositories.operators.buscar_colaborador_por_nome") as mock_busca:
            mock_busca.return_value = {
                "name": "Ana Maria Silva",
                "setor": "distribuicao",
                "matricula": "MAT-10",
                "idHuawei": "2447",
            }

            resolved = resolve_operator_identity("Ana", "Ana Maria Silva", None)

        self.assertEqual(resolved.operator_name, "Ana Maria Silva")
        self.assertEqual(resolved.db_sector, "distribuicao")
        self.assertEqual(resolved.id_huawei, "2447")
        self.assertEqual(resolved.source, "filename")

    def test_id_huawei_has_priority_over_conflicting_names(self):
        from unittest.mock import patch

        with patch("repositories.operators.buscar_colaborador_por_id_huawei") as mock_busca_id, patch("repositories.operators.buscar_colaborador_por_nome") as mock_busca_nome:
            mock_busca_id.return_value = {
                "name": "Operador Canonico",
                "setor": "uti",
                "matricula": "MAT-20",
                "idHuawei": "9988",
            }

            resolved = resolve_operator_identity("Nome Incorreto", "Outro Nome", "9988")

        self.assertEqual(resolved.operator_name, "Operador Canonico")
        self.assertEqual(resolved.db_sector, "uti")
        self.assertEqual(resolved.id_huawei, "9988")
        self.assertEqual(resolved.source, "id_huawei")
        mock_busca_nome.assert_not_called()

    def test_high_confidence_ai_sector_diferente_do_cadastro_confia_ia_possivel_hora_extra(self):
        """Caso 2 do D' (ROLLBACK, STRICT_RH_SECTOR_ENFORCEMENT=false): IA com confianca
        >= 0.90 classificando em setor diferente do cadastro deve PRESERVAR sector + alerta
        da IA (provavel hora extra). Por default (rigido) isso seria forcado pro setor do RH."""
        classification = {
            "sector_id": "distribuicao",
            "sector_label": "Distribuição",
            "alert_id": "DISTRIBUICAO-PARADA-MOT",
            "alert_label": "Parada de Motorista",
            "confidence": 0.95,
            "direction": "efetivada",
        }

        with patch.dict(os.environ, {"STRICT_RH_SECTOR_ENFORCEMENT": "false"}, clear=False):
            result = enforce_operator_and_direction_guardrails(
                classification,
                "Operador Logistica Hora Extra",
                db_sector="logistica",
            )

        self.assertEqual(result["sector_id"], "distribuicao", "Setor deve ser preservado da IA (provavel hora extra)")
        self.assertEqual(result["alert_id"], "DISTRIBUICAO-PARADA-MOT", "Alerta deve ser preservado da IA")
        self.assertEqual(result.get("_operator_cadastro_sector"), "logistica", "Cadastro deve ser salvo pra metadata")
        review_reasons = result.get("review_reasons") or []
        self.assertIn("setor_classificado_diferente_do_cadastro_possivel_hora_extra", review_reasons)
        # Nao deve ter sido aplicada a regra de override (setor_alterado_pelo_rh)
        self.assertNotIn("setor_alterado_pelo_rh", review_reasons)
        self.assertNotIn("alerta_incompativel_com_setor_operador", review_reasons)

    def test_low_confidence_ai_sector_diferente_forca_cadastro_mas_preserva_alerta_ia(self):
        """Caso 4 do D' (ROLLBACK, STRICT_RH_SECTOR_ENFORCEMENT=false): sem mapping valido nas
        heuristicas, forca setor do cadastro mas KEEP o alerta da IA original (nao zera para
        'desconhecido'). Por default (rigido) o alerta viraria 'desconhecido' -> triagem manual."""
        classification = {
            "sector_id": "fenix",  # IA chutou fenix
            "sector_label": "Fenix",
            "alert_id": "FENIX-ALGUMA-COISA-IMPOSSIVEL-DE-MAPEAR",
            "alert_label": "Alerta inventado",
            "confidence": 0.70,  # baixa
            "direction": "efetivada",
        }

        with patch.dict(os.environ, {"STRICT_RH_SECTOR_ENFORCEMENT": "false"}, clear=False):
            result = enforce_operator_and_direction_guardrails(
                classification,
                "Operador Cadastro",
                db_sector="distribuicao",
            )

        self.assertEqual(result["sector_id"], "distribuicao", "Setor deve ser forcado para o cadastro (IA insegura)")
        # KEEP alerta da IA — nao zerar
        self.assertEqual(result["alert_id"], "FENIX-ALGUMA-COISA-IMPOSSIVEL-DE-MAPEAR", "Alerta da IA deve ser preservado, nao virar desconhecido")
        self.assertEqual(result.get("_ai_original_sector_id"), "fenix", "Setor IA original deve ser salvo pra metadata")
        self.assertEqual(result.get("_ai_original_alert_id"), "FENIX-ALGUMA-COISA-IMPOSSIVEL-DE-MAPEAR", "Alerta IA original deve ser salvo pra metadata")
        review_reasons = result.get("review_reasons") or []
        self.assertIn("alerta_pode_estar_no_setor_diferente", review_reasons)
        # Motivo antigo NAO deve aparecer
        self.assertNotIn("alerta_incompativel_com_setor_operador", review_reasons)


if __name__ == "__main__":
    unittest.main()
