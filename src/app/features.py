"""Características: o que a cobra mede em cada direção candidata.

Nada aqui escolhe um movimento. evaluate_moves devolve uma MoveFeatures por
candidata e build_context monta o DecisionContext. Os dois entram em
decision.decide, que no futuro será trocada por um modelo de decisão externo.

A área, o território, a comida e a sobrevivência usam a ocupação temporal
(occupancy.py) sobre o BoardState da jogada. As rivais encurraladas
continuam com os obstáculos estáticos.
"""
from dataclasses import dataclass

from . import config
from .board_state import BoardState, from_game, idx, xy
from .decision import DecisionContext, MoveFeatures
from .floodfill import region_sizes
from .grid import (
    Pos, pos, step, manhattan, neighbors, obstacles, threat_zones,
    would_lose_head_to_head,
)
from .models import GameState, Snake
from .occupancy import (
    base_free_after, temporal_a_star, temporal_area, temporal_voronoi, with_growth,
)
from .survival import survival


@dataclass(frozen=True)
class FoodTarget:
    """A comida alvo e o caminho A* temporal da cabeça atual até ela."""
    pos: Pos
    dist: int
    path: list[Pos]
    # Custo de vida do caminho: 1 por passo, mais o dano de hazard nas casas
    # de hazard sem comida. Sem hazards, é igual a dist.
    cost: int


@dataclass(frozen=True)
class TurnSnapshot:
    """Tudo o que não depende da direção, calculado uma vez por jogada."""
    head: Pos
    rivals: list[Snake]
    obstacles: set[Pos]
    # obstáculos + casas vizinhas às cabeças de rivais estritamente maiores
    blocked: set[Pos]
    free_cells: int
    center: Pos
    target: FoodTarget | None
    # rival estritamente menor mais próxima, ou None
    prey: Snake | None
    # O tabuleiro em índices e a ocupação temporal base (sem o crescimento
    # da própria cobra, que depende da candidata).
    board: BoardState
    free_after: list[int]
    # Índices das casas vizinhas às cabeças de rivais estritamente maiores:
    # as únicas bloqueadas de vez nas buscas temporais.
    threats: frozenset[int]
    # Dona de cada casa no território do turno, ou None.
    owner: list[str | None]


def rivals_of(state: GameState) -> list[Snake]:
    """As adversárias vivas, na ordem do tabuleiro."""
    return [snake for snake in state.board.snakes if snake.id != state.you.id]


def turn_territory(board: BoardState, free_after: list[int]) -> list[str | None]:
    """Dona de cada casa no território temporal do turno: a semente de cada
    cobra viva é a cabeça atual, com distância 0.
    """
    seeds = {s.id: (s.head, 0) for s in board.snakes if s.alive}
    return temporal_voronoi(board, free_after, seeds)[1]


def path_cost(board: BoardState, path: list[int]) -> int:
    """Custo de vida de andar o caminho: 1 por passo, mais o dano de hazard
    (uma vez por ocorrência) nas casas de hazard sem comida.
    """
    damage = board.hazard_damage
    cost = 0
    for cell in path[1:]:
        cost += 1
        if cell not in board.food:
            cost += damage * board.hazards.get(cell, 0)
    return cost


