## Purpose

Define os logs estruturados que a cobra emite em cada chamada da API, para que só com o CloudWatch Logs Insights seja possível reconstruir uma partida e explicar cada movimento. Em particular, os logs separam timeout ou erro do servidor, emergência sem saída e decisão da própria lógica.

Convenções usadas em todos os requisitos: posições são listas `[x, y]` com origem no canto inferior esquerdo; "a cobra" é a cobra `you` do payload; as direções são `up`, `down`, `left` e `right`, nesta ordem canônica. Salvo indicação contrária, o tabuleiro é 11x11, o turno é 1, o timeout do jogo é 500 e não há comida.

## ADDED Requirements

### Requirement: Uma linha JSON por evento
Cada evento SHALL ser escrito na saída padrão como uma única linha que contém apenas um objeto JSON, sem prefixo de data, nível ou id de requisição. Textos não ASCII SHALL aparecer como caracteres, e não como sequências de escape. Os eventos da cobra não SHALL ser duplicados pelo logger raiz do runtime.

#### Scenario: Toda linha é um objeto JSON
- **WHEN** a cobra atende uma sequência de `/start`, `/move` e `/end`
- **THEN** cada linha emitida é um objeto JSON válido que contém `event` e `ts`

#### Scenario: Sem duplicação
- **WHEN** a cobra emite um evento `move`
- **THEN** exatamente uma linha com `"event":"move"` aparece na saída

### Requirement: Campos comuns
Todo evento SHALL conter:
- `event`: o nome do evento;
- `ts`: o instante em ISO 8601 UTC;
- `game_id`, `turn` e `snake_id`: os valores do payload quando ele foi lido, e `null` quando não foi;
- `aws_request_id`: o id da invocação quando há contexto da Lambda, e `null` quando não há.

Um mesmo campo SHALL ter sempre o mesmo nome e o mesmo tipo em todos os eventos. Números SHALL ser números JSON, nunca strings.

#### Scenario: Campos de jogo num move
- **WHEN** a cobra recebe um `/move` da partida `partida-de-teste`, no turno 7, sendo a cobra `eu`
- **THEN** o evento `move` tem `game_id` igual a `"partida-de-teste"`, `turn` igual ao número 7 e `snake_id` igual a `"eu"`

#### Scenario: Requisição sem payload de jogo
- **WHEN** a cobra recebe um `GET /`
- **THEN** o evento `request` tem `game_id`, `turn` e `snake_id` nulos

#### Scenario: Fora da Lambda
- **WHEN** a requisição não vem de uma invocação da Lambda
- **THEN** `aws_request_id` é nulo

#### Scenario: Dentro da Lambda
- **WHEN** a requisição vem de uma invocação da Lambda com id `abc-123`
- **THEN** todos os eventos dessa requisição têm `aws_request_id` igual a `"abc-123"`

### Requirement: Nível configurável
O nível mínimo dos eventos SHALL vir da variável de ambiente `LOG_LEVEL`, com padrão `INFO`. O evento `error` SHALL ter nível de erro. Os demais eventos SHALL ter nível informativo.

#### Scenario: Nível padrão
- **WHEN** `LOG_LEVEL` não está definida e a cobra atende um `/move`
- **THEN** os eventos `request` e `move` são emitidos

#### Scenario: Só erros
- **WHEN** `LOG_LEVEL` é `ERROR` e a cobra atende um `/move` sem falha
- **THEN** nenhum evento é emitido

### Requirement: Evento request
Toda requisição HTTP SHALL gerar exatamente um evento `request` com:
- `path`: o caminho já sem o prefixo de stage;
- `method`;
- `status`: o código HTTP da resposta, ou 500 se a requisição terminar em exceção;
- `duration_ms`: o tempo, em milissegundos, do recebimento da requisição até a resposta;
- `cold_start`: verdadeiro só na primeira requisição atendida pela instância;
- `remaining_ms`: o tempo restante da invocação da Lambda ao fim da requisição, ou `null` fora da Lambda;
- `slow`: verdadeiro se `duration_ms` for maior que o limite `SLOW_MS` (variável de ambiente, padrão 250).

#### Scenario: Move bem-sucedido
- **WHEN** a cobra recebe um `/move` válido
- **THEN** sai um evento `request` com `path` `"/move"`, `method` `"POST"`, `status` 200 e `duration_ms` numérico

