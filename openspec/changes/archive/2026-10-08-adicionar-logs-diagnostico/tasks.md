Cada grupo deixa a suíte verde e pode ser commitado sozinho. Ao fim de cada grupo:
- rodar `.venv/bin/pytest`;
- confirmar que os 20 testes do template, `test_estrategia.py`, `test_estrategia_v2.py` e `test_lambda.py` passam **sem alteração**;
- confirmar que `grep -rn "from src" src/app` não retorna nada.

Os testes novos vão em `tests/app/test_telemetry.py`, importando de `src.app.*` e de `tests.helpers`.

## 1. telemetry.py e formato

- [x] 1.1 Criar `src/app/telemetry.py`, só com imports relativos, contendo:
  - o logger `battlesnake`, configurado de forma idempotente, com `propagate=False`, `Formatter("%(message)s")` e nível `LOG_LEVEL` (padrão `INFO`, valor inválido vira `INFO`);
  - um handler de stdout que resolve `sys.stdout` a cada emit (design, decisão 1);
  - `SLOW_MS` lido do ambiente (padrão 250).
- [x] 1.2 Implementar o contexto por requisição: `ContextVar` com um dict mutável, `new_request_context(aws_request_id)`, `bind_game(state)` (muta o dict) e `game_fields(state)` (design, decisão 2).
- [x] 1.3 Implementar `log_event(event, level=logging.INFO, **fields)` assim:
  - sai cedo com `isEnabledFor`;
  - campos comuns com `null` por padrão, depois o contexto, depois os campos explícitos;
  - `ts` ISO 8601 UTC com `Z`;
  - `json.dumps(separators=(",", ":"), ensure_ascii=False, default=str)`;
  - nunca lança, e um erro de serialização vira uma linha mínima de `error`.
- [x] 1.4 Criar `tests/app/test_telemetry.py` com o fixture `eventos(capsys)` (`json.loads` de cada linha, falha se alguma não for JSON) e os testes:
  - "Toda linha é um objeto JSON" (`event` e `ts` presentes, `ts` termina em `Z`);
  - "Sem duplicação";
  - `ensure_ascii` (texto "ção" aparece literal);
  - "Só erros" (nível do logger em `ERROR` via `monkeypatch`, `log_event` de INFO não emite nada);
  - um campo não serializável não lança.

## 2. Evento request e cold start

- [x] 2.1 Em `main.py`, extrair `strip_stage_prefix(path)` da lógica de `remove_stage_prefix`, sem mudar seu comportamento.
- [x] 2.2 Adicionar a flag de módulo `_cold_start = True` e um middleware `request_telemetry`, declarado depois de `remove_stage_prefix` para ser o mais externo, que:
  - cria o contexto com o `aws_request_id` de `scope.get("aws.context")`;
  - mede com `perf_counter`;
  - em `finally`, emite `request` com `path` normalizado, `method`, `status` (500 em exceção, relançada), `duration_ms` (2 casas), `cold_start`, `remaining_ms` (`get_remaining_time_in_millis()` ou `None`) e `slow` (`duration_ms > telemetry.SLOW_MS`).
- [x] 2.3 Testes via `TestClient`:
  - "Move bem-sucedido" (`status` 200, `duration_ms` numérico, `method` POST);
  - "Cold start" (`monkeypatch.setattr(main, "_cold_start", True)`, primeira `true` e segunda `false`);
  - "Prefixo de stage" (`/dev/move` → `path` `/move`);
  - "Requisição lenta" (`SLOW_MS` 0);
  - "Requisição sem payload de jogo" (`GET /` com campos de jogo nulos);
  - "Fora da Lambda" (`aws_request_id` nulo).
- [x] 2.4 Teste "Dentro da Lambda": chamar o app via ASGI com um scope que tem `aws.context` falso (`aws_request_id="abc-123"`, `get_remaining_time_in_millis` → 1234) e conferir `aws_request_id` e `remaining_ms`.

## 3. mark_unsafe e blocked_by

- [x] 3.1 Em `logic.py`, criar `mark_unsafe(is_move_safe, reasons, direction, reason)`: atribui `False` e acrescenta o motivo sem repetir.
- [x] 3.2 Criar `reasons` em `get_move` e trocar cada `is_move_safe[...] = False` dos blocos pescoço, parede, corpo e adversárias por `mark_unsafe` com `neck`, `wall`, `self` e `opponent`. A condição `if is_move_safe[d] and ...` do bloco de adversárias continua igual.
- [x] 3.3 Rodar a suíte e confirmar que nada mudou: refatoração pura.

## 4. Decision e reason

