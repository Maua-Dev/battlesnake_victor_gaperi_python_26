"""Utilitários de tabuleiro usados pelas regras da cobra.

O Coord do Pydantic não é hasheável, então tudo aqui trabalha com tuplas
(x, y) — o tipo Pos — e a conversão fica concentrada em pos().
"""
from .models import Board, Coord, Snake

Pos = tuple[int, int]

# A ordem deste dict é a ordem canônica dos movimentos: em qualquer empate,
# vence a primeira direção. Lembre que up é y+1 (origem no canto inferior esquerdo).
MOVES: dict[str, Pos] = {
    "up": (0, 1),
    "down": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}


def pos(coord: Coord) -> Pos:
    """Converte um Coord do Pydantic em tupla (x, y)."""
    return (coord.x, coord.y)


def step(p: Pos, direction: str) -> Pos:
    """Casa vizinha de p na direção dada."""
    dx, dy = MOVES[direction]
    return (p[0] + dx, p[1] + dy)


def in_bounds(board: Board, p: Pos) -> bool:
    """Diz se p está dentro do tabuleiro."""
    return 0 <= p[0] < board.width and 0 <= p[1] < board.height


def manhattan(a: Pos, b: Pos) -> int:
    """Distância de Manhattan entre duas casas."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def occupied(board: Board) -> set[Pos]:
    """Todas as casas ocupadas por alguma cobra, inclusive a sua."""
    return {pos(segment) for snake in board.snakes for segment in snake.body}


def tail_moves(snake: Snake) -> bool:
    """Diz se a cauda sai do lugar neste turno.

    Logo depois de comer, os dois últimos segmentos ocupam a mesma casa e a
    cauda fica parada. Numa cobra de tamanho 1 a cauda é a própria cabeça,
    que tratamos como ocupada.
    """
    return len(snake.body) > 1 and snake.body[-1] != snake.body[-2]


def obstacles(board: Board) -> set[Pos]:
    """Casas ocupadas por qualquer cobra, menos as caudas que saem do lugar."""
    result = set()
    for snake in board.snakes:
        body = snake.body[:-1] if tail_moves(snake) else snake.body
        result.update(pos(segment) for segment in body)
    return result


def neighbors(board: Board, p: Pos, blocked: set[Pos]) -> list[Pos]:
    """Vizinhos de p dentro do tabuleiro e fora de blocked, na ordem de MOVES."""
    result = []
    for direction in MOVES:
        n = step(p, direction)
        if in_bounds(board, n) and n not in blocked:
            result.append(n)
    return result


def would_lose_head_to_head(board: Board, you: Snake, target: Pos) -> bool:
    """Diz se entrar em target arrisca um cabeça a cabeça perdido.

    Perde (ou empata, o que mata as duas) quem não for estritamente maior,
    então contam as rivais de tamanho maior OU IGUAL cuja cabeça alcança
    target no próximo turno.
    """
    for snake in board.snakes:
        if snake.id == you.id or snake.length < you.length:
            continue
        if manhattan(pos(snake.head), target) == 1:
            return True
    return False


def nearest_food(board: Board, origin: Pos) -> Pos | None:
    """Comida de menor distância de Manhattan até origin.

    Em empate fica a primeira da lista recebida; sem comida, devolve None.
    """
    if not board.food:
        return None
    return min((pos(f) for f in board.food), key=lambda f: manhattan(origin, f))


def threat_zones(board: Board, you: Snake) -> set[Pos]:
    """Casas (dentro do tabuleiro) vizinhas às cabeças das rivais
    ESTRITAMENTE maiores, onde elas podem aparecer no próximo turno.
    """
    zones = set()
    for snake in board.snakes:
        if snake.id == you.id or snake.length <= you.length:
            continue
        zones.update(neighbors(board, pos(snake.head), set()))
    return zones
