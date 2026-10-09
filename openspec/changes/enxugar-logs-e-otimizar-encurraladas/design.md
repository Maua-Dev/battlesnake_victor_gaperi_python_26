## Context

A motivação está em proposal.md (Why). O estado atual que importa para o como:

- `features.trapped_rivals(state, snap, new_head)` monta `sim = snap.obstacles | {new_head}`. Para cada rival, chama `flood_fill(board, saída, sim)` em cada casa de `neighbors(board, cabeça, set())`, o que inclui as casas bloqueadas, para as quais `flood_fill` devolve 0. A área da rival é o maior desses valores. `evaluate_moves` chama `trapped_rivals` uma vez por candidata.
- `flood_fill` é uma BFS a partir de uma casa, e a área da própria cobra (`evaluate_moves`) a usa com outro conjunto de bloqueios (`snap.blocked - {new_head}`).
- `telemetry.py` tem:
  - o logger dedicado (`_StdoutHandler`, `Formatter("%(message)s")`, `propagate=False`, `LOG_LEVEL`);
  - `log_event`/`emit`, que nunca lançam;
  - o contexto por requisição em `ContextVar`, que existia para o `request` e o `error` herdarem a partida;
  - os builders de `start`, `end` e `move`.
- `logic.get_move` registra o motivo de cada bloqueio em `reasons` (via `mark_unsafe`), mede `logic_ms` e emite o `move` em dois pontos: na emergência e no fim. `choose_move` devolve a dataclass `MoveChoice` só para alimentar o log.
- `main.py`:
  - `request_telemetry` é o middleware mais externo;
  - cada rota chama `bind_game(state)` e depois `report_errors(path)`;
  - o handler de `RequestValidationError` emite o `error` e delega ao handler padrão do FastAPI.

## Goals / Non-Goals

**Goals:**
- `trapped_rivals` passa a custar O(casas do tabuleiro) por candidata, em vez de O(rivais × saídas × casas), e devolve sempre o mesmo resultado de hoje.
- O código de telemetria fica do tamanho dos dois eventos que restam, e `logic.py` volta à forma do template, sem nada que só existia para o log.
- A ordem e o número de chamadas a `random` na emergência ficam iguais aos de hoje.

**Non-Goals:**
- Otimizar Voronoi, a área da própria cobra ou o A*, que passam a ser as maiores parcelas depois desta mudança.
- Reaproveitar a rotulagem entre direções, ou entre `trapped_rivals` e a área da própria cobra (os bloqueios são diferentes).
- Mudar o formato do `error`, além de tirar `ts`, `snake_id` e `aws_request_id`.

## Decisions

### 1. `region_sizes` com rotulagem preguiçosa

`region_sizes(board, blocked) -> Callable[[Pos], int]` devolve uma closure com um dict `casa -> tamanho`:
- uma casa fora do tabuleiro ou em `blocked` vale 0;
- uma casa já rotulada devolve o tamanho guardado;
- senão, uma BFS com `neighbors(board, casa, blocked)` percorre a região inteira, grava o tamanho em todas as casas dela e devolve esse tamanho.

Cada casa livre é visitada no máximo uma vez por função criada.

- **Por que preguiçosa:** quase todas as saídas das rivais caem na mesma região grande. A primeira consulta rotula essa região, e as seguintes custam uma busca no dict. Regiões que nenhuma saída toca nunca são percorridas.
- **Alternativa considerada, rotulagem gulosa:** rotular todas as componentes do tabuleiro de uma vez. É simples, mas percorre regiões que ninguém consulta, e o ganho sobre a preguiçosa é nulo.
- **Alternativa considerada, union-find:** é mais código para um tabuleiro de no máximo 25x25, e não traz ganho.
- **Alternativa considerada, cache de `flood_fill` por casa:** não aproveita que casas da mesma região têm o mesmo tamanho, e continuaria fazendo uma BFS por saída.
- `blocked` não é copiado. O chamador cria o conjunto (`snap.obstacles | {new_head}` já é um conjunto novo) e não o altera depois. A docstring deixa isso explícito.

### 2. Uma `region_sizes` por direção em `trapped_rivals`

```python
sizes = region_sizes(board, snap.obstacles | {new_head})
rival_area = max((sizes(cell) for cell in exits), default=0)
```

As saídas continuam vindo de `neighbors(board, cabeça, set())`. Uma saída bloqueada dá 0 nas duas versões, então o `max` é o mesmo. A docstring e a regra (área < tamanho, ids na ordem do tabuleiro) não mudam.

