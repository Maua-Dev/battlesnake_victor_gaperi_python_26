## MODIFIED Requirements

### Requirement: Uma linha JSON por evento
A cobra SHALL emitir só dois eventos: `move` e `error`. Cada evento SHALL ser escrito na saída padrão como uma única linha que contém apenas um objeto JSON, sem prefixo de data, nível ou id de requisição. Textos não ASCII SHALL aparecer como caracteres, e não como sequências de escape. Os eventos da cobra não SHALL ser duplicados pelo logger raiz do runtime.

Um campo que não pode ser serializado em JSON SHALL sair como texto, sem lançar exceção. Se a montagem ou a serialização de um evento falhar, SHALL sair no lugar dele um evento `error`, e a requisição SHALL seguir como seguiria sem os logs.

Nenhum evento SHALL conter os campos `ts`, `snake_id` ou `aws_request_id`.

#### Scenario: Toda linha é um objeto JSON
- **WHEN** a cobra atende uma sequência de `/start`, `/move` e `/end`
- **THEN** cada linha emitida é um objeto JSON válido que contém `event`

#### Scenario: Sem duplicação
- **WHEN** a cobra emite um evento `move`
- **THEN** exatamente uma linha com `"event":"move"` aparece na saída

#### Scenario: Texto não ASCII
- **WHEN** um evento traz o texto `ção`
- **THEN** a linha emitida contém `ção` literalmente

#### Scenario: Campo não serializável
- **WHEN** um evento traz um campo que não é serializável em JSON
- **THEN** o evento sai com esse campo como texto, e nenhuma exceção é lançada

#### Scenario: Falha de serialização
- **WHEN** um evento traz um campo com referência circular
- **THEN** sai um evento `error` no lugar dele, e nenhuma exceção é lançada

#### Scenario: Start e end não emitem nada
- **WHEN** a cobra atende um `/start` ou um `/end` sem falha
- **THEN** nenhuma linha é emitida

### Requirement: Nível configurável
O nível mínimo dos eventos SHALL vir da variável de ambiente `LOG_LEVEL`, com padrão `INFO`. O evento `error` SHALL ter nível de erro. O evento `move` SHALL ter nível informativo.

#### Scenario: Nível padrão
- **WHEN** `LOG_LEVEL` não está definida e a cobra atende um `/move` via HTTP
- **THEN** sai exatamente uma linha, e ela é o evento `move`

#### Scenario: Só erros
- **WHEN** o nível é `ERROR` e a cobra emite um `move` e um `error`
- **THEN** só o `error` sai

### Requirement: Evento move
Toda chamada da escolha de movimento SHALL gerar exatamente um evento `move`, emitido antes da resposta, inclusive na emergência (nenhuma direção segura). O evento SHALL conter exatamente estes campos:
- `event`: `"move"`;
- `game_id` e `turn`: os valores do payload;
- `move`: a direção devolvida na resposta;
- `timed_out_last_turn`: verdadeiro quando a latência que o motor informa na própria cobra, convertida para inteiro, é maior ou igual ao timeout do jogo. É falso caso contrário, e também quando a latência está ausente, vazia ou não é numérica.

O payload continua aceitando a latência da cobra.

#### Scenario: Campos do move
- **WHEN** a cobra recebe um `/move` da partida `partida-de-teste`, no turno 7
- **THEN** o evento `move` tem exatamente os campos `event`, `game_id`, `turn`, `move` e `timed_out_last_turn`, com `game_id` `"partida-de-teste"`, `turn` igual ao número 7 e `move` igual à direção da resposta

#### Scenario: Emergência
- **WHEN** o corpo é [(0,0),(1,0),(1,1),(0,1),(0,2)] e não há adversárias
- **THEN** sai exatamente um evento `move`, e o `move` dele é a direção da resposta

#### Scenario: Turno anterior estourou o tempo
- **WHEN** a latência da cobra é `"500"` ou `"750"` e o timeout é 500
- **THEN** `timed_out_last_turn` é verdadeiro

#### Scenario: Latência informada pelo motor
- **WHEN** a latência da cobra é `"499"` ou `"123"` e o timeout é 500
- **THEN** `timed_out_last_turn` é falso

#### Scenario: Latência ausente ou vazia
- **WHEN** a latência da cobra está ausente do payload, ou é `""`, ou é `"abc"`
- **THEN** `timed_out_last_turn` é falso

#### Scenario: Movimento observado
- **WHEN** a cabeça está em (5,5) e o segundo segmento em (5,4)
- **THEN** o evento `move` não tem o campo `observed_last_move` nem outro campo além dos cinco definidos

#### Scenario: Corpo empilhado
- **WHEN** o turno é 0 e os três segmentos estão em (5,5)
- **THEN** sai exatamente um evento `move`, com os cinco campos e `turn` igual a 0

#### Scenario: Comida alvo com fome
- **WHEN** o corpo é [(5,5),(5,4),(5,3)], a vida é 10 e há comida em (8,5)
- **THEN** o evento `move` tem `move` `"right"` e não tem `hungry`, `hunger_reasons`, `food_target` nem `astar_path_len`

### Requirement: Evento error
Uma exceção durante `/start`, `/move` ou `/end` SHALL gerar um evento `error` com exatamente estes campos:
- `event`: `"error"`;
- `path`;
- `exception`: o nome do tipo;
- `message`;
- `traceback`: texto;
- `game_id` e `turn`: os valores do payload quando ele foi lido, e `null` quando não foi.

Depois do evento, a exceção SHALL seguir como hoje: a requisição falha do mesmo jeito que falharia sem os logs.

