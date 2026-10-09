"""Testes dos logs estruturados de diagnóstico (src/app/telemetry.py).

Rode com: pytest tests/app/test_telemetry.py

Só dois eventos: move, um por jogada, e error. Cada um é uma linha JSON no
stdout; o fixture `eventos` lê o que foi capturado e devolve a lista de
objetos.
"""
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.app import logic, telemetry
from src.app.logic import get_move
from src.app.main import app
from src.app.models import GameState
from src.app.telemetry import log_event
from tests.helpers import snake, make_game

EU = "eu"
client = TestClient(app)

CAMPOS_DO_MOVE = {"event", "game_id", "turn", "move", "timed_out_last_turn"}
CAMPOS_DO_ERROR = {"event", "path", "exception", "message", "traceback", "game_id", "turn"}


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


def payload(state) -> dict:
    """O JSON que o motor mandaria para este GameState."""
    return state.model_dump()


def estado_simples(turn: int = 1):
    return make_game(snake(EU, [(5, 5), (5, 4), (5, 3)]), turn=turn)


def jogada(eventos, state) -> dict:
    """Roda get_move e devolve o único evento move emitido."""
    resposta = get_move(state)
    [evento] = eventos("move")
    assert evento["move"] == resposta.move
    return evento


# --- Formato ---

def test_toda_linha_e_um_objeto_json(eventos):
    log_event("teste", valor=1)
    assert eventos() == [{"event": "teste", "valor": 1}]

    corpo = payload(estado_simples())
    for path in ("/start", "/move", "/end"):
        client.post(path, json=corpo)
    lidos = eventos()
    assert lidos
    assert all("event" in e for e in lidos)


def test_sem_duplicacao(eventos):
    get_move(estado_simples())
    assert len(eventos("move")) == 1
    assert telemetry.logger.propagate is False


def test_texto_nao_ascii_sai_literal(capsys):
    log_event("teste", texto="ção")
    assert "ção" in capsys.readouterr().out


def test_so_erros(eventos, nivel):
    nivel(logging.ERROR)
    telemetry.log_move(estado_simples(), "up")
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
    assert set(evento) == CAMPOS_DO_ERROR
    assert "teste" in evento["message"]


def test_falha_ao_montar_o_move_vira_error(eventos, monkeypatch):
    def quebra(snake, timeout):
        raise RuntimeError("bug")
    monkeypatch.setattr(telemetry, "timed_out_last_turn", quebra)
    telemetry.log_move(estado_simples(), "up")
    [evento] = eventos()
    assert evento["event"] == "error"
    assert evento["exception"] == "RuntimeError"


# --- Evento move ---
# Nos desenhos ASCII, y cresce para cima (a primeira linha é a de cima):
# E = minha cabeça, e = meu corpo, R = cabeça da rival, r = corpo da rival,
# * = comida e . = casa livre.

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
    #   x: 0 1 2 3 4 5
    # y=10 . . E e e e     left é segura e dá num bolsão de 2 casas; down é
    # y=9  r r . . . .     arriscada mas tem espaço: down vence pela camada
    # y=8  r r R . . .
    # y=7  r . . . . .
    # y=6  r . . . . .
    # y=5  r . . . . .
    eu = snake(EU, [(2, 10), (3, 10), (4, 10), (5, 10)])
    maior = snake("maior", [(2, 8), (1, 8), (1, 9), (0, 9), (0, 8), (0, 7), (0, 6), (0, 5)])
    return make_game(eu, others=[maior])


def sem_saida():
    #   x: 0 1
    # y=2  e .     up é o corpo, right é o pescoço, left e down são parede
    # y=1  e e
    # y=0  E e
    return make_game(snake(EU, [(0, 0), (1, 0), (1, 1), (0, 1), (0, 2)]))


def test_move_tem_exatamente_os_cinco_campos(eventos):
    evento = jogada(eventos, estado_simples(turn=7))
    assert set(evento) == CAMPOS_DO_MOVE
    assert evento["event"] == "move"
    assert evento["game_id"] == "partida-de-teste"
    assert evento["turn"] == 7
    assert evento["timed_out_last_turn"] is False


def test_move_na_emergencia(eventos):
    evento = jogada(eventos, sem_saida())
    assert set(evento) == CAMPOS_DO_MOVE
    assert evento["move"] in ("up", "down", "left", "right")


def test_move_no_turno_zero_com_corpo_empilhado(eventos):
    state = make_game(snake(EU, [(5, 5), (5, 5), (5, 5)]), turn=0)
    evento = jogada(eventos, state)
    assert set(evento) == CAMPOS_DO_MOVE
    assert evento["turn"] == 0


