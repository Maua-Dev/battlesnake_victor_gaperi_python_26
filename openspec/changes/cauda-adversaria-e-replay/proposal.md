## Why

Na partida `dc8c4f05-84ac-4554-98f6-94b22d5a8b4d` a cobra (tamanho 11, vida 93) morreu por self-collision no turno 77, num duelo contra uma rival de tamanho 4, sem nenhum timeout (latência entre 154 e 236 ms). No turno 74 o filtro de `get_move` devolveu só `left`, que levava a um bolsão de 2 casas, porque trata todo o corpo das adversárias como ocupado, cauda incluída:

```
y=5  e e e t .
y=4  e . E r R      minha cabeça em (2,4); a cauda da rival está em (3,4)
y=3  e . e r r      corpo da rival: (4,4) (4,3) (3,3) (3,4)
y=2  e e e . .
     0 1 2 3 4
```

Pelas regras oficiais, a cauda que não está empilhada sempre sai do lugar, mesmo que a rival coma, porque o movimento vem antes da alimentação. `right`, para (3,4), era seguro, e `simulator.safe_moves` devolve `["left", "right"]` nesse tabuleiro. A rival ainda era menor: se voltasse para (3,4), morreria no cabeça a cabeça. Nos turnos 72 e 73, a DFS de sobrevivência e a busca (até profundidade 8) não viram derrota porque contavam com essa saída. O filtro, mais conservador que o simulador, vetou uma saída que as outras camadas consideravam válida. As camadas da cobra discordavam sobre as regras.

Para achar esse erro foi preciso baixar os frames da Arena e rodar a lógica à mão, turno a turno. Uma ferramenta de replay deixa essa investigação repetível. Ela também serve para a divergência que ainda está aberta: no turno 72 a lógica local escolhe `right` (food + kill), mas em produção a cobra jogou `up`. Pode ser o prazo de 120 ms cortando a DFS ou o A* na Lambda, ou uma versão implantada diferente do HEAD.

## What Changes

**Parte 1: cauda das adversárias no filtro**
- Uma regra única de ocupação, no simulador: as casas que continuam ocupadas depois do turno, qualquer que seja o movimento das cobras, são todos os segmentos de cada cobra viva menos o último. Uma cauda empilhada continua ocupada, porque o penúltimo segmento está na mesma casa.
- O filtro de `get_move` passa a usar essa regra para o próprio corpo e para as adversárias. A cauda de uma adversária que não está empilhada deixa de bloquear. A cauda empilhada continua bloqueando. `simulator.safe_moves` usa a mesma função.
- O filtro passa a ser uma função (`logic.filter_moves`) que devolve, para cada direção, o motivo da eliminação ou nada. `get_move` continua com a mesma ordem de checagens e o mesmo sorteio de emergência. A ferramenta de replay usa essa função para mostrar os motivos.
- Entrar na cauda de uma adversária continua sujeito às outras medições: com a cabeça dela vizinha da casa e tamanho maior ou igual, a direção é `risky`; com tamanho menor, vale `kill_chance`. Nada muda nas medições.
- `grid.opponent_cells` fica sem uso e sai.
- `docs/estrategia.md`: a seção "Diferenças em relação às regras" deixa de listar o filtro, e o passo 1 do fluxo deixa de dizer "a cauda delas inclusive".

**Parte 2: ferramenta de replay** (`scripts/replay.py`, só para uso local)
- `python scripts/replay.py <game_id> [--engine URL] [--snake ID|NOME] [--turns A-B] [--budget-ms 120] [--deep-budget-ms 5000]`.
- Baixa a partida e todos os frames da Arena (paginando), converte cada frame no JSON do `/move` e valida com `GameState`.
- Para cada turno: tabuleiro em ASCII, a direção jogada de fato e a latência, as candidatas e o motivo de cada eliminação, as medições e a decisão de cada candidata com prazo folgado, o que `get_move` devolve com o orçamento de produção e, num duelo, o valor da busca por candidata e profundidade dentro de um prazo folgado.
- Destaca os turnos em que a direção jogada difere da escolha local.
- Usa só a biblioteca padrão para HTTP e não entra no pacote da Lambda.
- `docs/estrategia.md` ganha a seção "Analisar uma partida".

### Testes que mudam de resultado

Medido rodando a suíte atual com a cauda das adversárias liberada no filtro (294 testes, 2 mudam):

| Teste | Antes → depois | Motivo e ajuste |
|---|---|---|
| `test_estrategia.py::test_entra_na_propria_cauda` | `left` → `right` | O bloqueio `[(8,10),(7,10),(6,10)]` tem a cauda em (6,10), que não está empilhada e agora conta como livre. `right` vira candidata e vence na nota. O teste quer "a única saída é a própria cauda", então o bloqueio ganha um segmento, `[(8,10),(7,10),(6,10),(6,9)]`, e (6,10) passa a ser corpo do meio. Com isso a resposta volta a ser `left` (conferido). |
| `test_telemetry.py::test_logs_nao_mudam_a_decisao[entra_na_cauda]` (`state5-left`) | `left` → `right` | Mesmo tabuleiro do teste acima. Recebe o mesmo bloqueio de 4 segmentos e continua esperando `left`. |

Nenhum outro teste de estratégia, de busca ou do simulador muda. Os 20 testes do template e `test_lambda.py` não mudam.

## Capabilities

### New Capabilities
- `analise-de-partida`: a ferramenta local que baixa uma partida da Arena e reexecuta a lógica da cobra turno a turno, com o diagnóstico de cada direção.

### Modified Capabilities
- `estrategia-de-movimento`: o filtro libera a cauda das adversárias que não está empilhada, usa a mesma regra de ocupação do simulador, e as candidatas do filtro passam a coincidir com as direções que não são morte certa da busca. Muda também o cenário "Única saída é a própria cauda", cujo bloqueio deixava de bloquear.

## Impact

- **Código alterado:** `src/app/logic.py` (`filter_moves`, `get_move` e `choose_move` com o `BoardState` opcional), `src/app/simulator.py` (`occupied_after_turn`, usada por `safe_moves`), `src/app/grid.py` (sai `opponent_cells`) e `src/app/search.py` (`minimax_value` ganha um prazo opcional, só para o replay; a busca da cobra não muda).
- **Código novo:** `scripts/__init__.py`, `scripts/replay.py`, `tests/scripts/test_replay.py`, `tests/fixtures/` com frames da partida (nomes, autores e ids das outras cobras anonimizados).
- **Testes alterados:** os 2 da tabela acima, só no tabuleiro.
- **Docs:** `docs/estrategia.md` (fluxo, "Diferenças em relação às regras", "Analisar uma partida") e `CLAUDE.md` (o filtro na seção de arquitetura, a ferramenta de replay nos comandos).
- **Sem mudança:** pesos, camadas, DFS, o comportamento da busca, o sorteio da emergência, o log de produção, `decision.py` (só importa `config`), imports relativos em `src/app/`, `requirements.txt`, a IaC e os workflows.
- **Comportamento em produção:** em toda jogada em que a cabeça é vizinha da cauda não empilhada de uma adversária, essa direção passa a ser candidata.
