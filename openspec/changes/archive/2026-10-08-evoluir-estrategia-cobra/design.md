## Context

Hoje `get_move` (`src/app/logic.py`) tem cinco blocos de filtro: pescoço, paredes, próprio corpo com a cauda livre, adversárias e cabeça a cabeça. Depois deles chama `choose_move`, que segue o A* até a comida quando `health < 80` e, nos outros casos, maximiza o flood fill. Os utilitários estão em `grid.py`, `floodfill.py` e `astar.py`, todos com tuplas `Pos` e imports relativos. A motivação está em `proposal.md` (Why), e o comportamento esperado está nas três specs desta mudança.

Restrições que moldam a solução:
- **Imports:** dentro de `src/app/` todo import é relativo. `test_lambda.py` importa `app.main` com `src/` como raiz.
- **Template:** os 20 testes do template não mudam, e o fallback aleatório sem candidatas continua igual.
- **Contrato do Jev:** a decisão não pode depender de `models.py`. Hoje `grid.py` importa `models`, então qualquer coisa que a decisão importe de `grid` puxaria `models` junto.
- **Tempo:** menos de 50 ms por jogada num 19x19 com 4 cobras de tamanho 15. Um protótipo descartável desta mesma estratégia, em Python puro e sem otimização, levou cerca de 8 ms nesse cenário (melhor de 20 medições).

## Goals / Non-Goals

**Goals:**
- Deixar a fronteira características → decisão explícita e estável, com tipos que não dependem do payload, para o Jev entrar no lugar de `decide` sem mexer no resto.
- Calcular uma única vez, por jogada, tudo o que não depende da direção: obstáculos, `threat_zones`, comida alvo e presa.
- Manter `get_move` reconhecível para quem conhece o template.

**Non-Goals:**
- Simulação de vários turnos e busca adversarial.
- Otimizações além do necessário para os 50 ms, como cache de flood fill por componente e mapas de distância reaproveitados entre direções. Elas ficam registradas como saída se o teste de desempenho apertar.
- Mudar `models.py`, `main.py`, a IaC ou os workflows.

## Decisions

### 1. Módulos e direção das dependências

```
config.py      ← só constantes, sem imports do app
decision.py    ← importa só config (MoveFeatures, DecisionContext, decide)
grid.py        ← models (ganha tail_moves e obstacles)
voronoi.py     ← grid
features.py    ← grid, floodfill, astar, voronoi, config, decision (tipos), models
logic.py       ← features, decision, grid, models
```

`MoveFeatures` e `DecisionContext` ficam em `decision.py`, e não em `features.py`. O contrato pertence a quem consome os dados, e assim `decision.py` não importa nada que puxe `models`.
*Alternativa descartada:* definir os tipos em `features.py`. A decisão teria que importar `features`, que importa `models`, e o critério de aceite seria quebrado de forma transitiva.

A ordem canônica entra em `decision.py` como `MOVE_ORDER = ("up", "down", "left", "right")`, porque importar `grid.MOVES` puxaria `models`. Um teste garante `tuple(MOVES) == MOVE_ORDER`.

### 2. `config.py`
São constantes de módulo em maiúsculas, com um comentário por grupo: `HEALTH_MARGIN = 15`, `NO_PATH_HEALTH = 50`, `LENGTH_LEAD = 2`, `START_LENGTH = 3`, `FEED_INTERVAL = 8` e os pesos `W_TERRITORY = 1.0`, `W_FOOD = 40`, `W_TRAP = 60`, `W_KILL = 50`, `W_HUNT = 10`, `W_DANGER = 25`, `W_CENTER = 1`.

Os módulos consumidores importam o módulo (`from . import config`) e leem `config.W_TRAP` na hora do uso, sem copiar o valor com `from .config import W_TRAP`. Assim um teste pode usar `monkeypatch.setattr(config, "W_TRAP", 0)` (cenário "Peso alterado muda a escolha").

### 3. Cauda empilhada: `grid.tail_moves(snake)` e `grid.obstacles(board)`
- `tail_moves(snake) = len(body) > 1 and body[-1] != body[-2]`. Numa cobra de tamanho 1 a cauda é a cabeça e continua sendo obstáculo, o que é conservador e só aparece em testes.
- `obstacles(board)` reúne as casas de todos os corpos, menos as caudas com `tail_moves`. Ela substitui `logic.obstacles(board, you)`, que só liberava a própria cauda.
- No bloco 3 do template, o `continue` da cauda passa a valer só se `tail_moves(state.you)`.
- `opponent_cells` (bloco 4) não muda: a cauda das rivais continua ocupada no filtro de candidatas, porque elas podem comer neste turno.

