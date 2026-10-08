Cada grupo deixa a suíte verde e pode ser commitado sozinho. Ao fim de cada grupo, rodar `.venv/bin/pytest` e confirmar que os 20 testes do template e o `test_lambda.py` passam sem alteração.

Até o grupo 8, `choose_move` continua com a lógica antiga e as medições novas são testadas diretamente. A troca para a decisão nova acontece só no grupo 8.

Os testes novos vão em `tests/app/test_estrategia_v2.py`, importando de `src.app.*` e de `tests.helpers`. Todo cenário de `get_move` precisa de resposta única e de um desenho ASCII do tabuleiro em comentário.

## 1. Constantes de ajuste

- [x] 1.1 Criar `src/app/config.py`, sem imports do app, com `HEALTH_MARGIN = 15`, `NO_PATH_HEALTH = 50`, `LENGTH_LEAD = 2`, `START_LENGTH = 3`, `FEED_INTERVAL = 8`, `W_TERRITORY = 1.0`, `W_FOOD = 40`, `W_TRAP = 60`, `W_KILL = 50`, `W_HUNT = 10`, `W_DANGER = 25` e `W_CENTER = 1`, com um comentário em português por grupo
- [x] 1.2 Criar `tests/app/test_estrategia_v2.py` com os imports e um teste que confere os valores iniciais de `config`

## 2. Cauda empilhada

- [x] 2.1 Em `grid.py`, criar `tail_moves(snake)` (`len(body) > 1 and body[-1] != body[-2]`) e `obstacles(board)`, que reúne todos os corpos menos as caudas com `tail_moves`
- [x] 2.2 No bloco 3 de `get_move`, só pular a própria cauda se `tail_moves(state.you)`. O bloco 4 (`opponent_cells`) não muda
- [x] 2.3 Trocar `logic.obstacles(board, you)` por `grid.obstacles(board)` em `choose_move` e remover a função antiga
- [x] 2.4 Revisar `test_evita_o_beco` em `tests/app/test_estrategia.py`: a rival ganha `(4,10)` repetido no fim (acabou de comer), e o comentário passa a explicar que o bolsão de `up` só existe porque a cauda da rival não sai do lugar. A resposta continua `down`
- [x] 2.5 Testes: "Cauda empilhada depois de comer" (corpo [(5,10),(5,9),(4,9),(4,10),(4,10)] → `right`), "Cauda que sai do lugar" (corpo [(5,10),(5,9),(4,9),(4,10)] → `left` como candidata), "Cauda de rival que sai do lugar" e "Cauda de rival empilhada" (`obstacles`)

## 3. Território (Voronoi)

- [x] 3.1 Criar `src/app/voronoi.py` com `voronoi(board, seeds, blocked) -> dict[str, int]`: BFS por níveis, sementes agrupadas por distância inicial e forçadas no próprio nível, conjunto de concorrentes por casa, dono = única estritamente maior, casa disputada se expandindo com o conjunto inteiro, e todas as chaves de `seeds` no resultado (design, decisão 5)
- [x] 3.2 Testes de território no 5x5: "Tamanhos iguais dividem o tabuleiro" (10/10, com `blocked={(0,2),(4,2)}`), "Rival maior leva o empate" (10/15), "Semente com distância inicial 1" (10/15) e "Três cobras de mesmo tamanho" (7/7/4)
- [x] 3.3 Confirmar que `grep -rn "from src" src/app` não retorna nada

## 4. Tipos da decisão e medições básicas

- [x] 4.1 Criar `src/app/decision.py`, importando só `config`, com `MOVE_ORDER`, `@dataclass(frozen=True) MoveFeatures` (os 12 campos, `trapped_rivals: tuple[str, ...]`) e `@dataclass(frozen=True) DecisionContext(health, length, turn, hungry)`. Ainda sem `decide`
- [x] 4.2 Criar `src/app/features.py` com o `TurnSnapshot` interno, `snapshot(state)` (obstáculos, `threat_zones`, `blocked`, rivais, casas livres, centro) e `evaluate_moves(state, candidates, snap=None)` preenchendo `move`, `risky`, `area`, `roomy`, `territory_pct`, `danger` e `center_dist`. Por enquanto `food_step=False`, `food_dist=None`, `trapped_rivals=()`, `kill_chance=False` e `hunt_step=False`
- [x] 4.3 Testes: "Ordem preservada", "Casa alcançável por rival igual" (`risky`), "Bolsão menor que a cobra" (`area` 2 e `roomy`), "Rival igual a duas casas" (`danger`), "Centro do 11x11" e `tuple(grid.MOVES) == decision.MOVE_ORDER`

## 5. Política de fome e comida alvo

