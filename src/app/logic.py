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
import time
from dataclasses import dataclass
from . import telemetry
from .models import GameState, MoveResponse
from .grid import pos, step, opponent_cells, tail_moves
from .features import FoodTarget, snapshot, build_context, evaluate_moves, hunger_reasons
from .decision import Decision, DecisionContext, MoveFeatures, explain


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
    telemetry.emit("start", telemetry.start_fields, state)


def end(state: GameState) -> None:
    """POST /end — chamado uma vez, quando a partida termina."""
    telemetry.emit("end", telemetry.end_fields, state)


def mark_unsafe(
    is_move_safe: dict[str, bool],
    reasons: dict[str, list[str]],
    direction: str,
    reason: str,
) -> None:
    """Marca a direção como insegura e registra o motivo, sem repetir."""
    is_move_safe[direction] = False
    if reason not in reasons[direction]:
        reasons[direction].append(reason)


def get_move(state: GameState) -> MoveResponse:
    """POST /move — chamado a cada turno. Aqui mora a inteligência da sua cobra.
    Precisa devolver "up", "down", "left" ou "right".
    Exemplo do JSON recebido: https://docs.battlesnake.com/api/example-move

    Emite um evento move por chamada, explicando a escolha (docs/logs.md).
    """
    started = time.perf_counter()
    is_move_safe: dict[str, bool] = {
        "up": True,
        "down": True,
        "left": True,
        "right": True,
    }
    # Por que cada direção caiu, na ordem dos blocos abaixo (blocked_by do
    # evento move).
    reasons: dict[str, list[str]] = {direction: [] for direction in is_move_safe}

    # --- Impedir que a cobra ande para trás (já implementado) ---
    # O pescoço é a parte do corpo logo atrás da cabeça. Voltar por cima dele
    # é morte certa, então marcamos aquela direção como insegura.
    my_head = state.you.body[0]
    my_neck = state.you.body[1] if len(state.you.body) >= 2 else None

    if my_neck is not None:
        if my_neck.x < my_head.x:
            # pescoço à esquerda da cabeça -> não vá para a esquerda
            mark_unsafe(is_move_safe, reasons, "left", "neck")
        elif my_neck.x > my_head.x:
            # pescoço à direita da cabeça -> não vá para a direita
            mark_unsafe(is_move_safe, reasons, "right", "neck")
        elif my_neck.y < my_head.y:
            # pescoço abaixo da cabeça -> não desça
            mark_unsafe(is_move_safe, reasons, "down", "neck")
        elif my_neck.y > my_head.y:
            # pescoço acima da cabeça -> não suba
            mark_unsafe(is_move_safe, reasons, "up", "neck")

    # 2. Impedir que a cobra saia do tabuleiro (paredes)
    board_width = state.board.width
    board_height = state.board.height

    if my_head.x + 1 >= board_width:
        mark_unsafe(is_move_safe, reasons, "right", "wall")
    if my_head.x - 1 < 0:
        mark_unsafe(is_move_safe, reasons, "left", "wall")
    if my_head.y + 1 >= board_height:
        mark_unsafe(is_move_safe, reasons, "up", "wall")
    if my_head.y - 1 < 0:
        mark_unsafe(is_move_safe, reasons, "down", "wall")

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
            mark_unsafe(is_move_safe, reasons, "right", "self")
        if segment.x == my_head.x - 1 and segment.y == my_head.y:
            mark_unsafe(is_move_safe, reasons, "left", "self")
        if segment.x == my_head.x and segment.y == my_head.y + 1:
            mark_unsafe(is_move_safe, reasons, "up", "self")
        if segment.x == my_head.x and segment.y == my_head.y - 1:
            mark_unsafe(is_move_safe, reasons, "down", "self")

    # 4. Impedir que a cobra bata nas adversárias (a cauda delas continua
    # bloqueada: se a rival comer neste turno, a cauda não sai do lugar)
    head = pos(my_head)
    rivals = opponent_cells(state.board, state.you)
    for direction in is_move_safe:
        if is_move_safe[direction] and step(head, direction) in rivals:
            mark_unsafe(is_move_safe, reasons, direction, "opponent")

    # O cabeça a cabeça com rival maior ou igual não elimina a direção: ele
    # só a marca como arriscada (MoveFeatures.risky), e a decisão prefere as
    # não arriscadas. Um cabeça a cabeça incerto é melhor que um beco certo.

    # Sobrou alguma direção segura?
    safe_moves = [direction for direction, safe in is_move_safe.items() if safe]

    if not safe_moves:
        # Emergência: todas as direções são perigosas.
        # Escolhemos uma ao acaso entre as 4 — melhor do que travar.
        all_moves = ["up", "down", "left", "right"]
        fallback = random.choice(all_moves)
        logic_ms = round((time.perf_counter() - started) * 1000, 2)
        telemetry.emit(
            "move", telemetry.move_fields,
            state, reasons, safe_moves, None, fallback, "emergency", logic_ms,
        )
        return MoveResponse(move=fallback)

    # Escolhe, entre as direções seguras, a melhor segundo a estratégia.
    choice = choose_move(state, safe_moves)
    chosen = choice.decision.move

    logic_ms = round((time.perf_counter() - started) * 1000, 2)
    telemetry.emit(
        "move", telemetry.move_fields,
        state, reasons, safe_moves, choice, chosen, choice.decision.reason, logic_ms,
    )
    return MoveResponse(move=chosen)


@dataclass(frozen=True)
class MoveChoice:
    """O rastro da escolha: o que foi medido e por que a decisão escolheu."""
    context: DecisionContext
    hunger_reasons: list[str]
    features: list[MoveFeatures]
    # A comida alvo do turno (com o caminho A* da cabeça atual), ou None.
    target: FoodTarget | None
    decision: Decision


def choose_move(state: GameState, safe_moves: list[str]) -> MoveChoice:
    """Escolhe uma direção dentre safe_moves (que nunca chega vazia).

    Três etapas: safe_moves são as candidatas, evaluate_moves mede cada uma e
    a decisão escolhe só a partir dessas medições e do contexto. explain é a
    própria decide, devolvendo também o porquê.
    """
    snap = snapshot(state)
    ctx = build_context(state, snap)
    features = evaluate_moves(state, safe_moves, snap)
    return MoveChoice(
        context=ctx,
        hunger_reasons=hunger_reasons(state, snap),
        features=features,
        target=snap.target,
        decision=explain(features, ctx),
    )
