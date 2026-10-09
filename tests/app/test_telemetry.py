"""Testes dos logs estruturados de diagnóstico (src/app/telemetry.py).

Rode com: pytest tests/app/test_telemetry.py

Cada evento é uma linha JSON no stdout; o fixture `eventos` lê o que foi
capturado e devolve a lista de objetos.
"""
import json
import logging

import pytest

from src.app import telemetry
from src.app.telemetry import log_event


@pytest.fixture
def eventos(capsys):
    """Função que devolve os eventos emitidos desde a última chamada."""
    def ler(nome: str | None = None) -> list[dict]:
        linhas = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
        lidos = []
        for linha in linhas:
            try:
                lidos.append(json.loads(linha))
            except json.JSONDecodeError:
                pytest.fail(f"linha que não é JSON: {linha!r}")
        assert all(isinstance(e, dict) for e in lidos)
        if nome is not None:
            lidos = [e for e in lidos if e["event"] == nome]
        return lidos
    ler()  # descarta o que veio antes do teste
    return ler


@pytest.fixture
def nivel():
    """Troca o nível do logger battlesnake só durante o teste."""
    original = telemetry.logger.level
    yield telemetry.logger.setLevel
    telemetry.logger.setLevel(original)


# --- Formato ---

def test_toda_linha_e_um_objeto_json(eventos):
    log_event("teste", valor=1)
    [evento] = eventos()
    assert evento["event"] == "teste"
    assert evento["ts"].endswith("Z")
    assert evento["valor"] == 1
    for campo in telemetry.COMMON_FIELDS:
        assert campo in evento and evento[campo] is None


def test_sem_duplicacao(eventos):
    log_event("unico")
    assert len(eventos("unico")) == 1
    assert telemetry.logger.propagate is False


def test_texto_nao_ascii_sai_literal(capsys):
    log_event("teste", texto="ção")
    assert "ção" in capsys.readouterr().out


def test_so_erros(eventos, nivel):
    nivel(logging.ERROR)
    log_event("teste")
    telemetry.log_error(path="/move", exception="X", message="", traceback="")
    assert [e["event"] for e in eventos()] == ["error"]


def test_campo_nao_serializavel_nao_lanca(eventos):
    log_event("teste", objeto=object())
    [evento] = eventos("teste")
    assert evento["objeto"].startswith("<object")


def test_falha_de_serializacao_vira_error(eventos):
    circular = {}
    circular["eu"] = circular
    log_event("teste", campo=circular)
    [evento] = eventos()
    assert evento["event"] == "error"
    assert "teste" in evento["message"]


def test_falha_no_builder_vira_error(eventos):
    def quebra():
        raise RuntimeError("bug")
    telemetry.emit("move", quebra)
    [evento] = eventos()
    assert evento["event"] == "error"
    assert evento["exception"] == "RuntimeError"


# --- Evento request ---

from fastapi.testclient import TestClient

from src.app import main
from src.app.main import app, handler
from tests.helpers import snake, make_game

EU = "eu"
client = TestClient(app)


def payload(state) -> dict:
    """O JSON que o motor mandaria para este GameState."""
    return state.model_dump()


def estado_simples(turn: int = 1):
    return make_game(snake(EU, [(5, 5), (5, 4), (5, 3)]), turn=turn)


def test_request_de_move_bem_sucedido(eventos):
    resp = client.post("/move", json=payload(estado_simples()))
    assert resp.status_code == 200
    [evento] = eventos("request")
    assert evento["path"] == "/move"
    assert evento["method"] == "POST"
    assert evento["status"] == 200
    assert isinstance(evento["duration_ms"], (int, float))
    assert isinstance(evento["slow"], bool)


def test_cold_start_so_na_primeira(eventos, monkeypatch):
    monkeypatch.setattr(main, "_cold_start", True)
    client.get("/")
    client.get("/")
    primeira, segunda = eventos("request")
    assert primeira["cold_start"] is True
    assert segunda["cold_start"] is False


def test_request_com_prefixo_de_stage(eventos):
    resp = client.post("/dev/move", json=payload(estado_simples()))
    assert resp.status_code == 200
    [evento] = eventos("request")
    assert evento["path"] == "/move"


def test_request_lenta(eventos, monkeypatch):
    monkeypatch.setattr(telemetry, "SLOW_MS", 0)
    client.get("/")
    [evento] = eventos("request")
    assert evento["slow"] is True


def test_request_sem_payload_de_jogo(eventos):
    client.get("/")
    [evento] = eventos("request")
    assert evento["game_id"] is None
    assert evento["turn"] is None
    assert evento["snake_id"] is None