def target_food(
    state: GameState,
    blocked: set[Pos],
    board: BoardState | None = None,
    free_after: list[int] | None = None,
    owner: list[str | None] | None = None,
) -> FoodTarget | None:
    """Comida alvo da jogada, ou None se nenhuma for alcançável.

    O caminho é o A* temporal da cabeça atual, sem passar por blocked. É a
    mais próxima entre as comidas que são minhas no território do turno; se
    nenhuma for, a mais próxima alcançável. Empate: a primeira da lista.

    board, free_after e owner são calculados aqui quando não vêm.
    """
    you = state.you
    board = board or from_game(state)
    if free_after is None:
        free_after = base_free_after(board, you.id)
    if owner is None:
        owner = turn_territory(board, free_after)
    w = board.width
    head = idx(you.head.x, you.head.y, w)
    blocked_idx = {idx(x, y, w) for x, y in blocked if 0 <= x < w and 0 <= y < board.height}

    mine: FoodTarget | None = None
    nearest: FoodTarget | None = None
    for coord in state.board.food:
        food = idx(coord.x, coord.y, w)
        path = temporal_a_star(board, free_after, head, 0, food, blocked_idx)
        if not path:
            continue
        candidate = FoodTarget(
            pos(coord), len(path) - 1, [xy(c, w) for c in path], path_cost(board, path)
        )
        # Comparação estrita: no empate fica a que veio antes na lista.
        if nearest is None or candidate.dist < nearest.dist:
            nearest = candidate
        if owner[food] == you.id and (mine is None or candidate.dist < mine.dist):
            mine = candidate
    return mine or nearest


