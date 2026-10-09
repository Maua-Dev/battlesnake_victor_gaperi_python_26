"""Testes da ferramenta de análise de partidas (scripts/replay.py), sem rede.

A fixture tem a partida dc8c4f05-84ac-4554-98f6-94b22d5a8b4d nos turnos 74
e 75, com as outras cobras anonimizadas. O cliente HTTP é sempre falso.

Rode com: pytest tests/scripts/test_replay.py
"""
import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from scripts import replay

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "arena_dc8c4f05_turnos_74_75.json"
GAME_ID = "dc8c4f05-84ac-4554-98f6-94b22d5a8b4d"
MINHA = "30a31a86-5a45-491b-b25d-f8d4904e0924"
ENGINE = "https://arena.exemplo/api"


@pytest.fixture
def partida():
    return json.loads(FIXTURE.read_text())


def coords(snake_model):
    return [(c.x, c.y) for c in snake_model.body]


# --- Conversão do frame ---

def test_frame_vira_o_estado_do_move(partida):
    game = partida["game"]["Game"]
    state = replay.frame_to_state(game, partida["frames"][0], MINHA)
    assert state.turn == 74
    assert state.game.id == GAME_ID
    assert state.game.timeout == 500
    assert state.game.ruleset == {"name": "standard"}
    assert (state.board.width, state.board.height) == (11, 11)
    # A cobra morta no turno 10 fica fora; a ordem do frame é mantida.
    assert [s.id for s in state.board.snakes] == ["rival-b-id", MINHA]
    assert state.you.id == MINHA
    assert coords(state.you) == [
        (2, 4), (2, 3), (2, 2), (1, 2), (0, 2), (0, 3), (0, 4), (0, 5),
        (1, 5), (2, 5), (3, 5),
    ]
    assert state.you.health == 96
    assert state.you.length == 11
    assert (state.you.head.x, state.you.head.y) == (2, 4)
    assert state.you.latency == "194"
    rival = state.board.snakes[0]
    assert coords(rival) == [(4, 4), (4, 3), (3, 3), (3, 4)]
    assert rival.health == 40
    assert [(f.x, f.y) for f in state.board.food] == [(1, 9), (10, 4), (7, 2)]
    assert state.board.hazards == []


def test_direcao_jogada(partida):
    f74, f75 = partida["frames"]
    assert replay.played_move(f74, f75, MINHA) == "left"
    assert replay.played_move(f74, None, MINHA) is None


def test_direcao_jogada_desconhecida_se_a_cabeca_pula():
    f = {"Turn": 1, "Snakes": [{"ID": "a", "Body": [{"X": 1, "Y": 1}]}]}
    g = {"Turn": 2, "Snakes": [{"ID": "a", "Body": [{"X": 3, "Y": 1}]}]}
    assert replay.played_move(f, g, "a") is None


def test_latencia_vem_do_frame_seguinte(partida):
    f75 = partida["frames"][1]
    assert replay.turn_latency(f75, MINHA) == "176"
    assert replay.turn_latency(None, MINHA) is None


# --- Escolha da cobra ---

def test_escolhe_a_cobra_pelo_author(partida):
    escolhida = replay.pick_snake(partida["frames"], None, "gasperi")
    assert escolhida["ID"] == MINHA


@pytest.mark.parametrize("wanted", [MINHA, "gasperi-1", "rival-a"])
def test_escolhe_a_cobra_por_id_ou_nome(partida, wanted):
    escolhida = replay.pick_snake(partida["frames"], wanted, "gasperi")
    assert wanted in (escolhida["ID"], escolhida["Name"])


def test_nenhuma_cobra_bate(partida):
    with pytest.raises(replay.ReplayError) as erro:
        replay.pick_snake(partida["frames"], None, "ninguem")
    # A mensagem lista as cobras da partida.
    for nome in ("rival-a", "rival-b", "gasperi-1"):
        assert nome in str(erro.value)


