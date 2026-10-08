"""Voronoi: quanto do tabuleiro cada cobra alcança antes das outras."""
from .grid import Pos, neighbors
from .models import Board


def voronoi(
    board: Board,
    seeds: dict[str, tuple[Pos, int]],
    blocked: set[Pos],
) -> dict[str, int]:
    """Conta as casas de cada cobra numa BFS multi-origem.

    seeds mapeia o id de cada cobra para (casa de origem, distância inicial).
    Cada casa fora de blocked pertence à cobra de menor distância. Num empate,
    fica com a única estritamente maior entre as empatadas (ela venceria o
    cabeça a cabeça). Sem uma única maior, a casa é disputada: não conta para
    ninguém, mas continua sendo expandida para todas as empatadas.

    A casa de origem conta para a própria cobra mesmo estando em blocked.
    """
    length = {snake.id: snake.length for snake in board.snakes}
    counts = {snake_id: 0 for snake_id in seeds}

    # As sementes entram no nível da própria distância inicial, e as casas de
    # origem ficam reservadas desde o começo: nenhuma outra cobra as alcança
    # antes de a semente entrar.
    pending: dict[int, list[tuple[Pos, str]]] = {}
    reserved: set[Pos] = set()
    for snake_id, (origin, dist) in seeds.items():
        pending.setdefault(dist, []).append((origin, snake_id))
        reserved.add(origin)

    # contenders[casa] = cobras que alcançam a casa na menor distância.
    contenders: dict[Pos, set[str]] = {}
    frontier: list[Pos] = []
    level = min(pending, default=0)
    while frontier or pending:
        # Sementes deste nível: forçadas, nenhuma outra cobra fica com elas.
        for origin, snake_id in pending.pop(level, []):
            contenders[origin] = {snake_id}
            counts[snake_id] += 1
            frontier.append(origin)

        claims: dict[Pos, set[str]] = {}
        for current in frontier:
            for n in neighbors(board, current, blocked):
                if n not in contenders and n not in reserved:
                    claims.setdefault(n, set()).update(contenders[current])

        frontier = []
        for cell, tied in claims.items():
            contenders[cell] = tied
            biggest = max(length[snake_id] for snake_id in tied)
            winners = [snake_id for snake_id in tied if length[snake_id] == biggest]
            if len(winners) == 1:
                counts[winners[0]] += 1
            frontier.append(cell)
        level += 1
    return counts
