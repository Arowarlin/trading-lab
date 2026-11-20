"""Caché LRU de indicadores por worker.

La clave es ``(bloque, params, contexto)``; el contexto lo construye el
compilador (zona horaria, sesión y HTF). El límite se reparte entre workers:
``ram_limit_gb × 1024³ / workers``. Cada worker tiene su propia instancia; no
se comparte entre procesos.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import numpy as np

_MISSING = object()


class IndicatorCache:
    def __init__(self, limit_bytes: int, *, dataset_token: int | None = None) -> None:
        self.limit_bytes = max(0, int(limit_bytes))
        self.dataset_token = dataset_token
        self._data: OrderedDict[Any, Any] = OrderedDict()
        self._bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _size(self, value: Any) -> int:
        if isinstance(value, np.ndarray):
            return int(value.nbytes) + 256
        values = getattr(value, "to_numpy", None)
        if callable(values):
            try:
                return int(values().nbytes) + 256
            except Exception:  # noqa: BLE001 - objeto no convertible
                return 256
        return 256

    def get(self, key: Any) -> Any:
        if self.limit_bytes <= 0:
            self.misses += 1
            return _MISSING
        value = self._data.get(key, _MISSING)
        if value is _MISSING:
            self.misses += 1
            return _MISSING
        self.hits += 1
        self._data.move_to_end(key)
        return value

    def put(self, key: Any, value: Any) -> None:
        if self.limit_bytes <= 0:
            return
        size = self._size(value)
        if size > self.limit_bytes:
            return
        if key in self._data:
            self._bytes -= self._size(self._data.pop(key))
        self._data[key] = value
        self._bytes += size
        while self._bytes > self.limit_bytes and self._data:
            _old_key, old = self._data.popitem(last=False)
            self._bytes -= self._size(old)
            self.evictions += 1

    def stats(self) -> dict[str, int]:
        return {
            "hits": int(self.hits),
            "misses": int(self.misses),
            "evictions": int(self.evictions),
            "entries": int(len(self._data)),
            "bytes": int(self._bytes),
            "limit_bytes": int(self.limit_bytes),
        }


MISSING = _MISSING

__all__ = ["IndicatorCache", "MISSING"]