def test_mais_de_uma_cobra_bate(partida):
    with pytest.raises(replay.ReplayError):
        replay.pick_snake(partida["frames"], None, "autor-")


def test_snake_que_nao_existe(partida):
    with pytest.raises(replay.ReplayError):
        replay.pick_snake(partida["frames"], "outra", "gasperi")


# --- Turnos ---

@pytest.mark.parametrize("texto, esperado", [("72-76", (72, 76)), ("74", (74, 74))])
def test_intervalo_de_turnos(texto, esperado):
    assert replay.parse_turns(texto) == esperado


@pytest.mark.parametrize("texto", ["76-72", "abc", "1-2-3", "-3", ""])
def test_intervalo_invalido(texto):
    with pytest.raises(ValueError):
        replay.parse_turns(texto)


def frames_simples(ultimo_turno, morte=None):
    """Frames mínimos de uma cobra "a", com Death a partir do turno da morte."""
    frames = []
    for t in range(ultimo_turno + 1):
        death = {"Cause": "x", "EliminatedBy": "", "Turn": morte} if morte is not None and t >= morte else None
        frames.append({"Turn": t, "Snakes": [{"ID": "a", "Death": death}]})
    return frames


def test_turnos_padrao_antes_da_morte():
    assert replay.default_turns(frames_simples(77, morte=77), "a") == list(range(69, 77))


def test_turnos_padrao_sem_morte():
    assert replay.default_turns(frames_simples(30), "a") == list(range(23, 31))


def test_turnos_padrao_nao_passam_de_zero():
    assert replay.default_turns(frames_simples(5, morte=3), "a") == [0, 1, 2]


# --- Download ---

class ClienteFalso:
    """Serve a partida e as páginas de frames, e guarda as URLs pedidas."""

    def __init__(self, game, frames):
        self.game = game
        self.frames = frames
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        parsed = urlparse(url)
        if parsed.path.endswith("/frames"):
            q = parse_qs(parsed.query)
            offset, limit = int(q["offset"][0]), int(q["limit"][0])
            page = self.frames[offset:offset + limit]
            return {"count": len(page), "frames": page}
        return self.game


def test_paginacao_junta_duas_paginas():
    frames = [{"Turn": t, "Snakes": []} for t in range(5)]
    cliente = ClienteFalso({}, frames)
    baixados = replay.fetch_frames(ENGINE, GAME_ID, cliente, page_size=3)
    assert [f["Turn"] for f in baixados] == [0, 1, 2, 3, 4]
    offsets = [parse_qs(urlparse(u).query)["offset"][0] for u in cliente.urls]
    assert offsets == ["0", "3"]
    assert cliente.urls[0] == f"{ENGINE}/games/{GAME_ID}/frames?offset=0&limit=3"


def test_paginacao_para_na_pagina_vazia():
    frames = [{"Turn": t, "Snakes": []} for t in range(3)]
    cliente = ClienteFalso({}, frames)
    assert len(replay.fetch_frames(ENGINE, GAME_ID, cliente, page_size=3)) == 3
    assert len(cliente.urls) == 2


def test_frames_ordenados_por_turno():
    frames = [{"Turn": t, "Snakes": []} for t in (1, 0, 2)]
    baixados = replay.fetch_frames(ENGINE, GAME_ID, ClienteFalso({}, frames), page_size=10)
    assert [f["Turn"] for f in baixados] == [0, 1, 2]


def test_baixa_a_partida(partida):
    cliente = ClienteFalso(partida["game"], [])
    assert replay.fetch_game(ENGINE, GAME_ID, cliente)["Width"] == 11
    assert cliente.urls == [f"{ENGINE}/games/{GAME_ID}"]


def test_erro_de_rede_vira_erro_com_a_url():
    def quebra(url):
        raise replay.ReplayError(f"falha ao baixar {url}: recusada")
    with pytest.raises(replay.ReplayError, match="/games/"):
        replay.fetch_game(ENGINE, GAME_ID, quebra)


# --- Relatório ---

