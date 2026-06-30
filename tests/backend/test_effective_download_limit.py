"""Opção 1: downloads por ciclo = meta de auditorias (1:1).

`_effective_download_attempt_limit` não lê mais `huawei_d1_limite_ligacoes`;
o limite de downloads passa a ser a própria meta (`automacao_audit_target_count`
/ `automacao_audit_batch_size`), com override de emergência por env e um default
quando nada está configurado. Testes puros: `database.get_config_value` é mockado,
não há acesso a banco.
"""

import pytest

from core import huawei_sync


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in (
        "HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS",
        "AUTOMATION_AUDIT_TARGET_COUNT",
        "AUTOMATION_AUDIT_BATCH_SIZE",
        "HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO",
        "AUTOMACAO_COBERTURA_INICIAL_DIAS",
        "AUTOMACAO_COBERTURA_INICIAL_MIN_POR_OPERADOR",
    ):
        monkeypatch.delenv(key, raising=False)


def _patch_config(monkeypatch, values):
    monkeypatch.setattr(
        huawei_sync.database,
        "get_config_value",
        lambda key, default="": values.get(key, default),
    )


def test_downloads_iguais_a_meta(monkeypatch):
    _patch_config(monkeypatch, {"automacao_audit_target_count": "7"})
    assert huawei_sync._effective_download_attempt_limit() == 7


def test_ignora_antigo_limite_ligacoes(monkeypatch):
    # Mesmo com o antigo huawei_d1_limite_ligacoes alto, downloads = meta.
    _patch_config(
        monkeypatch,
        {"automacao_audit_target_count": "5", "huawei_d1_limite_ligacoes": "100"},
    )
    assert huawei_sync._effective_download_attempt_limit() == 5


def test_override_por_env_vence(monkeypatch):
    monkeypatch.setenv("HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS", "12")
    _patch_config(monkeypatch, {"automacao_audit_target_count": "5"})
    assert huawei_sync._effective_download_attempt_limit() == 12


def test_default_quando_nada_configurado(monkeypatch):
    _patch_config(monkeypatch, {})
    assert (
        huawei_sync._effective_download_attempt_limit()
        == huawei_sync.DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT
    )


def test_fallback_batch_size(monkeypatch):
    # Sem target_count, usa batch_size como meta.
    _patch_config(monkeypatch, {"automacao_audit_batch_size": "9"})
    assert huawei_sync._effective_download_attempt_limit() == 9


def test_teto_fixo_500_acima_da_meta(monkeypatch):
    # Teto fixo de downloads por ciclo = 500: meta maior e limitada a 500.
    _patch_config(monkeypatch, {"automacao_audit_target_count": "1000"})
    assert huawei_sync._effective_download_attempt_limit() == 500


def test_meta_abaixo_do_teto_segue_meta(monkeypatch):
    # Abaixo do teto, o numero de downloads segue a meta de auditorias (400 -> 400).
    _patch_config(monkeypatch, {"automacao_audit_target_count": "400"})
    assert huawei_sync._effective_download_attempt_limit() == 400


def test_override_por_env_tambem_respeita_teto(monkeypatch):
    # O override de emergencia tambem nao ultrapassa o teto fixo de 500.
    monkeypatch.setenv("HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS", "900")
    _patch_config(monkeypatch, {})
    assert huawei_sync._effective_download_attempt_limit() == 500


# --- Teto de download POR OPERADOR por ciclo (desacoplado da cota do supervisor) ---
# A cota de compliance (huawei_cota_max_por_operador_mes=2) governa SO o envio ao
# supervisor; o download usa esta chave separada para nao ficar preso em 2/operador.


def test_download_por_operador_default_dez(monkeypatch):
    # Sem config, o teto de download por operador e o default 10.
    _patch_config(monkeypatch, {})
    assert (
        huawei_sync._download_max_por_operador_ciclo()
        == huawei_sync.DEFAULT_HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO
        == 10
    )


def test_download_por_operador_configuravel(monkeypatch):
    _patch_config(monkeypatch, {"huawei_download_max_por_operador_ciclo": "5"})
    assert huawei_sync._download_max_por_operador_ciclo() == 5


def test_download_por_operador_zero_e_ilimitado(monkeypatch):
    # 0 = sem teto por operador (segue so a meta + rodizio por setor).
    _patch_config(monkeypatch, {"huawei_download_max_por_operador_ciclo": "0"})
    assert huawei_sync._download_max_por_operador_ciclo() == 0


def test_download_por_operador_override_por_env(monkeypatch):
    monkeypatch.setenv("HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO", "25")
    _patch_config(monkeypatch, {"huawei_download_max_por_operador_ciclo": "5"})
    assert huawei_sync._download_max_por_operador_ciclo() == 25


def test_download_por_operador_nao_le_chave_de_compliance(monkeypatch):
    # Setar so a cota do supervisor NAO afeta o teto de download (default 10).
    _patch_config(monkeypatch, {"huawei_cota_max_por_operador_mes": "2"})
    assert huawei_sync._download_max_por_operador_ciclo() == 10


# --- Cobertura inicial obrigatoria por operador ---


def test_cobertura_inicial_default(monkeypatch):
    _patch_config(monkeypatch, {})
    assert huawei_sync._initial_quota_coverage_days() == 3
    assert huawei_sync._initial_quota_coverage_min_per_operator() == 2


def test_cobertura_inicial_configuravel(monkeypatch):
    _patch_config(
        monkeypatch,
        {
            "automacao_cobertura_inicial_dias": "5",
            "automacao_cobertura_inicial_min_por_operador": "4",
        },
    )
    assert huawei_sync._initial_quota_coverage_days() == 5
    assert huawei_sync._initial_quota_coverage_min_per_operator() == 4


def test_cobertura_inicial_minimo_fallback_cota_compliance(monkeypatch):
    _patch_config(monkeypatch, {"huawei_cota_max_por_operador_mes": "3"})
    assert huawei_sync._initial_quota_coverage_min_per_operator() == 3
