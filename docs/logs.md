# Logs de diagnóstico

A cobra grava **uma linha JSON por evento** no stdout da Lambda. Cada linha chega ao CloudWatch como JSON puro, sem o prefixo `[INFO] <data> <request id>` do runtime, e o CloudWatch Logs Insights descobre os campos sozinho, sem `parse`.

O objetivo é responder, só olhando o CloudWatch, **por que a cobra fez cada movimento** de uma partida.

- Código: `src/app/telemetry.py` (formato e builders), `src/app/main.py` (`request` e `error`) e `src/app/logic.py` (`start`, `move` e `end`).
- Grupo de logs: `/aws/lambda/battlesnake-<repo-slug>-lambda-dev`.
- Variáveis de ambiente (opcionais; a IaC não as define, então valem os padrões):
  - `LOG_LEVEL`: padrão `INFO`. Com `WARNING` ou `ERROR`, só os eventos `error` saem.
  - `SLOW_MS`: padrão `250`. Acima disso o `request` sai com `slow: true`.

## Campos comuns

Todo evento tem:

| Campo | Tipo | Conteúdo |
|---|---|---|
| `event` | string | `request`, `start`, `move`, `end` ou `error` |
| `ts` | string | instante em ISO 8601 UTC (`2026-10-08T21:14:03.512Z`) |
| `game_id` | string ou null | id da partida, quando o payload foi lido |
| `turn` | número ou null | turno do payload |
| `snake_id` | string ou null | id da minha cobra |
| `aws_request_id` | string ou null | id da invocação da Lambda (null fora dela) |

Um mesmo campo tem sempre o mesmo nome e o mesmo tipo em todos os eventos. Números são números, nunca strings. Nenhum evento contém cabeçalhos HTTP, query string, variáveis de ambiente nem o corpo bruto da requisição.

## Eventos

### `request`: um por requisição HTTP

| Campo | Conteúdo |
|---|---|
| `path`, `method` | caminho sem o prefixo de stage (`/dev/move` vira `/move`) e método |
| `status` | código HTTP da resposta, ou 500 se a requisição terminou em exceção |
| `duration_ms` | do recebimento até a resposta pronta, medido dentro da Lambda (não inclui a rede nem a conversão do Mangum) |
| `cold_start` | `true` só na primeira requisição atendida pela instância |
| `remaining_ms` | tempo restante da invocação ao fim da requisição |
| `slow` | `duration_ms > SLOW_MS` |

### `start`: um por partida

`ruleset` (`name`, `version`), `map`, `timeout`, `width`, `height`, `snake_count` e `opponents` (lista de `{id, name}`).

### `move`: exatamente um por `/move` respondido

| Campo | Conteúdo |
|---|---|
| `you` | `head` `[x, y]`, `length` e `health` |
| `engine_latency_ms` | a latência que o **motor** mediu na resposta do turno **anterior** (`you.latency` do payload), ou null |
| `timed_out_last_turn` | `engine_latency_ms >= timeout`: o turno anterior estourou o tempo |
| `observed_last_move` | a direção que a cobra **de fato** andou no turno anterior, de `body[1]` para `body[0]`. É null no turno 0 e com corpo empilhado |
| `board` | `width`, `height`, `snake_count` e `food_count` |
| `directions` | um objeto por direção (`up`, `down`, `left`, `right`), descrito abaixo |
| `safe_moves` | as candidatas, na ordem canônica |
| `hungry` | se a cobra estava com fome (null na emergência, quando a fome nem é avaliada) |
| `hunger_reasons` | critérios de fome que dispararam: `starving` (vida curta para chegar à comida), `outsized` (não está 2 segmentos à frente da maior rival) e `behind_schedule` (menos de uma comida a cada 8 turnos) |
| `food_target` | a comida alvo `[x, y]`, ou null |
| `astar_path_len` | passos do A* da cabeça atual até a comida alvo, ou null |
| `chosen` | a direção devolvida ao motor |
| `reason` | o motivo da escolha (tabela abaixo) |
| `logic_ms` | tempo de cálculo da jogada, sem contar a montagem do log |

Cada direção em `directions` tem:

- `target`: a casa de destino `[x, y]`, mesmo fora do tabuleiro;
- `blocked_by`: por que a direção foi eliminada, na ordem das regras. Vazia quando a direção é candidata:
  - `neck`: voltaria pelo pescoço;
  - `wall`: sairia do tabuleiro;
  - `self`: bateria no próprio corpo (o pescoço também é corpo, então `down` costuma vir como `["neck", "self"]`);
  - `opponent`: bateria no corpo de uma adversária, cauda incluída;
- as medições da candidata (`MoveFeatures`):
  - `risky`: uma rival maior ou igual alcança a mesma casa (cabeça a cabeça);
  - `area` e `roomy`: espaço alcançável, e se cabe a cobra inteira;
  - `territory_pct`;
  - `food_step` e `food_dist`;
  - `trapped_rivals`;
  - `kill_chance`;
  - `hunt_step`;
  - `danger`;
  - `center_dist`;
- `layer`: a camada de segurança, de 0 a 3:
  - 0: não arriscada e com espaço;
  - 1: arriscada e com espaço;
  - 2: não arriscada e sem espaço;
  - 3: arriscada e sem espaço;
- `score`: a nota dentro da camada;
- `score_terms`: as parcelas da nota (`territory`, `food`, `trap`, `kill`, `hunt`, `danger`, `center`). A soma delas é `score`.

Nas direções eliminadas, e em todas na emergência, as medições, `layer`, `score` e `score_terms` são null.

O cabeça a cabeça **não** elimina direções: ele aparece como `risky: true` e empurra a direção para a camada 1 ou 3.

