## 1. Base de testes e configuração

- [x] 1.1 Acrescentar a `src/app/config.py` as constantes novas:
  - `SURVIVAL_MAX_DEPTH` 12, `SURVIVAL_MAX_NODES` 400 e `SURVIVAL_DEADLINE_EVERY` 32;
  - `W_SURVIVAL` 20, `W_HAZARD` 30 e `W_SQUEEZE` 0.5;
  - `MAX_SEARCH_DEPTH` 20, `WIN` 1_000_000 e `DRAW` -500_000;
  - os pesos da folha: `EVAL_TERRITORY` 1.0, `EVAL_AREA` 0.5, `EVAL_LENGTH` 10, `EVAL_FOOD` 1.0, `EVAL_HEALTH` 0.1 e `EVAL_CENTER` 0.5;
  - `SEARCH_BUDGET_FRACTION` 0.4 e `SEARCH_BUDGET_MAX_MS` vindo de `_positive_int_env("SEARCH_BUDGET_MAX_MS", 120)`.
- [x] 1.2 Testes do config:
  - os valores iniciais novos;
  - `_positive_int_env` com `"90"`, ausente, `""`, `"abc"`, `"-5"` e `"0"`, sem lançar.
- [x] 1.3 Criar `tests/conftest.py` com as fixtures:
  - `sem_busca`: `config.MAX_SEARCH_DEPTH = 0`;
  - `relogio_parado`: `clock.now` fixo em 0.0, criado junto com o `clock.py` da tarefa 3.1;
  - uma fábrica de relógio que estoura depois de N leituras;
  - um relógio que conta as leituras.
- [x] 1.4 Em `tests/helpers.py`, `make_game` ganha `hazards=()` e `hazard_damage=None`. Quando o dano vem, ele é escrito em `ruleset.settings.hazardDamagePerTurn`. Sem esses argumentos, o JSON gerado é o mesmo de antes.
- [x] 1.5 Aplicar `pytestmark = pytest.mark.usefixtures("sem_busca")` em `test_estrategia.py` e `test_estrategia_v2.py`, e a fixture em `test_telemetry.py::test_logs_nao_mudam_a_decisao`. A suíte continua verde.

## 2. Representação do tabuleiro (`src/app/board_state.py`)

- [x] 2.1 Implementar:
  - `idx(x, y, w)` e `xy(i, w)`;
  - `neighbor_table(w, h)` com `lru_cache`, na ordem `up, down, left, right`;
  - os dataclasses `SnakeState` e `BoardState` com `slots`;
  - os hazards como `dict[int, int]`, com a contagem;
  - `hazard_damage(ruleset)`;
  - `from_game(state)`, por duck typing e sem importar `models.py`.
- [x] 2.2 Escrever `tests/app/test_board_state.py` com os cenários de `representacao-do-tabuleiro`:
  - ida e volta do índice, inclusive num tabuleiro não quadrado;
  - os vizinhos no meio, nas bordas e nos cantos;
  - o reaproveitamento da tabela;
  - a cauda empilhada;
  - o hazard repetido;
  - o dano informado, ausente e inválido.

## 3. Relógio e prazo

- [x] 3.1 Criar `src/app/clock.py` com `now()` (que usa `time.perf_counter`), `Deadline(start, budget_ms)` (com `expired()` e `remaining_ms()`) e `budget_ms(timeout)`.
- [x] 3.2 Em `src/app/main.py`:
  - o middleware grava `request.state.started_at = clock.now()` antes de `call_next`;
  - `/move` recebe `request: Request` e chama `logic.get_move(state, started_at=...)`.

  Conferir que o 422 e os eventos de validação continuam iguais (`test_telemetry.py`).
- [x] 3.3 `logic.get_move(state, started_at=None)` cria o `Deadline`, com `clock.now()` quando `started_at` não vem, e o passa para `choose_move` por palavra-chave. Ajustar o substituto em `test_telemetry.py::test_falha_na_escolha_do_movimento` para aceitar `**kwargs`.
- [x] 3.4 Escrever `tests/app/test_tempo.py` com:
  - o orçamento, com timeout 500 dando 120 ms e timeout 200 dando 80 ms;
  - o instante marcado antes da validação: um relógio falso no middleware e um payload válido;
  - a chamada direta;
  - o relógio falso usado em todas as leituras.

