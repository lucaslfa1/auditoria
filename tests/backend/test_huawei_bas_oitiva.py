"""BAS audita só ligação policial; oitiva (caminhoneiro, geralmente celular) é descartada.

Regra de negócio (Lucas, 2026-06-17): numa ligação da BAS, se o número da outra
ponta for celular -> é oitiva -> descarta (`oitiva_bas`). Números institucionais/
policiais (ex: 011190) e fixos são mantidos. Whitelist de números policiais
permite manter eventuais policiais por celular.

Testes puros (sem banco): exercitam helpers de número e o gatekeeper diretamente.
"""

from core.huawei_direction import is_brazilian_mobile, resolve_counterpart_number
from core.huawei_sync_gatekeeper import BasOitivaRule, SyncDownloadGatekeeper
from core.huawei.telemetry import _increment_skip_counter
from repositories import configuration


class TestIsBrazilianMobile:
    def test_celular_com_ddd_e_nono_digito(self):
        assert is_brazilian_mobile("47999998888") is True

    def test_celular_com_zero_de_tronco(self):
        # Como vem no manifesto da Huawei (ex: 0 + DDD 94 + 9XXXXXXXX)
        assert is_brazilian_mobile("094992645354") is True

    def test_celular_com_ddi_55(self):
        assert is_brazilian_mobile("5547999998888") is True

    def test_celular_sem_ddd(self):
        assert is_brazilian_mobile("999998888") is True

    def test_fixo_nao_e_celular(self):
        assert is_brazilian_mobile("4733334444") is False

    def test_0800_nao_e_celular(self):
        assert is_brazilian_mobile("008007230108") is False

    def test_numero_policial_curto_nao_e_celular(self):
        assert is_brazilian_mobile("011190") is False

    def test_vazio_nao_e_celular(self):
        assert is_brazilian_mobile("") is False
        assert is_brazilian_mobile(None) is False


class TestResolveCounterpartNumber:
    def test_ativa_usa_callee(self):
        payload = {"callerNo": "4721016122", "calleeNo": "94992645354", "isCallIn": "false"}
        assert resolve_counterpart_number(payload) == "94992645354"

    def test_receptiva_usa_caller(self):
        payload = {"callerNo": "94992645354", "calleeNo": "4721016122", "isCallIn": "true"}
        assert resolve_counterpart_number(payload) == "94992645354"

    def test_direcao_desconhecida_pega_ponta_externa(self):
        # Sem isCallIn; workNo bate com callee -> contraparte é o caller.
        payload = {"callerNo": "94992645354", "calleeNo": "2435", "workNo": "2435"}
        assert resolve_counterpart_number(payload) == "94992645354"


class TestBasOitivaRule:
    def _bas_operador(self):
        return {"setor": "BAS", "id_huawei": "15", "huawei_registered": True, "auditavel_db": True}

    def test_bas_ativa_para_celular_e_oitiva(self):
        rule = BasOitivaRule()
        interacao = {"callerNo": "4721016122", "calleeNo": "94992645354", "isCallIn": "false"}
        assert rule.check(interacao, self._bas_operador()) == "oitiva_bas"

    def test_bas_ativa_para_numero_policial_e_mantida(self):
        rule = BasOitivaRule()
        interacao = {"callerNo": "4721016122", "calleeNo": "011190", "isCallIn": "false"}
        assert rule.check(interacao, self._bas_operador()) is None

    def test_bas_ativa_para_fixo_e_mantida(self):
        rule = BasOitivaRule()
        interacao = {"callerNo": "4721016122", "calleeNo": "4733334444", "isCallIn": "false"}
        assert rule.check(interacao, self._bas_operador()) is None

    def test_policial_por_celular_na_whitelist_e_mantida(self):
        rule = BasOitivaRule(police_numbers={"47988887777"})
        interacao = {"callerNo": "4721016122", "calleeNo": "47988887777", "isCallIn": "false"}
        assert rule.check(interacao, self._bas_operador()) is None

    def test_outro_setor_para_celular_nao_e_oitiva(self):
        rule = BasOitivaRule()
        operador = {"setor": "UTI", "id_huawei": "20", "huawei_registered": True, "auditavel_db": True}
        interacao = {"callerNo": "4721016122", "calleeNo": "94992645354", "isCallIn": "false"}
        assert rule.check(interacao, operador) is None


class TestGatekeeperIntegration:
    def _bas_operador(self):
        return {"setor": "BAS", "id_huawei": "15", "huawei_registered": True, "auditavel_db": True}

    def test_gatekeeper_descarta_oitiva_bas(self):
        gk = SyncDownloadGatekeeper({}, police_numbers={"011190"})
        interacao = {"callerNo": "4721016122", "calleeNo": "94992645354", "isCallIn": "false"}
        assert gk.check_eligibility(interacao, self._bas_operador()) == "oitiva_bas"

    def test_gatekeeper_mantem_policial_bas(self):
        gk = SyncDownloadGatekeeper({}, police_numbers={"011190"})
        interacao = {"callerNo": "4721016122", "calleeNo": "011190", "isCallIn": "false"}
        assert gk.check_eligibility(interacao, self._bas_operador()) is None


class TestOitivaTelemetria:
    def test_oitiva_bas_incrementa_contador(self):
        stats = {}
        _increment_skip_counter(stats, "oitiva_bas")
        assert stats["ignoradas_oitiva_bas"] == 1


class TestBasPoliceNumbersConfig:
    def test_parse_lista_e_normaliza_digitos(self, monkeypatch):
        monkeypatch.setattr(
            configuration, "get_config_value",
            lambda *a, **k: "011190, (47) 98888-7777 ; 4733334444",
        )
        nums = configuration.get_bas_police_numbers(lambda: None)
        assert nums == {"011190", "47988887777", "4733334444"}

    def test_default_inclui_011190(self, monkeypatch):
        monkeypatch.setattr(configuration, "get_config_value", lambda *a, **k: "")
        assert "011190" in configuration.get_bas_police_numbers(lambda: None)
