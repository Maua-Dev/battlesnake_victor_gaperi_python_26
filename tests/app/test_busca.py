"""Testes da busca no duelo (src/app/search.py) e do prazo dentro dela.

Rode com: pytest tests/app/test_busca.py

Os testes fixam a profundidade e usam relógios falsos (tests/conftest.py):
o resultado não depende da velocidade da máquina.

Nos desenhos ASCII, y cresce para cima (a primeira linha é a de cima):
E = minha cabeça, e = meu corpo, R = cabeça da rival, r = corpo da rival,
* = comida e . = casa livre.
"""
import random

import pytest

from src.app import config, search
from src.app.board_state import from_game
from src.app.clock import Deadline
from src.app.logic import get_move
from src.app.search import best_move, evaluate, minimax_value
from src.app.simulator import safe_moves, step
from tests.app.test_regioes import corpo_aleatorio
from tests.helpers import snake, make_game

EU, RIVAL = "eu", "rival"
WIN, DRAW = config.WIN, config.DRAW


def duelo(eu, rival, food=(), width=11, height=11, health=100):
    return make_game(
        snake(EU, eu, health=health), others=[snake(RIVAL, rival)],
        food=food, width=width, height=height,
    )


def valor(state, move, depth):
    """Valor de um movimento da raiz numa profundidade fixa."""
    return minimax_value(from_game(state), EU, RIVAL, depth, root_moves=[move])


def prazo_parado():
    return Deadline(0.0, 120)


# --- Valores terminais ---

def test_cabeca_a_cabeca_contra_menor(relogio_parado):
    #   x: 4 5 6 7 8 9
    # y=5  . E . R r r     (6,5): se a rival menor também entrar, ela morre
    # y=4  . e . . . .
    state = duelo([(5, 5), (5, 4), (5, 3), (5, 2)], [(7, 5), (8, 5), (9, 5)])
    v = valor(state, "right", 1)
    assert v > DRAW
    assert v > -WIN + 1


def test_cabeca_a_cabeca_contra_igual(monkeypatch, relogio_parado):
    # Entre iguais o confronto mata as duas: right vale DRAW.
    state = duelo([(5, 5), (5, 4), (5, 3)], [(7, 5), (8, 5), (9, 5)])
    assert valor(state, "right", 1) == DRAW
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 1)
    escolhido = best_move(from_game(state), EU, RIVAL, ["right", "up", "left"], prazo_parado())
    assert escolhido != "right"


def test_vitoria_mais_cedo_vale_mais():
    #   x: 0 1 2 3 4
    # y=4  . . r r R     a rival só pode descer para (4,3). right entra lá
    # y=3  . . . E .     e vence o cabeça a cabeça no turno 1; com left, a
    # y=2  . . e e .     rival desce pela coluna x=4 e bate no meu corpo no
    # y=1  . . e e e     turno 3
    # y=0  . . e e e
    state = duelo(
        [(3, 3), (3, 2), (2, 2), (2, 1), (3, 1), (4, 1), (4, 0), (3, 0), (2, 0)],
        [(4, 4), (3, 4), (2, 4)],
        width=5, height=5,
    )
    assert valor(state, "right", 3) == WIN - 1
    assert valor(state, "left", 3) == WIN - 3


def test_adversaria_sem_saida():
    #   x: 0 1 2 3
    # y=2  r . . .     a rival não tem saída: up é o pescoço, right é o meu
    # y=1  r e E .     corpo e o resto é parede. A busca simula para ela a
    # y=0  R e e e     primeira direção da ordem canônica, que a elimina
    state = duelo([(2, 1), (1, 1), (1, 0), (2, 0), (3, 0)], [(0, 0), (0, 1), (0, 2)])
    board = from_game(state)
    assert safe_moves(board, RIVAL) == ["up"]
    assert not step(board, {EU: "up", RIVAL: "up"}).snake(RIVAL).alive
    assert valor(state, "up", 1) == WIN - 1


# --- Avaliação das folhas ---

def duelos_aleatorios(quantidade: int, semente: int, size: int = 7):
    """Duelos com corpos aleatórios, comida e vida sorteadas."""
    rng = random.Random(semente)
    gerados = 0
    while gerados < quantidade:
        ocupadas: set = set()
        eu = corpo_aleatorio(rng, size, ocupadas)
        ocupadas.update(eu)
        rival = corpo_aleatorio(rng, size, ocupadas)
        ocupadas.update(rival)
        if len(eu) < 2 or len(rival) < 2:
            continue
        livres = [(x, y) for x in range(size) for y in range(size) if (x, y) not in ocupadas]
        food = rng.sample(livres, min(len(livres), rng.randint(0, 3)))
        gerados += 1
        yield duelo(eu, rival, food=food, width=size, height=size, health=rng.randint(1, 100))


