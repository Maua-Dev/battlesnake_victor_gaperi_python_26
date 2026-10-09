# decisao-de-movimento Specification

## Purpose

Define como uma lista de medições por direção, mais o contexto da jogada, vira um único movimento. A regra é determinística e independente do estado bruto do jogo, para que um modelo de decisão externo possa substituí-la recebendo exatamente as mesmas entradas.

## Requirements

### Requirement: Entradas restritas
A decisão SHALL depender apenas da lista de medições (ver `caracteristicas-de-movimento`) e do contexto da jogada, que tem vida, tamanho, turno e se a cobra está com fome. Ela não SHALL ler o estado do jogo nem os modelos do payload do Battlesnake. Para as mesmas entradas, SHALL devolver sempre o mesmo movimento. A lista recebida nunca é vazia: sem candidatas, vale o fallback de emergência de `estrategia-de-movimento`. Uma lista vazia SHALL ser rejeitada com erro.

#### Scenario: Decisão sem tabuleiro
- **WHEN** a decisão recebe medições montadas à mão e um contexto, sem nenhum estado de jogo
- **THEN** devolve o `move` de uma das medições

#### Scenario: Independência do payload
- **WHEN** o código da decisão é inspecionado
- **THEN** ele não importa os modelos do payload nem o estado do jogo

#### Scenario: Lista vazia
- **WHEN** a decisão recebe uma lista vazia
- **THEN** ela lança erro

### Requirement: Camadas de segurança
A decisão SHALL agrupar as medições em quatro camadas, nesta ordem de preferência, e considerar só a primeira camada não vazia:
1. não arriscada e com espaço (`risky` falso, `roomy` verdadeiro);
2. arriscada e com espaço;
3. não arriscada e sem espaço;
4. arriscada e sem espaço.

Nenhuma pontuação de uma camada posterior SHALL vencer uma medição de camada anterior.

#### Scenario: Não arriscada com espaço vence tudo
- **WHEN** `up` está na camada 2 com pontuação 500 e `down` está na camada 1 com pontuação 0
- **THEN** a resposta é `down`

#### Scenario: Ordem das camadas
- **WHEN** há uma medição em cada uma das camadas 2, 3 e 4, e nenhuma na camada 1
- **THEN** a resposta é a da camada 2; sem ela, a da camada 3; sem as duas, a da camada 4

#### Scenario: Beco versus cabeça a cabeça
- **WHEN** o corpo é [(0,1),(1,1),(2,1),(2,0),(1,0)] e uma adversária de tamanho 6 ocupa [(0,3),(0,4),(0,5),(0,6),(0,7),(0,8)]
- **THEN** `down` é não arriscada mas leva a um bolsão de 2 casas, `up` é arriscada com área grande, e a resposta é `up`

#### Scenario: Não morde a isca
- **WHEN** o corpo é [(5,5),(5,4),(5,3),(5,2)] e uma adversária de tamanho 5 ocupa [(7,5),(8,5),(9,5),(10,5),(10,4)]
- **THEN** `right` é arriscada e a resposta é `left`

### Requirement: Pontuação dentro da camada
Dentro da camada escolhida, cada medição SHALL receber a pontuação abaixo, com os pesos vindos do módulo de configuração:

```
score = W_TERRITORY * territory_pct
      + (com fome e food_step ? W_FOOD : 0)
      + W_TRAP * quantidade de trapped_rivals
      + (kill_chance ? W_KILL : 0)
      + (hunt_step e sem fome ? W_HUNT : 0)
      - (danger ? W_DANGER : 0)
      - (sem fome ? W_CENTER * center_dist : 0)
```

A maior pontuação SHALL vencer.

#### Scenario: Peso do território
- **WHEN** duas medições na mesma camada diferem só em `territory_pct`, 30 e 40
- **THEN** vence a de 40

#### Scenario: Comida só pesa com fome
- **WHEN** `up` tem `territory_pct` 50 e `down` tem `territory_pct` 20 com `food_step` verdadeiro, ambas na mesma camada
- **THEN** com fome a resposta é `down` (60 > 50), e sem fome é `up`

#### Scenario: Peso da rival encurralada
- **WHEN** `up` tem `territory_pct` 0 e uma rival encurralada, e `down` tem `territory_pct` 59, sem fome e com o mesmo `center_dist`
- **THEN** a resposta é `up` (60 > 59)

#### Scenario: Peso da chance de matar
- **WHEN** `up` tem `kill_chance` verdadeiro e `territory_pct` 0, e `down` tem `territory_pct` 49, com fome
- **THEN** a resposta é `up` (50 > 49)

