## Context

A motivação está em `proposal.md` (Why). O estado atual que molda a abordagem:

- **`logic.py` só tem dois logs de texto**: `get_move` grava `logger.info` na emergência e `logger.debug` no resto, com o logger do módulo propagando para o logger raiz da Lambda (com o prefixo `[INFO]\t<ts>\t<request id>`). `start` e `end` gravam uma linha de texto cada.
- **A escolha tem três etapas**: candidatas → características → decisão. `decision.py` não pode importar `models.py` (teste `test_decisao_nao_importa_models`), porque o Jev vai substituir `decide(features, ctx)`.
- **`decide` não expõe o porquê**: usa `min` com a chave `(layer, -score, MOVE_ORDER.index)` e devolve só a `str`.
- **A fome vem de três critérios** combinados por `or` em `build_context` (`starving`, `outsized`, `behind_schedule`), e `DecisionContext` guarda só o booleano.
- **`Snake.latency: str | None` já existe** em `models.py`.
- **Mangum 0.22 coloca `aws.context`** (o `LambdaContext`) no scope ASGI. A Function URL usa o formato do API Gateway v2.
- **FastAPI roda rotas `def` numa thread** com cópia do contexto, e o `@app.middleware("http")` (BaseHTTPMiddleware) chama a aplicação em outra task. Um `ContextVar.set` feito dentro da rota não volta para o middleware.
- **Os testes chamam `logic.get_move` direto** (sem HTTP) e via `TestClient`. O `capsys` troca `sys.stdout` a cada teste.

## Goals / Non-Goals

**Goals:**
- Um único ponto de emissão (`log_event`) que garanta o formato e os campos comuns da spec `telemetria-de-diagnostico`.
- Extrair o "porquê" da execução real (motivos de eliminação, camadas, pontuações) sem recalcular nada e sem uma segunda implementação da regra.
- Falha de telemetria nunca muda a resposta.

**Non-Goals:**
- Não criar uma camada genérica de observabilidade (métricas, tracing, EMF).
- Não registrar o estado inteiro do tabuleiro: as posições das outras cobras não entram no `move`. Dá para reconstruí-las pelo replay da partida na Arena.
- Não explicar decisões de um futuro `decide` do Jev: `explain` descreve a regra atual.

## Decisions

### 1. `telemetry.py`: logger dedicado com stdout resolvido no `emit`

- O logger `battlesnake` é configurado no import, de forma idempotente (só adiciona o handler se ainda não houver um do mesmo tipo), com `propagate=False`, `Formatter("%(message)s")` e nível `LOG_LEVEL` (padrão `INFO`, valor inválido cai em `INFO`).
- O handler é um `StreamHandler` cuja stream é resolvida para `sys.stdout` **a cada emit**, e não guardada no import. Assim o `capsys` do pytest captura as linhas sem um handler de teste, e o comportamento na Lambda é o mesmo.
  - *Alternativa:* `StreamHandler(sys.stdout)` fixo, com os testes adicionando um handler próprio. Foi descartada porque os testes não exercitariam o handler real.
- `log_event(event, level=logging.INFO, **fields)` funciona assim:
  - retorna cedo se `not logger.isEnabledFor(level)`, sem montar nada;
  - monta `{"event", "ts", game_id, turn, snake_id, aws_request_id}` (`null` por padrão), por cima o contexto da requisição e por cima os `fields` explícitos;
  - serializa com `json.dumps(separators=(",", ":"), ensure_ascii=False, default=str)`.
- `ts` vem de `datetime.now(timezone.utc).isoformat(timespec="milliseconds")`, com `Z` no lugar de `+00:00`.
- **`log_event` nunca lança.** Um erro de serialização vira uma linha mínima `{"event":"error","exception":...,"message":"telemetry", ...}`, e a jogada segue. Isso cumpre "Logs não mudam a decisão" mesmo com bug na telemetria.
- `SLOW_MS` é lido de `os.environ` no import, como atributo do módulo (`telemetry.SLOW_MS`), e usado na hora (`telemetry.SLOW_MS`), para o teste poder trocar com `monkeypatch`. É a mesma convenção do `config`.

