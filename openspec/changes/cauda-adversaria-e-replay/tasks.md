## 1. Regra de ocupação compartilhada (`src/app/simulator.py`)

- [x] 1.1 Escrever primeiro os testes de `occupied_after_turn(board)` em `tests/app/test_simulador.py`:
  - uma cauda que não está empilhada fica fora;
  - uma cauda empilhada fica dentro;
  - o corpo todo empilhado no começo da partida fica dentro;
  - cobras eliminadas (`alive=False`) ficam fora.
- [x] 1.2 Implementar `occupied_after_turn` como a união de `body[:-1]` de toda cobra viva, com docstring em português, e fazer `safe_moves` chamá-la. Os testes `test_safe_moves_*` atuais continuam verdes sem mudança.

## 2. Filtro de `get_move` com a regra compartilhada (`src/app/logic.py`)

- [x] 2.1 Ajustar o tabuleiro dos testes que mudam de resultado (ver a tabela da proposta). O bloqueio passa a `[(8,10),(7,10),(6,10),(6,9)]` em `test_estrategia.py::test_entra_na_propria_cauda` e no caso `entra_na_cauda` de `test_telemetry.py::test_logs_nao_mudam_a_decisao`, que continuam esperando `left`. Atualizar o comentário do tabuleiro.
- [x] 2.2 Escrever os testes novos em `tests/app/test_estrategia_v3.py`, com tabuleiro ASCII e o fixture `candidatas`, seguindo os cenários de "Não entrar em adversárias":
  - o turno 74 (candidatas `["left", "right"]`, `right` com `kill_chance` e sem `risky`, resposta `right`);
  - a cauda empilhada de uma adversária (candidatas `["up", "left"]`);
  - a cauda de uma adversária maior com a cabeça vizinha (`right` candidata e `risky`, resposta `left`).
  Conferir que eles falham com o código atual.
- [x] 2.3 Extrair `filter_moves(state, board) -> dict[str, str | None]`, na ordem canônica e com os motivos `neck`, `wall`, `body` e `health`. Pescoço, paredes e vida ficam como estão, com os comentários do template. Os blocos 3 e 4 viram um bloco "corpos" que consulta `simulator.occupied_after_turn(board)` com o índice da casa de destino.
- [x] 2.4 `get_move` monta `board = board_state.from_game(state)` depois do prazo, chama `filter_moves` e passa `board=board` para `choose_move`. `choose_move` ganha `board: BoardState | None = None` e só monta o tabuleiro quando ele não vem. O sorteio de emergência e `telemetry.log_move` não mudam.
- [x] 2.5 Remover `grid.opponent_cells` e o import dele em `logic.py`. `grid.tail_moves` continua por causa de `grid.obstacles`.
- [x] 2.6 Testes de `filter_moves` com os motivos: pescoço, parede, corpo da própria cobra, corpo de adversária e vida. Se uma direção é pescoço e corpo ao mesmo tempo, o motivo é `neck`.
- [x] 2.7 Rodar a suíte pelo `.venv`. Só os testes de 2.1 podem ter mudado de tabuleiro. Os 20 testes do template, `test_lambda.py` e `test_decisao_nao_importa_models` passam sem alteração, e `grep -rn "from src" src/app` não devolve nada.

## 3. Equivalência entre filtro e simulador

- [x] 3.1 Escrever em `tests/app/test_simulador.py` (ou num arquivo novo de equivalência) o gerador de tabuleiros com `random.Random` e semente fixa (design D3):
  - algumas centenas de tabuleiros 11x11, com 1 a 4 cobras;
  - corpos contínuos, sem sobreposição;
  - uma parte com a cauda empilhada e outra com o corpo todo empilhado;
  - vida 100 e sem hazards.
- [x] 3.2 Afirmar, para cada tabuleiro, que as direções com motivo `None` em `filter_moves` são iguais a `simulator.safe_moves(board, you)`, e que, quando o filtro não deixa nenhuma, `safe_moves` é `["up"]`.
- [x] 3.3 Afirmar uma quantidade mínima de tabuleiros com a cauda não empilhada de uma adversária vizinha da minha cabeça, e também com a cauda empilhada. Conferir que o teste falha com o filtro antigo, voltando temporariamente o bloco das adversárias.

## 4. Documentação da parte 1

- [x] 4.1 `docs/estrategia.md`:
  - o passo 1 do fluxo passa a dizer que a cauda das adversárias conta como livre quando não está empilhada, com a mesma regra do simulador;
  - a seção "Diferenças em relação às regras" diz que o filtro e o simulador seguem as regras oficiais de ocupação. A simulação não gera comida, mas isso já está em "Aproximações".
- [x] 4.2 `CLAUDE.md`: a descrição do filtro na seção de arquitetura troca "opponent bodies including their tails" pela regra de `occupied_after_turn`, e menciona `filter_moves`.

## 5. Busca com prazo opcional para o replay (`src/app/search.py`)

