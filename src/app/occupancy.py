"""Ocupação temporal: em quantos movimentos cada casa fica livre.

free_after[casa] = 0 numa casa sem cobra. Num corpo de n segmentos, o
segmento i (0 é a cabeça) sai da casa depois de n - i movimentos. As buscas
deste módulo só alcançam uma casa no tempo t se free_after[casa] <= t: um
corpo que vai sair do caminho a tempo não é tratado como parede.

Tudo aqui trabalha com índices de board_state, sem Pydantic.
"""
import heapq

from .board_state import BoardState, SnakeState


def _mark(free_after: list[int], snake: SnakeState, grows: bool) -> None:
    """Escreve os tempos de liberação do corpo, ficando com o maior por casa.

    Se a cobra pode comer no próximo turno (grows), o corpo para de encurtar
    por um turno: todo segmento soma 1, menos o último. Pelas regras
    oficiais o movimento vem antes da alimentação, então a casa da cauda
    atual libera no próximo turno mesmo quando a cobra come.
    """
    body = snake.body
    n = len(body)
    last = n - 1
    for i, cell in enumerate(body):
        t = n - i + (1 if grows and i != last else 0)
        if t > free_after[cell]:
            free_after[cell] = t


def base_free_after(board: BoardState, me: str | None = None) -> list[int]:
    """free_after de todas as cobras vivas.

    As adversárias (todas menos `me`) com a cabeça vizinha a uma comida são
    tratadas como se fossem comer. O crescimento de `me` depende da
    candidata e é aplicado à parte, com with_growth.
    """
    free_after = [0] * board.size
    neighbors = board.neighbors
    food = board.food
    for snake in board.snakes:
        if not snake.alive:
            continue
        grows = snake.id != me and any(n in food for n in neighbors[snake.head])
        _mark(free_after, snake, grows)
    return free_after


def with_growth(free_after: list[int], snake: SnakeState) -> list[int]:
    """Cópia de free_after com `snake` crescendo no próximo turno.

    Usada na candidata cuja nova cabeça tem comida.
    """
    grown = list(free_after)
    _mark(grown, snake, True)
    return grown


def temporal_reach(
    board: BoardState,
    free_after: list[int],
    start: int,
    t0: int,
    blocked=frozenset(),
    targets=frozenset(),
) -> tuple[int, int | None]:
    """BFS temporal sem espera a partir de `start` no tempo t0.

    Um vizinho só é alcançado no tempo t+1 se estiver fora de `blocked` e
    tiver free_after <= t+1. Uma casa recusada não é marcada e pode ser
    alcançada mais tarde, por outra casa da fronteira. A cobra não fica
    parada esperando.

    Devolve (casas alcançadas, passos até a primeira casa de `targets`, ou
    None). Início fora do tabuleiro ou bloqueado devolve (0, None).
    """
    if not 0 <= start < board.size or start in blocked:
        return 0, None
    neighbors = board.neighbors
    seen = {start}
    frontier = [start]
    t = t0
    found = 0 if start in targets else None
    while frontier:
        t += 1
        nxt = []
        for cell in frontier:
            for n in neighbors[cell]:
                if n in seen or n in blocked or free_after[n] > t:
                    continue
                seen.add(n)
                nxt.append(n)
                if found is None and n in targets:
                    found = t - t0
        frontier = nxt
    return len(seen), found


def temporal_area(
    board: BoardState,
    free_after: list[int],
    start: int,
    t0: int,
    blocked=frozenset(),
) -> int:
    """Quantas casas a BFS temporal alcança a partir de start (inclusive)."""
    return temporal_reach(board, free_after, start, t0, blocked)[0]


def temporal_voronoi(
    board: BoardState,
    free_after: list[int],
    seeds: dict[str, tuple[int, int]],
) -> tuple[dict[str, int], list[str | None]]:
    """Território temporal: BFS multi-origem, com as regras de voronoi.voronoi.

    seeds mapeia o id de cada cobra para (casa de origem, distância inicial).
    Uma cobra só alcança uma casa na distância d se free_after <= d. Cada
    casa pertence à cobra de menor distância; no empate, à única
    estritamente maior entre as empatadas. Sem uma única maior, a casa é
    disputada: não conta para ninguém, mas é expandida para todas.

    Devolve as contagens por cobra e owner[índice]: o id da dona, ou None
    (disputada ou não alcançada). A casa de origem é sempre da semente.
    """
    length = {s.id: s.length for s in board.snakes}
    neighbors = board.neighbors
    counts = {snake_id: 0 for snake_id in seeds}
    owner: list[str | None] = [None] * board.size

    pending: dict[int, list[tuple[int, str]]] = {}
    reserved = set()
    for snake_id, (origin, dist) in seeds.items():
        pending.setdefault(dist, []).append((origin, snake_id))
        reserved.add(origin)

    # contenders[casa] = cobras que alcançam a casa na menor distância.
    contenders: dict[int, tuple[str, ...]] = {}
    frontier: list[int] = []
    level = min(pending, default=0)
    while frontier or pending:
        for origin, snake_id in pending.pop(level, []):
            contenders[origin] = (snake_id,)
            owner[origin] = snake_id
            counts[snake_id] += 1
            frontier.append(origin)

        arrival = level + 1
        claims: dict[int, set[str]] = {}
        for current in frontier:
            for n in neighbors[current]:
                if n in contenders or n in reserved or free_after[n] > arrival:
                    continue
                claims.setdefault(n, set()).update(contenders[current])

        frontier = []
        for cell, tied in claims.items():
            contenders[cell] = tuple(tied)
            if len(tied) == 1:
                winner = next(iter(tied))
            else:
                biggest = max(length[s] for s in tied)
                winners = [s for s in tied if length[s] == biggest]
                winner = winners[0] if len(winners) == 1 else None
            if winner is not None:
                counts[winner] += 1
                owner[cell] = winner
            frontier.append(cell)
        level += 1
    return counts, owner


def temporal_a_star(
    board: BoardState,
    free_after: list[int],
    start: int,
    t0: int,
    goal: int,
    blocked=frozenset(),
) -> list[int]:
    """Caminho mais curto de start até goal (os dois incluídos), ou [].

    g é o tempo de chegada: o vizinho só entra se estiver fora de `blocked`
    e tiver free_after <= g + 1. Guarda o melhor g por casa, uma
    aproximação: um caminho que chegaria mais tarde numa casa, justamente
    para encontrar a próxima já livre, é descartado.
    """
    neighbors = board.neighbors
    w, height = board.width, board.height
    gx, gy = goal % w, goal // w

    def h(cell: int) -> int:
        return abs(cell % w - gx) + abs(cell // w - gy)

    def order(cell: int) -> int:
        # Desempate do heap pela tupla (x, y), como em astar.a_star.
        return (cell % w) * height + cell // w

    heap = [(t0 + h(start), t0, order(start), start)]
    best_g = {start: t0}
    came_from: dict[int, int] = {}
    while heap:
        _, g, _, current = heapq.heappop(heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]
        if g > best_g[current]:
            continue
        new_g = g + 1
        for n in neighbors[current]:
            if n in blocked or free_after[n] > new_g:
                continue
            if new_g < best_g.get(n, new_g + 1):
                best_g[n] = new_g
                came_from[n] = current
                heapq.heappush(heap, (new_g + h(n), new_g, order(n), n))
    return []
