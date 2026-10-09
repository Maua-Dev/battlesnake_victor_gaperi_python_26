# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A [Battlesnake](https://docs.battlesnake.com/api) bot: a FastAPI app served on AWS Lambda through Mangum, built from the Mauá Dev `battlesnake_fastapi_template`. Snake behavior lives in `src/app/logic.py`. The rest of the repo carries the game state to it and deploys it. Code comments, docstrings, test names and the README are in Brazilian Portuguese, so new code should follow that.

## Commands

Python 3.13 (CI and the Lambda runtime both use 3.13).

```bash
pip install -r requirements.txt -r requirements-dev.txt

pytest                                              # full suite (run from repo root)
pytest tests/app/test_logic.py                      # one file
pytest tests/app/test_logic.py::test_evita_parede_na_borda
pytest tests/app/test_app.py::TestMove::test_nunca_volta_contra_o_pescoco

uvicorn src.app.main:app --reload                   # local server on :8000
```

There is no linter or formatter configured.

## Architecture

- `src/app/main.py`: the FastAPI routes (`GET /`, `POST /start|/move|/end`) delegate to `logic.info/start/get_move/end`. It also has a middleware that strips a leading stage segment (`/dev`, `/prod`, …) from the path and records `request.state.started_at = clock.now()` before the payload is validated; `/move` passes that instant to `logic.get_move(state, started_at=...)`, so the move deadline counts from arrival. `handler = Mangum(app)` is the Lambda entry point. `/move` uses `response_model_exclude_none=True` so that `shout` is omitted rather than sent as `null`.
- `src/app/models.py`: Pydantic models for the Battlesnake request payload (`GameState` → `Board`, `Snake`, `Coord`, `Game`) plus `MoveResponse`. Coordinates start at (0,0) in the bottom-left corner, so `up` is `y+1`. `body[0]` is the head.
- `src/app/logic.py`: `get_move` builds an `is_move_safe` dict and filters out certain death (neck/backwards, walls, own body, opponent bodies including their tails, and moves where health would reach 0 from starvation or hazard damage, following the official `standard.go` order). The leftover `safe_moves` are the candidates. If none are left, it picks a random direction of the four, which is the only randomness. Otherwise `choose_move` runs the three-step decision below and then, only in a duel, the search. The game allows about 500 ms per move. The move budget is `min(0.4 × game.timeout, SEARCH_BUDGET_MAX_MS)` (120 ms by default, overridable by the env var of the same name), counted from arrival (`clock.Deadline`). The heuristic phase target is 50 ms on a 19x19 with 4 snakes and 10 ms on an 11x11 with 8 snakes, measured locally. The Lambda's 128 MB CPU is far slower; see `docs/estrategia.md`.
- **Three-step decision:** candidates (`get_move`) → features (`src/app/features.py`: `snapshot`, `build_context`, `evaluate_moves` returning one `MoveFeatures` per candidate, with no choice made) → decision (`src/app/decision.py`: `decide(features, context)` / `explain`, safety layers, then score, then canonical-order tiebreak). A head-to-head against an equal or bigger rival marks a move `risky` instead of removing it. `roomy` is `area >= length or survives` and is computed in `features`, not in `decision`. The heuristic choice is always ready before the search.
- **Duel search** (`src/app/search.py`): runs after the heuristic only with exactly one live rival, more than one candidate, `MAX_SEARCH_DEPTH > 0` and time left. Simultaneous-move max-min (paranoid) with alpha-beta and iterative deepening; the deadline is checked at every node, an unfinished depth is discarded, and `None` (no finished depth) falls back to the heuristic. The search only **vetoes**: it keeps the heuristic choice (`Decision.ranking[0]`, searched first with a full window) unless its value is a loss or draw (`<= DRAW`) and another root move scores higher; ties among replacements follow `Decision.ranking`. The leaf weights are uncalibrated, so the leaf never decides between moves that don't lose. `MAX_SEARCH_DEPTH = 0` turns it off.
- **Index-based modules** (no Pydantic, never import `models.py`): `board_state.py` (`from_game` reads the `GameState` once per move into `BoardState`/`SnakeState` with cells as `y * width + x`, cached neighbor tables, hazards as a count per cell, hazard damage from `ruleset.settings.hazardDamagePerTurn`), `occupancy.py` (`free_after` per cell plus the temporal BFS, Voronoi and A* that only enter a cell at time t if `free_after <= t`), `survival.py` (iterative DFS that simulates the own body exactly), `simulator.py` (`step` in the official rule order, no food spawning; `safe_moves`), `clock.py` (`now`, `Deadline`, `budget_ms`). Always call `clock.now()` at use time so tests can swap the clock.
- **`decision.py` must not import `models.py`** (directly or transitively; it may only import `config`), because Jev will replace `decide` using `MoveFeatures` + `DecisionContext` as its context. `tests/app/test_estrategia_v2.py::test_decisao_nao_importa_models` enforces this.
- `src/app/config.py` holds every tuning weight and threshold. Read them as `config.NAME` at use time (never `from .config import NAME`) so tests can `monkeypatch` them.
- Helpers: `grid.py` (`Pos` tuples, `MOVES` canonical order, `obstacles` that frees only tails that actually move, since a stacked tail right after eating stays put), `floodfill.py`, `astar.py`, `voronoi.py` (multi-source BFS territory: ties go to the strictly bigger snake, otherwise the cell is contested). These static versions remain for `trapped_rivals` and their tests; area, territory and food use the temporal versions in `occupancy.py`.
- Strategy reference (flow, every measurement and weight, approximations, budget calibration): `docs/estrategia.md`.
- **Import path constraint:** tests import the code as `src.app.*` from the repo root. The Lambda packages `src/` as its code root with handler `app.main.handler`, though. Imports inside `src/app/` must therefore stay **relative** (`from .models import …`). An absolute `src.app` import will pass the tests and then break in Lambda.
- **Runtime dependencies:** CD runs `pip install -t src -r requirements.txt` to vendor dependencies into `src/` before `cdk deploy`. Any package the Lambda needs must be in `requirements.txt`. `requirements-dev.txt` is for tests and local tooling only.

