## Context

`src/app/logic.py` monta um dict `is_move_safe` em três blocos (pescoço, paredes, próprio corpo), filtra `safe_moves` e sorteia uma direção. Com `safe_moves` vazio, sorteia entre as quatro. Os modelos Pydantic (`Coord`, `Snake`, `Board`) não são hasheáveis, o que impede usar `Coord` em `set` e `dict`.

Restrições que moldam a solução:

- **Imports:** na Lambda a raiz do código é `src/` e o handler é `app.main.handler`. Dentro de `src/app/` todo import é relativo (`from .grid import ...`). Nos testes é o contrário: `from src.app...`.
- **Template intocado:** os 20 testes existentes não podem mudar, e os blocos de `get_move` ficam como estão. O código novo só se acrescenta a eles.
- **Orçamento:** cerca de 500 ms por jogada no jogo, mas a meta é ficar abaixo de 1 ms num 19x19 com 4 cobras.

A motivação está em `proposal.md`, e o comportamento esperado em `specs/estrategia-de-movimento/spec.md` e `specs/empacotamento-lambda/spec.md`.

## Goals / Non-Goals

**Goals:**
- Separar os utilitários de tabuleiro (`grid`), a busca de área (`floodfill`) e a busca de caminho (`astar`) em módulos puros, testáveis sem montar um `GameState`.
- Manter o diff em `get_move` pequeno e legível para quem conhece o template.
- Tornar a escolha determinística para que cada cenário de teste tenha uma única resposta.

**Non-Goals:**
- Busca adversarial (minimax) ou simulação de turnos futuros.
- Tratar a cauda empilhada logo depois de comer, hazards e a estratégia sem nenhuma direção segura (ver proposta).
- Mexer em `models.py`, `main.py`, na IaC ou nos workflows.

## Decisions

### 1. Tuplas `Pos = tuple[int, int]` com conversão centralizada em `pos(coord)`
Toda regra nova trabalha com tuplas, que são hasheáveis e baratas, e `set`s de tuplas viram o formato comum de "casas bloqueadas". A conversão `Coord -> Pos` acontece só em `grid.pos`.
*Alternativa descartada:* tornar `Coord` hasheável (`frozen=True`/`__hash__`). Isso mexe em `models.py`, que o template diz para não editar, e deixa as estruturas internas acopladas ao Pydantic.

### 2. `MOVES` como dict ordenado `{"up": (0,1), "down": (0,-1), "left": (-1,0), "right": (1,0)}`
A ordem de inserção do dict é a ordem canônica, e todos os desempates saem dela: a ordem de `neighbors`, a de `safe_moves` (que já segue `is_move_safe`, na mesma ordem) e a varredura do flood fill com comparação estrita `>`.

### 3. Módulo `grid.py`
Funções puras, sem estado:
- `pos`, `step(p, direction)`, `in_bounds(board, p)`, `manhattan(a, b)`.
- `occupied(board) -> set[Pos]`: todas as casas de todas as cobras.
- `opponent_cells(board, you) -> set[Pos]`: casas das adversárias, identificadas por `id != you.id`, com a cauda incluída.
- `neighbors(board, p, blocked) -> list[Pos]`: vizinhos dentro do tabuleiro e fora de `blocked`, na ordem de `MOVES`.
- `would_lose_head_to_head(board, you, target) -> bool`: `True` se alguma adversária com `length >= you.length` tem a cabeça a distância de Manhattan 1 de `target`.
- `threat_zones(board, you) -> set[Pos]`: vizinhos, dentro do tabuleiro, das cabeças das adversárias com `length > you.length`.
- `nearest_food(board, origin) -> Pos | None`: comida de menor Manhattan; com `min()` sobre a lista, o empate fica com a primeira.

Note a assimetria de propósito: o filtro de cabeça a cabeça usa `>=` (empate mata as duas cobras), enquanto `threat_zones` no flood fill usa `>` estrito. Com `>=` no flood fill a cobra superestimaria a ameaça de rivais iguais, que já foram barradas no primeiro passo.

### 4. Regras de filtro dentro de `get_move`, como blocos novos depois do bloco 3
- **Cauda (alteração no bloco 3):** `my_tail = my_body[-1]` e `if segment == my_tail: continue`. A comparação entre `Coord` funciona por igualdade de campos no Pydantic v2. O bloco do pescoço vem antes e continua barrando a meia-volta numa cobra de tamanho 2, em que pescoço e cauda são a mesma casa.
- **Adversárias:** para cada direção ainda segura, `step(head, d) in opponent_cells(...)` marca `False`.
- **Cabeça a cabeça:** para cada direção ainda segura, `would_lose_head_to_head(board, you, step(head, d))` marca `False`.

Os blocos novos entram no lugar do `TODO: Passo 3`, antes da montagem de `safe_moves`. O bloco de emergência fica intocado.

