"""Características: o que a cobra mede em cada direção candidata.

Nada aqui escolhe um movimento. evaluate_moves devolve uma MoveFeatures por
candidata e build_context monta o DecisionContext. Os dois entram em
decision.decide, que no futuro será trocada por um modelo de decisão externo.
"""
from dataclasses import dataclass

from . import config
from .astar import a_star
from .decision import DecisionContext, MoveFeatures
from .floodfill import flood_fill
from .grid import (
    Pos, pos, step, manhattan, neighbors, obstacles, threat_zones,
    would_lose_head_to_head,
)
from .models import GameState, Snake
from .voronoi import voronoi


@dataclass(frozen=True)
class FoodTarget:
    """A comida alvo e o caminho A* da cabeça atual até ela."""
    pos: Pos
    dist: int
    path: list[Pos]


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


def rivals_of(state: GameState) -> list[Snake]:
    """As adversárias vivas, na ordem do tabuleiro."""
    return [snake for snake in state.board.snakes if snake.id != state.you.id]


def target_food(state: GameState, blocked: set[Pos]) -> FoodTarget | None:
    """Comida alvo da jogada, ou None se nenhuma for alcançável.

    É a mais próxima (pelo A*) que a cobra alcança ANTES de toda rival de
    tamanho maior ou igual, medida pela Manhattan da cabeça da rival. Se
    nenhuma for "minha", a mais próxima alcançável. Empate: a primeira da lista.
    """
    you = state.you
    head = pos(you.head)
    threats = [r for r in rivals_of(state) if r.length >= you.length]
    mine: FoodTarget | None = None
    nearest: FoodTarget | None = None
    for coord in state.board.food:
        food = pos(coord)
        path = a_star(state.board, head, food, blocked)
        if not path:
            continue
        candidate = FoodTarget(food, len(path) - 1, path)
        # Comparação estrita: no empate fica a que veio antes na lista.
        if nearest is None or candidate.dist < nearest.dist:
            nearest = candidate
        if all(candidate.dist < manhattan(pos(r.head), food) for r in threats):
            if mine is None or candidate.dist < mine.dist:
                mine = candidate
    return mine or nearest


def snapshot(state: GameState) -> TurnSnapshot:
    """Lê o turno: obstáculos, ameaças, comida alvo e presa."""
    board, you = state.board, state.you
    head = pos(you.head)
    rivals = rivals_of(state)
    obs = obstacles(board)
    blocked = obs | threat_zones(board, you)
    smaller = [r for r in rivals if r.length < you.length]
    # min() fica com a primeira do tabuleiro num empate de distância.
    prey = min(smaller, key=lambda r: manhattan(head, pos(r.head)), default=None)
    return TurnSnapshot(
        head=head,
        rivals=rivals,
        obstacles=obs,
        blocked=blocked,
        free_cells=max(1, board.width * board.height - len(obs)),
        center=(board.width // 2, board.height // 2),
        target=target_food(state, blocked),
        prey=prey,
    )


# --- Política de fome ---

def starving(health: int, target: FoodTarget | None) -> bool:
    """Sobrevivência: a vida não dá folga para chegar até a comida alvo."""
    if target is None:
        return health < config.NO_PATH_HEALTH
    return health < target.dist + config.HEALTH_MARGIN


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
    dela, com a minha nova cabeça virando obstáculo.
    """
    board = state.board
    sim = snap.obstacles | {new_head}
    trapped = []
    for rival in snap.rivals:
        exits = neighbors(board, pos(rival.head), set())
        rival_area = max((flood_fill(board, cell, sim) for cell in exits), default=0)
        if rival_area < rival.length:
            trapped.append(rival.id)
    return tuple(trapped)


def evaluate_moves(
    state: GameState,
    candidates: list[str],
    snap: TurnSnapshot | None = None,
) -> list[MoveFeatures]:
    """Uma MoveFeatures por candidata, na mesma ordem. Não decide nada."""
    snap = snap or snapshot(state)
    board, you = state.board, state.you
    head = snap.head
    target = snap.target

    features = []
    for direction in candidates:
        new_head = step(head, direction)
        # A nova cabeça não entra em blocked: uma candidata pode cair numa
        # threat_zone e ainda assim ter espaço.
        free = snap.blocked - {new_head}
        area = flood_fill(board, new_head, free)

        seeds = {you.id: (new_head, 1)}
        for rival in snap.rivals:
            seeds[rival.id] = (pos(rival.head), 0)
        territory = voronoi(board, seeds, snap.obstacles)[you.id]

        food_step = False
        food_dist = None
        if target is not None:
            food_step = len(target.path) >= 2 and target.path[1] == new_head
            path = a_star(board, new_head, target.pos, free)
            food_dist = len(path) - 1 if path else None

        hunt_step = snap.prey is not None and (
            manhattan(new_head, pos(snap.prey.head)) < manhattan(head, pos(snap.prey.head))
        )

        features.append(MoveFeatures(
            move=direction,
            risky=would_lose_head_to_head(board, you, new_head),
            area=area,
            roomy=area >= you.length,
            territory_pct=100 * territory / snap.free_cells,
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
        ))
    return features
