"""Constantes de ajuste da estratégia, todas num lugar só.

Os valores abaixo são o ponto de partida e serão calibrados em partidas na
Arena. Quem usa uma constante lê `config.NOME` na hora do uso, sem copiar o
valor com `from .config import NOME`: assim um teste consegue trocá-la.
"""

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
