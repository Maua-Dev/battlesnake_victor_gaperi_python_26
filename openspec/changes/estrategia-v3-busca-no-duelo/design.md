## Context

Hoje a jogada passa por `logic.get_move`, que filtra as candidatas, e por `choose_move`, que chama `features.snapshot`, `build_context`, `evaluate_moves` e `decision.decide`. As medições de espaço (`flood_fill`, `voronoi` e `a_star`) trabalham com tuplas `(x, y)` e com o `Board` do Pydantic, e tratam como obstáculo fixo todo corpo, menos as caudas que saem do lugar. Medido localmente (Python 3.12, M-series), a jogada leva cerca de 2,8 ms num 19x19 com 4 cobras e cerca de 0,3 ms num 11x11 com 8 cobras.

Algumas restrições moldam a abordagem (a motivação está em proposal.md, seção "Why"):
- **CPU da Lambda.** A Lambda tem 128 MB, e a CPU é proporcional à memória: 1 vCPU equivale a 1.769 MB, então 128 MB dá cerca de 7% de uma vCPU. Código Python que só faz conta roda dezenas de vezes mais devagar que no laptop. Os orçamentos em milissegundos valem no relógio de parede da Lambda, e as metas locais (10 ms, 50 ms) servem só para comparar versões.
- **Fronteira com o Jev.** `decision.py` não importa `models.py`. A busca roda depois de `decide` e não muda essa fronteira.
- **Testes do template.** Os testes do template não mudam e chamam `logic.get_move(state)` direto, sem instante de chegada. `test_telemetry.py` troca `logic.choose_move` por um substituto.

Antes de escrever o design, conferimos as regras oficiais em `BattlesnakeOfficial/rules`, arquivo `standard.go`:
- **Ordem das etapas:** `GameOver → Movement → Starvation → HazardDamage → FeedSnakes → Elimination`.
- **`DamageHazardsStandard`:**
  - lê `settings.Int("hazardDamagePerTurn", 0)`;
  - pula a casa que tem comida;
  - aplica o dano uma vez **para cada entrada repetida** da casa na lista de hazards;
  - limita a vida a [0, 100];
  - elimina a cobra na hora se a vida chegar a 0.
- **Movimento antes da alimentação.** O movimento remove o último segmento antes de `growSnake` repetir a nova cauda. Por isso, no turno em que uma cobra come, a casa da cauda dela **sai** do lugar, e o atraso só aparece no turno seguinte (a cauda empilhada).
- **`EliminateSnakesStandard`:**
  - primeiro elimina por vida e por sair do tabuleiro;
  - depois marca as colisões todas juntas: o próprio corpo, o corpo de outra cobra (`Body[1:]`) e o cabeça a cabeça (`len(s) <= len(other)`);
  - as colisões usam os corpos depois da alimentação e só as cobras ainda vivas.

## Goals / Non-Goals

**Goals:**
- Uma única conversão por jogada para uma representação por índices, usada por tudo que roda em laço quente.
- Uma busca no duelo que nunca atrasa a resposta: a escolha heurística sai primeiro, e a busca só melhora o resultado quando termina uma profundidade dentro do prazo.
- Resultados determinísticos nos testes, sem depender da velocidade da máquina.

**Non-Goals:**
- Tabela de transposição, heurística de killer moves ou estratégias mistas (equilíbrio de Nash) no movimento simultâneo.
- Reescrever `flood_fill`, `region_sizes`, `voronoi` e `a_star` em índices. Eles continuam como estão, para as rivais encurraladas e para os testes existentes. As versões temporais são novas.
- Calibrar os pesos. Os valores iniciais são palpites, e a calibração acontece na Arena.

## Decisions

### 1. `board_state.py`: índices, vizinhos em cache e hazards com contagem
- `idx = y * w + x`. `neighbor_table(w, h)` fica em `functools.lru_cache` e devolve uma tupla de tuplas na ordem `up, down, left, right`.
- `BoardState` e `SnakeState` são dataclasses com `slots`. O corpo é uma `tuple[int, ...]`, imutável, o que facilita o simulador. A comida é um `frozenset[int]`.
- **Hazards: `dict[int, int]` com a contagem**, e não um conjunto como pedia o pedido original. O motivo é que as regras oficiais aplicam o dano uma vez por entrada repetida, e um conjunto perderia o empilhamento.
- `from_game(state)` faz a única leitura do `GameState`. `hazard_damage(ruleset)` lê `ruleset["settings"]["hazardDamagePerTurn"]` e devolve 0 quando o valor falta ou não é `int` (`bool` também conta como inválido).
- O módulo não importa `models.py`: lê o estado por duck typing. Assim `simulator`, `search` e `occupancy` ficam sem Pydantic na árvore de imports.

