Cada grupo deixa a suíte verde e pode ser commitado sozinho. Os testes de `tests/app/test_estrategia.py` entram no grupo em que o comportamento testado passa a ser determinístico. Ao fim de cada grupo, rodar `pytest` e confirmar que os 20 testes do template continuam passando sem alteração.

## 1. Helper de testes

- [x] 1.1 Criar `tests/helpers.py` com `snake(id, body, health=100)`, que monta o dict de uma cobra a partir de uma lista de `(x, y)` (`head = body[0]`, `length = len(body)`)
- [x] 1.2 Em `tests/helpers.py`, criar `make_game(you, others=(), food=(), width=11, height=11, turn=1)`, que monta o JSON do `/move` com `you` em `board.snakes` seguido de `others` e devolve `GameState.model_validate(...)`
- [x] 1.3 Criar `tests/app/test_estrategia.py` (vazio de cenários, com os imports `from src.app...` e `from tests.helpers import ...`) e confirmar que `pytest` coleta sem erro

## 2. Grid e tipo Pos

- [x] 2.1 Criar `src/app/grid.py` com `Pos`, `MOVES` (dict ordenado `up, down, left, right` → delta), `pos(coord)`, `step`, `in_bounds`, `manhattan`, `occupied`, `opponent_cells` e `neighbors`, sem nenhum import absoluto
- [x] 2.2 Confirmar que `grep -rn "from src" src/app` não retorna nada

## 3. Adversárias

- [x] 3.1 Em `get_move`, no lugar do `TODO: Passo 3`, acrescentar o bloco que marca como insegura toda direção cuja casa de destino esteja em `opponent_cells` (import relativo de `.grid`)
- [x] 3.2 Adicionar o teste "desvia de adversária": eu [(5,10),(5,9),(5,8)], outra [(4,10),(3,10),(2,10)] → `right`

## 4. Própria cauda

- [x] 4.1 No bloco 3 do template, acrescentar `my_tail = my_body[-1]` e `if segment == my_tail: continue` no laço dos segmentos
- [x] 4.2 Adicionar o teste "entra na própria cauda": eu [(5,10),(5,9),(4,9),(4,10)], bloqueio [(8,10),(7,10),(6,10)] → `left`
- [x] 4.3 Adicionar o teste "pescoço de cobra de tamanho 2": eu [(5,5),(5,4)] → nunca `down` em 50 execuções

## 5. Cabeça a cabeça

- [x] 5.1 Em `grid.py`, implementar `would_lose_head_to_head(board, you, target)`: `True` se alguma adversária com `length >= you.length` tem a cabeça adjacente a `target`
- [x] 5.2 Em `get_move`, depois do bloco das adversárias, acrescentar o bloco que marca como insegura toda direção cujo destino faça `would_lose_head_to_head` ser `True`
- [x] 5.3 Adicionar os testes "evita cabeça a cabeça com maior" (rival [(3,10),(2,10),(1,10),(0,10)] → `right`) e "evita cabeça a cabeça com igual" (rival [(3,10),(2,10),(1,10)] → `right`), ambos com eu [(5,10),(5,9),(5,8)]
- [x] 5.4 Adicionar o teste "cabeça a cabeça com menor é permitida": eu [(5,10),(5,9),(5,8),(5,7)], menor [(3,10),(2,10),(1,10)] → `would_lose_head_to_head(..., (4,10))` é `False`

## 6. Comida gulosa

- [x] 6.1 Em `grid.py`, implementar `nearest_food(board, origin)` (menor Manhattan, empate fica com a primeira da lista, `None` sem comida)
- [x] 6.2 Em `logic.py`, criar `choose_move(state, safe_moves)` numa versão gulosa: com comida, a direção segura cujo destino fica mais perto da comida mais próxima (empate na ordem de `safe_moves`); sem comida, mantém o `random.choice`
- [x] 6.3 Trocar o sorteio final de `get_move` por `chosen = choose_move(state, safe_moves)`, sem mexer no bloco de emergência
- [x] 6.4 Adicionar o teste "com fome vai para a comida": eu [(5,5),(5,4),(5,3)] com health 50, comida (2,5) → `left`