Um payload rejeitado pela validação SHALL também gerar um evento `error`, com `exception` igual a `RequestValidationError` e `message` listando o local e o tipo de cada erro, sem os valores recebidos. `game_id` e `turn` SHALL ser lidos do corpo quando ele for um JSON com esses campos. A resposta continua sendo 422, com o mesmo corpo que o FastAPI devolve sem o tratamento da cobra.

#### Scenario: Falha na escolha do movimento
- **WHEN** o cálculo da escolha lança uma exceção durante um `/move` da partida `partida-de-teste`, no turno 7
- **THEN** sai um evento `error` com:
  - `path` `"/move"`, o tipo e a mensagem da exceção e um `traceback` não vazio;
  - `game_id` `"partida-de-teste"` e `turn` 7;
- **AND** a exceção chega ao chamador

#### Scenario: Payload inválido
- **WHEN** um `/move` chega sem o campo `you`, com `game.id` `"g1"` e `turn` 3
- **THEN** a resposta é 422, com o mesmo corpo do FastAPI sem o tratamento da cobra
- **AND** sai um evento `error` com `exception` `"RequestValidationError"`, `message` `"body.you: missing"`, `game_id` `"g1"` e `turn` 3

#### Scenario: Corpo que não é JSON
- **WHEN** um `/move` chega com um corpo que não é JSON
- **THEN** a resposta é 422, e sai um evento `error` com `game_id` nulo

### Requirement: Sem segredos
Nenhum evento SHALL conter cabeçalhos HTTP, query string, variáveis de ambiente, credenciais ou o corpo bruto da requisição.

#### Scenario: Cabeçalho sensível
- **WHEN** um `/move` chega com o cabeçalho `Authorization: Bearer segredo-xyz`
- **THEN** nenhuma linha emitida contém `segredo-xyz`

#### Scenario: Query string sensível
- **WHEN** um `/move` chega com a query string `token=segredo-xyz`
- **THEN** nenhuma linha emitida contém `segredo-xyz`

### Requirement: Consultas documentadas
O repositório SHALL ter um documento curto com os dois eventos e seus campos e com as consultas do CloudWatch Logs Insights para:
- os turnos de uma partida, em ordem de turno, com `turn`, `move` e `timed_out_last_turn`;
- os turnos que estouraram o tempo, em todas as partidas;
- os erros;
- a duração da Lambda (média, máxima e percentil 95 por intervalo de tempo), lida das linhas `REPORT` do runtime.

O documento SHALL avisar que a sintaxe do filtro de campo booleano precisa ser conferida contra logs reais.

#### Scenario: Consultas presentes
- **WHEN** o documento de logs é lido
- **THEN** ele descreve os eventos `move` e `error` e traz as quatro consultas e o aviso sobre o filtro booleano

#### Scenario: Filtro booleano validado
- **WHEN** o documento de logs é lido antes de a consulta ser testada contra logs reais
- **THEN** a consulta de turnos que estouraram o tempo filtra por `timed_out_last_turn = 1`, e o aviso diz que essa forma ainda precisa ser conferida contra logs reais

## REMOVED Requirements

### Requirement: Campos comuns
**Reason**: `ts`, `snake_id` e `aws_request_id` não ajudam a ler a partida. O CloudWatch já guarda o `@timestamp` e o `@requestId` de cada linha. `game_id` e `turn` passam a ser definidos em "Evento move" e "Evento error".
**Migration**: Use o `@timestamp` do CloudWatch no lugar de `ts`, e o `@requestId` ou as linhas `REPORT` no lugar de `aws_request_id`.

### Requirement: Evento request
**Reason**: A duração e o cold start já aparecem nas linhas `REPORT` que o runtime da Lambda grava em toda invocação. O evento duplicava essa informação e deixava os logs mais difíceis de ler.
**Migration**: Use `filter @type = "REPORT" | stats avg(@duration), max(@duration), pct(@duration, 95) by bin(5m)`. Para cold starts, use `@initDuration` nas mesmas linhas.

### Requirement: Evento start
**Reason**: O ruleset, o mapa, o timeout e as adversárias não foram usados no diagnóstico. A partida já é identificada pelo `game_id` de cada `move`.
**Migration**: Nenhuma. Os dados ficam na página da partida no site do Battlesnake.

### Requirement: Direções do evento move
**Reason**: O detalhamento por direção (alvo, bloqueios, medições, camada, pontuação e parcelas) tornou o evento `move` grande demais para ler. A explicação continua disponível no código pela explicação da decisão (capability `decisao-de-movimento`).
**Migration**: Para investigar uma jogada, reproduza o estado localmente e chame a explicação da decisão com as medições daquele turno.

### Requirement: Motivo da escolha
**Reason**: Sai junto com o detalhamento das direções. O motivo continua calculado pela explicação da decisão, que não foi alterada.
**Migration**: Reproduza o estado localmente e leia o motivo devolvido pela explicação da decisão.

### Requirement: Evento end
**Reason**: O resultado da partida não foi usado no diagnóstico, e o último `move` de cada `game_id` já mostra até onde a cobra chegou.
**Migration**: Use a página da partida no site do Battlesnake, ou o maior `turn` dos eventos `move` daquela partida.

### Requirement: Custo dos logs
**Reason**: O evento `move` passa a ter cinco campos escalares e não percorre o tabuleiro. O custo medido do evento antigo já era de 0,02 ms, e o do novo é ainda menor.
**Migration**: Nenhuma. Para medir o tempo total da Lambda, use as linhas `REPORT`.