Alternativa descartada: migrar as funções atuais para índices. Isso exigiria mexer nos testes delas e não muda o resultado, e o ganho de tempo vem das funções novas.

### 2. `clock.py` e o instante de chegada
- `clock.now()` chama `time.perf_counter()`. Quem usa sempre chama `clock.now()` na hora do uso, como já se faz com `config`, para que os testes possam fazer `monkeypatch.setattr(clock, "now", falso)`.
- `Deadline(start, budget_ms)` expõe `expired()` e `remaining_ms()`.
- `budget_ms(timeout)` devolve `min(config.SEARCH_BUDGET_FRACTION * timeout, config.SEARCH_BUDGET_MAX_MS)`.
- **Instante de chegada:** o middleware que já existe em `main.py` grava `request.state.started_at = clock.now()` no começo de toda requisição. O middleware roda antes de o FastAPI validar o corpo. A rota `/move` passa a receber `request: Request` junto com `state: GameState` e chama `logic.get_move(state, started_at=request.state.started_at)`.
- `get_move(state, started_at=None)` usa `clock.now()` quando o instante não vem, o que cobre os testes do template.

Alternativa descartada: ler o corpo cru e validar dentro da rota. Isso mudaria o caminho do 422 e da telemetria de validação, enquanto o middleware resolve sem mexer nisso.

### 3. `config.SEARCH_BUDGET_MAX_MS` vindo do ambiente
`_positive_int_env(name, default)` lê `os.environ` uma vez, no import, e devolve o padrão quando o valor falta, é vazio, não é inteiro ou não é positivo. Não lança nunca: um erro no import derrubaria a Lambda inteira. A IaC não é alterada. Definir a variável na Lambda é uma ação manual, e um deploy futuro do CDK pode removê-la, como explica `docs/estrategia.md`.

### 4. `occupancy.py`: `free_after` e as três buscas temporais
- `base_free_after(board)` monta uma lista de `w*h` inteiros com as regras da spec. A regra do crescimento soma 1 a todo segmento **menos o último**, em vez de "todas as casas". O pedido original dizia "somar 1 em todas as casas", mas as regras oficiais mostram que a cauda atual sai do lugar mesmo quando a cobra come. A versão adotada é exata e continua conservadora para os outros segmentos.
- Na própria cobra, se a candidata come, `with_growth(free_after, me)` devolve uma cópia ajustada. Isso é raro e copiar 121 inteiros é barato.
- **BFS temporal sem espera.** A BFS anda por níveis, e uma casa só é aceita no nível `d` se `free_after <= d`. Casas recusadas não entram no `visited` e podem ser aceitas num nível posterior, se outra casa da fronteira for vizinha delas. Não há "esperar parado". Isso é conservador num corredor e pode subestimar a área num espaço aberto ao lado de um corpo, caso que a DFS de sobrevivência cobre.
- **Voronoi temporal.** É a mesma estrutura do `voronoi` atual (sementes por nível, `reserved`, `contenders`), com a checagem `free_after[n] <= level + 1`. Devolve as contagens por cobra e um vetor `owner[idx]` (id da dona ou `None`), usado por `food_owned`.
- **A\* temporal.** `g` é o tempo de chegada, e o vizinho só é aceito se `free_after[n] <= g + 1`. Mantém o `best_g` por casa, o que é uma aproximação: um caminho que chegaria mais tarde numa casa, justamente para encontrar a próxima já livre, é descartado. Isso é aceitável para escolher a comida.

Alternativa descartada: busca em estado (casa, tempo). Seria exata, mas multiplica o custo pelo horizonte de tempo.

### 5. `survival.py`: DFS iterativa com corpo exato
- Pilha explícita, sem recursão, para não depender do limite de recursão nem pagar o custo de chamada.
- O próprio corpo fica numa `deque` de índices, com um contador de ocupação por casa, que trata a cauda empilhada. A cada passo:
  - a cauda sai, a não ser que a cobra tenha comido no passo anterior;
  - entrar numa casa da comida faz a cobra crescer e tira aquela comida do caminho;
  - o desfazer restaura tudo isso.
