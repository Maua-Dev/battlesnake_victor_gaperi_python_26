"""Testes da estratégia v3: vida e hazards no filtro, ocupação temporal nas
medições, sobrevivência, comida alvo pelo território e as parcelas novas.

Rode com: pytest tests/app/test_estrategia_v3.py

Nos desenhos ASCII, y cresce para cima (a primeira linha é a de cima):
E = minha cabeça, e = meu corpo, R = cabeça da rival, r = corpo da rival,
* = comida, h = hazard e . = casa livre.

Os cenários de get_move testam a escolha heurística: a busca do duelo fica
desligada (fixture sem_busca, em tests/conftest.py).
"""
import random
import time

import pytest

from src.app import logic
from src.app.decision import DecisionContext, MoveFeatures, decide, explain
from src.app.features import build_context, evaluate_moves, snapshot
from src.app.logic import get_move
from tests.helpers import snake, make_game

EU = "eu"
COBRA_DE_3 = [(5, 5), (5, 4), (5, 3)]

pytestmark = pytest.mark.usefixtures("sem_busca")


@pytest.fixture
def candidatas(monkeypatch):
    """Função estado -> candidatas que get_move entregou a choose_move.

    O espião repassa a chamada ao choose_move original: a resposta de
    get_move não muda.
    """
    original = logic.choose_move
    recebidas: list[list[str]] = []

    def espiao(state, safe_moves, **kwargs):
        recebidas.append(list(safe_moves))
        return original(state, safe_moves, **kwargs)

    monkeypatch.setattr(logic, "choose_move", espiao)

    def ler(state) -> list[str]:
        recebidas.clear()
        get_move(state)
        return recebidas[0] if recebidas else []
    return ler


# --- Vida e hazards no filtro ---

def test_vida_1_so_sobrevive_comendo(candidatas):
    #   x: 3 4 5 6
    # y=6  . . . .     vida 1: só a casa com comida não mata de fome
    # y=5  . * E .
    # y=4  . . e .
    state = make_game(snake(EU, COBRA_DE_3, health=1), food=[(4, 5)])
    assert candidatas(state) == ["left"]
    assert get_move(state).move == "left"


def test_hazard_que_zera_a_vida(candidatas):
    #   x: 3 4 5 6
    # y=6  . . h .     vida 10, dano 14: up e left zerariam a vida
    # y=5  . h E .
    # y=4  . . e .
    state = make_game(
        snake(EU, COBRA_DE_3, health=10), hazards=[(5, 6), (4, 5)], hazard_damage=14
    )
    assert candidatas(state) == ["right"]
    assert get_move(state).move == "right"


def test_hazards_empilhados(candidatas):
    #   x: 4 5 6
    # y=6  . h .     vida 15, dano 7: (5,6) duas vezes na lista dá
    # y=5  . E .     15 - 1 - 14 = 0; uma vez só dá 7
    # y=4  . e .
    duas_vezes = make_game(
        snake(EU, COBRA_DE_3, health=15), hazards=[(5, 6), (5, 6)], hazard_damage=7
    )
    assert "up" not in candidatas(duas_vezes)
    uma_vez = make_game(snake(EU, COBRA_DE_3, health=15), hazards=[(5, 6)], hazard_damage=7)
    assert "up" in candidatas(uma_vez)


def test_comida_no_hazard(candidatas):
    #   x: 4 5 6
    # y=6  . * .     (5,6) é hazard e tem comida: o dano não se aplica
    # y=5  . E .
    state = make_game(
        snake(EU, COBRA_DE_3, health=5), food=[(5, 6)], hazards=[(5, 6)], hazard_damage=14
    )
    assert "up" in candidatas(state)


def test_hazard_sem_dano_nao_elimina(candidatas):
    state = make_game(snake(EU, COBRA_DE_3, health=2), hazards=[(5, 6)])
    assert candidatas(state) == ["up", "left", "right"]


# --- Medições novas ---

def medir(state, candidates):
    """evaluate_moves indexado pela direção, para os asserts ficarem curtos."""
    return {f.move: f for f in evaluate_moves(state, candidates)}


def test_medicao_montada_sem_os_campos_novos():
    f = MoveFeatures(
        move="up", risky=False, area=10, roomy=True, territory_pct=0.0,
        food_step=False, food_dist=None, trapped_rivals=(), kill_chance=False,
        hunt_step=False, danger=False, center_dist=0,
    )
    assert (f.survival_depth, f.survives, f.hazard) == (0, True, False)
    assert (f.rival_territory_pct, f.food_owned) == (0.0, False)


