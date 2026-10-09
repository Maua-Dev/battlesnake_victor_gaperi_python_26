## Context

Hoje há duas regras de ocupação para "morte certa no próximo turno":
- `logic.get_move` trabalha sobre o `GameState` (Pydantic). O bloco 3 libera a própria cauda com `grid.tail_moves`, e o bloco 4 bloqueia todo o corpo das adversárias com `grid.opponent_cells`, cauda incluída.
- `simulator.safe_moves` trabalha sobre o `BoardState` (índices) e bloqueia `body[:-1]` de toda cobra viva. É a regra oficial, e a busca a usa em todos os nós internos.

`simulator.py` faz parte dos módulos indexados e não pode importar `models.py`. Já `logic.py` importa os dois mundos. Hoje o `BoardState` da jogada só é montado em `choose_move`, depois do filtro.

A Arena (`https://arena.devmaua.com/api`) expõe os dados assim, conforme conferido na partida do diagnóstico:
- `GET /games/<id>` devolve `{"Game": {"ID", "Status", "Width", "Height"}}`, sem ruleset nem timeout.
- `GET /games/<id>/frames?offset=&limit=` devolve `{"count": <frames nesta página>, "frames": [...]}`. Sem `limit`, devolveu os 78 frames, e um `offset` além do fim devolve `count: 0`.
- Cada frame tem `Turn`, `Food`, `Hazards` e `Snakes`. Cada cobra tem `ID`, `Name`, `Author`, `Health`, `Body` (com `X` e `Y`), `Latency` (string: `"194"`, `"0"` ou `"timeout"`), `Shout` e `Death` (`null` ou `{"Cause", "EliminatedBy", "Turn"}`).
- As cobras mortas continuam nos frames seguintes, com `Death` preenchido.
- O `Latency` do frame T+1 é o da resposta ao `/move` do turno T: no frame 1 aparece a latência da primeira jogada.
- O `author` de `info()` é `"gasperi"`, e a cobra na Arena tem `Author` `"VictorGasperi"` e `Name` `"gasperi-1"`. Uma comparação exata não acharia a cobra.

## Goals / Non-Goals

**Goals:**
- Uma única função define as casas ocupadas depois do turno, e o filtro e o simulador a usam.
- A ferramenta de replay usa as mesmas funções da cobra (filtro, medições, decisão, `get_move` e busca), sem reimplementar nenhuma delas.
- As partes da ferramenta que não dependem de rede podem ser testadas com um cliente HTTP falso.

**Non-Goals:**
- Mudar `grid.obstacles` e `grid.tail_moves`, que as medições estáticas usam (rivais encurraladas, `voronoi`, `floodfill`).
- Simular a CPU da Lambda no replay.
- Ler regras de partida que a Arena não informa.

## Decisions

### D1. `simulator.occupied_after_turn(board) -> set[int]`
A função devolve a união de `body[:-1]` de toda cobra viva. É a regra que `safe_moves` já usa, só extraída. `safe_moves` passa a chamá-la, e o filtro de `get_move` também.

- **Por que no simulador:** é uma regra do jogo, e o simulador é o módulo das regras. Ele não importa `models.py`, então a função pode ser usada por quem trabalha com índices e também por `logic.py`.
- **Alternativa recusada: uma versão em `grid.py` sobre o Pydantic.** O simulador não pode importá-la, e teríamos duas implementações, que é exatamente o que divergiu.
- **Alternativa recusada: deixar a função em `board_state.py`.** Esse módulo só representa o tabuleiro e não contém regras.
- **Cobra de tamanho 1:** `body[:-1]` é vazio, então a casa dela fica livre. Isso segue as regras, porque ela anda e sai da casa. `grid.tail_moves` trata esse caso como ocupado, mas isso só importava para a própria cauda, e a casa da própria cabeça nunca é vizinha da cabeça. Uma adversária de tamanho 1 não existe no modo standard. Nada muda na prática, e as duas camadas passam a concordar.

### D2. O filtro vira `logic.filter_moves(state, board) -> dict[str, str | None]`
A função devolve um dict na ordem canônica: para cada direção, o motivo da eliminação (`"neck"`, `"wall"`, `"body"` ou `"health"`) ou `None` se a direção é candidata.

