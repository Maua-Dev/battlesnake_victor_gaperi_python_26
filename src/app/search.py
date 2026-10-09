"""Busca no duelo: max-min com movimentos simultâneos e poda alpha-beta.

Cada nível é um turno inteiro. Para cada movimento meu (nó MAX), a rival
escolhe a resposta que mais me prejudica (nó MIN) e o turno é simulado com
os dois movimentos (simulator.step). É o modelo "paranoico" do movimento
simultâneo: a rival responde como se conhecesse o meu movimento. É
pessimista de propósito, contra adversárias fortes.

A busca não escolhe o movimento de maior valor: ela só veta a escolha
heurística, trocando-a quando ela perde ou empata dentro do horizonte e outro
movimento vale mais. Com os pesos iniciais da folha o território domina a
parcela de comida, e uma busca que sempre escolhesse o maior valor trocaria
a escolha heurística com fome pela comida da rival. A heurística decide entre
os movimentos que não perdem; a busca enxerga as derrotas à frente.

Roda por aprofundamento iterativo dentro do prazo da jogada, e só vale o
resultado de uma profundidade inteira.
"""
import math

from . import config
from .board_state import BoardState, idx
from .occupancy import base_free_after, temporal_reach, temporal_voronoi
from .simulator import safe_moves, step

# Na raiz, a substituta buscada depois da melhor até ali usa como limite
# inferior um valor um pouco abaixo da melhor: um empate sai exato, e não
# podado.
_TIE_EPSILON = 1e-9


class _Timeout(Exception):
    """O prazo passou no meio de uma profundidade."""


