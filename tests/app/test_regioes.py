"""Testes da rotulagem de regiões (floodfill.region_sizes) e das rivais
encurraladas calculadas com ela.

Rode com: pytest tests/app/test_regioes.py

A referência é a implementação anterior de trapped_rivals, com um flood fill
por saída. A nova precisa dar sempre o mesmo resultado, e bem mais rápido.
"""
import random
import timeit

from src.app import features
from src.app.features import evaluate_moves, snapshot
from src.app.floodfill import flood_fill, region_sizes
from src.app.grid import Pos, in_bounds, neighbors, pos, step, MOVES
from tests.helpers import snake, make_game

EU = "eu"


# --- region_sizes ---

def test_region_sizes_igual_a_flood_fill_com_parede():
    # 7x7 com uma parede na coluna x=2: à esquerda 2x7 = 14 casas, à direita
    # 4x7 = 28.
    #   . . # . . . .
    #   . . # . . . .
    #   ...
    board = make_game(snake(EU, [(6, 6)]), width=7, height=7).board
    parede = {(2, y) for y in range(7)}
    sizes = region_sizes(board, parede)

    casas = [(x, y) for x in range(7) for y in range(7)]
    fora = [(-1, 0), (7, 3), (3, -1), (3, 7)]
    for casa in casas + fora:
        assert sizes(casa) == flood_fill(board, casa, parede), casa

    assert sizes((0, 0)) == 14
    assert sizes((6, 6)) == 28
    assert sizes((2, 3)) == 0
    assert sizes((-1, 0)) == 0


# --- Rivais encurraladas: equivalência com a implementação anterior ---

def trapped_rivals_referencia(state, snap, new_head: Pos) -> tuple[str, ...]:
    """A implementação anterior de features.trapped_rivals, copiada sem mudar."""
    board = state.board
    sim = snap.obstacles | {new_head}
    trapped = []
    for rival in snap.rivals:
        exits = neighbors(board, pos(rival.head), set())
        rival_area = max((flood_fill(board, cell, sim) for cell in exits), default=0)
        if rival_area < rival.length:
            trapped.append(rival.id)
    return tuple(trapped)


def corpo_aleatorio(rng: random.Random, size: int, ocupadas: set[Pos]) -> list[Pos]:
    """Passeio aleatório sem auto-interseção, fora de ocupadas. body[0] é a cabeça.

    O tamanho é sorteado, e o passeio para antes se ficar sem saída. Às vezes
    repete a cauda, como logo depois de comer.
    """
    livres = [(x, y) for x in range(size) for y in range(size) if (x, y) not in ocupadas]
    corpo = [rng.choice(livres)]
    for _ in range(rng.randint(0, 9)):
        x, y = corpo[-1]
        opcoes = [
            (x + dx, y + dy) for dx, dy in MOVES.values()
            if 0 <= x + dx < size and 0 <= y + dy < size
            and (x + dx, y + dy) not in ocupadas and (x + dx, y + dy) not in corpo
        ]
        if not opcoes:
            break
        corpo.append(rng.choice(opcoes))
    if rng.random() < 0.3:
        corpo.append(corpo[-1])
    return corpo


def tabuleiros_aleatorios(quantidade: int, semente: int = 2026):
    """Estados 7x7 e 11x11 com 2 a 6 cobras de corpos aleatórios."""
    rng = random.Random(semente)
    for _ in range(quantidade):
        size = rng.choice((7, 11))
        ocupadas: set[Pos] = set()
        cobras = []
        for i in range(rng.randint(2, 6)):
            corpo = corpo_aleatorio(rng, size, ocupadas)
            ocupadas.update(corpo)
            cobras.append(snake(EU if i == 0 else f"r{i}", corpo))
        yield make_game(cobras[0], others=cobras[1:], width=size, height=size)


def test_trapped_rivals_igual_a_referencia_em_tabuleiros_aleatorios():
    casos = 0
    for state in tabuleiros_aleatorios(600):
        snap = snapshot(state)
        for direction in MOVES:
            new_head = step(snap.head, direction)
            if not in_bounds(state.board, new_head):
                continue
            esperado = trapped_rivals_referencia(state, snap, new_head)
            assert features.trapped_rivals(state, snap, new_head) == esperado
            casos += 1
    assert casos >= 1500


# --- Desempenho ---

# Posições iniciais padrão de 8 cobras num 11x11: cantos e meios das bordas.
INICIAIS = [(1, 1), (1, 9), (9, 1), (9, 9), (1, 5), (5, 1), (5, 9), (9, 5)]


def turno_zero_com_oito_cobras():
    """11x11, turno 0, 8 cobras com os 3 segmentos empilhados."""
    cobras = [
        snake(EU if i == 0 else f"r{i}", [inicial] * 3)
        for i, inicial in enumerate(INICIAIS)
    ]
    return make_game(cobras[0], others=cobras[1:], turn=0)


def melhor_tempo(funcao) -> float:
    """O menor tempo de várias repetições (timeit já desliga o GC)."""
    return min(timeit.repeat(funcao, number=5, repeat=7))


def test_evaluate_moves_ao_menos_5x_mais_rapido_que_a_referencia(monkeypatch):
    state = turno_zero_com_oito_cobras()
    snap = snapshot(state)
    candidatas = list(MOVES)

    def avaliar():
        return evaluate_moves(state, candidatas, snap)

    esperado = avaliar()
    novo = melhor_tempo(avaliar)

    monkeypatch.setattr(features, "trapped_rivals", trapped_rivals_referencia)
    assert avaliar() == esperado
    referencia = melhor_tempo(avaliar)

    assert referencia / novo >= 5, f"só {referencia / novo:.1f}x mais rápido"
