"""Montadores de estado de jogo para os testes de estratégia.

O JSON montado aqui passa por GameState.model_validate, o mesmo caminho
que o /move percorre em produção.
"""
from src.app.models import GameState


def snake(id: str, body: list[tuple[int, int]], health: int = 100) -> dict:
    """Monta o dict de uma cobra a partir de uma lista de (x, y). body[0] é a cabeça."""
    coords = [{"x": x, "y": y} for x, y in body]
    return {
        "id": id,
        "name": id,
        "health": health,
        "body": coords,
        "head": coords[0],
        "length": len(coords),
        "latency": "0",
        "shout": "",
    }


def make_game(
    you: dict,
    others=(),
    food=(),
    width: int = 11,
    height: int = 11,
    turn: int = 1,
) -> GameState:
    """Monta o estado do /move com `you` em board.snakes, seguido de `others`."""
    return GameState.model_validate({
        "game": {
            "id": "partida-de-teste",
            "ruleset": {"name": "standard", "version": "v1.2.3"},
            "map": "standard",
            "timeout": 500,
        },
        "turn": turn,
        "board": {
            "height": height,
            "width": width,
            "food": [{"x": x, "y": y} for x, y in food],
            "hazards": [],
            "snakes": [you, *others],
        },
        "you": you,
    })
