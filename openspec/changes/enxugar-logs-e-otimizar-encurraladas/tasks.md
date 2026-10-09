## 1. Arquivar adicionar-logs-diagnostico

- [x] 1.1 Confirmar que o arquivamento já feito na árvore de trabalho está completo:
  - `openspec/changes/archive/2026-10-08-adicionar-logs-diagnostico/` existe e `openspec/changes/adicionar-logs-diagnostico/` não existe mais;
  - `openspec/specs/telemetria-de-diagnostico/spec.md` existe;
  - `openspec/specs/decisao-de-movimento/spec.md` tem o requisito "Explicação da decisão".
- [x] 1.2 No `tasks.md` arquivado, marcar 11.1 e 11.2 como `[x]`, cada uma com a nota "Substituída por `enxugar-logs-e-otimizar-encurraladas`: os eventos `start`, `end` e `request` e as sete consultas deixam de existir".
- [x] 1.3 Rodar `openspec validate enxugar-logs-e-otimizar-encurraladas --strict` e commitar o arquivamento separado do código (`chore(adicionar-logs-diagnostico): ...`).

## 2. region_sizes (Parte 1)

- [x] 2.1 Criar `tests/app/test_regioes.py` com o teste pontual: num 7x7 com uma parede vertical que deixa duas regiões, `region_sizes(board, parede)` é igual a `flood_fill(board, casa, parede)` em todas as casas do tabuleiro, nas casas da parede e em casas fora do tabuleiro ((-1,0), (7,3), (3,-1), (3,7)). Confirmar que ele falha, porque `region_sizes` ainda não existe.
- [x] 2.2 Implementar `region_sizes(board, blocked)` em `src/app/floodfill.py`, com rotulagem preguiçosa (design, decisão 1), docstring em português e imports relativos. `flood_fill` não muda.
- [x] 2.3 Rodar `pytest tests/app/test_regioes.py` e confirmar que passa.

## 3. trapped_rivals com region_sizes (Parte 1)

- [x] 3.1 Em `test_regioes.py`, copiar a implementação atual de `features.trapped_rivals` como `trapped_rivals_referencia`, que chama `flood_fill` por saída.
- [x] 3.2 Escrever o gerador de tabuleiros aleatórios com semente fixa (design, decisão 3):
  - 7x7 e 11x11, com 2 a 6 cobras;
  - corpos em passeio aleatório sem auto-interseção;
  - parte das caudas empilhadas;
  - estados montados com `tests/helpers`.
- [x] 3.3 Escrever o teste de equivalência: em pelo menos 500 tabuleiros, para cada casa vizinha da cabeça da cobra dentro do tabuleiro, `features.trapped_rivals` é igual à referência. Rodar antes da troca e confirmar que passa (as duas implementações ainda são iguais).
- [x] 3.4 Trocar, em `features.trapped_rivals`, o `flood_fill` por saída por uma `region_sizes(board, snap.obstacles | {new_head})` por chamada (design, decisão 2). Manter a docstring e a regra, e importar `region_sizes` de forma relativa.
- [x] 3.5 Rodar `test_regioes.py`, `test_estrategia.py` e `test_estrategia_v2.py` e confirmar que estão verdes, sem nenhuma alteração nas suítes de estratégia.

## 4. Teste de desempenho relativo (Parte 1)

- [x] 4.1 Em `test_regioes.py`, montar o estado do turno 0 no 11x11 com 8 cobras de 3 segmentos empilhados nas posições iniciais padrão: (1,1), (1,9), (9,1), (9,9), (1,5), (5,1), (5,9) e (9,5).
- [x] 4.2 Medir `evaluate_moves` com a implementação nova e com `features.trapped_rivals` trocada pela referência via `monkeypatch`:
  - o mesmo `snap` e as mesmas candidatas nos dois lados;
  - em cada lado, o mínimo de `timeit.repeat`.
- [x] 4.3 Exigir razão ≥ 5. Se a razão oscilar perto do limite, registrar o desvio aqui antes de trocar a medição (design, Riscos).
- [x] 4.4 Fazer o profiling local de `get_move` nesse mesmo estado (script no scratchpad, fora do repo) e confirmar que `trapped_rivals` deixou de ser a maior parcela. Registrar os números no commit ou no PR.

## 5. Testes de explain num arquivo próprio (Parte 2)

- [ ] 5.1 Criar `tests/app/test_explicacao.py` com a seção "Explicação da decisão" de `test_telemetry.py` copiada sem mudar o conteúdo: `COM_FOME`, `SEM_FOME`, `feat`, `por_move`, `MEDICOES` e todos os `test_explain_*`. Os imports ficam no topo.
- [ ] 5.2 Apagar essa seção de `test_telemetry.py` e rodar `pytest tests/app/test_explicacao.py`, confirmando que tem a mesma contagem de testes de antes.

## 6. Enxugar telemetry.py e main.py (Parte 2)

- [ ] 6.1 Reescrever `src/app/telemetry.py` (design, decisão 4):
  - mantém o logger dedicado e `log_event`, sem campos comuns;
  - ganha `timed_out_last_turn(snake, timeout)`, `log_move(state, move)`, `log_error`, que completa `game_id`/`turn` com `None`, e `report_errors(path, state)`;
  - mantém `validation_error_fields`;
  - remove `COMMON_FIELDS`, `FEATURE_FIELDS`, `SLOW_MS`, `_env_int`, o `ContextVar`, `new_request_context`, `end_request_context`, `bind_game`, `remaining_ms`, `_now`, `emit` e os builders de `start`, `end` e `move`;
  - atualiza a docstring do módulo.
