"""Regressão do fix v1.3.185: /sync/status deixa de mentir "running" quando a
coleta de segundo plano morreu no Cloud Run (fire-and-forget throttled/reciclado).

Testes sem banco: mockam `_is_sync_running`, `get_active_telefonia_sync_run`,
`reconcile_stale_telefonia_sync_runs` e `_credentials_status`.
"""
import asyncio

import pytest

# Importar o pacote `routers.telefonia` ANTES do submódulo `sync` evita o import
# circular (telefonia.py inclui o router de sync no fim do módulo). É a ordem em
# que o app carrega em produção.
from routers import telefonia as tf
from routers.telefonia_routes import sync as sync_mod
from repositories import telefonia as telefonia_repo


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    # reconcile e credenciais não devem tocar o banco nestes testes
    monkeypatch.setattr(telefonia_repo, "reconcile_stale_telefonia_sync_runs", lambda *a, **k: 0)
    monkeypatch.setattr(tf, "_credentials_status", lambda: {})


def _run(coro):
    return asyncio.run(coro)


def test_status_interrupted_quando_memoria_running_mas_task_morta(monkeypatch):
    """Mesmo-processo: task acabou e lock liberado -> reporta interrupted, não running."""
    monkeypatch.setattr(tf, "_LAST_SYNC", {"status": "running", "started_at": "x", "finished_at": None})
    monkeypatch.setattr(tf, "_is_sync_running", lambda: False)

    result = _run(sync_mod.sync_status(_user={}))

    assert result["status"] == "interrupted"
    assert "interrompida" in result["message"].lower()


def test_status_interrupted_quando_lock_fantasma_sem_run_ativo(monkeypatch):
    """_is_sync_running True só pelo sync_lock, mas sem run ativo no banco -> interrupted."""
    monkeypatch.setattr(tf, "_LAST_SYNC", {"status": "running", "started_at": "x", "finished_at": None})
    monkeypatch.setattr(tf, "_is_sync_running", lambda: True)
    monkeypatch.setattr(telefonia_repo, "get_active_telefonia_sync_run", lambda *a, **k: None)

    result = _run(sync_mod.sync_status(_user={}))

    assert result["status"] == "interrupted"


def test_status_running_quando_run_ativo_fresco(monkeypatch):
    """Coleta de fato viva (run ativo no banco) -> mantém running."""
    monkeypatch.setattr(tf, "_LAST_SYNC", {"status": "running", "started_at": "x", "finished_at": None})
    monkeypatch.setattr(tf, "_is_sync_running", lambda: True)
    monkeypatch.setattr(telefonia_repo, "get_active_telefonia_sync_run", lambda *a, **k: {"id": 1})

    result = _run(sync_mod.sync_status(_user={}))

    assert result["status"] == "running"


def test_status_terminal_nao_e_tocado(monkeypatch):
    """Status terminal (completed) não vira interrupted."""
    monkeypatch.setattr(tf, "_LAST_SYNC", {"status": "completed", "started_at": "x", "finished_at": "y"})
    monkeypatch.setattr(tf, "_is_sync_running", lambda: False)

    result = _run(sync_mod.sync_status(_user={}))

    assert result["status"] == "completed"
