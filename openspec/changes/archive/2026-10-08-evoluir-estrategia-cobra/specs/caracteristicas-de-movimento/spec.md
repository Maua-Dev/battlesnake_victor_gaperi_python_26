## Purpose

Define o que é medido para cada direção candidata a cada jogada: risco, espaço, território, comida, rivais encurraladas, caça, perigo e centro. Essas medições são o único insumo da decisão e, no futuro, o contexto entregue ao modelo de decisão externo.

Convenções de `estrategia-de-movimento`: origem (0,0) no canto inferior esquerdo, `up` é y+1, o primeiro segmento é a cabeça e o último é a cauda, e a ordem canônica é `up, down, left, right`. "Nova cabeça" é a casa de destino da candidata.

## ADDED Requirements

### Requirement: Uma medição por candidata
A etapa de características SHALL receber o estado do jogo e a lista de candidatas e SHALL devolver uma medição por candidata, na mesma ordem da lista. Ela não SHALL escolher nem descartar direções. Cada medição SHALL ter os campos `move`, `risky`, `area`, `roomy`, `territory_pct`, `food_step`, `food_dist`, `trapped_rivals`, `kill_chance`, `hunt_step`, `danger` e `center_dist`.

#### Scenario: Ordem preservada
- **WHEN** as candidatas são [`up`, `left`, `right`]
- **THEN** são devolvidas três medições, com `move` igual a `up`, `left` e `right`, nessa ordem

### Requirement: Obstáculos
Os obstáculos SHALL ser todas as casas ocupadas por qualquer cobra, menos as caudas que saem do lugar neste turno. Uma cauda sai do lugar quando o último segmento é diferente do penúltimo. Essa regra vale para a própria cobra e para as adversárias e é a base da área, do território, da comida e das rivais encurraladas. O filtro de candidatas continua tratando a cauda das adversárias como ocupada (ver "Não entrar em adversárias" em `estrategia-de-movimento`).

#### Scenario: Cauda de rival que sai do lugar
- **WHEN** uma adversária ocupa [(4,2),(4,1)]
- **THEN** (4,2) é obstáculo e (4,1) não é

#### Scenario: Cauda de rival empilhada
- **WHEN** uma adversária ocupa [(4,3),(4,2),(4,2)]
- **THEN** (4,3) e (4,2) são obstáculos

### Requirement: Risco
`risky` SHALL ser verdadeiro quando a nova cabeça fica a distância de Manhattan 1 da cabeça de uma adversária de tamanho maior ou igual.

#### Scenario: Casa alcançável por rival igual
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(3,10),(2,10),(1,10)]
- **THEN** `risky` é verdadeiro para `left` e falso para `right`

### Requirement: Área alcançável
`area` SHALL ser a quantidade de casas alcançáveis a partir da nova cabeça, ela inclusive. Contam como bloqueadas os obstáculos e as casas vizinhas às cabeças de adversárias estritamente maiores. A própria nova cabeça não conta como bloqueada. `roomy` SHALL ser verdadeiro quando `area` for maior ou igual ao tamanho da cobra.

#### Scenario: Área num tabuleiro vazio
- **WHEN** o tabuleiro é 5x5, nada está bloqueado e a contagem começa em (2,2)
- **THEN** a área é 25

#### Scenario: Área limitada por um muro
- **WHEN** o tabuleiro é 5x5, toda a coluna x=2 está bloqueada e a contagem começa em (0,0)
- **THEN** a área é 10

#### Scenario: Início bloqueado ou fora do tabuleiro
- **WHEN** a contagem começa numa casa bloqueada ou fora do tabuleiro
- **THEN** a área é 0

#### Scenario: Bolsão menor que a cobra
- **WHEN** o corpo é [(0,1),(1,1),(2,1),(2,0),(1,0)] e uma adversária ocupa [(0,3),(0,4),(0,5),(0,6),(0,7),(0,8)]
- **THEN** `down` tem `area` 2 e `roomy` falso, e `up` tem `roomy` verdadeiro

### Requirement: Território
O território SHALL ser calculado por uma busca em largura com várias origens, uma semente por cobra viva. Cada semente tem uma casa de origem e uma distância inicial. A distância de uma cobra até uma casa é a distância inicial mais o número de passos do caminho mais curto que não atravessa obstáculos. A casa de origem conta para a própria cobra mesmo sendo obstáculo, e nenhuma outra cobra fica com ela.

Cada casa alcançável pertence à cobra de menor distância. Se várias empatam, a casa fica com a única estritamente maior entre as empatadas. Se não houver uma única maior, a casa é disputada: não conta para ninguém, mas continua sendo expandida para todas as empatadas.

Ao medir uma candidata, a semente da cobra é a nova cabeça com distância 1 e a de cada adversária é a cabeça atual dela com distância 0. `territory_pct` SHALL ser 100 vezes as casas da cobra divididas pelas casas livres do tabuleiro (largura × altura menos a quantidade de obstáculos).

