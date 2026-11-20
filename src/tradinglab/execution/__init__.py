from __future__ import annotations

from ..config import Settings
from .paper import PaperBroker


def get_broker(settings: Settings, db_path=None):
    """Broker de paper interno. Solo paper; el laboratorio ya no opera acciones."""
    if db_path is None:
        from ..config import DEFAULT_DB

        db_path = DEFAULT_DB
    return PaperBroker(
        db_path,
        settings.starting_cash,
        settings.execution.commission_bps,
        settings.execution.slippage_bps,
    )


def get_broker_for_account(settings: Settings, account, db_path=None):
    """Broker que corresponde a la cuenta declarada por un bot.

    Solo paper/demo. Las cuentas CFD/futuros usan MT5 o ProjectX; el broker
    interno se conserva para simulaciones y pruebas.
    """
    if str(getattr(settings, "mode", "paper")) == "live":
        raise ValueError("modo live bloqueado: el laboratorio solo opera paper/demo")
    platform = str(
        getattr(account, "platform", "") or getattr(account, "broker", "")
    ).lower()
    status = str(getattr(account, "status", "")).lower()
    if status not in {"active", "paper", "demo", "simulated"}:
        raise ValueError(f"cuenta {getattr(account, 'id', '?')} no paper/demo: {status}")
    if platform in {"internal", "paper"}:
        if db_path is None:
            from ..config import DEFAULT_DB

            db_path = DEFAULT_DB
        return PaperBroker(
            db_path,
            settings.starting_cash,
            settings.execution.commission_bps,
            settings.execution.slippage_bps,
        )
    raise ValueError(
        f"cuenta {getattr(account, 'id', '?')} con plataforma {platform}: "
        "sin broker de paper para esa plataforma"
    )


def get_projectx_broker(settings: Settings, db_path=None, dry_run: bool | None = None):
    """Broker de futuros vía ProjectX/TopstepX. Import perezoso (httpx)."""
    from ..config import DEFAULT_DB
    from .projectx import ProjectXBroker

    return ProjectXBroker(
        base_url=settings.projectx.base_url,
        username=settings.projectx.username,
        account_id=settings.projectx.account_id,
        dry_run=settings.projectx.dry_run if dry_run is None else dry_run,
        require_simulated=settings.projectx.require_simulated,
        db_path=db_path or DEFAULT_DB,
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


__all__ = [
    "PaperBroker",
    "get_broker",
    "get_broker_for_account",
    "get_mt5_broker",
    "get_projectx_broker",
]