def test_sobrevivencia_nas_medicoes():
    # Tabuleiro vazio: toda candidata chega à profundidade alvo (tamanho 3).
    f = medir(make_game(snake(EU, COBRA_DE_3)), ["up", "left", "right"])
    for move in ("up", "left", "right"):
        assert (f[move].survival_depth, f[move].survives) == (3, True)


def test_territorio_da_adversaria_no_duelo():
    #   x: 0 1 2 3 4 5 6 7 8 9 10
    # y=5  . . . . . E . . . R r     a rival fica com o lado direito
    # y=4  . . . . . e . . . . r
    rival = snake("rival", [(9, 5), (10, 5), (10, 4)])
    state = make_game(snake(EU, COBRA_DE_3), others=[rival])
    snap = snapshot(state)
    f = medir(state, ["up", "left", "right"])
    for move in ("up", "left", "right"):
        assert 0 < f[move].rival_territory_pct < 100
    # Andar para a direita aperta o território da rival.
    assert f["right"].rival_territory_pct < f["left"].rival_territory_pct
    # Os percentuais das duas cobras nunca passam do total de casas livres.
    for move in f:
        assert f[move].territory_pct + f[move].rival_territory_pct <= 100 + 1e-9
    # 6 casas de cobra, menos as duas caudas que saem do lugar.
    assert snap.free_cells == 121 - 4


def test_sem_adversarias_o_territorio_da_rival_e_zero():
    f = medir(make_game(snake(EU, COBRA_DE_3)), ["up"])
    assert f["up"].rival_territory_pct == 0.0


def test_comida_no_meu_territorio():
    state = make_game(snake(EU, COBRA_DE_3), food=[(2, 5)])
    for f in evaluate_moves(state, ["up", "left", "right"]):
        assert f.food_owned is True


def test_sem_comida_nao_ha_food_owned():
    for f in evaluate_moves(make_game(snake(EU, COBRA_DE_3)), ["up", "left", "right"]):
        assert (f.food_step, f.food_dist, f.food_owned) == (False, None, False)


def test_casa_de_hazard():
    state = make_game(snake(EU, COBRA_DE_3), hazards=[(5, 6)], hazard_damage=14)
    f = medir(state, ["up", "left", "right"])
    assert f["up"].hazard is True
    assert (f["left"].hazard, f["right"].hazard) == (False, False)


def test_hazard_sem_dano():
    state = make_game(snake(EU, COBRA_DE_3), hazards=[(5, 6)])
    assert medir(state, ["up"])["up"].hazard is False


def test_hazard_com_comida_nao_conta():
    state = make_game(snake(EU, COBRA_DE_3), food=[(5, 6)], hazards=[(5, 6)], hazard_damage=14)
    assert medir(state, ["up"])["up"].hazard is False


# --- Comida alvo e fome ---

def test_empate_com_rival_do_mesmo_tamanho():
    #   x: 0 1 2 3 4 5 6 7 8 9 10
    # y=5  . . * . . E . * . R r     (7,5) fica a 2 passos de cada cabeça:
    # y=4  . . . . . e . . . . r     disputada, não é minha
    rival = snake("rival", [(9, 5), (10, 5), (10, 4)])
    state = make_game(snake(EU, COBRA_DE_3), others=[rival], food=[(7, 5), (2, 5)])
    assert snapshot(state).target.pos == (2, 5)
    assert get_move(state).move == "left"


def test_hazard_no_caminho_ate_a_comida():
    #   x: 4 5 6
    # y=8  . * .     vida 30: o caminho de 3 passos custa 3 + 14 por causa
    # y=7  . . .     do hazard em (5,6); 30 < 17 + 15 é fome
    # y=6  . h .
    # y=5  . E .
    com_hazard = make_game(
        snake(EU, COBRA_DE_3, health=30), food=[(5, 8)], hazards=[(5, 6)], hazard_damage=14
    )
    snap = snapshot(com_hazard)
    assert (snap.target.dist, snap.target.cost) == (3, 17)
    assert build_context(com_hazard).hungry is True

    sem_hazard = make_game(snake(EU, COBRA_DE_3, health=30), food=[(5, 8)])
    assert snapshot(sem_hazard).target.cost == 3
    assert build_context(sem_hazard).hungry is False