- [x] 4.1 Em `decision.py`, criar `score_terms(f, ctx) -> dict[str, float]` (`territory`, `food`, `trap`, `kill`, `hunt`, `danger`, `center`, na ordem e com os sinais atuais) e reescrever `score` como `sum(score_terms(...).values())` (design, decisão 6).
- [x] 4.2 Criar as dataclasses congeladas `RankedMove(move, layer, score, terms)` e `Decision(move, reason, ranking)` e a função `explain(features, ctx) -> Decision`:
  - `ValueError` com lista vazia;
  - ordena pela chave atual;
  - `reason` vem da comparação com o segundo colocado.
  - `decide` passa a devolver `explain(features, ctx).move`.
- [x] 4.3 Em `features.py`, criar `hunger_reasons(state, snap) -> list[str]` (`starving`, `outsized`, `behind_schedule`, sem curto-circuito) e fazer `build_context` usar `hungry=bool(hunger_reasons(...))`. `DecisionContext` não muda.
- [x] 4.4 Em `logic.py`, criar a dataclass `MoveChoice(context, hunger_reasons, features, target, decision)` e fazer `choose_move` devolvê-la. `get_move` usa `choice.decision.move`.
- [x] 4.5 Testes de `explain` com `MoveFeatures` montadas à mão: "Única medição", "Vence pela camada", "Vence pela pontuação" (parcelas `territory` 20 e `food` 40), "Empate com lista fora de ordem" e lista vazia.
- [x] 4.6 Teste "Coerência com a decisão": para um conjunto de medições variadas (as dos cenários de `decide` em `test_estrategia_v2.py` remontadas), `decide == explain(...).move` e `score == sum(terms.values())`. Rodar `test_decisao_nao_importa_models`.

## 5. Evento move completo

- [x] 5.1 Em `telemetry.py`, criar `move_fields(state, reasons, safe_moves, choice, chosen, reason, logic_ms) -> dict` com:
  - `you`, `board`, `safe_moves`, `hungry`, `hunger_reasons`, `food_target`, `astar_path_len`, `chosen`, `reason` e `logic_ms`;
  - `directions` com `target`, `blocked_by`, as 11 medições, `layer`, `score` e `score_terms`, tudo `null` para as direções eliminadas e no ramo de emergência;
  - `game_fields(state)`.
  - Nada é recalculado.
- [x] 5.2 Em `get_move`, fazer o seguinte:
  - marcar `t0` no início e medir `logic_ms` antes de montar o evento;
  - emitir `move` exatamente uma vez nos dois ramos (normal e emergência, com `reason="emergency"` e `choice=None`), antes do `return`;
  - chamar o builder dentro de uma função que captura exceções e emite a linha mínima de erro, para a jogada nunca falhar por causa da telemetria.
- [x] 5.3 Remover de `logic.py` os `logger.info`/`logger.debug` de texto, o `logger` e o `import logging`.
- [x] 5.4 Testes de `move` com `get_move` direto:
  - "Adversária ao lado e parede acima" / "Única opção" (`blocked_by` exatos, `safe_moves` `["right"]`, medições nulas nas eliminadas, `reason` `only_option`);
  - "Cabeça a cabeça arriscado" (`left` com `risky` e `layer` 1);
  - "Empate decidido pela ordem canônica" (`tie`, `up`);
  - "Pontuação com fome" (`score`, `right`, `food_step` só em `right`, `score_terms.food` > 0) e "Comida alvo com fome" (`food_target` `[8,5]`, `astar_path_len` 3, `hunger_reasons` com `starving`);
  - "Camada de segurança" (`layer`, `up`);
  - "Emergência" (as 4 direções com `blocked_by` não vazio, `safe_moves` vazio);
  - "Parcelas somam a pontuação";
  - "Campos de jogo num move" (turno 7).
- [x] 5.5 Teste "Cenários de estratégia existentes": parametrizado com os estados dos cenários acima e de `test_estrategia.py` que têm resposta única. Compara o movimento com o logger em `CRITICAL` e em `DEBUG`, e com o valor esperado.
- [x] 5.6 Teste "Tabuleiro cheio":
  - estado 19x19 com 9 cobras e comidas;
  - `choose_move` fora da medição;
  - a melhor de 20 repetições de `move_fields` + `log_event` abaixo de 5 ms;
  - no mesmo estado, o `move` achatado em folhas fica abaixo de 200 campos.

## 6. Latência do motor e movimento observado

- [x] 6.1 Em `telemetry.py`, criar:
  - `engine_latency_ms(snake)` (`int` em `try`, `None` para ausente, vazio ou não numérico);
  - `timed_out_last_turn` (`latency is not None and latency >= game.timeout`);
  - `observed_last_move(snake)` (delta `body[0] - body[1]` procurado em `grid.MOVES`, senão `None`).
  - Incluir os três no `move_fields`.
