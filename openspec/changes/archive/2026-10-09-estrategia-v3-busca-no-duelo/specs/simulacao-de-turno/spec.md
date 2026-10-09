## Purpose

Define como a cobra avança um turno do modo standard na própria cabeça, dado um movimento por cobra viva, seguindo a ordem das regras oficiais do Battlesnake. É a base da busca no duelo.

## ADDED Requirements

### Requirement: Ordem das regras oficiais
A simulação de um turno SHALL seguir as etapas do modo standard das regras oficiais (https://github.com/BattlesnakeOfficial/rules, `standard.go`), nesta ordem:
1. **Movimento**: cada cobra viva ganha uma nova cabeça na direção dada e perde o último segmento.
2. **Fome**: cada cobra viva perde 1 de vida.
3. **Hazard**: se a nova cabeça está num hazard e a casa não tem comida, a cobra perde o dano de hazard uma vez para cada ocorrência da casa na lista de hazards. A vida não fica abaixo de 0, e a cobra que chega a 0 aqui é eliminada.
4. **Alimentação**: cada comida que está sob a cabeça de alguma cobra viva sai do tabuleiro. Toda cobra viva com a cabeça nela volta a 100 de vida e cresce: o último segmento é repetido.
5. **Eliminação**, em duas fases:
   - primeiro saem as cobras com vida 0 ou com a cabeça fora do tabuleiro;
   - depois, entre as que sobraram, são marcadas ao mesmo tempo as que colidiram com o próprio corpo, com o corpo de outra cobra (qualquer segmento menos a cabeça) ou que perderam um cabeça a cabeça. Uma cobra perde o cabeça a cabeça quando a cabeça dela está na mesma casa da cabeça de outra e o tamanho dela é menor ou igual ao da outra.

As colisões SHALL ser verificadas com os corpos já depois da alimentação, e só contra cobras não eliminadas na primeira fase. A simulação não SHALL gerar comida nova.

#### Scenario: Movimento
- **WHEN** uma cobra com o corpo [(1,1),(1,0),(0,0)] anda `up` num tabuleiro sem comida
- **THEN** o corpo passa a ser [(1,2),(1,1),(1,0)]

#### Scenario: Perda de vida
- **WHEN** uma cobra com vida 50 anda para uma casa sem comida e sem hazard
- **THEN** a vida passa a ser 49

#### Scenario: Alimentação e crescimento
- **WHEN** uma cobra com o corpo [(1,1),(1,0),(0,0)] e vida 50 anda `up` e há comida em (1,2)
- **THEN** o corpo passa a ser [(1,2),(1,1),(1,0),(1,0)], a vida é 100 e (1,2) não tem mais comida

#### Scenario: Dano de hazard
- **WHEN** o dano de hazard é 14, uma cobra com vida 50 anda para um hazard sem comida
- **THEN** a vida passa a ser 35

#### Scenario: Hazards empilhados
- **WHEN** o dano de hazard é 7, a casa de destino aparece duas vezes na lista de hazards e a cobra tem vida 50
- **THEN** a vida passa a ser 35

#### Scenario: Comida no hazard
- **WHEN** o dano de hazard é 14 e uma cobra com vida 5 anda para um hazard que tem comida
- **THEN** a cobra não é eliminada e a vida passa a ser 100

#### Scenario: Fora do tabuleiro
- **WHEN** uma cobra com a cabeça em (0,1) anda `left`
- **THEN** a cobra é eliminada

#### Scenario: Colisão com corpo
- **WHEN** a cobra A anda para uma casa ocupada por um segmento da cobra B que não é a cauda que sai do lugar
- **THEN** A é eliminada e B continua viva

#### Scenario: Cauda que sai do lugar não mata
- **WHEN** a cobra A anda para a casa da cauda da cobra B, B não come neste turno e a cauda de B não está empilhada
- **THEN** as duas continuam vivas

#### Scenario: Cabeça a cabeça com a menor morrendo
- **WHEN** a cobra A, de tamanho 4, e a cobra B, de tamanho 3, andam para a mesma casa
- **THEN** B é eliminada e A continua viva

#### Scenario: Cabeça a cabeça entre iguais
- **WHEN** duas cobras de tamanho 3 andam para a mesma casa
- **THEN** as duas são eliminadas

#### Scenario: Morte por fome
- **WHEN** uma cobra com vida 1 anda para uma casa sem comida
- **THEN** a cobra é eliminada

#### Scenario: Comida salva da fome
- **WHEN** uma cobra com vida 1 anda para uma casa com comida
- **THEN** a cobra continua viva com vida 100

#### Scenario: Corpo de cobra morta de fome não mata
- **WHEN** a cobra A, com vida 1, anda para uma casa sem comida, e no mesmo turno a cobra B anda para uma casa ocupada por um segmento do corpo de A
- **THEN** A é eliminada e B continua viva

### Requirement: Simulação sem efeito colateral
A simulação SHALL receber um estado e um movimento por cobra viva e devolver um estado novo. O estado recebido não SHALL ser alterado. Cobras eliminadas não SHALL receber movimento e não SHALL mudar.

#### Scenario: Estado original intacto
- **WHEN** um turno é simulado a partir de um estado
- **THEN** o corpo, a vida e a comida do estado original continuam iguais aos de antes da simulação
