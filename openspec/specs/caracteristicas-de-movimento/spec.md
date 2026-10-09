# caracteristicas-de-movimento Specification

## Purpose

Define o que é medido para cada direção candidata a cada jogada: risco, espaço, território, comida, rivais encurraladas, caça, perigo e centro. Essas medições são o único insumo da decisão e, no futuro, o contexto entregue ao modelo de decisão externo.

Convenções de `estrategia-de-movimento`: origem (0,0) no canto inferior esquerdo, `up` é y+1, o primeiro segmento é a cabeça e o último é a cauda, e a ordem canônica é `up, down, left, right`. "Nova cabeça" é a casa de destino da candidata.

## Requirements

### Requirement: Uma medição por candidata
A etapa de características SHALL receber o estado do jogo e a lista de candidatas e SHALL devolver uma medição por candidata, na mesma ordem da lista. Ela não SHALL escolher nem descartar direções. Cada medição SHALL ter os campos `move`, `risky`, `area`, `roomy`, `territory_pct`, `food_step`, `food_dist`, `trapped_rivals`, `kill_chance`, `hunt_step`, `danger`, `center_dist`, `survival_depth`, `survives`, `hazard`, `rival_territory_pct` e `food_owned`. Os cinco últimos SHALL ter valor padrão (`survival_depth` 0, `survives` verdadeiro, `hazard` falso, `rival_territory_pct` 0,0 e `food_owned` falso), para que uma medição montada sem eles continue válida.

#### Scenario: Ordem preservada
- **WHEN** as candidatas são [`up`, `left`, `right`]
- **THEN** são devolvidas três medições, com `move` igual a `up`, `left` e `right`, nessa ordem

#### Scenario: Medição montada sem os campos novos
- **WHEN** uma medição é montada só com os campos de `move` a `center_dist`
- **THEN** ela tem `survival_depth` 0, `survives` verdadeiro, `hazard` falso, `rival_territory_pct` 0,0 e `food_owned` falso

### Requirement: Obstáculos
Os obstáculos estáticos SHALL ser todas as casas ocupadas por qualquer cobra, menos as caudas que saem do lugar neste turno. Uma cauda sai do lugar quando o último segmento é diferente do penúltimo. Essa regra vale para a própria cobra e para as adversárias e é a base das rivais encurraladas e da contagem de casas livres do território. A área, o território e a comida usam a ocupação temporal (ver "Ocupação temporal"). O filtro de candidatas continua tratando a cauda das adversárias como ocupada (ver "Não entrar em adversárias" em `estrategia-de-movimento`).

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
`area` SHALL ser a quantidade de casas alcançadas pela busca em largura temporal a partir da nova cabeça no tempo 1, ela inclusive. Contam como bloqueadas de vez as casas vizinhas às cabeças de adversárias estritamente maiores, menos a própria nova cabeça. As casas ocupadas por cobras seguem a ocupação temporal da candidata. `roomy` SHALL ser verdadeiro quando `area` for maior ou igual ao tamanho da cobra **ou** `survives` for verdadeiro.

#### Scenario: Área num tabuleiro vazio
- **WHEN** o tabuleiro é 5x5, nada está bloqueado e a contagem começa em (2,2)
- **THEN** a área é 25

#### Scenario: Área limitada por um muro
- **WHEN** o tabuleiro é 5x5, toda a coluna x=2 está bloqueada de vez e a contagem começa em (0,0)
- **THEN** a área é 10

#### Scenario: Início bloqueado ou fora do tabuleiro
- **WHEN** a contagem começa numa casa bloqueada ou fora do tabuleiro
- **THEN** a área é 0

#### Scenario: Fuga perseguindo a própria cauda
- **WHEN** o corpo é [(0,1),(1,1),(2,1),(2,0),(1,0)] e uma adversária ocupa [(0,3),(0,4),(0,5),(0,6),(0,7),(0,8)]
- **THEN** `down` tem `area` maior que 5 e `roomy` verdadeiro, porque (1,0) libera em 1 movimento e (2,0) em 2, e por eles a cobra chega ao resto do tabuleiro

#### Scenario: Bolsão menor que a cobra
- **WHEN** o corpo é [(2,10),(3,10),(4,10),(5,10)] e uma adversária ocupa [(5,8),(4,8),(3,8),(2,8),(1,8),(1,9),(0,9),(0,8),(0,7),(0,6)]
- **THEN** `left` tem `area` 2 e `roomy` falso, porque (1,9) só libera em 5 movimentos e (0,9) só em 4, e `down` tem `roomy` verdadeiro

