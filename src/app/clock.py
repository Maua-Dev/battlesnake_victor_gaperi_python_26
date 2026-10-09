"""Relógio e prazo da jogada.

Toda leitura de tempo passa por clock.now(), chamado na hora do uso (nunca
`from .clock import now`), para que um teste troque o relógio com
monkeypatch.setattr(clock, "now", falso).
"""
import time
from dataclasses import dataclass

from . import config


def now() -> float:
    """Instante atual em segundos, de um relógio monotônico."""
    return time.perf_counter()


def budget_ms(timeout: int) -> float:
    """Orçamento da jogada: min(fração do timeout, teto), em ms."""
    return min(config.SEARCH_BUDGET_FRACTION * timeout, config.SEARCH_BUDGET_MAX_MS)


@dataclass(frozen=True)
class Deadline:
    """Prazo da jogada: `start` (em segundos de now()) mais `budget_ms`."""
    start: float
    budget_ms: float

    def remaining_ms(self) -> float:
        """Milissegundos que faltam; negativo depois do prazo."""
        return self.budget_ms - (now() - self.start) * 1000

    def expired(self) -> bool:
        """Diz se o prazo já passou."""
        return self.remaining_ms() <= 0
