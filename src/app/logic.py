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
from collections import Counter

from . import board_state, clock, config, search, telemetry
from .board_state import hazard_damage
from .models import GameState, MoveResponse
from .grid import pos, step, opponent_cells, tail_moves
from .features import snapshot, build_context, evaluate_moves
from .decision import explain


def info() -> dict:
    """GET / — chamado quando você cadastra a cobra e a cada partida.
    Controla a aparência dela.
    Opções de cabeça, cauda e cor: https://docs.battlesnake.com/guides/customizations
    """
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


def end(state: GameState) -> None:
    """POST /end — chamado uma vez, quando a partida termina."""


def get_move(state: GameState, started_at: float | None = None) -> MoveResponse:
    """POST /move — chamado a cada turno. Aqui mora a inteligência da sua cobra.
    Precisa devolver "up", "down", "left" ou "right".
    Exemplo do JSON recebido: https://docs.battlesnake.com/api/example-move

    started_at é o instante de chegada do /move (clock.now(), marcado no
    middleware de main.py); sem ele, o prazo começa agora.

    Emite um evento move por chamada (docs/logs.md).
    """
    if started_at is None:
        started_at = clock.now()
    deadline = clock.Deadline(started_at, clock.budget_ms(state.game.timeout))

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
    # turno, exceto logo depois de comer (cauda empilhada, ver tail_moves).
    # O bloco do pescoço, lá em cima, continua barrando a meia-volta.
    my_tail = my_body[-1]
    free_tail = tail_moves(state.you)
    for segment in my_body:
        if free_tail and segment == my_tail:
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

    # 5. Impedir que a cobra morra de fome ou num hazard. As regras oficiais
    # do modo standard rodam nesta ordem: movimento, perda de 1 de vida,
    # dano de hazard (que não vale numa casa com comida), alimentação e só
    # então as eliminações. Então, sem comida no destino, a vida que sobra é
    # vida - 1 - dano × (vezes que a casa aparece na lista de hazards).
    # https://github.com/BattlesnakeOfficial/rules/blob/main/standard.go
    damage = hazard_damage(state.game.ruleset)
    food = {pos(f) for f in state.board.food}
    hazards = Counter(pos(h) for h in state.board.hazards)
    for direction in is_move_safe:
        target = step(head, direction)
        if not is_move_safe[direction] or target in food:
            continue
        if state.you.health - 1 - damage * hazards[target] <= 0:
            is_move_safe[direction] = False

    # O cabeça a cabeça com rival maior ou igual não elimina a direção: ele
    # só a marca como arriscada (MoveFeatures.risky), e a decisão prefere as
    # não arriscadas. Um cabeça a cabeça incerto é melhor que um beco certo.

    # Sobrou alguma direção segura?
    safe_moves = [direction for direction, safe in is_move_safe.items() if safe]

    if not safe_moves:
        # Emergência: todas as direções são perigosas.
        # Escolhemos uma ao acaso entre as 4 — melhor do que travar.
        all_moves = ["up", "down", "left", "right"]
        move = random.choice(all_moves)
    else:
        # Escolhe, entre as direções seguras, a melhor segundo a estratégia.
        move = choose_move(state, safe_moves, deadline=deadline)

    telemetry.log_move(state, move)
    return MoveResponse(move=move)


def choose_move(
    state: GameState,
    safe_moves: list[str],
    deadline: clock.Deadline | None = None,
) -> str:
    """Escolhe uma direção dentre safe_moves (que nunca chega vazia).

    Três etapas: safe_moves são as candidatas, evaluate_moves mede cada uma e
    explain (a decide com o porquê) escolhe só a partir dessas medições e do
    contexto. Essa escolha heurística fica pronta primeiro. Depois, num
    duelo e se o prazo ainda não passou, a busca pode substituí-la, mas só
    com o resultado de uma profundidade que terminou dentro do prazo.
    """
    if deadline is None:
        deadline = clock.Deadline(clock.now(), clock.budget_ms(state.game.timeout))
    board = board_state.from_game(state)
    snap = snapshot(state, board)
    ctx = build_context(state, snap)
    features = evaluate_moves(state, safe_moves, snap, deadline)
    decision = explain(features, ctx)

    rivals = [s for s in board.snakes if s.id != state.you.id and s.alive]
    if (
        config.MAX_SEARCH_DEPTH > 0
        and len(safe_moves) > 1
        and len(rivals) == 1
        and not deadline.expired()
    ):
        root_order = [r.move for r in decision.ranking]
        found = search.best_move(board, state.you.id, rivals[0].id, root_order, deadline)
        if found is not None:
            return found
    return decision.move
