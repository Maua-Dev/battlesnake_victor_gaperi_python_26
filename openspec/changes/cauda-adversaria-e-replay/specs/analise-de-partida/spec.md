## Purpose

Uma ferramenta local que baixa uma partida jogada na Arena e reexecuta a lógica da cobra turno a turno. Ela mostra o que cada direção mediu, o que a busca acha com tempo de sobra e onde a jogada de produção divergiu da escolha local.

## ADDED Requirements

### Requirement: Linha de comando
A ferramenta SHALL rodar a partir da raiz do repositório como `python scripts/replay.py <game_id>`, com as opções:
- `--engine URL`: base da API, `https://arena.devmaua.com/api` por padrão;
- `--snake ID_OU_NOME`: a cobra analisada, pelo id ou pelo nome exato;
- `--turns A-B`: o intervalo de turnos, com as duas pontas incluídas, ou um turno só (`--turns 74`);
- `--budget-ms N`: o orçamento da jogada simulada, 120 por padrão;
- `--deep-budget-ms N`: o prazo folgado das medições e da busca, 5000 por padrão.

Um intervalo inválido (fora do formato ou com `A > B`) SHALL encerrar com código de saída diferente de 0 e uma mensagem de erro, sem baixar nada.

#### Scenario: Intervalo inválido
- **WHEN** a ferramenta roda com `--turns 76-72`
- **THEN** ela termina com código diferente de 0, mostra o erro e não faz nenhuma requisição

### Requirement: Download da partida
A ferramenta SHALL baixar `GET <engine>/games/<game_id>` e os frames por `GET <engine>/games/<game_id>/frames?offset=<o>&limit=<n>`, começando em `offset=0`. A cada página, o `offset` avança pelo número de frames recebidos, até chegar uma página vazia ou menor que `limit`. Os frames SHALL ser juntados na ordem de `Turn`. Uma falha de rede ou uma resposta HTTP de erro SHALL encerrar com código diferente de 0 e uma mensagem com a URL que falhou.

#### Scenario: Duas páginas
- **WHEN** o cliente HTTP devolve uma página cheia com os turnos 0 a 2 e depois uma página com os turnos 3 e 4
- **THEN** a ferramenta pede `offset=0` e depois `offset=3`, e fica com os 5 frames, do turno 0 ao 4

### Requirement: Escolha da cobra analisada
Com `--snake`, a cobra SHALL ser a do primeiro frame cujo `ID` ou `Name` é igual ao valor dado. Sem `--snake`, SHALL ser a única cobra em que o `author` de `GET /` da própria cobra (`"gasperi"`) aparece no `Author` ou no `Name`, sem diferenciar maiúsculas de minúsculas. Se nenhuma cobra bater, ou se mais de uma bater, a ferramenta SHALL listar id, nome e autor de todas as cobras da partida e encerrar com código diferente de 0, pedindo `--snake`.

#### Scenario: Pelo autor
- **WHEN** a partida tem as cobras de autores `autor-a`, `autor-b` e `VictorGasperi` (nome `gasperi-1`) e não há `--snake`
- **THEN** a cobra analisada é a de autor `VictorGasperi`

#### Scenario: Nenhuma cobra bate
- **WHEN** nenhuma cobra tem `gasperi` no autor nem no nome e não há `--snake`
- **THEN** a ferramenta lista as cobras e termina com código diferente de 0

### Requirement: Conversão de um frame no estado do /move
Cada frame SHALL virar o JSON que o `/move` receberia naquele turno, validado com o mesmo modelo do `/move`:
- `turn` vem de `Turn`, `board.width` e `board.height` vêm da partida, `board.food` e `board.hazards` vêm de `Food` e `Hazards`;
- `board.snakes` tem só as cobras vivas no frame, ou seja, sem `Death`, na ordem do frame. Cada uma tem `id`, `name`, `health`, `body`, `head` (o primeiro segmento), `length` (o número de segmentos), `latency` e `shout`, a partir de `ID`, `Name`, `Health`, `Body`, `Latency` e `Shout`, com `X` e `Y` virando `x` e `y`;
- `you` é a cobra analisada;
- `game.timeout` é 500 e `game.ruleset` é `{"name": "standard"}`, sem `settings`, porque a Arena não informa as regras da partida. O dano de hazard fica 0.

Um turno em que a cobra analisada já não está viva SHALL ficar fora da análise.

#### Scenario: Frame com cobra morta
- **WHEN** o frame salvo do turno 74 da partida `dc8c4f05-84ac-4554-98f6-94b22d5a8b4d` tem três cobras, uma delas com `Death` do turno 10
- **THEN** o estado tem `turn` 74, duas cobras em `board.snakes`, `you` é a cobra analisada com corpo [(2,4),(2,3),(2,2),(1,2),(0,2),(0,3),(0,4),(0,5),(1,5),(2,5),(3,5)], vida 96 e `length` 11, e a comida é (1,9), (10,4) e (7,2)

