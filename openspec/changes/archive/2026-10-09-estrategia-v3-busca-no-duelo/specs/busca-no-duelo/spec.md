## Purpose

Define a busca adversarial que, no duelo (exatamente uma adversária viva), olha alguns turnos à frente com movimentos simultâneos e pode vetar a escolha heurística quando ela perde ou empata dentro do horizonte da busca. O orçamento de tempo dela está em `controle-de-tempo`.

## ADDED Requirements

### Requirement: Só no duelo
A busca SHALL rodar apenas quando há exatamente uma adversária viva e ao menos duas candidatas. Com nenhuma adversária, com duas ou mais, ou com uma única candidata, a resposta SHALL ser a escolha heurística (ver `decisao-de-movimento`).

#### Scenario: Duas adversárias
- **WHEN** o tabuleiro tem a cobra e duas adversárias vivas e há várias candidatas
- **THEN** a busca não roda e a resposta é a escolha heurística

#### Scenario: Sem adversária
- **WHEN** o tabuleiro tem só a cobra
- **THEN** a busca não roda

#### Scenario: Única candidata
- **WHEN** há exatamente uma adversária e uma única candidata
- **THEN** a busca não roda e a resposta é essa candidata

### Requirement: Movimentos simultâneos com pior caso
Cada nível da busca SHALL ser um turno inteiro: para cada movimento da cobra, cada resposta da adversária é simulada no mesmo turno (ver `simulacao-de-turno`). O valor de um movimento da cobra SHALL ser o pior valor entre as respostas da adversária. A poda alpha-beta SHALL ser aplicada entre as respostas da adversária e entre os movimentos da cobra, e não SHALL mudar o valor encontrado.

#### Scenario: Movimento que não perde para nenhuma resposta
- **WHEN** num duelo a candidata de maior nota heurística perde para alguma resposta da adversária dentro da profundidade buscada, e outra candidata não perde para nenhuma resposta
- **THEN** a busca escolhe a outra candidata

#### Scenario: Armadilha em dois turnos
- **WHEN** num duelo a escolha heurística entra num corredor que a adversária fecha em 2 turnos, com a cobra presa e sem espaço para o corpo, e outra candidata não leva a derrota dentro da profundidade buscada
- **THEN** com profundidade 3 ou mais, a busca não escolhe a direção do corredor

#### Scenario: Poda não muda o valor
- **WHEN** a busca com poda e o minimax sem poda avaliam os mesmos tabuleiros pequenos gerados com semente fixa, com a mesma profundidade
- **THEN** o valor de cada raiz é o mesmo nas duas versões

### Requirement: Candidatas dentro da busca
Na raiz, os movimentos da cobra SHALL ser as candidatas que passaram no filtro de `estrategia-de-movimento`. Nos níveis internos, e para a adversária em todos os níveis, os movimentos SHALL ser as direções que não são morte certa: dentro do tabuleiro, fora do pescoço e fora de casas ocupadas por segmentos que continuam no lugar depois do turno, qualquer que seja o movimento das outras cobras. Se nenhuma direção sobrar para uma cobra, SHALL ser simulada a primeira direção da ordem canônica, que a elimina.

#### Scenario: Adversária sem saída
- **WHEN** a adversária tem todas as direções bloqueadas por parede ou corpo
- **THEN** a busca simula para ela a primeira direção da ordem canônica, e o resultado é a eliminação dela

### Requirement: Valores terminais
Depois de cada turno simulado, a profundidade `p` é o número de turnos desde a raiz. Os valores terminais SHALL ser:
- só a adversária eliminada: vitória, `WIN - p`, com `WIN` = 1.000.000;
- só a cobra eliminada: derrota, `-WIN + p`;
- as duas eliminadas no mesmo turno: empate, `DRAW` = -500.000.

Vencer antes vale mais que vencer depois, e perder depois vale mais que perder antes.

