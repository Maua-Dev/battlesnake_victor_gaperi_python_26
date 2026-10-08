"""Flood fill: quantas casas a cobra alcança a partir de uma posição."""
from collections import deque

from .grid import Pos, in_bounds, neighbors
from .models import Board


def flood_fill(board: Board, start: Pos, blocked: set[Pos]) -> int:
    """Conta as casas alcançáveis a partir de start (inclusive), sem passar
    por blocked. Devolve 0 se start estiver fora do tabuleiro ou bloqueado.
    """
    if not in_bounds(board, start) or start in blocked:
        return 0

    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for n in neighbors(board, current, blocked):
            if n not in visited:
                visited.add(n)
                queue.append(n)
    return len(visited)
