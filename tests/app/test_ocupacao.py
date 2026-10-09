"""Testes da ocupação temporal (src/app/occupancy.py).

Rode com: pytest tests/app/test_ocupacao.py

free_after[casa] diz em quantos movimentos a casa fica livre. A BFS, o
Voronoi e o A* temporais só alcançam uma casa no tempo t se
free_after <= t.
"""
from dataclasses import replace

from src.app.board_state import from_game, idx, xy
from src.app.occupancy import (
    base_free_after, temporal_a_star, temporal_area, temporal_voronoi, with_growth,
)
from tests.helpers import snake, make_game

EU = "eu"


def estado(*cobras, food=(), width=11, height=11):
    """BoardState com as cobras dadas; a primeira faz o papel de `you`."""
    return from_game(make_game(cobras[0], others=cobras[1:], food=food, width=width, height=height))


def em(board, free_after, x, y):
    return free_after[idx(x, y, board.width)]


def vazio(width, height):
    """Tabuleiro sem cobras no caminho: a única cobra fica fora da conta."""
    return estado(snake(EU, [(0, 0)]), width=width, height=height)


# --- free_after ---

def test_adversaria_reta():
    board = estado(snake(EU, [(9, 9)]), snake("rival", [(3, 5), (2, 5), (1, 5)]))
    fa = base_free_after(board, EU)
    assert [em(board, fa, x, 5) for x in (3, 2, 1)] == [3, 2, 1]
    assert em(board, fa, 4, 5) == 0
    assert sum(1 for v in fa if v) == 4  # as 3 da rival e a minha cabeça


def test_cauda_empilhada_atrasa_um_turno():
    board = estado(snake(EU, [(9, 9)]), snake("rival", [(3, 5), (2, 5), (2, 5)]))
    fa = base_free_after(board, EU)
    assert (em(board, fa, 3, 5), em(board, fa, 2, 5)) == (3, 2)


def test_adversaria_ao_lado_de_comida():
    board = estado(
        snake(EU, [(9, 9)]), snake("rival", [(3, 5), (2, 5), (1, 5)]), food=[(3, 6)]
    )
    fa = base_free_after(board, EU)
    assert [em(board, fa, x, 5) for x in (3, 2, 1)] == [4, 3, 1]


def test_comida_com_cauda_ja_empilhada():
    board = estado(
        snake(EU, [(9, 9)]), snake("rival", [(3, 5), (2, 5), (1, 5), (1, 5)]), food=[(3, 6)]
    )
    fa = base_free_after(board, EU)
    assert [em(board, fa, x, 5) for x in (3, 2, 1)] == [5, 4, 3]


def test_a_propria_cobra_nao_cresce_no_free_after_base():
    board = estado(snake(EU, [(5, 5), (5, 4), (5, 3)]), food=[(5, 6)])
    fa = base_free_after(board, EU)
    assert [em(board, fa, 5, y) for y in (5, 4, 3)] == [3, 2, 1]


def test_candidata_que_come():
    #   y=6 *      up come a comida: o corpo para de encurtar por um turno
    #   y=5 E
    #   y=4 e
    #   y=3 e
    board = estado(snake(EU, [(5, 5), (5, 4), (5, 3)]), food=[(5, 6)])
    base = base_free_after(board, EU)
    fa = with_growth(base, board.snake(EU))
    assert [em(board, fa, 5, y) for y in (5, 4, 3)] == [4, 3, 1]
    # A cópia não altera o free_after base.
    assert em(board, base, 5, 5) == 3


def test_cobra_morta_nao_ocupa():
    board = estado(snake(EU, [(9, 9)]), snake("rival", [(3, 5), (2, 5)]))
    morta = replace(board.snake("rival"), alive=False)
    board = replace(board, snakes=(board.snake(EU), morta))
    assert em(board, base_free_after(board, EU), 3, 5) == 0


# --- BFS temporal ---

def test_casa_que_libera_a_tempo():
    # 3x1: (0,0) -> (1,0) libera em 1 movimento -> (2,0)
    board = vazio(3, 1)
    fa = [0, 1, 0]
    assert temporal_area(board, fa, idx(0, 0, 3), 0) == 3


def test_casa_que_nao_libera_a_tempo():
    board = vazio(3, 1)
    fa = [0, 2, 0]
    assert temporal_area(board, fa, idx(0, 0, 3), 0) == 1


def test_casa_recusada_alcancada_mais_tarde_por_outro_caminho():
    # 3x2. (1,0) só libera em 3: é recusada a partir de (0,0) no tempo 1 e
    # alcançada a partir de (1,1) no tempo 3.
    #   y=1  . . .
    #   y=0  S x .
    board = vazio(3, 2)
    fa = [0] * 6
    fa[idx(1, 0, 3)] = 3
    assert temporal_area(board, fa, idx(0, 0, 3), 0) == 6


