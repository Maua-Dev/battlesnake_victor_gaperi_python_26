"""Ponte entre o AWS Lambda e a lógica da sua cobra.

Você NÃO precisa mexer aqui. Este arquivo define os endpoints FastAPI e
repassa as chamadas para logic.py.

Rotas da API (https://docs.battlesnake.com/api):
  GET  /        -> aparência da cobra
  POST /start   -> a partida começou
  POST /move    -> escolha a jogada deste turno
  POST /end     -> a partida acabou
"""
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from mangum import Mangum
from . import clock, logic, telemetry
from .models import GameState, MoveResponse

app = FastAPI()

# Nomes de stage que o API Gateway pode colocar na frente do caminho.
STAGE_PREFIXES = ("dev", "homolog", "prod", "staging")


def strip_stage_prefix(path: str) -> str:
    """Caminho sem o prefixo do stage (ex.: "/dev/move" -> "/move")."""
    first, _, rest = path.lstrip("/").partition("/")
    if first in STAGE_PREFIXES:
        return "/" + rest
    return path


@app.middleware("http")
async def remove_stage_prefix(request: Request, call_next):
    """Remove o prefixo do stage (ex.: /dev, /staging) quando presente.

    Dependendo de como a API e exposta, o caminho pode chegar como "/dev/move"
    em vez de "/move". Sem esta normalizacao a rota nao casa e vira 404.

    Também marca o instante de chegada, antes de o FastAPI validar o corpo:
    o prazo da jogada conta a partir daqui (ver clock.Deadline).
    """
    request.state.started_at = clock.now()
    request.scope["path"] = strip_stage_prefix(request.scope["path"])

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def log_validation_error(request: Request, exc: RequestValidationError):
    """Payload recusado: o motor escolhe o movimento no lugar da cobra.

    Loga o erro (sem os valores recebidos) e devolve o mesmo 422 de sempre.
    """
    path = strip_stage_prefix(request.scope["path"])
    telemetry.log_error(**telemetry.validation_error_fields(path, exc))
    return await request_validation_exception_handler(request, exc)


@app.get("/")
def read_root() -> dict:
    """GET / — informações e aparência da cobra."""
    return logic.info()


@app.post("/start")
def start(state: GameState) -> str:
    """POST /start — chamado no início de cada partida."""
    with telemetry.report_errors("/start", state):
        logic.start(state)
    return "ok"


# exclude_none tira o "shout": null da resposta — o contrato define shout
# como opcional, e nao como nulo.
@app.post("/move", response_model_exclude_none=True)
def move(state: GameState, request: Request) -> MoveResponse:
    """POST /move — chamado a cada turno. Chama a lógica da cobra."""
    with telemetry.report_errors("/move", state):
        return logic.get_move(state, started_at=request.state.started_at)


@app.post("/end")
def end(state: GameState) -> str:
    """POST /end — chamado no fim de cada partida."""
    with telemetry.report_errors("/end", state):
        logic.end(state)
    return "ok"


# Handler para AWS Lambda via Mangum
handler = Mangum(app, lifespan="off")