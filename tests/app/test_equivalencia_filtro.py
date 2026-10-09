"""O filtro de get_move e o simulador da busca seguem a mesma regra de
ocupação: em tabuleiros aleatórios, as candidatas do filtro (sem a regra de
vida e hazard) são as direções que não são morte certa na simulação.

Rode com: pytest tests/app/test_equivalencia_filtro.py
"""
import random

from src.app.board_state import from_game
from src.app.grid import MOVES, manhattan
from src.app.logic import filter_moves
from src.app.simulator import safe_moves
from tests.helpers import snake, make_game

EU = "eu"
LADO = 11
TABULEIROS = 400
SEMENTE = 74


def vizinhas_livres(rng, casa, ocupadas):
    """As vizinhas de casa dentro do tabuleiro e fora de ocupadas, embaralhadas."""
    x, y = casa
    result = [
        (x + dx, y + dy)
        for dx, dy in MOVES.values()
        if 0 <= x + dx < LADO and 0 <= y + dy < LADO and (x + dx, y + dy) not in ocupadas
    ]
    rng.shuffle(result)
    return result


def passeio(rng, inicio, tamanho, ocupadas):
    """Corpo contínuo que começa em inicio e não cruza ocupadas nem a si mesmo.
    Pode sair menor que tamanho se o passeio ficar sem saída.
    """
    corpo = [inicio]
    while len(corpo) < tamanho:
        livres = vizinhas_livres(rng, corpo[-1], ocupadas | set(corpo))
        if not livres:
            break
        corpo.append(livres[0])
    return corpo


def variar(rng, corpo):
    """Às vezes o corpo todo empilhado (começo da partida), às vezes a cauda
    empilhada (acabou de comer)."""
    sorteio = rng.random()
    if sorteio < 0.1:
        return [corpo[0]] * 3
    if sorteio < 0.4:
        return corpo + [corpo[-1]]
    return corpo


def gerar(rng):
    """Um tabuleiro aleatório: a minha cobra primeiro e de 0 a 3 rivais. A
    primeira rival tem muitas vezes a cauda vizinha da minha cabeça.
    """
    ocupadas = set()
    livres = [(x, y) for x in range(LADO) for y in range(LADO)]
    meu = passeio(rng, rng.choice(livres), rng.randint(2, 12), ocupadas)
    meu = variar(rng, meu)
    ocupadas |= set(meu)
    cobras = [snake(EU, meu)]
    for i in range(rng.randint(0, 3)):
        tamanho = rng.randint(2, 12)
        perto = vizinhas_livres(rng, meu[0], ocupadas)
        if i == 0 and perto and rng.random() < 0.6:
            # Começa o passeio na casa vizinha da minha cabeça e o inverte:
            # essa casa vira a cauda da rival.
            corpo = list(reversed(passeio(rng, perto[0], tamanho, ocupadas)))
        else:
            soltas = [c for c in livres if c not in ocupadas]
            corpo = passeio(rng, rng.choice(soltas), tamanho, ocupadas)
        corpo = variar(rng, corpo)
        ocupadas |= set(corpo)
        cobras.append(snake(f"rival-{i}", corpo))
    return make_game(cobras[0], others=cobras[1:], width=LADO, height=LADO)


def cauda_vizinha(state):
    """'livre' ou 'empilhada' se a cauda de alguma rival é vizinha da minha
    cabeça, senão None."""
    cabeca = (state.you.head.x, state.you.head.y)
    for s in state.board.snakes[1:]:
        cauda = (s.body[-1].x, s.body[-1].y)
        if manhattan(cabeca, cauda) == 1 and len(s.body) > 1:
            return "empilhada" if s.body[-1] == s.body[-2] else "livre"
    return None


def test_filtro_igual_ao_simulador_em_tabuleiros_aleatorios():
    rng = random.Random(SEMENTE)
    casos = {"livre": 0, "empilhada": 0, None: 0}
    for _ in range(TABULEIROS):
        state = gerar(rng)
        board = from_game(state)
        filtro = [d for d, motivo in filter_moves(state, board).items() if motivo is None]
        simulacao = safe_moves(board, EU)
        if filtro:
            assert filtro == simulacao, state.board.model_dump()
        else:
            # Sem nenhuma direção, a simulação usa a primeira da ordem canônica.
            assert simulacao == ["up"], state.board.model_dump()
        casos[cauda_vizinha(state)] += 1
    # O caso que motivou a regra comum precisa aparecer de fato na amostra.
    assert casos["livre"] >= 40
    assert casos["empilhada"] >= 20
