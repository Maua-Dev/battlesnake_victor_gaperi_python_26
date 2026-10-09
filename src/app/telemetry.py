"""Logs estruturados de diagnóstico: uma linha JSON por evento no stdout.

Cada linha chega ao CloudWatch como JSON puro, sem o prefixo do runtime da
Lambda, e o CloudWatch Logs Insights descobre os campos sozinho. Os eventos,
os campos e as consultas estão em docs/logs.md.

Nada aqui muda a jogada: log_event e emit nunca lançam, e os builders só
reorganizam o que a lógica já calculou.
"""
import json
import logging
import os
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from .grid import MOVES, pos, step
from .models import GameState, Snake

logger = logging.getLogger("battlesnake")

_HANDLER_NAME = "battlesnake-stdout"

# Campos que todo evento tem, com null quando não se aplicam.
COMMON_FIELDS = ("game_id", "turn", "snake_id", "aws_request_id")

# As medições de MoveFeatures que vão para cada direção do evento move.
FEATURE_FIELDS = (
    "risky", "area", "roomy", "territory_pct", "food_step", "food_dist",
    "trapped_rivals", "kill_chance", "hunt_step", "danger", "center_dist",
)


class _StdoutHandler(logging.StreamHandler):
    """StreamHandler que procura sys.stdout a cada linha.

    Guardar a stream no import prenderia o handler ao stdout daquele momento;
    assim o capsys do pytest também enxerga os eventos.
    """

    def __init__(self) -> None:
        super().__init__()
        self.set_name(_HANDLER_NAME)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value) -> None:
        pass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _configure() -> None:
    """Handler próprio, sem propagar para o logger raiz (que põe prefixo)."""
    if not any(h.get_name() == _HANDLER_NAME for h in logger.handlers):
        handler = _StdoutHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    level = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO").upper())
    logger.setLevel(level if isinstance(level, int) else logging.INFO)


_configure()

# Requisições mais demoradas que isto saem com slow=true. Lido na hora do uso
# (telemetry.SLOW_MS), para os testes poderem trocar.
SLOW_MS = _env_int("SLOW_MS", 250)


# --- Contexto da requisição ---

# Um dict por requisição, criado pelo middleware. As rotas o MUTAM com
# bind_game: a rota roda numa thread com uma cópia do contexto, e um set lá
# dentro não voltaria para o middleware, mas o dict é o mesmo objeto.
_request: ContextVar[dict | None] = ContextVar("battlesnake_request", default=None)


def new_request_context(aws_request_id: str | None):
    """Abre o contexto de uma requisição; devolve o token para fechá-lo."""
    ctx = dict.fromkeys(COMMON_FIELDS)
    ctx["aws_request_id"] = aws_request_id
    return _request.set(ctx)


def end_request_context(token) -> None:
    _request.reset(token)


def game_fields(state: GameState) -> dict:
    """Os campos comuns que vêm do payload."""
    return {"game_id": state.game.id, "turn": state.turn, "snake_id": state.you.id}


def bind_game(state: GameState) -> None:
    """Põe a partida no contexto: request e error passam a trazê-la."""
    ctx = _request.get()
    if ctx is not None:
        ctx.update(game_fields(state))


def remaining_ms(aws_context) -> int | None:
    """Tempo restante da invocação da Lambda, ou None fora dela."""
    try:
        return int(aws_context.get_remaining_time_in_millis())
    except Exception:
        return None


# --- Emissão ---

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dumps(record: dict) -> str:
    return json.dumps(record, separators=(",", ":"), ensure_ascii=False, default=str)


def _failure(event: str, exc: Exception) -> dict:
    """Campos do error emitido quando a própria telemetria falha."""
    return {
        "path": None,
        "exception": type(exc).__name__,
        "message": f"telemetry: falha ao montar o evento {event}",
        "traceback": traceback.format_exc(),
    }


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """Grava uma linha com o evento em JSON. Nunca lança."""
    if not logger.isEnabledFor(level):
        return
    try:
        record = {"event": event, "ts": _now(), **dict.fromkeys(COMMON_FIELDS)}
        record.update(_request.get() or {})
        record.update(fields)
        line = _dumps(record)
    except Exception as exc:
        level = logging.ERROR
        line = _dumps({
            "event": "error", "ts": _now(), **dict.fromkeys(COMMON_FIELDS),
            **_failure(event, exc),
        })
    logger.log(level, line)


def log_error(**fields) -> None:
    log_event("error", logging.ERROR, **fields)


