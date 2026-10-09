## ADDED Requirements

### Requirement: Não morrer de fome nem em hazard
A cobra SHALL tratar como insegura toda direção cuja casa de destino não tem comida e em que `vida - 1 - dano de hazard × ocorrências da casa na lista de hazards` fica menor ou igual a 0. Numa casa que não é hazard, as ocorrências são 0. Uma casa com comida nunca é eliminada por esta regra. Isso segue a ordem das regras oficiais do modo standard: movimento, perda de 1 de vida, dano de hazard (que não se aplica se a casa tiver comida), alimentação e eliminações. O dano de hazard vem das regras da partida (ver `representacao-do-tabuleiro`).

#### Scenario: Vida 1 só sobrevive comendo
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 1, não há adversárias e há comida só em (4,5)
- **THEN** `left` é a única candidata e a resposta é `left`

#### Scenario: Hazard que zera a vida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 10, o dano de hazard é 14 e há hazards em (5,6) e (4,5)
- **THEN** `up` e `left` não são candidatas e a resposta é `right`

#### Scenario: Hazards empilhados
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 15, o dano de hazard é 7 e (5,6) aparece duas vezes na lista de hazards
- **THEN** `up` não é candidata (15 - 1 - 14 = 0); com (5,6) uma única vez na lista, `up` é candidata

#### Scenario: Comida no hazard
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 5, o dano de hazard é 14 e (5,6) é hazard e tem comida
- **THEN** `up` é candidata

## MODIFIED Requirements

### Requirement: Decisão determinística e rápida
Com ao menos uma candidata, a cobra SHALL devolver sempre a mesma resposta para o mesmo estado de jogo e a mesma sequência de leituras do relógio (ver `controle-de-tempo`), sem nenhuma aleatoriedade. Enquanto o prazo não passa, a escolha heurística não depende do relógio. A fase heurística de uma jogada (candidatas, contexto, as características de todas as candidatas e a decisão, sem a busca do duelo) SHALL levar menos de 50 ms num tabuleiro 19x19 com 4 cobras de tamanho 15 e menos de 10 ms num tabuleiro 11x11 com 8 cobras, medida localmente.

#### Scenario: Mesmo estado, mesma resposta
- **WHEN** o mesmo estado com ao menos uma candidata é enviado várias vezes
- **THEN** todas as respostas são iguais

#### Scenario: Tabuleiro grande
- **WHEN** o tabuleiro é 19x19 com 4 cobras de tamanho 15 e algumas comidas
- **THEN** a melhor de várias medições da jogada completa fica abaixo de 50 ms

#### Scenario: Oito cobras
- **WHEN** o tabuleiro é 11x11 com 8 cobras de tamanho 6 e algumas comidas
- **THEN** a melhor de várias medições da fase heurística fica abaixo de 10 ms

### Requirement: Escolha em três etapas
A cobra SHALL decidir cada jogada em três etapas, cada uma testável sozinha:
1. **Candidatas**: as direções que não levam a morte certa. Ficam fora o pescoço, as paredes, o próprio corpo, o corpo das adversárias e as casas em que a cobra morreria de fome ou por hazard (ver "Não morrer de fome nem em hazard").
2. **Características**: uma medição por candidata (ver a capability `caracteristicas-de-movimento`). Essa etapa não escolhe nada.
3. **Decisão**: a escolha de uma direção a partir das características e do contexto da jogada (ver a capability `decisao-de-movimento`). É a escolha heurística.

O contexto da jogada SHALL conter a vida, o tamanho, o turno e se a cobra está com fome. Depois da decisão, num duelo, a busca (ver `busca-no-duelo`) SHALL poder trocar a escolha heurística quando ela perde ou empata dentro do horizonte da busca, só dentro do prazo (ver `controle-de-tempo`). Sem nenhuma candidata, vale o requisito "Resposta sempre válida".

#### Scenario: Única candidata
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** `right` é a única candidata e é a resposta

#### Scenario: Evita o beco
- **WHEN** o corpo é [(2,10),(3,10),(4,10),(5,10)], uma adversária ocupa [(5,8),(4,8),(3,8),(2,8),(1,8),(1,9),(0,9),(0,8),(0,7),(0,6)] e não há comida
- **THEN** `left` leva a uma área de 2 casas, cercada por segmentos que só liberam depois de a cobra chegar, e a resposta é `down`

### Requirement: Política de fome
A cobra SHALL estar com fome quando ao menos uma das condições abaixo for verdadeira. Os valores entre parênteses são os iniciais das constantes de ajuste.
- **Sobrevivência**: a vida é menor que o custo de vida do caminho até a comida alvo mais a margem de vida (15). O custo de vida é a soma, para cada passo do caminho, de 1 mais o dano de hazard vezes as ocorrências da casa na lista de hazards, quando a casa é hazard e não tem comida. Sem hazards, o custo é a distância em passos. Sem caminho até nenhuma comida (inclusive sem comida no tabuleiro), a condição é vida menor que o piso sem caminho (50).
- **Disputa de tamanho**: o tamanho é menor que o maior tamanho entre as adversárias vivas mais a vantagem de tamanho (2). Sem adversárias, a condição é falsa.
- **Taxa de crescimento**: o tamanho é menor que o tamanho inicial (3) mais a divisão inteira do turno pelo intervalo de alimentação (8).

