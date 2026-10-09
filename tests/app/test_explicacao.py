"""Testes da explicação da decisão (decision.explain).

Rode com: pytest tests/app/test_explicacao.py

explain é a própria decide devolvendo também o porquê: a camada, a pontuação
e as parcelas de cada medição e o motivo da escolha.
"""
import pytest

from src.app.decision import DecisionContext, MoveFeatures, decide, explain, score

COM_FOME = DecisionContext(health=10, length=5, turn=10, hungry=True)
SEM_FOME = DecisionContext(health=100, length=5, turn=10, hungry=False)


def feat(move: str, **campos) -> MoveFeatures:
    """MoveFeatures com valores neutros: segura, com espaço e tudo zerado."""
    neutros = dict(
        risky=False, area=50, roomy=True, territory_pct=0.0, food_step=False,
        food_dist=None, trapped_rivals=(), kill_chance=False, hunt_step=False,
        danger=False, center_dist=0,
    )
    neutros.update(campos)
    return MoveFeatures(move=move, **neutros)


def por_move(decisao) -> dict:
    return {r.move: r for r in decisao.ranking}


def test_explain_unica_medicao():
    decisao = explain([feat("left")], SEM_FOME)
    assert (decisao.move, decisao.reason) == ("left", "only_option")


def test_explain_vence_pela_camada():
    decisao = explain(
        [feat("up", risky=True, territory_pct=500.0), feat("down")], COM_FOME
    )
    assert (decisao.move, decisao.reason) == ("down", "layer")
    assert por_move(decisao)["up"].layer == 1
    assert por_move(decisao)["down"].layer == 0


def test_explain_vence_pela_pontuacao():
    decisao = explain(
        [feat("up", territory_pct=50.0), feat("down", territory_pct=20.0, food_step=True)],
        COM_FOME,
    )
    assert (decisao.move, decisao.reason) == ("down", "score")
    termos = por_move(decisao)["down"].terms
    assert termos["territory"] == 20
    assert termos["food"] == 40


def test_explain_empate_com_lista_fora_de_ordem():
    decisao = explain([feat("right"), feat("up")], COM_FOME)
    assert (decisao.move, decisao.reason) == ("up", "tie")


def test_explain_lista_vazia_e_erro():
    with pytest.raises(ValueError):
        explain([], COM_FOME)


# As medições dos cenários de decide em test_estrategia_v2.py, remontadas.
MEDICOES = [
    [feat("up", risky=True, territory_pct=500.0), feat("down", territory_pct=0.0)],
    [feat("left", risky=True, roomy=False, territory_pct=99.0),
     feat("down", roomy=False, territory_pct=90.0), feat("up", risky=True)],
    [feat("up", territory_pct=30.0), feat("down", territory_pct=40.0)],
    [feat("up", territory_pct=50.0), feat("down", territory_pct=20.0, food_step=True)],
    [feat("up", trapped_rivals=("rival",), center_dist=3),
     feat("down", territory_pct=59.0, center_dist=3)],
    [feat("up", kill_chance=True), feat("down", territory_pct=49.0)],
    [feat("up", hunt_step=True, center_dist=2), feat("down", territory_pct=5.0, center_dist=2)],
    [feat("up", danger=True, territory_pct=30.0), feat("down", territory_pct=10.0)],
    [feat("up", center_dist=8), feat("down", center_dist=2)],
    [feat("right", territory_pct=33.333333333333336, center_dist=4),
     feat("up", territory_pct=12.1, danger=True, hunt_step=True)],
    [feat("up", survival_depth=5, hazard=True, rival_territory_pct=40.0, territory_pct=60.0),
     feat("down", survival_depth=3, territory_pct=20.0),
     feat("left", survival_depth=5, survives=False, rival_territory_pct=12.5)],
]


@pytest.mark.parametrize("medicoes", MEDICOES)
@pytest.mark.parametrize("ctx", [COM_FOME, SEM_FOME])
def test_explain_e_coerente_com_decide(medicoes, ctx):
    decisao = explain(medicoes, ctx)
    assert decisao.move == decide(medicoes, ctx)
    for f in medicoes:
        avaliada = por_move(decisao)[f.move]
        assert avaliada.score == score(f, ctx) == sum(avaliada.terms.values())
