"""Analisa uma partida da Arena: baixa os frames e roda a lógica da cobra
turno a turno, mostrando o que cada direção mediu e o que a busca acha com
tempo de sobra.

Uso (da raiz do repositório):
  python scripts/replay.py <game_id> [--engine URL] [--snake ID_OU_NOME]
      [--turns 70-76] [--budget-ms 120] [--deep-budget-ms 5000]

Ferramenta só local: fica fora de src/, então não entra no pacote da Lambda,
e usa só a biblioteca padrão. Escreve só no terminal. Detalhes em
docs/estrategia.md, seção "Analisar uma partida".
"""
import argparse
import json
import logging
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

# `python scripts/replay.py` põe scripts/ em sys.path[0], e não a raiz.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app import board_state, clock, config, logic, search  # noqa: E402
from src.app.decision import explain  # noqa: E402
from src.app.features import build_context, evaluate_moves, snapshot  # noqa: E402
from src.app.models import GameState  # noqa: E402

DEFAULT_ENGINE = "https://arena.devmaua.com/api"
# A Arena não informa as regras da partida: vale o timeout padrão do motor.
TIMEOUT_MS = 500
DEFAULT_TURNS = 8
PAGE_SIZE = 100

_DELTAS = {(0, 1): "up", (0, -1): "down", (-1, 0): "left", (1, 0): "right"}


class ReplayError(Exception):
    """Erro que encerra a ferramenta com uma mensagem, sem traceback."""


# --- Download ---

def ssl_context() -> ssl.SSLContext:
    """Contexto TLS com os certificados do certifi, se instalado (ele vem
    com o httpx de requirements-dev.txt). O Python do python.org no macOS
    não traz certificados de CA próprios; sem o certifi, vale o padrão."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def http_get_json(url: str):
    """GET de um JSON, com timeout de 30 s. Qualquer falha vira ReplayError
    com a URL."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "battlesnake-replay"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ReplayError(f"falha ao baixar {url}: {exc}") from exc


def fetch_game(engine: str, game_id: str, get_json) -> dict:
    """Os dados da partida (ID, Status, Width, Height)."""
    url = f"{engine}/games/{game_id}"
    payload = get_json(url)
    if not isinstance(payload, dict) or "Game" not in payload:
        raise ReplayError(f"resposta inesperada de {url}")
    return payload["Game"]


def fetch_frames(engine: str, game_id: str, get_json, page_size: int = PAGE_SIZE) -> list[dict]:
    """Todos os frames da partida, em ordem de Turn. Pede páginas de
    page_size até chegar uma vazia ou menor que page_size."""
    frames: list[dict] = []
    offset = 0
    while True:
        url = f"{engine}/games/{game_id}/frames?offset={offset}&limit={page_size}"
        payload = get_json(url)
        if not isinstance(payload, dict) or not isinstance(payload.get("frames"), list):
            raise ReplayError(f"resposta inesperada de {url}")
        page = payload["frames"]
        frames.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)
    return sorted(frames, key=lambda f: f["Turn"])


# --- Leitura dos frames ---

def find_snake(frame: dict | None, snake_id: str) -> dict | None:
    """A cobra com esse ID no frame, ou None."""
    if frame is None:
        return None
    return next((s for s in frame["Snakes"] if s["ID"] == snake_id), None)


def is_alive(snake: dict | None) -> bool:
    """Uma cobra está viva no frame quando não tem Death."""
    return snake is not None and snake.get("Death") is None


def describe_snakes(frames: list[dict]) -> str:
    """Id, nome e autor de cada cobra da partida, uma por linha."""
    return "\n".join(
        f"  {s['ID']}  nome={s.get('Name', '')!r}  autor={s.get('Author', '')!r}"
        for s in frames[0]["Snakes"]
    )


