"""Testes do simulador de turno (src/app/simulator.py): um teste por regra
do modo standard.

Rode com: pytest tests/app/test_simulador.py
"""
from src.app.board_state import from_game, idx, xy
from src.app.simulator import safe_moves, step
from tests.helpers import snake, make_game

A, B = "a", "b"


def tabuleiro(*cobras, food=(), hazards=(), hazard_damage=None, width=11, height=11):
    return from_game(make_game(
        cobras[0], others=cobras[1:], food=food, hazards=hazards,
        hazard_damage=hazard_damage, width=width, height=height,
    ))


def corpo(board, snake_id):
    return [xy(c, board.width) for c in board.snake(snake_id).body]


def viva(board, snake_id):
    return board.snake(snake_id).alive


# --- Movimento, vida e alimentação ---

def test_movimento():
    board = tabuleiro(snake(A, [(1, 1), (1, 0), (0, 0)]))
    depois = step(board, {A: "up"})
    assert corpo(depois, A) == [(1, 2), (1, 1), (1, 0)]


def test_perda_de_vida():
    board = tabuleiro(snake(A, [(1, 1), (1, 0), (0, 0)], health=50))
    assert step(board, {A: "up"}).snake(A).health == 49


def test_alimentacao_e_crescimento():
    board = tabuleiro(snake(A, [(1, 1), (1, 0), (0, 0)], health=50), food=[(1, 2)])
    depois = step(board, {A: "up"})
    assert corpo(depois, A) == [(1, 2), (1, 1), (1, 0), (1, 0)]
    assert depois.snake(A).health == 100
    assert idx(1, 2, 11) not in depois.food


# --- Hazards ---

def test_dano_de_hazard():
    board = tabuleiro(
        snake(A, [(1, 1), (1, 0), (0, 0)], health=50), hazards=[(1, 2)], hazard_damage=14
    )
    assert step(board, {A: "up"}).snake(A).health == 35


def test_hazards_empilhados():
    board = tabuleiro(
        snake(A, [(1, 1), (1, 0), (0, 0)], health=50),
        hazards=[(1, 2), (1, 2)], hazard_damage=7,
    )
    assert step(board, {A: "up"}).snake(A).health == 35


def test_comida_no_hazard():
    board = tabuleiro(
        snake(A, [(1, 1), (1, 0), (0, 0)], health=5),
        food=[(1, 2)], hazards=[(1, 2)], hazard_damage=14,
    )
    depois = step(board, {A: "up"})
    assert viva(depois, A)
    assert depois.snake(A).health == 100


def test_hazard_que_zera_a_vida_elimina():
    board = tabuleiro(
        snake(A, [(1, 1), (1, 0), (0, 0)], health=10), hazards=[(1, 2)], hazard_damage=14
    )
    depois = step(board, {A: "up"})
    assert not viva(depois, A)
    assert depois.snake(A).health == 0


# --- Eliminações ---

def test_fora_do_tabuleiro():
    board = tabuleiro(snake(A, [(0, 1), (1, 1), (2, 1)]))
    assert not viva(step(board, {A: "left"}), A)


def test_colisao_com_corpo():
    #   x: 2 3 4
    # y=3  . b .
    # y=2  A b .      A anda para (3,2), um segmento de B que não é a cauda
    # y=1  a B .
    board = tabuleiro(
        snake(A, [(2, 2), (2, 1), (2, 0)]),
        snake(B, [(3, 1), (3, 2), (3, 3), (3, 4)]),
    )
    depois = step(board, {A: "right", B: "right"})
    assert not viva(depois, A)
    assert viva(depois, B)


def test_cauda_que_sai_do_lugar_nao_mata():
    #   A anda para (3,3), a cauda de B, que não come nem está empilhada
    board = tabuleiro(
        snake(A, [(2, 3), (2, 2), (2, 1)]),
        snake(B, [(3, 1), (3, 2), (3, 3)]),
    )
    depois = step(board, {A: "right", B: "right"})
    assert viva(depois, A)
    assert viva(depois, B)


def test_cauda_empilhada_mata():
    board = tabuleiro(
        snake(A, [(2, 3), (2, 2), (2, 1)]),
        snake(B, [(3, 1), (3, 2), (3, 3), (3, 3)]),
    )
    depois = step(board, {A: "right", B: "right"})
    assert not viva(depois, A)


def test_colisao_com_o_proprio_corpo():
    #   A dá a volta e entra no próprio corpo
    board = tabuleiro(snake(A, [(1, 1), (1, 2), (2, 2), (2, 1), (2, 0)]))
    assert not viva(step(board, {A: "right"}), A)


def test_cabeca_a_cabeca_com_a_menor_morrendo():
    board = tabuleiro(
        snake(A, [(4, 5), (3, 5), (2, 5), (1, 5)]),
        snake(B, [(6, 5), (7, 5), (8, 5)]),
    )
    depois = step(board, {A: "right", B: "left"})
    assert viva(depois, A)
    assert not viva(depois, B)