### 4. Cabeça a cabeça: de filtro a marcação
O bloco 5 sai de `get_move`. `would_lose_head_to_head` continua em `grid.py`, e o teste dele não muda. Ela passa a calcular `MoveFeatures.risky` em `features.py`. As candidatas são o `safe_moves` que sobra dos blocos 1 a 4.

### 5. Voronoi: BFS por níveis com conjunto de concorrentes
`voronoi(board, seeds, blocked) -> dict[str, int]`, com `seeds: dict[str, tuple[Pos, int]]`. O tamanho de cada cobra vem de `board.snakes`, procurado pelo id.
- As sementes são agrupadas por distância inicial. A BFS anda nível a nível, e as sementes de um nível entram nele **forçadas**: a casa de origem fica com a própria cobra, mesmo que esteja em `blocked` ou que outra cobra chegue no mesmo nível.
- Cada casa guarda o conjunto de cobras que a alcançam na menor distância. Uma casa do nível L+1 recebe a união dos conjuntos dos vizinhos do nível L que chegam até ela. O dono é a única cobra estritamente maior do conjunto. Se não houver uma única maior, a casa é disputada e se expande com o conjunto inteiro.
- O resultado tem todas as chaves de `seeds`, inclusive as que ficaram com 0 casas.

Isso equivale a calcular a distância de cada cobra de forma independente e comparar, que é a definição da spec. Também acerta os quatro cenários de território, conferidos no protótipo.
*Alternativa descartada:* propagar só o dono da casa. É mais barato, mas a cobra que perde um empate deixa de alcançar as casas de trás, e o resultado passa a depender da forma do tabuleiro de um jeito difícil de especificar.
*Alternativa adiada:* calcular uma vez por turno o mapa de distância de cada rival, que não depende da minha direção, e por direção só a minha BFS. Fica como otimização se o tempo apertar.

### 6. `features.py`: leitura do turno uma vez, medições por direção
- `snapshot(state) -> TurnSnapshot` (dataclass interna) calcula uma vez por jogada:
  - `obstacles`, `threat_zones` e `blocked = obstacles | threat_zones`;
  - as rivais;
  - as casas livres (`W*H - len(obstacles)`) e o centro (`(W // 2, H // 2)`);
  - a presa;
  - a comida alvo: `(pos, dist, path)` ou `None`.
- `target_food(state, blocked)` roda um A* da cabeça até cada comida, usando `dist = len(path) - 1`. Ela guarda a melhor entre as "minhas" e a melhor entre todas, com comparação estrita `<`, de modo que o empate fica com a primeira da lista. Ela é exposta para o teste da comida contestada.
- `build_context(state, snap=None) -> DecisionContext(health, length, turn, hungry)`. As três condições de fome seguem a spec, e cada uma vira uma função pequena e testável.
- `evaluate_moves(state, candidates, snap=None) -> list[MoveFeatures]`. Para cada candidata, com `n = step(head, d)`:
  - `risky`: `would_lose_head_to_head(board, you, n)`;
  - `area`: `flood_fill(board, n, blocked - {n})`, e `roomy = area >= you.length`;
  - `territory_pct`: `voronoi(board, {you.id: (n, 1), rival.id: (cabeça, 0)...}, obstacles)`, dividido pelas casas livres e multiplicado por 100;
  - `food_step`: `path[1] == n`;
  - `food_dist`: `a_star(board, n, alvo, blocked - {n})`, com `None` se não houver caminho;
  - `trapped_rivals`: com `sim = obstacles | {n}`, para cada rival é o máximo de `flood_fill(board, v, sim)` sobre os vizinhos `v` dentro do tabuleiro da cabeça dela (`neighbors(board, cabeça, set())`), comparado com `rival.length`;
  - `kill_chance`, `hunt_step`, `danger` e `center_dist`, por Manhattan, como na spec.

O parâmetro opcional `snap` existe para que `choose_move` calcule a leitura do turno uma vez e a passe para as duas funções. Chamadas sem ele, que é o caso dos testes, calculam por conta própria, e as assinaturas pedidas continuam valendo.
*Alternativa descartada:* uma função única que devolve `(features, context)`. Ela acoplaria o contexto às medições, e o Jev talvez precise de um sem o outro.

`trapped_rivals` não diferencia rivais que já estavam encurraladas antes do meu passo. Elas somam o mesmo bônus em todas as direções, o que não muda a escolha dentro da camada, e a informação continua disponível para o Jev.