## 4. Ocupação temporal (`src/app/occupancy.py`)

- [x] 4.1 Implementar `base_free_after(board)`:
  - `n - i` por segmento, com o maior valor por casa;
  - o crescimento das adversárias com a cabeça a 1 casa de uma comida: +1 em todo segmento, menos no último.

  Implementar também `with_growth(free_after, snake)` para a candidata que come.
- [x] 4.2 Implementar a BFS temporal sem espera, `temporal_area(board, free_after, start, t0, blocked)`, e escrever os testes: casa que libera a tempo e casa que não libera (3x1), tabuleiro vazio 5x5 dando 25, muro dando 10, início bloqueado ou fora do tabuleiro dando 0.
- [x] 4.3 Implementar `temporal_voronoi(board, free_after, seeds)`, que devolve as contagens e `owner[idx]`, com a mesma regra de empate do `voronoi` atual. Testes: os quatro cenários atuais de território reproduzidos em índices e a casa ocupada que libera a tempo (3x1).
- [x] 4.4 Implementar o `temporal_a_star(board, free_after, start, t0, goal, blocked)`, que devolve o caminho em índices, com `g` igual ao tempo de chegada. Testes: o caminho que contorna o obstáculo (11 casas), sem caminho, e um caminho que só existe porque uma casa libera a tempo.
- [x] 4.5 Escrever `tests/app/test_ocupacao.py` com os cenários de `free_after`: adversária reta, cauda empilhada, adversária ao lado de comida, comida com cauda já empilhada e candidata que come.

## 5. Sobrevivência por DFS e a nova `roomy`

- [x] 5.1 Implementar `src/app/survival.py` com `survival(board, free_after, me, direction, deadline)`, que devolve `(depth, survives, nodes)`. A DFS é iterativa e simula o corpo exato, a comida comida no caminho, a vida e os hazards. O prazo é conferido a cada `SURVIVAL_DEADLINE_EVERY` nós.
- [x] 5.2 Escrever `tests/app/test_sobrevivencia.py`:
  - a cobra que persegue a própria cauda num 3x2 tem `survives` verdadeiro e profundidade 5;
  - o bolsão sem saída dá profundidade 2 e `survives` falso;
  - o limite de nós (`SURVIVAL_MAX_NODES` = 3) é respeitado;
  - a fome dentro da busca (vida 2) dá profundidade 1;
  - a DFS cortada pelo prazo, com um relógio que estoura, devolve a profundidade alcançada.

## 6. Vida e hazards no filtro

- [x] 6.1 Em `logic.get_move`, acrescentar o bloco que elimina a direção sem comida em que `vida - 1 - dano × ocorrências <= 0`, com o comentário citando `standard.go` e a ordem das etapas.
- [x] 6.2 Testes de `get_move`, com desenho ASCII e resposta única:
  - vida 1 só sobrevive comendo (resposta `left`);
  - o hazard que zera a vida (resposta `right`);
  - hazards empilhados (`up` sai com a casa duas vezes na lista e fica com ela uma vez);
  - comida no hazard (`up` continua candidata).

## 7. Medições novas, comida alvo e pesos

- [x] 7.1 Em `decision.py`:
  - os campos `survival_depth`, `survives`, `hazard`, `rival_territory_pct` e `food_owned`, com os valores padrão;
  - as parcelas `survival`, `hazard` e `squeeze` em `score_terms`, com divisor `max(1, min(ctx.length, SURVIVAL_MAX_DEPTH))`;
  - nenhum import novo além de `config`.
- [x] 7.2 `snapshot(state, board=None)` monta o `BoardState`, o `free_after` base e o território do turno. `target_food` escolhe pelo território do turno, com o A\* temporal, e `FoodTarget.cost` passa a incluir o dano de hazard. `starving` usa `cost`. As assinaturas atuais continuam valendo.
- [x] 7.3 Em `evaluate_moves(state, candidates, snap=None, deadline=None)`:
  - área temporal, sobrevivência e `roomy = area >= length or survives`;
  - Voronoi temporal (`territory_pct`, `rival_territory_pct` e `food_owned`);
  - `food_step` e `food_dist` pelo A\* temporal;
  - `hazard`.

  `trapped_rivals` não muda.