def pick_snake(frames: list[dict], wanted: str | None, author: str) -> dict:
    """A cobra analisada, do primeiro frame.

    Com wanted, a primeira cujo ID ou Name é igual a ele. Sem wanted, a
    única em que author aparece no Author ou no Name, sem diferenciar
    maiúsculas de minúsculas.
    """
    if not frames:
        raise ReplayError("a partida não tem frames")
    snakes = frames[0]["Snakes"]
    if wanted is not None:
        matches = [s for s in snakes if wanted in (s["ID"], s.get("Name"))][:1]
        problem = f"nenhuma cobra tem id ou nome {wanted!r}"
    else:
        needle = author.lower()
        matches = [
            s for s in snakes
            if needle in s.get("Author", "").lower() or needle in s.get("Name", "").lower()
        ]
        problem = (
            f"nenhuma cobra tem {author!r} no autor ou no nome" if not matches
            else f"mais de uma cobra tem {author!r} no autor ou no nome"
        )
    if len(matches) != 1:
        raise ReplayError(f"{problem}; use --snake. Cobras da partida:\n{describe_snakes(frames)}")
    return matches[0]


def _coord(c: dict) -> dict:
    return {"x": c["X"], "y": c["Y"]}


def _snake_json(s: dict) -> dict:
    body = [_coord(c) for c in s["Body"]]
    return {
        "id": s["ID"],
        "name": s.get("Name", ""),
        "health": s["Health"],
        "body": body,
        "head": body[0],
        "length": len(body),
        "latency": str(s.get("Latency", "")),
        "shout": s.get("Shout") or "",
    }


def frame_to_state(game: dict, frame: dict, you_id: str) -> GameState:
    """O estado que o /move receberia no turno do frame, validado com o
    mesmo modelo do /move. Só entram as cobras vivas, na ordem do frame."""
    snakes = [_snake_json(s) for s in frame["Snakes"] if is_alive(s)]
    you = next((s for s in snakes if s["id"] == you_id), None)
    if you is None:
        raise ReplayError(f"a cobra {you_id} não está viva no turno {frame['Turn']}")
    return GameState.model_validate({
        "game": {
            "id": game["ID"],
            "ruleset": {"name": "standard"},
            "map": "standard",
            "timeout": TIMEOUT_MS,
        },
        "turn": frame["Turn"],
        "board": {
            "width": game["Width"],
            "height": game["Height"],
            "food": [_coord(c) for c in frame.get("Food") or []],
            "hazards": [_coord(c) for c in frame.get("Hazards") or []],
            "snakes": snakes,
        },
        "you": you,
    })


def played_move(frame: dict, next_frame: dict | None, you_id: str) -> str | None:
    """A direção jogada no turno do frame: da cabeça neste frame para a do
    próximo. None sem o próximo frame ou sem uma diferença de uma casa."""
    now, later = find_snake(frame, you_id), find_snake(next_frame, you_id)
    if now is None or later is None:
        return None
    a, b = now["Body"][0], later["Body"][0]
    return _DELTAS.get((b["X"] - a["X"], b["Y"] - a["Y"]))


def turn_latency(next_frame: dict | None, you_id: str) -> str | None:
    """A latência do turno T está no frame T+1, o produzido pela resposta."""
    snake = find_snake(next_frame, you_id)
    return None if snake is None else str(snake.get("Latency", ""))


def parse_turns(text: str) -> tuple[int, int]:
    """'A-B' (pontas incluídas) ou 'A'. Levanta ValueError se inválido."""
    parts = text.split("-")
    if len(parts) not in (1, 2) or not all(p.isdigit() for p in parts):
        raise ValueError(f"intervalo de turnos inválido: {text!r} (use A-B ou A)")
    first, last = int(parts[0]), int(parts[-1])
    if first > last:
        raise ValueError(f"intervalo de turnos invertido: {text!r}")
    return first, last


def default_turns(frames: list[dict], you_id: str) -> list[int]:
    """Os DEFAULT_TURNS turnos antes da morte da cobra ou, se ela não
    morreu, os DEFAULT_TURNS últimos frames."""
    snake = find_snake(frames[-1], you_id)
    death = snake.get("Death") if snake else None
    if death:
        end = death["Turn"]
        return list(range(max(0, end - DEFAULT_TURNS), end))
    return [f["Turn"] for f in frames[-DEFAULT_TURNS:]]


# --- Relatório ---