def test_folha_fica_entre_draw_e_menos_draw(monkeypatch):
    for state in duelos_aleatorios(100, semente=3):
        assert DRAW < evaluate(from_game(state), EU, RIVAL) < -DRAW
    # Mesmo com pesos absurdos a folha não alcança um fim de jogo.
    monkeypatch.setattr(config, "EVAL_TERRITORY", 1e12)
    monkeypatch.setattr(config, "EVAL_LENGTH", -1e12)
    for state in duelos_aleatorios(30, semente=4):
        assert DRAW < evaluate(from_game(state), EU, RIVAL) < -DRAW


# --- Poda ---

def test_poda_nao_muda_o_valor():
    casos = 0
    for i, state in enumerate(duelos_aleatorios(60, semente=2026)):
        board = from_game(state)
        depth = 3 if i % 4 == 0 else 2
        com_poda = minimax_value(board, EU, RIVAL, depth, prune=True)
        sem_poda = minimax_value(board, EU, RIVAL, depth, prune=False)
        assert com_poda == sem_poda
        casos += 1
    assert casos == 60


# --- Valor com prazo (para scripts/replay.py) ---

def test_minimax_com_prazo_folgado_da_o_mesmo_valor(relogio_parado):
    for state in duelos_aleatorios(10, semente=7):
        board = from_game(state)
        sem_prazo = minimax_value(board, EU, RIVAL, 2)
        assert minimax_value(board, EU, RIVAL, 2, deadline=Deadline(0.0, 120)) == sem_prazo


def test_minimax_com_prazo_que_estoura_devolve_none(relogio_que_estoura_em):
    board = from_game(duelo(**MEIO_DE_JOGO))
    relogio_que_estoura_em(5)
    assert minimax_value(board, EU, RIVAL, 3, deadline=Deadline(0.0, 120)) is None


# --- Cenas ---

COLISAO = dict(
    eu=[(5, 5), (4, 5), (4, 6), (3, 6), (3, 5), (2, 5)],
    rival=[(6, 4), (5, 4), (4, 4), (4, 3), (5, 3), (6, 3), (6, 2), (6, 1)],
    width=7, height=7,
)


def test_cena_colisao(monkeypatch, relogio_parado):
    #   x: 0 1 2 3 4 5 6
    # y=6  . . . e e . .     right é arriscada, mas tem espaço, e vence a
    # y=5  . . e e e E .     heurística pela camada; a rival maior entra em
    # y=4  . . . . r r R     (6,5) e vence o cabeça a cabeça. up é o único
    # y=3  . . . . r r r     movimento que não perde no turno 1
    # y=2  . . . . . . r
    # y=1  . . . . . . r
    state = duelo(**COLISAO)
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 0)
    assert get_move(state).move == "right"
    assert valor(state, "right", 1) == -WIN + 1
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 2)
    assert get_move(state).move == "up"


ARMADILHA = dict(
    eu=[(6, 5), (5, 5), (5, 4), (5, 3), (5, 2), (5, 1), (4, 1)],
    rival=[(4, 4), (3, 4), (3, 5), (2, 5), (2, 4), (2, 3), (2, 2)],
    width=7, height=7,
)


def test_cena_armadilha(monkeypatch, relogio_parado):
    #   x: 0 1 2 3 4 5 6
    # y=6  . . . . . . .     up entra no canto e segue pela linha de cima,
    # y=5  . . r r . e E     que a rival fecha subindo por (4,5) e (4,6):
    # y=4  . . r r R e .     a cobra fica presa. down desce pela coluna
    # y=3  . . r . . e .     x=6, que o meu corpo vai liberando
    # y=2  . . r . . e .
    # y=1  . . . . e e .
    state = duelo(**ARMADILHA)
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 0)
    assert get_move(state).move == "up"
    assert valor(state, "up", 3) < -WIN / 2
    assert valor(state, "down", 3) > DRAW
    for depth in (3, 4):
        monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", depth)
        assert get_move(state).move == "down"


# --- Veto da escolha heurística ---

ALIMENTACAO = dict(
    eu=[(5, 5), (5, 4), (5, 3)],
    rival=[(8, 5), (9, 5), (10, 5), (10, 4)],
    food=[(2, 5), (7, 7)],
)


@pytest.mark.parametrize("vida", [5, 10, 40])
def test_cena_alimentacao(monkeypatch, relogio_parado, vida):
    #   x: 1 2 3 4 5 6 7 8 9 10
    # y=7  . . . . . . * . . .     com fome, a heurística vai para (2,5), que
    # y=6  . . . . . . . . . .     é da cobra; (7,7) fica mais perto da rival.
    # y=5  . * . . E . . R r r     A folha prefere right, que ganha
    # y=4  . . . . e . . . . r     território, mas left não perde: o veto
    # y=3  . . . . e . . . . .     mantém a escolha heurística
    state = duelo(**ALIMENTACAO, health=vida)
    assert valor(state, "right", 1) > valor(state, "left", 1) > DRAW
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 0)
    assert get_move(state).move == "left"
    for depth in (1, 2, 3):
        monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", depth)
        assert get_move(state).move == "left"