- [x] 7.4 Testes das medições, conforme a spec de `caracteristicas-de-movimento`:
  - a medição montada sem os campos novos;
  - a fuga perseguindo a própria cauda;
  - o bolsão menor que a cobra, num tabuleiro novo;
  - o território da adversária no duelo;
  - a comida no meu território;
  - `hazard` com e sem dano.
- [x] 7.5 Testes da decisão: os pesos da sobrevivência, do hazard e do cerco, as parcelas novas na explicação, e o caso novo em `MEDICOES` de `test_explicacao.py`.
- [x] 7.6 Testes de estratégia:
  - o empate com uma rival do mesmo tamanho na comida alvo;
  - o hazard no caminho até a comida na política de fome;
  - "Evita o beco" com o bolsão novo;
  - "Beco versus cabeça a cabeça" com o bolsão real;
  - "Persegue a própria cauda".

## 8. Simulador (`src/app/simulator.py`)

- [x] 8.1 Implementar `step(board, moves)`, que devolve um `BoardState` novo, na ordem oficial:
  - movimento;
  - fome;
  - hazard, com as ocorrências empilhadas e a comida anulando o dano;
  - alimentação;
  - eliminação em duas fases, com as colisões depois da alimentação.

  O comentário cita o link das regras.
- [x] 8.2 Implementar `safe_moves(board, snake_id)`, com as direções que não são morte certa e, sem nenhuma, a primeira da ordem canônica.
- [x] 8.3 Escrever `tests/app/test_simulador.py` com um teste por regra:
  - movimento, perda de vida, alimentação e crescimento;
  - dano de hazard, hazards empilhados e comida no hazard;
  - sair do tabuleiro, colisão com corpo, cauda que sai do lugar;
  - cabeça a cabeça com a menor morrendo e entre iguais;
  - morte por fome e comida que salva da fome;
  - o corpo de uma cobra morta de fome que não mata;
  - o estado original intacto.

## 9. Minimax com alpha-beta (`src/app/search.py`)

- [x] 9.1 Implementar o max-min simultâneo com poda, os valores terminais (`WIN - p`, `-WIN + p`, `DRAW`) e a avaliação das folhas, com os pesos `EVAL_*` e o limite `±(|DRAW| - 1)`. Expor `minimax_value(..., prune=False)` para o teste da poda.
- [x] 9.2 Testes em `tests/app/test_busca.py`, com `relogio_parado` e profundidade fixa:
  - o cabeça a cabeça contra uma rival menor (profundidade 1, `right` não é derrota nem empate);
  - contra uma rival igual (`right` vale `DRAW` e não é escolhido);
  - a vitória mais cedo vale mais;
  - a folha fica entre `DRAW` e `-DRAW`;
  - a adversária sem saída;
  - a poda dá o mesmo valor que o minimax sem poda em tabuleiros 7x7 aleatórios com semente fixa.
- [x] 9.3 Testes de cena, com desenho ASCII e o tabuleiro concreto escolhido na implementação:
  - colisão: o único movimento que não perde é escolhido mesmo com nota heurística menor;
  - armadilha: o corredor que a rival fecha em 2 turnos é evitado com profundidade 3 ou mais;
  - alimentação: com vida baixa, a escolha heurística que vai para a comida da cobra é mantida pela busca, mesmo que a folha prefira outro movimento.

## 10. Aprofundamento iterativo e prazo na busca

- [x] 10.1 Implementar `best_move(board, me, rival, root_order, deadline)`:
  - profundidades `1..MAX_SEARCH_DEPTH`;
  - `_Timeout` conferido em todo nó, descartando a profundidade em andamento;
  - na raiz, a escolha heurística (`root_order[0]`) primeiro, com janela cheia;
  - o veto: se o valor dela for maior que `DRAW`, a profundidade termina com ela; se não, as demais são buscadas (o melhor da profundidade anterior primeiro, depois a ordem heurística) e vale a de maior valor, se for maior que o dela;
  - o desempate exato entre as substitutas (`alpha = melhor - 1e-9`), que favorece a ordem heurística;
  - a parada quando a árvore fica resolvida sem nenhum corte.

  Devolve a resposta da última profundidade completa, ou `None` se nenhuma terminar.
