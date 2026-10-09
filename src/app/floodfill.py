"""Flood fill: quantas casas a cobra alcança a partir de uma posição."""
from collections import deque
from collections.abc import Callable

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


def region_sizes(board: Board, blocked: set[Pos]) -> Callable[[Pos], int]:
    """Função casa -> tamanho da região livre que contém a casa.

    Dá o mesmo que flood_fill(board, casa, blocked) para qualquer casa, mas a
    primeira consulta a uma região rotula todas as casas dela de uma vez; as
    seguintes, de qualquer casa da mesma região, só leem o tamanho guardado.

    blocked não é copiado: não o altere depois de criar a função.
    """
    sizes: dict[Pos, int] = {}

    def size_of(start: Pos) -> int:
        if not in_bounds(board, start) or start in blocked:
            return 0
        if start in sizes:
            return sizes[start]

        visited = {start}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for n in neighbors(board, current, blocked):
                if n not in visited:
                    visited.add(n)
                    queue.append(n)
        for cell in visited:
            sizes[cell] = len(visited)
        return len(visited)

    return size_of