# --- Pesos novos da decisão ---

COM_FOME = DecisionContext(health=50, length=5, turn=10, hungry=True)


def feat(move: str, **campos) -> MoveFeatures:
    """MoveFeatures com valores neutros: segura, com espaço e tudo zerado."""
    neutros = dict(
        risky=False, area=50, roomy=True, territory_pct=0.0, food_step=False,
        food_dist=None, trapped_rivals=(), kill_chance=False, hunt_step=False,
        danger=False, center_dist=0,
    )
    neutros.update(campos)
    return MoveFeatures(move=move, **neutros)


def test_decide_peso_da_sobrevivencia():
    features = [feat("up", survival_depth=5), feat("down", territory_pct=19.0)]
    assert decide(features, COM_FOME) == "up"  # 20 > 19


def test_decide_sobrevivencia_com_alvo_limitado():
    # Tamanho 30 e limite 12: a profundidade 12 já vale o peso inteiro.
    ctx = DecisionContext(health=50, length=30, turn=10, hungry=True)
    [avaliada] = explain([feat("up", survival_depth=12)], ctx).ranking
    assert avaliada.terms["survival"] == 20


def test_decide_peso_do_hazard():
    features = [feat("up", hazard=True, territory_pct=40.0), feat("down", territory_pct=15.0)]
    assert decide(features, COM_FOME) == "down"  # 15 > 40 - 30


def test_decide_peso_do_cerco():
    features = [
        feat("up", territory_pct=30.0, rival_territory_pct=40.0),
        feat("down", territory_pct=20.0),
    ]
    assert decide(features, COM_FOME) == "down"  # 20 > 30 - 20


def test_parcelas_novas_na_explicacao():
    f = feat("up", survival_depth=5, hazard=True, rival_territory_pct=40.0)
    [avaliada] = explain([f], COM_FOME).ranking
    assert avaliada.terms["survival"] == 20
    assert avaliada.terms["hazard"] == -30
    assert avaliada.terms["squeeze"] == -20
    assert avaliada.score == sum(avaliada.terms.values())


def test_contexto_com_tamanho_zero_nao_divide_por_zero():
    ctx = DecisionContext(health=50, length=0, turn=0, hungry=True)
    [avaliada] = explain([feat("up", survival_depth=1)], ctx).ranking
    assert avaliada.terms["survival"] == 20


# --- Desempenho da fase heurística ---

def corpo_de_6(rng: random.Random, ocupadas: set) -> list[tuple[int, int]]:
    """Passeio aleatório de exatamente 6 casas num 11x11, fora de ocupadas."""
    while True:
        corpo = [(rng.randrange(11), rng.randrange(11))]
        if corpo[0] in ocupadas:
            continue
        while len(corpo) < 6:
            x, y = corpo[-1]
            opcoes = [
                (x + dx, y + dy) for dx, dy in ((0, 1), (0, -1), (-1, 0), (1, 0))
                if 0 <= x + dx < 11 and 0 <= y + dy < 11
                and (x + dx, y + dy) not in ocupadas and (x + dx, y + dy) not in corpo
            ]
            if not opcoes:
                break
            corpo.append(rng.choice(opcoes))
        if len(corpo) == 6:
            return corpo


def oito_cobras_de_6():
    """11x11 com 8 cobras de tamanho 6, corpos sorteados com semente fixa."""
    rng = random.Random(8)
    ocupadas: set = set()
    cobras = []
    for i in range(8):
        corpo = corpo_de_6(rng, ocupadas)
        ocupadas.update(corpo)
        cobras.append(snake(EU if i == 0 else f"r{i}", corpo))
    return make_game(cobras[0], others=cobras[1:], food=[(2, 2), (8, 3), (5, 8)], turn=30)


def test_fase_heuristica_com_oito_cobras_cabe_em_10_ms():
    state = oito_cobras_de_6()
    assert [s.length for s in state.board.snakes] == [6] * 8
    # Com 8 cobras a busca não roda: get_move é só a fase heurística.
    tempos = []
    for _ in range(10):
        inicio = time.perf_counter()
        get_move(state)
        tempos.append(time.perf_counter() - inicio)
    assert min(tempos) < 0.010, f"melhor tempo: {min(tempos) * 1000:.1f} ms"