- [x] 10.2 Testes de tempo e do veto, com relógio falso:
  - o prazo estoura antes de a profundidade 1 terminar e vale a escolha heurística;
  - o prazo estoura no meio da profundidade 3, pela contagem `C2 + (C3 - C2) // 2`, e vale o resultado da profundidade 2;
  - o empate de valor entre as substitutas é desempatado pela nota heurística (a escolha heurística perde, e duas outras empatam);
  - a escolha heurística que não perde é mantida mesmo quando outra vale mais;
  - com todas as candidatas perdendo, vale a que perde mais tarde;
  - o prazo já vencido ao fim da heurística impede a busca;
  - com o relógio parado e `MAX_SEARCH_DEPTH` 3, as respostas são sempre as mesmas.

## 11. Integração em `choose_move`

- [x] 11.1 `choose_move(state, safe_moves, deadline=None)`:
  - converte o estado uma vez e roda `snapshot`, `build_context`, `evaluate_moves` e `explain`;
  - a busca só roda quando `MAX_SEARCH_DEPTH > 0`, há mais de uma candidata, há exatamente uma adversária e o prazo não passou;
  - sem resultado da busca, vale `decision.move`.
- [x] 11.2 Testes de integração: com duas adversárias a busca não roda (espiar `search.best_move` com `monkeypatch`); sem adversária, a busca não roda; com uma única candidata, a busca não roda.
- [x] 11.3 Conferir que `test_decisao_nao_importa_models` continua verde, que `test_lambda.py` passa e que `grep -rn "from src" src/app` não devolve nada.

## 12. Testes antigos e desempenho

- [x] 12.1 Reescrever os testes que mudam por construção, conforme a tabela da proposta:
  - `test_area_de_bolsao_menor_que_a_cobra`, que passa a afirmar a fuga e ganha o bolsão novo;
  - `test_beco_versus_cabeca_a_cabeca`, que vira `test_persegue_a_propria_cauda` mais o tabuleiro novo;
  - `test_evita_o_beco`, que troca de tabuleiro;
  - os casos `beco_versus_cabeca_a_cabeca` e `beco` de `test_logs_nao_mudam_a_decisao`.
- [x] 12.2 Testes de desempenho:
  - a fase heurística num 11x11 com 8 cobras de tamanho 6 fica abaixo de 10 ms (melhor de várias medições);
  - o 19x19 com 4 cobras continua abaixo de 50 ms;
  - o duelo 11x11 de meio de jogo, com o relógio real e o orçamento padrão, leva no máximo 130 ms;
  - `test_evaluate_moves_ao_menos_5x_mais_rapido_que_a_referencia`: se a razão cair abaixo de 5, o teste passa a medir só `trapped_rivals`.
- [x] 12.3 Rodar `.venv/bin/python -m pytest` completo. Conferir um por um os testes em risco listados na proposta. Atualizar a tabela "Testes antigos que mudam" de `proposal.md` com o que de fato mudou, e com o motivo. Ajustar os cenários das specs que mudarem.

## 13. Documentação e aceite

- [x] 13.1 Escrever `docs/estrategia.md`:
  - o fluxo (filtro → heurística → busca no duelo → prazo);
  - cada medição e cada peso;
  - as aproximações:
    - sem geração de comida na simulação;
    - o crescimento das rivais estimado pela comida vizinha;
    - a BFS temporal sem espera;
    - o A\* com `best_g`;
    - o território e a ocupação como estimativas;
    - o modelo paranoico;
    - a profundidade limitada pelo orçamento;
  - a cauda das rivais bloqueada no filtro, mais conservador que as regras;
  - como calibrar `SEARCH_BUDGET_MAX_MS` com `timed_out_last_turn` e a duração das linhas `REPORT`;
  - o efeito da CPU proporcional à memória;
  - o aviso de que uma variável definida à mão pode sumir num deploy.
- [x] 13.2 Atualizar o `CLAUDE.md` (seção Architecture) com os módulos novos, o prazo desde a chegada e a fixture `sem_busca`.
- [x] 13.3 Aceite local: pytest verde, `grep -rn "from src" src/app` vazio e `openspec validate estrategia-v3-busca-no-duelo --strict` válido.
- [ ] 13.4 Depois do deploy (fora do código): partidas de duelo e com 8 cobras na Arena sem nenhum turno com `timed_out_last_turn` verdadeiro. Se houver, reduzir `SEARCH_BUDGET_MAX_MS` antes de avaliar a estratégia.