def emit(event: str, build, *args) -> None:
    """Emite event com os campos de build(*args).

    Se a montagem falhar, sai um error no lugar e a jogada segue.
    """
    if not logger.isEnabledFor(logging.INFO):
        return
    try:
        fields = build(*args)
    except Exception as exc:
        log_error(**_failure(event, exc))
        return
    log_event(event, **fields)


@contextmanager
def report_errors(path: str):
    """Loga qualquer exceção do bloco como error e a relança."""
    try:
        yield
    except Exception as exc:
        log_error(
            path=path,
            exception=type(exc).__name__,
            message=str(exc),
            traceback=traceback.format_exc(),
        )
        raise


def validation_error_fields(path: str, exc) -> dict:
    """Campos do error de um payload rejeitado pela validação.

    A mensagem só tem o local e o tipo de cada erro, nunca o valor recebido.
    game_id e turn saem do corpo quando ele os tem com o tipo certo.
    """
    message = "; ".join(
        f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('type')}"
        for err in exc.errors()
    )
    fields = {
        "path": path,
        "exception": type(exc).__name__,
        "message": message,
        "traceback": "",
    }
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        game = body.get("game")
        if isinstance(game, dict) and isinstance(game.get("id"), str):
            fields["game_id"] = game["id"]
        turn = body.get("turn")
        if isinstance(turn, int) and not isinstance(turn, bool):
            fields["turn"] = turn
    return fields


# --- Builders dos eventos de jogo ---

def engine_latency_ms(snake: Snake) -> int | None:
    """A latência do turno anterior medida pelo motor, ou None."""
    try:
        return int(snake.latency)
    except (TypeError, ValueError):
        return None


def observed_last_move(snake: Snake) -> str | None:
    """O movimento que a cobra de fato fez no turno anterior, ou None."""
    if len(snake.body) < 2:
        return None
    head, neck = snake.body[0], snake.body[1]
    delta = (head.x - neck.x, head.y - neck.y)
    for direction, d in MOVES.items():
        if d == delta:
            return direction
    return None


def start_fields(state: GameState) -> dict:
    game, board = state.game, state.board
    return {
        **game_fields(state),
        "ruleset": {"name": game.ruleset.get("name"), "version": game.ruleset.get("version")},
        "map": game.map,
        "timeout": game.timeout,
        "width": board.width,
        "height": board.height,
        "snake_count": len(board.snakes),
        "opponents": [
            {"id": s.id, "name": s.name} for s in board.snakes if s.id != state.you.id
        ],
    }


def end_fields(state: GameState) -> dict:
    survivors = [s.id for s in state.board.snakes]
    return {
        **game_fields(state),
        "turns": state.turn,
        "won": survivors == [state.you.id],
        "eliminated": state.you.id not in survivors,
        "survivors": survivors,
    }


def move_fields(
    state: GameState,
    reasons: dict[str, list[str]],
    safe_moves: list[str],
    choice,
    chosen: str,
    reason: str,
    logic_ms: float,
) -> dict:
    """Campos do evento move. choice é o logic.MoveChoice, ou None na emergência.

    Só reorganiza o que get_move já calculou: nada de flood fill, A* ou
    Voronoi roda de novo aqui.
    """
    you, board = state.you, state.board
    head = pos(you.body[0])
    latency = engine_latency_ms(you)
    features = {f.move: f for f in choice.features} if choice else {}
    ranked = {r.move: r for r in choice.decision.ranking} if choice else {}
    target = choice.target if choice else None

    directions = {}
    for direction in MOVES:
        f = features.get(direction)
        r = ranked.get(direction)
        entry = {"target": list(step(head, direction)), "blocked_by": list(reasons[direction])}
        for name in FEATURE_FIELDS:
            entry[name] = getattr(f, name) if f else None
        entry["layer"] = r.layer if r else None
        entry["score"] = r.score if r else None
        entry["score_terms"] = dict(r.terms) if r else None
        directions[direction] = entry

    return {
        **game_fields(state),
        "you": {"head": list(head), "length": you.length, "health": you.health},
        "engine_latency_ms": latency,
        "timed_out_last_turn": latency is not None and latency >= state.game.timeout,
        "observed_last_move": observed_last_move(you),
        "board": {
            "width": board.width,
            "height": board.height,
            "snake_count": len(board.snakes),
            "food_count": len(board.food),
        },
        "directions": directions,
        "safe_moves": list(safe_moves),
        # Sem candidatas a fome nem chega a ser avaliada.
        "hungry": choice.context.hungry if choice else None,
        "hunger_reasons": list(choice.hunger_reasons) if choice else [],
        "food_target": list(target.pos) if target else None,
        "astar_path_len": target.dist if target else None,
        "chosen": chosen,
        "reason": reason,
        "logic_ms": logic_ms,
    }
