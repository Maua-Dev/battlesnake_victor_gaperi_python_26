## Why

Perdemos para uma cobra que junta heurística e busca adversarial no duelo, e a maior parte das partidas termina num duelo. Além disso, a nossa medição de espaço trata todo corpo como parede permanente, menos a cauda: a cobra recusa caminhos que estariam livres a tempo, e `area >= tamanho` não prova que ela sobrevive. Também já perdemos partidas por timeout: a Lambda tem 128 MB, fica em sa-east-1, e em partidas com 8 cobras todos os turnos estouraram os 500 ms. Qualquer busca nova precisa de um prazo rígido e de uma resposta pronta antes de começar.

Pré-requisito: a mudança "enxugar logs e otimizar encurraladas" já está aplicada e arquivada (`region_sizes` nas rivais encurraladas e um evento `move` só com `game_id`, `turn`, `move` e `timed_out_last_turn`).

## What Changes

- **Representação leve do tabuleiro** (`src/app/board_state.py`): casas como índices (`y * largura + x`), uma tabela de vizinhos por tamanho de tabuleiro na ordem canônica, cobras com corpo em índices, comida e hazards. O dano de hazard vem de `game.ruleset.settings.hazardDamagePerTurn`, com 0 quando ausente. O `GameState` é convertido uma vez por jogada, e nenhum objeto Pydantic entra nos laços quentes.
- **Ocupação temporal**: `free_after[casa]` diz em quantos movimentos a casa fica livre. A área da própria cobra, o território (Voronoi) e o A* até a comida passam a usar uma BFS temporal, em que uma casa só pode ser alcançada na distância `d` se `free_after <= d`. As rivais encurraladas continuam com obstáculos estáticos.
- **Sobrevivência por DFS**: para cada candidata, uma busca em profundidade simula o próprio corpo andando e devolve `survival_depth` e `survives`. A camada de segurança passa a usar `roomy = (área temporal >= tamanho) OU survives`.
- **Fome e hazards no filtro**: a direção é eliminada quando a vida chegaria a 0 com o movimento, conforme a ordem oficial das regras. Hazards ganham a medição `hazard`, com penalidade, e entram na conta de vida da política de fome.
- **Novas medições e pesos**: entram `survival_depth`, `survives`, `hazard`, `rival_territory_pct` e `food_owned`, todas com valor padrão. Entram também os pesos `W_SURVIVAL`, `W_HAZARD` e `W_SQUEEZE`. A comida alvo passa a ser escolhida pelo território do turno, e não mais pela Manhattan até as cabeças rivais.
- **Simulador de turno** (`src/app/simulator.py`): segue a ordem das regras oficiais do modo standard e não gera comida nova.
- **Busca no duelo** (`src/app/search.py`): minimax com poda alpha-beta e movimentos simultâneos, só com exatamente uma adversária viva, por aprofundamento iterativo. A busca só **veta** a escolha heurística: troca-a apenas quando ela perde ou empata dentro do horizonte e outro movimento vale mais. Com os pesos iniciais da folha, uma busca que sempre escolhesse o maior valor trocava a escolha heurística com fome pela comida da rival.
- **Controle de tempo** (`src/app/clock.py`): o prazo começa quando o `/move` chega, antes da validação do payload. O orçamento é `min(0.4 × timeout, SEARCH_BUDGET_MAX_MS)`, com 120 ms por padrão, e `SEARCH_BUDGET_MAX_MS` também pode vir de uma variável de ambiente. A escolha heurística fica pronta antes da busca, e a busca só a veta com o resultado de uma profundidade inteira que terminou dentro do prazo. O relógio é `time.perf_counter` e pode ser trocado nos testes.
- **Documentação**: novo `docs/estrategia.md`.
- O log não muda. `decision.py` continua sem importar `models.py`, e a fronteira com o Jev fica onde está.

### Testes antigos que mudam

Por decisão do usuário, os testes antigos de cenário rodam **sem a busca**: uma fixture explícita `sem_busca` zera `MAX_SEARCH_DEPTH`. Eles continuam testando a heurística, e a busca ganha cenários próprios. A tabela abaixo registra o que de fato mudou ao rodar a suíte (tarefa 12.3).

**Mudaram por construção** (a área temporal enxerga a fuga perseguindo uma cauda):

