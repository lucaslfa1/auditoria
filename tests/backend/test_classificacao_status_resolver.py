"""Fase 1 — decisão de status da classificação automática (gap do pending).

A automação não rebaixa mais para 'pending' por baixa confiança (flag default ON):
vai para auto_resolved (READY) e a esteira (_audit_single_item) decide. Função pura,
sem banco.
"""
import importlib

hs = importlib.import_module("core.huawei_sync")


def test_skip_pending_baixa_confianca_vira_ready(monkeypatch):
    # flag ON (default): needs_review NAO rebaixa para pending
    monkeypatch.delenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", raising=False)
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="pending") == "auto_resolved"
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="auto_resolved") == "auto_resolved"


def test_flag_off_preserva_pending(monkeypatch):
    monkeypatch.setenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", "false")
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="auto_resolved") == "pending"


def test_status_humano_nao_e_sobrescrito(monkeypatch):
    monkeypatch.delenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", raising=False)
    # reviewed/audited/etc. nunca é mexido
    assert hs._resolve_auto_classificacao_status(needs_review=True, status_atual="reviewed") == "reviewed"
    assert hs._resolve_auto_classificacao_status(needs_review=False, status_atual="audited") == "audited"


def test_sem_review_vai_para_ready(monkeypatch):
    monkeypatch.delenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE", raising=False)
    assert hs._resolve_auto_classificacao_status(needs_review=False, status_atual="pending") == "auto_resolved"