#### Scenario: Cold start
- **WHEN** a instância atende a primeira e depois a segunda requisição
- **THEN** a primeira tem `cold_start` verdadeiro e a segunda tem `cold_start` falso

#### Scenario: Prefixo de stage
- **WHEN** a requisição chega em `/dev/move`
- **THEN** o evento `request` tem `path` `"/move"`

#### Scenario: Requisição lenta
- **WHEN** `SLOW_MS` é 0 e a cobra atende uma requisição
- **THEN** o evento `request` tem `slow` verdadeiro

### Requirement: Evento start
Todo `/start` SHALL gerar um evento `start` com:
- `ruleset`: um objeto com `name` e `version`;
- `map`, `timeout`, `width`, `height` e `snake_count`;
- `opponents`: lista de objetos com `id` e `name` de cada adversária, na ordem do tabuleiro.

#### Scenario: Partida com adversárias
- **WHEN** a partida começa num 11x11, com ruleset `standard` `v1.2.3`, timeout 500, a cobra `eu` e as adversárias `a` e `b`
- **THEN** o evento `start` tem `snake_count` 3, `timeout` 500 e `opponents` com os ids `a` e `b`, nessa ordem

### Requirement: Evento move
Todo `/move` respondido SHALL gerar exatamente um evento `move`, emitido antes da resposta. O evento contém:
- `you`: `head` (`[x, y]`), `length` e `health`;
- `engine_latency_ms`: a latência que o motor informa na própria cobra, convertida para inteiro, ou `null` se ausente, vazia ou não numérica. É o tempo de resposta do turno anterior medido pelo motor;
- `timed_out_last_turn`: verdadeiro quando `engine_latency_ms` é maior ou igual ao timeout do jogo, e falso caso contrário ou quando a latência é nula;
- `observed_last_move`: a direção do segundo segmento do corpo para a cabeça, ou seja, o movimento que a cobra de fato fez no turno anterior. É `null` quando o corpo tem um segmento só, quando os dois primeiros segmentos coincidem ou quando a diferença não é de uma casa;
- `board`: `width`, `height`, `snake_count` e `food_count`;
- `directions`: um objeto com as quatro direções, descritas no requisito "Direções do evento move";
- `safe_moves`: as candidatas, na ordem canônica;
- `hungry` e `hunger_reasons`: a lista dos critérios de fome que dispararam, entre `starving`, `outsized` e `behind_schedule`. Vazia quando não há fome ou não há candidatas;
- `food_target` (`[x, y]` ou `null`) e `astar_path_len`: o número de passos do caminho da cabeça atual até a comida alvo, ou `null`;
- `chosen`: a direção devolvida na resposta;
- `reason`: o motivo da escolha, descrito no requisito "Motivo da escolha";
- `logic_ms`: o tempo gasto calculando a jogada, sem contar a montagem e a emissão do evento.

#### Scenario: Latência informada pelo motor
- **WHEN** a latência da cobra no payload é `"123"` e o timeout é 500
- **THEN** `engine_latency_ms` é o número 123 e `timed_out_last_turn` é falso

#### Scenario: Latência ausente ou vazia
- **WHEN** a latência da cobra está ausente do payload, ou é `""`
- **THEN** `engine_latency_ms` é nulo e `timed_out_last_turn` é falso

#### Scenario: Turno anterior estourou o tempo
- **WHEN** a latência da cobra é `"500"` e o timeout é 500
- **THEN** `timed_out_last_turn` é verdadeiro

#### Scenario: Movimento observado
- **WHEN** a cabeça está em (5,5) e o segundo segmento em (5,4)
- **THEN** `observed_last_move` é `"up"`

#### Scenario: Corpo empilhado
- **WHEN** o turno é 0 e os três segmentos estão em (5,5)
- **THEN** `observed_last_move` é nulo

#### Scenario: Comida alvo com fome
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 10 e há comida em (8,5)
- **THEN** `hungry` é verdadeiro, `hunger_reasons` contém `starving`, `food_target` é `[8,5]` e `astar_path_len` é 3

