"""A*: caminho mais curto entre duas casas, desviando das bloqueadas."""
import heapq

from .grid import Pos, manhattan, neighbors
from .models import Board


def a_star(board: Board, start: Pos, goal: Pos, blocked: set[Pos]) -> list[Pos]:
    """Caminho de start até goal, incluindo os dois, ou [] se não houver.

    A heurística é a distância de Manhattan, que nunca superestima numa
    grade de 4 direções, então o caminho devolvido é o mais curto.
    """
    heap = [(manhattan(start, goal), 0, start)]
    best_g = {start: 0}
    came_from: dict[Pos, Pos] = {}

    while heap:
        _, g, current = heapq.heappop(heap)
        # O objetivo só conta como alcançado ao SAIR do heap: é aí que o
        # custo dele está garantidamente mínimo.
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]
        if g > best_g[current]:
            continue  # entrada velha: essa casa já foi alcançada mais barato

        for n in neighbors(board, current, blocked):
            new_g = g + 1
            if new_g < best_g.get(n, new_g + 1):
                best_g[n] = new_g
                came_from[n] = current
                heapq.heappush(heap, (new_g + manhattan(n, goal), new_g, n))
    return []
