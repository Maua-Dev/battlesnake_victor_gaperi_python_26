## Why

Hoje a cobra só evita o próprio pescoço, as paredes e o próprio corpo, e sorteia entre o que sobra. Ela entra em adversárias, perde confrontos de cabeça a cabeça, se tranca em becos e morre de fome. A proposta é replicar a estratégia da cobra campeã: filtrar as direções seguras, buscar comida com A* quando estiver com fome e, sem fome, escolher a direção que maximiza o espaço alcançável (flood fill).

## What Changes

- Três regras novas de filtro em `get_move`, aplicadas antes de montar `safe_moves`:
  - a própria cauda deixa de ser obstáculo, porque ela anda junto no mesmo turno;
  - toda casa ocupada por uma adversária (cauda incluída) passa a ser insegura;
  - toda casa que a cabeça de uma rival de tamanho maior ou igual alcança no próximo turno passa a ser insegura.
- O sorteio final entre as direções seguras é trocado por `chosen = choose_move(state, safe_moves)`, que é determinístico:
  - com fome (`health < 80`) e com comida no tabuleiro, segue o primeiro passo do caminho A* até a comida mais próxima, desde que esse passo esteja em `safe_moves`;
  - nos outros casos, escolhe a direção segura com a maior área alcançável, desempatando pela proximidade da comida quando estiver com fome e, depois, pela ordem canônica `up, down, left, right`.
- Módulos novos: `src/app/grid.py` (tipo `Pos` e utilitários de tabuleiro), `src/app/floodfill.py` e `src/app/astar.py`.
- Testes novos: `tests/helpers.py`, `tests/app/test_estrategia.py` (13 cenários determinísticos) e `tests/app/test_lambda.py` (guarda contra imports absolutos que quebram a Lambda).
- O template não é reescrito. Os blocos de pescoço, paredes, próprio corpo e o fallback aleatório quando não há direção segura continuam onde estão. A única mudança dentro de um bloco existente é pular a própria cauda no bloco 3.

Nenhuma mudança é **BREAKING**: o contrato HTTP (`/`, `/start`, `/move`, `/end`) não muda e os 20 testes do template continuam passando sem alteração.

## Capabilities

### New Capabilities
- `estrategia-de-movimento`: como a cobra decide o movimento a cada turno. Cobre as regras de segurança (pescoço, paredes, corpos, cabeça a cabeça), a busca de comida quando está com fome, a maximização de espaço e as regras de desempate.
- `empacotamento-lambda`: garantia de que o pacote `app` importa com `src/` como raiz, como acontece na Lambda.

### Modified Capabilities
<!-- Nenhuma: openspec/specs/ ainda está vazio. -->

## Impact

- **Código:** `src/app/logic.py` (só acréscimos, mais a linha do `chosen` e o `continue` da cauda); novos `src/app/grid.py`, `src/app/floodfill.py` e `src/app/astar.py`.
- **Testes:** novos `tests/helpers.py`, `tests/app/test_estrategia.py` e `tests/app/test_lambda.py`. A suíte passa de 20 para 34 testes.
- **Dependências:** nenhuma nova. Só biblioteca padrão (`collections.deque`, `heapq`).
- **Deploy:** nenhuma mudança na IaC nem nos workflows. O teste da Lambda roda no `pytest` do CI/CD e impede o deploy se algum import absoluto escapar.
- **Desempenho:** o orçamento é de cerca de 500 ms por jogada; a meta é responder em menos de 1 ms num tabuleiro 19x19 com 4 cobras.
- **Fora de escopo:** cauda empilhada logo depois de comer (continua sendo liberada), `threat_zones` no A* (só o primeiro passo é validado), estratégia para quando não há direção segura (mantém o sorteio), hazards e os campos de `info()`.
