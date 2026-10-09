"""Logs estruturados de diagnóstico: uma linha JSON por evento no stdout.

Só dois eventos: move (um por jogada) e error. Cada linha chega ao
CloudWatch como JSON puro, sem o prefixo do runtime da Lambda, e o
CloudWatch Logs Insights descobre os campos sozinho. Os campos e as
consultas estão em docs/logs.md.

Nada aqui muda a jogada: log_event e log_move nunca lançam.
"""
import json
import logging
import os
import sys
import traceback
from contextlib import contextmanager

from .models import GameState, Snake

logger = logging.getLogger("battlesnake")

_HANDLER_NAME = "battlesnake-stdout"


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


# --- Emissão ---

def _dumps(record: dict) -> str:
    return json.dumps(record, separators=(",", ":"), ensure_ascii=False, default=str)


def _failure(event: str, exc: Exception) -> dict:
    """Campos do error emitido quando a própria telemetria falha."""
    return {
        "path": None,
        "exception": type(exc).__name__,
        "message": f"telemetry: falha ao montar o evento {event}",
        "traceback": traceback.format_exc(),
        "game_id": None,
        "turn": None,
    }


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """Grava uma linha com o evento em JSON. Nunca lança."""
    if not logger.isEnabledFor(level):
        return
    try:
        line = _dumps({"event": event, **fields})
    except Exception as exc:
        level = logging.ERROR
        line = _dumps({"event": "error", **_failure(event, exc)})
    logger.log(level, line)


def log_error(**fields) -> None:
    """Grava um error; game_id e turn saem nulos quando não vêm."""
    log_event("error", logging.ERROR, **{"game_id": None, "turn": None, **fields})


# --- Evento move ---

def timed_out_last_turn(snake: Snake, timeout: int) -> bool:
    """Diz se o turno anterior estourou o tempo, pela latência que o motor mede.

    Latência ausente, vazia ou não numérica conta como dentro do tempo.
    """
    try:
        return int(snake.latency) >= timeout
    except (TypeError, ValueError):
        return False


def log_move(state: GameState, move: str) -> None:
    """Grava o evento move da jogada. Nunca lança.

    Se a montagem falhar, sai um error no lugar e a jogada segue.
    """
    if not logger.isEnabledFor(logging.INFO):
        return
    try:
        fields = {
            "game_id": state.game.id,
            "turn": state.turn,
            "move": move,
            "timed_out_last_turn": timed_out_last_turn(state.you, state.game.timeout),
        }
    except Exception as exc:
        log_error(**_failure("move", exc))
        return
    log_event("move", **fields)


# --- Evento error ---

@contextmanager
def report_errors(path: str, state: GameState):
    """Loga qualquer exceção do bloco como error, com a partida, e a relança."""
    try:
        yield
    except Exception as exc:
        log_error(
            path=path,
            exception=type(exc).__name__,
            message=str(exc),
            traceback=traceback.format_exc(),
            game_id=state.game.id,
            turn=state.turn,
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