## 7. Limiar de fome

- [x] 7.1 Acrescentar `HUNGER_THRESHOLD = 80` em `logic.py` e só seguir a comida quando `health < HUNGER_THRESHOLD`; sem fome, devolver provisoriamente a primeira direção de `safe_moves`, o que já é determinístico
- [x] 7.2 Adicionar o teste "sem fome ignora a comida": mesma cobra com health 100, comida (2,5) → `up`

## 8. Flood fill

- [x] 8.1 Criar `src/app/floodfill.py` com `flood_fill(board, start, blocked) -> int` (BFS com `deque` e `set` `visited`, usando `neighbors`; retorna 0 se `start` estiver fora do tabuleiro ou bloqueado)
- [x] 8.2 Em `grid.py`, implementar `threat_zones(board, you)`: vizinhos dentro do tabuleiro das cabeças de adversárias estritamente maiores
- [x] 8.3 Em `logic.py`, criar `obstacles(board, you)` = `occupied(board)` menos a própria cauda
- [x] 8.4 Em `choose_move`, trocar o ramo provisório por: para cada direção de `safe_moves`, `area = flood_fill(board, new_head, (obstacles | threat_zones) - {new_head})`; nota `(area, desempate)` com `desempate = 100 - manhattan(new_head, nearest_food(board, new_head))` se estiver com fome e houver comida, ou 0; escolher com `>` estrito. O ramo com fome que não decidir também cai aqui
- [x] 8.5 Adicionar os testes "flood fill no tabuleiro vazio" (5x5 a partir de (2,2) → 25) e "flood fill com muro" (coluna x=2 bloqueada num 5x5 a partir de (0,0) → 10)
- [x] 8.6 Adicionar o teste "evita o beco": eu [(5,9),(6,9),(7,9),(7,10),(8,10)], outra [(0,5),(0,6),(0,7),(0,8),(0,9),(0,10),(1,10),(2,10),(3,10),(4,10)] → `down`

## 9. A*

- [x] 9.1 Criar `src/app/astar.py` com `a_star(board, start, goal, blocked) -> list[Pos]`: heap de `(f, g, pos)`, `f = g + manhattan`, `best_g` e `came_from` atualizados juntos só quando o novo `g` for estritamente menor, objetivo reconhecido ao sair do heap, retorno `[start, ..., goal]` ou `[]`
- [x] 9.2 Em `choose_move`, trocar o ramo guloso por: com fome e com comida, `path = a_star(board, head, nearest_food(board, head), obstacles)`; se `len(path) >= 2` e a direção de `path[1]` estiver em `safe_moves`, retornar essa direção; senão, seguir para o flood fill
- [x] 9.3 Adicionar o teste "A* contorna obstáculo": 5x5, bloqueado {(1,0),(1,1),(1,2),(1,3)}, de (0,0) até (2,0) → caminho de 11 casas começando em (0,0) e terminando em (2,0)
- [x] 9.4 Adicionar o teste "A* sem caminho": 3x3, bloqueado {(1,0),(1,1),(0,1)}, de (0,0) até (2,2) → `[]`
- [x] 9.5 Confirmar que "com fome vai para a comida" continua passando com o A*

## 10. Guarda da Lambda

- [x] 10.1 Criar `tests/app/test_lambda.py`, que roda `[sys.executable, "-c", "import app.main"]` com `cwd=<repo>/src` via `subprocess` e exige `returncode == 0` (mostrando o `stderr` na falha)
- [x] 10.2 Conferir que o teste falha ao trocar temporariamente um import de `src/app/` por `from src.app...`, e então desfazer a troca

## 11. Verificação final

- [x] 11.1 Rodar `pytest` e confirmar 34 testes passando: 20 do template, 13 de estratégia e 1 da Lambda
- [x] 11.2 Medir com `timeit` (script descartável, fora da suíte) uma jogada num 19x19 com 4 cobras e confirmar média abaixo de 1 ms
- [x] 11.3 Revisar o diff de `src/app/logic.py`: só acréscimos, mais o `continue` da cauda e a linha do `chosen`; `info()` intocado