### Requirement: Direção jogada e latência
A direção jogada no turno T SHALL ser deduzida da diferença entre a cabeça da cobra analisada no frame T e no frame T+1: `up` para y+1, `down` para y-1, `left` para x-1 e `right` para x+1. A latência do turno T SHALL ser o `Latency` da cobra analisada no frame T+1, que é o frame produzido pela resposta àquele `/move`, mostrado como veio (por exemplo `194` ou `timeout`). Sem o frame T+1, ou com uma diferença que não é de uma casa, a direção e a latência SHALL aparecer como desconhecidas.

#### Scenario: Turno 74
- **WHEN** a cabeça está em (2,4) no frame 74 e em (1,4) no frame 75, com `Latency` `176` no frame 75
- **THEN** a direção jogada no turno 74 é `left` e a latência é `176`

#### Scenario: Último frame
- **WHEN** o turno analisado é o último frame da partida
- **THEN** a direção jogada e a latência aparecem como desconhecidas

### Requirement: Turnos analisados
Com `--turns`, a ferramenta SHALL analisar os turnos do intervalo em que a cobra analisada está viva. Sem `--turns`, SHALL analisar os 8 turnos anteriores ao `Death.Turn` da cobra analisada (de `Death.Turn - 8` a `Death.Turn - 1`) ou, se ela não morreu, os 8 últimos frames da partida. Turnos antes de 0 não entram.

#### Scenario: Cobra que morreu no turno 77
- **WHEN** a cobra analisada tem `Death.Turn` 77 e não há `--turns`
- **THEN** são analisados os turnos 69 a 76

### Requirement: Relatório de cada turno
Para cada turno analisado, a ferramenta SHALL escrever no terminal, nesta ordem:
1. o turno, a vida e o tamanho da cobra analisada e o número de adversárias vivas;
2. o tabuleiro em ASCII com y crescendo para cima e a legenda dos testes de estratégia: `E`/`e` para a cabeça e o corpo da cobra analisada, `t` para a cauda dela, `R`/`r` para a cabeça e o corpo das adversárias, `*` para comida, `h` para hazard e `.` para casa vazia, com as coordenadas nas margens;
3. a direção jogada e a latência;
4. as candidatas do filtro e, para cada direção eliminada, o motivo (pescoço, parede, corpo ou vida);
5. com prazo de `--deep-budget-ms`, para cada candidata na ordem da decisão: camada, nota, as parcelas da nota diferentes de 0, `area`, `survival_depth` sobre a profundidade alvo, `survives`, `roomy`, `risky` e `kill_chance`, além da escolha heurística e do motivo dela;
6. a direção que a cobra devolve com o orçamento de `--budget-ms`, pelo mesmo caminho do `/move` e com o prazo contado do início dessa chamada. O orçamento efetivo é `min(0,4 × 500, --budget-ms)`, como em produção;
7. num duelo com mais de uma candidata: o valor da busca para cada candidata em cada profundidade de 1 até a última que terminou dentro de `--deep-budget-ms`, sem passar de `MAX_SEARCH_DEPTH`. Uma profundidade interrompida pelo prazo é descartada. Cada valor de fim de jogo SHALL ser marcado: `VENCE` quando a adversária morre dentro do horizonte, `PERDE` quando a cobra analisada morre e `EMPATE` quando as duas morrem.

As medições e a decisão do item 5 SHALL ser as mesmas que a cobra usa, sem reimplementação na ferramenta.

#### Scenario: Turno 74 da partida do diagnóstico
- **WHEN** a ferramenta roda com `dc8c4f05-84ac-4554-98f6-94b22d5a8b4d --turns 72-76`
- **THEN** no turno 74 as candidatas são `left` e `right`, sem `up` (corpo) e `down` (pescoço), e a direção devolvida com o orçamento padrão é `right`

### Requirement: Divergência destacada
Quando a direção jogada é conhecida, o filtro deixa ao menos uma candidata e a direção jogada difere da direção devolvida com `--budget-ms`, o turno SHALL ser marcado em destaque no cabeçalho, e uma linha de resumo no fim SHALL listar os turnos divergentes, ou dizer que não houve nenhum.

#### Scenario: Turno 74 depois da correção da cauda
- **WHEN** o turno 74 da partida do diagnóstico é analisado, com a jogada de produção `left`
- **THEN** o turno 74 aparece em destaque, porque a escolha local é `right`, e entra no resumo

#### Scenario: Sem candidatas
- **WHEN** o filtro não deixa nenhuma candidata num turno
- **THEN** a direção devolvida aparece marcada como sorteio, e o turno não é marcado como divergente

### Requirement: Uso só local e sem efeitos
A ferramenta SHALL escrever apenas no terminal. Ela não grava arquivos, não muda nada no repositório e não emite o log de produção da cobra durante a análise. Ela SHALL usar só a biblioteca padrão e as dependências que já estão em `requirements.txt` e `requirements-dev.txt`. Ela fica fora de `src/` e por isso não entra no pacote da Lambda.

#### Scenario: Sem log de produção
- **WHEN** a ferramenta analisa um turno
- **THEN** nenhuma linha JSON do evento `move` aparece na saída
