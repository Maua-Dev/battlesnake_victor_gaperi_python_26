"""Sobrevivência: a cobra consegue andar a profundidade alvo sem morrer?

Uma DFS com retrocesso parte da nova cabeça (profundidade 1) e simula passo
a passo o próprio corpo de verdade (a cauda sai, a comida comida faz crescer
e some daquele caminho), a vida (1 por passo, o dano de hazard e a volta a
100 ao comer) e as adversárias pela ocupação temporal: a casa só pode ser
ocupada no passo t se free_after <= t.

O corpo segue as regras oficiais: a cauda sai antes de a cabeça entrar, e
comer repete o último segmento. Por isso uma cauda empilhada continua
ocupando a casa no passo seguinte, sem tratamento especial.
"""
from collections import deque

from . import config
from .board_state import BoardState, MOVE_ORDER, OFF_BOARD, SnakeState


def survival(
    board: BoardState,
    free_after: list[int],
    me: SnakeState,
    direction: str,
    deadline=None,
) -> tuple[int, bool, int]:
    """(maior profundidade alcançada, chegou à profundidade alvo, nós).

    A profundidade alvo é min(tamanho, SURVIVAL_MAX_DEPTH). Cada casa
    entrada conta como um nó, a nova cabeça inclusive. A busca para na
    profundidade alvo, em SURVIVAL_MAX_NODES nós ou quando o prazo passa;
    o prazo é conferido a cada SURVIVAL_DEADLINE_EVERY nós, porque ler o
    relógio em todo nó custaria mais que o próprio nó.

    free_after deve ser o base: o próprio corpo é simulado aqui.
    """
    steps = board.steps
    first = steps[me.head][MOVE_ORDER.index(direction)]
    if first == OFF_BOARD:
        return 0, False, 0

    target = min(me.length, config.SURVIVAL_MAX_DEPTH)
    max_nodes = config.SURVIVAL_MAX_NODES
    every = config.SURVIVAL_DEADLINE_EVERY
    damage = board.hazard_damage
    hazards = board.hazards

    body = deque(me.body)
    occupied = [0] * board.size
    for cell in body:
        occupied[cell] += 1
    food = set(board.food)
    health = me.health

    best = 0
    nodes = 0

    def fits(cell: int, t: int) -> bool:
        """A cabeça pode entrar em cell no passo t (a cauda já saiu)?"""
        if cell == OFF_BOARD or occupied[cell] or free_after[cell] > t:
            return False
        if cell in food:
            return True
        return health - 1 - damage * hazards.get(cell, 0) > 0

    # A cauda sai antes de a cabeça entrar: o primeiro passo já vê a casa
    # dela livre (se não estiver empilhada).
    tail = body.pop()
    occupied[tail] -= 1
    if not fits(first, 1):
        return 0, False, 0

    # Cada quadro: [casa, passo, próxima direção, vida anterior, comeu, cauda
    # que saiu para o próximo passo].
    stack: list[list] = []
    cell, t = first, 1
    while True:
        # Entra em cell no passo t.
        prev_health = health
        ate = cell in food
        body.appendleft(cell)
        occupied[cell] += 1
        if ate:
            food.discard(cell)
            body.append(body[-1])
            occupied[body[-1]] += 1
            health = 100
        else:
            health -= 1 + damage * hazards.get(cell, 0)
        nodes += 1
        if t > best:
            best = t
        if t >= target:
            return best, True, nodes
        if nodes >= max_nodes:
            break
        if deadline is not None and nodes % every == 0 and deadline.expired():
            break
        moved = body.pop()
        occupied[moved] -= 1
        stack.append([cell, t, 0, prev_health, ate, moved])

        # Procura o próximo passo, voltando enquanto o quadro do topo não
        # tiver mais direções.
        cell = OFF_BOARD
        while stack:
            frame = stack[-1]
            here, here_t, d = frame[0], frame[1], frame[2]
            while d < 4:
                n = steps[here][d]
                d += 1
                if fits(n, here_t + 1):
                    cell, t = n, here_t + 1
                    break
            frame[2] = d
            if cell != OFF_BOARD:
                break
            # Sem saída: desfaz a entrada em `here`.
            stack.pop()
            _, _, _, health, ate_here, moved_here = frame
            body.append(moved_here)
            occupied[moved_here] += 1
            if ate_here:
                occupied[body.pop()] -= 1
                food.add(here)
            body.popleft()
            occupied[here] -= 1
        if cell == OFF_BOARD:
            break
    return best, False, nodes