- A vida é simulada como no simulador.
- As adversárias entram pelo `free_after` base, sem o ajuste da própria cobra.
- O prazo é conferido a cada 32 nós (`config.SURVIVAL_DEADLINE_EVERY`), porque ler o relógio em todo nó custaria mais que o próprio nó.
- Devolve `(depth, survives, nodes)`. O número de nós existe para o teste do limite.

### 6. Medições: onde cada campo novo nasce
- `snapshot(state, board=None)` monta o `BoardState` uma vez e calcula o `free_after` base, o território do turno (sementes nas cabeças, todas com distância 0) e a comida alvo. As assinaturas atuais (`snapshot(state)`, `target_food(state, blocked)` e `evaluate_moves(state, candidates, snap)`) continuam funcionando, porque os testes as chamam assim.
- **`target_food`** escolhe a mais próxima pelo A\* temporal entre as comidas da cobra no território do turno; se nenhuma for dela, a mais próxima alcançável. `FoodTarget` ganha `cost`, o custo de vida do caminho, que já inclui o dano de hazard. `starving` passa a comparar a vida com `cost + HEALTH_MARGIN`.
- **Para cada candidata:**
  - a área temporal e a sobrevivência;
  - um Voronoi temporal, que dá `territory_pct`, `rival_territory_pct` (a maior adversária pelo tamanho; no empate, a primeira) e `food_owned`;
  - o A\* temporal até a comida alvo;
  - `hazard`, que é verdadeiro quando a casa é hazard sem comida e o dano é maior que 0.
- **`roomy = area >= length or survives`** é calculado aqui, em `features`, e não em `decision.layer`. Os testes que montam `MoveFeatures` à mão usam `survives=True` por padrão. Se a camada fizesse o OU, toda medição montada com `roomy=False` viraria `roomy`, e `test_decide_ordem_das_camadas` quebraria.
- **`decision.py`:**
  - os cinco campos novos têm valor padrão;
  - `score_terms` ganha `survival` (`W_SURVIVAL * survival_depth / min(ctx.length, SURVIVAL_MAX_DEPTH)`, com divisor de no mínimo 1), `hazard` e `squeeze`;
  - `Decision.ranking` já está ordenado e passa a ser a ordem heurística que a busca usa;
  - continua importando só `config`.

### 7. O filtro de vida e hazard em `get_move`
É um quinto bloco depois do das adversárias. Usa o dano do `BoardState`, ou de `hazard_damage(state.game.ruleset)` caso o filtro rode antes da conversão, e conta as ocorrências da casa em `state.board.hazards`. O comentário cita o link de `standard.go` e a ordem das etapas. As caudas das adversárias continuam bloqueadas no filtro, uma escolha conservadora que já existia: pelas regras, a cauda da rival que não está empilhada sempre sai do lugar, mesmo que ela coma. Essa diferença fica registrada em `docs/estrategia.md`.

### 8. `simulator.py`: `step(board, moves) -> BoardState`
- Cria tuplas novas e não muta o estado recebido.
- Segue as etapas na ordem oficial e elimina em duas fases. Na fase das colisões, monta um `Counter` das casas de corpo (`body[1:]`) das cobras vivas e um mapa cabeça → cobras.
- As cobras eliminadas ficam com `alive=False`, e a busca não gera movimento para elas. Não há geração de comida.
- `safe_moves(board, snake_id)` lista as direções que não são morte certa: dentro do tabuleiro, fora do pescoço e fora das casas que continuam ocupadas depois do turno, qualquer que seja o movimento dos outros. Uma cauda conta como livre só se não estiver empilhada. Sem nenhuma direção, devolve a primeira da ordem canônica.

### 9. `search.py`: max-min simultâneo com alpha-beta
- **Formulação.** Para cada movimento meu (nó MAX), itero as respostas da rival (nó MIN), simulo o turno com os dois movimentos e recorro com `depth - 1`. É o modelo "paranoico" de movimento simultâneo: a rival responde como se conhecesse o meu movimento. Isso é pessimista, e o pessimismo é a postura certa contra a cobra que nos venceu.
- **Poda.** No nó MIN, sai assim que `value <= alpha`. No MAX, quando `value >= beta`.
- **Terminais.** Depois de `step`: as duas mortas valem `DRAW`; só eu morto, `-WIN + ply`; só a rival morta, `WIN - ply`; `ply` é a distância até a raiz.
- **Folha.** Uma avaliação barata com os pesos `EVAL_*` do config:
  - `EVAL_TERRITORY * (meu - dela)`, pelo Voronoi temporal;
  - `EVAL_AREA * minha área temporal`;
  - `EVAL_LENGTH * (meu tamanho - dela)`;
  - `- EVAL_FOOD * distância BFS até a comida mais próxima * (100 - vida) / 100`;
  - `EVAL_HEALTH * vida`;
  - `- EVAL_CENTER * distância de Manhattan até o centro`.

  Os valores iniciais são `EVAL_TERRITORY` 1.0, `EVAL_AREA` 0.5, `EVAL_LENGTH` 10, `EVAL_FOOD` 1.0, `EVAL_HEALTH` 0.1 e `EVAL_CENTER` 0.5. A soma fica limitada a `±(|DRAW| - 1)`, o que garante a spec.
