"""Representação leve do tabuleiro, para os laços quentes.

Cada casa (x, y) vira o índice `y * largura + x`. O GameState é lido uma
única vez por jogada (from_game), e a ocupação temporal, a sobrevivência, o
simulador e a busca trabalham só sobre BoardState, sem objetos Pydantic.

Este módulo não importa models.py: lê o estado por duck typing, para que
simulator, search e occupancy fiquem sem Pydantic na árvore de imports.
"""
from dataclasses import dataclass
from functools import lru_cache

# A mesma ordem canônica de grid.MOVES e decision.MOVE_ORDER.
MOVE_ORDER = ("up", "down", "left", "right")
_DELTAS = ((0, 1), (0, -1), (-1, 0), (1, 0))

# Casa fora do tabuleiro em step_table.
OFF_BOARD = -1


def idx(x: int, y: int, w: int) -> int:
    """Índice da casa (x, y) num tabuleiro de largura w."""
    return y * w + x


def xy(i: int, w: int) -> tuple[int, int]:
    """Casa (x, y) do índice i num tabuleiro de largura w."""
    return (i % w, i // w)


@lru_cache(maxsize=None)
def step_table(w: int, h: int) -> tuple[tuple[int, ...], ...]:
    """Para cada índice, o vizinho em cada direção de MOVE_ORDER, ou
    OFF_BOARD quando a direção sai do tabuleiro.
    """
    table = []
    for i in range(w * h):
        x, y = xy(i, w)
        row = []
        for dx, dy in _DELTAS:
            nx, ny = x + dx, y + dy
            row.append(idx(nx, ny, w) if 0 <= nx < w and 0 <= ny < h else OFF_BOARD)
        table.append(tuple(row))
    return tuple(table)


@lru_cache(maxsize=None)
def neighbor_table(w: int, h: int) -> tuple[tuple[int, ...], ...]:
    """Para cada índice, os vizinhos dentro do tabuleiro, na ordem canônica.

    Calculada uma vez por tamanho de tabuleiro e reaproveitada.
    """
    return tuple(
        tuple(n for n in row if n != OFF_BOARD) for row in step_table(w, h)
    )


@dataclass(frozen=True, slots=True)
class SnakeState:
    """Uma cobra: corpo em índices (cabeça primeiro, repetições mantidas)."""
    id: str
    body: tuple[int, ...]
    health: int
    alive: bool = True

    @property
    def head(self) -> int:
        return self.body[0]

    @property
    def length(self) -> int:
        return len(self.body)


@dataclass(frozen=True, slots=True)
class BoardState:
    """O tabuleiro de uma jogada, ou de um turno simulado."""
    width: int
    height: int
    snakes: tuple[SnakeState, ...]
    food: frozenset[int]
    # índice -> quantas vezes a casa aparece na lista de hazards; o dano é
    # aplicado uma vez por ocorrência.
    hazards: dict[int, int]
    hazard_damage: int

    @property
    def size(self) -> int:
        return self.width * self.height

    @property
    def neighbors(self) -> tuple[tuple[int, ...], ...]:
        return neighbor_table(self.width, self.height)

    @property
    def steps(self) -> tuple[tuple[int, ...], ...]:
        return step_table(self.width, self.height)

    def snake(self, snake_id: str) -> SnakeState:
        """A cobra com esse id."""
        for s in self.snakes:
            if s.id == snake_id:
                return s
        raise KeyError(snake_id)

    def manhattan(self, a: int, b: int) -> int:
        """Distância de Manhattan entre dois índices."""
        w = self.width
        return abs(a % w - b % w) + abs(a // w - b // w)


def hazard_damage(ruleset) -> int:
    """Dano de hazard por turno, de settings.hazardDamagePerTurn.

    Ausente ou inválido (inclusive bool) vale 0: nenhum valor é assumido.
    """
    settings = ruleset.get("settings") if isinstance(ruleset, dict) else None
    value = settings.get("hazardDamagePerTurn") if isinstance(settings, dict) else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def from_game(state) -> BoardState:
    """A única leitura do GameState na jogada."""
    board = state.board
    w = board.width

    def to_idx(coord) -> int:
        return idx(coord.x, coord.y, w)

    hazards: dict[int, int] = {}
    for coord in board.hazards:
        i = to_idx(coord)
        hazards[i] = hazards.get(i, 0) + 1
    return BoardState(
        width=w,
        height=board.height,
        snakes=tuple(
            SnakeState(s.id, tuple(to_idx(c) for c in s.body), s.health)
            for s in board.snakes
        ),
        food=frozenset(to_idx(c) for c in board.food),
        hazards=hazards,
        hazard_damage=hazard_damage(state.game.ruleset),
    )
