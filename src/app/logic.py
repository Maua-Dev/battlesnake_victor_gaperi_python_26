# Bem-vindo ao
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \   __\   __\  | _/ __ \ /  ___//    \__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  | |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\_____>
#
# ESTE É O ARQUIVO QUE VOCÊ VAI EDITAR. Todo o resto do projeto existe
# só para levar o estado do jogo até as quatro funções abaixo.
#
# Para começar, já deixamos pronta a lógica que impede a sua cobra de andar
# para trás (ela morreria na hora). Os TODOs marcam os próximos passos.
# Documentação: https://docs.battlesnake.com

import random
import logging
from .models import Board, GameState, MoveResponse, Snake
from .grid import (
    Pos, pos, step, manhattan, occupied, opponent_cells,
    would_lose_head_to_head, threat_zones, nearest_food,
)
from .floodfill import flood_fill
from .astar import a_star

logger = logging.getLogger(__name__)
# O runtime Python da Lambda deixa o logger raiz em WARNING: sem esta linha
# as jogadas nao aparecem no CloudWatch.
logger.setLevel(logging.INFO)

# Abaixo desta vida a cobra passa a ir atrás de comida.
HUNGER_THRESHOLD = 80


def info() -> dict:
    """GET / — chamado quando você cadastra a cobra e a cada partida.
    Controla a aparência dela.
    Opções de cabeça, cauda e cor: https://docs.battlesnake.com/guides/customizations
    """
    logger.info("INFO")

    return {
        "apiversion": "1",
        "author": "gasperi",
        "color": "#E80978",
        "head": "tiger-king",
        "tail": "tiger-tail",
        "version": "1.0.0",
    }


def start(state: GameState) -> None:
    """POST /start — chamado uma vez, quando a partida começa.
    Bom lugar para preparar qualquer estado inicial.
    """
    logger.info("JOGO COMEÇOU (partida %s)", state.game.id)


def end(state: GameState) -> None:
    """POST /end — chamado uma vez, quando a partida termina."""
    logger.info("FIM DE JOGO após %d turnos", state.turn)


def get_move(state: GameState) -> MoveResponse:
    """POST /move — chamado a cada turno. Aqui mora a inteligência da sua cobra.
    Precisa devolver "up", "down", "left" ou "right".
    Exemplo do JSON recebido: https://docs.battlesnake.com/api/example-move
    """
    is_move_safe: dict[str, bool] = {
        "up": True,
        "down": True,
        "left": True,
        "right": True,
    }

    # --- Impedir que a cobra ande para trás (já implementado) ---
    # O pescoço é a parte do corpo logo atrás da cabeça. Voltar por cima dele
    # é morte certa, então marcamos aquela direção como insegura.
    my_head = state.you.body[0]
    my_neck = state.you.body[1] if len(state.you.body) >= 2 else None

    if my_neck is not None:
        if my_neck.x < my_head.x:
            # pescoço à esquerda da cabeça -> não vá para a esquerda
            is_move_safe["left"] = False
        elif my_neck.x > my_head.x:
            # pescoço à direita da cabeça -> não vá para a direita
            is_move_safe["right"] = False
        elif my_neck.y < my_head.y:
            # pescoço abaixo da cabeça -> não desça
            is_move_safe["down"] = False
        elif my_neck.y > my_head.y:
            # pescoço acima da cabeça -> não suba
            is_move_safe["up"] = False

    # 2. Impedir que a cobra saia do tabuleiro (paredes)
    board_width = state.board.width
    board_height = state.board.height

    if my_head.x + 1 >= board_width:
        is_move_safe["right"] = False
    if my_head.x - 1 < 0:
        is_move_safe["left"] = False
    if my_head.y + 1 >= board_height:
        is_move_safe["up"] = False
    if my_head.y - 1 < 0:
        is_move_safe["down"] = False

    # 3. Impedir que a cobra bata no próprio corpo
    my_body = state.you.body
    # A cauda anda junto com a cabeça, então a casa dela fica livre neste
    # turno. O bloco do pescoço, lá em cima, continua barrando a meia-volta.
    my_tail = my_body[-1]
    for segment in my_body:
        if segment == my_tail:
            continue
        if segment.x == my_head.x + 1 and segment.y == my_head.y:
            is_move_safe["right"] = False
        if segment.x == my_head.x - 1 and segment.y == my_head.y:
            is_move_safe["left"] = False
        if segment.x == my_head.x and segment.y == my_head.y + 1:
            is_move_safe["up"] = False
        if segment.x == my_head.x and segment.y == my_head.y - 1:
            is_move_safe["down"] = False

    # 4. Impedir que a cobra bata nas adversárias (a cauda delas continua
    # bloqueada: se a rival comer neste turno, a cauda não sai do lugar)
    head = pos(my_head)
    rivals = opponent_cells(state.board, state.you)
    for direction in is_move_safe:
        if is_move_safe[direction] and step(head, direction) in rivals:
            is_move_safe[direction] = False

    # 5. Evitar cabeça a cabeça com rivais de tamanho maior ou igual
    for direction in is_move_safe:
        if is_move_safe[direction] and would_lose_head_to_head(
            state.board, state.you, step(head, direction)
        ):
            is_move_safe[direction] = False

    # Sobrou alguma direção segura?
    safe_moves = [direction for direction, safe in is_move_safe.items() if safe]

    if not safe_moves:
        # Emergência: todas as direções são perigosas.
        # Escolhemos uma ao acaso entre as 4 — melhor do que travar.
        all_moves = ["up", "down", "left", "right"]
        fallback = random.choice(all_moves)
        logger.info("MOVE %d: sem saída! emergência -> %s", state.turn, fallback)
        return MoveResponse(move=fallback)

    # Escolhe, entre as direções seguras, a melhor segundo a estratégia.
    chosen = choose_move(state, safe_moves)

    logger.debug("MOVE %d: %s", state.turn, chosen)
    return MoveResponse(move=chosen)


def choose_move(state: GameState, safe_moves: list[str]) -> str:
    """Escolhe uma direção dentre safe_moves (que nunca chega vazia)."""
    head = pos(state.you.body[0])
    hungry = state.you.health < HUNGER_THRESHOLD
    food = nearest_food(state.board, head)

    my_obstacles = obstacles(state.board, state.you)

    if hungry and food is not None:
        # Com fome: segue o primeiro passo do caminho A* até a comida, desde
        # que esse passo seja uma direção segura. Senão, cai no flood fill.
        path = a_star(state.board, head, food, my_obstacles)
        if len(path) >= 2:
            for direction in safe_moves:
                if step(head, direction) == path[1]:
                    return direction

    # Flood fill: fica a direção que deixa mais espaço livre pela frente.
    blocked = my_obstacles | threat_zones(state.board, state.you)
    best_move = safe_moves[0]
    best_score = None
    for direction in safe_moves:
        new_head = step(head, direction)
        # A nova cabeça não entra em blocked: senão uma direção segura que
        # cai numa threat_zone teria área 0 mesmo havendo espaço.
        area = flood_fill(state.board, new_head, blocked - {new_head})
        tiebreak = 0
        if hungry and food is not None:
            closest = nearest_food(state.board, new_head)
            tiebreak = 100 - manhattan(new_head, closest)
        score = (area, tiebreak)
        # Comparação estrita: num empate total fica a primeira direção.
        if best_score is None or score > best_score:
            best_move, best_score = direction, score
    return best_move


def obstacles(board: Board, you: Snake) -> set[Pos]:
    """Casas ocupadas por qualquer cobra, menos a própria cauda (que anda junto)."""
    return occupied(board) - {pos(you.body[-1])}
