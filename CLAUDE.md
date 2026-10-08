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
- `src/app/logic.py`: `get_move` builds an `is_move_safe` dict, filters out unsafe directions (neck/backwards, walls, own body), and picks one of the remaining safe moves at random. If none are safe, it picks a random direction of the four rather than raising an error. Avoiding opponents and seeking food are still TODOs. The game allows about 500 ms per move.
- **Import path constraint:** tests import the code as `src.app.*` from the repo root. The Lambda packages `src/` as its code root with handler `app.main.handler`, though. Imports inside `src/app/` must therefore stay **relative** (`from .models import …`). An absolute `src.app` import will pass the tests and then break in Lambda.
- **Runtime dependencies:** CD runs `pip install -t src -r requirements.txt` to vendor dependencies into `src/` before `cdk deploy`. Any package the Lambda needs must be in `requirements.txt`. `requirements-dev.txt` is for tests and local tooling only.

## Tests

- `tests/app/test_logic.py` calls `logic` directly with a `make_state(head, neck)` helper.
- `tests/app/test_app.py` goes through HTTP with `TestClient` and a `game_state(head, neck)` dict builder.

Moves are random, so tests assert invariants over repeated calls (`for _ in range(50)`) rather than exact outputs, except where only one move is legal.

## CI/CD

- `pytest_ci.yml`: runs `pytest` on every push and PR.
- `aws_cd.yml`: on push to `dev`, it runs `pytest` again, vendors dependencies, and runs `cdk deploy` from `iac/` into `sa-east-1`. Authentication uses OIDC (`AWS_DEPLOY_ROLE_ARN`, `AWS_ACCOUNT_ID_DEV` secrets). Failing tests block the deploy. The snake URL is the stack's CfnOutput.
- `aws_destroy.yml`: a manual `cdk destroy`.
- `iac/iac/iac_stack.py`: Lambda (15 s timeout), a public Function URL, an IAM role with the `pb-battlesnake-participant` permissions boundary, and an invocation alarm that notifies the shared `sns-battlesnake` topic. Resources are named `battlesnake-{repo-slug}-*-dev`, with `STACK_NAME`/`PROJECT_NAME`/`REPO_SLUG` env vars set by CI. You can't run `cdk synth` locally without those env vars.

## OpenSpec

The repo uses OpenSpec's spec-driven workflow (`openspec/`, `/opsx:*` commands, `openspec-*` skills in `.claude/`). Specs go in `openspec/specs/` and changes in `openspec/changes/`.
