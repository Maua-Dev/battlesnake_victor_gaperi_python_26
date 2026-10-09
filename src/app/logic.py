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
from .board_state import BoardState, hazard_damage, idx
from .models import GameState, MoveResponse
from .grid import pos, step
from .simulator import occupied_after_turn
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
    board = board_state.from_game(state)

    # Sobrou alguma direção segura?
    reasons = filter_moves(state, board)
    safe_moves = [direction for direction, reason in reasons.items() if reason is None]

    if not safe_moves:
        # Emergência: todas as direções são perigosas.
        # Escolhemos uma ao acaso entre as 4 — melhor do que travar.
        all_moves = ["up", "down", "left", "right"]
        move = random.choice(all_moves)
    else:
        # Escolhe, entre as direções seguras, a melhor segundo a estratégia.
        move = choose_move(state, safe_moves, deadline=deadline, board=board)

    telemetry.log_move(state, move)
    return MoveResponse(move=move)


def filter_moves(state: GameState, board: BoardState) -> dict[str, str | None]:
    """O filtro de get_move: para cada direção, na ordem canônica, o motivo
    da eliminação ("neck", "wall", "body" ou "health") ou None, se a direção
    é candidata. Vale o primeiro motivo encontrado.

    board é o BoardState da jogada (board_state.from_game(state)).
    """
    reasons: dict[str, str | None] = {
        "up": None,
        "down": None,
        "left": None,
        "right": None,
    }

    def eliminate(direction: str, reason: str) -> None:
        if reasons[direction] is None:
            reasons[direction] = reason

    # --- Impedir que a cobra ande para trás (já implementado) ---
    # O pescoço é a parte do corpo logo atrás da cabeça. Voltar por cima dele
    # é morte certa, então marcamos aquela direção como insegura.
    my_head = state.you.body[0]
    my_neck = state.you.body[1] if len(state.you.body) >= 2 else None

    if my_neck is not None:
        if my_neck.x < my_head.x:
            # pescoço à esquerda da cabeça -> não vá para a esquerda
            eliminate("left", "neck")
        elif my_neck.x > my_head.x:
            # pescoço à direita da cabeça -> não vá para a direita
            eliminate("right", "neck")
        elif my_neck.y < my_head.y:
            # pescoço abaixo da cabeça -> não desça
            eliminate("down", "neck")
        elif my_neck.y > my_head.y:
            # pescoço acima da cabeça -> não suba
            eliminate("up", "neck")

    # 2. Impedir que a cobra saia do tabuleiro (paredes)
    board_width = state.board.width
    board_height = state.board.height

    if my_head.x + 1 >= board_width:
        eliminate("right", "wall")
    if my_head.x - 1 < 0:
        eliminate("left", "wall")
    if my_head.y + 1 >= board_height:
        eliminate("up", "wall")
    if my_head.y - 1 < 0:
        eliminate("down", "wall")

    # 3. Impedir que a cobra bata num corpo, o próprio ou o das adversárias.
    # A cauda anda junto com a cabeça, então a casa dela fica livre neste
    # turno, mesmo que a cobra coma (o movimento vem antes da alimentação),
    # exceto logo depois de comer (cauda empilhada). É a mesma regra do
    # simulador da busca (occupied_after_turn). O bloco do pescoço, lá em
    # cima, continua barrando a meia-volta.
    head = pos(my_head)
    occupied = occupied_after_turn(board)
    for direction in reasons:
        if reasons[direction] is None:
            x, y = step(head, direction)
            if idx(x, y, board.width) in occupied:
                eliminate(direction, "body")

    # 4. Impedir que a cobra morra de fome ou num hazard. As regras oficiais
    # do modo standard rodam nesta ordem: movimento, perda de 1 de vida,
    # dano de hazard (que não vale numa casa com comida), alimentação e só
    # então as eliminações. Então, sem comida no destino, a vida que sobra é
    # vida - 1 - dano × (vezes que a casa aparece na lista de hazards).
    # https://github.com/BattlesnakeOfficial/rules/blob/main/standard.go
    damage = hazard_damage(state.game.ruleset)
    food = {pos(f) for f in state.board.food}
    hazards = Counter(pos(h) for h in state.board.hazards)
    for direction in reasons:
        target = step(head, direction)
        if reasons[direction] is not None or target in food:
            continue
        if state.you.health - 1 - damage * hazards[target] <= 0:
            eliminate(direction, "health")

    # O cabeça a cabeça com rival maior ou igual não elimina a direção: ele
    # só a marca como arriscada (MoveFeatures.risky), e a decisão prefere as
    # não arriscadas. Um cabeça a cabeça incerto é melhor que um beco certo.
    return reasons


def choose_move(
    state: GameState,
    safe_moves: list[str],
    deadline: clock.Deadline | None = None,
    board: BoardState | None = None,
) -> str:
    """Escolhe uma direção dentre safe_moves (que nunca chega vazia).

    Três etapas: safe_moves são as candidatas, evaluate_moves mede cada uma e
    explain (a decide com o porquê) escolhe só a partir dessas medições e do
    contexto. Essa escolha heurística fica pronta primeiro. Depois, num
    duelo e se o prazo ainda não passou, a busca pode substituí-la, mas só
    com o resultado de uma profundidade que terminou dentro do prazo.

    board é o BoardState da jogada; sem ele, é montado aqui.
    """
    if deadline is None:
        deadline = clock.Deadline(clock.now(), clock.budget_ms(state.game.timeout))
    if board is None:
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
