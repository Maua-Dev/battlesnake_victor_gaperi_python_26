"""Testes da estratégia da cobra: cada cenário tem uma única resposta certa.

Rode com: pytest tests/app/test_estrategia.py
"""
from src.app.logic import get_move
from src.app.grid import would_lose_head_to_head
from src.app.floodfill import flood_fill
from src.app.astar import a_star
from tests.helpers import snake, make_game

EU = "eu"


def test_desvia_de_adversaria():
    # left é o corpo da outra cobra, up é parede e down é o pescoço.
    eu = snake(EU, [(5, 10), (5, 9), (5, 8)])
    outra = snake("outra", [(4, 10), (3, 10), (2, 10)])
    state = make_game(eu, others=[outra])
    assert get_move(state).move == "right"


def test_entra_na_propria_cauda():
    # A cauda (4,10) sai do lugar neste turno, então left é a única saída:
    # up é parede, down é o pescoço e right é o corpo do bloqueio.
    eu = snake(EU, [(5, 10), (5, 9), (4, 9), (4, 10)])
    bloqueio = snake("bloqueio", [(8, 10), (7, 10), (6, 10)])
    state = make_game(eu, others=[bloqueio])
    assert get_move(state).move == "left"


def test_pescoco_de_cobra_de_tamanho_2():
    # Em cobra de tamanho 2 o pescoço também é a cauda: liberar a cauda
    # não pode liberar a meia-volta.
    eu = snake(EU, [(5, 5), (5, 4)])
    state = make_game(eu)
    for _ in range(50):
        assert get_move(state).move != "down"


def test_evita_cabeca_a_cabeca_com_maior():
    # A cabeça da rival (3,10) também alcança (4,10): left perderia o confronto.
    eu = snake(EU, [(5, 10), (5, 9), (5, 8)])
    grande = snake("grande", [(3, 10), (2, 10), (1, 10), (0, 10)])
    state = make_game(eu, others=[grande])
    assert get_move(state).move == "right"


def test_evita_cabeca_a_cabeca_com_igual():
    # Empate de tamanho mata as duas cobras, então também é evitado.
    eu = snake(EU, [(5, 10), (5, 9), (5, 8)])
    igual = snake("igual", [(3, 10), (2, 10), (1, 10)])
    state = make_game(eu, others=[igual])
    assert get_move(state).move == "right"


def test_cabeca_a_cabeca_com_menor_e_permitida():
    eu = snake(EU, [(5, 10), (5, 9), (5, 8), (5, 7)])
    menor = snake("menor", [(3, 10), (2, 10), (1, 10)])
    state = make_game(eu, others=[menor])
    assert would_lose_head_to_head(state.board, state.you, (4, 10)) is False


def test_com_fome_vai_para_a_comida():
    # Sem rivais e no turno 1, a fome vem da regra de sobrevivência: a comida
    # está a 3 passos e 10 < 3 + 15. Com vida 50 já não seria fome.
    eu = snake(EU, [(5, 5), (5, 4), (5, 3)], health=10)
    state = make_game(eu, food=[(2, 5)])
    assert get_move(state).move == "left"


def test_sem_fome_ignora_a_comida():
    # Mesma cobra, vida cheia: a comida à esquerda não pesa na decisão.
    eu = snake(EU, [(5, 5), (5, 4), (5, 3)], health=100)
    state = make_game(eu, food=[(2, 5)])
    assert get_move(state).move == "up"


def tabuleiro(width: int, height: int):
    """Tabuleiro vazio para testar as buscas; a cobra não entra em blocked."""
    return make_game(snake(EU, [(0, 0)]), width=width, height=height).board


def test_flood_fill_no_tabuleiro_vazio():
    assert flood_fill(tabuleiro(5, 5), (2, 2), set()) == 25


def test_flood_fill_com_muro():
    muro = {(2, y) for y in range(5)}
    assert flood_fill(tabuleiro(5, 5), (0, 0), muro) == 10


def test_evita_o_beco():
    # A outra cobra acabou de comer: a cauda dela está empilhada em (4,10) e
    # não sai do lugar. Por isso up leva a um bolsão de 2 casas, (5,10) e
    # (6,10), entre a outra cobra e o próprio corpo. Se a cauda saísse do
    # lugar, o bolsão se abriria por (4,10) e o teste deixaria de testar o beco.
    # down e left dão no resto do tabuleiro, e down vence.
    eu = snake(EU, [(5, 9), (6, 9), (7, 9), (7, 10), (8, 10)])
    outra = snake("outra", [
        (0, 5), (0, 6), (0, 7), (0, 8), (0, 9), (0, 10),
        (1, 10), (2, 10), (3, 10), (4, 10), (4, 10),
    ])
    state = make_game(eu, others=[outra])
    assert get_move(state).move == "down"


def test_a_star_contorna_obstaculo():
    # A coluna x=1 só tem passagem em (1,4): o caminho sobe, cruza e desce.
    bloqueado = {(1, 0), (1, 1), (1, 2), (1, 3)}
    caminho = a_star(tabuleiro(5, 5), (0, 0), (2, 0), bloqueado)
    assert len(caminho) == 11
    assert caminho[0] == (0, 0)
    assert caminho[-1] == (2, 0)


def test_a_star_sem_caminho():
    bloqueado = {(1, 0), (1, 1), (0, 1)}
    assert a_star(tabuleiro(3, 3), (0, 0), (2, 2), bloqueado) == []