def test_move_sem_os_campos_removidos(eventos):
    # Movimento observado: cabeça em (5,5), segundo segmento em (5,4).
    assert set(jogada(eventos, estado_simples())) == CAMPOS_DO_MOVE
    # Comida alvo com fome: o move é right e não traz a fome nem a comida.
    evento = jogada(eventos, com_fome())
    assert evento["move"] == "right"
    assert set(evento) == CAMPOS_DO_MOVE


def test_move_via_http_emite_exatamente_uma_linha(eventos):
    resp = client.post("/move", json=payload(estado_simples()))
    assert resp.status_code == 200
    [evento] = eventos()
    assert evento["event"] == "move"
    assert evento["move"] == resp.json()["move"]


@pytest.mark.parametrize("path", ["/start", "/end"])
def test_start_e_end_nao_emitem_nada(eventos, path):
    resp = client.post(path, json=payload(estado_simples()))
    assert resp.status_code == 200
    assert eventos() == []


# --- Turno anterior estourou o tempo ---

def com_latencia(latency):
    """Estado simples com a latência dada na própria cobra (None = ausente)."""
    eu = snake(EU, [(5, 5), (5, 4), (5, 3)])
    if latency is None:
        del eu["latency"]
    else:
        eu["latency"] = latency
    return make_game(eu)


@pytest.mark.parametrize("latency, estourou", [
    ("500", True),
    ("750", True),
    ("499", False),
    ("123", False),
    (None, False),
    ("", False),
    ("abc", False),
])
def test_timed_out_last_turn(eventos, latency, estourou):
    evento = jogada(eventos, com_latencia(latency))
    assert evento["timed_out_last_turn"] is estourou


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
        snake(EU, [(2, 10), (3, 10), (4, 10), (5, 10)]),
        others=[snake("outra", [
            (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (1, 9), (0, 9), (0, 8), (0, 7), (0, 6),
        ])],
    )
    return [
        (desvia_de_adversaria(), "right"),
        (cabeca_a_cabeca_com_maior(), "right"),
        (centro_sem_fome(), "up"),
        (com_fome(), "right"),
        (beco_versus_cabeca_a_cabeca(), "down"),
        (entra_na_cauda, "left"),
        (igual, "right"),
        (fome_esquerda, "left"),
        (sem_fome, "up"),
        (beco, "down"),
    ]


@pytest.mark.parametrize("state, esperado", cenarios_de_estrategia())
def test_logs_nao_mudam_a_decisao(state, esperado, nivel, sem_busca):
    nivel(logging.CRITICAL)
    sem_logs = get_move(state).move
    nivel(logging.DEBUG)
    com_logs = get_move(state).move
    assert sem_logs == com_logs == esperado


# --- Evento error ---

def test_falha_na_escolha_do_movimento(eventos, monkeypatch):
    def quebra(state, safe_moves, **kwargs):
        raise RuntimeError("falhou de propósito")
    monkeypatch.setattr(logic, "choose_move", quebra)

    with pytest.raises(RuntimeError, match="falhou de propósito"):
        client.post("/move", json=payload(estado_simples(turn=7)))

    [erro] = eventos()
    assert set(erro) == CAMPOS_DO_ERROR
    assert erro["event"] == "error"
    assert erro["path"] == "/move"
    assert erro["exception"] == "RuntimeError"
    assert erro["message"] == "falhou de propósito"
    assert "Traceback" in erro["traceback"]
    assert erro["game_id"] == "partida-de-teste"
    assert erro["turn"] == 7


def resposta_padrao_do_fastapi(corpo: dict):
    """O 422 de um app sem o handler de validação da cobra."""
    puro = FastAPI()

    @puro.post("/move")
    def move(state: GameState) -> dict:
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

    [erro] = eventos()
    assert set(erro) == CAMPOS_DO_ERROR
    assert erro["exception"] == "RequestValidationError"
    assert erro["path"] == "/move"
    assert erro["message"] == "body.you: missing"
    assert erro["game_id"] == "g1"
    assert erro["turn"] == 3


def test_payload_que_nao_e_json(eventos):
    resp = client.post("/move", content=b"nada", headers={"content-type": "application/json"})
    assert resp.status_code == 422
    [erro] = eventos()
    assert set(erro) == CAMPOS_DO_ERROR
    assert erro["exception"] == "RequestValidationError"
    assert erro["game_id"] is None
    assert erro["turn"] is None


# --- Sem segredos ---

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
