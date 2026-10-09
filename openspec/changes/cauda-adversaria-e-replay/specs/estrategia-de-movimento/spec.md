## ADDED Requirements

### Requirement: Filtro e simulação com a mesma regra de ocupação
Para a própria cobra, as candidatas do filtro, sem contar a regra "Não morrer de fome nem em hazard", SHALL ser exatamente as direções que não são morte certa no requisito "Candidatas dentro da busca" de `busca-no-duelo`, na mesma ordem canônica, sempre que o filtro deixar ao menos uma. Quando o filtro não deixa nenhuma, a simulação SHALL usar a primeira direção da ordem canônica, como já diz aquele requisito. Nos dois casos, uma casa conta como ocupada quando guarda um segmento de cobra viva que continua no lugar depois do turno, qualquer que seja o movimento das cobras: todos os segmentos de cada cobra menos o último. Uma cauda empilhada continua ocupada, porque o penúltimo segmento está na mesma casa.

#### Scenario: Tabuleiros aleatórios
- **WHEN** tabuleiros 11x11 são gerados com semente fixa, com 1 a 4 cobras de corpos contínuos, algumas com a cauda empilhada e algumas com o corpo todo empilhado (começo de partida), vida 100 para todas e sem hazards
- **THEN** em todos eles, as candidatas do filtro são iguais às direções que não são morte certa na simulação; quando o filtro não deixa nenhuma, a simulação usa `up`

## MODIFIED Requirements

### Requirement: Própria cauda é uma casa livre
A cobra SHALL tratar a casa da própria cauda como livre quando a cauda sai do lugar neste turno, ou seja, quando o último segmento do corpo é diferente do penúltimo. Logo depois de comer, os dois últimos segmentos ocupam a mesma casa e a cauda não sai do lugar. Nesse caso a casa da cauda SHALL ser insegura. Os demais segmentos do próprio corpo SHALL continuar inseguros. A regra do pescoço prevalece sobre esta.

#### Scenario: Única saída é a própria cauda
- **WHEN** o corpo é [(5,10),(5,9),(4,9),(4,10)] e uma adversária ocupa [(8,10),(7,10),(6,10),(6,9)]
- **THEN** a resposta é `left`

#### Scenario: Cauda que sai do lugar
- **WHEN** o corpo é [(5,10),(5,9),(4,9),(4,10)], não há adversárias nem comida e o turno é 1
- **THEN** `left` e `right` são candidatas, empatam na decisão e a resposta é `left`

#### Scenario: Cauda empilhada depois de comer
- **WHEN** o corpo é [(5,10),(5,9),(4,9),(4,10),(4,10)], não há adversárias nem comida e o turno é 1
- **THEN** `left` não é candidata e a resposta é `right`

### Requirement: Não entrar em adversárias
A cobra SHALL tratar como insegura toda direção cuja casa de destino esteja ocupada por um segmento de uma adversária que continua no lugar depois do turno: qualquer segmento menos a cauda que sai do lugar. A cauda de uma adversária sai do lugar quando o último segmento do corpo dela é diferente do penúltimo, mesmo que ela coma neste turno, porque pelas regras oficiais o movimento vem antes da alimentação. Essa casa SHALL ser candidata. A cauda empilhada de uma adversária SHALL continuar insegura. Uma direção para a cauda de uma adversária continua sujeita às medições de cabeça a cabeça: é arriscada quando a cabeça da adversária alcança a casa e ela tem tamanho maior ou igual (ver "Evitar cabeça a cabeça desfavorável"), e é uma chance de abate quando ela é menor (ver `caracteristicas-de-movimento`).

#### Scenario: Adversária ao lado da cabeça
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** a resposta é `right`

#### Scenario: Cauda de adversária menor que sai do lugar
- **WHEN** o turno é 74, o corpo é [(2,4),(2,3),(2,2),(1,2),(0,2),(0,3),(0,4),(0,5),(1,5),(2,5),(3,5)] com vida 96, uma adversária ocupa [(4,4),(4,3),(3,3),(3,4)] com vida 40 e há comida em (1,9), (10,4) e (7,2)
- **THEN** as candidatas são `left` e `right`, `right` é uma chance de abate e não é arriscada, e a resposta é `right`

#### Scenario: Cauda empilhada de adversária
- **WHEN** o corpo é [(5,5),(5,4),(5,3)] e uma adversária que acabou de comer ocupa [(8,5),(7,5),(6,5),(6,5)]
- **THEN** `right` não é candidata, e as candidatas são `up` e `left`

#### Scenario: Cauda de adversária maior com a cabeça vizinha
- **WHEN** o corpo é [(5,5),(5,4),(5,3)] e uma adversária de tamanho 4 ocupa [(6,6),(7,6),(7,5),(6,5)]
- **THEN** `right`, para a cauda dela em (6,5), é candidata e arriscada, e a resposta é `left`, a única candidata não arriscada