def test_request_fora_da_lambda(eventos):
    client.get("/")
    [evento] = eventos("request")
    assert evento["aws_request_id"] is None
    assert evento["remaining_ms"] is None


class ContextoLambda:
    """O mínimo do LambdaContext que a telemetria lê."""
    aws_request_id = "abc-123"

    def get_remaining_time_in_millis(self) -> int:
        return 1234


def evento_function_url(method: str, path: str, body: str | None = None) -> dict:
    """Evento da Function URL (formato 2.0 do API Gateway)."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "lambda.local", "content-type": "application/json"},
        "requestContext": {
            "http": {
                "method": method, "path": path, "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1", "userAgent": "teste",
            },
            "stage": "$default",
        },
        "body": body,
        "isBase64Encoded": False,
    }


def test_request_dentro_da_lambda(eventos):
    corpo = json.dumps(payload(estado_simples()))
    resposta = handler(evento_function_url("POST", "/move", corpo), ContextoLambda())
    assert resposta["statusCode"] == 200
    lidos = eventos()
    assert sorted(e["event"] for e in lidos) == ["move", "request"]
    assert all(e["aws_request_id"] == "abc-123" for e in lidos)
    [request] = [e for e in lidos if e["event"] == "request"]
    assert request["remaining_ms"] == 1234


# --- Explicação da decisão ---

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
]


@pytest.mark.parametrize("medicoes", MEDICOES)
@pytest.mark.parametrize("ctx", [COM_FOME, SEM_FOME])
def test_explain_e_coerente_com_decide(medicoes, ctx):
    decisao = explain(medicoes, ctx)
    assert decisao.move == decide(medicoes, ctx)
    for f in medicoes:
        avaliada = por_move(decisao)[f.move]
        assert avaliada.score == score(f, ctx) == sum(avaliada.terms.values())


# --- Evento move ---
# Nos desenhos ASCII, y cresce para cima (a primeira linha é a de cima):
# E = minha cabeça, e = meu corpo, R = cabeça da rival, r = corpo da rival,
# * = comida e . = casa livre.

import time

from src.app import logic
from src.app.grid import MOVES
from src.app.logic import get_move


def jogada(eventos, state) -> dict:
    """Roda get_move e devolve o único evento move emitido."""
    resposta = get_move(state)
    [evento] = eventos("move")
    assert evento["chosen"] == resposta.move
    return evento


def desvia_de_adversaria():
    # x: 2 3 4 5 6
    # y=10 r r R E .     up é parede, down é o pescoço, left é a adversária
    # y=9  . . . e .
    # y=8  . . . e .
    eu = snake(EU, [(5, 10), (5, 9), (5, 8)])
    outra = snake("outra", [(4, 10), (3, 10), (2, 10)])
    return make_game(eu, others=[outra])


def cabeca_a_cabeca_com_maior():
    # x: 0 1 2 3 4 5
    # y=10 r r r R . E     a rival maior também alcança (4,10)
    # y=9  . . . . . e
    eu = snake(EU, [(5, 10), (5, 9), (5, 8)])
    grande = snake("grande", [(3, 10), (2, 10), (1, 10), (0, 10)])
    return make_game(eu, others=[grande])


def centro_sem_fome():
    # Vida cheia, sem rivais nem comida: up, left e right empatam.
    return make_game(snake(EU, [(5, 5), (5, 4), (5, 3)], health=100))


def com_fome():
    # x: 5 6 7 8
    # y=5  E . . *     vida 10: a comida a 3 passos dá fome por sobrevivência
    # y=4  e . . .
    return make_game(snake(EU, [(5, 5), (5, 4), (5, 3)], health=10), food=[(8, 5)])


def beco_versus_cabeca_a_cabeca():
    #   x: 0 1 2
    # y=3  R . .      up é arriscada mas tem espaço; down é segura e dá num
    # y=2  . . .      bolsão de 2 casas: up vence pela camada
    # y=1  E e e
    # y=0  . e e
    eu = snake(EU, [(0, 1), (1, 1), (2, 1), (2, 0), (1, 0)])
    maior = snake("maior", [(0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8)])
    return make_game(eu, others=[maior])


def sem_saida():
    #   x: 0 1
    # y=2  e .     up é o corpo, right é o pescoço, left e down são parede
    # y=1  e e
    # y=0  E e
    return make_game(snake(EU, [(0, 0), (1, 0), (1, 1), (0, 1), (0, 2)]))


def test_move_adversaria_ao_lado_e_parede_acima(eventos):
    evento = jogada(eventos, desvia_de_adversaria())
    blocked = {d: evento["directions"][d]["blocked_by"] for d in MOVES}
    assert blocked == {
        "up": ["wall"], "down": ["neck", "self"], "left": ["opponent"], "right": [],
    }
    assert evento["safe_moves"] == ["right"]
    assert evento["chosen"] == "right"
    assert evento["reason"] == "only_option"
    assert evento["directions"]["up"]["target"] == [5, 11]
    for d in ("up", "down", "left"):
        direcao = evento["directions"][d]
        for campo in telemetry.FEATURE_FIELDS + ("layer", "score", "score_terms"):
            assert direcao[campo] is None, (d, campo)
    assert evento["directions"]["right"]["area"] is not None


def test_move_cabeca_a_cabeca_arriscado(eventos):
    evento = jogada(eventos, cabeca_a_cabeca_com_maior())
    left = evento["directions"]["left"]
    assert left["blocked_by"] == []
    assert left["risky"] is True
    assert left["layer"] == 1
    assert evento["chosen"] == "right"


def test_move_empate_decidido_pela_ordem_canonica(eventos):
    evento = jogada(eventos, centro_sem_fome())
    candidatas = [evento["directions"][d] for d in ("up", "left", "right")]
    assert len({(c["layer"], c["score"]) for c in candidatas}) == 1
    assert evento["chosen"] == "up"
    assert evento["reason"] == "tie"
    assert evento["hungry"] is False
    assert evento["hunger_reasons"] == []


def test_move_pontuacao_com_fome(eventos):
    evento = jogada(eventos, com_fome())
    assert evento["chosen"] == "right"
    assert evento["reason"] == "score"
    food_step = {d: evento["directions"][d]["food_step"] for d in ("up", "left", "right")}
    assert food_step == {"up": False, "left": False, "right": True}
    assert evento["directions"]["right"]["score_terms"]["food"] > 0


def test_move_comida_alvo_com_fome(eventos):
    evento = jogada(eventos, com_fome())
    assert evento["hungry"] is True
    assert "starving" in evento["hunger_reasons"]
    assert evento["food_target"] == [8, 5]
    assert evento["astar_path_len"] == 3


def test_move_camada_de_seguranca(eventos):
    evento = jogada(eventos, beco_versus_cabeca_a_cabeca())
    assert evento["chosen"] == "up"
    assert evento["reason"] == "layer"


def test_move_emergencia(eventos):
    evento = jogada(eventos, sem_saida())
    assert evento["reason"] == "emergency"
    assert evento["safe_moves"] == []
    assert all(evento["directions"][d]["blocked_by"] for d in MOVES)
    assert evento["chosen"] in MOVES
    assert evento["hungry"] is None


def test_move_parcelas_somam_a_pontuacao(eventos):
    for state in (com_fome(), centro_sem_fome(), cabeca_a_cabeca_com_maior()):
        evento = jogada(eventos, state)
        for direcao in evento["directions"].values():
            if direcao["score"] is not None:
                assert sum(direcao["score_terms"].values()) == direcao["score"]


def test_move_campos_de_jogo(eventos):
    state = make_game(snake(EU, [(5, 5), (5, 4), (5, 3)]), turn=7)
    evento = jogada(eventos, state)
    assert evento["game_id"] == "partida-de-teste"
    assert evento["turn"] == 7
    assert evento["snake_id"] == EU
    assert evento["you"] == {"head": [5, 5], "length": 3, "health": 100}
    assert evento["board"] == {"width": 11, "height": 11, "snake_count": 1, "food_count": 0}
    assert isinstance(evento["logic_ms"], float)


def test_move_via_http_emite_exatamente_um(eventos):
    client.post("/move", json=payload(estado_simples()))
    assert len(eventos("move")) == 1


# --- Logs não mudam a decisão ---

def cenarios_de_estrategia():
    """Estados com resposta única: os desta suíte e os de test_estrategia.py."""
    entra_na_cauda = make_game(
        snake(EU, [(5, 10), (5, 9), (4, 9), (4, 10)]),
        others=[snake("bloqueio", [(8, 10), (7, 10), (6, 10)])],
    )
    igual = make_game(
        snake(EU, [(5, 10), (5, 9), (5, 8)]),
        others=[snake("igual", [(3, 10), (2, 10), (1, 10)])],
    )
    fome_esquerda = make_game(snake(EU, [(5, 5), (5, 4), (5, 3)], health=10), food=[(2, 5)])
    sem_fome = make_game(snake(EU, [(5, 5), (5, 4), (5, 3)], health=100), food=[(2, 5)])
    beco = make_game(
        snake(EU, [(5, 9), (6, 9), (7, 9), (7, 10), (8, 10)]),
        others=[snake("outra", [
            (0, 5), (0, 6), (0, 7), (0, 8), (0, 9), (0, 10),
            (1, 10), (2, 10), (3, 10), (4, 10), (4, 10),
        ])],
    )
    return [
        (desvia_de_adversaria(), "right"),
        (cabeca_a_cabeca_com_maior(), "right"),
        (centro_sem_fome(), "up"),
        (com_fome(), "right"),
        (beco_versus_cabeca_a_cabeca(), "up"),
        (entra_na_cauda, "left"),
        (igual, "right"),
        (fome_esquerda, "left"),
        (sem_fome, "up"),
        (beco, "down"),
    ]


@pytest.mark.parametrize("state, esperado", cenarios_de_estrategia())
def test_logs_nao_mudam_a_decisao(state, esperado, nivel):
    nivel(logging.CRITICAL)
    sem_logs = get_move(state).move
    nivel(logging.DEBUG)
    com_logs = get_move(state).move
    assert sem_logs == com_logs == esperado


# --- Custo dos logs ---

def serpente(id: str, x0: int) -> dict:
    """Cobra de tamanho 15 em zigue-zague: sobe a coluna x0 e desce a x0+1."""
    body = [(x0, y) for y in range(9, 1, -1)] + [(x0 + 1, y) for y in range(2, 9)]
    return snake(id, body)


def tabuleiro_cheio():
    """19x19 com 9 cobras de tamanho 15, 5 comidas e turno 60."""
    cobras = [serpente(EU, 0)] + [serpente(f"r{i}", 2 * i) for i in range(1, 9)]
    return make_game(
        cobras[0], others=cobras[1:],
        food=[(3, 15), (9, 17), (14, 12), (18, 1), (0, 18)],
        width=19, height=19, turn=60,
    )


def folhas(valor) -> int:
    """Quantos campos o Logs Insights descobriria neste JSON achatado."""
    if isinstance(valor, dict):
        return sum(folhas(v) for v in valor.values()) or 1
    if isinstance(valor, list):
        return sum(folhas(v) for v in valor) or 1
    return 1


def test_custo_do_evento_move_no_tabuleiro_cheio(eventos, monkeypatch):
    state = tabuleiro_cheio()
    assert len(state.board.snakes) == 9
    # Captura os argumentos com que get_move monta o evento, sem medir a lógica.
    chamadas = []
    monkeypatch.setattr(telemetry, "emit", lambda *args: chamadas.append(args))
    get_move(state)
    monkeypatch.undo()
    [(evento, build, *args)] = chamadas
    assert evento == "move"

    tempos = []
    for _ in range(20):
        inicio = time.perf_counter()
        telemetry.emit(evento, build, *args)
        tempos.append(time.perf_counter() - inicio)
    assert min(tempos) < 0.005, f"melhor tempo: {min(tempos) * 1000:.2f} ms"

    emitido = eventos("move")[0]
    assert folhas(emitido) < 200, folhas(emitido)


# --- Latência do motor e movimento observado ---

def com_latencia(latency):
    """Estado simples com a latência dada na própria cobra (None = ausente)."""
    eu = snake(EU, [(5, 5), (5, 4), (5, 3)])
    if latency is None:
        del eu["latency"]
    else:
        eu["latency"] = latency
    return make_game(eu)


def test_latencia_informada_pelo_motor(eventos):
    evento = jogada(eventos, com_latencia("123"))
    assert evento["engine_latency_ms"] == 123
    assert evento["timed_out_last_turn"] is False


@pytest.mark.parametrize("latency", [None, "", "abc"])
def test_latencia_ausente_ou_vazia(eventos, latency):
    evento = jogada(eventos, com_latencia(latency))
    assert evento["engine_latency_ms"] is None
    assert evento["timed_out_last_turn"] is False


def test_turno_anterior_estourou_o_tempo(eventos):
    evento = jogada(eventos, com_latencia("500"))  # timeout do make_game é 500
    assert evento["timed_out_last_turn"] is True
    evento = jogada(eventos, com_latencia("499"))
    assert evento["timed_out_last_turn"] is False


def test_movimento_observado(eventos):
    evento = jogada(eventos, estado_simples())  # cabeça (5,5), pescoço (5,4)
    assert evento["observed_last_move"] == "up"


def test_corpo_empilhado_nao_tem_movimento_observado(eventos):
    state = make_game(snake(EU, [(5, 5), (5, 5), (5, 5)]), turn=0)
    evento = jogada(eventos, state)
    assert evento["observed_last_move"] is None


# --- Eventos start e end ---

def test_start_com_adversarias(eventos):
    state = make_game(
        snake(EU, [(1, 1), (1, 1), (1, 1)]),
        others=[snake("a", [(5, 5), (5, 5), (5, 5)]), snake("b", [(9, 9), (9, 9), (9, 9)])],
        turn=0,
    )
    resp = client.post("/start", json=payload(state))
    assert resp.status_code == 200
    [evento] = eventos("start")
    assert evento["ruleset"] == {"name": "standard", "version": "v1.2.3"}
    assert evento["map"] == "standard"
    assert evento["timeout"] == 500
    assert (evento["width"], evento["height"]) == (11, 11)
    assert evento["snake_count"] == 3
    assert evento["opponents"] == [{"id": "a", "name": "a"}, {"id": "b", "name": "b"}]
    assert evento["game_id"] == "partida-de-teste"


def fim_de_jogo(*vivas: str) -> dict:
    """Payload do /end com só as cobras de id em `vivas` no tabuleiro."""
    eu = snake(EU, [(1, 1), (1, 2), (1, 3)])
    outras = {
        "a": snake("a", [(5, 5), (5, 6), (5, 7)]),
        "b": snake("b", [(9, 9), (9, 8), (9, 7)]),
    }
    state = payload(make_game(eu, turn=42))
    todas = {EU: eu, **outras}
    state["board"]["snakes"] = [todas[i] for i in vivas]
    return state


@pytest.mark.parametrize("vivas, won, eliminated", [
    ((EU,), True, False),
    (("a", "b"), False, True),
    ((EU, "a"), False, False),
])
def test_end(eventos, vivas, won, eliminated):
    resp = client.post("/end", json=fim_de_jogo(*vivas))
    assert resp.status_code == 200
    [evento] = eventos("end")
    assert evento["turns"] == 42
    assert evento["won"] is won
    assert evento["eliminated"] is eliminated
    assert evento["survivors"] == list(vivas)


# --- Evento error ---

from fastapi import FastAPI

from src.app.models import GameState as ModeloGameState


def test_falha_na_escolha_do_movimento(eventos, monkeypatch):
    def quebra(state, safe_moves):
        raise RuntimeError("falhou de propósito")
    monkeypatch.setattr(logic, "choose_move", quebra)

    with pytest.raises(RuntimeError, match="falhou de propósito"):
        client.post("/move", json=payload(estado_simples(turn=7)))

    [erro] = eventos("error")
    assert erro["path"] == "/move"
    assert erro["exception"] == "RuntimeError"
    assert erro["message"] == "falhou de propósito"
    assert "Traceback" in erro["traceback"]
    assert erro["game_id"] == "partida-de-teste"
    assert erro["turn"] == 7


def test_falha_gera_request_500_com_a_partida(eventos, monkeypatch):
    def quebra(state, safe_moves):
        raise RuntimeError("falhou de propósito")
    monkeypatch.setattr(logic, "choose_move", quebra)
    with pytest.raises(RuntimeError):
        client.post("/move", json=payload(estado_simples(turn=7)))
    [request] = eventos("request")
    assert request["status"] == 500
    assert request["game_id"] == "partida-de-teste"
    assert request["turn"] == 7


def resposta_padrao_do_fastapi(corpo: dict):
    """O 422 de um app sem o handler de validação da cobra."""
    puro = FastAPI()

    @puro.post("/move")
    def move(state: ModeloGameState) -> dict:
        return {}

    return TestClient(puro).post("/move", json=corpo)


def test_payload_invalido(eventos):
    corpo = payload(estado_simples(turn=3))
    corpo["game"]["id"] = "g1"
    del corpo["you"]
    resp = client.post("/move", json=corpo)
    esperado = resposta_padrao_do_fastapi(corpo)
    assert resp.status_code == 422
    assert resp.json() == esperado.json()

    [erro] = eventos("error")
    assert erro["exception"] == "RequestValidationError"
    assert erro["path"] == "/move"
    assert erro["message"] == "body.you: missing"
    assert erro["game_id"] == "g1"
    assert erro["turn"] == 3


def test_payload_que_nao_e_json(eventos):
    resp = client.post("/move", content=b"nada", headers={"content-type": "application/json"})
    assert resp.status_code == 422
    [erro] = eventos("error")
    assert erro["exception"] == "RequestValidationError"
    assert erro["game_id"] is None


def test_sem_segredos(capsys):
    capsys.readouterr()
    client.post(
        "/move",
        json=payload(estado_simples()),
        headers={"Authorization": "Bearer segredo-xyz"},
        params={"token": "segredo-xyz"},
    )
    saida = capsys.readouterr().out
    assert saida
    assert "segredo-xyz" not in saida
