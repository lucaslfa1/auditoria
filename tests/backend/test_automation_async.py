"""Fase 2 — auditorias assíncronas com teto de concorrência.

Testes de objeto puro / mocks; não tocam o banco.
"""
import importlib

automation = importlib.import_module("core.automation")


def test_progress_exposes_in_flight_list():
    p = automation.AutomationProgress()
    d = p.to_dict()
    assert "current_filenames" in d
    assert d["current_filenames"] == []