### Requirement: Direções do evento move
Cada uma das quatro direções em `directions` SHALL conter:
- `target`: a casa de destino `[x, y]`, mesmo fora do tabuleiro;
- `blocked_by`: os motivos que eliminaram a direção, sem repetição e na ordem em que as regras são aplicadas, entre `neck`, `wall`, `self` e `opponent`. A lista é vazia quando a direção é candidata;
- as medições da direção quando ela é candidata, com `null` em todos esses campos quando ela foi eliminada: `risky`, `area`, `roomy`, `territory_pct`, `food_step`, `food_dist`, `trapped_rivals`, `kill_chance`, `hunt_step`, `danger` e `center_dist`;
- `layer` e `score`: a camada de segurança (de 0, a preferida, a 3) e a pontuação dentro da camada, ou `null` quando a direção foi eliminada;
- `score_terms`: as parcelas da pontuação (`territory`, `food`, `trap`, `kill`, `hunt`, `danger`, `center`), cuja soma é `score`, ou `null` quando a direção foi eliminada.

O cabeça a cabeça desfavorável não elimina direções. Ele SHALL aparecer como `risky` verdadeiro e na camada.

#### Scenario: Adversária ao lado e parede acima
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** `up` tem `blocked_by` `["wall"]`, `down` tem `["neck", "self"]`, `left` tem `["opponent"]`, `right` tem `[]`, `safe_moves` é `["right"]` e as medições de `up`, `down` e `left` são nulas

#### Scenario: Cabeça a cabeça arriscado
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(3,10),(2,10),(1,10),(0,10)]
- **THEN** `left` tem `blocked_by` vazio, `risky` verdadeiro e `layer` 1

#### Scenario: Parcelas somam a pontuação
- **WHEN** o evento `move` traz uma direção candidata
- **THEN** a soma dos valores de `score_terms` dessa direção é igual ao seu `score`

### Requirement: Motivo da escolha
O campo `reason` do evento `move` SHALL ser um entre:
- `emergency`: não havia candidata, e a direção veio do sorteio de emergência;
- `only_option`: havia uma única candidata;
- `layer`: a escolhida era a única candidata na melhor camada de segurança presente;
- `score`: a escolhida tinha pontuação estritamente maior que as outras candidatas da mesma camada;
- `tie`: outra candidata da mesma camada tinha a mesma pontuação, e a ordem canônica desempatou.

#### Scenario: Única opção
- **WHEN** o corpo é [(5,10),(5,9),(5,8)] e uma adversária ocupa [(4,10),(3,10),(2,10)]
- **THEN** `chosen` é `"right"` e `reason` é `"only_option"`

#### Scenario: Empate decidido pela ordem canônica
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 100, não há adversárias nem comida e o turno é 1
- **THEN** `up`, `left` e `right` têm a mesma camada e a mesma pontuação, `chosen` é `"up"` e `reason` é `"tie"`

#### Scenario: Pontuação com fome
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 10 e há comida em (8,5)
- **THEN** `chosen` é `"right"`, `reason` é `"score"`, `food_step` é verdadeiro só em `right` e `score_terms.food` de `right` é positivo

#### Scenario: Camada de segurança
- **WHEN** o corpo é [(0,1),(1,1),(2,1),(2,0),(1,0)] e uma adversária ocupa [(0,3),(0,4),(0,5),(0,6),(0,7),(0,8)]
- **THEN** `chosen` é `"up"` e `reason` é `"layer"`

#### Scenario: Emergência
- **WHEN** o corpo é [(0,0),(1,0),(1,1),(0,1),(0,2)] e não há adversárias
- **THEN** `reason` é `"emergency"`, `safe_moves` é vazio, as quatro direções têm `blocked_by` não vazio e `chosen` é uma das quatro direções

### Requirement: Evento end
Todo `/end` SHALL gerar um evento `end` com:
- `turns`: o turno do payload;
- `won`: verdadeiro quando a cobra é a única cobra viva no tabuleiro;
- `eliminated`: verdadeiro quando a cobra não está entre as cobras do tabuleiro;
- `survivors`: os ids das cobras do tabuleiro, na ordem do payload.

#### Scenario: Vitória
- **WHEN** o tabuleiro final tem só a cobra `eu`
- **THEN** `won` é verdadeiro, `eliminated` é falso e `survivors` é `["eu"]`

