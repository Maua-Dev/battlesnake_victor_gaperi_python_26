"""Constantes de ajuste da estratégia, todas num lugar só.

Os valores abaixo são o ponto de partida e serão calibrados em partidas na
Arena. Quem usa uma constante lê `config.NOME` na hora do uso, sem copiar o
valor com `from .config import NOME`: assim um teste consegue trocá-la.
"""
import os


def _positive_int_env(name: str, default: int) -> int:
    """Inteiro positivo da variável de ambiente, ou o padrão.

    Nunca lança: um erro aqui, no import, derrubaria a Lambda inteira.
    """
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


# --- Política de fome ---
# Sobrevivência: com fome se vida < distância até a comida alvo + margem.
HEALTH_MARGIN = 15
# Sem caminho até nenhuma comida: com fome se vida < este piso.
NO_PATH_HEALTH = 50
# Disputa de tamanho: com fome enquanto não estiver esta vantagem à frente
# da maior rival.
LENGTH_LEAD = 2
# Taxa de crescimento: ao menos uma comida a cada FEED_INTERVAL turnos,
# partindo do tamanho inicial do modo standard.
START_LENGTH = 3
FEED_INTERVAL = 8

# --- Pesos da pontuação da decisão ---
W_TERRITORY = 1.0  # por ponto percentual de território
W_FOOD = 40        # primeiro passo até a comida alvo, só com fome
W_TRAP = 60        # por rival encurralada
W_KILL = 50        # casa que uma rival menor pode ocupar
W_HUNT = 10        # aproxima da rival menor mais próxima, só sem fome
W_DANGER = 25      # rival maior ou igual a duas casas (penalidade)
W_CENTER = 1       # por casa de distância do centro, só sem fome (penalidade)
W_SURVIVAL = 20    # sobrevivência por DFS, proporcional à profundidade alcançada
W_HAZARD = 30      # nova cabeça num hazard sem comida (penalidade)
W_SQUEEZE = 0.5    # por ponto percentual de território da maior rival (penalidade)

# --- Sobrevivência por DFS ---
SURVIVAL_MAX_DEPTH = 12       # profundidade alvo: min(tamanho, este limite)
SURVIVAL_MAX_NODES = 400      # casas entradas por candidata
SURVIVAL_DEADLINE_EVERY = 32  # o prazo é conferido a cada tantos nós

# --- Busca no duelo ---
MAX_SEARCH_DEPTH = 20  # 0 desliga a busca
WIN = 1_000_000
DRAW = -500_000
# Pesos da avaliação das folhas.
EVAL_TERRITORY = 1.0  # por casa de território a mais que a rival
EVAL_AREA = 0.5       # por casa da minha área temporal
EVAL_LENGTH = 10      # por segmento a mais que a rival
EVAL_FOOD = 1.0       # por passo até a comida, escalado pela fome (penalidade)
EVAL_HEALTH = 0.1     # por ponto de vida
EVAL_CENTER = 0.5     # por casa de distância do centro (penalidade)

# --- Tempo ---
# Orçamento da jogada: min(fração do timeout, teto), em ms, contado desde a
# chegada do /move. O teto pode vir da variável de ambiente de mesmo nome.
SEARCH_BUDGET_FRACTION = 0.4
SEARCH_BUDGET_MAX_MS = _positive_int_env("SEARCH_BUDGET_MAX_MS", 120)