### 2. Contexto por requisição: `ContextVar` com um dict mutável

- O middleware cria um dict novo por requisição (`aws_request_id`, `game_id`, `turn` e `snake_id`, todos `None` menos o id da Lambda) e faz `_ctx.set(d)`.
- As rotas chamam `telemetry.bind_game(state)`, que **muta** esse mesmo dict. Como a thread da rota e a task do `call_next` recebem uma cópia do contexto que aponta para o mesmo objeto, a mutação aparece no `request` e no `error` emitidos depois.
  - *Alternativa:* `ContextVar.set` na rota. Não funciona, porque o set fica na cópia.
  - *Alternativa:* `request.state`. Exigiria `Request` em todas as rotas e no `log_event`.
- Os eventos `start`, `move` e `end` passam `game_id`, `turn` e `snake_id` **explicitamente** (`telemetry.game_fields(state)`). Assim `logic.get_move` chamado direto, sem middleware, como em `test_logic.py`, já emite um `move` completo. Fora de uma requisição, `_ctx.get()` devolve um dict vazio.

### 3. Middleware de `request` separado do de stage

- Um novo `@app.middleware("http")` é declarado **depois** de `remove_stage_prefix`, o que o torna o mais externo no Starlette. Ele mede do recebimento ao fim do `call_next` com `time.perf_counter()`.
- O `path` logado é normalizado por um helper `strip_stage_prefix(path)`, extraído da lógica atual e usado pelos dois middlewares. Assim o log não depende da ordem em que o scope é mutado.
- `aws_request_id` vem de `scope.get("aws.context").aws_request_id`, e `remaining_ms` de `get_remaining_time_in_millis()` ao fim da requisição. Fora da Lambda, os dois são `None`.
- O `cold_start` usa uma flag de módulo em `main.py` (`_cold_start = True`), que vira `False` na primeira requisição. O teste a restaura com `monkeypatch.setattr(main, "_cold_start", True)`.
- Se `call_next` lançar, o `request` sai com `status` 500 e a exceção é relançada (`try/except/finally`).
- Os cabeçalhos, a query e o corpo nunca são lidos pelo middleware, o que cumpre "Sem segredos" por construção.

### 4. Erros: context manager nas rotas e handler de validação

- `telemetry.report_errors(path)` é um context manager que, numa `Exception`, emite `error` (nível ERROR) com `path`, `exception=type(exc).__name__`, `message=str(exc)` e `traceback=traceback.format_exc()`, e faz `raise`. Cada rota de jogo faz `bind_game(state)` e depois `with report_errors("/move"): ...`.
- **Payload inválido:** o FastAPI responde 422 antes de a rota rodar, e esse é exatamente um caso da hipótese 1 (o motor escolhe no lugar da cobra). Por isso entra um `@app.exception_handler(RequestValidationError)` que:
  - emite `error` com `message` igual a `"; ".join(f"{loc}: {type}")` dos `exc.errors()`, sem o `input`, que poderia carregar o payload;
  - lê `game_id` e `turn` de `exc.body` quando é dict com os tipos certos;
  - devolve `await fastapi.exception_handlers.request_validation_exception_handler(request, exc)`, com o mesmo 422 e o mesmo corpo de hoje.

### 5. `mark_unsafe` e `blocked_by`

- `get_move` ganha `reasons: dict[str, list[str]]` (as 4 direções, listas vazias). Cada `is_move_safe[d] = False` vira `mark_unsafe(is_move_safe, reasons, d, motivo)`, que faz a mesma atribuição e acrescenta o motivo se ele ainda não está na lista. Corpo empilhado repete segmentos, e sem essa checagem `self` sairia duplicado.
- A ordem dos motivos é a ordem dos blocos: `neck`, `wall`, `self`, `opponent`. O bloco de adversárias continua só olhando direções ainda seguras (`if is_move_safe[d] and ...`), o que mantém o comportamento. Uma casa de adversária não coincide com parede nem com o próprio corpo, então nenhum motivo se perde.
- Não existe `head_to_head` em `blocked_by`: o cabeça a cabeça é `risky` (spec "Direções do evento move").

### 6. `explain` e `Decision` em `decision.py`, sem duplicar a regra