- [x] 6.2 Testes:
  - "Latência informada pelo motor" (`"123"` → 123, falso);
  - "Latência ausente ou vazia" (ausente e `""` → `null`, falso);
  - "Turno anterior estourou o tempo" (`"500"` com timeout 500 → verdadeiro);
  - "Movimento observado" ((5,5) e (5,4) → `up`);
  - "Corpo empilhado" (turno 0, três segmentos em (5,5) → `null`).

## 7. Eventos start e end

- [x] 7.1 Em `telemetry.py`, criar:
  - `start_fields(state)`: `ruleset` `{name, version}`, `map`, `timeout`, `width`, `height`, `snake_count` e `opponents` `[{id, name}]` na ordem do tabuleiro;
  - `end_fields(state)`: `turns`, `won`, `eliminated` e `survivors`.
  - Emitir os eventos em `logic.start` e `logic.end`.
- [x] 7.2 Em `main.py`, fazer as rotas `/start`, `/move` e `/end` chamarem `telemetry.bind_game(state)` antes de delegar a `logic`.
- [x] 7.3 Testes: "Partida com adversárias" (`start`), "Vitória", "Eliminada" e "Várias vivas" (`end`).

## 8. Evento error

- [x] 8.1 Em `telemetry.py`, criar o context manager `report_errors(path)`: numa `Exception`, emite `error` (nível ERROR) com `path`, `exception`, `message` e `traceback`, e faz `raise`. Envolver em `main.py` a chamada a `logic` nas três rotas de jogo.
- [x] 8.2 Em `main.py`, registrar `@app.exception_handler(RequestValidationError)` que:
  - emite `error` com `exception` `RequestValidationError`, `message` só com `loc` e `type` de cada erro, e `game_id`/`turn` de `exc.body` quando forem do tipo certo;
  - delega a `fastapi.exception_handlers.request_validation_exception_handler`.
- [x] 8.3 Testes:
  - "Falha na escolha do movimento": `monkeypatch` de `logic.choose_move` para lançar, `TestClient` com `raise_server_exceptions=True`, a exceção chega ao teste, e o `error` traz `path` `/move`, tipo, mensagem, `traceback` não vazio, `game_id` e `turn` 7, com `request` de `status` 500;
  - "Payload inválido": resposta 422 com corpo igual ao de antes e `error` com `game_id` `g1` e `turn` 3;
  - "Sem segredos": cabeçalho `Authorization: Bearer segredo-xyz` ausente de todas as linhas.

## 9. Deploy intocado

- [x] 9.1 Confirmar que `iac/` e `.github/workflows/` não têm nenhuma alteração (`git status --short iac .github` vazio). `LOG_LEVEL` e `SLOW_MS` ficam só com os padrões do código.

## 10. docs/logs.md

- [x] 10.1 Criar `docs/logs.md` com:
  - o formato (uma linha JSON por evento) e a tabela dos eventos e campos;
  - o significado de cada `reason` e de `blocked_by`;
  - a nota de que `reason` descreve a regra atual de `decision.py`, não a de um futuro Jev.
- [x] 10.2 Documentar as sete consultas do Logs Insights, cada uma com uma explicação curta:
  - linha do tempo;
  - timeouts;
  - lentas e cold starts;
  - emergências;
  - distribuição por `reason`/`chosen`;
  - erros;
  - resultados.
  - Usar os nomes de campo desta change (`reason` com `layer`/`score`/`tie`, `hunger_reasons`), com as duas formas de filtro booleano (`= 1` e `= "true"`) marcadas como "a validar".
- [x] 10.3 Escrever o roteiro das três hipóteses:
  - **timeout ou erro**: `timed_out_last_turn`, `error`, `request` com `status` diferente de 200 ou `slow`, ou `observed_last_move` diferente do `chosen` do turno anterior;
  - **emergência**: `reason = "emergency"` e os `blocked_by`;
  - **decisão da lógica**: `reason`, `layer`, `score` e `score_terms` das candidatas.
- [x] 10.4 Rodar a suíte inteira e confirmar todos os testes verdes.

## 11. Validação depois do deploy

- [x] 11.1 Depois do deploy na `dev`, jogar uma partida na Arena e conferir no Logs Insights: um `start`, um `move` por turno, um `end` e um `request` por chamada, todos como JSON puro com os campos descobertos sem `parse`. Substituída por `enxugar-logs-e-otimizar-encurraladas`: os eventos `start`, `end` e `request` e as sete consultas deixam de existir.
- [x] 11.2 Rodar as sete consultas, registrar em `docs/logs.md` a sintaxe de filtro booleano que funcionou e remover a marcação "a validar". Substituída por `enxugar-logs-e-otimizar-encurraladas`: os eventos `start`, `end` e `request` e as sete consultas deixam de existir.
