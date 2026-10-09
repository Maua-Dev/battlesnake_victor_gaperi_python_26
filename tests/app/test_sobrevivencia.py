"""Testes da sobrevivência por DFS (src/app/survival.py).

Rode com: pytest tests/app/test_sobrevivencia.py

Nos desenhos ASCII, y cresce para cima (a primeira linha é a de cima):
E = minha cabeça, e = meu corpo, R = cabeça da rival, r = corpo da rival,
* = comida e . = casa livre.
"""
import random
from dataclasses import replace

from src.app import clock, config
from src.app.board_state import MOVE_ORDER, OFF_BOARD, from_game
from src.app.occupancy import base_free_after
from src.app.survival import survival
from tests.app.test_regioes import tabuleiros_aleatorios
from tests.helpers import snake, make_game

EU = "eu"


def sobreviver(state, direction, deadline=None):
    board = from_game(state)
    return survival(board, base_free_after(board, EU), board.snake(EU), direction, deadline)


def test_persegue_a_propria_cauda_num_espaco_menor_que_o_corpo():
    #   x: 0 1 2
    # y=1  e e e      right leva a (1,0), cuja área estática seria 1; a
    # y=0  E . e      cobra sai dando a volta atrás da própria cauda
    state = make_game(snake(EU, [(0, 0), (0, 1), (1, 1), (2, 1), (2, 0)]), width=3, height=2)
    depth, survives, _ = sobreviver(state, "right")
    assert (depth, survives) == (5, True)


BOLSAO_EU = [(2, 10), (3, 10), (4, 10), (5, 10)]
BOLSAO_RIVAL = [(5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (1, 9), (0, 9), (0, 8), (0, 7), (0, 6)]


def test_bolsao_sem_saida():
    #   x: 0 1 2 3 4 5
    # y=10 . . E e e e     left leva a (1,10) e (0,10); (1,9) só libera em
    # y=9  r r . . . .     5 movimentos e (0,9) em 4
    # y=8  r r r r r R
    # y=7  r . . . . .
    # y=6  r . . . . .
    state = make_game(snake(EU, BOLSAO_EU), others=[snake("rival", BOLSAO_RIVAL)])
    depth, survives, _ = sobreviver(state, "left")
    assert (depth, survives) == (2, False)


def test_limite_de_nos(monkeypatch):
    monkeypatch.setattr(config, "SURVIVAL_MAX_NODES", 3)
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3), (5, 2), (5, 1)]))
    for direction in ("up", "left", "right"):
        depth, survives, nodes = sobreviver(state, direction)
        assert nodes <= 3
        assert depth <= 3
        assert survives is False


def test_fome_dentro_da_busca():
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3)], health=2))
    depth, survives, _ = sobreviver(state, "up")
    assert (depth, survives) == (1, False)


def test_comida_no_caminho_salva_da_fome():
    # Vida 2: sem a comida em (5,6) a cobra morreria no segundo passo.
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3)], health=2), food=[(5, 6)])
    depth, survives, _ = sobreviver(state, "up")
    assert (depth, survives) == (3, True)


def test_hazard_dentro_da_busca():
    # Vida 20 e dano 14, com hazards em todas as linhas de y=6 para cima: o
    # primeiro passo, (5,6), deixa a vida em 5. Dali, as outras casas são
    # hazards que a zerariam, e (5,5) é o próprio corpo.
    hazards = [(x, y) for x in range(11) for y in range(6, 11)]
    state = make_game(
        snake(EU, [(5, 5), (5, 4), (5, 3)], health=20),
        hazards=hazards, hazard_damage=14,
    )
    depth, survives, _ = sobreviver(state, "up")
    assert (depth, survives) == (1, False)


def test_morre_contra_parede_na_primeira_casa():
    state = make_game(snake(EU, [(5, 10), (5, 9), (5, 8)]))
    assert sobreviver(state, "up") == (0, False, 0)


def test_dfs_cortada_pelo_prazo(monkeypatch, relogio_que_estoura_em):
    # Conferindo o prazo a cada 2 nós, com o prazo vencido desde a primeira
    # leitura, a DFS para no segundo nó e devolve a profundidade alcançada.
    monkeypatch.setattr(config, "SURVIVAL_DEADLINE_EVERY", 2)
    relogio_que_estoura_em(0)
    prazo = clock.Deadline(0.0, 120)
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3), (5, 2), (5, 1)]))
    depth, survives, nodes = sobreviver(state, "up", prazo)
    assert (depth, survives, nodes) == (2, False, 2)


def test_sem_prazo_vencido_a_dfs_vai_ate_o_alvo(relogio_parado):
    prazo = clock.Deadline(0.0, 120)
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3), (5, 2), (5, 1)]))
    depth, survives, nodes = sobreviver(state, "up", prazo)
    assert (depth, survives, nodes) == (5, True, 5)


# --- Equivalência com uma DFS recursiva, que copia o estado a cada passo ---

def sobrevivencia_referencia(board, free_after, me, direction):
    """A mesma DFS escrita do jeito mais direto: recursiva e sem desfazer."""
    steps = board.steps
    target = min(me.length, config.SURVIVAL_MAX_DEPTH)
    best = [0]
    nodes = [0]

    def andar(body, health, food, cell, t):
        moved = body[:-1]
        if cell == OFF_BOARD or cell in moved or free_after[cell] > t:
            return False
        if cell in food:
            body, health, food = (cell,) + moved + (moved[-1],), 100, food - {cell}
        else:
            health -= 1 + board.hazard_damage * board.hazards.get(cell, 0)
            if health <= 0:
                return False
            body = (cell,) + moved
        nodes[0] += 1
        best[0] = max(best[0], t)
        if t >= target or nodes[0] >= config.SURVIVAL_MAX_NODES:
            return True
        return any(andar(body, health, food, steps[cell][d], t + 1) for d in range(4))

    first = steps[me.head][MOVE_ORDER.index(direction)]
    andar(me.body, me.health, board.food, first, 1)
    return best[0], best[0] >= target, nodes[0]


def test_igual_a_referencia_em_tabuleiros_aleatorios(monkeypatch):
    # Corpos aleatórios, com comida, hazards e vida baixa sorteados, para
    # exercitar o crescimento, a fome e o dano dentro da DFS.
    monkeypatch.setattr(config, "SURVIVAL_MAX_NODES", 60)
    rng = random.Random(7)
    casos = 0
    for state in tabuleiros_aleatorios(300, semente=7):
        board = from_game(state)
        livres = [i for i in range(board.size) if i not in {c for s in board.snakes for c in s.body}]
        board = replace(
            board,
            food=frozenset(rng.sample(livres, min(len(livres), rng.randint(0, 6)))),
            hazards={i: rng.randint(1, 2) for i in rng.sample(livres, min(len(livres), 8))},
            hazard_damage=rng.choice((0, 3, 14)),
        )
        me = replace(board.snake(EU), health=rng.randint(1, 12))
        board = replace(board, snakes=(me,) + board.snakes[1:])
        fa = base_free_after(board, EU)
        if me.length < 2:
            continue
        for direction in ("up", "down", "left", "right"):
            esperado = sobrevivencia_referencia(board, fa, me, direction)
            assert survival(board, fa, me, direction) == esperado
            casos += 1
    assert casos >= 400
