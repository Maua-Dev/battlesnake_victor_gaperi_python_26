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

- `src/app/main.py`: the FastAPI routes (`GET /`, `POST /start|/move|/end`) delegate to `logic.info/start/get_move/end`. It also has a middleware that strips a leading stage segment (`/dev`, `/prod`, …) from the path, and `handler = Mangum(app)` is the Lambda entry point. `/move` uses `response_model_exclude_none=True` so that `shout` is omitted rather than sent as `null`.
- `src/app/models.py`: Pydantic models for the Battlesnake request payload (`GameState` → `Board`, `Snake`, `Coord`, `Game`) plus `MoveResponse`. Coordinates start at (0,0) in the bottom-left corner, so `up` is `y+1`. `body[0]` is the head.
- `src/app/logic.py`: `get_move` builds an `is_move_safe` dict and filters out certain death (neck/backwards, walls, own body, opponent bodies including their tails). The leftover `safe_moves` are the candidates. If none are left, it picks a random direction of the four, which is the only randomness. Otherwise `choose_move` runs the three-step decision below. The game allows about 500 ms per move. The strategy budget is 50 ms on a 19x19 with 4 snakes, and the rest is reserved for a future external decision model (Jev).
- **Three-step decision:** candidates (`get_move`) → features (`src/app/features.py`: `snapshot`, `build_context`, `evaluate_moves` returning one `MoveFeatures` per candidate, with no choice made) → decision (`src/app/decision.py`: `decide(features, context)`, safety layers, then score, then canonical-order tiebreak). A head-to-head against an equal or bigger rival marks a move `risky` instead of removing it.
- **`decision.py` must not import `models.py`** (directly or transitively; it may only import `config`), because Jev will replace `decide` using `MoveFeatures` + `DecisionContext` as its context. `tests/app/test_estrategia_v2.py::test_decisao_nao_importa_models` enforces this.
- `src/app/config.py` holds every tuning weight and threshold. Read them as `config.NAME` at use time (never `from .config import NAME`) so tests can `monkeypatch` them.
- Helpers: `grid.py` (`Pos` tuples, `MOVES` canonical order, `obstacles` that frees only tails that actually move, since a stacked tail right after eating stays put), `floodfill.py`, `astar.py`, `voronoi.py` (multi-source BFS territory: ties go to the strictly bigger snake, otherwise the cell is contested).
- **Import path constraint:** tests import the code as `src.app.*` from the repo root. The Lambda packages `src/` as its code root with handler `app.main.handler`, though. Imports inside `src/app/` must therefore stay **relative** (`from .models import …`). An absolute `src.app` import will pass the tests and then break in Lambda.
- **Runtime dependencies:** CD runs `pip install -t src -r requirements.txt` to vendor dependencies into `src/` before `cdk deploy`. Any package the Lambda needs must be in `requirements.txt`. `requirements-dev.txt` is for tests and local tooling only.

## Tests

- `tests/app/test_logic.py` calls `logic` directly with a `make_state(head, neck)` helper.
- `tests/app/test_app.py` goes through HTTP with `TestClient` and a `game_state(head, neck)` dict builder.
- `tests/app/test_estrategia.py` and `tests/app/test_estrategia_v2.py` build states with `tests/helpers.py` (`snake`, `make_game`) and assert exact moves, with an ASCII board comment per `get_move` scenario. `decide` is tested on its own with hand-built `MoveFeatures`.

The template tests (`test_logic.py`, `test_app.py`) assert invariants over repeated calls (`for _ in range(50)`) and must not be changed. Strategy moves are deterministic whenever at least one candidate exists.

## CI/CD

- `pytest_ci.yml`: runs `pytest` on every push and PR.
- `aws_cd.yml`: on push to `dev`, it runs `pytest` again, vendors dependencies, and runs `cdk deploy` from `iac/` into `sa-east-1`. Authentication uses OIDC (`AWS_DEPLOY_ROLE_ARN`, `AWS_ACCOUNT_ID_DEV` secrets). Failing tests block the deploy. The snake URL is the stack's CfnOutput.
- `aws_destroy.yml`: a manual `cdk destroy`.
- `iac/iac/iac_stack.py`: Lambda (15 s timeout), a public Function URL, an IAM role with the `pb-battlesnake-participant` permissions boundary, and an invocation alarm that notifies the shared `sns-battlesnake` topic. Resources are named `battlesnake-{repo-slug}-*-dev`, with `STACK_NAME`/`PROJECT_NAME`/`REPO_SLUG` env vars set by CI. You can't run `cdk synth` locally without those env vars.

## OpenSpec

The repo uses OpenSpec's spec-driven workflow (`openspec/`, `/opsx:*` commands, `openspec-*` skills in `.claude/`). Specs go in `openspec/specs/` and changes in `openspec/changes/`.