#### Scenario: Fome por disputa de tamanho
- **WHEN** a vida é 100, o corpo é [(5,5),(5,4),(5,3)], uma adversária de tamanho 6 ocupa [(10,0),(10,1),(10,2),(10,3),(10,4),(10,5)] e há comida em (2,5)
- **THEN** a cobra está com fome e a escolha heurística é `left`, o primeiro passo até a comida

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

#### Scenario: Hazard no caminho até a comida
- **WHEN** a vida é 30, o corpo é [(5,5),(5,4),(5,3)], não há adversárias, o turno é 1, há comida em (5,8), o dano de hazard é 14 e (5,6) é hazard
- **THEN** a cobra está com fome (30 < 3 + 14 + 15); sem o hazard, não estaria (30 não é menor que 3 + 15)

#### Scenario: Com fome vai para a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 10, não há adversárias e há comida em (2,5)
- **THEN** a resposta é `left`

#### Scenario: Sem fome ignora a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 100, não há adversárias, o turno é 1 e há comida em (2,5)
- **THEN** a resposta é `up`

### Requirement: Comida alvo
A cobra SHALL escolher uma única comida alvo por jogada. Para isso, calcula o caminho mais curto da cabeça até cada comida pela ocupação temporal (ver "Comida" em `caracteristicas-de-movimento`), desviando também das casas vizinhas às cabeças de adversárias estritamente maiores. Uma comida sem caminho não é alcançável.

Entre as alcançáveis, a comida é "da cobra" quando pertence a ela no território do turno: o território temporal calculado com a cabeça atual de cada cobra viva como semente, todas com distância 0 (ver "Território" em `caracteristicas-de-movimento`). A comida alvo SHALL ser a mais próxima, em passos do caminho, entre as que são da cobra. Se nenhuma for, SHALL ser a mais próxima entre as alcançáveis. Em empate de distância, vence a primeira na lista recebida. Sem comida alcançável, não há comida alvo.

#### Scenario: Comida contestada
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], uma adversária de tamanho 5 ocupa [(10,5),(10,4),(10,3),(10,2),(10,1)] e as comidas são [(8,5),(1,5)]
- **THEN** a comida alvo é (1,5), porque (8,5) fica a 3 passos da cobra e a 2 da rival e é território dela, e a escolha heurística é `left`

#### Scenario: Empate com rival do mesmo tamanho
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], uma adversária de tamanho 3 ocupa [(9,5),(10,5),(10,4)] e as comidas são [(7,5),(2,5)]
- **THEN** (7,5) é disputada e não é da cobra, e a comida alvo é (2,5)

#### Scenario: Caminho contorna obstáculo
- **WHEN** o tabuleiro é 5x5, as casas {(1,0),(1,1),(1,2),(1,3)} estão bloqueadas e o caminho vai de (0,0) até (2,0)
- **THEN** o caminho tem 11 casas, começa em (0,0) e termina em (2,0)

#### Scenario: Sem caminho possível
- **WHEN** o tabuleiro é 3x3, as casas {(1,0),(1,1),(0,1)} estão bloqueadas e o caminho vai de (0,0) até (2,2)
- **THEN** o resultado é um caminho vazio

### Requirement: Constantes de ajuste centralizadas
Todos os pesos, margens, limites, intervalos e orçamentos usados pelas características, pela política de fome, pela decisão, pela busca e pelo controle de tempo SHALL vir de um único módulo de configuração e SHALL ser lidos nele no momento do uso. Os valores iniciais são:
- margem de vida: 15
- piso de vida sem caminho: 50
- vantagem de tamanho: 2
- tamanho inicial: 3
- intervalo de alimentação: 8
- pesos: território 1.0, comida 40, rival encurralada 60, chance de matar 50, caça 10, perigo 25, centro 1, sobrevivência 20, hazard 30, cerco 0.5
- sobrevivência: profundidade máxima 12, limite de 400 nós
- busca: profundidade máxima 20, vitória 1.000.000, empate -500.000 e os pesos da avaliação das folhas
- tempo: fração do timeout 0,4, teto do orçamento 120 ms (ver `controle-de-tempo`)

#### Scenario: Peso alterado muda a escolha
- **WHEN** o peso da rival encurralada é trocado por 0 no módulo de configuração e o cenário "Encurrala a rival menor" de `decisao-de-movimento` é avaliado
- **THEN** a escolha heurística deixa de ser `up` e passa a ser `right`
