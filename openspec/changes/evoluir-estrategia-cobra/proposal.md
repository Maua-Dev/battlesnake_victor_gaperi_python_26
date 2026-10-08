## Why

Nas partidas reais a cobra fica do lado do tabuleiro em que nasceu e só come quando a vida cai abaixo de 80. Por isso fica com 3 ou 4 segmentos enquanto as rivais crescem. Com quase toda rival maior ou igual, o filtro de cabeça a cabeça e as `threat_zones` fecham cada vez mais saídas, até uma rival maior encurralar a cobra. O flood fill mede espaço livre, mas não diz se a rival chega lá antes, e a cobra nunca ataca. A próxima mudança vai entregar a escolha do movimento a um modelo de decisão externo (Jev). Antes disso, o cálculo das características de cada direção precisa estar separado da escolha.

## What Changes

- **Decisão em três etapas** testáveis sozinhas:
  1. *Candidatas* (`get_move`): pescoço, paredes, próprio corpo e corpo das adversárias continuam eliminando direções. O cabeça a cabeça com rival maior ou igual **deixa de eliminar** e só marca a direção como arriscada.
  2. *Características* (novo `src/app/features.py`): `evaluate_moves(state, candidates)` devolve uma `MoveFeatures` por direção (risky, area, roomy, territory_pct, food_step, food_dist, trapped_rivals, kill_chance, hunt_step, danger, center_dist). Essa etapa não decide nada.
  3. *Decisão* (novo `src/app/decision.py`): `decide(features, context)`, uma pontuação determinística por camadas de segurança. Ela não conhece `GameState` nem `models.py`, porque é a peça que o Jev vai substituir.
- **Território (Voronoi)**: novo `src/app/voronoi.py`, uma BFS multi-origem. Cada casa vai para a cobra que chega primeiro, e o empate fica com a estritamente maior.
- **Ataque**: detecção de rivais encurraladas (`trapped_rivals`), chance de matar uma rival menor no cabeça a cabeça (`kill_chance`) e aproximação da rival menor mais próxima (`hunt_step`).
- **Nova política de fome** (**BREAKING** de comportamento, não de API): sai `HUNGER_THRESHOLD = 80`. A cobra passa a ter fome por sobrevivência (vida menor que a distância do A* até a comida alvo + 15), por disputa de tamanho (não estar 2 segmentos à frente da maior rival) ou por taxa de crescimento (ao menos uma comida a cada 8 turnos).
- **Comida alvo**: a comida mais próxima que a cobra alcança antes de qualquer rival maior ou igual. Se não houver nenhuma, a mais próxima alcançável.
- **Camadas de segurança** na decisão: não arriscada e com espaço > arriscada e com espaço > não arriscada sem espaço > arriscada sem espaço. Um cabeça a cabeça incerto passa a ser preferível a um beco certo.
- **Constantes centralizadas** em novo `src/app/config.py` (pesos, margens e intervalos).
- **Correções**:
  - cauda empilhada: logo depois de comer, a cauda não sai do lugar e deixa de ser tratada como livre, tanto a própria quanto a das rivais nos obstáculos;
  - o A* passa a desviar das `threat_zones`.
- **Desempenho**: a jogada completa leva menos de 50 ms num 19x19 com 4 cobras. A meta anterior era 1 ms. O resto do orçamento de 500 ms fica para o Jev.

### Testes da versão anterior revisados de propósito

| Teste (`tests/app/test_estrategia.py`) | O que muda | Motivo |
|---|---|---|
| `test_com_fome_vai_para_a_comida` | a vida passa de 50 para 10 | Pela nova política, vida 50 com a comida a 3 passos não é fome (50 ≥ 3 + 15). Sem fome, a cobra responderia `up`. Com vida 10 a regra de sobrevivência dispara e a resposta continua `left`. |
| `test_sem_fome_ignora_a_comida` | nada (só revisado) | Continua `up`: vida 100 ≥ 3 + 15, turno 1, tamanho 3 e sem rivais, então não há fome. As três direções empatam e vence a primeira da ordem. |
| `test_evita_o_beco` | a rival ganha um segmento repetido no fim (acabou de comer) e o comentário é reescrito | Com a cauda da rival saindo do lugar, o "bolsão" de `up` deixa de existir (área 106). O teste continuaria verde por outro motivo e deixaria de testar o beco. Com a cauda empilhada o bolsão volta a ter 2 casas, `up` cai na camada sem espaço e `down` vence `left` pelo território. |

Os outros 10 testes de `test_estrategia.py`, os 20 do template e o `test_lambda.py` não mudam.

## Capabilities

### New Capabilities
- `caracteristicas-de-movimento`: o que é medido para cada direção candidata (risco, área, território, comida, rivais encurraladas, caça, perigo, centro) e os algoritmos de território e de rival encurralada.
- `decisao-de-movimento`: como uma lista de características vira um movimento (camadas de segurança, pontuação, desempate), sem depender do estado bruto do jogo.

### Modified Capabilities
- `estrategia-de-movimento`:
  - o cabeça a cabeça desfavorável passa de filtro a marcação;
  - a cauda empilhada deixa de ser casa livre;
  - "com fome, ir até a comida mais próxima" e "maximizar o espaço alcançável" dão lugar à política de fome, à comida alvo e ao fluxo candidatas → características → decisão;
  - a meta de tempo passa de 1 ms para 50 ms;
  - entra o requisito das constantes centralizadas.

## Impact

- **Código:**
  - `src/app/logic.py`: o filtro de cabeça a cabeça vira marcação, entra a regra da cauda empilhada, `choose_move` passa a delegar a `features` e `decision`, e `HUNGER_THRESHOLD` sai;
  - módulos novos `src/app/config.py`, `src/app/voronoi.py`, `src/app/features.py` e `src/app/decision.py`;
  - `src/app/grid.py` ganha funções auxiliares (obstáculos com a regra da cauda).
- **Testes:**
  - novo `tests/app/test_estrategia_v2.py`;
  - `tests/helpers.py` ganha um montador de `MoveFeatures`, se for preciso;
  - os três testes da tabela acima são revisados.
- **Dependências:** nenhuma nova, só a biblioteca padrão.
- **Deploy:** nada muda na IaC nem nos workflows. Imports relativos dentro de `src/app/` continuam garantidos por `test_lambda.py`.
- **Fora de escopo:** integração com o Jev, minimax, alpha-beta, MCTS, hazards e modos de jogo diferentes do standard, e ajuste fino dos pesos (os valores iniciais serão calibrados na Arena).