- **Aprofundamento iterativo.** `best_move(board, me, rival, root_order, deadline)` roda as profundidades `1..MAX_SEARCH_DEPTH`.
  - O prazo é conferido em todo nó. Quando passa, a busca lança `_Timeout` e a profundidade em andamento é descartada.
  - Uma profundidade termina com `(melhor_movimento, valor, cortou)`, em que `cortou` diz se alguma folha parou pelo limite de profundidade. Sem nenhum corte, a árvore está resolvida e o aprofundamento para.
  - **Veto, e não substituição.** A busca não escolhe o movimento de maior valor: ela só troca a escolha heurística (`root_order[0]`) quando o valor dela é derrota ou empate (`<= DRAW`) e outro movimento da raiz vale mais. Aí vale o de maior valor. O motivo apareceu na implementação: com os pesos iniciais da folha, o território domina a parcela de comida (no máximo cerca de 0,9 por passo contra 1 por casa). Na profundidade 1 ou 2, que é a esperada na Lambda, uma busca que sempre escolhesse o maior valor trocava a escolha heurística com fome (`left`, rumo à comida da própria cobra) por `right`, rumo à comida da rival, e só voltava atrás quando a morte por fome entrava no horizonte. A heurística já trata fome, armadilhas e caça, e a busca entra para o que ela não vê: derrotas e empates alguns turnos à frente.
  - A cada profundidade, a escolha heurística é buscada primeiro, com janela cheia (`alpha = -inf`), para ter o valor exato. Se ele for maior que `DRAW`, a profundidade termina ali e as outras candidatas da raiz nem são buscadas. Se não, as demais são buscadas com o melhor da profundidade anterior primeiro (quando não for a heurística) e depois `root_order`. Nos níveis internos, a ordem é a canônica.
  - **Empate entre as substitutas.** Com a poda comum, um filho da raiz que empata com o melhor seria cortado, e o empate não ficaria visível. Por isso, cada substituta depois da primeira é buscada com o limite inferior um pouco abaixo do melhor até ali (`alpha = melhor - 1e-9`). Assim, um valor igual ao melhor sai exato. Entre as de valor máximo, vence a primeira em `root_order`. A primeira substituta usa como limite o valor da heurística: só interessa o que for estritamente melhor que ela.
  - `best_move` devolve a resposta da última profundidade completa, já com o veto aplicado, ou `None` se nenhuma terminou.
- **Por que não MCTS ou paranoid com várias cobras:** está fora de escopo, e o duelo é onde o ganho se concentra.

### 10. Integração em `choose_move`
```
choose_move(state, safe_moves, deadline=None):
    deadline = deadline or Deadline(clock.now(), budget_ms(state.game.timeout))
    board = board_state.from_game(state)
    snap = snapshot(state, board); ctx = build_context(state, snap)
    features = evaluate_moves(state, safe_moves, snap, deadline)
    decision = explain(features, ctx)             # escolha heurística pronta
    if config.MAX_SEARCH_DEPTH > 0 and len(safe_moves) > 1 \
       and len(rivais vivas) == 1 and not deadline.expired():
        return search.best_move(board, ..., [r.move for r in decision.ranking], deadline) \
               or decision.move
    return decision.move
```
`get_move` cria o `Deadline` com `started_at` e o passa por palavra-chave. O substituto de `choose_move` em `test_telemetry.py` passa a aceitar `**kwargs`, como a proposta registra.

### 11. Testes: determinismo e fixtures
- **`tests/conftest.py`:**
  - `sem_busca` faz `monkeypatch.setattr(config, "MAX_SEARCH_DEPTH", 0)`;
  - `relogio_parado` fixa `clock.now` em 0.0, então o prazo nunca passa;
  - `relogio_que_estoura_em(n)` é uma fábrica: um relógio que devolve 0.0 nas `n` primeiras leituras e um valor muito grande depois.
