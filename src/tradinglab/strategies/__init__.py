from .base import StrategyResult, clamp_target
from .meanrev import meanrev_signal
from .trend import trend_signal

STRATEGIES = {
    "trend": trend_signal,
    "meanrev": meanrev_signal,
}

__all__ = ["StrategyResult", "clamp_target", "trend_signal", "meanrev_signal", "STRATEGIES"]
