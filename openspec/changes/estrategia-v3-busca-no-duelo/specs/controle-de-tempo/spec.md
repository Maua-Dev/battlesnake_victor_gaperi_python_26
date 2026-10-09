## Purpose

Garante que toda jogada responde antes do prazo. Define quando o prazo começa a contar, como o orçamento é calculado, como a busca usa o tempo que sobra e qual resposta vale quando o tempo acaba.

## ADDED Requirements

### Requirement: Prazo a partir da chegada da requisição
O prazo de uma jogada SHALL começar a contar no instante em que a requisição do `/move` chega à aplicação, antes da validação do payload, porque a validação e a conversão também gastam tempo. O prazo SHALL ser esse instante mais o orçamento. Quando a lógica é chamada sem esse instante (por exemplo, direto num teste), o prazo SHALL começar no início da chamada. Toda medição de tempo SHALL usar um relógio monotônico (`time.perf_counter`), que os testes podem trocar por um relógio falso.

#### Scenario: Instante marcado antes da validação
- **WHEN** uma requisição do `/move` chega pelo HTTP
- **THEN** o instante usado como início do prazo é lido antes de o payload ser validado

#### Scenario: Chamada direta
- **WHEN** a lógica da jogada é chamada diretamente, sem o instante de chegada
- **THEN** o prazo começa no início da chamada

#### Scenario: Relógio falso
- **WHEN** um teste troca o relógio por um que devolve valores fixos
- **THEN** toda leitura de tempo da jogada usa esse relógio

### Requirement: Orçamento
O orçamento, em milissegundos, SHALL ser `min(SEARCH_BUDGET_FRACTION × game.timeout, SEARCH_BUDGET_MAX_MS)`. Os valores padrão são `SEARCH_BUDGET_FRACTION` = 0,4 e `SEARCH_BUDGET_MAX_MS` = 120. `SEARCH_BUDGET_MAX_MS` SHALL poder vir da variável de ambiente de mesmo nome. Quando a variável está ausente, vazia, não é um inteiro ou não é positiva, vale o padrão, sem erro.

#### Scenario: Timeout padrão do motor
- **WHEN** `game.timeout` é 500 e a variável de ambiente não está definida
- **THEN** o orçamento é 120 ms

#### Scenario: Timeout curto
- **WHEN** `game.timeout` é 200 e `SEARCH_BUDGET_MAX_MS` é 120
- **THEN** o orçamento é 80 ms

#### Scenario: Variável de ambiente
- **WHEN** a variável de ambiente `SEARCH_BUDGET_MAX_MS` é `"90"`
- **THEN** `SEARCH_BUDGET_MAX_MS` vale 90

#### Scenario: Variável inválida
- **WHEN** a variável de ambiente `SEARCH_BUDGET_MAX_MS` é `"abc"` ou `"-5"`
- **THEN** `SEARCH_BUDGET_MAX_MS` vale 120 e nenhum erro é lançado

### Requirement: Resposta pronta antes da busca
A escolha heurística (filtro, medições e decisão) SHALL ficar pronta antes de qualquer busca. Só depois, se a busca se aplica (ver `busca-no-duelo`) e o prazo ainda não passou, a busca SHALL rodar por aprofundamento iterativo: profundidade 1, 2, … até `MAX_SEARCH_DEPTH` (20). O prazo SHALL ser conferido dentro da busca, a cada nó. Quando o prazo passa, a profundidade em andamento SHALL ser descartada. A resposta SHALL ser a resposta da busca na última profundidade completa (a escolha heurística ou, se ela foi vetada, a que a substitui; ver "Veto da escolha heurística" em `busca-no-duelo`) ou, se nenhuma profundidade terminou, a escolha heurística. O aprofundamento SHALL parar antes de `MAX_SEARCH_DEPTH` quando uma profundidade terminar sem nenhuma folha cortada pelo limite de profundidade, porque a árvore foi resolvida até o fim.

#### Scenario: Prazo estoura antes da profundidade 1 terminar
- **WHEN** num duelo o relógio falso passa do prazo durante a profundidade 1
- **THEN** a resposta é a escolha heurística

#### Scenario: Prazo estoura no meio da profundidade 3
- **WHEN** num duelo o relógio falso passa do prazo depois de a profundidade 2 terminar e antes de a profundidade 3 terminar
- **THEN** a resposta é a resposta da busca na profundidade 2

#### Scenario: Prazo já vencido ao fim da heurística
- **WHEN** num duelo o prazo já passou quando a escolha heurística fica pronta
- **THEN** a busca não roda e a resposta é a escolha heurística

### Requirement: Medições caras respeitam o prazo
A sobrevivência por DFS (ver `caracteristicas-de-movimento`) SHALL conferir o prazo enquanto roda. Quando o prazo passa, ela SHALL parar e devolver a profundidade alcançada até ali, em vez de estourar o tempo.

#### Scenario: DFS cortada pelo prazo
- **WHEN** o relógio falso passa do prazo durante a DFS de sobrevivência de uma candidata
- **THEN** a DFS para, devolve a profundidade alcançada até ali e a jogada segue normalmente

### Requirement: Determinismo com o mesmo relógio
Para a mesma entrada e a mesma sequência de leituras do relógio, a resposta SHALL ser sempre a mesma. Em particular, com um relógio que nunca passa do prazo, a mesma entrada SHALL dar sempre a mesma resposta.

#### Scenario: Relógio parado
- **WHEN** o mesmo duelo é enviado várias vezes com um relógio que nunca passa do prazo e `MAX_SEARCH_DEPTH` 3
- **THEN** todas as respostas são iguais

### Requirement: Jogada dentro do orçamento
Medida localmente com o relógio real, a jogada completa (filtro, heurística e busca) de um duelo 11x11 de meio de jogo SHALL terminar em no máximo o orçamento mais 10 ms de folga, que cobre a última conferência do prazo e a volta da busca.

#### Scenario: Duelo de meio de jogo
- **WHEN** um duelo 11x11 de meio de jogo é avaliado com o orçamento padrão de 120 ms
- **THEN** a jogada completa leva no máximo 130 ms