- **Ordem dos blocos:** a mesma de hoje (pescoço, paredes, corpos e vida). Vale o primeiro motivo encontrado.
- **Blocos 3 e 4:** viram um bloco só, "corpos", que consulta `occupied_after_turn(board)` com a casa de destino convertida em índice. Esse bloco só roda se a direção ainda for segura, o que garante que o destino está dentro do tabuleiro.
- **Comentários didáticos:** os do template ficam dentro de `filter_moves`.
- **`get_move`:** monta `board = board_state.from_game(state)` logo depois do prazo, chama `filter_moves` e passa o mesmo `board` para `choose_move`. O sorteio de emergência e `telemetry.log_move` ficam como estão.
- **`choose_move(state, safe_moves, deadline=None, board=None)`:** sem `board`, monta o `BoardState` como hoje. Os espiões dos testes já repassam `**kwargs`. A conversão só muda de lugar e não custa mais tempo. No caminho de emergência ela é usada só pelo filtro.
- **Alternativa recusada: manter o filtro inline e reproduzi-lo no replay.** O replay mostraria motivos que podem divergir do filtro de verdade, que é o mesmo tipo de erro que esta mudança corrige.
- **Premissa:** `you` está em `board.snakes`, como a API garante. `evaluate_moves` já depende disso. Os montadores de estado dos testes do template (`make_state`, `game_state`) põem `you` na lista.

`grid.opponent_cells` fica sem uso e sai. `grid.tail_moves` continua, porque `grid.obstacles` a usa.

### D3. Teste de equivalência por tabuleiros aleatórios
Um gerador com `random.Random(semente)` monta algumas centenas de tabuleiros 11x11, com 1 a 4 cobras. Os corpos são passeios aleatórios contínuos que não se cruzam e não se sobrepõem às outras cobras. Uma parte deles tem a cauda empilhada, e outra parte tem o corpo todo empilhado, como no começo da partida. Todas as cobras têm vida 100, e não há hazards, então a regra de vida nunca dispara.

Para cada tabuleiro, o teste compara as direções com motivo `None` em `filter_moves` com `simulator.safe_moves(board, you)`. Quando o filtro não deixa nenhuma, `safe_moves` deve ser `["up"]`. O teste também confere que a amostra tem casos em que a cauda não empilhada de uma adversária é vizinha da minha cabeça, e também com a cauda empilhada. Assim o caso que motivou a mudança fica coberto de fato.

### D4. Estrutura do `scripts/replay.py`
O script é dividido em funções puras, que os testes importam como `scripts.replay`. Por isso entram `scripts/__init__.py` e `tests/scripts/__init__.py`.
- `parse_turns(text) -> tuple[int, int]`.
- `fetch_game(engine, game_id, get_json)` e `fetch_frames(engine, game_id, get_json, page_size=100)`. `get_json(url)` é o cliente HTTP injetado. O padrão usa `urllib.request` com timeout de 30 s e transforma erro de rede ou HTTP numa exceção com a URL.
- `pick_snake(frames, wanted, author)`: com `wanted`, compara exatamente com `ID` ou `Name`. Sem `wanted`, procura `author.lower()` como substring de `Author.lower()` ou `Name.lower()` e exige exatamente uma cobra.
- `frame_to_state(game, frame, you_id) -> GameState`: monta o dict do `/move` e o valida com `GameState.model_validate`.
- `played_move(frame, next_frame, you_id)` e `turn_latency(next_frame, you_id)`.
- `render_board(state) -> list[str]`, `default_turns(frames, you_id)`, `analyze_turn(...) -> list[str]` e `main(argv, get_json=..., out=print) -> int`.

`python scripts/replay.py` põe `scripts/` em `sys.path[0]`, e não a raiz. Por isso o script insere a raiz do repositório (`Path(__file__).resolve().parents[1]`) em `sys.path` antes de importar `src.app`. Os imports absolutos `from src.app ...` ficam só no script, fora de `src/app/`.

**Alternativa recusada: `httpx`.** Ele está só em `requirements-dev.txt`. O `urllib` resolve dois GETs de JSON sem nenhuma dependência.