#### Scenario: Cabeça a cabeça contra menor
- **WHEN** a cobra, de tamanho 4, tem cabeça em (5,5) e corpo [(5,5),(5,4),(5,3),(5,2)], e a adversária, de tamanho 3, ocupa [(7,5),(8,5),(9,5)]
- **THEN** com profundidade 1, o valor de `right` não é derrota nem empate

#### Scenario: Cabeça a cabeça contra igual
- **WHEN** a cobra ocupa [(5,5),(5,4),(5,3)] e a adversária, de tamanho 3, ocupa [(7,5),(8,5),(9,5)]
- **THEN** com profundidade 1, o valor de `right` é `DRAW`, e a busca não escolhe `right`

#### Scenario: Vitória mais cedo
- **WHEN** um movimento vence no turno 1 e outro vence no turno 3
- **THEN** o primeiro vale `WIN - 1` e o segundo vale `WIN - 3`

### Requirement: Avaliação das folhas
Ao atingir a profundidade da iteração sem fim de jogo, o estado SHALL ser avaliado por uma soma ponderada, com todos os pesos no módulo de configuração, de:
- diferença entre o território da cobra e o da adversária, pelo território temporal (ver `caracteristicas-de-movimento`);
- área temporal da cobra;
- diferença de tamanho;
- distância até a comida mais próxima, com peso maior quanto menor for a vida (penalidade);
- vida;
- distância de Manhattan até o centro (penalidade).

O valor absoluto de toda avaliação de folha SHALL ser menor que o de `DRAW`.

#### Scenario: Folha nunca vale mais que um fim de jogo
- **WHEN** uma folha é avaliada em qualquer estado
- **THEN** o valor fica entre `DRAW` e `-DRAW`, sem incluir os extremos

### Requirement: Veto da escolha heurística
Ao fim de cada profundidade completa, a resposta da busca SHALL ser a escolha heurística, a menos que o valor dela seja derrota ou empate (menor ou igual a `DRAW`) e algum outro movimento da raiz tenha valor maior. Nesse caso, a resposta SHALL ser o movimento de maior valor e, no empate de valor, o que vem antes na ordem heurística. Quando o valor da escolha heurística é maior que `DRAW`, as outras candidatas da raiz não precisam ser buscadas naquela profundidade.

A busca só evita derrotas e empates à vista: com os pesos iniciais da avaliação das folhas, o território domina a parcela da comida, e uma busca que sempre escolhesse o maior valor trocaria a escolha heurística com fome por um movimento rumo à comida da adversária.

#### Scenario: Escolha heurística que não perde é mantida
- **WHEN** num duelo a cobra tem vida baixa, a escolha heurística segue para uma comida que é da cobra, outra comida fica mais perto da adversária, e a escolha heurística não perde nem empata dentro da profundidade buscada
- **THEN** a resposta é a escolha heurística, mesmo que a avaliação das folhas prefira outro movimento

#### Scenario: Todas as candidatas perdem
- **WHEN** todas as candidatas da raiz perdem dentro da profundidade buscada, e a escolha heurística perde antes de outra candidata
- **THEN** a resposta é a candidata que perde mais tarde

### Requirement: Ordem de exploração
Em toda profundidade, a escolha heurística SHALL ser explorada primeiro na raiz, sem limite de poda, para que o valor dela seja exato. Se ela for vetada, as demais SHALL ser exploradas com o melhor movimento da profundidade anterior primeiro (quando não for a própria escolha heurística) e as outras na ordem heurística: camada, nota e ordem canônica. Nos níveis internos, a ordem SHALL ser a canônica. Em empate de valor entre os movimentos que substituiriam a escolha heurística, SHALL vencer o que vem antes na ordem heurística.

#### Scenario: Empate de valor
- **WHEN** a escolha heurística perde dentro da profundidade buscada e dois outros movimentos da raiz terminam a profundidade com o mesmo valor, maior que o dela
- **THEN** vence, entre os dois, o que tem a melhor posição na escolha heurística