def test_cabeca_a_cabeca_entre_iguais():
    board = tabuleiro(
        snake(A, [(4, 5), (3, 5), (2, 5)]),
        snake(B, [(6, 5), (7, 5), (8, 5)]),
    )
    depois = step(board, {A: "right", B: "left"})
    assert not viva(depois, A)
    assert not viva(depois, B)


def test_cabeca_a_cabeca_na_comida():
    # As duas cabeças caem na comida: as duas comem e crescem antes das
    # colisões, e o confronto compara os tamanhos de depois. A tem 4 e B
    # tem 3; depois de comer, 5 contra 4, e A vence.
    board = tabuleiro(
        snake(A, [(4, 5), (3, 5), (2, 5), (1, 5)]),
        snake(B, [(6, 5), (7, 5), (8, 5)]),
        food=[(5, 5)],
    )
    depois = step(board, {A: "right", B: "left"})
    assert viva(depois, A) and not viva(depois, B)
    assert depois.snake(A).length == 5
    assert idx(5, 5, 11) not in depois.food


def test_morte_por_fome():
    board = tabuleiro(snake(A, [(1, 1), (1, 0), (0, 0)], health=1))
    assert not viva(step(board, {A: "up"}), A)


def test_comida_salva_da_fome():
    board = tabuleiro(snake(A, [(1, 1), (1, 0), (0, 0)], health=1), food=[(1, 2)])
    depois = step(board, {A: "up"})
    assert viva(depois, A)
    assert depois.snake(A).health == 100


def test_corpo_de_cobra_morta_de_fome_nao_mata():
    #   x: 2 3 4
    # y=3  . a .      A (vida 1) morre de fome; B anda para (3,2), que seria
    # y=2  B a .      um segmento de A
    # y=1  b A .
    board = tabuleiro(
        snake(A, [(3, 1), (3, 2), (3, 3), (3, 4)], health=1),
        snake(B, [(2, 2), (2, 1), (2, 0)]),
    )
    depois = step(board, {A: "right", B: "right"})
    assert not viva(depois, A)
    assert viva(depois, B)


def test_cobra_eliminada_nao_muda():
    board = tabuleiro(snake(A, [(0, 1), (1, 1), (2, 1)]), snake(B, [(5, 5), (5, 4)]))
    depois = step(board, {A: "left", B: "up"})
    morta = depois.snake(A)
    assert step(depois, {B: "up"}).snake(A) == morta


def test_comida_comida_sai_e_nada_nasce():
    board = tabuleiro(snake(A, [(1, 1), (1, 0)]), food=[(1, 2), (5, 5)])
    depois = step(board, {A: "up"})
    assert depois.food == frozenset({idx(5, 5, 11)})


def test_estado_original_intacto():
    board = tabuleiro(
        snake(A, [(1, 1), (1, 0), (0, 0)], health=50),
        snake(B, [(5, 5), (5, 4)]),
        food=[(1, 2)],
    )
    corpo_a, vida_a, comida = board.snake(A).body, board.snake(A).health, board.food
    step(board, {A: "up", B: "up"})
    assert board.snake(A).body == corpo_a
    assert board.snake(A).health == vida_a
    assert board.food == comida


# --- Direções que não são morte certa ---

def test_safe_moves_tira_parede_pescoco_e_corpos():
    #   x: 0 1 2
    # y=2  . b b      down e left são parede e right é o pescoço; up, (0,1),
    # y=1  . B .      está livre
    # y=0  A a a
    board = tabuleiro(
        snake(A, [(0, 0), (1, 0), (2, 0)]),
        snake(B, [(1, 1), (1, 2), (2, 2)]),
        width=3, height=3,
    )
    assert safe_moves(board, A) == ["up"]
    # B: up é o pescoço, down é o corpo de A, left e right estão livres.
    assert safe_moves(board, B) == ["left", "right"]


def test_safe_moves_libera_cauda_que_sai_do_lugar():
    #   x: 0 1
    # y=1  a a      a cauda (0,1) sai do lugar: up é candidata
    # y=0  A a
    board = tabuleiro(snake(A, [(0, 0), (1, 0), (1, 1), (0, 1)]), width=2, height=2)
    assert safe_moves(board, A) == ["up"]


def test_safe_moves_cauda_empilhada_nao_e_livre():
    board = tabuleiro(
        snake(A, [(0, 0), (1, 0), (1, 1), (0, 1), (0, 1)]), width=2, height=2
    )
    assert safe_moves(board, A) == ["up"]  # nenhuma: a primeira da ordem


def test_safe_moves_sem_saida_simula_a_primeira_direcao():
    board = tabuleiro(snake(A, [(0, 0), (1, 0), (1, 1), (0, 1), (0, 1)]), width=2, height=2)
    depois = step(board, {A: safe_moves(board, A)[0]})
    assert not viva(depois, A)


def test_safe_moves_no_turno_zero_com_corpo_empilhado():
    board = tabuleiro(snake(A, [(5, 5), (5, 5), (5, 5)]))
    assert safe_moves(board, A) == ["up", "down", "left", "right"]