### 5. `choose_move(state, safe_moves) -> str` em `logic.py`
1. `HUNGER_THRESHOLD = 80`; `hungry = you.health < HUNGER_THRESHOLD`.
2. `obstacles = occupied(board) - {pos(my_tail)}`. A cabeça atual fica em `obstacles`, o que não atrapalha: o A* só filtra vizinhos, nunca o `start`.
3. **Comida:** se `hungry` e houver comida, `path = a_star(board, head, nearest_food(board, head), obstacles)`. Se `len(path) >= 2` e a direção de `head -> path[1]` estiver em `safe_moves`, retorna essa direção. A direção sai da comparação de `step(head, d) == path[1]` para cada `d` de `MOVES`.
4. **Espaço:** `blocked = obstacles | threat_zones(board, you)`. Para cada `d` em `safe_moves`, `new_head = step(head, d)` e `area = flood_fill(board, new_head, blocked - {new_head})`. Remover `new_head` do conjunto é essencial: uma direção segura pode cair numa casa de `threat_zones` (rival estritamente maior a duas casas), e sem a remoção a área seria 0 mesmo havendo espaço. Esse era o bug da versão em Java.
5. Nota `(area, desempate)`, com `desempate = 100 - manhattan(new_head, nearest_food(board, new_head))` se `hungry` e houver comida, e 0 caso contrário. Mantém a melhor nota com `>` estrito; a primeira direção fica com o empate total.

`get_move` troca só `chosen = random.choice(safe_moves)` por `chosen = choose_move(state, safe_moves)`. O `import random` continua em uso pelo fallback.

*Alternativa descartada:* uma pontuação única somando área e comida. Pesos arbitrários tornam os cenários menos previsíveis; a tupla deixa a prioridade explícita (área primeiro).

### 6. `flood_fill(board, start, blocked) -> int`
BFS com `collections.deque` e um `set` `visited`, expandindo com `neighbors`. Retorna 0 se `start` estiver fora do tabuleiro ou em `blocked`. O custo é O(W·H) por chamada; num 19x19 são 361 casas.

### 7. `a_star(board, start, goal, blocked) -> list[Pos]`
`heapq` com tuplas `(f, g, pos)`, `f = g + manhattan(pos, goal)`. `best_g` e `came_from` são atualizados juntos, e só quando o novo `g` for estritamente menor, o que evita caminhos de reconstrução inconsistentes. O objetivo conta como alcançado quando sai do heap, não quando entra, e isso garante o caminho ótimo com heurística consistente. Entradas obsoletas do heap são ignoradas comparando `g` com `best_g[pos]`. Retorna `[start, ..., goal]` ou `[]`. O `start` não é testado contra `blocked`, e o `goal` também não, já que comida nunca está sob um corpo no modo standard.
*Alternativa descartada:* BFS simples até a comida, que daria o mesmo caminho em grade uniforme. O A* foi mantido por fidelidade à estratégia de referência, e ele explora menos casas quando a comida está perto.

### 8. Testes
- `tests/helpers.py` monta o JSON do `/move` e passa por `GameState.model_validate`, o mesmo caminho da produção, em vez de instanciar modelos à mão. `make_game` coloca `you` como primeira cobra de `board.snakes`, seguida de `others`.
- `tests/app/test_estrategia.py` importa de `src.app.*` e usa apenas cenários com resposta única, então não precisa de laços de repetição, exceto o caso do pescoço (50 execuções).
- `tests/app/test_lambda.py` roda `[sys.executable, "-c", "import app.main"]` com `cwd=<repo>/src` via `subprocess` e exige `returncode == 0`. O `sys.executable` garante o mesmo interpretador e o mesmo ambiente do pytest.

## Risks / Trade-offs

- [A meta de 1 ms em Python puro: até 3 flood fills de 361 casas mais um A* podem chegar perto do limite] → as estruturas são `set`/`deque` de tuplas, sem objetos Pydantic no laço quente, e `occupied`/`threat_zones` são calculados uma vez por jogada. Uma task mede com `timeit` num 19x19 com 4 cobras. Mesmo estourando 1 ms, a margem até os 500 ms é grande.
- [Cauda empilhada depois de comer: a cauda é liberada mas não sai do lugar] → limitação aceita (fora de escopo). O risco é baixo, porque a cauda só fica empilhada no turno seguinte a comer.
- [O A* ignora `threat_zones`, então o caminho pode passar perto de uma rival maior] → só o primeiro passo é validado contra `safe_moves`, que já exclui cabeça a cabeça com maior ou igual. Os passos seguintes são reavaliados no próximo turno.
- [Liberar a cauda no filtro e em `obstacles` muda o comportamento de testes do template?] → conferido: nos testes existentes, nenhuma casa que hoje bloqueia uma direção esperada é a cauda. `test_evita_proprio_corpo_quando_tem_opcao` bloqueia com (5,5), e a cauda é (4,3). Nos testes "sem safe moves" a resposta só precisa ser uma das quatro.
- [Determinismo pode tornar a cobra previsível para adversárias] → aceito; previsibilidade facilita testar e depurar, e a estratégia de referência também é determinística.

## Migration Plan

Sem migração de dados. O deploy é o fluxo normal: push em `dev` → `pytest` (agora com 34 testes, incluindo a guarda da Lambda) → `cdk deploy`. Rollback: reverter o commit em `dev`; o CD republica a versão anterior.
