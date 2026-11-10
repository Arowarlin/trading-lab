from .base import StrategyResult, clamp_target
from .meanrev import meanrev_signal
from .sector_momentum import sector_momentum_signal
from .trend import trend_ls_signal, trend_signal

STRATEGIES = {
    "trend": trend_signal,
    "trend-ls": trend_ls_signal,
    "meanrev": meanrev_signal,
    "sector_momentum": sector_momentum_signal,
}

__all__ = [
    "StrategyResult",
    "clamp_target",
    "trend_signal",
    "trend_ls_signal",
    "meanrev_signal",
    "sector_momentum_signal",
    "STRATEGIES",
]