- `score_terms(f, ctx) -> dict[str, float]` devolve as 7 parcelas, na mesma ordem e com os mesmos sinais de hoje (as condições falsas valem 0).
- `score(f, ctx)` passa a ser `sum(score_terms(f, ctx).values())`. O resultado é bit a bit igual ao atual: somar `+0.0` não altera um float, `x - d` é igual a `x + (-d)` em IEEE 754 e a ordem das somas é preservada. Os testes de `decide` existentes e os de estratégia confirmam.
- `RankedMove(move, layer, score, terms)` e `Decision(move, reason, ranking)` são dataclasses congeladas, sem tipos de `models`.
- `explain(features, ctx)` funciona assim:
  - ordena pela chave atual `(layer, -score, MOVE_ORDER.index)`;
  - toma o primeiro como `move`;
  - deriva o `reason` comparando com o segundo: um só → `only_option`; camada diferente → `layer`; pontuação diferente → `score`; igual → `tie`. Comparar só com o segundo basta, porque ele é o melhor dos demais pela mesma chave.
- `decide(features, ctx)` vira `return explain(features, ctx).move`. A regra existe num lugar só, e "Coerência com a decisão" vale por construção.
  - *Alternativa:* reconstruir o motivo fora de `decision.py`, em `logic`. Duplicaria a chave e arriscaria divergir quando os pesos mudarem.
- **Custo:** `explain` calcula `score_terms` uma vez por candidata (no máximo 3). Hoje `min` já calcula `score` uma vez por candidata.

### 7. Critérios de fome sem mudar `DecisionContext`

- `features.hunger_reasons(state, snap) -> list[str]` avalia os três critérios, sem curto-circuito (são funções puras e baratas), e devolve os nomes que dispararam.
- `build_context` passa a usar `hungry = bool(hunger_reasons(state, snap))`. O valor é o mesmo do `or` de hoje.
- `DecisionContext` não muda, porque é o contrato do Jev.

### 8. `choose_move` devolve o rastro; `get_move` emite

- `choose_move(state, safe_moves) -> MoveChoice` é uma dataclass em `logic.py` com `context`, `hunger_reasons`, `features`, `target` (a `FoodTarget` do snapshot) e `decision`. `get_move` usa `choice.decision.move`. Nenhum teste chama `choose_move` direto, e o teste de erro só faz `monkeypatch` dela para lançar.
- `get_move` funciona assim:
  - marca `t0 = perf_counter()` no início;
  - calcula como hoje;
  - mede `logic_ms` **antes** de montar o evento;
  - chama `telemetry.log_event("move", **telemetry.move_fields(...))`;
  - devolve `MoveResponse`.
- No ramo de emergência o fluxo é o mesmo, com `choice=None` e `reason="emergency"`. O `random.choice` fica onde está.
- Os builders (`move_fields`, `start_fields`, `end_fields`, `engine_latency_ms` e `observed_last_move`) ficam em `telemetry.py`, que pode importar `models`, `grid` e `decision`, mas não `logic` (para evitar ciclo).
- `move_fields` só reorganiza o que já foi calculado. Nada de flood fill, A* ou Voronoi roda de novo.
- Os `logger.info`/`logger.debug` de texto e o `import logging` saem de `logic.py`. `info()` não emite evento, porque o `request` do `GET /` cobre.

### 9. Conversões

- `engine_latency_ms`: `int(latency)` dentro de `try`, e `None` para ausente, vazio ou não numérico.
- `timed_out_last_turn`: `latency is not None and latency >= game.timeout`.
- `observed_last_move`: com `dx, dy = body[0] - body[1]`, procura em `grid.MOVES` a direção com esse delta; `None` se o corpo tem menos de 2 segmentos ou o delta não é de uma casa (empilhado, ou wrap em outros modos).
- `duration_ms` e `logic_ms` são floats arredondados a 2 casas. `remaining_ms` e as latências são int.

### 10. Testes (`tests/app/test_telemetry.py`)