### Requirement: Território
O território SHALL ser calculado por uma busca em largura temporal com várias origens, uma semente por cobra viva. Cada semente tem uma casa de origem e uma distância inicial. Uma cobra só SHALL alcançar uma casa na distância d se a casa estiver dentro do tabuleiro e tiver `free_after` menor ou igual a d. A casa de origem conta para a própria cobra mesmo ocupada, e nenhuma outra cobra fica com ela.

Cada casa alcançável pertence à cobra de menor distância. Se várias empatam, a casa fica com a única estritamente maior entre as empatadas. Se não houver uma única maior, a casa é disputada: não conta para ninguém, mas continua sendo expandida para todas as empatadas.

Ao medir uma candidata, a semente da cobra é a nova cabeça com distância 1 e a de cada adversária é a cabeça atual dela com distância 0. `territory_pct` SHALL ser 100 vezes as casas da cobra divididas pelas casas livres do tabuleiro (largura × altura menos a quantidade de obstáculos estáticos). `rival_territory_pct` SHALL ser 100 vezes as casas da maior adversária (a de maior tamanho; no empate, a primeira no tabuleiro) divididas pelas mesmas casas livres, ou 0 sem adversárias.

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

#### Scenario: Casa ocupada que libera a tempo
- **WHEN** o tabuleiro tem 3x1 casas, só há uma semente, em (0,0) com distância 0, e `free_after` de (1,0) é 1
- **THEN** a cobra tem 3 casas; com `free_after` de (1,0) igual a 2, ela tem 1

#### Scenario: Território da adversária no duelo
- **WHEN** há uma única adversária
- **THEN** `rival_territory_pct` de cada candidata é 100 vezes as casas dela no território daquela candidata divididas pelas casas livres

### Requirement: Comida
`food_step` SHALL ser verdadeiro quando a nova cabeça é a segunda casa do caminho mais curto, pela ocupação temporal, da cabeça atual até a comida alvo (ver "Comida alvo" em `estrategia-de-movimento`). Nesse caminho, a casa alcançada no passo t precisa ter `free_after` menor ou igual a t. `food_dist` SHALL ser a quantidade de passos do caminho mais curto da nova cabeça (tempo 1) até a comida alvo, com os mesmos bloqueios, ou ausente quando não houver comida alvo ou caminho. Se a nova cabeça for a própria comida, `food_dist` é 0. `food_owned` SHALL ser verdadeiro quando a comida alvo pertence à cobra no território medido para a candidata.

#### Scenario: Primeiro passo até a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], não há adversárias e há comida em (2,5)
- **THEN** `left` tem `food_step` verdadeiro e `food_dist` 2, e `up` tem `food_step` falso e `food_dist` 4

#### Scenario: Sem comida
- **WHEN** não há comida no tabuleiro
- **THEN** todas as medições têm `food_step` falso, `food_dist` ausente e `food_owned` falso

#### Scenario: Comida no meu território
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], não há adversárias e há comida em (2,5)
- **THEN** todas as medições têm `food_owned` verdadeiro

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

### Requirement: Ocupação temporal
A cada jogada, SHALL ser calculado para cada casa em quantos movimentos ela fica livre (`free_after`):
- casa sem cobra: 0;
- para uma cobra com n segmentos (repetições contadas), o segmento de posição i (0 é a cabeça) libera a casa depois de `n - i` movimentos;
- quando dois segmentos ocupam a mesma casa (cauda empilhada depois de comer), vale o maior valor;
- **crescimento das adversárias**: quando a cabeça de uma adversária está a distância de Manhattan 1 de uma comida, cada segmento dela, menos o último, soma 1 antes de tirar o maior por casa. Ela pode comer no próximo turno, e aí o corpo para de encurtar por um turno. Pelas regras oficiais, o movimento vem antes da alimentação, e por isso a casa da cauda atual libera no próximo turno mesmo quando a cobra come;
- **crescimento da própria cobra**: ao medir uma candidata cuja nova cabeça tem comida, a mesma regra vale para a própria cobra.

A ocupação temporal é a base da área, do território, da comida e da sobrevivência. As rivais encurraladas continuam usando os obstáculos estáticos.

#### Scenario: Adversária reta
- **WHEN** uma adversária ocupa [(3,5),(2,5),(1,5)] e não há comida vizinha à cabeça dela
- **THEN** `free_after` vale 3 em (3,5), 2 em (2,5), 1 em (1,5) e 0 nas casas sem cobra

#### Scenario: Cauda empilhada atrasa um turno
- **WHEN** uma adversária ocupa [(3,5),(2,5),(2,5)]
- **THEN** `free_after` vale 3 em (3,5) e 2 em (2,5)

#### Scenario: Adversária ao lado de comida
- **WHEN** uma adversária ocupa [(3,5),(2,5),(1,5)] e há comida em (3,6)
- **THEN** `free_after` vale 4 em (3,5), 3 em (2,5) e 1 em (1,5)

