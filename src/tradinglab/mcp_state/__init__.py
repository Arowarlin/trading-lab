"""Servidor MCP ``tradinglab-state`` de solo lectura (FUT-T2).

Mismo estado para Claude y para OpenCode, sin SQL improvisado y sin ninguna ruta
de escritura: ``docs/futures/02_EXTENSIONES_CLAUDE_CODE.md §4``.

El servidor se importa de forma perezosa como ``mcp_server`` para no tapar el
submódulo ``tradinglab.mcp_state.server`` ni cargarlo al arrancar con
``python -m tradinglab.mcp_state.server``.
"""

__all__ = ["mcp_server"]


def __getattr__(name: str) -> object:
    if name == "mcp_server":
        from .server import server

        return server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
