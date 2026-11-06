from __future__ import annotations

from ..config import Settings
from .alpaca import AlpacaBroker, AlpacaError
from .paper import PaperBroker


def get_broker(settings: Settings, db_path=None):
    """Broker de acciones: paper interno o Alpaca."""
    if settings.execution.broker == "alpaca":
        return AlpacaBroker(paper=(settings.mode != "live"), db_path=db_path)
    if db_path is None:
        from ..config import DEFAULT_DB

        db_path = DEFAULT_DB
    return PaperBroker(
        db_path,
        settings.starting_cash,
        settings.execution.commission_bps,
        settings.execution.slippage_bps,
    )


def get_mt5_broker(settings: Settings, db_path=None, dry_run: bool | None = None):
    """Broker MT5 para forex. Import perezoso: el paquete solo existe en Windows."""
    from ..config import DEFAULT_DB
    from .mt5 import MT5Broker

    return MT5Broker(
        path=settings.mt5.terminal_path,
        login=settings.mt5.login,
        server=settings.mt5.server,
        magic=settings.mt5.magic,
        deviation=settings.mt5.deviation,
        dry_run=settings.mt5.dry_run if dry_run is None else dry_run,
        db_path=db_path or DEFAULT_DB,
        server_utc_offset_hours=settings.mt5.server_utc_offset_hours,
        require_demo=settings.mt5.require_demo,
    )


__all__ = ["PaperBroker", "AlpacaBroker", "AlpacaError", "get_broker", "get_mt5_broker"]