### D5. Como o replay reexecuta a lógica
- **Log de produção:** `logging.getLogger("battlesnake").disabled = True` no começo de `main`. `log_event` consulta `isEnabledFor`, que é falso num logger desabilitado, e o código de produção não muda.
- **Candidatas e motivos:** vêm de `logic.filter_moves(state, board)`.
- **Medições (item 5):** `snapshot`, `build_context`, `evaluate_moves(..., deadline=Deadline(now, deep))` e `explain`, as mesmas funções de `choose_move`. A profundidade alvo mostrada é `min(tamanho, SURVIVAL_MAX_DEPTH)`.
- **Orçamento de produção (item 6):** `config.SEARCH_BUDGET_MAX_MS` recebe `--budget-ms` dentro de um `try/finally` que restaura o valor, e o script chama `logic.get_move(state)`. O estado convertido tem `timeout` 500, então o orçamento efetivo é `min(200, --budget-ms)`, a mesma conta de produção.
- **Busca com prazo folgado (item 7):** `search.minimax_value` ganha um parâmetro opcional `deadline=None`. Com um prazo que passa no meio, ela devolve `None`. Sem prazo, o comportamento é o de hoje. O replay chama `minimax_value(board, me, rival, d, root_moves=[move], deadline=...)` para cada candidata, em profundidades crescentes, e para na primeira profundidade em que alguma candidata volta `None`. Essa profundidade é descartada inteira, e as anteriores ficam. Com uma raiz de um movimento só e janela cheia, o valor é exato. O laço não passa de `MAX_SEARCH_DEPTH`. Isso não muda a busca da cobra, que continua em `best_move`.
- **Marcas de fim de jogo:** `VENCE em k` quando `valor >= WIN - profundidade`, com `k = WIN - valor`; `PERDE em k` quando `valor <= -WIN + profundidade`; `EMPATE` quando `valor == DRAW`.
- **Alternativa recusada: usar `search._Search` e `_Timeout` direto no script.** Seria depender de nomes privados num script que ninguém roda na CI.

### D6. Estado convertido
- `game`: `{"id": game_id, "ruleset": {"name": "standard"}, "map": "standard", "timeout": 500}`. A Arena não informa as regras, então o dano de hazard fica 0. Uma partida com hazards seria analisada sem o dano, e o relatório avisa isso numa linha quando o frame tem hazards.
- **Cobra viva:** uma cobra está viva no frame quando `Death` é `null`.
- **Ordem:** `board.snakes` segue a ordem do frame, porque o desempate do território depende dela, e `you` é o mesmo dict da cobra analisada.

### D7. Fixture
Fica em `tests/fixtures/arena_dc8c4f05_turnos_74_75.json`, com `{"game": ..., "frames": [frame 74, frame 75]}` da partida real. As outras cobras têm `ID`, `Name` e `Author` trocados por valores neutros (`rival-a`, `autor-a`, ...), e o `EliminatedBy` acompanha a troca. A cobra analisada fica como está. O teste de paginação não usa a fixture: ele monta frames mínimos num cliente falso que registra as URLs pedidas.

## Risks / Trade-offs

- **[A cobra entra mais vezes na cauda de rivais.]** → É o comportamento correto pelas regras, e o simulador e a DFS já contavam com ele. O risco de cabeça a cabeça continua marcado por `risky`, e a camada de segurança prefere as candidatas não arriscadas. O turno 75 da partida confirma a regra no motor da Arena: a cauda (3,4) da rival saiu do lugar.
- **[A API da Arena não é documentada e pode mudar.]** → O replay é ferramenta local e não roda em produção. Os erros mostram a URL, e os testes usam a fixture e um cliente falso, sem rede.
- **[O replay roda numa CPU muito mais rápida que a da Lambda.]** → Com `--budget-ms 120`, a escolha local pode diferir da de produção só por profundidade. A seção "Analisar uma partida" explica isso e sugere repetir com orçamentos menores (por exemplo 10 a 30 ms) para imitar a Lambda.
- **[Mudar `config.SEARCH_BUDGET_MAX_MS` em tempo de execução.]** → Isso só acontece no processo do script, num `try/finally`. O código de produção não muda.
- **[A análise profunda é lenta.]** → Ela gasta até `--deep-budget-ms` por turno nas medições e o mesmo na busca, então 5 turnos levam até cerca de 50 s. O prazo é configurável.
- **[O teste de equivalência pode não exercitar o caso raro.]** → O próprio teste exige uma quantidade mínima de tabuleiros com a cauda de uma adversária vizinha da minha cabeça.

## Migration Plan

O deploy é o de sempre, com push na `dev`, e a CI roda `pytest` antes do `cdk deploy`. Não há mudança na IaC, nas variáveis de ambiente nem nos workflows. O rollback é reverter o commit da parte 1. A ferramenta de replay não vai para a Lambda.

## Open Questions

- Por que no turno 72 a produção jogou `up` e a lógica local escolhe `right`? Essa é a primeira investigação a fazer com a ferramenta, e a resposta não muda esta mudança.
