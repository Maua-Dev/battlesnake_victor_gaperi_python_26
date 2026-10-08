## Purpose

Define como a cobra escolhe o movimento a cada turno do `/move`: quais direções são seguras, quando ela vai atrás de comida, como maximiza o espaço livre e como desempata, de forma determinística sempre que existir ao menos uma direção segura.

Convenções usadas em todos os requisitos: a origem (0,0) fica no canto inferior esquerdo e `up` é y+1; o primeiro segmento do corpo é a cabeça e o último é a cauda; a lista de cobras do tabuleiro inclui a própria cobra, e as adversárias são as de id diferente; a ordem canônica dos movimentos é `up, down, left, right`. Salvo indicação contrária, o tabuleiro é 11x11.

## ADDED Requirements

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
A cobra SHALL tratar a casa da própria cauda como livre, porque a cauda sai do lugar no mesmo turno. Os demais segmentos do próprio corpo SHALL continuar inseguros. A regra do pescoço prevalece sobre esta.

#### Scenario: Única saída é a própria cauda
- **WHEN** o corpo é [(5,10),(5,9),(4,9),(4,10)] e uma adversária ocupa [(8,10),(7,10),(6,10)]
- **THEN** a resposta é `left`

### Requirement: Não entrar em adversárias
A cobra SHALL tratar como insegura toda direção cuja casa de destino esteja ocupada por qualquer segmento de uma adversária, cauda incluída.

#### Scenario: Adversária ao lado da cabeça
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** a resposta é `right`

### Requirement: Evitar cabeça a cabeça desfavorável
A cobra SHALL tratar como insegura toda casa que a cabeça de uma adversária de tamanho maior ou igual ao seu alcança no próximo turno. Uma casa alcançável apenas por adversárias menores SHALL continuar segura.

#### Scenario: Rival maior
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(3,10),(2,10),(1,10),(0,10)]
- **THEN** a resposta é `right`

#### Scenario: Rival de mesmo tamanho
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(3,10),(2,10),(1,10)]
- **THEN** a resposta é `right`

#### Scenario: Rival menor
- **WHEN** o corpo é [(5,10),(5,9),(5,8),(5,7)] e uma adversária ocupa [(3,10),(2,10),(1,10)]
- **THEN** a casa (4,10) não é considerada uma derrota em cabeça a cabeça

### Requirement: Com fome, ir até a comida mais próxima
A cobra SHALL considerar-se com fome quando a vida for menor que 80. Com fome e com comida no tabuleiro, ela SHALL escolher a comida de menor distância de Manhattan até a cabeça (em empate, a primeira da lista recebida), calcular o caminho mais curto até ela desviando dos corpos de todas as cobras (exceto a própria cauda) e responder com a direção do primeiro passo desse caminho, desde que essa direção seja segura. Se não houver caminho, ou se o primeiro passo não for seguro, ela SHALL decidir pela regra de espaço.

#### Scenario: Com fome vai para a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 50 e há comida em (2,5)
- **THEN** a resposta é `left`

#### Scenario: Sem fome ignora a comida
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 100 e há comida em (2,5)
- **THEN** a resposta é `up`

#### Scenario: Caminho contorna obstáculo
- **WHEN** o tabuleiro é 5x5, as casas {(1,0),(1,1),(1,2),(1,3)} estão bloqueadas e o caminho vai de (0,0) até (2,0)
- **THEN** o caminho tem 11 casas, começa em (0,0) e termina em (2,0)

#### Scenario: Sem caminho possível
- **WHEN** o tabuleiro é 3x3, as casas {(1,0),(1,1),(0,1)} estão bloqueadas e o caminho vai de (0,0) até (2,2)
- **THEN** o resultado é um caminho vazio

### Requirement: Sem comida a seguir, maximizar o espaço alcançável
Quando a regra da comida não decidir o movimento, a cobra SHALL calcular, para cada direção segura, a quantidade de casas alcançáveis a partir da nova posição da cabeça. Contam como bloqueadas as casas ocupadas por qualquer cobra (exceto a própria cauda) e as casas vizinhas às cabeças de adversárias estritamente maiores. A própria casa de destino SHALL contar como alcançável. A cobra SHALL escolher a direção com a maior área; com fome e com comida no tabuleiro, a área empatada SHALL ser desempatada pela menor distância de Manhattan entre a nova posição e a comida mais próxima dela; persistindo o empate, vence a primeira direção na ordem canônica.

#### Scenario: Evita o beco
- **WHEN** o corpo é [(5,9),(6,9),(7,9),(7,10),(8,10)] e uma adversária ocupa [(0,5),(0,6),(0,7),(0,8),(0,9),(0,10),(1,10),(2,10),(3,10),(4,10)]
- **THEN** a resposta é `down`

#### Scenario: Área num tabuleiro vazio
- **WHEN** o tabuleiro é 5x5, nada está bloqueado e a contagem começa em (2,2)
- **THEN** a área é 25

#### Scenario: Área limitada por um muro
- **WHEN** o tabuleiro é 5x5, toda a coluna x=2 está bloqueada e a contagem começa em (0,0)
- **THEN** a área é 10

#### Scenario: Início bloqueado ou fora do tabuleiro
- **WHEN** a contagem começa numa casa bloqueada ou fora do tabuleiro
- **THEN** a área é 0

### Requirement: Decisão determinística e rápida
Com ao menos uma direção segura, a cobra SHALL devolver sempre a mesma resposta para o mesmo estado de jogo. Uma jogada SHALL ser decidida em menos de 1 ms num tabuleiro 19x19 com 4 cobras.

#### Scenario: Mesmo estado, mesma resposta
- **WHEN** o mesmo estado com ao menos uma direção segura é enviado várias vezes
- **THEN** todas as respostas são iguais

#### Scenario: Tabuleiro grande
- **WHEN** o tabuleiro é 19x19 com 4 cobras
- **THEN** a decisão leva menos de 1 ms
