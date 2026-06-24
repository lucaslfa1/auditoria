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