#### Scenario: Eliminada
- **WHEN** o tabuleiro final tem só as adversárias `a` e `b`
- **THEN** `won` é falso, `eliminated` é verdadeiro e `survivors` é `["a", "b"]`

#### Scenario: Várias vivas
- **WHEN** o tabuleiro final tem a cobra `eu` e a adversária `a`
- **THEN** `won` é falso e `eliminated` é falso

### Requirement: Evento error
Uma exceção durante `/start`, `/move` ou `/end` SHALL gerar um evento `error` com `path`, `exception` (o nome do tipo), `message` e `traceback` (texto). Quando o payload foi lido, os campos comuns de jogo SHALL vir preenchidos. Depois do evento, a exceção SHALL seguir como hoje: a requisição falha do mesmo jeito que falharia sem os logs.

Um payload rejeitado pela validação SHALL também gerar um evento `error`, com `exception` igual a `RequestValidationError`, `message` listando o local e o tipo de cada erro sem os valores recebidos, e `game_id` e `turn` lidos do corpo quando ele for um JSON com esses campos. A resposta continua sendo 422, com o mesmo corpo de hoje.

#### Scenario: Falha na escolha do movimento
- **WHEN** o cálculo da escolha lança uma exceção durante um `/move` da partida `partida-de-teste`, no turno 7
- **THEN** sai um evento `error` com `path` `"/move"`, o tipo e a mensagem da exceção, um `traceback` não vazio, `game_id` `"partida-de-teste"` e `turn` 7, e a exceção chega ao chamador

#### Scenario: Payload inválido
- **WHEN** um `/move` chega sem o campo `you`, com `game.id` `"g1"` e `turn` 3
- **THEN** a resposta é 422, e sai um evento `error` com `exception` `"RequestValidationError"`, `game_id` `"g1"` e `turn` 3

### Requirement: Sem segredos
Nenhum evento SHALL conter cabeçalhos HTTP, query string, variáveis de ambiente, credenciais ou o corpo bruto da requisição.

#### Scenario: Cabeçalho sensível
- **WHEN** um `/move` chega com o cabeçalho `Authorization: Bearer segredo-xyz`
- **THEN** nenhuma linha emitida contém `segredo-xyz`

### Requirement: Logs não mudam a decisão
Para o mesmo payload, o movimento devolvido SHALL ser o mesmo com qualquer nível de log, e o mesmo de antes desta capability, sempre que houver ao menos uma candidata.

#### Scenario: Cenários de estratégia existentes
- **WHEN** os cenários de estratégia já existentes rodam com os eventos ligados e com eles desligados
- **THEN** o movimento devolvido é o mesmo nos dois casos e igual ao esperado pelos testes existentes

### Requirement: Custo dos logs
Montar e emitir o evento `move` SHALL levar menos de 5 ms num tabuleiro 19x19 com 9 cobras. A medição não inclui o cálculo da jogada.

#### Scenario: Tabuleiro cheio
- **WHEN** o tabuleiro é 19x19 com 9 cobras e algumas comidas
- **THEN** a melhor de várias medições da montagem mais a emissão do evento `move` fica abaixo de 5 ms

### Requirement: Consultas documentadas
O repositório SHALL ter um documento com as consultas do CloudWatch Logs Insights para:
- a linha do tempo de uma partida;
- os turnos que estouraram o tempo;
- as requisições lentas e os cold starts;
- as emergências;
- a distribuição das decisões por `reason` e `chosen`;
- os erros;
- o resultado das partidas.

Cada consulta SHALL ter uma explicação curta. O documento SHALL explicar como separar as três hipóteses de um movimento inesperado:
- timeout ou erro;
- emergência;
- decisão da lógica.

O documento SHALL também registrar a sintaxe dos filtros de campos booleanos validada contra logs reais.

#### Scenario: Consultas presentes
- **WHEN** o documento de logs é lido
- **THEN** ele tem as sete consultas, cada uma com explicação, e o roteiro das três hipóteses

#### Scenario: Filtro booleano validado
- **WHEN** a primeira partida depois do deploy gera eventos no CloudWatch
- **THEN** o documento registra a forma do filtro booleano que retornou resultados (por exemplo `slow = 1` ou `slow = "true"`)