def test_heuristica_que_nao_perde_dispensa_as_outras(monkeypatch, relogio_parado):
    # Só a escolha heurística é buscada na raiz quando ela não perde.
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 2)
    board = from_game(duelo(**ALIMENTACAO, health=10))
    na_raiz = []
    original = search._Search.min_value

    def min_value(self, board, my_move, rival_moves, depth, alpha, beta, ply):
        if ply == 0:
            na_raiz.append(my_move)
        return original(self, board, my_move, rival_moves, depth, alpha, beta, ply)

    monkeypatch.setattr(search._Search, "min_value", min_value)
    assert best_move(board, EU, RIVAL, ["left", "up", "right"], prazo_parado()) == "left"
    assert na_raiz == ["left", "left"]


def test_todas_as_candidatas_perdem(monkeypatch, relogio_parado):
    #   x: 0 1 2 3 4
    # y=4  r r r e .     left cai ao lado da cabeça da rival maior e perde o
    # y=3  r r r e e     cabeça a cabeça no turno 1; right entra num beco e
    # y=2  . r r e e     morre no turno 3. Vale a que perde mais tarde
    # y=1  . r R e .
    # y=0  . . . E .
    state = duelo(
        [(3, 0), (3, 1), (3, 2), (4, 2), (4, 3), (3, 3), (3, 4)],
        [(2, 1), (2, 2), (2, 3), (2, 4), (1, 4), (0, 4), (0, 3), (1, 3), (1, 2), (1, 1)],
        width=5, height=5,
    )
    assert valor(state, "left", 3) == -WIN + 1
    assert valor(state, "right", 3) == -WIN + 3
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 3)
    assert best_move(from_game(state), EU, RIVAL, ["left", "right"], prazo_parado()) == "right"


# Simétrico em x=5: up cai ao lado da cabeça da rival maior.
SIMETRICO = dict(eu=[(5, 3), (5, 2), (5, 1)], rival=[(5, 5), (5, 6), (5, 7), (5, 8)])


def test_empate_entre_substitutas_desempata_pela_ordem_heuristica(monkeypatch, relogio_parado):
    #   x: 3 4 5 6 7
    # y=6  . . r . .     a escolha heurística é up, que perde o cabeça a
    # y=5  . . R . .     cabeça em (5,4) no turno 1. left e right, simétricas,
    # y=4  . . . . .     têm o mesmo valor: vence a que vem antes na ordem
    # y=3  . . E . .     heurística
    # y=2  . . e . .
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 3)
    state = duelo(**SIMETRICO)
    assert valor(state, "up", 1) == -WIN + 1
    for depth in (1, 2, 3):
        assert valor(state, "left", depth) == valor(state, "right", depth) > DRAW
    board = from_game(state)
    assert best_move(board, EU, RIVAL, ["up", "right", "left"], prazo_parado()) == "right"
    assert best_move(board, EU, RIVAL, ["up", "left", "right"], prazo_parado()) == "left"


# --- Prazo dentro da busca ---

def leituras_antes_da_busca(state, monkeypatch, relogio_que_conta) -> int:
    """Quantas leituras do relógio a jogada faz antes de chamar a busca."""
    leituras = []
    original = search.best_move

    def espiao(*args, **kwargs):
        leituras.append(relogio_que_conta.leituras)
        return original(*args, **kwargs)

    monkeypatch.setattr(search, "best_move", espiao)
    get_move(state)
    monkeypatch.setattr(search, "best_move", original)
    [n] = leituras
    return n


def test_prazo_estoura_antes_da_profundidade_1_terminar(
    monkeypatch, relogio_que_conta, relogio_que_estoura_em
):
    # Na cena da colisão, a heurística diz right e a busca diz up.
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 3)
    state = duelo(**COLISAO)
    antes = leituras_antes_da_busca(state, monkeypatch, relogio_que_conta)
    # A primeira leitura da busca passa; a segunda, ainda na profundidade 1,
    # já está depois do prazo.
    relogio_que_estoura_em(antes + 1)
    assert get_move(state).move == "right"


def test_prazo_ja_vencido_ao_fim_da_heuristica(
    monkeypatch, relogio_que_conta, relogio_que_estoura_em
):
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 3)
    state = duelo(**COLISAO)
    antes = leituras_antes_da_busca(state, monkeypatch, relogio_que_conta)
    # A última leitura antes da busca é a conferência do prazo em choose_move.
    relogio_que_estoura_em(antes - 1)
    chamadas = []
    monkeypatch.setattr(search, "best_move", lambda *a, **k: chamadas.append(a))
    assert get_move(state).move == "right"
    assert chamadas == []


