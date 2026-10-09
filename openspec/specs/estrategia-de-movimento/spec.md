# estrategia-de-movimento Specification

## Purpose

Define como a cobra escolhe o movimento a cada turno do `/move`: quais direções são seguras, quando ela vai atrás de comida, como maximiza o espaço livre e como desempata, de forma determinística sempre que existir ao menos uma direção segura.

Convenções usadas em todos os requisitos: a origem (0,0) fica no canto inferior esquerdo e `up` é y+1; o primeiro segmento do corpo é a cabeça e o último é a cauda; a lista de cobras do tabuleiro inclui a própria cobra, e as adversárias são as de id diferente; a ordem canônica dos movimentos é `up, down, left, right`. Salvo indicação contrária, o tabuleiro é 11x11.

## Requirements

### Requirement: Resposta sempre válida
A cobra SHALL responder a todo `/move` com exatamente uma das direções `up`, `down`, `left` ou `right`, sem lançar erro. Quando nenhuma direção for segura, a cobra SHALL sortear uma das quatro direções (comportamento do template, mantido).

#### Scenario: Sem nenhuma direção segura
- **WHEN** a cabeça está em (0,0) e as quatro direções estão bloqueadas por parede ou corpo
- **THEN** a resposta é uma das quatro direções e nenhum erro é lançado

### Requirement: Não voltar pelo pescoço
A cobra SHALL tratar como insegura a direção que leva ao segundo segmento do próprio corpo, inclusive quando esse segmento também é a cauda (cobra de tamanho 2).

#### Scenario: Cobra de tamanho 2
- **WHEN** o corpo é [(5,5),(5,4)]
- **THEN** a resposta nunca é `down`, em 50 execuções seguidas

### Requirement: Não sair do tabuleiro
A cobra SHALL tratar como insegura toda direção cuja casa de destino fique fora do tabuleiro.

#### Scenario: Canto inferior esquerdo
- **WHEN** a cabeça está em (0,0) e o pescoço em (1,0)
- **THEN** a resposta é `up`

### Requirement: Própria cauda é uma casa livre
A cobra SHALL tratar a casa da própria cauda como livre quando a cauda sai do lugar neste turno, ou seja, quando o último segmento do corpo é diferente do penúltimo. Logo depois de comer, os dois últimos segmentos ocupam a mesma casa e a cauda não sai do lugar. Nesse caso a casa da cauda SHALL ser insegura. Os demais segmentos do próprio corpo SHALL continuar inseguros. A regra do pescoço prevalece sobre esta.

#### Scenario: Única saída é a própria cauda
- **WHEN** o corpo é [(5,10),(5,9),(4,9),(4,10)] e uma adversária ocupa [(8,10),(7,10),(6,10)]
- **THEN** a resposta é `left`

#### Scenario: Cauda que sai do lugar
- **WHEN** o corpo é [(5,10),(5,9),(4,9),(4,10)], não há adversárias nem comida e o turno é 1
- **THEN** `left` e `right` são candidatas, empatam na decisão e a resposta é `left`

#### Scenario: Cauda empilhada depois de comer
- **WHEN** o corpo é [(5,10),(5,9),(4,9),(4,10),(4,10)], não há adversárias nem comida e o turno é 1
- **THEN** `left` não é candidata e a resposta é `right`

### Requirement: Não entrar em adversárias
A cobra SHALL tratar como insegura toda direção cuja casa de destino esteja ocupada por qualquer segmento de uma adversária, cauda incluída.

#### Scenario: Adversária ao lado da cabeça
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** a resposta é `right`

### Requirement: Evitar cabeça a cabeça desfavorável
A cobra SHALL marcar como arriscada, sem eliminar, toda candidata cuja casa de destino a cabeça de uma adversária de tamanho maior ou igual alcança no próximo turno. Uma casa alcançável apenas por adversárias menores SHALL continuar não arriscada. A decisão SHALL preferir as candidatas não arriscadas conforme as camadas de segurança de `decisao-de-movimento`.

