"""TradingLab Prop Fund: capa multiempresa / multicuenta CFD + Futures.

Se construye alrededor del carril FTMO existente sin modificarlo. Ver
``docs/propfund/`` para la auditoría, la arquitectura y el plan por fases.

Todo el paquete es PAPER/DEMO: ningún módulo envía órdenes.
"""

from .models import AutomationPermission, ConnectionState, Market, VerificationStatus
from .registry import Registry, RegistryError, load_registry

__all__ = [
    "AutomationPermission",
    "ConnectionState",
    "Market",
    "Registry",
    "RegistryError",
    "VerificationStatus",
    "load_registry",
]