MEIO_DE_JOGO = dict(
    eu=[(3, 5), (3, 4), (3, 3), (2, 3), (1, 3), (1, 4), (1, 5), (1, 6)],
    rival=[(7, 6), (7, 5), (7, 4), (8, 4), (9, 4), (9, 5), (9, 6)],
    food=[(5, 9), (9, 1), (0, 0)],
    health=60,
)


def test_prazo_estoura_no_meio_da_profundidade_3(
    monkeypatch, relogio_que_conta, relogio_que_estoura_em
):
    board = from_game(duelo(**MEIO_DE_JOGO))
    ordem = safe_moves(board, EU)

    def buscar(max_depth):
        monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", max_depth)
        inicio = relogio_que_conta.leituras
        escolhido = best_move(board, EU, RIVAL, ordem, prazo_parado())
        return escolhido, relogio_que_conta.leituras - inicio

    ate_2, c2 = buscar(2)
    _, c3 = buscar(3)
    assert c3 > c2  # a profundidade 3 existe e faz mais leituras

    # As profundidades 1 e 2 fazem as mesmas c2 leituras de antes; o prazo
    # passa no meio das leituras da profundidade 3.
    relogio_que_estoura_em(c2 + (c3 - c2) // 2)
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 20)
    assert best_move(board, EU, RIVAL, ordem, prazo_parado()) == ate_2


def test_sem_nenhuma_profundidade_completa_devolve_none(relogio_que_estoura_em):
    board = from_game(duelo(**MEIO_DE_JOGO))
    relogio_que_estoura_em(0)
    assert best_move(board, EU, RIVAL, safe_moves(board, EU), Deadline(0.0, 120)) is None


def test_arvore_resolvida_para_o_aprofundamento(monkeypatch, relogio_que_conta):
    # No tabuleiro da vitória mais cedo, todas as linhas terminam em poucos
    # turnos: alguma profundidade termina sem folha cortada pelo limite, e o
    # aprofundamento para antes de MAX_SEARCH_DEPTH.
    state = duelo(
        [(3, 3), (3, 2), (2, 2), (2, 1), (3, 1), (4, 1), (4, 0), (3, 0), (2, 0)],
        [(4, 4), (3, 4), (2, 4)],
        width=5, height=5,
    )
    board = from_game(state)
    profundidades = []
    original = search._Search.root

    def root(self, board, root_order, previous, depth):
        profundidades.append(depth)
        return original(self, board, root_order, previous, depth)

    monkeypatch.setattr(search._Search, "root", root)
    assert best_move(board, EU, RIVAL, ["right", "left"], prazo_parado()) == "right"
    assert profundidades[-1] < config.MAX_SEARCH_DEPTH


def test_relogio_parado_da_sempre_a_mesma_resposta(monkeypatch, relogio_parado):
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 3)
    state = duelo(**MEIO_DE_JOGO)
    respostas = {get_move(state).move for _ in range(5)}
    assert len(respostas) == 1


# --- Só no duelo ---

@pytest.fixture
def chamadas_da_busca(monkeypatch, relogio_parado):
    """Espia search.best_move e devolve a lista de chamadas."""
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 3)
    chamadas = []
    original = search.best_move

    def espiao(*args, **kwargs):
        chamadas.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(search, "best_move", espiao)
    return chamadas


def test_com_duas_adversarias_a_busca_nao_roda(chamadas_da_busca):
    state = make_game(
        snake(EU, [(5, 5), (5, 4), (5, 3)]),
        others=[snake("r1", [(1, 1), (1, 0)]), snake("r2", [(9, 9), (9, 10)])],
    )
    get_move(state)
    assert chamadas_da_busca == []


def test_sem_adversaria_a_busca_nao_roda(chamadas_da_busca):
    get_move(make_game(snake(EU, [(5, 5), (5, 4), (5, 3)])))
    assert chamadas_da_busca == []


def test_com_uma_unica_candidata_a_busca_nao_roda(chamadas_da_busca):
    # left é a adversária, up é parede e down é o pescoço.
    state = duelo([(5, 10), (5, 9), (5, 8)], [(4, 10), (3, 10), (2, 10)])
    assert get_move(state).move == "right"
    assert chamadas_da_busca == []


def test_no_duelo_a_busca_roda(chamadas_da_busca):
    get_move(duelo(**MEIO_DE_JOGO))
    assert len(chamadas_da_busca) == 1


def test_busca_desligada_nao_roda(monkeypatch, chamadas_da_busca):
    monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 0)
    get_move(duelo(**MEIO_DE_JOGO))
    assert chamadas_da_busca == []