#### Scenario: Rival maior
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(3,10),(2,10),(1,10),(0,10)]
- **THEN** `left` é candidata arriscada e a resposta é `right`

#### Scenario: Rival de mesmo tamanho
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(3,10),(2,10),(1,10)]
- **THEN** `left` é candidata arriscada e a resposta é `right`

#### Scenario: Rival menor
- **WHEN** o corpo é [(5,10),(5,9),(5,8),(5,7)] e uma adversária ocupa [(3,10),(2,10),(1,10)]
- **THEN** a casa (4,10) não é considerada uma derrota em cabeça a cabeça

### Requirement: Decisão determinística e rápida
Com ao menos uma candidata, a cobra SHALL devolver sempre a mesma resposta para o mesmo estado de jogo, sem nenhuma aleatoriedade. O cálculo completo de uma jogada (candidatas, contexto, as características de todas as candidatas e a decisão) SHALL levar menos de 50 ms num tabuleiro 19x19 com 4 cobras de tamanho 15.

#### Scenario: Mesmo estado, mesma resposta
- **WHEN** o mesmo estado com ao menos uma candidata é enviado várias vezes
- **THEN** todas as respostas são iguais

#### Scenario: Tabuleiro grande
- **WHEN** o tabuleiro é 19x19 com 4 cobras de tamanho 15 e algumas comidas
- **THEN** a melhor de várias medições da jogada completa fica abaixo de 50 ms

### Requirement: Escolha em três etapas
A cobra SHALL decidir cada jogada em três etapas, cada uma testável sozinha:
1. **Candidatas**: as direções que não levam a morte certa. Ficam fora o pescoço, as paredes, o próprio corpo e o corpo das adversárias.
2. **Características**: uma medição por candidata (ver a capability `caracteristicas-de-movimento`). Essa etapa não escolhe nada.
3. **Decisão**: a escolha de uma direção a partir das características e do contexto da jogada (ver a capability `decisao-de-movimento`).

O contexto da jogada SHALL conter a vida, o tamanho, o turno e se a cobra está com fome. Sem nenhuma candidata, vale o requisito "Resposta sempre válida".

#### Scenario: Única candidata
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** `right` é a única candidata e é a resposta

#### Scenario: Evita o beco
- **WHEN** o corpo é [(5,9),(6,9),(7,9),(7,10),(8,10)], uma adversária que acabou de comer ocupa [(0,5),(0,6),(0,7),(0,8),(0,9),(0,10),(1,10),(2,10),(3,10),(4,10),(4,10)] e não há comida
- **THEN** `up` leva a uma área de 2 casas, menor que o tamanho da cobra, e a resposta é `down`

### Requirement: Política de fome
A cobra SHALL estar com fome quando ao menos uma das condições abaixo for verdadeira. Os valores entre parênteses são os iniciais das constantes de ajuste.
- **Sobrevivência**: a vida é menor que a distância, em passos, do caminho mais curto até a comida alvo mais a margem de vida (15). Sem caminho até nenhuma comida (inclusive sem comida no tabuleiro), a condição é vida menor que o piso sem caminho (50).
- **Disputa de tamanho**: o tamanho é menor que o maior tamanho entre as adversárias vivas mais a vantagem de tamanho (2). Sem adversárias, a condição é falsa.
- **Taxa de crescimento**: o tamanho é menor que o tamanho inicial (3) mais a divisão inteira do turno pelo intervalo de alimentação (8).

#### Scenario: Fome por disputa de tamanho
- **WHEN** a vida é 100, o corpo é [(5,5),(5,4),(5,3)], uma adversária de tamanho 6 ocupa [(10,0),(10,1),(10,2),(10,3),(10,4),(10,5)] e há comida em (2,5)
- **THEN** a cobra está com fome e a resposta é `left`, o primeiro passo até a comida

