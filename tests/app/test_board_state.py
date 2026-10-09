"""Testes da representação leve do tabuleiro (src/app/board_state.py).

Rode com: pytest tests/app/test_board_state.py
"""
import pytest

from src.app.board_state import (
    from_game, hazard_damage, idx, neighbor_table, step_table, xy, OFF_BOARD,
)
from tests.helpers import snake, make_game

EU = "eu"


def vizinhos(x: int, y: int, w: int = 11, h: int = 11) -> list[tuple[int, int]]:
    return [xy(n, w) for n in neighbor_table(w, h)[idx(x, y, w)]]


# --- Índices ---

def test_ida_e_volta():
    assert idx(3, 7, 11) == 80
    assert xy(80, 11) == (3, 7)


def test_tabuleiro_nao_quadrado():
    assert idx(6, 4, 7) == 34
    assert xy(34, 7) == (6, 4)
    # Todas as casas de um 7x5 voltam para si mesmas.
    for i in range(7 * 5):
        assert idx(*xy(i, 7), 7) == i


# --- Vizinhos ---

def test_vizinhos_da_casa_do_meio():
    assert vizinhos(5, 5) == [(5, 6), (5, 4), (4, 5), (6, 5)]


def test_vizinhos_do_canto_inferior_esquerdo():
    assert vizinhos(0, 0) == [(0, 1), (1, 0)]


def test_vizinhos_da_borda_superior():
    assert vizinhos(4, 10) == [(4, 9), (3, 10), (5, 10)]


def test_vizinhos_do_canto_superior_direito():
    assert vizinhos(10, 10) == [(10, 9), (9, 10)]


def test_vizinhos_num_tabuleiro_nao_quadrado():
    assert vizinhos(6, 4, w=7, h=5) == [(6, 3), (5, 4)]


def test_step_table_marca_fora_do_tabuleiro():
    assert step_table(11, 11)[idx(0, 0, 11)] == (idx(0, 1, 11), OFF_BOARD, OFF_BOARD, idx(1, 0, 11))


def test_tabela_reaproveitada_entre_jogadas():
    primeira = from_game(make_game(snake(EU, [(5, 5), (5, 4)])))
    segunda = from_game(make_game(snake(EU, [(1, 1), (1, 2)])))
    assert primeira.neighbors is segunda.neighbors
    assert neighbor_table(11, 11) is neighbor_table(11, 11)


# --- Estado leve ---

def test_cauda_empilhada_preservada():
    board = from_game(make_game(snake(EU, [(4, 3), (4, 2), (4, 2)])))
    eu = board.snake(EU)
    assert eu.body == (37, 26, 26)
    assert eu.length == 3


def test_estado_leve_tem_cobras_comida_e_dimensoes():
    eu = snake(EU, [(5, 5), (5, 4)], health=42)
    outra = snake("outra", [(1, 1)])
    board = from_game(make_game(eu, others=[outra], food=[(2, 3)], width=7, height=9))
    assert (board.width, board.height) == (7, 9)
    assert [s.id for s in board.snakes] == [EU, "outra"]
    assert board.snake(EU).health == 42
    assert all(s.alive for s in board.snakes)
    assert board.food == frozenset({idx(2, 3, 7)})


def test_hazard_repetido():
    state = make_game(snake(EU, [(0, 0)]), hazards=[(5, 6), (5, 6), (1, 1)])
    board = from_game(state)
    assert board.hazards == {idx(5, 6, 11): 2, idx(1, 1, 11): 1}


# --- Dano de hazard ---

def test_dano_informado():
    state = make_game(snake(EU, [(0, 0)]), hazard_damage=14)
    assert from_game(state).hazard_damage == 14


def test_sem_settings():
    assert hazard_damage({"name": "standard", "version": "v1.2.3"}) == 0
    assert from_game(make_game(snake(EU, [(0, 0)]))).hazard_damage == 0


@pytest.mark.parametrize("valor", ["muito", None, 1.5, True, [14]])
def test_valor_invalido(valor):
    assert hazard_damage({"settings": {"hazardDamagePerTurn": valor}}) == 0


def test_settings_que_nao_e_dict():
    assert hazard_damage({"settings": "x"}) == 0
    assert hazard_damage({}) == 0
