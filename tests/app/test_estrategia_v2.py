"""Testes da estratégia v2: território, ataque, nova política de fome e a
separação entre características e decisão.

Rode com: pytest tests/app/test_estrategia_v2.py

Nos desenhos ASCII, y cresce para cima (a primeira linha é a de cima):
E = minha cabeça, e = meu corpo, R = cabeça da rival, r = corpo da rival,
* = comida e . = casa livre.
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.app import config
from src.app import decision
from src.app.decision import DecisionContext, MoveFeatures, decide
from src.app.features import build_context, evaluate_moves, target_food, snapshot
from src.app.grid import MOVES, obstacles
from src.app.logic import get_move
from src.app.voronoi import voronoi
from tests.helpers import snake, make_game

EU = "eu"


def test_config_tem_os_valores_iniciais():
    assert (config.HEALTH_MARGIN, config.NO_PATH_HEALTH, config.LENGTH_LEAD) == (15, 50, 2)
    assert (config.START_LENGTH, config.FEED_INTERVAL) == (3, 8)
    assert (config.W_TERRITORY, config.W_FOOD, config.W_TRAP, config.W_KILL) == (1.0, 40, 60, 50)
    assert (config.W_HUNT, config.W_DANGER, config.W_CENTER) == (10, 25, 1)


# --- Cauda empilhada ---

def test_cauda_empilhada_depois_de_comer_nao_e_livre():
    #   x: 3 4 5 6
    # y=10 . e E .     a cauda (4,10) está empilhada: a cobra acabou de comer
    # y=9  . e e .
    # up é parede, down é o pescoço e left é a cauda que não sai do lugar.
    eu = snake(EU, [(5, 10), (5, 9), (4, 9), (4, 10), (4, 10)])
    state = make_game(eu)
    assert get_move(state).move == "right"


def test_cauda_que_sai_do_lugar_e_candidata():
    #   x: 3 4 5 6
    # y=10 . e E .     mesma cobra sem ter comido: a cauda (4,10) sai do lugar
    # y=9  . e e .
    # left e right empatam e left vem antes na ordem canônica.
    eu = snake(EU, [(5, 10), (5, 9), (4, 9), (4, 10)])
    state = make_game(eu)
    assert get_move(state).move == "left"


def test_cauda_de_rival_que_sai_do_lugar_nao_e_obstaculo():
    eu = snake(EU, [(0, 0)])
    rival = snake("rival", [(4, 2), (4, 1)])
    board = make_game(eu, others=[rival], width=5, height=5).board
    assert (4, 2) in obstacles(board)
    assert (4, 1) not in obstacles(board)


def test_cauda_de_rival_empilhada_e_obstaculo():
    eu = snake(EU, [(0, 0)])
    rival = snake("rival", [(4, 3), (4, 2), (4, 2)])
    board = make_game(eu, others=[rival], width=5, height=5).board
    assert {(4, 3), (4, 2)} <= obstacles(board)


# --- Território (Voronoi) ---

def tabuleiro_5x5(*cobras):
    """Tabuleiro 5x5 com as cobras dadas; a primeira faz o papel de `you`."""
    return make_game(cobras[0], others=cobras[1:], width=5, height=5).board


def test_voronoi_tamanhos_iguais_dividem_o_tabuleiro():
    #   x: 0 1 2 3 4
    # y=2  E . ? . R     ? = coluna x=2 disputada
    board = tabuleiro_5x5(snake(EU, [(0, 2)]), snake("rival", [(4, 2)]))
    seeds = {EU: ((0, 2), 0), "rival": ((4, 2), 0)}
    # As casas de origem contam para a própria cobra mesmo bloqueadas.
    assert voronoi(board, seeds, {(0, 2), (4, 2)}) == {EU: 10, "rival": 10}


def test_voronoi_rival_maior_leva_o_empate():
    # A cauda (4,1) da rival sai do lugar, então é casa livre e conta para ela.
    board = tabuleiro_5x5(snake(EU, [(0, 2)]), snake("rival", [(4, 2), (4, 1)]))
    seeds = {EU: ((0, 2), 0), "rival": ((4, 2), 0)}
    assert voronoi(board, seeds, obstacles(board)) == {EU: 10, "rival": 15}


def test_voronoi_semente_com_distancia_inicial_1():
    # Com distância inicial 1, a coluna x=2 fica mais perto da rival.
    board = tabuleiro_5x5(snake(EU, [(0, 2)]), snake("rival", [(4, 2)]))
    seeds = {EU: ((0, 2), 1), "rival": ((4, 2), 0)}
    assert voronoi(board, seeds, obstacles(board)) == {EU: 10, "rival": 15}


def test_voronoi_tres_cobras_de_mesmo_tamanho():
    board = tabuleiro_5x5(
        snake(EU, [(0, 2)]), snake("r1", [(4, 2)]), snake("r2", [(2, 0)])
    )
    seeds = {EU: ((0, 2), 0), "r1": ((4, 2), 0), "r2": ((2, 0), 0)}
    assert voronoi(board, seeds, obstacles(board)) == {EU: 7, "r1": 7, "r2": 4}


def test_voronoi_semente_vizinha_da_rival_continua_sendo_minha():
    # Minha semente (1,2), com distância 1, é vizinha da cabeça da rival maior
    # (0,2): a rival a alcançaria no mesmo nível, mas a casa de origem é minha.
    # Os outros empates vão para a rival, e eu fico com (1,2), (2,2) e (3,2).
    board = tabuleiro_5x5(snake(EU, [(4, 2)]), snake("rival", [(0, 2), (0, 1)]))
    seeds = {EU: ((1, 2), 1), "rival": ((0, 2), 0)}
    assert voronoi(board, seeds, obstacles(board)) == {EU: 3, "rival": 21}


# --- Medições por direção ---

def medir(state, candidates):
    """evaluate_moves indexado pela direção, para os asserts ficarem curtos."""
    return {f.move: f for f in evaluate_moves(state, candidates)}


def test_ordem_canonica_e_a_mesma_do_grid():
    assert tuple(MOVES) == decision.MOVE_ORDER


def test_uma_medicao_por_candidata_na_mesma_ordem():
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3)]))
    features = evaluate_moves(state, ["up", "left", "right"])
    assert [f.move for f in features] == ["up", "left", "right"]


def test_risky_marca_casa_alcancavel_por_rival_igual():
    #   x: 1 2 3 4 5 6
    # y=10 r r R . E .     (4,10) é alcançável pela cabeça da rival
    # y=9  . . . . e .
    eu = snake(EU, [(5, 10), (5, 9), (5, 8)])
    igual = snake("igual", [(3, 10), (2, 10), (1, 10)])
    f = medir(make_game(eu, others=[igual]), ["left", "right"])
    assert f["left"].risky is True
    assert f["right"].risky is False


def test_area_de_bolsao_menor_que_a_cobra():
    #   x: 0 1 2
    # y=3  R . .
    # y=2  . . .
    # y=1  E e e
    # y=0  . e e       a cauda (1,0) sai do lugar: down leva a 2 casas
    eu = snake(EU, [(0, 1), (1, 1), (2, 1), (2, 0), (1, 0)])
    maior = snake("maior", [(0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8)])
    f = medir(make_game(eu, others=[maior]), ["up", "down"])
    assert (f["down"].area, f["down"].roomy) == (2, False)
    assert f["up"].roomy is True


def test_danger_com_rival_igual_a_duas_casas():
    # (6,10) fica a 2 casas da cabeça da rival (4,10).
    eu = snake(EU, [(5, 10), (5, 9), (5, 8)])
    igual = snake("igual", [(4, 10), (3, 10), (2, 10)])
    f = medir(make_game(eu, others=[igual]), ["right"])
    assert f["right"].danger is True


def test_center_dist_no_11x11():
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3)]))
    assert medir(state, ["up"])["up"].center_dist == 1  # (5,6) até (5,5)


# --- Política de fome ---

COBRA_DE_3 = [(5, 5), (5, 4), (5, 3)]
COBRA_DE_8 = [(5, 5), (5, 4), (5, 3), (5, 2), (5, 1), (5, 0), (6, 0), (7, 0)]


def test_fome_por_taxa_de_crescimento():
    # 3 < 3 + 40 // 8
    state = make_game(snake(EU, COBRA_DE_3), turn=40)
    assert build_context(state).hungry is True


def test_sem_fome():
    state = make_game(snake(EU, COBRA_DE_3), turn=1)
    assert build_context(state).hungry is False


def test_fome_por_sobrevivencia_sendo_a_maior():
    # A comida (5,10) está a 5 passos: 19 < 5 + 15. Tamanho 8 contra 3 e turno 1,
    # então as outras duas condições são falsas.
    menor = snake("menor", [(10, 10), (10, 9), (10, 8)])
    state = make_game(snake(EU, COBRA_DE_8, health=19), others=[menor], food=[(5, 10)])
    assert build_context(state).hungry is True


def test_limite_da_sobrevivencia():
    # 20 não é menor que 5 + 15.
    menor = snake("menor", [(10, 10), (10, 9), (10, 8)])
    state = make_game(snake(EU, COBRA_DE_8, health=20), others=[menor], food=[(5, 10)])
    assert build_context(state).hungry is False


def test_fome_por_disputa_de_tamanho_no_contexto():
    # 3 < 6 + 2, mesmo com vida 100.
    grande = snake("grande", [(10, 0), (10, 1), (10, 2), (10, 3), (10, 4), (10, 5)])
    state = make_game(snake(EU, COBRA_DE_3), others=[grande], food=[(2, 5)])
    ctx = build_context(state)
    assert (ctx.hungry, ctx.health, ctx.length, ctx.turn) == (True, 100, 3, 1)


def test_comida_contestada_vira_a_outra():
    #   x: 0 1 2 3 4 5 6 7 8 9 10
    # y=5  . * . . . E . . * . R     (8,5): 3 passos meus, 2 da rival maior
    # y=4  . . . . . e . . . . r
    maior = snake("maior", [(10, 5), (10, 4), (10, 3), (10, 2), (10, 1)])
    state = make_game(snake(EU, COBRA_DE_3), others=[maior], food=[(8, 5), (1, 5)])
    assert target_food(state, snapshot(state).blocked).pos == (1, 5)
    f = medir(state, ["up", "left", "right"])
    assert f["left"].food_step is True
    assert f["right"].food_step is False


def test_primeiro_passo_ate_a_comida():
    state = make_game(snake(EU, COBRA_DE_3), food=[(2, 5)])
    f = medir(state, ["up", "left", "right"])
    assert (f["left"].food_step, f["left"].food_dist) == (True, 2)
    assert (f["up"].food_step, f["up"].food_dist) == (False, 4)


def test_sem_comida_nao_ha_food_step():
    state = make_game(snake(EU, COBRA_DE_3))
    for f in evaluate_moves(state, ["up", "left", "right"]):
        assert (f.food_step, f.food_dist) == (False, None)


# --- Rivais encurraladas ---

ENCURRALADORA = [(2, 9), (1, 9), (1, 8), (1, 7)]
ENCURRALADA = [(0, 10), (0, 9), (0, 8)]


def test_passo_que_fecha_a_unica_saida_encurrala():
    #   x: 0 1 2 3
    # y=10 R . . .     a única saída da rival é (1,10); com a minha cabeça em
    # y=9  r e E .     (2,10), ela fica com 1 casa para um corpo de 3
    # y=8  r e . .
    # y=7  . e . .
    state = make_game(snake(EU, ENCURRALADORA), others=[snake("menor", ENCURRALADA)])
    f = medir(state, ["up", "down", "right"])
    assert f["up"].trapped_rivals == ("menor",)
    assert f["down"].trapped_rivals == ()
    assert f["right"].trapped_rivals == ()


# --- Chance de matar e caça ---

COBRA_DE_4 = [(5, 5), (5, 4), (5, 3), (5, 2)]


def test_kill_chance_na_casa_que_a_rival_menor_pode_ocupar():
    #   x: 4 5 6 7 8 9
    # y=5  . E . R r r     (6,5) é vizinha das duas cabeças
    # y=4  . e . . . .
    menor = snake("menor", [(7, 5), (8, 5), (9, 5)])
    f = medir(make_game(snake(EU, COBRA_DE_4), others=[menor]), ["up", "left", "right"])
    assert (f["right"].kill_chance, f["right"].hunt_step) == (True, True)
    for move in ("up", "left"):
        assert (f[move].kill_chance, f[move].hunt_step) == (False, False)


def test_rival_maior_nao_e_presa():
    maior = snake("maior", [(7, 5), (8, 5), (9, 5), (10, 5), (10, 4)])
    f = medir(make_game(snake(EU, COBRA_DE_4), others=[maior]), ["up", "left", "right"])
    for move in ("up", "left", "right"):
        assert (f[move].kill_chance, f[move].hunt_step) == (False, False)
    assert f["right"].risky is True


# --- Decisão isolada (sem tabuleiro) ---

COM_FOME = DecisionContext(health=50, length=5, turn=10, hungry=True)
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


def test_decide_nao_arriscada_com_espaco_vence_tudo():
    features = [
        feat("up", risky=True, territory_pct=500.0),
        feat("down", territory_pct=0.0),
    ]
    assert decide(features, COM_FOME) == "down"


def test_decide_ordem_das_camadas():
    camada_2 = feat("up", risky=True, roomy=True)
    camada_3 = feat("down", roomy=False, territory_pct=90.0)
    camada_4 = feat("left", risky=True, roomy=False, territory_pct=99.0)
    assert decide([camada_4, camada_3, camada_2], COM_FOME) == "up"
    assert decide([camada_4, camada_3], COM_FOME) == "down"
    assert decide([camada_4], COM_FOME) == "left"


def test_decide_peso_do_territorio():
    features = [feat("up", territory_pct=30.0), feat("down", territory_pct=40.0)]
    assert decide(features, COM_FOME) == "down"


def test_decide_comida_so_pesa_com_fome():
    features = [feat("up", territory_pct=50.0), feat("down", territory_pct=20.0, food_step=True)]
    assert decide(features, COM_FOME) == "down"  # 60 > 50
    assert decide(features, SEM_FOME) == "up"


def test_decide_peso_da_rival_encurralada():
    features = [
        feat("up", trapped_rivals=("rival",), center_dist=3),
        feat("down", territory_pct=59.0, center_dist=3),
    ]
    assert decide(features, SEM_FOME) == "up"  # 60 > 59


def test_decide_peso_da_chance_de_matar():
    features = [feat("up", kill_chance=True), feat("down", territory_pct=49.0)]
    assert decide(features, COM_FOME) == "up"  # 50 > 49


def test_decide_caca_so_pesa_sem_fome():
    features = [
        feat("up", hunt_step=True, center_dist=2),
        feat("down", territory_pct=5.0, center_dist=2),
    ]
    assert decide(features, SEM_FOME) == "up"  # 10 > 5
    assert decide(features, COM_FOME) == "down"


def test_decide_peso_do_perigo():
    features = [feat("up", danger=True, territory_pct=30.0), feat("down", territory_pct=10.0)]
    assert decide(features, COM_FOME) == "down"  # 10 > 30 - 25


def test_decide_centro_so_pesa_sem_fome():
    features = [feat("up", center_dist=8), feat("down", center_dist=2)]
    assert decide(features, SEM_FOME) == "down"
    assert decide(features, COM_FOME) == "up"  # empate: up vem antes


def test_decide_empate_usa_a_ordem_canonica():
    assert decide([feat("right"), feat("up")], COM_FOME) == "up"


def test_decide_lista_vazia_e_erro():
    with pytest.raises(ValueError):
        decide([], COM_FOME)


def test_decisao_nao_importa_models():
    # Mesmo molde do test_lambda: com src/ como raiz, importar a decisão não
    # pode carregar models.py, nem por um import indireto.
    src = Path(__file__).resolve().parents[2] / "src"
    codigo = "import sys, app.decision; assert 'app.models' not in sys.modules"
    result = subprocess.run(
        [sys.executable, "-c", codigo], cwd=src, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# --- Cenários de get_move ---

def test_beco_versus_cabeca_a_cabeca():
    #   x: 0 1 2
    # y=4  r . .
    # y=3  R . .      up é arriscada (a rival maior alcança (0,2)), mas leva
    # y=2  . . .      ao resto do tabuleiro; down é segura e dá num bolsão de
    # y=1  E e e      2 casas, menor que a cobra
    # y=0  . e e
    eu = snake(EU, [(0, 1), (1, 1), (2, 1), (2, 0), (1, 0)])
    maior = snake("maior", [(0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8)])
    assert get_move(make_game(eu, others=[maior])).move == "up"


def test_nao_morde_a_isca():
    #   x: 4 5 6 7 8 9 10
    # y=5  . E . R r r r      a rival é maior: entrar em (6,5) é arriscado
    # y=4  . e . . . . r
    maior = snake("maior", [(7, 5), (8, 5), (9, 5), (10, 5), (10, 4)])
    assert get_move(make_game(snake(EU, COBRA_DE_4), others=[maior])).move == "left"


def test_encurrala_a_rival_menor():
    #   x: 0 1 2 3 4 5
    # y=10 R . . . . .     up fecha a única saída da rival (vale 60);
    # y=9  r e E . . *     right é o primeiro passo até a comida (vale 40)
    # y=8  r e . . . .
    # y=7  . e . . . .
    state = make_game(
        snake(EU, ENCURRALADORA), others=[snake("menor", ENCURRALADA)], food=[(5, 9)]
    )
    assert get_move(state).move == "up"


def test_peso_alterado_muda_a_escolha(monkeypatch):
    # Sem o bônus de rival encurralada, a comida volta a decidir.
    monkeypatch.setattr(config, "W_TRAP", 0)
    state = make_game(
        snake(EU, ENCURRALADORA), others=[snake("menor", ENCURRALADA)], food=[(5, 9)]
    )
    assert get_move(state).move == "right"


def test_ataca_a_rival_menor():
    #   x: 4 5 6 7 8 9
    # y=8  . * . . . .     up é o primeiro passo até a comida (vale 40);
    # y=7  . . . . . .     right cai na casa que a rival menor pode ocupar
    # y=6  . . . . . .     (vale 50)
    # y=5  . E . R r r
    # y=4  . e . . . .
    menor = snake("menor", [(7, 5), (8, 5), (9, 5)])
    state = make_game(snake(EU, COBRA_DE_4), others=[menor], food=[(5, 8)])
    assert get_move(state).move == "right"


def test_fome_por_disputa_de_tamanho_segue_a_comida():
    #   x: 0 1 2 3 4 5 6 7 8 9 10
    # y=5  . . * . . E . . . . R     vida 100, mas a rival tem 6 contra 3
    # y=4  . . . . . e . . . . r
    # y=3  . . . . . e . . . . r
    grande = snake("grande", [(10, 0), (10, 1), (10, 2), (10, 3), (10, 4), (10, 5)])
    state = make_game(snake(EU, COBRA_DE_3), others=[grande], food=[(2, 5)])
    assert get_move(state).move == "left"


def test_comida_contestada_get_move():
    #   x: 0 1 2 3 4 5 6 7 8 9 10
    # y=5  . * . . . E . . * . R     vai para (1,5): a rival chega antes em (8,5)
    maior = snake("maior", [(10, 5), (10, 4), (10, 3), (10, 2), (10, 1)])
    state = make_game(snake(EU, COBRA_DE_3), others=[maior], food=[(8, 5), (1, 5)])
    assert get_move(state).move == "left"


# --- Desempenho e determinismo ---

def serpente(id: str, x0: int) -> dict:
    """Cobra de tamanho 15 em zigue-zague: sobe a coluna x0 e desce a x0+1."""
    body = [(x0, y) for y in range(9, 1, -1)] + [(x0 + 1, y) for y in range(2, 9)]
    return snake(id, body)


def tabuleiro_grande():
    """19x19 com 4 cobras de tamanho 15, 5 comidas e turno 60."""
    cobras = [serpente(EU, 1), serpente("r1", 6), serpente("r2", 11), serpente("r3", 16)]
    return make_game(
        cobras[0], others=cobras[1:],
        food=[(3, 15), (9, 17), (14, 12), (17, 1), (0, 18)],
        width=19, height=19, turn=60,
    )


def test_jogada_completa_cabe_em_50_ms():
    state = tabuleiro_grande()
    assert all(s.length == 15 for s in state.board.snakes)
    # O melhor de várias medições filtra a flutuação de máquina no CI.
    tempos = []
    for _ in range(10):
        inicio = time.perf_counter()
        get_move(state)
        tempos.append(time.perf_counter() - inicio)
    assert min(tempos) < 0.050, f"melhor tempo: {min(tempos) * 1000:.1f} ms"


def test_mesmo_estado_mesma_resposta():
    state = tabuleiro_grande()
    respostas = {get_move(state).move for _ in range(20)}
    assert len(respostas) == 1
