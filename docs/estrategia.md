# Estratégia da cobra

Como a cobra escolhe cada jogada, o que ela mede, onde estão os pesos e quais aproximações ela faz. Os valores citados aqui são os iniciais de `src/app/config.py`, e é lá que eles mudam.

## Fluxo de uma jogada

```
/move chega ─► middleware marca o instante (clock.now)
             ─► validação do payload (Pydantic)
             ─► logic.get_move
                  1. filtro: candidatas que não são morte certa
                  2. heurística: medições (features) ─► decisão (decision.explain)
                  3. busca no duelo, só se sobrou prazo (search.best_move)
             ─► resposta
```

1. **Filtro** (`logic.get_move`). Tira as direções que matam com certeza: o pescoço, as paredes, o próprio corpo (a cauda conta como livre se não estiver empilhada), o corpo das adversárias (a cauda delas inclusive, veja "Diferenças em relação às regras") e as casas em que a vida chegaria a 0. Sem nenhuma candidata, a cobra sorteia uma das quatro direções. É a única aleatoriedade.
2. **Heurística**. `features.evaluate_moves` mede cada candidata, e `decision.explain` escolhe a partir dessas medições e do contexto (vida, tamanho, turno e fome). A escolha heurística fica pronta antes de qualquer busca.
3. **Busca no duelo** (`search.best_move`). Roda só quando há exatamente uma adversária viva, mais de uma candidata, `MAX_SEARCH_DEPTH > 0` e o prazo ainda não passou. Ela só **veta** a escolha heurística: troca-a apenas quando ela perde ou empata dentro do horizonte da busca e outro movimento vale mais, e só com o resultado de uma profundidade que terminou dentro do prazo.

### Prazo

- O prazo começa quando o `/move` chega, no middleware de `src/app/main.py`, antes da validação do payload. A validação e a conversão do estado também gastam tempo.
- O orçamento é `min(SEARCH_BUDGET_FRACTION × game.timeout, SEARCH_BUDGET_MAX_MS)`, que com os padrões (0,4 e 120 ms) e o timeout de 500 ms dá 120 ms.
- Toda leitura de tempo passa por `clock.now()` (`time.perf_counter`), que os testes trocam por um relógio falso.
- A DFS de sobrevivência confere o prazo a cada `SURVIVAL_DEADLINE_EVERY` (32) nós e, quando ele passa, devolve a profundidade alcançada. A busca confere o prazo em todo nó e descarta a profundidade em andamento.

## Representação do tabuleiro

`board_state.from_game` lê o `GameState` uma única vez por jogada e monta um `BoardState`:
- cada casa (x, y) vira o índice `y × largura + x`;
- os vizinhos de cada índice ficam numa tabela calculada uma vez por tamanho de tabuleiro;
- os corpos são tuplas de índices (cabeça primeiro, repetições mantidas);
- os hazards guardam quantas vezes cada casa aparece na lista, porque o dano é aplicado uma vez por ocorrência;
- o dano de hazard vem de `game.ruleset.settings.hazardDamagePerTurn`, com 0 quando falta ou é inválido.

A ocupação temporal, a sobrevivência, o simulador e a busca trabalham só sobre o `BoardState`, sem objetos Pydantic. Esses módulos não importam `models.py`.

## Ocupação temporal

`free_after[casa]` diz em quantos movimentos a casa fica livre. Num corpo de n segmentos, o segmento i (0 é a cabeça) libera a casa depois de n − i movimentos. Numa cauda empilhada vale o maior valor. As buscas só alcançam uma casa no tempo t se `free_after <= t`. Assim um corpo que vai sair do caminho a tempo não é tratado como parede.

O crescimento é estimado assim:
- uma adversária com a cabeça vizinha a uma comida pode comer no próximo turno, então todos os segmentos dela, menos o último, somam 1;
- a própria cobra só cresce na medição da candidata cuja nova cabeça tem comida.

## Medições por candidata (`MoveFeatures`)

