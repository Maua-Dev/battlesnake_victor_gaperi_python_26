"""Ponte entre o AWS Lambda e a lógica da sua cobra.

Você NÃO precisa mexer aqui. Este arquivo define os endpoints FastAPI e
repassa as chamadas para logic.py.

Rotas da API (https://docs.battlesnake.com/api):
  GET  /        -> aparência da cobra
  POST /start   -> a partida começou
  POST /move    -> escolha a jogada deste turno
  POST /end     -> a partida acabou
"""
import time

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from mangum import Mangum
from . import logic, telemetry
from .models import GameState, MoveResponse

app = FastAPI()

# Nomes de stage que o API Gateway pode colocar na frente do caminho.
STAGE_PREFIXES = ("dev", "homolog", "prod", "staging")

# Verdadeiro até a primeira requisição atendida por esta instância da Lambda.
_cold_start = True


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
    """
    request.scope["path"] = strip_stage_prefix(request.scope["path"])

    return await call_next(request)


# Declarado depois de remove_stage_prefix, este middleware é o mais externo:
# mede a requisição inteira, do recebimento à resposta.
@app.middleware("http")
async def request_telemetry(request: Request, call_next):
    """Emite um evento request por requisição (ver docs/logs.md).

    Não lê cabeçalhos, query nem corpo: nada disso vai para o log.
    """
    global _cold_start
    cold_start, _cold_start = _cold_start, False
    aws_context = request.scope.get("aws.context")
    token = telemetry.new_request_context(getattr(aws_context, "aws_request_id", None))
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        telemetry.log_event(
            "request",
            path=strip_stage_prefix(request.scope["path"]),
            method=request.method,
            status=status,
            duration_ms=duration_ms,
            cold_start=cold_start,
            remaining_ms=telemetry.remaining_ms(aws_context),
            slow=duration_ms > telemetry.SLOW_MS,
        )
        telemetry.end_request_context(token)


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
    telemetry.bind_game(state)
    with telemetry.report_errors("/start"):
        logic.start(state)
    return "ok"


# exclude_none tira o "shout": null da resposta — o contrato define shout
# como opcional, e nao como nulo.
@app.post("/move", response_model_exclude_none=True)
def move(state: GameState) -> MoveResponse:
    """POST /move — chamado a cada turno. Chama a lógica da cobra."""
    telemetry.bind_game(state)
    with telemetry.report_errors("/move"):
        return logic.get_move(state)


@app.post("/end")
def end(state: GameState) -> str:
    """POST /end — chamado no fim de cada partida."""
    telemetry.bind_game(state)
    with telemetry.report_errors("/end"):
        logic.end(state)
    return "ok"


# Handler para AWS Lambda via Mangum
handler = Mangum(app, lifespan="off")