- O fixture `eventos(capsys)` faz `json.loads` de cada linha de `capsys.readouterr().out` e falha se alguma não for JSON.
- Os cenários da spec usam `tests/helpers.py` (`snake`, `make_game`). Os de HTTP usam `TestClient(app)` e builders de dict locais. Os de `decision.explain` usam `MoveFeatures` montadas à mão, como em `test_estrategia_v2.py`.
- **Determinismo:**
  - os testes de estratégia existentes continuam passando sem alteração;
  - entra um teste parametrizado que roda os estados dos cenários da spec com `LOG_LEVEL` efetivo `CRITICAL` e `DEBUG` (via `monkeypatch` do nível do logger) e compara os movimentos;
  - outro teste confere `decide == explain(...).move` e `score == sum(terms)` sobre as medições dos cenários de `decide`.
- **Desempenho:**
  - monta o estado 19x19 com 9 cobras;
  - roda `choose_move` uma vez fora da medição;
  - mede só `move_fields` + `log_event`, a melhor de 20 repetições, e exige menos de 5 ms.
- **Campos descobertos:** um teste achata o `move` desse estado e confere que fica abaixo de 200 folhas (ver Riscos).

### 11. Deploy intocado

Nada muda em `iac/` nem nos workflows. `LOG_LEVEL` e `SLOW_MS` têm padrões no código (`INFO` e `250`), e a Lambda roda com eles, porque a IaC não define essas variáveis.

## Risks / Trade-offs

- **[Volume de log]**: um `move` tem alguns KB, e são cerca de 300 turnos por partida. → O CloudWatch cobra por GB ingerido, e o volume da Arena é pequeno. `LOG_LEVEL=WARNING` desliga tudo menos `error`, sem mudar código.
- **[Limite de campos do Logs Insights]**: o Insights descobre um número limitado de campos por evento JSON (confirmar o valor atual na documentação da AWS durante a implementação). Com 9 cobras o `move` fica perto de 155 folhas, e `trapped_rivals` pode crescer. → O teste de contagem pega regressões. Se estourar, as parcelas de `score_terms` saem primeiro, porque dá para recalculá-las a partir das medições.
- **[Booleanos no Insights]**: não se sabe se `true` vira `1` ou `"true"` nos filtros. → `docs/logs.md` registra as duas formas e a que funcionou contra logs reais depois do primeiro deploy (spec "Consultas documentadas").
- **[`explain` desatualizado com o Jev]**: quando o Jev substituir `decide`, o `reason` vai descrever a regra antiga. → Fica registrado em `docs/logs.md`, e a troca para o Jev terá de revisar o evento `move`.
- **[BaseHTTPMiddleware e o fim da resposta]**: `call_next` retorna quando os cabeçalhos estão prontos, e o corpo JSON já foi calculado. → `duration_ms` cobre todo o trabalho da cobra. Só não cobre a serialização do Mangum para a Lambda, o que fica documentado.
- **[Telemetria quebrando a jogada]**: um bug num builder poderia lançar dentro de `get_move`. → A montagem do `move` também fica dentro do guarda de `log_event` (o builder é chamado por uma função que captura e emite a linha mínima de erro). Os testes cobrem todos os ramos (candidatas, emergência, sem comida, sem rivais).
- **[Corpo inválido com dados do jogador]**: o `message` da validação pode citar locais de campos. → Os valores (`input`) nunca entram, só `loc` e `type`.

## Migration Plan

1. Merge na `dev` → o CD de sempre roda o `pytest` e faz o `cdk deploy`, sem nenhuma mudança na IaC.
2. Jogar uma partida na Arena. No Logs Insights do grupo da Lambda, conferir:
   - um `start`, um `move` por turno, um `end` e um `request` por chamada, todos como JSON puro;
   - que as sete consultas retornam linhas sem `parse`.
3. Registrar em `docs/logs.md` a sintaxe de filtro booleano que funcionou, num commit de docs.
4. **Rollback**: reverter o commit na `dev`. Não há estado nem migração de dados. Para só silenciar os logs, definir `LOG_LEVEL=ERROR` no console da Lambda (o próximo deploy apaga a variável e volta ao padrão `INFO`).

## Open Questions

- A sintaxe exata dos filtros booleanos no Logs Insights (`slow = 1` ou `slow = "true"`) só se confirma com logs reais. A resposta muda só `docs/logs.md`.