| Medição | Como é calculada |
|---|---|
| `risky` | uma rival de tamanho maior ou igual alcança a mesma casa no próximo turno |
| `area` | BFS temporal a partir da nova cabeça no tempo 1; as casas vizinhas às cabeças de rivais estritamente maiores ficam bloqueadas de vez (menos a própria nova cabeça) |
| `survival_depth`, `survives` | DFS que simula o próprio corpo de verdade, a comida comida no caminho, a vida e os hazards. A profundidade alvo é `min(tamanho, SURVIVAL_MAX_DEPTH)` (12), com no máximo `SURVIVAL_MAX_NODES` (400) nós por candidata |
| `roomy` | `area >= tamanho` **ou** `survives` |
| `territory_pct` | Voronoi temporal (minha semente: a nova cabeça, com distância 1; as rivais: a cabeça atual, com distância 0), em percentual das casas livres |
| `rival_territory_pct` | o mesmo, para a maior rival (no empate, a primeira do tabuleiro); 0 sem rivais |
| `food_step` | a nova cabeça é o segundo passo do A\* temporal até a comida alvo |
| `food_dist` | passos do A\* temporal da nova cabeça até a comida alvo |
| `food_owned` | a comida alvo é minha no território desta candidata |
| `trapped_rivals` | rivais que ficam sem espaço para o corpo depois do meu passo (obstáculos estáticos) |
| `kill_chance` | a nova cabeça cai numa casa que uma rival estritamente menor pode ocupar |
| `hunt_step` | aproxima da rival estritamente menor mais próxima |
| `danger` | rival de tamanho maior ou igual a duas casas da nova cabeça |
| `center_dist` | distância de Manhattan até o centro |
| `hazard` | a nova cabeça cai num hazard sem comida, e o dano da partida é maior que 0 |

### Comida alvo e fome

- **Comida alvo**: a mais próxima pelo A\* temporal entre as comidas que são minhas no território do turno (sementes nas cabeças atuais, todas com distância 0). Se nenhuma for minha, vale a mais próxima alcançável.
- **Custo de vida do caminho**: 1 por passo, mais o dano de hazard nas casas de hazard sem comida.
- **Fome**: a cobra está com fome quando vale qualquer uma destas condições:
  - vida < custo + `HEALTH_MARGIN` (15), ou vida < `NO_PATH_HEALTH` (50) sem caminho até nenhuma comida;
  - tamanho < maior rival + `LENGTH_LEAD` (2);
  - tamanho < `START_LENGTH` (3) + turno ÷ `FEED_INTERVAL` (8).

## Decisão (`decision.py`)

Primeiro as camadas, depois a nota, depois a ordem canônica `up, down, left, right`:
1. não arriscada e com espaço;
2. arriscada e com espaço;
3. não arriscada e sem espaço;
4. arriscada e sem espaço.

Dentro da camada, vence a maior nota:

```
score = W_TERRITORY (1.0)  × territory_pct
      + W_FOOD (40)        se com fome e food_step
      + W_TRAP (60)        × rivais encurraladas
      + W_KILL (50)        se kill_chance
      + W_HUNT (10)        se hunt_step e sem fome
      − W_DANGER (25)      se danger
      − W_CENTER (1)       × center_dist, se sem fome
      + W_SURVIVAL (20)    × survival_depth / min(tamanho, SURVIVAL_MAX_DEPTH)
      − W_HAZARD (30)      se hazard
      − W_SQUEEZE (0.5)    × rival_territory_pct
```

`decision.explain` devolve também as parcelas de cada candidata e a ordem completa. A busca usa essa ordem para explorar e desempatar. `decision.py` só importa `config`, porque é o ponto em que o modelo de decisão externo (Jev) vai entrar.

## Busca no duelo (`search.py`)

- **Turno inteiro por nível**: para cada movimento meu, cada resposta da rival é simulada no mesmo turno (`simulator.step`, que segue a ordem oficial de `standard.go`). O valor do meu movimento é o pior entre as respostas: o modelo "paranoico", em que a rival responde como se conhecesse o meu movimento.
- **Poda alpha-beta** nos dois níveis. Ela não muda o valor, e um teste compara com o minimax sem poda.
- **Movimentos**: na raiz, as candidatas do filtro. Nos níveis internos, e para a rival, as direções que não são morte certa (`simulator.safe_moves`). Sem nenhuma, vale a primeira da ordem canônica, que elimina a cobra.
- **Valores terminais**: vitória `WIN − p`, derrota `−WIN + p`, empate `DRAW`, em que p é o número de turnos desde a raiz (`WIN` = 1.000.000, `DRAW` = −500.000).
- **Folha** (limitada a ±(|DRAW| − 1)):

  ```
  EVAL_TERRITORY (1.0) × (meu território − o da rival)    Voronoi temporal
  + EVAL_AREA (0.5)    × minha área temporal
  + EVAL_LENGTH (10)   × (meu tamanho − o da rival)
  − EVAL_FOOD (1.0)    × passos até a comida mais próxima × (100 − vida) / 100
  + EVAL_HEALTH (0.1)  × vida
  − EVAL_CENTER (0.5)  × distância até o centro
  ```
