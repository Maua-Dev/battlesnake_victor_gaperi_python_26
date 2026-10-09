# representacao-do-tabuleiro Specification

## Purpose

Define a representação leve do tabuleiro em que rodam as medições temporais, a sobrevivência, o simulador e a busca: as casas como índices, os vizinhos pré-calculados e o dano de hazard lido das regras da partida.

## Requirements

### Requirement: Casas como índices
Cada casa (x, y) de um tabuleiro de largura L SHALL ter o índice `y * L + x`. A conversão de volta SHALL devolver a mesma casa (x, y). As convenções de `estrategia-de-movimento` continuam valendo: origem no canto inferior esquerdo e `up` é y+1.

#### Scenario: Ida e volta
- **WHEN** o tabuleiro é 11x11 e a casa é (3,7)
- **THEN** o índice é 80, e o índice 80 volta para (3,7)

#### Scenario: Tabuleiro não quadrado
- **WHEN** o tabuleiro tem largura 7 e altura 5 e a casa é (6,4)
- **THEN** o índice é 34, e o índice 34 volta para (6,4)

### Requirement: Vizinhos pré-calculados
Para cada tamanho de tabuleiro (largura, altura), SHALL existir uma tabela com os vizinhos de cada índice dentro do tabuleiro, na ordem canônica `up, down, left, right`, e sem as direções que saem do tabuleiro. A tabela de um tamanho SHALL ser calculada uma vez e reaproveitada nas jogadas seguintes com o mesmo tamanho.

#### Scenario: Casa do meio
- **WHEN** o tabuleiro é 11x11 e a casa é (5,5)
- **THEN** os vizinhos são (5,6), (5,4), (4,5) e (6,5), nessa ordem

#### Scenario: Canto inferior esquerdo
- **WHEN** o tabuleiro é 11x11 e a casa é (0,0)
- **THEN** os vizinhos são (0,1) e (1,0), nessa ordem

#### Scenario: Borda superior
- **WHEN** o tabuleiro é 11x11 e a casa é (4,10)
- **THEN** os vizinhos são (4,9), (3,10) e (5,10), nessa ordem

#### Scenario: Canto superior direito
- **WHEN** o tabuleiro é 11x11 e a casa é (10,10)
- **THEN** os vizinhos são (10,9) e (9,10), nessa ordem

#### Scenario: Reaproveitamento
- **WHEN** duas jogadas seguidas chegam com tabuleiros 11x11
- **THEN** as duas usam a mesma tabela de vizinhos

### Requirement: Estado leve da jogada
A cada jogada, o estado recebido SHALL ser convertido uma única vez numa representação que guarda:
- a largura e a altura;
- para cada cobra: o id, o corpo como lista de índices (cabeça primeiro, repetições mantidas), a vida, o tamanho e se está viva;
- a comida como conjunto de índices;
- os hazards com a quantidade de vezes que cada índice aparece na lista recebida;
- o dano de hazard por turno.

As medições temporais, a sobrevivência, o simulador e a busca SHALL trabalhar só sobre essa representação, sem consultar os modelos do payload dentro dos seus laços.

#### Scenario: Cauda empilhada preservada
- **WHEN** uma cobra chega com o corpo [(4,3),(4,2),(4,2)] num 11x11
- **THEN** o corpo convertido é [37, 26, 26] e o tamanho é 3

#### Scenario: Hazard repetido
- **WHEN** a lista de hazards traz (5,6) duas vezes
- **THEN** o índice de (5,6) aparece com quantidade 2

### Requirement: Dano de hazard das regras da partida
O dano de hazard por turno SHALL ser lido de `game.ruleset.settings.hazardDamagePerTurn`, o nome usado pelas regras oficiais. Quando o valor está ausente ou não é um inteiro, o dano SHALL ser 0. Nenhum valor fixo SHALL ser assumido.

#### Scenario: Dano informado
- **WHEN** `game.ruleset.settings.hazardDamagePerTurn` é 14
- **THEN** o dano de hazard é 14

#### Scenario: Sem settings
- **WHEN** `game.ruleset` é `{"name": "standard", "version": "v1.2.3"}`
- **THEN** o dano de hazard é 0

#### Scenario: Valor inválido
- **WHEN** `game.ruleset.settings.hazardDamagePerTurn` é `"muito"`
- **THEN** o dano de hazard é 0