- **Alternativa considerada:** criar uma `region_sizes` por jogada, com `snap.obstacles`, e corrigir o efeito da nova cabeça. A nova cabeça pode partir uma região em várias, e o ganho sobre os 26x medidos não paga essa complexidade.

### 3. Testes de equivalência e desempenho contra uma cópia da implementação atual

`tests/app/test_regioes.py` guarda `trapped_rivals_referencia`, uma cópia literal da versão atual com `flood_fill` por saída, e cobre três coisas:
- **Pontual:** num 7x7 com uma parede vertical que deixa duas regiões, `region_sizes` é comparada com `flood_fill` em todas as casas do tabuleiro, nas casas da parede e em casas fora do tabuleiro, como (-1, 0) e (7, 3).
- **Equivalência:** um gerador com `random.Random(semente fixa)` monta pelo menos 500 tabuleiros 7x7 e 11x11, com 2 a 6 cobras.
  - Os corpos são passeios aleatórios sem auto-interseção, de tamanho variado. Parte deles tem a cauda empilhada, para exercitar a regra da cauda que fica parada.
  - Os estados são montados com `tests/helpers.snake`/`make_game`.
  - Para cada tabuleiro e cada casa vizinha da cabeça da cobra dentro do tabuleiro, `trapped_rivals` deve ser igual à referência. A comparação vale para qualquer `new_head`, não só para as candidatas seguras, e cobre mais casos.
- **Desempenho:** 11x11, turno 0, 8 cobras de 3 segmentos empilhados nas posições iniciais padrão, que são os cantos (1,1), (1,9), (9,1) e (9,9) e os meios (1,5), (5,1), (5,9) e (9,5).
  - Mede `evaluate_moves(state, candidatas, snap)` com a implementação nova e com `monkeypatch` trocando `features.trapped_rivals` pela referência.
  - O mesmo `snap` vale para as duas medições, e cada lado fica com o melhor de várias repetições (`timeit.repeat`, mínimo).
  - Exige razão ≥ 5. A comparação é relativa, por isso não depende da máquina do CI.
  - Pelo profiling, `trapped_rivals` ocupa cerca de 90% de `evaluate_moves` no turno 0. Com o ganho de 26x medido, a razão esperada fica perto de 7x.

### 4. Telemetria reduzida a `log_event`, `log_move`, `log_error` e `report_errors`

O que fica em `telemetry.py`:
- **Logger dedicado:** igual ao de hoje.
- **`log_event(event, level=INFO, **fields)`:** primitiva que nunca lança. Ela grava `{"event": event, **fields}`, sem campos comuns. Se a serialização falhar, grava no lugar um `error` com `path`, `game_id` e `turn` nulos. Os testes de formato usam `log_event` direto.
- **`timed_out_last_turn(snake, timeout) -> bool`:** `int(snake.latency) >= timeout`. Dá `False` em `TypeError` ou `ValueError`, o que cobre a latência ausente (`None`), vazia e não numérica. Substitui `engine_latency_ms`.
- **`log_move(state, move)`:** monta os cinco campos dentro de um `try`. Se a montagem falhar, sai um `error` no lugar, e a jogada segue. Substitui `emit` + `move_fields`: com um só evento de jogo, o builder genérico deixa de ter uso.
- **`log_error(**fields)`:** completa `game_id` e `turn` com `None` quando não vêm. Assim o `error` tem sempre as mesmas chaves.
- **`report_errors(path, state)`:** context manager que, numa exceção, emite o `error` com `game_id=state.game.id` e `turn=state.turn` e relança. A rota já tem o `GameState`, então passá-lo explicitamente substitui o `ContextVar`, o `bind_game` e o truque do dict mutável entre threads.
- **`validation_error_fields(path, exc)`:** igual à de hoje.

O que sai: `COMMON_FIELDS`, `FEATURE_FIELDS`, `_env_int`, `SLOW_MS`, o contexto por requisição, `remaining_ms`, `_now`, `emit`, `engine_latency_ms`, `observed_last_move`, `start_fields`, `end_fields` e `move_fields`.

### 5. O `move` sai num ponto só de `get_move`

`get_move` fica assim:
- os quatro blocos do template voltam a fazer `is_move_safe[direção] = False`;
- a emergência e o caminho normal atribuem `move` (`random.choice(all_moves)` ou `choose_move(state, safe_moves)`);
- uma única chamada a `telemetry.log_move(state, move)` vem antes do `return MoveResponse(move=move)`.