#### Scenario: Fome por taxa de crescimento
- **WHEN** a vida é 100, não há adversárias, o turno é 40 e o corpo é [(5,5),(5,4),(5,3)]
- **THEN** a cobra está com fome

#### Scenario: Sem fome
- **WHEN** a vida é 100, não há adversárias, o turno é 1 e o corpo é [(5,5),(5,4),(5,3)]
- **THEN** a cobra não está com fome

#### Scenario: Fome por sobrevivência sendo a maior cobra
- **WHEN** a vida é 19, o corpo é [(5,5),(5,4),(5,3),(5,2),(5,1),(5,0),(6,0),(7,0)], uma adversária ocupa [(10,10),(10,9),(10,8)], o turno é 1 e há comida em (5,10), a 5 passos
- **THEN** a cobra está com fome (19 < 5 + 15)

#### Scenario: Limite da sobrevivência
- **WHEN** o mesmo estado do cenário anterior tem vida 20
- **THEN** a cobra não está com fome (20 não é menor que 5 + 15)

#### Scenario: Com fome vai para a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 10, não há adversárias e há comida em (2,5)
- **THEN** a resposta é `left`

#### Scenario: Sem fome ignora a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 100, não há adversárias, o turno é 1 e há comida em (2,5)
- **THEN** a resposta é `up`

### Requirement: Comida alvo
A cobra SHALL escolher uma única comida alvo por jogada. Para isso, calcula o caminho mais curto da cabeça até cada comida, desviando dos obstáculos (ver "Obstáculos" em `caracteristicas-de-movimento`) e das casas vizinhas às cabeças de adversárias estritamente maiores. Uma comida sem caminho não é alcançável.

Entre as alcançáveis, a comida é "da cobra" quando a distância do caminho for estritamente menor que a distância de Manhattan entre a comida e a cabeça de cada adversária de tamanho maior ou igual. A comida alvo SHALL ser a mais próxima entre as que são da cobra. Se nenhuma for, SHALL ser a mais próxima entre as alcançáveis. Em empate de distância, vence a primeira na lista recebida. Sem comida alcançável, não há comida alvo.

#### Scenario: Comida contestada
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], uma adversária de tamanho 5 ocupa [(10,5),(10,4),(10,3),(10,2),(10,1)] e as comidas são [(8,5),(1,5)]
- **THEN** a comida alvo é (1,5), porque (8,5) fica a 3 passos da cobra e a 2 da rival, e a resposta é `left`

#### Scenario: Caminho contorna obstáculo
- **WHEN** o tabuleiro é 5x5, as casas {(1,0),(1,1),(1,2),(1,3)} estão bloqueadas e o caminho vai de (0,0) até (2,0)
- **THEN** o caminho tem 11 casas, começa em (0,0) e termina em (2,0)

#### Scenario: Sem caminho possível
- **WHEN** o tabuleiro é 3x3, as casas {(1,0),(1,1),(0,1)} estão bloqueadas e o caminho vai de (0,0) até (2,2)
- **THEN** o resultado é um caminho vazio

### Requirement: Constantes de ajuste centralizadas
Todos os pesos, margens, limites e intervalos usados pelas características, pela política de fome e pela decisão SHALL vir de um único módulo de configuração. Os valores iniciais são:
- margem de vida: 15
- piso de vida sem caminho: 50
- vantagem de tamanho: 2
- tamanho inicial: 3
- intervalo de alimentação: 8
- pesos: território 1.0, comida 40, rival encurralada 60, chance de matar 50, caça 10, perigo 25, centro 1

#### Scenario: Peso alterado muda a escolha
- **WHEN** o peso da rival encurralada é trocado por 0 no módulo de configuração e o cenário "Encurrala a rival menor" de `decisao-de-movimento` é avaliado
- **THEN** a resposta deixa de ser `up` e passa a ser `right`