| Teste | Antes → depois | Motivo |
|---|---|---|
| `test_estrategia_v2.py::test_area_de_bolsao_menor_que_a_cobra` | `down`: área 2 e `roomy` falso → área grande e `roomy` verdadeiro | De (0,0) a cobra persegue a própria cauda: (1,0) libera em 1 movimento e (2,0) em 2, e por eles ela sai para o resto do tabuleiro. A afirmação da fuga virou `test_fuga_perseguindo_a_propria_cauda`, e `test_area_de_bolsao_menor_que_a_cobra` passou a usar o bolsão de verdade (`left` com área 2 e `roomy` falso). |
| `test_estrategia_v2.py::test_beco_versus_cabeca_a_cabeca` | `up` → `down` | Pelo mesmo motivo, `down` passou a ter espaço e não é arriscada (camada 0). O cenário virou `test_persegue_a_propria_cauda`, com resposta `down`. O conflito "beco contra cabeça a cabeça" ganhou um tabuleiro com um bolsão real, cuja resposta é a direção arriscada (`down`). |
| `test_telemetry.py::test_logs_nao_mudam_a_decisao[beco_versus_cabeca_a_cabeca]` | `up` → `down` | O caso passou a usar o tabuleiro novo do bolsão real, com resposta `down`. |
| `test_estrategia.py::test_evita_o_beco` | `down` → `down`, com outro tabuleiro | Com o tabuleiro antigo o teste continuou passando, mas pela nota: a cauda empilhada da rival em (4,10) libera em 2 movimentos, e `up` deixou de ser bolsão (área 117 e `roomy`). O teste trocou de tabuleiro para um bolsão cercado por segmentos que liberam tarde. O mesmo vale para o caso `beco` de `test_logs_nao_mudam_a_decisao`. |

**Em risco, decididos pela margem da nota:** `test_estrategia_v2.py::test_nao_morde_a_isca`, `test_peso_alterado_muda_a_escolha`, `test_comida_contestada_get_move`, `test_fome_por_disputa_de_tamanho_segue_a_comida`, `test_encurrala_a_rival_menor` e `test_ataca_a_rival_menor`. Nenhum mudou.

**Ajustes sem mudança de resultado:**
- `pytestmark = pytest.mark.usefixtures("sem_busca")` em `test_estrategia.py` e `test_estrategia_v2.py`, e a mesma fixture em `test_telemetry.py::test_logs_nao_mudam_a_decisao`.
- `test_telemetry.py::test_falha_na_escolha_do_movimento`: o substituto de `choose_move` passou a aceitar `**kwargs`, porque `choose_move` recebe o prazo.
- `test_regioes.py::test_evaluate_moves_ao_menos_5x_mais_rapido_que_a_referencia`: a razão ficou em cerca de 13x (medido localmente), e o teste não mudou.

Os 20 testes do template e o `test_lambda.py` não mudam.

## Capabilities

### New Capabilities
- `representacao-do-tabuleiro`: índices, tabela de vizinhos e leitura do dano de hazard.
- `simulacao-de-turno`: avançar um turno conforme as regras oficiais do modo standard.
- `busca-no-duelo`: minimax alpha-beta com movimentos simultâneos quando há exatamente uma adversária.
- `controle-de-tempo`: o prazo da jogada, o orçamento, o aprofundamento iterativo e a resposta de reserva.

### Modified Capabilities
- `caracteristicas-de-movimento`: ocupação temporal, BFS temporal na área, no território e na comida, sobrevivência por DFS, `roomy` nova e as medições `hazard`, `rival_territory_pct` e `food_owned`.
- `decisao-de-movimento`: as parcelas `survival`, `hazard` e `squeeze` na pontuação e na explicação, e o cenário "Beco versus cabeça a cabeça" com um bolsão real.
- `estrategia-de-movimento`: o filtro de vida e hazard, a comida alvo pelo território, a fome com dano de hazard, a busca no duelo como refinamento depois da decisão, o determinismo condicionado ao relógio, a meta de tempo da heurística com 8 cobras e as constantes novas.

## Impact

- **Código novo:** `src/app/board_state.py`, `occupancy.py`, `survival.py`, `simulator.py`, `search.py` e `clock.py`.
- **Código alterado:**
  - `features.py`: medições novas, comida alvo e uso do `BoardState`;
  - `decision.py`: campos com valor padrão e as parcelas novas;
  - `logic.py`: o filtro de vida e hazard, o prazo e a busca em `choose_move`;
  - `main.py`: o instante de chegada, marcado no middleware e repassado ao `/move`;
  - `config.py`: os pesos, limites e orçamento novos.
- **Testes:** novos arquivos para o tabuleiro, a ocupação, a sobrevivência, o simulador, a busca e o tempo. `tests/conftest.py` ganha as fixtures `sem_busca` e de relógio falso, e `tests/helpers.py` ganha hazards e settings no `make_game`.
- **Dependências:** nenhuma, só a biblioteca padrão.
- **Deploy:** nada muda em `iac/`, nos workflows nem nas variáveis de ambiente da Lambda. `SEARCH_BUDGET_MAX_MS` é lida do ambiente com padrão 120 ms no código. Defini-la na Lambda é uma decisão manual e fica fora desta mudança.
- **Fora de escopo:**
  - busca com 3 ou mais cobras;
  - gerar comida na simulação;
  - mudar a infraestrutura ou a região;
  - a integração com o Jev;
  - mudar os logs.