#### Scenario: Candidata que come
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], há comida em (5,6) e a candidata é `up`
- **THEN** na medição de `up`, `free_after` vale 4 em (5,5), 3 em (5,4) e 1 em (5,3)

#### Scenario: Comida com cauda já empilhada
- **WHEN** uma adversária ocupa [(3,5),(2,5),(1,5),(1,5)] e há comida em (3,6)
- **THEN** `free_after` vale 5 em (3,5), 4 em (2,5) e 3 em (1,5)

### Requirement: Busca em largura temporal
A busca em largura temporal SHALL partir de uma casa num tempo inicial t0. Um vizinho só SHALL ser alcançado no tempo t+1 se estiver dentro do tabuleiro, fora das casas bloqueadas de vez e com `free_after` menor ou igual a t+1. Uma casa recusada num tempo SHALL poder ser alcançada mais tarde, a partir de outra casa da fronteira, se nesse tempo já estiver livre. A cobra não fica parada esperando a casa liberar.

#### Scenario: Casa que libera a tempo
- **WHEN** o tabuleiro tem 3x1 casas, a busca parte de (0,0) no tempo 0, `free_after` de (1,0) é 1 e o resto é 0
- **THEN** as 3 casas são alcançadas

#### Scenario: Casa que não libera a tempo
- **WHEN** o tabuleiro tem 3x1 casas, a busca parte de (0,0) no tempo 0, `free_after` de (1,0) é 2 e o resto é 0
- **THEN** só (0,0) é alcançada

### Requirement: Sobrevivência por busca em profundidade
Para cada candidata, uma busca em profundidade com retrocesso SHALL partir da nova cabeça (profundidade 1) e simular, passo a passo:
- o deslocamento exato do próprio corpo: a cauda sai a cada passo, menos no passo seguinte a uma alimentação, e a comida comida some daquele caminho;
- a vida: 1 a menos por passo e o dano de hazard nas casas de hazard sem comida, como na simulação de turno; comer volta a vida a 100; um passo que leva a vida a 0 sem comida não é possível;
- as adversárias pela ocupação temporal: a casa só pode ser ocupada no passo t se `free_after` for menor ou igual a t.

As direções SHALL ser tentadas na ordem canônica. A profundidade alvo é `min(tamanho da cobra, SURVIVAL_MAX_DEPTH)`, com `SURVIVAL_MAX_DEPTH` = 12. Cada casa entrada conta como um nó, inclusive a nova cabeça, e o limite é `SURVIVAL_MAX_NODES` = 400 nós por candidata. A busca SHALL parar ao atingir a profundidade alvo, ao chegar ao limite de nós ou ao passar do prazo (ver `controle-de-tempo`). `survival_depth` SHALL ser a maior profundidade alcançada, e `survives` SHALL ser verdadeiro quando a profundidade alvo for atingida.

#### Scenario: Persegue a própria cauda num espaço menor que o corpo
- **WHEN** o tabuleiro tem 3x2 casas, o corpo é [(0,0),(0,1),(1,1),(2,1),(2,0)], não há adversárias e a candidata é `right`
- **THEN** a área estática da nova cabeça (1,0) seria 1, mas `survives` é verdadeiro e `survival_depth` é 5

#### Scenario: Bolsão sem saída
- **WHEN** o corpo é [(2,10),(3,10),(4,10),(5,10)] e uma adversária ocupa [(5,8),(4,8),(3,8),(2,8),(1,8),(1,9),(0,9),(0,8),(0,7),(0,6)]
- **THEN** `left` tem `survival_depth` 2 e `survives` falso

#### Scenario: Limite de nós
- **WHEN** `SURVIVAL_MAX_NODES` é 3, o tabuleiro é 11x11 sem adversárias e o corpo tem tamanho 5
- **THEN** a busca de cada candidata entra em no máximo 3 casas, `survival_depth` é no máximo 3 e `survives` é falso

#### Scenario: Fome dentro da busca
- **WHEN** a vida é 2, o corpo é [(5,5),(5,4),(5,3)], não há comida e a candidata é `up`
- **THEN** `survival_depth` é 1 e `survives` é falso

### Requirement: Hazard na nova cabeça
`hazard` SHALL ser verdadeiro quando a nova cabeça cai numa casa de hazard sem comida e o dano de hazard da partida é maior que 0.

#### Scenario: Casa de hazard
- **WHEN** o dano de hazard é 14 e a nova cabeça de `up` é um hazard sem comida
- **THEN** `up` tem `hazard` verdadeiro e as outras candidatas, fora de hazards, têm `hazard` falso

#### Scenario: Hazard sem dano
- **WHEN** a nova cabeça de `up` é um hazard, mas o dano de hazard é 0
- **THEN** `up` tem `hazard` falso
