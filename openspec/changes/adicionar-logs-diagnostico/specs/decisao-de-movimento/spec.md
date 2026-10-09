## ADDED Requirements

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
