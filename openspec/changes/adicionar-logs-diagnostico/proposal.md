## Why

Nas partidas reais (9 cobras, adversárias "Scared Bot") a cobra sobe em linha reta e às vezes bate em outra cobra. Hoje não dá para saber por quê, porque o CloudWatch só recebe duas linhas de texto soltas por partida. Há três hipóteses, e os logs precisam separá-las:

1. **Timeout ou erro**: o servidor falhou ou demorou, e o motor escolheu no lugar da cobra (`up` no primeiro turno, repetição do último movimento depois).
2. **Emergência**: nenhuma direção era candidata, e o fallback sorteou uma das quatro.
3. **Decisão da lógica**: a própria estratégia escolheu aquele movimento, por exemplo num empate de pontuação desfeito pela ordem canônica, que favorece `up`.

O objetivo é responder, só com o CloudWatch Logs Insights, por que a cobra fez cada movimento de uma partida.

## What Changes

- **Novo `src/app/telemetry.py`**, com três responsabilidades:
  - `log_event(event, **fields)` grava uma linha por evento, contendo só um objeto JSON compacto;
  - o logger dedicado `battlesnake` tem handler próprio para stdout, `propagate=False` e nível vindo de `LOG_LEVEL`;
  - um contexto por requisição (`aws_request_id`, `game_id`, `turn`, `snake_id`) entra em todo evento.
- **Cinco eventos**:
  - `request`: um por requisição, emitido pelo middleware. Tem duração, `cold_start`, `remaining_ms` da Lambda e `slow`.
  - `start`: ruleset, mapa, timeout, tamanho do tabuleiro e adversárias.
  - `move`: exatamente um por turno. Tem a latência que o motor mediu no turno anterior, o movimento que a cobra de fato fez no turno anterior, o motivo de eliminação de cada direção, as medições, a camada e a pontuação de cada candidata, o movimento escolhido, o `reason` e `logic_ms`.
  - `end`: turnos, vitória, eliminação e sobreviventes.
  - `error`: tipo, mensagem e traceback de qualquer exceção em `/start`, `/move` ou `/end`, inclusive payload rejeitado pela validação. A exceção continua sendo relançada como hoje.
- **O vocabulário do evento `move` segue a decisão atual**: camadas de segurança, depois pontuação, depois desempate canônico. Não segue a estratégia antiga de flood fill e A*.
  - `reason` é um entre `only_option`, `layer`, `score`, `tie` e `emergency`.
  - `blocked_by` vem de `wall`, `neck`, `self` e `opponent`. O cabeça a cabeça não elimina mais direções: aparece como `risky` e na camada.
  - A fome aparece como `hungry` mais a lista dos critérios que dispararam (`starving`, `outsized`, `behind_schedule`).
- **Refatorações que não mudam o comportamento**, para expor o "porquê" sem duplicar lógica:
  - `get_move` passa a registrar o motivo de cada eliminação por um helper `mark_unsafe`;
  - `choose_move` passa a devolver o rastro da escolha (contexto, medições, comida alvo e `Decision`);
  - `decision.py` ganha `explain(features, ctx) -> Decision`, com camada, pontuação e parcelas de cada candidata e o `reason`. `decide` passa a delegar a ela e continua devolvendo `str`;
  - `features.py` expõe os critérios de fome sem mudar `DecisionContext`.
- **Os logs de texto atuais de `logic.py` saem**, substituídos pelos eventos.
- **`docs/logs.md`**: as consultas do Logs Insights e um roteiro para separar as três hipóteses.
- **Deploy não muda**: nada em `iac/` nem nos workflows. `LOG_LEVEL` e `SLOW_MS` são lidas do ambiente com padrões no código (`INFO` e `250`), e como a Lambda não as define, valem os padrões.

Nenhuma decisão da cobra muda: mesma entrada, mesmo movimento. Nenhum teste existente é alterado.

## Capabilities

### New Capabilities
- `telemetria-de-diagnostico`: o formato das linhas de log e os campos comuns, os eventos `request`, `start`, `move`, `end` e `error` com seus campos e tipos, o custo máximo por jogada, a garantia de não mudar decisões, a ausência de segredos e cabeçalhos, e a documentação das consultas.

### Modified Capabilities
- `decisao-de-movimento`: entra o requisito "Explicação da decisão". A decisão passa a poder devolver, além do movimento, a camada, a pontuação e as parcelas de cada medição e o motivo da escolha, sempre coerentes com `decide`.

## Impact

- **Código**:
  - novo `src/app/telemetry.py`;
  - `src/app/main.py`: o middleware mede e emite `request`, as rotas registram o contexto do jogo e emitem `error`, e entra um handler da validação que loga e mantém o 422;
  - `src/app/logic.py`: `mark_unsafe`, o rastro de `choose_move` e a emissão de `start`, `move` e `end`;
  - `src/app/decision.py`: `explain`, `Decision` e `score_terms`, ainda sem importar `models`;
  - `src/app/features.py`: os critérios de fome.
  - `src/app/models.py` não muda, porque `Snake.latency` já existe.
- **Testes**: novo `tests/app/test_telemetry.py`. Os 20 testes do template, `test_estrategia.py`, `test_estrategia_v2.py` e `test_lambda.py` não mudam.
- **Infra**: nada muda em `iac/` nem nos workflows (restrição do projeto: o deploy não é mexido).
- **Dependências**: nenhuma nova, só a biblioteca padrão.
- **Operação**: o volume de log sobe para cerca de uma linha JSON de alguns KB por turno.
- **Fora de escopo**:
  - métricas customizadas, dashboards e alarmes;
  - qualquer mudança de estratégia, inclusive um movimento de fallback em caso de exceção;
  - qualquer mudança de deploy (`iac/`, workflows), inclusive variáveis de ambiente da Lambda.
