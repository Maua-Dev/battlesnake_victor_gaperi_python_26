## Why

Em partidas de 8 cobras na Arena, todo turno estoura os 500 ms. O motor ignora a resposta e repete o movimento anterior, e a cobra sobe até morrer, mesmo quando a lógica escolhe certo. Na Lambda de 128 MB (a memória não pode subir), o `logic_ms` ficou entre 61 e 460 ms. O profiling local mostra que `trapped_rivals` responde por 87 a 90% do `get_move`, porque roda até 4 × 7 × 4 = 112 flood fills por jogada, quase sempre sobre a mesma região livre. Os logs não pesam no tempo, mas o evento `move` ficou grande demais para ler: na prática só interessa o turno, a direção escolhida e se o turno anterior estourou o tempo.

## What Changes

As duas partes são independentes e podem ser implementadas em qualquer ordem. Nenhuma decisão da cobra muda: o mesmo estado dá o mesmo movimento.

**Parte 1: rivais encurraladas com rotulagem de regiões**
- `floodfill.region_sizes(board, blocked)`: devolve uma função casa → tamanho da região livre que contém a casa, igual a `flood_fill(board, casa, blocked)` para qualquer casa. Cada região é percorrida por uma BFS só, na primeira consulta, e as consultas seguintes leem o tamanho guardado.
- `features.trapped_rivals` passa a criar uma `region_sizes` por direção e a consultá-la para todas as saídas de todas as rivais. A regra de "Rivais encurraladas" não muda.
- `flood_fill` continua existindo e medindo a área da própria cobra.
- Testes novos: equivalência pontual com `flood_fill`, equivalência em pelo menos 500 tabuleiros aleatórios contra uma cópia da implementação atual e desempenho relativo de pelo menos 5x no turno 0 de 11x11 com 8 cobras.

**Parte 2: logs enxutos** (**BREAKING** para as consultas do CloudWatch)
- Ficam só dois eventos, cada um uma linha JSON pura:
  - `move`, com exatamente `event`, `game_id`, `turn`, `move` e `timed_out_last_turn`;
  - `error`, com `path`, `exception`, `message`, `traceback`, `game_id` e `turn`.
- Saem os eventos `request`, `start` e `end`, o middleware `request_telemetry`, `_cold_start`, `SLOW_MS`, `remaining_ms` e `aws_request_id`.
- Saem também os campos `ts`, `snake_id`, `you`, `engine_latency_ms`, `observed_last_move`, `board`, `directions`, `safe_moves`, `hungry`, `hunger_reasons`, `food_target`, `astar_path_len`, `reason` e `logic_ms`.
- Sai o contexto por requisição (`ContextVar`, `new_request_context`, `bind_game`). `report_errors` passa a receber o `GameState` da rota.
- `logic.py` perde o que só existia para o log:
  - `mark_unsafe` e o dict `reasons`; os blocos do template voltam a fazer `is_move_safe[direção] = False`;
  - a dataclass `MoveChoice` e a medição de `logic_ms`; `choose_move` volta a devolver a direção (`str`);
  - o corpo de `start` e `end`, que passam a ter só a docstring.
- Ficam: `decision.explain`, `features.hunger_reasons`, o middleware `remove_stage_prefix` e o handler de `RequestValidationError`.
- Os testes de `explain` saem de `test_telemetry.py` e vão, sem mudança, para `tests/app/test_explicacao.py`. `test_telemetry.py` é reescrito para os dois eventos.
- `docs/logs.md` vira um documento curto com os dois eventos, quatro consultas do Logs Insights (a partida, os turnos que estouraram, os erros e a duração pelas linhas `REPORT`) e um aviso sobre a sintaxe do filtro booleano.

**OpenSpec**
- `adicionar-logs-diagnostico` é arquivada antes, com as tasks 11.x marcadas como substituídas por esta mudança.

## Capabilities

### New Capabilities
(nenhuma)

### Modified Capabilities
- `telemetria-de-diagnostico`: só os eventos `move` e `error` ficam.
  - **Saem:** os eventos `request`, `start` e `end`; os campos comuns (`ts`, `snake_id`, `aws_request_id`); as direções e o motivo do `move`; o requisito de custo dos logs.
  - **Mudam:** "Uma linha JSON por evento", "Nível configurável", "Evento move", "Evento error", "Sem segredos" e "Consultas documentadas".

`caracteristicas-de-movimento` não muda, porque a regra de rivais encurraladas continua a mesma e só a implementação troca. `decisao-de-movimento` também não muda, porque `explain` continua igual.

## Impact

- **Código:**
  - `src/app/floodfill.py` (nova `region_sizes`);
  - `src/app/features.py` (`trapped_rivals`);
  - `src/app/telemetry.py` (reduzido aos dois eventos);
  - `src/app/main.py` (sem `request_telemetry` e `bind_game`; `report_errors` recebe o estado);
  - `src/app/logic.py` (sem `mark_unsafe`, `reasons`, `MoveChoice` e `logic_ms`).
- **Testes:**
  - novos: `tests/app/test_regioes.py` (region_sizes, equivalência e desempenho) e `tests/app/test_explicacao.py`;
  - reescrito: `tests/app/test_telemetry.py`;
  - sem nenhuma alteração: `test_estrategia.py`, `test_estrategia_v2.py`, `test_logic.py`, `test_app.py` e `test_lambda.py`.
- **Docs:** `docs/logs.md` reescrito.
- **Operação:** as consultas salvas no Logs Insights que usam campos removidos deixam de funcionar. A duração da Lambda passa a ser lida nas linhas `REPORT`.
- **Sem mudança:** infraestrutura (memória, região e timeout da Lambda), dependências, pesos, camadas e regras da estratégia.
