import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from core import automation_coverage_backfill as backfill


def _operator(nome, huawei, matricula):
    return {
        "id": len(nome),
        "nome": nome,
        "id_huawei": huawei,
        "id_telefonia": huawei,
        "matricula": matricula,
        "setor": "uti",
    }


def test_build_operator_coverage_backfill_plan_ordena_pendentes(monkeypatch):
    roster = [
        _operator("Operador Um", "HUA-1", "MAT-1"),
        _operator("Operador Dois", "HUA-2", "MAT-2"),
        _operator("Operador Cheio", "HUA-3", "MAT-3"),
    ]
    monkeypatch.setattr(backfill.operators, "listar_auditaveis_com_id_huawei", lambda get_connection: roster)
    monkeypatch.setattr(
        backfill.audits,
        "get_operator_audit_counts_for_month_bulk",
        lambda get_connection, keys, year, month: {
            ("operador um", "mat-1"): 0,
            ("operador dois", "mat-2"): 1,
            ("operador cheio", "mat-3"): 2,
        },
    )
    monkeypatch.setattr(backfill, "_initial_quota_coverage_min_per_operator", lambda: 2)

    result = backfill.build_operator_coverage_backfill_plan(
        lambda: None,
        agora=datetime(2026, 6, 10, 12, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )

    assert result["operadores_considerados"] == 3
    assert result["operadores_pendentes"] == 2
    assert [item["summary"]["nome"] for item in result["operadores"]] == ["Operador Um", "Operador Dois"]
    assert [item["faltantes"] for item in result["operadores"]] == [2, 1]


def test_run_operator_coverage_backfill_chama_sync_direcionado(monkeypatch):
    roster = [_operator("Operador Um", "HUA-1", "MAT-1")]
    calls = []

    async def fake_sync(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ok",
            "baixadas": 2,
            "enfileiradas": 2,
            "candidatos_download": 2,
            "ignoradas_operador_fora_alvo": 5,
        }

    monkeypatch.setattr(backfill, "_automation_coverage_backfill_enabled", lambda: True)
    monkeypatch.setattr(backfill, "_get_automation_coverage_backfill_max_operators", lambda: 3)
    monkeypatch.setattr(backfill, "_get_automation_coverage_backfill_lookback_days", lambda: 7)
    monkeypatch.setattr(backfill.operators, "listar_auditaveis_com_id_huawei", lambda get_connection: roster)
    monkeypatch.setattr(
        backfill.audits,
        "get_operator_audit_counts_for_month_bulk",
        lambda get_connection, keys, year, month: {("operador um", "mat-1"): 0},
    )
    monkeypatch.setattr(backfill, "_initial_quota_coverage_min_per_operator", lambda: 2)

    result = asyncio.run(
        backfill.run_operator_coverage_backfill(
            lambda: None,
            agora=datetime(2026, 6, 10, 12, tzinfo=ZoneInfo("America/Sao_Paulo")),
            sync_func=fake_sync,
        )
    )

    assert result["status"] == "ok"
    assert result["baixadas"] == 2
    assert result["enfileiradas"] == 2
    assert calls[0]["target_operator_ids"] == {"hua-1"}
    assert calls[0]["target_operator_names"] == {"Operador Um"}
    assert calls[0]["max_download_attempts_override"] == 2


def test_buscar_auditorias_faltantes_operador_retorna_completo_quando_sem_divida(monkeypatch):
    roster = [_operator("Operador Cheio", "HUA-3", "MAT-3")]
    monkeypatch.setattr(backfill, "_get_automation_coverage_backfill_lookback_days", lambda: 7)
    monkeypatch.setattr(backfill.operators, "listar_auditaveis_com_id_huawei", lambda get_connection: roster)
    monkeypatch.setattr(
        backfill.audits,
        "get_operator_audit_counts_for_month_bulk",
        lambda get_connection, keys, year, month: {("operador cheio", "mat-3"): 2},
    )
    monkeypatch.setattr(backfill, "_initial_quota_coverage_min_per_operator", lambda: 2)

    result = asyncio.run(
        backfill.buscar_auditorias_faltantes_operador(
            lambda: None,
            operator_id="HUA-3",
            agora=datetime(2026, 6, 10, 12, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )
    )

    assert result["status"] == "already_complete"