#### Scenario: Tamanhos iguais dividem o tabuleiro
- **WHEN** o tabuleiro é 5x5, a cobra ocupa [(0,2)], uma adversária ocupa [(4,2)] e as duas sementes começam na cabeça com distância 0
- **THEN** a cobra tem 10 casas, a adversária tem 10 e a coluna x=2 é disputada

#### Scenario: Rival maior leva o empate
- **WHEN** o tabuleiro é 5x5, a cobra ocupa [(0,2)], uma adversária ocupa [(4,2),(4,1)] e as duas sementes começam na cabeça com distância 0
- **THEN** a cobra tem 10 casas e a adversária tem 15, incluindo a coluna x=2 e a casa da própria cauda

#### Scenario: Semente com distância inicial 1
- **WHEN** o tabuleiro é 5x5, a cobra ocupa [(0,2)] com semente de distância 1 e uma adversária de mesmo tamanho ocupa [(4,2)] com semente de distância 0
- **THEN** a cobra tem 10 casas (colunas x=0 e x=1) e a adversária tem 15

#### Scenario: Três cobras de mesmo tamanho
- **WHEN** o tabuleiro é 5x5 e cobras de tamanho 1 ocupam [(0,2)], [(4,2)] e [(2,0)], todas com distância 0
- **THEN** as contagens são 7, 7 e 4, nessa ordem

### Requirement: Comida
`food_step` SHALL ser verdadeiro quando a nova cabeça é a segunda casa do caminho mais curto da cabeça atual até a comida alvo (ver "Comida alvo" em `estrategia-de-movimento`). `food_dist` SHALL ser a quantidade de passos do caminho mais curto da nova cabeça até a comida alvo, com os mesmos bloqueios, ou ausente quando não houver comida alvo ou caminho. Se a nova cabeça for a própria comida, `food_dist` é 0.

#### Scenario: Primeiro passo até a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], não há adversárias e há comida em (2,5)
- **THEN** `left` tem `food_step` verdadeiro e `food_dist` 2, e `up` tem `food_step` falso e `food_dist` 4

#### Scenario: Sem comida
- **WHEN** não há comida no tabuleiro
- **THEN** todas as medições têm `food_step` falso e `food_dist` ausente

### Requirement: Rivais encurraladas
Para cada candidata, a cobra SHALL simular o próprio passo acrescentando a nova cabeça aos obstáculos. Para cada adversária, SHALL calcular a área dela como a maior entre as áreas alcançáveis a partir de cada uma das casas vizinhas à cabeça dela, com esses obstáculos e sem considerar outras ameaças. A adversária está encurralada quando essa área é menor que o tamanho dela. `trapped_rivals` SHALL listar os ids das adversárias encurraladas, na ordem em que aparecem no tabuleiro.

#### Scenario: O passo fecha a única saída
- **WHEN** o corpo é [(2,9),(1,9),(1,8),(1,7)] e uma adversária "menor" ocupa [(0,10),(0,9),(0,8)]
- **THEN** `up` tem `trapped_rivals` igual a ["menor"], e `down` e `right` têm lista vazia

### Requirement: Chance de matar e caça
`kill_chance` SHALL ser verdadeiro quando a nova cabeça fica a distância de Manhattan 1 da cabeça de uma adversária estritamente menor. A presa é a adversária estritamente menor cuja cabeça está mais perto, por Manhattan, da cabeça atual; em empate, a primeira no tabuleiro. `hunt_step` SHALL ser verdadeiro quando a distância de Manhattan da nova cabeça até a cabeça da presa for menor que a da cabeça atual. Sem adversária menor, `hunt_step` é falso.

#### Scenario: Casa que a rival menor pode ocupar
- **WHEN** o corpo é [(5,5),(5,4),(5,3),(5,2)] e uma adversária ocupa [(7,5),(8,5),(9,5)]
- **THEN** `right` tem `kill_chance` e `hunt_step` verdadeiros, e `up` e `left` têm os dois falsos

#### Scenario: Rival maior não é presa
- **WHEN** o corpo é [(5,5),(5,4),(5,3),(5,2)] e uma adversária ocupa [(7,5),(8,5),(9,5),(10,5),(10,4)]
- **THEN** todas as medições têm `kill_chance` e `hunt_step` falsos, e `right` tem `risky` verdadeiro

### Requirement: Perigo e centro
`danger` SHALL ser verdadeiro quando a nova cabeça fica a distância de Manhattan exatamente 2 da cabeça de uma adversária de tamanho maior ou igual. `center_dist` SHALL ser a distância de Manhattan da nova cabeça até a casa (largura ÷ 2, altura ÷ 2), com divisão inteira.

#### Scenario: Rival igual a duas casas
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** `right` tem `danger` verdadeiro, porque (6,10) fica a 2 casas de (4,10)

#### Scenario: Centro do 11x11
- **WHEN** o tabuleiro é 11x11 e a nova cabeça é (5,6)
- **THEN** `center_dist` é 1