- **"No meio da profundidade 3."** O teste roda a busca com um relógio que conta as leituras, primeiro até a profundidade 2 (`C2` leituras) e depois até a 3 (`C3`), e então estoura em `C2 + (C3 - C2) // 2`. O resultado não depende da máquina.
- **Testes antigos de cenário:** usam `sem_busca` (decisão do usuário). Os cenários novos da busca fixam `MAX_SEARCH_DEPTH` e usam `relogio_parado`.
- **Desempenho:** os testes de desempenho usam o relógio real e o melhor de várias medições. No duelo, o limite é o orçamento mais 10 ms.
- **`helpers.make_game`** ganha `hazards=()` e `hazard_damage=None`. Quando o dano vem, ele é escrito em `ruleset.settings`.
- **Poda contra minimax sem poda:** `search` expõe `minimax_value(..., prune=False)` para o teste com tabuleiros pequenos (7x7) e semente fixa.

## Risks / Trade-offs

- **[Risco] Com a CPU de 128 MB, a fase heurística sozinha pode consumir o orçamento com 8 cobras.** Os cerca de 10 ms locais podem virar mais de 100 ms na Lambda.
  → O prazo conta desde a chegada. A DFS para no prazo, e a busca nem começa se ele já passou. A meta local de menos de 10 ms com 8 cobras é um teste. `docs/estrategia.md` explica como calibrar pelo `timed_out_last_turn` e pela duração no `REPORT`. Se ainda faltar tempo, o próximo passo é cortar medições, o que fica para outra mudança.
- **[Risco] Profundidade rasa em Python.** Com 9 pares de movimentos por turno e uma folha que custa um Voronoi, 120 ms na Lambda devem dar profundidade 1 ou 2.
  → A folha é barata, a ordenação ajuda a poda, e a busca para cedo quando a árvore fica resolvida. Os testes de cenário usam profundidade fixa e não dependem da velocidade.
- **[Trade-off] O modelo paranoico é pessimista** e pode recusar jogadas boas cujo risco depende de a rival adivinhar o movimento.
- **[Trade-off] A busca só veta.** Ela não melhora jogadas sem fim de jogo à vista: entre movimentos que não perdem, a heurística decide. É o preço de não confiar na folha antes de calibrá-la.
  → É aceitável contra adversárias fortes. As estratégias mistas ficam fora de escopo.
- **[Risco] Os pesos da folha não estão calibrados** e podem fazer a busca pior que a heurística nos casos sem fim de jogo à vista.
  → A busca só veta a escolha heurística quando ela perde ou empata, então a folha nunca decide entre movimentos que não perdem. Os pesos ficam todos em `config`. O `MAX_SEARCH_DEPTH = 0` desliga a busca com uma mudança de uma linha.
- **[Trade-off] A BFS sem espera e o A\* com `best_g` são aproximações** e podem subestimar a área ou não achar um caminho.
  → `roomy` também aceita `survives`, porque a DFS simula o corpo de verdade.
- **[Risco] Os testes antigos em risco mudarem de resultado** pelas margens de nota.
  → A tarefa 12.3 confere cada um e atualiza a tabela da proposta e os cenários das specs.
- **[Risco] Um deploy do CDK pode apagar uma variável de ambiente definida à mão.**
  → O padrão no código é seguro (120 ms), e o problema fica documentado.

## Migration Plan

1. Implementar na ordem das tarefas, com a suíte verde a cada grupo.
2. Fazer o push em `dev`. O `aws_cd.yml` roda o pytest e faz o deploy.
3. Jogar partidas de duelo e com 8 cobras na Arena e consultar `timed_out_last_turn` com a query de `docs/logs.md`. Se algum turno estourar, reduzir `SEARCH_BUDGET_MAX_MS` (variável de ambiente, à mão, ou o padrão no código) antes de avaliar a estratégia.
4. Para reverter rápido, há dois caminhos: `MAX_SEARCH_DEPTH = 0` em `config.py`, que desliga só a busca, ou `git revert` da mudança.

## Open Questions

- Valores iniciais dos pesos `EVAL_*` e de `W_SQUEEZE`: são calibrados na Arena e não mudam specs nem tarefas.
- A sintaxe do filtro booleano no Logs Insights, que já é uma pendência de `docs/logs.md`, segue em aberto. O guia de calibração aponta para ela.