- [x] 5.1 Em `features.py`, criar `target_food(state, blocked)`, que devolve `(pos, dist, path)` ou `None`: A* da cabeça até cada comida com `blocked = obstacles | threat_zones`, a comida "minha" quando `dist < manhattan(cabeça_rival, comida)` para toda rival de tamanho maior ou igual, e comparação estrita (o empate fica com a primeira da lista)
- [x] 5.2 Guardar a comida alvo no `snapshot` e preencher `food_step` (`path[1] == nova_cabeça`) e `food_dist` (A* da nova cabeça com `blocked - {nova_cabeça}`, `len(path) - 1` ou `None`)
- [x] 5.3 Criar `build_context(state, snap=None) -> DecisionContext`, com uma função por condição de fome (sobrevivência, disputa de tamanho, taxa de crescimento), lendo as constantes de `config` na hora do uso
- [x] 5.4 Testes: "Fome por taxa de crescimento", "Sem fome", "Fome por sobrevivência sendo a maior cobra" (vida 19), "Limite da sobrevivência" (vida 20), "Fome por disputa de tamanho" (só `hungry` por enquanto), "Comida contestada" (`target_food` devolve (1,5) e `left` tem `food_step`), "Primeiro passo até a comida" e "Sem comida"

## 6. Rivais encurraladas

- [x] 6.1 Em `evaluate_moves`, preencher `trapped_rivals`: com `sim = obstacles | {nova_cabeça}`, cada rival em que o máximo de `flood_fill(board, v, sim)` sobre os vizinhos `v` da cabeça dela é menor que `rival.length`, na ordem do tabuleiro
- [x] 6.2 Teste "O passo fecha a única saída": `up` tem `("menor",)`, e `down` e `right` têm `()`

## 7. Chance de matar e caça

- [x] 7.1 No `snapshot`, escolher a presa: a rival estritamente menor com a cabeça mais perto da minha por Manhattan, com empate para a primeira do tabuleiro
- [x] 7.2 Em `evaluate_moves`, preencher `kill_chance` (Manhattan 1 da cabeça de uma rival estritamente menor) e `hunt_step` (a distância até a presa diminui)
- [x] 7.3 Testes: "Casa que a rival menor pode ocupar" e "Rival maior não é presa"

## 8. Camadas, pontuação e troca da decisão

- [x] 8.1 Em `decision.py`, implementar `layer(f)`, `score(f, ctx)` (pesos lidos de `config` na hora do uso) e `decide(features, ctx)`: `ValueError` se a lista estiver vazia e `min` pela chave `(layer, -score, MOVE_ORDER.index(move))`
- [x] 8.2 Testes isolados de `decide`, com um helper `feat(move, **campos)` de valores neutros: "Não arriscada com espaço vence tudo", "Ordem das camadas", cada cenário de peso de "Pontuação dentro da camada", "Empate com lista fora de ordem" e "Lista vazia"
- [x] 8.3 Teste de isolamento: `subprocess` com `cwd=src` rodando `import app.decision, sys; assert "app.models" not in sys.modules`
- [x] 8.4 Trocar o corpo de `choose_move` por `snapshot` → `build_context` → `evaluate_moves` → `decide`, com um `logger.debug` do contexto e das medições. Remover o bloco 5 (cabeça a cabeça) de `get_move` e a constante `HUNGER_THRESHOLD`, sem mexer no bloco de emergência
- [x] 8.5 Revisar `test_com_fome_vai_para_a_comida`: a vida passa de 50 para 10, com um comentário dizendo que a fome agora vem da regra de sobrevivência (10 < 3 + 15). Confirmar que `test_sem_fome_ignora_a_comida` continua `up` sem alteração
- [x] 8.6 Testes de `get_move` com ASCII: "Beco versus cabeça a cabeça" (`up`), "Não morde a isca" (`left`), "Encurrala a rival menor" (`up`), "Ataca a rival menor" (`right`), "Fome por disputa de tamanho" (`left`), "Comida contestada" (`left`). "Rival maior" e "Rival de mesmo tamanho" já são cobertos por `test_evita_cabeca_a_cabeca_com_maior` e `test_evita_cabeca_a_cabeca_com_igual`, e a marcação de `left` como arriscada é coberta no 4.3
- [x] 8.7 Teste "Peso alterado muda a escolha": com `monkeypatch.setattr(config, "W_TRAP", 0)`, o cenário "Encurrala a rival menor" passa a responder `right`
- [x] 8.8 Rodar a suíte inteira e conferir que os outros 10 testes de `test_estrategia.py` passam sem alteração

## 9. Desempenho e fechamento

- [x] 9.1 Teste de desempenho: 19x19 com 4 cobras de tamanho 15 em colunas em zigue-zague (x = 1, 6, 11, 16), 5 comidas e turno 60. O melhor de 10 medições de `get_move` com `time.perf_counter()` fica abaixo de 50 ms
- [x] 9.2 Teste de determinismo: o mesmo estado do 9.1 enviado 20 vezes devolve sempre a mesma resposta
- [x] 9.3 (Não foi preciso: o melhor tempo medido foi de cerca de 8 ms.) Se o 9.1 falhar, aplicar as otimizações adiadas do design (mapas de distância das rivais por turno, cache de flood fill por componente em `trapped_rivals`) antes de mexer no limite
- [x] 9.4 Atualizar a seção Architecture do `CLAUDE.md`: as três etapas, os módulos novos, `config.py` e a regra de que `decision.py` não importa `models`
- [x] 9.5 Rodar `.venv/bin/pytest` da raiz e confirmar tudo verde: template, `test_lambda.py`, `test_estrategia.py` e `test_estrategia_v2.py`