def test_tabuleiro_do_turno_74(partida):
    state = replay.frame_to_state(partida["game"]["Game"], partida["frames"][0], MINHA)
    linhas = replay.render_board(state)
    # A primeira linha é a de cima (y=10); y=4 é a sétima.
    assert linhas[0].startswith("y=10")
    assert linhas[6] == "y=4   e . E r R . . . . . *"
    assert linhas[5] == "y=5   e e e t . . . . . . ."
    assert linhas[-1].split() == ["x:"] + [str(x) for x in range(11)]


def cliente_da_fixture(partida):
    """Cliente falso que serve a fixture como a partida inteira."""
    return ClienteFalso(partida["game"], partida["frames"])


def rodar(partida, *args):
    linhas = []
    codigo = replay.main([GAME_ID, *args], get_json=cliente_da_fixture(partida), out=linhas.append)
    return codigo, "\n".join(linhas)


def test_relatorio_do_turno_74(partida, capsys):
    codigo, saida = rodar(partida, "--turns", "74", "--deep-budget-ms", "300")
    assert codigo == 0
    assert "candidatas: left, right" in saida
    assert "up: body" in saida
    assert "down: neck" in saida
    assert "get_move (orçamento 120 ms): right" in saida
    assert "DIVERGE" in saida
    assert "turnos divergentes: 74" in saida
    # O log de produção (linhas JSON do evento move) fica de fora.
    assert '"event"' not in saida
    assert '"event"' not in capsys.readouterr().out


def test_intervalo_invalido_nao_baixa_nada(partida):
    cliente = cliente_da_fixture(partida)
    linhas = []
    codigo = replay.main([GAME_ID, "--turns", "76-72"], get_json=cliente, out=linhas.append)
    assert codigo != 0
    assert cliente.urls == []


def test_cobra_nao_encontrada_lista_as_cobras(partida):
    codigo, saida = rodar(partida, "--snake", "outra")
    assert codigo != 0
    assert "rival-a" in saida and "gasperi-1" in saida


def test_erro_de_rede_encerra_com_a_url(partida):
    def quebra(url):
        raise replay.ReplayError(f"falha ao baixar {url}: recusada")
    linhas = []
    codigo = replay.main([GAME_ID], get_json=quebra, out=linhas.append)
    assert codigo != 0
    assert f"/games/{GAME_ID}" in "\n".join(linhas)


def test_sorteio_sem_candidatas_nao_conta_como_divergencia(partida):
    partida = copy.deepcopy(partida)
    # No turno 74, a rival com (3,4) no meio do corpo tira right, e uma
    # terceira cobra com a cabeça em (1,4) tira left.
    snakes = partida["frames"][0]["Snakes"]
    rival = next(s for s in snakes if s["ID"] == "rival-b-id")
    rival["Body"] = [{"X": 4, "Y": 4}, {"X": 3, "Y": 4}, {"X": 3, "Y": 3}, {"X": 4, "Y": 3}]
    terceira = copy.deepcopy(rival)
    terceira.update(ID="rival-c-id", Name="rival-c", Author="autor-c")
    terceira["Body"] = [{"X": 1, "Y": 4}, {"X": 1, "Y": 3}, {"X": 1, "Y": 3}]
    snakes.append(terceira)
    codigo, saida = rodar(partida, "--turns", "74", "--deep-budget-ms", "100")
    assert codigo == 0
    assert "candidatas: nenhuma" in saida
    assert "sorteio" in saida
    assert "DIVERGE" not in saida
    assert "turnos divergentes: nenhum" in saida


def test_turno_sem_a_cobra_viva_fica_fora(partida):
    partida = copy.deepcopy(partida)
    for s in partida["frames"][1]["Snakes"]:
        if s["ID"] == MINHA:
            s["Death"] = {"Cause": "self-collision", "EliminatedBy": MINHA, "Turn": 75}
    codigo, saida = rodar(partida, "--turns", "74-75", "--deep-budget-ms", "200")
    assert codigo == 0
    assert "turno 74" in saida
    assert "turno 75" not in saida