- [x] 5.1 Testes em `tests/app/test_busca.py`:
  - `minimax_value(..., deadline=None)` devolve o mesmo valor de hoje;
  - com um prazo que estoura no meio (relógio falso de `conftest.py`), devolve `None`;
  - com um prazo que nunca estoura, devolve o mesmo valor que sem prazo.
- [x] 5.2 Implementar o parâmetro `deadline=None` em `minimax_value`, com `_Search(..., deadline)` e `_Timeout` virando `None`. `best_move` não muda.

## 6. Replay: conversão de frames (`scripts/replay.py`)

- [x] 6.1 Criar `scripts/__init__.py`, `tests/scripts/__init__.py` e a fixture `tests/fixtures/arena_dc8c4f05_turnos_74_75.json`, com a partida e os frames 74 e 75 da partida real. As outras cobras têm `ID`, `Name`, `Author` e `EliminatedBy` anonimizados.
- [x] 6.2 Escrever primeiro os testes em `tests/scripts/test_replay.py`, sem rede:
  - `frame_to_state` no frame 74 (turno, duas cobras vivas, `you` com o corpo, a vida 96 e `length` 11 da spec, comida, `timeout` 500, `ruleset` `standard` sem `settings`, coordenadas `x`/`y`);
  - `played_move` (`left` de 74 para 75; desconhecida sem o próximo frame);
  - `turn_latency` (`176` do frame 75);
  - `pick_snake` pelo author (`gasperi` dentro de `VictorGasperi`), por `--snake` com id e com nome, nenhuma cobra batendo e mais de uma batendo;
  - `parse_turns` (`72-76`, `74`, `76-72` inválido, texto inválido);
  - `default_turns` (69 a 76 com `Death.Turn` 77; os 8 últimos frames sem morte; nada antes de 0).
- [x] 6.3 Implementar essas funções. O script insere a raiz do repositório em `sys.path` antes de importar `src.app`.

## 7. Replay: download com paginação

- [x] 7.1 Testes com um cliente falso que registra as URLs: duas páginas (cheia com os turnos 0 a 2 e depois a dos turnos 3 e 4, com `page_size=3`) juntam 5 frames ordenados por `Turn` e pedem `offset=0` e depois `offset=3`; uma página vazia encerra; um erro do cliente vira uma exceção com a URL.
- [x] 7.2 Implementar `fetch_game`, `fetch_frames` e o cliente padrão com `urllib.request` (timeout de 30 s), sem dependência nova.

## 8. Replay: relatório no terminal

- [x] 8.1 Implementar `render_board`, com a legenda dos testes de estratégia e as coordenadas nas margens, e um teste do tabuleiro do turno 74.
- [x] 8.2 Implementar `analyze_turn` com os itens 1 a 7 de "Relatório de cada turno" (design D5):
  - o logger `battlesnake` desabilitado;
  - os motivos vindos de `filter_moves`;
  - as medições com `Deadline` de `--deep-budget-ms`;
  - `get_move` com `SEARCH_BUDGET_MAX_MS` trocado num `try/finally`;
  - a busca por candidata e profundidade, com as marcas `VENCE`, `PERDE` e `EMPATE`;
  - o aviso quando o frame tem hazards.
- [x] 8.3 Implementar `main(argv, get_json=..., out=print)`:
  - os argumentos com `argparse`;
  - os códigos de saída de erro (intervalo inválido sem requisição, cobra não encontrada com a lista das cobras, falha de rede com a URL);
  - o destaque dos turnos divergentes e a linha de resumo no fim.
- [x] 8.4 Teste de `main` com o cliente falso servindo a fixture e `--turns 74`. A saída contém as candidatas `left` e `right`, o motivo `neck` de `down` e `body` de `up`, a escolha `right`, o turno 74 marcado como divergente (jogada `left`) e nenhuma linha JSON do evento `move`.
- [x] 8.5 Rodar `python scripts/replay.py dc8c4f05-84ac-4554-98f6-94b22d5a8b4d --turns 72-76` (com rede) e conferir que, no turno 74, as candidatas são `["left", "right"]` e a escolha é `right`. Anotar no resumo da implementação o que a ferramenta mostra no turno 72.

## 9. Documentação do replay e verificação final

- [x] 9.1 `docs/estrategia.md`, nova seção "Analisar uma partida":
  - o comando e as opções;
  - o que cada bloco do relatório mostra;
  - de onde vêm a direção jogada e a latência;
  - as premissas (timeout 500, sem dano de hazard);
  - a ressalva de que a CPU local é mais rápida que a da Lambda, com a sugestão de repetir com `--budget-ms` menores.
- [x] 9.2 `CLAUDE.md`: o comando do replay na seção de comandos e o `scripts/` como ferramenta local fora do pacote da Lambda.
- [x] 9.3 Verificação final pelo `.venv`:
  - `pytest` verde;
  - `grep -rn "from src" src/app` sem resultado;
  - `test_lambda.py` verde;
  - `decision.py` importando só `config`;
  - `requirements.txt` sem mudança;
  - a lista de testes que mudaram de resultado conferida com a tabela da proposta.
