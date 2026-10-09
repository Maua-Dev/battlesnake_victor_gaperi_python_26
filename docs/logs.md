# Logs de diagnóstico

A cobra grava **uma linha JSON por evento** no stdout da Lambda. Cada linha chega ao CloudWatch como JSON puro, sem o prefixo `[INFO] <data> <request id>` do runtime, e o CloudWatch Logs Insights descobre os campos sozinho, sem `parse`.

São só dois eventos: `move`, um por jogada, e `error`.

- Código: `src/app/telemetry.py`. O `move` sai de `src/app/logic.py` e o `error` sai de `src/app/main.py`.
- Grupo de logs: `/aws/lambda/battlesnake-<repo-slug>-lambda-dev`.
- `LOG_LEVEL` (variável de ambiente opcional; a IaC não a define): o padrão é `INFO`. Com `WARNING` ou `ERROR`, só os eventos `error` saem.

Nenhum evento contém cabeçalhos HTTP, query string, variáveis de ambiente nem o corpo bruto da requisição. O instante e o id da invocação ficam em `@timestamp` e `@requestId`, que o CloudWatch já põe em toda linha.

## Eventos

### `move`: exatamente um por jogada

```json
{"event": "move", "game_id": "...", "turn": 12, "move": "left", "timed_out_last_turn": false}
```

| Campo | Conteúdo |
|---|---|
| `game_id`, `turn` | a partida e o turno do payload |
| `move` | a direção devolvida ao motor, inclusive na emergência (sorteada quando nenhuma direção é segura) |
| `timed_out_last_turn` | `true` quando a latência que o motor mediu na resposta do turno **anterior** (`you.latency`) é maior ou igual ao `timeout` da partida. Latência ausente, vazia ou não numérica vale `false` |

Quando o turno anterior estoura o tempo, o motor ignora a resposta da cobra e repete o movimento anterior.

### `error`

Qualquer exceção em `/start`, `/move` ou `/end` gera um `error` com `path`, `exception` (o tipo), `message`, `traceback`, `game_id` e `turn`. A exceção segue normalmente: a requisição falha como falharia sem os logs.

Um payload recusado pela validação (resposta 422) também gera um `error`:
- `exception` é `RequestValidationError`;
- `message` traz só o local e o tipo de cada erro, sem os valores (por exemplo `body.you: missing`);
- `game_id` e `turn` são lidos do corpo quando possível, e ficam `null` quando não dá.

Se a própria telemetria falhar ao montar um evento, sai um `error` com `message` `telemetry: falha ao montar o evento <nome>`, e a jogada segue.

## Consultas do Logs Insights

> **A conferir contra logs reais:** a sintaxe do filtro booleano. A consulta de turnos que estouraram o tempo usa `timed_out_last_turn = 1`. Se ela não retornar nada numa partida em que sabidamente houve timeout, troque por `timed_out_last_turn = "true"`, e registre aqui a forma que funcionou.

**A partida.** Uma linha por turno, com a direção escolhida e se o turno anterior estourou o tempo.

```
fields turn, move, timed_out_last_turn
| filter event = "move" and game_id = "<id>"
| sort turn asc
```

**Turnos que estouraram o tempo**, em todas as partidas.

```
fields game_id, turn, move
| filter event = "move" and timed_out_last_turn = 1
| sort @timestamp desc
```

**Erros:** exceções e payloads recusados.

```
fields path, exception, message, game_id, turn
| filter event = "error"
| sort @timestamp desc
```

**Duração da Lambda.** O runtime grava uma linha `REPORT` em toda invocação, com a duração (`@duration`, em ms) e, no cold start, `@initDuration`. Esta consulta dá a média, a máxima e o percentil 95 a cada 5 minutos:

```
filter @type = "REPORT"
| stats avg(@duration), max(@duration), pct(@duration, 95) by bin(5m)
```

O timeout do motor (500 ms) inclui também a rede. Por isso, uma duração bem abaixo de 500 ms ainda pode vir com `timed_out_last_turn` verdadeiro.
