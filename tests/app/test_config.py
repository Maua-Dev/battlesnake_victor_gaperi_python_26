"""Testes das constantes novas de src/app/config.py e da leitura do ambiente.

Rode com: pytest tests/app/test_config.py
"""
import pytest

from src.app import config


def test_valores_iniciais_da_sobrevivencia_e_dos_pesos_novos():
    assert (config.SURVIVAL_MAX_DEPTH, config.SURVIVAL_MAX_NODES) == (12, 400)
    assert config.SURVIVAL_DEADLINE_EVERY == 32
    assert (config.W_SURVIVAL, config.W_HAZARD, config.W_SQUEEZE) == (20, 30, 0.5)


def test_valores_iniciais_da_busca():
    assert (config.MAX_SEARCH_DEPTH, config.WIN, config.DRAW) == (20, 1_000_000, -500_000)
    assert (config.EVAL_TERRITORY, config.EVAL_AREA, config.EVAL_LENGTH) == (1.0, 0.5, 10)
    assert (config.EVAL_FOOD, config.EVAL_HEALTH, config.EVAL_CENTER) == (1.0, 0.1, 0.5)


def test_valores_iniciais_do_tempo():
    assert config.SEARCH_BUDGET_FRACTION == 0.4
    assert config.SEARCH_BUDGET_MAX_MS == 120


def test_variavel_de_ambiente_valida(monkeypatch):
    monkeypatch.setenv("SEARCH_BUDGET_MAX_MS", "90")
    assert config._positive_int_env("SEARCH_BUDGET_MAX_MS", 120) == 90


def test_variavel_de_ambiente_ausente(monkeypatch):
    monkeypatch.delenv("SEARCH_BUDGET_MAX_MS", raising=False)
    assert config._positive_int_env("SEARCH_BUDGET_MAX_MS", 120) == 120


@pytest.mark.parametrize("valor", ["", "abc", "-5", "0", "1.5"])
def test_variavel_de_ambiente_invalida_vale_o_padrao(monkeypatch, valor):
    monkeypatch.setenv("SEARCH_BUDGET_MAX_MS", valor)
    assert config._positive_int_env("SEARCH_BUDGET_MAX_MS", 120) == 120