## Tests

- `tests/app/test_logic.py` calls `logic` directly with a `make_state(head, neck)` helper.
- `tests/app/test_app.py` goes through HTTP with `TestClient` and a `game_state(head, neck)` dict builder.
- `tests/app/test_estrategia.py`, `test_estrategia_v2.py` and `test_estrategia_v3.py` build states with `tests/helpers.py` (`snake`, `make_game`, which also takes `hazards` and `hazard_damage`) and assert exact moves, with an ASCII board comment per `get_move` scenario. `decide` is tested on its own with hand-built `MoveFeatures`.
- `tests/conftest.py` has the `sem_busca` fixture (sets `MAX_SEARCH_DEPTH` to 0) and fake clocks (`relogio_parado`, `relogio_que_conta`, `relogio_que_estoura_em`). Heuristic scenario tests run with `sem_busca` (`pytestmark` in the strategy files); search tests (`test_busca.py`) fix the depth and use a fake clock, so results never depend on machine speed.

The template tests (`test_logic.py`, `test_app.py`) assert invariants over repeated calls (`for _ in range(50)`) and must not be changed. Strategy moves are deterministic whenever at least one candidate exists, given the same sequence of clock readings (in a duel the search depth depends on the clock).

## CI/CD

- `pytest_ci.yml`: runs `pytest` on every push and PR.
- `aws_cd.yml`: on push to `dev`, it runs `pytest` again, vendors dependencies, and runs `cdk deploy` from `iac/` into `sa-east-1`. Authentication uses OIDC (`AWS_DEPLOY_ROLE_ARN`, `AWS_ACCOUNT_ID_DEV` secrets). Failing tests block the deploy. The snake URL is the stack's CfnOutput.
- `aws_destroy.yml`: a manual `cdk destroy`.
- `iac/iac/iac_stack.py`: Lambda (15 s timeout), a public Function URL, an IAM role with the `pb-battlesnake-participant` permissions boundary, and an invocation alarm that notifies the shared `sns-battlesnake` topic. Resources are named `battlesnake-{repo-slug}-*-dev`, with `STACK_NAME`/`PROJECT_NAME`/`REPO_SLUG` env vars set by CI. You can't run `cdk synth` locally without those env vars.

## OpenSpec

The repo uses OpenSpec's spec-driven workflow (`openspec/`, `/opsx:*` commands, `openspec-*` skills in `.claude/`). Specs go in `openspec/specs/` and changes in `openspec/changes/`.
