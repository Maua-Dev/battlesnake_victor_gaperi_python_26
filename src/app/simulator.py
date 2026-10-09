"""Simulador de turno do modo standard, para a busca do duelo.

Segue as regras oficiais (standard.go), nesta ordem:
https://github.com/BattlesnakeOfficial/rules/blob/main/standard.go
  1. movimento: nova cabeça na direção dada, último segmento sai;
  2. fome: 1 de vida a menos;
  3. hazard: o dano, uma vez por ocorrência da casa, se ela não tem comida;
  4. alimentação: a comida sob uma cabeça sai, e quem comeu volta a 100 de
     vida e cresce (o último segmento se repete);
  5. eliminação em duas fases: primeiro vida 0 e cabeça fora do tabuleiro;
     depois, todas de uma vez, as colisões com corpos (já depois da
     alimentação, só das cobras que sobraram) e os cabeça a cabeça perdidos.

Não gera comida nova. Não altera o estado recebido.
"""
from .board_state import BoardState, MOVE_ORDER, OFF_BOARD, SnakeState

_DIRECTION = {move: i for i, move in enumerate(MOVE_ORDER)}


def step(board: BoardState, moves: dict[str, str]) -> BoardState:
    """O tabuleiro depois de um turno, com um movimento por cobra viva.

    As cobras eliminadas continuam na tupla, com alive=False; o corpo delas
    não é usado por mais ninguém. As já eliminadas não mudam.
    """
    steps = board.steps
    food = board.food
    hazards = board.hazards
    damage = board.hazard_damage

    # 1 a 4: movimento, fome, hazard e alimentação. bodies[i] fica None para
    # quem já estava eliminada e para quem saiu do tabuleiro.
    bodies: list[tuple[int, ...] | None] = []
    healths: list[int] = []
    eaten = set()
    for s in board.snakes:
        if not s.alive:
            bodies.append(None)
            healths.append(s.health)
            continue
        head = steps[s.head][_DIRECTION[moves[s.id]]]
        health = s.health - 1
        if head == OFF_BOARD:
            bodies.append(None)
            healths.append(health)
            continue
        body = (head,) + s.body[:-1]
        if head in food:
            eaten.add(head)
            health = 100
            body += (body[-1],)
        elif head in hazards:
            health = max(0, health - damage * hazards[head])
        bodies.append(body)
        healths.append(health)

    # 5a: vida zerada ou cabeça fora do tabuleiro.
    survivors = [
        i for i, body in enumerate(bodies) if body is not None and healths[i] > 0
    ]

    # 5b: colisões, todas marcadas juntas, contra quem passou da fase 5a.
    body_cells: dict[int, int] = {}
    for i in survivors:
        for cell in bodies[i][1:]:
            body_cells[cell] = body_cells.get(cell, 0) + 1
    dead = set()
    for i in survivors:
        head = bodies[i][0]
        if head in body_cells:
            dead.add(i)
            continue
        size = len(bodies[i])
        for j in survivors:
            if j != i and bodies[j][0] == head and size <= len(bodies[j]):
                dead.add(i)
                break

    alive_now = set(survivors) - dead
    snakes = []
    for i, s in enumerate(board.snakes):
        if not s.alive:
            snakes.append(s)
        elif i in alive_now:
            snakes.append(SnakeState(s.id, bodies[i], healths[i]))
        else:
            # Eliminada neste turno: o corpo fica o de antes (uma cabeça
            # fora do tabuleiro não tem índice).
            snakes.append(SnakeState(s.id, s.body, healths[i], alive=False))
    return BoardState(
        width=board.width,
        height=board.height,
        snakes=tuple(snakes),
        food=food - eaten if eaten else food,
        hazards=hazards,
        hazard_damage=damage,
    )


def occupied_after_turn(board: BoardState) -> set[int]:
    """As casas que continuam ocupadas depois do turno, qualquer que seja o
    movimento das cobras: todo segmento menos o último de cada cobra viva.

    Pelas regras oficiais, o último segmento sai do lugar antes da
    alimentação, então a cauda fica livre mesmo que a cobra coma. Uma cauda
    empilhada (logo depois de comer) continua ocupada, porque o penúltimo
    segmento está na mesma casa. É a regra do filtro de logic.get_move e de
    safe_moves, para que os dois não divirjam.
    """
    occupied = set()
    for s in board.snakes:
        if s.alive:
            occupied.update(s.body[:-1])
    return occupied


def safe_moves(board: BoardState, snake_id: str) -> list[str]:
    """As direções que não são morte certa para a cobra, na ordem canônica.

    Ficam fora: sair do tabuleiro, o pescoço e as casas de
    occupied_after_turn. Sem nenhuma direção, devolve a primeira da ordem
    canônica, que elimina a cobra.
    """
    me = board.snake(snake_id)
    occupied = occupied_after_turn(board)
    neck = me.body[1] if me.length > 1 and me.body[1] != me.head else None
    result = []
    for move, cell in zip(MOVE_ORDER, board.steps[me.head]):
        if cell != OFF_BOARD and cell != neck and cell not in occupied:
            result.append(move)
    return result or [MOVE_ORDER[0]]