- [ ] 6.2 Em `src/app/main.py`, remover `request_telemetry`, `_cold_start` e `import time`, trocar `bind_game` + `report_errors(path)` por `report_errors(path, state)` nas três rotas, e manter `strip_stage_prefix`, `remove_stage_prefix` e `log_validation_error`.

## 7. Simplificar logic.py (Parte 2)

- [ ] 7.1 Remover `mark_unsafe` e o dict `reasons`, e fazer os blocos do template voltarem a `is_move_safe["<direção>"] = False`, com os mesmos comentários.
- [ ] 7.2 Fazer a emergência e o caminho normal atribuírem `move`, com uma única chamada a `telemetry.log_move(state, move)` antes do `return MoveResponse(move=move)` (design, decisão 5). Remover a medição de `logic_ms`.
- [ ] 7.3 Remover `MoveChoice` e fazer `choose_move` devolver `str` via `decide(features, ctx)`. Deixar `start` e `end` só com a docstring, limpar os imports que sobraram e atualizar a docstring de `get_move`.
- [ ] 7.4 Rodar `test_logic.py`, `test_app.py`, `test_lambda.py` e as suítes de estratégia e confirmar que estão verdes sem alteração. Rodar também `grep -rn "from src" src/app` e confirmar que a saída é vazia.

## 8. Reescrever test_telemetry.py (Parte 2)

- [ ] 8.1 Testes de formato com `log_event`:
  - toda linha é um objeto JSON;
  - não há duplicação (`propagate` é `False`);
  - texto não ASCII sai literal;
  - com nível `ERROR`, só o `error` sai;
  - um campo não serializável não lança;
  - uma falha de serialização vira um `error`.
- [ ] 8.2 Testes do evento `move`:
  - tem exatamente os 5 campos, com `game_id` e `turn` do payload e `move` igual à resposta;
  - também sai na emergência;
  - turno 0 com o corpo empilhado;
  - não tem os campos removidos (cenários "Movimento observado" e "Comida alvo com fome");
  - `POST /move` via HTTP produz exatamente uma linha, o `move`;
  - `POST /start` e `POST /end` não produzem nenhuma linha.
- [ ] 8.3 Testes de `timed_out_last_turn` com timeout 500: `"500"` e `"750"` dão `true`; `"499"`, `"123"`, ausente, `""` e `"abc"` dão `false`.
- [ ] 8.4 "Logs não mudam a decisão": copiar os cenários de resposta única que já existem e rodar cada um com o logger em `CRITICAL` e em `DEBUG`.
- [ ] 8.5 Testes de `error`:
  - uma exceção forçada em `choose_move` gera um `error` com `path`, `exception`, `message`, `traceback`, `game_id` e `turn`, sem outros campos, e a exceção é relançada;
  - um payload sem `you` gera um `error` com `message` `"body.you: missing"` e o mesmo 422 do FastAPI puro;
  - um corpo que não é JSON gera um `error` com `game_id` nulo.
- [ ] 8.6 Teste "sem segredos": o cabeçalho `Authorization` e a query string não aparecem na saída.
- [ ] 8.7 Rodar o `pytest` completo e confirmar que está verde.

## 9. docs/logs.md

- [ ] 9.1 Reescrever `docs/logs.md` como um documento curto, com:
  - os eventos `move` e `error` e seus campos;
  - `LOG_LEVEL`;
  - o grupo de logs.
- [ ] 9.2 Incluir as quatro consultas, cada uma com uma linha de explicação:
  - a partida: `fields turn, move, timed_out_last_turn | filter event = "move" and game_id = "<id>" | sort turn asc`;
  - os turnos que estouraram o tempo: `fields game_id, turn, move | filter event = "move" and timed_out_last_turn = 1 | sort @timestamp desc`;
  - os erros: `fields path, exception, message, game_id, turn | filter event = "error" | sort @timestamp desc`;
  - a duração da Lambda pelas linhas `REPORT`: `filter @type = "REPORT" | stats avg(@duration), max(@duration), pct(@duration, 95) by bin(5m)`.
- [ ] 9.3 Incluir o aviso de que a sintaxe do filtro booleano (`timed_out_last_turn = 1`) precisa ser conferida contra logs reais.

## 10. Fechamento

- [ ] 10.1 Rodar o `pytest` completo e confirmar que está verde. Rodar `git diff --stat` e confirmar que `test_estrategia.py`, `test_estrategia_v2.py`, `test_logic.py`, `test_app.py`, `test_lambda.py`, `iac/` e `.github/` não mudaram.
- [ ] 10.2 Depois do deploy na `dev`, numa partida de 8 cobras na Arena, conferir:
  - exatamente uma linha `move` por turno no CloudWatch;
  - a consulta de `REPORT` com a duração média bem abaixo dos 155 a 525 ms de antes;
  - a sintaxe do filtro booleano, registrando em `docs/logs.md` a forma que funcionou.
- [ ] 10.3 Ao arquivar esta mudança, reescrever o `## Purpose` de `openspec/specs/telemetria-de-diagnostico/spec.md`, que ainda fala em "explicar cada movimento" e nas três hipóteses, para descrever os dois eventos enxutos.