def test_area_no_tabuleiro_vazio():
    board = vazio(5, 5)
    assert temporal_area(board, [0] * 25, idx(2, 2, 5), 1) == 25


def test_area_com_muro():
    board = vazio(5, 5)
    muro = {idx(2, y, 5) for y in range(5)}
    assert temporal_area(board, [0] * 25, idx(0, 0, 5), 1, muro) == 10


def test_inicio_bloqueado_ou_fora_do_tabuleiro():
    board = vazio(5, 5)
    assert temporal_area(board, [0] * 25, idx(0, 0, 5), 1, {idx(0, 0, 5)}) == 0
    assert temporal_area(board, [0] * 25, -1, 1) == 0
    assert temporal_area(board, [0] * 25, 25, 1) == 0


# --- Voronoi temporal ---

def contagens(board, seeds):
    counts, _ = temporal_voronoi(board, base_free_after(board), seeds)
    return counts


def test_voronoi_tamanhos_iguais_dividem_o_tabuleiro():
    #   x: 0 1 2 3 4
    # y=2  E . ? . R     ? = coluna x=2 disputada
    board = estado(snake(EU, [(0, 2)]), snake("rival", [(4, 2)]), width=5, height=5)
    seeds = {EU: (idx(0, 2, 5), 0), "rival": (idx(4, 2, 5), 0)}
    counts, owner = temporal_voronoi(board, base_free_after(board), seeds)
    assert counts == {EU: 10, "rival": 10}
    assert all(owner[idx(2, y, 5)] is None for y in range(5))
    assert owner[idx(0, 2, 5)] == EU


def test_voronoi_rival_maior_leva_o_empate():
    board = estado(snake(EU, [(0, 2)]), snake("rival", [(4, 2), (4, 1)]), width=5, height=5)
    seeds = {EU: (idx(0, 2, 5), 0), "rival": (idx(4, 2, 5), 0)}
    assert contagens(board, seeds) == {EU: 10, "rival": 15}


def test_voronoi_semente_com_distancia_inicial_1():
    board = estado(snake(EU, [(0, 2)]), snake("rival", [(4, 2)]), width=5, height=5)
    seeds = {EU: (idx(0, 2, 5), 1), "rival": (idx(4, 2, 5), 0)}
    assert contagens(board, seeds) == {EU: 10, "rival": 15}


def test_voronoi_tres_cobras_de_mesmo_tamanho():
    board = estado(
        snake(EU, [(0, 2)]), snake("r1", [(4, 2)]), snake("r2", [(2, 0)]), width=5, height=5
    )
    seeds = {EU: (idx(0, 2, 5), 0), "r1": (idx(4, 2, 5), 0), "r2": (idx(2, 0, 5), 0)}
    assert contagens(board, seeds) == {EU: 7, "r1": 7, "r2": 4}


def test_voronoi_casa_ocupada_que_libera_a_tempo():
    board = vazio(3, 1)
    seeds = {EU: (idx(0, 0, 3), 0)}
    assert temporal_voronoi(board, [0, 1, 0], seeds)[0] == {EU: 3}
    assert temporal_voronoi(board, [0, 2, 0], seeds)[0] == {EU: 1}


# --- A* temporal ---

def test_a_star_contorna_obstaculo():
    # A coluna x=1 só tem passagem em (1,4): o caminho sobe, cruza e desce.
    board = vazio(5, 5)
    bloqueado = {idx(1, y, 5) for y in range(4)}
    caminho = temporal_a_star(board, [0] * 25, idx(0, 0, 5), 0, idx(2, 0, 5), bloqueado)
    assert len(caminho) == 11
    assert xy(caminho[0], 5) == (0, 0)
    assert xy(caminho[-1], 5) == (2, 0)


def test_a_star_sem_caminho():
    board = vazio(3, 3)
    bloqueado = {idx(1, 0, 3), idx(1, 1, 3), idx(0, 1, 3)}
    assert temporal_a_star(board, [0] * 9, idx(0, 0, 3), 0, idx(2, 2, 3), bloqueado) == []


def test_a_star_por_casa_que_libera_a_tempo():
    # 3x1: (1,0) libera em 1 movimento, a tempo; em 2, tarde demais.
    board = vazio(3, 1)
    assert temporal_a_star(board, [0, 1, 0], 0, 0, 2) == [0, 1, 2]
    assert temporal_a_star(board, [0, 2, 0], 0, 0, 2) == []
    # Partindo no tempo 1, a casa que libera em 2 já está livre.
    assert temporal_a_star(board, [0, 2, 0], 0, 1, 2) == [0, 1, 2]