def evaluate(board: BoardState, me: str, rival: str) -> float:
    """Valor de uma folha sem fim de jogo, do meu ponto de vista.

    Soma ponderada (pesos EVAL_* do config) da diferença de território
    temporal, da minha área temporal, da diferença de tamanho, da distância
    até a comida mais próxima (pesando mais com a vida baixa), da vida e da
    distância até o centro. Fica sempre entre DRAW e -DRAW, sem os extremos.
    """
    mine, theirs = board.snake(me), board.snake(rival)
    free_after = base_free_after(board, me)
    counts, _ = temporal_voronoi(
        board, free_after, {me: (mine.head, 0), rival: (theirs.head, 0)}
    )
    area, food_dist = temporal_reach(board, free_after, mine.head, 0, targets=board.food)
    if food_dist is None:
        food_dist = board.width + board.height
    center = idx(board.width // 2, board.height // 2, board.width)
    value = (
        config.EVAL_TERRITORY * (counts[me] - counts[rival])
        + config.EVAL_AREA * area
        + config.EVAL_LENGTH * (mine.length - theirs.length)
        - config.EVAL_FOOD * food_dist * (100 - mine.health) / 100
        + config.EVAL_HEALTH * mine.health
        - config.EVAL_CENTER * board.manhattan(mine.head, center)
    )
    limit = abs(config.DRAW) - 1
    return max(-limit, min(limit, value))


class _Search:
    """Uma busca de `me` contra `rival`, com ou sem poda e prazo."""

    def __init__(self, me: str, rival: str, deadline=None, prune: bool = True):
        self.me = me
        self.rival = rival
        self.deadline = deadline
        self.prune = prune
        # Alguma folha parou pelo limite de profundidade nesta iteração.
        self.cut = False

    def max_value(self, board, depth, alpha, beta, ply, my_moves=None) -> float:
        """Nó MAX: o melhor dos meus movimentos."""
        rival_moves = safe_moves(board, self.rival)
        best = -math.inf
        for move in my_moves or safe_moves(board, self.me):
            value = self.min_value(board, move, rival_moves, depth, alpha, beta, ply)
            if value > best:
                best = value
                if best > alpha:
                    alpha = best
                if self.prune and best >= beta:
                    break
        return best

    def min_value(self, board, my_move, rival_moves, depth, alpha, beta, ply) -> float:
        """Nó MIN: a pior resposta da rival ao meu movimento."""
        worst = math.inf
        for reply in rival_moves:
            after = step(board, {self.me: my_move, self.rival: reply})
            value = self.value_after(after, depth - 1, alpha, beta, ply + 1)
            if value < worst:
                worst = value
                if worst < beta:
                    beta = worst
                if self.prune and worst <= alpha:
                    break
        return worst

    def value_after(self, board, depth, alpha, beta, ply) -> float:
        """Valor do tabuleiro depois de um turno, `ply` turnos desde a raiz."""
        if self.deadline is not None and self.deadline.expired():
            raise _Timeout
        me_alive = board.snake(self.me).alive
        rival_alive = board.snake(self.rival).alive
        if not me_alive and not rival_alive:
            return config.DRAW
        if not me_alive:
            return -config.WIN + ply
        if not rival_alive:
            return config.WIN - ply
        if depth == 0:
            self.cut = True
            return evaluate(board, self.me, self.rival)
        return self.max_value(board, depth, alpha, beta, ply)

    def root(self, board, root_order, previous, depth) -> str:
        """A resposta da busca numa profundidade, com o veto.

        A escolha heurística (root_order[0]) é buscada primeiro, com janela
        cheia, para ter o valor exato. Se ele for maior que DRAW, ela fica, e
        as outras candidatas nem são buscadas. Se não, as demais são buscadas
        (`previous`, a resposta da profundidade anterior, primeiro, e depois a
        ordem heurística), e vale a de maior valor, se for maior que o dela.
        Entre substitutas de mesmo valor, vence a primeira em root_order.
        """
        rival_moves = safe_moves(board, self.rival)
        heuristic = root_order[0]
        heuristic_value = self.min_value(
            board, heuristic, rival_moves, depth, -math.inf, math.inf, 0
        )
        if heuristic_value > config.DRAW:
            return heuristic

        explore = [m for m in root_order[1:] if m != previous]
        if previous is not None and previous != heuristic:
            explore.insert(0, previous)
        best_value = heuristic_value
        tied: list[str] = []
        for move in explore:
            # A primeira substituta só interessa se for estritamente melhor
            # que a heurística; as seguintes, se empatarem com a melhor.
            alpha = best_value - _TIE_EPSILON if tied else heuristic_value
            value = self.min_value(board, move, rival_moves, depth, alpha, math.inf, 0)
            if value > best_value:
                best_value = value
                tied = [move]
            elif tied and value == best_value:
                tied.append(move)
        return min(tied, key=root_order.index) if tied else heuristic


def minimax_value(
    board: BoardState,
    me: str,
    rival: str,
    depth: int,
    prune: bool = True,
    root_moves: list[str] | None = None,
) -> float:
    """Valor da raiz numa profundidade fixa, sem prazo. Com prune=False é o
    minimax puro, para conferir que a poda não muda o valor.
    """
    search = _Search(me, rival, prune=prune)
    return search.max_value(board, depth, -math.inf, math.inf, 0, root_moves)


def best_move(
    board: BoardState,
    me: str,
    rival: str,
    root_order: list[str],
    deadline,
) -> str | None:
    """Aprofundamento iterativo, de 1 a MAX_SEARCH_DEPTH, dentro do prazo.

    root_order são as candidatas na ordem da escolha heurística; a
    primeira é a escolha heurística, que a busca só troca pelo veto (ver
    _Search.root). O prazo é conferido em todo nó; quando passa, a
    profundidade em andamento é descartada. Para cedo quando uma
    profundidade termina sem nenhuma folha cortada pelo limite: a árvore
    foi resolvida até o fim.

    Devolve a resposta da última profundidade completa, ou None se nenhuma
    terminou.
    """
    search = _Search(me, rival, deadline)
    best = None
    for depth in range(1, config.MAX_SEARCH_DEPTH + 1):
        search.cut = False
        try:
            best = search.root(board, root_order, best, depth)
        except _Timeout:
            break
        if not search.cut:
            break
    return best