| `reason` | Significado |
|---|---|
| `only_option` | havia uma única candidata |
| `layer` | a escolhida era a única candidata na melhor camada presente |
| `score` | a escolhida tinha nota estritamente maior que as outras da mesma camada |
| `tie` | outra candidata da mesma camada tinha a mesma nota, e a ordem canônica `up, down, left, right` desempatou. É o caso que favorece `up` |
| `emergency` | nenhuma candidata. O movimento foi **sorteado** entre as quatro direções |

`reason`, `layer` e `score` descrevem a regra atual de `src/app/decision.py` (`explain`, que é a própria `decide`). Quando um modelo de decisão externo (Jev) substituir `decide`, este evento terá de ser revisto.

### `end`: um por partida

`turns`, `won` (minha cobra é a única viva), `eliminated` (meu id não está em `board.snakes`) e `survivors` (ids das cobras vivas).

### `error`

Qualquer exceção em `/start`, `/move` ou `/end` gera um `error` com `path`, `exception` (tipo), `message` e `traceback`, mais `game_id` e `turn`. A exceção segue normalmente: a requisição falha como falharia sem os logs, e o motor escolhe o movimento.

Um payload recusado pela validação (resposta 422) também gera `error`, com estes campos:

- `exception`: `RequestValidationError`;
- `message`: só o local e o tipo de cada erro, sem os valores (por exemplo `body.you: missing`);
- `game_id` e `turn`: lidos do corpo quando possível.

Se a própria telemetria falhar ao montar um evento, sai um `error` com `message` `telemetry: falha ao montar o evento <nome>`, e a jogada segue.

## Consultas do Logs Insights

> **A validar no primeiro deploy (tarefa 11.2).** Há duas incertezas:
> - **Booleanos:** o Insights pode exigir `slow = 1` ou `slow = "true"` (ou `ispresent`). As consultas abaixo usam `= 1`. Se não retornarem nada, troque por `= "true"`.
> - **Listas:** listas JSON podem aparecer achatadas por índice (`safe_moves.0`, `safe_moves.1`, …).
>
> Registre aqui a forma que funcionou.

**Linha do tempo de uma partida.** Uma linha por turno com a escolha, o motivo e o que o motor observou. É o ponto de partida de toda investigação.

```
fields turn, chosen, reason, observed_last_move, engine_latency_ms, timed_out_last_turn, safe_moves
| filter event = "move" and game_id = "<id>"
| sort turn asc
```

**Turnos que estouraram o tempo.** O motor informa no turno N+1 que a resposta do turno N demorou o timeout inteiro.

```
fields game_id, turn, engine_latency_ms
| filter event = "move" and timed_out_last_turn = 1
| sort @timestamp desc
```

**Requisições lentas e cold starts.** Mostra se a lentidão vem da primeira chamada da instância ou do cálculo.

```
fields path, duration_ms, cold_start, remaining_ms
| filter event = "request" and (slow = 1 or cold_start = 1)
| sort duration_ms desc
```

**Emergências.** Turnos sem nenhuma candidata, com o motivo de cada direção ter caído.

```
fields game_id, turn, directions.up.blocked_by, directions.down.blocked_by, directions.left.blocked_by, directions.right.blocked_by
| filter event = "move" and reason = "emergency"
```

**Distribuição das decisões.** Quantas vezes cada motivo levou a cada direção. Um `tie` com `up` dominante confirma o viés do desempate.

```
filter event = "move"
| stats count(*) by reason, chosen
```

**Erros.** Exceções e payloads recusados.

```
fields path, exception, message, game_id, turn
| filter event = "error"
| sort @timestamp desc
```

**Resultado das partidas.**

```
fields game_id, turns, won, eliminated
| filter event = "end"
| sort @timestamp desc
```

## Como separar as três hipóteses

Para um movimento inesperado no turno N (por exemplo, a cobra subiu e bateu), abra a **linha do tempo** da partida e olhe os turnos N e N+1.

### 1. Timeout ou erro: o motor escolheu no lugar da cobra

Quando a cobra não responde a tempo, o motor repete o último movimento (no turno 0, `up`). Há quatro sinais:

- **No turno N+1, `observed_last_move` difere do `chosen` do turno N.** A cobra pediu uma direção e andou em outra. É o sinal mais direto.
- **`timed_out_last_turn` é `true` no turno N+1.** A resposta do turno N levou o timeout inteiro, segundo o motor.
- **Não existe evento `move` para o turno N.** A requisição nem chegou à cobra, ou caiu antes. Procure um `request` com `status` diferente de 200, ou um `error` com o mesmo `game_id` e `turn`.
- **O `request` do turno N saiu com `slow: true` ou `cold_start: true`.** Compare `duration_ms` com o `timeout` do evento `start`. A latência do motor também inclui a rede, então ela pode estourar mesmo com `duration_ms` baixo.

### 2. Emergência: nenhuma direção era candidata

- **`reason` é `emergency`.** O `chosen` foi sorteado.
- **Os `blocked_by` das quatro direções dizem o que fechou cada uma.** Se o problema foi chegar a esse beco, olhe os turnos anteriores: as camadas e as notas mostram por que a cobra entrou nele.

### 3. Decisão da lógica

Neste caso `reason` é `only_option`, `layer`, `score` ou `tie`, e `observed_last_move` do turno seguinte bate com o `chosen`.

- **`only_option`:** só havia uma saída. Veja os `blocked_by` das outras.
- **`layer`:** as outras candidatas estavam numa camada pior. Veja `risky` e `roomy`.
- **`score`:** compare `score_terms` das candidatas para ver qual parcela decidiu (território, comida, rival encurralada…).
- **`tie`:** as notas empataram e a ordem canônica escolheu. Por isso `up` aparece quando tudo empata.