def render_board(state: GameState) -> list[str]:
    """O tabuleiro em ASCII, com y crescendo para cima e a legenda dos
    testes: E/e/t para a cobra analisada (cabeça, corpo, cauda), R/r para
    as adversárias, * comida, h hazard e . casa vazia."""
    w, h = state.board.width, state.board.height
    grid = [["."] * w for _ in range(h)]
    for c in state.board.hazards:
        grid[c.y][c.x] = "h"
    for c in state.board.food:
        grid[c.y][c.x] = "*"
    for s in state.board.snakes:
        if s.id == state.you.id:
            continue
        for c in reversed(s.body):
            grid[c.y][c.x] = "r"
        grid[s.body[0].y][s.body[0].x] = "R"
    body = state.you.body
    for c in body:
        grid[c.y][c.x] = "e"
    if len(body) > 1:
        grid[body[-1].y][body[-1].x] = "t"
    grid[body[0].y][body[0].x] = "E"
    lines = [f"{f'y={y}':<4}  " + " ".join(grid[y]) for y in range(h - 1, -1, -1)]
    lines.append(f"{'x:':<4}  " + " ".join(str(x) for x in range(w)))
    return lines


def _number(value: float) -> str:
    return f"{value:.1f}"


def search_label(value: float, depth: int) -> str:
    """O valor da busca, com as marcas de fim de jogo dentro do horizonte."""
    if value == config.DRAW:
        return "EMPATE"
    if value >= config.WIN - depth:
        return f"VENCE em {int(config.WIN - value)}"
    if value <= -config.WIN + depth:
        return f"PERDE em {int(value + config.WIN)}"
    return _number(value)


def deep_search(board, me: str, rival: str, moves: list[str], budget_ms: float) -> list[str]:
    """O valor de cada candidata por profundidade, de 1 até a última que
    terminou dentro do prazo, sem passar de MAX_SEARCH_DEPTH."""
    deadline = clock.Deadline(clock.now(), budget_ms)
    lines = []
    for depth in range(1, config.MAX_SEARCH_DEPTH + 1):
        values = {}
        for move in moves:
            value = search.minimax_value(
                board, me, rival, depth, root_moves=[move], deadline=deadline
            )
            if value is None:
                break
            values[move] = value
        if len(values) < len(moves):
            lines.append(f"    profundidade {depth} interrompida pelo prazo (descartada)")
            break
        cells = "  ".join(f"{m}: {search_label(v, depth)}" for m, v in values.items())
        lines.append(f"    d={depth:<2} {cells}")
    return lines


def local_move(state: GameState, budget_ms: int) -> tuple[str, float]:
    """O que get_move devolve com o teto de orçamento dado, pelo mesmo
    caminho do /move, e o orçamento efetivo."""
    previous = config.SEARCH_BUDGET_MAX_MS
    try:
        config.SEARCH_BUDGET_MAX_MS = budget_ms
        effective = clock.budget_ms(state.game.timeout)
        return logic.get_move(state).move, effective
    finally:
        config.SEARCH_BUDGET_MAX_MS = previous