def snapshot(state: GameState, board: BoardState | None = None) -> TurnSnapshot:
    """Lê o turno: obstáculos, ameaças, ocupação temporal, território,
    comida alvo e presa. board é o BoardState da jogada, se já existir.
    """
    you = state.you
    board = board or from_game(state)
    head = pos(you.head)
    rivals = rivals_of(state)
    obs = obstacles(state.board)
    zones = threat_zones(state.board, you)
    free_after = base_free_after(board, you.id)
    owner = turn_territory(board, free_after)
    smaller = [r for r in rivals if r.length < you.length]
    # min() fica com a primeira do tabuleiro num empate de distância.
    prey = min(smaller, key=lambda r: manhattan(head, pos(r.head)), default=None)
    return TurnSnapshot(
        head=head,
        rivals=rivals,
        obstacles=obs,
        blocked=obs | zones,
        free_cells=max(1, board.width * board.height - len(obs)),
        center=(board.width // 2, board.height // 2),
        target=target_food(state, zones, board, free_after, owner),
        prey=prey,
        board=board,
        free_after=free_after,
        threats=frozenset(idx(x, y, board.width) for x, y in zones),
        owner=owner,
    )


# --- Política de fome ---

def starving(health: int, target: FoodTarget | None) -> bool:
    """Sobrevivência: a vida não dá folga para chegar até a comida alvo,
    contando o dano dos hazards no caminho.
    """
    if target is None:
        return health < config.NO_PATH_HEALTH
    return health < target.cost + config.HEALTH_MARGIN


def outsized(length: int, rivals: list[Snake]) -> bool:
    """Disputa de tamanho: ainda não está LENGTH_LEAD à frente da maior rival."""
    if not rivals:
        return False
    return length < max(r.length for r in rivals) + config.LENGTH_LEAD


def behind_schedule(length: int, turn: int) -> bool:
    """Taxa de crescimento: ao menos uma comida a cada FEED_INTERVAL turnos."""
    return length < config.START_LENGTH + turn // config.FEED_INTERVAL


def hunger_reasons(state: GameState, snap: TurnSnapshot | None = None) -> list[str]:
    """Os critérios de fome que dispararam nesta jogada; vazia é sem fome."""
    snap = snap or snapshot(state)
    you = state.you
    criteria = {
        "starving": starving(you.health, snap.target),
        "outsized": outsized(you.length, snap.rivals),
        "behind_schedule": behind_schedule(you.length, state.turn),
    }
    return [name for name, hit in criteria.items() if hit]


def build_context(state: GameState, snap: TurnSnapshot | None = None) -> DecisionContext:
    """Contexto da jogada para a decisão: vida, tamanho, turno e fome."""
    snap = snap or snapshot(state)
    you = state.you
    return DecisionContext(
        health=you.health,
        length=you.length,
        turn=state.turn,
        hungry=bool(hunger_reasons(state, snap)),
    )


# --- Medições por direção ---

def trapped_rivals(state: GameState, snap: TurnSnapshot, new_head: Pos) -> tuple[str, ...]:
    """Rivais que ficam sem espaço para o próprio corpo depois do meu passo.

    A área da rival é o maior flood fill entre as casas vizinhas à cabeça
    dela, com a minha nova cabeça virando obstáculo. Uma única rotulagem de
    regiões atende todas as saídas de todas as rivais: cada região livre é
    percorrida uma vez, em vez de um flood fill por saída.
    """
    board = state.board
    sizes = region_sizes(board, snap.obstacles | {new_head})
    trapped = []
    for rival in snap.rivals:
        exits = neighbors(board, pos(rival.head), set())
        rival_area = max((sizes(cell) for cell in exits), default=0)
        if rival_area < rival.length:
            trapped.append(rival.id)
    return tuple(trapped)


def biggest_rival(board: BoardState, me: str) -> str | None:
    """Id da maior rival viva pelo tamanho; no empate, a primeira do tabuleiro."""
    best = None
    for s in board.snakes:
        if s.id != me and s.alive and (best is None or s.length > best.length):
            best = s
    return best.id if best else None


def evaluate_moves(
    state: GameState,
    candidates: list[str],
    snap: TurnSnapshot | None = None,
    deadline=None,
) -> list[MoveFeatures]:
    """Uma MoveFeatures por candidata, na mesma ordem. Não decide nada.

    deadline (clock.Deadline) limita a DFS de sobrevivência; sem ele, ela
    só para pelos limites de profundidade e de nós.
    """
    snap = snap or snapshot(state)
    board, you = snap.board, state.you
    me = board.snake(you.id)
    head = snap.head
    target = snap.target
    w = board.width
    target_idx = idx(*target.pos, w) if target is not None else None
    biggest = biggest_rival(board, you.id)

    features = []
    for direction in candidates:
        new_head = step(head, direction)
        cell = idx(*new_head, w)
        # Se a candidata come, o meu corpo para de encurtar por um turno.
        free_after = (
            with_growth(snap.free_after, me) if cell in board.food else snap.free_after
        )
        # A nova cabeça não fica bloqueada: uma candidata pode cair numa
        # casa vizinha a uma rival maior e ainda assim ter espaço.
        blocked = snap.threats - {cell}
        area = temporal_area(board, free_after, cell, 1, blocked)
        depth, survives, _ = survival(board, snap.free_after, me, direction, deadline)

        seeds = {you.id: (cell, 1)}
        for rival in board.snakes:
            if rival.id != you.id and rival.alive:
                seeds[rival.id] = (rival.head, 0)
        counts, owner = temporal_voronoi(board, free_after, seeds)

        food_step = False
        food_dist = None
        if target is not None:
            food_step = len(target.path) >= 2 and target.path[1] == new_head
            path = temporal_a_star(board, free_after, cell, 1, target_idx, blocked)
            food_dist = len(path) - 1 if path else None

        hunt_step = snap.prey is not None and (
            manhattan(new_head, pos(snap.prey.head)) < manhattan(head, pos(snap.prey.head))
        )

        features.append(MoveFeatures(
            move=direction,
            risky=would_lose_head_to_head(state.board, you, new_head),
            area=area,
            roomy=area >= you.length or survives,
            territory_pct=100 * counts[you.id] / snap.free_cells,
            food_step=food_step,
            food_dist=food_dist,
            trapped_rivals=trapped_rivals(state, snap, new_head),
            kill_chance=any(
                r.length < you.length and manhattan(pos(r.head), new_head) == 1
                for r in snap.rivals
            ),
            hunt_step=hunt_step,
            danger=any(
                r.length >= you.length and manhattan(pos(r.head), new_head) == 2
                for r in snap.rivals
            ),
            center_dist=manhattan(new_head, snap.center),
            survival_depth=depth,
            survives=survives,
            hazard=(
                board.hazard_damage > 0 and cell in board.hazards and cell not in board.food
            ),
            rival_territory_pct=(
                100 * counts[biggest] / snap.free_cells if biggest is not None else 0.0
            ),
            food_owned=target_idx is not None and owner[target_idx] == you.id,
        ))
    return features