Assim "exatamente um por chamada, inclusive na emergência" vale pela estrutura, e não por duas chamadas paralelas. `random.choice` continua sendo a única chamada a `random`, e só acontece na emergência.

`choose_move` volta a ser `snapshot` → `build_context` → `evaluate_moves` → `decide`, e devolve a direção (`str`). Fica com `decide` e não com `explain`, porque `decide` é a interface que o Jev vai substituir, e `explain(...).move == decide(...)` já é garantido por teste. Os imports de `FoodTarget`, `hunger_reasons`, `Decision`, `MoveFeatures`, `explain` e `time` saem de `logic.py`. `start` e `end` ficam só com a docstring.

- **Alternativa considerada:** emitir o `move` na rota `/move` de `main.py`. Os testes chamam `get_move` direto e esperam o evento, e a emergência é decidida em `logic`.

### 6. `main.py` sem `request_telemetry`

Saem `request_telemetry`, `_cold_start` e `import time`. Ficam:
- `strip_stage_prefix`, usado pelo middleware de stage e pelo handler de validação;
- `remove_stage_prefix`;
- `log_validation_error`.

As rotas ficam `with telemetry.report_errors("/move", state): return logic.get_move(state)`, e o mesmo vale para `/start` e `/end`.

### 7. Testes de `explain` num arquivo próprio

A seção "Explicação da decisão" de `test_telemetry.py` vai inteira para `tests/app/test_explicacao.py`, com os mesmos nomes e corpos: `COM_FOME`/`SEM_FOME`, `feat`, `por_move`, `MEDICOES` e os testes. Só os imports necessários (`pytest` e `src.app.decision`) sobem para o topo. `test_telemetry.py` é reescrito do zero com a lista de testes de proposal.md. Os cenários de "logs não mudam a decisão" são copiados como estão hoje.

## Risks / Trade-offs

- **[Risco] O teste de desempenho relativo falhar de forma intermitente no CI.** A razão esperada é perto de 7x, contra um mínimo de 5x. → Cada lado fica com o mínimo de várias repetições, com o GC desligado durante a medição. Se ainda assim oscilar, o fallback é medir `trapped_rivals` isolada, onde a razão é perto de 26x. Isso fica registrado como desvio na task, e não é feito em silêncio.
- **[Risco] A equivalência passar nos aleatórios e falhar num caso de borda,** por exemplo uma saída fora do tabuleiro, uma cauda empilhada ou a nova cabeça partindo a região de uma rival. → O gerador inclui caudas empilhadas e tabuleiros pequenos e cheios (7x7 com até 6 cobras). O teste pontual cobre casas fora do tabuleiro e bloqueadas. As suítes de estratégia ficam sem alteração e precisam continuar verdes.
- **[Trade-off] Menos diagnóstico no CloudWatch.** Sem `directions`, `reason` e `logic_ms`, uma jogada estranha só se explica reproduzindo o estado localmente. → É o pedido explícito: o evento ficou ilegível. `decision.explain` continua disponível para essa reprodução.
- **[Risco] Consultas salvas no Logs Insights pararem de funcionar.** → `docs/logs.md` traz as consultas novas, e o tempo da Lambda passa a vir das linhas `REPORT`.
- **[Risco] A Lambda de 128 MB continuar perto do limite mesmo com `trapped_rivals` 26x mais rápida,** com Voronoi e a área virando o gargalo. → Fica fora do escopo. A verificação na Arena (critério de aceite) mostra se basta, e, se não bastar, isso vira outra mudança.

## Migration Plan

1. Arquivar `adicionar-logs-diagnostico`, com 11.x marcadas como substituídas, e commitar o arquivamento antes de começar.
2. Implementar a Parte 1 e a Parte 2 em commits separados. Cada parte deixa o `pytest` verde sozinha.
3. Fazer push na `dev`. O CD roda os testes e faz o deploy, sem nenhuma mudança em `iac/` ou nos workflows.
4. Numa partida de 8 cobras na Arena, conferir que sai uma linha `move` por turno e que a consulta de `REPORT` mostra a duração média bem abaixo de 155 a 525 ms. Conferir também a sintaxe do filtro booleano.
5. **Rollback:** reverter os commits na `dev`. O CD faz um novo deploy com a versão anterior.