#### Scenario: Caça só pesa sem fome
- **WHEN** `up` tem `hunt_step` verdadeiro e `territory_pct` 0, `down` tem `territory_pct` 5 e as duas têm o mesmo `center_dist`
- **THEN** sem fome a resposta é `up` (10 > 5), e com fome é `down`

#### Scenario: Peso do perigo
- **WHEN** `up` tem `danger` verdadeiro e `territory_pct` 30, e `down` tem `territory_pct` 10, com fome
- **THEN** a resposta é `down` (10 > 5)

#### Scenario: Centro só pesa sem fome
- **WHEN** `up` tem `center_dist` 8 e `down` tem `center_dist` 2, com o mesmo `territory_pct`
- **THEN** sem fome a resposta é `down`, e com fome é `up` pelo desempate

#### Scenario: Encurrala a rival menor
- **WHEN** o corpo é [(2,9),(1,9),(1,8),(1,7)], uma adversária "menor" ocupa [(0,10),(0,9),(0,8)] e há comida em (5,9), cujo caminho começa por `right`
- **THEN** a resposta é `up`, que fecha a única saída da rival e vale mais que seguir a comida

#### Scenario: Ataca a rival menor
- **WHEN** o corpo é [(5,5),(5,4),(5,3),(5,2)], uma adversária de tamanho 3 ocupa [(7,5),(8,5),(9,5)] e há comida em (5,8), cujo caminho começa por `up`
- **THEN** a resposta é `right`, a casa que a rival menor pode ocupar no próximo turno

### Requirement: Desempate pela ordem canônica
Em empate de pontuação, a decisão SHALL escolher a primeira direção na ordem `up, down, left, right`, independentemente da ordem em que as medições chegaram.

#### Scenario: Empate com lista fora de ordem
- **WHEN** a decisão recebe as medições [`right`, `up`] com a mesma camada e a mesma pontuação
- **THEN** a resposta é `up`

### Requirement: Explicação da decisão
Para as mesmas entradas da decisão (lista de medições e contexto da jogada), SHALL existir uma explicação que devolve:
- o movimento escolhido, sempre igual ao devolvido pela decisão;
- para cada medição, a camada de segurança (de 0 a 3, na ordem do requisito "Camadas de segurança"), a pontuação e as parcelas da pontuação;
- o motivo da escolha.

As parcelas SHALL ser `territory`, `food`, `trap`, `kill`, `hunt`, `danger` e `center`, com os sinais da fórmula de "Pontuação dentro da camada" (`danger` e `center` são negativas ou zero). A soma delas SHALL ser igual à pontuação usada pela decisão.

O motivo SHALL ser:
- `only_option`: a lista tem uma única medição;
- `layer`: a escolhida é a única medição da melhor camada presente;
- `score`: a pontuação da escolhida é estritamente maior que a de todas as outras medições da mesma camada;
- `tie`: outra medição da mesma camada tem a mesma pontuação, e a ordem canônica desempatou.

A explicação segue as restrições do requisito "Entradas restritas": não lê o estado do jogo, não importa os modelos do payload e rejeita lista vazia com erro.

#### Scenario: Única medição
- **WHEN** a explicação recebe só a medição de `left`
- **THEN** o movimento é `left` e o motivo é `only_option`

#### Scenario: Vence pela camada
- **WHEN** `up` está na camada 2 com pontuação 500 e `down` está na camada 1 com pontuação 0
- **THEN** o movimento é `down`, o motivo é `layer`, e a camada informada é 1 para `up` e 0 para `down`

#### Scenario: Vence pela pontuação
- **WHEN** `up` tem `territory_pct` 50 e `down` tem `territory_pct` 20 com `food_step` verdadeiro, ambas na mesma camada e com fome
- **THEN** o movimento é `down`, o motivo é `score`, e as parcelas de `down` têm `territory` 20 e `food` 40

#### Scenario: Empate com lista fora de ordem
- **WHEN** a explicação recebe as medições [`right`, `up`] com a mesma camada e a mesma pontuação
- **THEN** o movimento é `up` e o motivo é `tie`

#### Scenario: Coerência com a decisão
- **WHEN** a decisão e a explicação recebem as mesmas medições e o mesmo contexto, em qualquer cenário de teste da decisão
- **THEN** o movimento da explicação é igual ao da decisão, e a pontuação de cada medição é igual à soma das suas parcelas
