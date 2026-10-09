"""Decisão: transforma as medições de cada direção num único movimento.

Este módulo é o ponto em que um modelo de decisão externo vai entrar no
futuro. Por isso ele só conhece MoveFeatures e DecisionContext e NÃO pode
importar models.py, grid.py nem nada que dependa do GameState: o único
import do app permitido aqui é config.
"""
from dataclasses import dataclass

from . import config

# Ordem canônica dos movimentos (a mesma de grid.MOVES, que não pode ser
# importado daqui porque puxaria models.py). Em todo empate vence a primeira.
MOVE_ORDER = ("up", "down", "left", "right")


@dataclass(frozen=True)
class MoveFeatures:
    """O que foi medido para uma direção candidata. Não decide nada."""
    move: str
    # Uma rival de tamanho maior ou igual alcança a mesma casa no próximo turno.
    risky: bool
    # Casas alcançáveis a partir da nova cabeça, e se cabem a cobra inteira.
    area: int
    roomy: bool
    # 100 * casas do meu território / casas livres do tabuleiro.
    territory_pct: float
    # A direção é o primeiro passo do A* até a comida alvo.
    food_step: bool
    # Passos do A* da nova cabeça até a comida alvo, ou None.
    food_dist: int | None
    # Ids das rivais que ficam sem espaço depois deste movimento.
    trapped_rivals: tuple[str, ...]
    # A nova cabeça cai numa casa que uma rival estritamente menor pode ocupar.
    kill_chance: bool
    # Aproxima da rival estritamente menor mais próxima.
    hunt_step: bool
    # Rival de tamanho maior ou igual a duas casas da nova cabeça.
    danger: bool
    # Distância de Manhattan da nova cabeça até o centro do tabuleiro.
    center_dist: int


@dataclass(frozen=True)
class DecisionContext:
    """O que a decisão sabe da jogada além das medições."""
    health: int
    length: int
    turn: int
    hungry: bool


def layer(f: MoveFeatures) -> int:
    """Camada de segurança, da preferida (0) para a pior (3).

    Um cabeça a cabeça incerto (risky) é preferível a um beco certo (sem roomy).
    """
    if f.roomy:
        return 0 if not f.risky else 1
    return 2 if not f.risky else 3


def score_terms(f: MoveFeatures, ctx: DecisionContext) -> dict[str, float]:
    """As parcelas da nota, na ordem da soma; condição falsa vale 0.

    Os pesos vêm de config. danger e center entram negativas.
    """
    return {
        "territory": config.W_TERRITORY * f.territory_pct,
        "food": config.W_FOOD if ctx.hungry and f.food_step else 0,
        "trap": config.W_TRAP * len(f.trapped_rivals),
        "kill": config.W_KILL if f.kill_chance else 0,
        "hunt": config.W_HUNT if f.hunt_step and not ctx.hungry else 0,
        "danger": -config.W_DANGER if f.danger else 0,
        "center": -config.W_CENTER * f.center_dist if not ctx.hungry else 0,
    }


def score(f: MoveFeatures, ctx: DecisionContext) -> float:
    """Nota de uma direção dentro da camada: a soma das parcelas."""
    return sum(score_terms(f, ctx).values())


@dataclass(frozen=True)
class RankedMove:
    """Uma candidata já avaliada: camada, nota e as parcelas da nota."""
    move: str
    layer: int
    score: float
    terms: dict[str, float]


@dataclass(frozen=True)
class Decision:
    """O movimento escolhido, o motivo e todas as candidatas, da melhor
    para a pior.

    reason é um entre:
      only_option  havia uma única candidata;
      layer        a escolhida era a única na melhor camada;
      score        nota estritamente maior que as outras da mesma camada;
      tie          mesma camada e mesma nota, a ordem canônica desempatou.
    """
    move: str
    reason: str
    ranking: tuple[RankedMove, ...]


def explain(features: list[MoveFeatures], ctx: DecisionContext) -> Decision:
    """A decisão com o porquê: primeira camada não vazia, maior nota e, no
    empate, a primeira direção de MOVE_ORDER (não importa a ordem da lista).
    """
    if not features:
        raise ValueError("decide precisa de ao menos uma candidata")
    ranking = []
    for f in features:
        terms = score_terms(f, ctx)
        ranking.append(RankedMove(f.move, layer(f), sum(terms.values()), terms))
    ranking.sort(key=lambda r: (r.layer, -r.score, MOVE_ORDER.index(r.move)))

    best = ranking[0]
    if len(ranking) == 1:
        reason = "only_option"
    elif ranking[1].layer != best.layer:
        reason = "layer"
    elif ranking[1].score != best.score:
        reason = "score"
    else:
        reason = "tie"
    return Decision(best.move, reason, tuple(ranking))


def decide(features: list[MoveFeatures], ctx: DecisionContext) -> str:
    """Escolhe o movimento; o porquê está em explain."""
    return explain(features, ctx).move