### 7. `decision.py`
- `@dataclass(frozen=True) MoveFeatures`, com os 12 campos da spec. `trapped_rivals` é uma `tuple[str, ...]`, para manter o objeto imutável e hasheável.
- `@dataclass(frozen=True) DecisionContext(health, length, turn, hungry)`.
- `layer(f) -> int`: 0 a 3, na ordem da spec.
- `score(f, ctx) -> float`: a fórmula da spec, com pesos de `config`.
- `decide(features, ctx)` lança `ValueError` se a lista estiver vazia. Caso contrário, devolve o `move` do `min` pela chave `(layer(f), -score(f, ctx), MOVE_ORDER.index(f.move))`.

A chave em tupla torna explícitas as três regras (camada, nota, ordem canônica), sem depender da ordem da lista recebida.
*Alternativa descartada:* somar uma penalidade grande por camada à nota. Ela funciona até um peso futuro passar do valor escolhido, e a spec exige que nenhuma nota de uma camada posterior vença uma anterior.

### 8. `get_move` e `choose_move`
- Os blocos 1 a 4 ficam como estão, com a única mudança no `continue` da cauda. O bloco 5 sai, e o bloco de emergência fica intocado.
- `choose_move` fica assim: `snap = snapshot(state)`, `ctx = build_context(state, snap)`, `feats = evaluate_moves(state, safe_moves, snap)`, `return decide(feats, ctx)`. Um `logger.debug` registra o contexto e as medições.
- `HUNGER_THRESHOLD` e o antigo `obstacles` de `logic.py` saem. `random` continua importado por causa do fallback.

### 9. Testes
- `tests/app/test_estrategia_v2.py` importa de `src.app.*` e de `tests.helpers`.
- Todo cenário de `get_move` tem resposta única, conferida no protótipo, e leva um desenho ASCII do tabuleiro em comentário. Os cenários de "Encurrala" e "Ataca" incluem uma comida que puxa para outra direção, para que o bônus testado seja o que decide. Sem ele, a resposta muda.
- Os testes de `decide` montam `MoveFeatures` com um helper `feat(move, **campos)`, cujos valores padrão são neutros (`risky=False`, `roomy=True` e zeros).
- O isolamento da decisão é testado com `subprocess`, no mesmo molde do `test_lambda.py`: `import app.decision, sys; assert "app.models" not in sys.modules`, com `cwd=src`. Esse teste pega também imports transitivos.
- O desempenho é testado num 19x19 com 4 cobras de tamanho 15, em colunas em zigue-zague nas posições x = 1, 6, 11 e 16, com 5 comidas e turno 60. O teste mede o **melhor de 10** `time.perf_counter()` da jogada completa (`get_move`) e exige menos de 50 ms. Usar o melhor de várias medições, e não a média, reduz a flutuação no CI.

## Risks / Trade-offs

- [A disputa de tamanho deixa a cobra com fome quase o tempo todo no começo da partida (3 < 3 + 2 com rivais de tamanho 3), o que desliga a penalidade de centro e a caça] → é o comportamento pedido para resolver a cobra pequena. Os pesos e o `LENGTH_LEAD` ficam em `config.py` para calibrar na Arena.
- [Comida numa casa vizinha à cabeça de rival estritamente maior fica inalcançável, porque o A* bloqueia `threat_zones`] → é aceito: essa comida é perigosa. Se todas estiverem assim, vale a regra de sobrevivência sem caminho (vida < 50).
- [`kill_chance` supõe que a rival menor pode ir para a casa, não que vai] → é só um peso, sem garantia, e não sobrepõe as camadas de segurança.
- [Medir tempo no CI é instável] → o limite é de 50 ms contra cerca de 8 ms medidos no protótipo, e o teste usa o melhor de 10 execuções.
- [Notas em ponto flutuante: um empate pode deixar de ser empate por arredondamento] → as notas da mesma jogada saem das mesmas operações. Nos testes de `decide`, os valores são escolhidos para que o empate seja exato.
- [A cobra passa a aceitar cabeça a cabeça com rival igual ou maior quando a alternativa é um beco] → é a troca pedida (camada 2 antes da 3). O cenário "Beco versus cabeça a cabeça" documenta a escolha.

## Migration Plan

Não há migração de dados nem mudança de API. O deploy segue o fluxo atual: push em `dev`, `pytest` no CD e `cdk deploy`. Rollback é `git revert` do merge, seguido de um novo push em `dev`.