def analyze_turn(
    state: GameState,
    played: str | None,
    latency: str | None,
    budget_ms: int,
    deep_budget_ms: int,
) -> tuple[list[str], str | None]:
    """As linhas do relatório de um turno e a direção escolhida localmente,
    ou None quando não há candidata e get_move sorteia."""
    you = state.you
    board = board_state.from_game(state)
    rivals = [s for s in state.board.snakes if s.id != you.id]
    body: list[str] = []

    body += render_board(state)
    if state.board.hazards:
        body.append("aviso: há hazards, mas a Arena não informa o dano; analisado com dano 0")
    latency_text = "desconhecida" if latency is None else f"{latency} ms" if latency.isdigit() else latency
    body.append(f"jogada: {played or 'desconhecida'} · latência: {latency_text}")

    reasons = logic.filter_moves(state, board)
    candidates = [m for m, r in reasons.items() if r is None]
    eliminated = " · ".join(f"{m}: {r}" for m, r in reasons.items() if r is not None)
    body.append(f"candidatas: {', '.join(candidates) or 'nenhuma'}")
    if eliminated:
        body.append(f"eliminadas: {eliminated}")

    ranking: list[str] = candidates
    if candidates:
        snap = snapshot(state, board)
        ctx = build_context(state, snap)
        features = evaluate_moves(
            state, candidates, snap, clock.Deadline(clock.now(), deep_budget_ms)
        )
        decision = explain(features, ctx)
        by_move = {f.move: f for f in features}
        target = max(1, min(you.length, config.SURVIVAL_MAX_DEPTH))
        body.append(
            f"medições (prazo {deep_budget_ms} ms, fome={ctx.hungry}): "
            f"heurística {decision.move} ({decision.reason})"
        )
        for r in decision.ranking:
            f = by_move[r.move]
            terms = " ".join(f"{k}={_number(v)}" for k, v in r.terms.items() if v)
            body.append(
                f"  {r.move:<5} camada {r.layer}  nota {_number(r.score)}  [{terms}]"
            )
            body.append(
                f"        area={f.area} survival={f.survival_depth}/{target} "
                f"survives={f.survives} roomy={f.roomy} risky={f.risky} "
                f"kill_chance={f.kill_chance}"
            )
        ranking = [r.move for r in decision.ranking]

    move, effective = local_move(state, budget_ms)
    if candidates:
        body.append(f"get_move (orçamento {effective:g} ms): {move}")
    else:
        # Sem candidata, get_move sorteia: não há escolha para comparar.
        body.append(f"get_move (orçamento {effective:g} ms): {move} (sorteio entre as quatro)")
        move = None

    if len(rivals) == 1 and len(candidates) > 1 and config.MAX_SEARCH_DEPTH > 0:
        body.append(f"busca (prazo {deep_budget_ms} ms):")
        body += deep_search(board, you.id, rivals[0].id, ranking, deep_budget_ms)

    header = (
        f"=== turno {state.turn} · vida {you.health} · tamanho {you.length} · "
        f"{len(rivals)} adversária(s) viva(s) ==="
    )
    if played is not None and move is not None and played != move:
        header += f"  <<< DIVERGE: jogada {played}, local {move} >>>"
    return [header, *body, ""], move


# --- Linha de comando ---

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reexecuta a lógica da cobra nos turnos de uma partida da Arena."
    )
    parser.add_argument("game_id")
    parser.add_argument("--engine", default=DEFAULT_ENGINE, help="base da API da Arena")
    parser.add_argument("--snake", help="id ou nome da cobra analisada")
    parser.add_argument("--turns", help="intervalo de turnos, A-B ou A")
    parser.add_argument("--budget-ms", type=int, default=120,
                        help="teto do orçamento da jogada simulada (padrão 120)")
    parser.add_argument("--deep-budget-ms", type=int, default=5000,
                        help="prazo folgado das medições e da busca (padrão 5000)")
    return parser


def main(argv: list[str] | None = None, get_json=http_get_json, out=print) -> int:
    args = build_parser().parse_args(argv)
    try:
        turns = parse_turns(args.turns) if args.turns is not None else None
    except ValueError as exc:
        out(f"erro: {exc}")
        return 2

    # O log de produção da cobra não entra na análise.
    log = logging.getLogger("battlesnake")
    was_disabled = log.disabled
    log.disabled = True
    try:
        engine = args.engine.rstrip("/")
        game = fetch_game(engine, args.game_id, get_json)
        frames = fetch_frames(engine, args.game_id, get_json)
        snake = pick_snake(frames, args.snake, logic.info()["author"])
        you_id = snake["ID"]
        out(f"partida {args.game_id} · {game['Width']}x{game['Height']} · {len(frames)} frames")
        out(f"cobra analisada: {snake.get('Name', '')} ({you_id})")
        out("")

        selected = list(range(turns[0], turns[1] + 1)) if turns else default_turns(frames, you_id)
        by_turn = {f["Turn"]: f for f in frames}
        divergent = []
        for turn in selected:
            frame = by_turn.get(turn)
            if frame is None or not is_alive(find_snake(frame, you_id)):
                continue
            next_frame = by_turn.get(turn + 1)
            state = frame_to_state(game, frame, you_id)
            played = played_move(frame, next_frame, you_id)
            lines, move = analyze_turn(
                state, played, turn_latency(next_frame, you_id),
                args.budget_ms, args.deep_budget_ms,
            )
            for line in lines:
                out(line)
            if played is not None and move is not None and played != move:
                divergent.append(turn)
        out(
            f"turnos divergentes: {', '.join(map(str, divergent))}" if divergent
            else "turnos divergentes: nenhum"
        )
        return 0
    except ReplayError as exc:
        out(f"erro: {exc}")
        return 1
    finally:
        log.disabled = was_disabled


if __name__ == "__main__":
    sys.exit(main())