- **Veto**: a busca não escolhe o movimento de maior valor. Em cada profundidade, a escolha heurística é buscada primeiro, com janela cheia. Se o valor dela for maior que `DRAW`, ela fica, e as outras candidatas da raiz nem são buscadas. Se for derrota ou empate, as demais são buscadas (a resposta da profundidade anterior primeiro, depois a ordem heurística), e vale a de maior valor, se for maior que o dela. Entre substitutas de mesmo valor, vence a que vem antes na ordem heurística. Com todas as candidatas perdendo, vale a que perde mais tarde.
- **Por que só veto**: com os pesos iniciais da folha, o território domina a parcela de comida. Numa partida de teste, com vida entre 5 e 40, uma busca que sempre escolhesse o maior valor trocava a escolha heurística com fome (rumo à comida da própria cobra) pela direção da comida da rival, na profundidade 1 ou 2. A heurística decide entre os movimentos que não perdem, e a busca enxerga as derrotas à frente.
- **Aprofundamento iterativo**: profundidades 1, 2, … até `MAX_SEARCH_DEPTH` (20). O aprofundamento para quando uma profundidade termina sem nenhuma folha cortada pelo limite, porque a árvore foi resolvida.
- **Desligar a busca**: `MAX_SEARCH_DEPTH = 0` em `config.py`. Os testes de cenário da heurística usam a fixture `sem_busca` (`tests/conftest.py`), que faz isso.

## Aproximações

- **A simulação não gera comida.** A busca não prevê comida nova.
- **O crescimento das rivais é estimado** pela comida vizinha à cabeça. Uma rival que vai comer mais longe não é prevista.
- **A BFS temporal não espera.** A cobra não fica parada esperando uma casa liberar: uma casa recusada só é alcançada mais tarde a partir de outra casa da fronteira. Isso é conservador num corredor e pode subestimar a área ao lado de um corpo. A DFS de sobrevivência cobre esse caso, e por isso `roomy` também aceita `survives`.
- **O A\* temporal guarda o melhor tempo por casa.** Um caminho que chegaria mais tarde numa casa, justamente para encontrar a próxima já livre, é descartado.
- **O território e a ocupação são estimativas.** Os corpos das rivais são tratados como se encurtassem a cada turno, mas elas se movem para onde quiserem.
- **O modelo paranoico é pessimista.** Ele pode recusar jogadas boas cujo risco depende de a rival adivinhar o movimento.
- **A profundidade depende do orçamento.** Localmente a busca chega a cerca de 4 turnos num duelo 11x11 de meio de jogo. Na Lambda, deve ficar em 1 ou 2.
- **Os pesos da folha não estão calibrados.** Com os valores iniciais, a parcela de comida da folha vale no máximo cerca de 1 por passo, e o território vale 1 por casa. O veto limita o estrago: a folha só decide entre movimentos que substituem uma escolha heurística perdida. Em compensação, a busca não melhora jogadas sem fim de jogo à vista.

## Diferenças em relação às regras

O filtro trata a cauda das adversárias como ocupada. Pelas regras oficiais, a cauda que não está empilhada sempre sai do lugar, mesmo que a rival coma, porque o movimento vem antes da alimentação. O filtro é mais conservador de propósito. O simulador da busca segue as regras à risca.

## Calibrar o orçamento

A Lambda tem 128 MB, e a CPU é proporcional à memória: 1 vCPU equivale a 1.769 MB, então 128 MB dá cerca de 7% de uma vCPU. Código Python que só faz conta roda dezenas de vezes mais devagar que num laptop. As metas locais (10 ms com 8 cobras, 50 ms no 19x19) servem para comparar versões. O que vale é o relógio da Lambda.

Para calibrar `SEARCH_BUDGET_MAX_MS`:
1. Jogue partidas de duelo e com 8 cobras na Arena.
2. Procure turnos com `timed_out_last_turn` verdadeiro, com a consulta "Turnos que estouraram o tempo" de [`docs/logs.md`](logs.md). A sintaxe do filtro booleano ainda está a conferir lá.
3. Compare com a duração das linhas `REPORT` (consulta "Duração da Lambda"). O timeout do motor (500 ms) inclui a rede, então a duração precisa ficar bem abaixo disso.
4. Se houver estouro, reduza `SEARCH_BUDGET_MAX_MS` antes de avaliar a estratégia. Se a fase heurística sozinha já passar do orçamento com 8 cobras, o próximo passo é cortar medições.

`SEARCH_BUDGET_MAX_MS` pode vir da variável de ambiente de mesmo nome. Um valor ausente, vazio, não inteiro ou não positivo vale o padrão do código (120), sem erro. A IaC não define essa variável. **Uma variável definida à mão no console da Lambda pode sumir no próximo `cdk deploy`.** Para uma mudança duradoura, altere o padrão em `config.py`.
