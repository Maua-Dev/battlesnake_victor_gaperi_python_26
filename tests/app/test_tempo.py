"""Testes do controle de tempo: orçamento, instante de chegada e relógio.

Rode com: pytest tests/app/test_tempo.py

Os relógios falsos estão em tests/conftest.py.
"""
import time

from fastapi.testclient import TestClient

from src.app import clock, config, logic
from src.app.logic import get_move
from src.app.main import app
from tests.helpers import snake, make_game

EU = "eu"
client = TestClient(app)


class RelogioQueAnda:
    """Relógio que avança 1 µs a cada leitura e guarda os valores lidos."""

    def __init__(self, inicio: float = 1000.0):
        self.valores: list[float] = []
        self.proximo = inicio

    def __call__(self) -> float:
        valor = self.proximo
        self.valores.append(valor)
        self.proximo += 1e-6
        return valor


def espiar_prazo(monkeypatch) -> list:
    """Troca logic.choose_move por um espião que guarda o prazo recebido."""
    recebidos = []
    original = logic.choose_move

    def espiao(state, safe_moves, **kwargs):
        recebidos.append(kwargs.get("deadline"))
        return original(state, safe_moves, **kwargs)

    monkeypatch.setattr(logic, "choose_move", espiao)
    return recebidos


def estado_simples():
    return make_game(snake(EU, [(5, 5), (5, 4), (5, 3)]))


# --- Orçamento ---

def test_orcamento_com_o_timeout_padrao_do_motor():
    assert clock.budget_ms(500) == 120


def test_orcamento_com_timeout_curto():
    assert clock.budget_ms(200) == 80


def test_orcamento_segue_o_teto_do_config(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_BUDGET_MAX_MS", 90)
    assert clock.budget_ms(500) == 90


# --- Prazo ---

def test_prazo_conta_desde_o_inicio(monkeypatch):
    agora = [10.0]
    monkeypatch.setattr(clock, "now", lambda: agora[0])
    prazo = clock.Deadline(10.0, 120)
    assert prazo.remaining_ms() == 120
    assert not prazo.expired()
    agora[0] = 10.119
    assert not prazo.expired()
    agora[0] = 10.121
    assert prazo.expired()


# --- Instante de chegada ---

def test_instante_marcado_antes_da_validacao(monkeypatch):
    relogio = RelogioQueAnda()
    monkeypatch.setattr(clock, "now", relogio)
    recebidos = espiar_prazo(monkeypatch)

    resp = client.post("/move", json=estado_simples().model_dump())
    assert resp.status_code == 200
    [prazo] = recebidos
    # O prazo começa na primeira leitura da requisição, a do middleware.
    assert prazo.start == relogio.valores[0]
    assert prazo.budget_ms == 120


def test_instante_marcado_mesmo_quando_a_validacao_falha(monkeypatch):
    # Num 422 a rota nem roda; a leitura do relógio prova que o instante é
    # marcado antes da validação do payload.
    relogio = RelogioQueAnda()
    monkeypatch.setattr(clock, "now", relogio)
    corpo = estado_simples().model_dump()
    del corpo["you"]
    resp = client.post("/move", json=corpo)
    assert resp.status_code == 422
    assert len(relogio.valores) == 1


def test_chamada_direta_comeca_o_prazo_na_chamada(monkeypatch):
    relogio = RelogioQueAnda()
    monkeypatch.setattr(clock, "now", relogio)
    recebidos = espiar_prazo(monkeypatch)

    get_move(estado_simples())
    [prazo] = recebidos
    assert prazo.start == relogio.valores[0]


def test_instante_recebido_e_usado(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: 5.0)
    recebidos = espiar_prazo(monkeypatch)
    get_move(estado_simples(), started_at=4.95)
    [prazo] = recebidos
    assert prazo.start == 4.95


def test_relogio_falso_em_todas_as_leituras(monkeypatch, relogio_que_conta):
    # Num duelo a jogada passa pela heurística e pela busca. Com o relógio
    # trocado, nenhuma leitura pode ir direto ao perf_counter.
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 2)

    def proibido():
        raise AssertionError("leitura de tempo fora de clock.now")

    monkeypatch.setattr(time, "perf_counter", proibido)
    eu = snake(EU, [(3, 5), (3, 4), (3, 3)])
    rival = snake("rival", [(7, 5), (7, 4), (7, 3)])
    get_move(make_game(eu, others=[rival], food=[(5, 8)]))
    assert relogio_que_conta.leituras > 1


# --- Jogada dentro do orçamento ---

def test_duelo_de_meio_de_jogo_cabe_no_orcamento_mais_10_ms():
    # Relógio real e orçamento padrão (120 ms): a busca usa o tempo que
    # sobra e para no prazo. O melhor de 3 filtra a flutuação de máquina.
    eu = snake(EU, [(3, 5), (3, 4), (3, 3), (2, 3), (1, 3), (1, 4), (1, 5), (1, 6)], health=60)
    rival = snake("rival", [(7, 6), (7, 5), (7, 4), (8, 4), (9, 4), (9, 5), (9, 6)], health=70)
    state = make_game(eu, others=[rival], food=[(5, 9), (9, 1), (0, 0)], turn=50)
    tempos = []
    for _ in range(3):
        inicio = time.perf_counter()
        get_move(state)
        tempos.append(time.perf_counter() - inicio)
    assert min(tempos) <= 0.130, f"melhor tempo: {min(tempos) * 1000:.1f} ms"
