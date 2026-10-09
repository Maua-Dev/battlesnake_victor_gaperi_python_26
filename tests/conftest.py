"""Fixtures compartilhadas: a busca desligada e os relógios falsos.

Os relógios trocam src.app.clock.now, que toda leitura de tempo da jogada
chama na hora do uso.
"""
import pytest

from src.app import clock, config

# Bem depois de qualquer prazo, em segundos.
MUITO_DEPOIS = 1e9


@pytest.fixture
def sem_busca(monkeypatch):
    """Desliga a busca do duelo: só a escolha heurística decide."""
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 0)


@pytest.fixture
def relogio_parado(monkeypatch):
    """Relógio sempre em 0.0: o prazo nunca passa."""
    monkeypatch.setattr(clock, "now", lambda: 0.0)


class RelogioQueConta:
    """Relógio que devolve 0.0 e conta as leituras.

    Com `estoura_em`, as leituras a partir da de número `estoura_em` (contando
    de 0) devolvem MUITO_DEPOIS: o prazo passa nessa leitura.
    """

    def __init__(self, estoura_em: int | None = None):
        self.leituras = 0
        self.estoura_em = estoura_em

    def __call__(self) -> float:
        n = self.leituras
        self.leituras += 1
        if self.estoura_em is not None and n >= self.estoura_em:
            return MUITO_DEPOIS
        return 0.0


@pytest.fixture
def relogio_que_conta(monkeypatch):
    """Instala um relógio parado que conta as leituras e o devolve."""
    relogio = RelogioQueConta()
    monkeypatch.setattr(clock, "now", relogio)
    return relogio


@pytest.fixture
def relogio_que_estoura_em(monkeypatch):
    """Fábrica: instala um relógio que devolve 0.0 nas n primeiras leituras
    e MUITO_DEPOIS a partir daí, e o devolve.
    """
    def instalar(n: int) -> RelogioQueConta:
        relogio = RelogioQueConta(estoura_em=n)
        monkeypatch.setattr(clock, "now", relogio)
        return relogio
    return instalar
