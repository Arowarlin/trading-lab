"""Políticas de tamaño del ORPAE (risk/02_ORPAE_DISENO.md §2.2-§3) — FUT-O3.

* ``fixed``: riesgo fijo en USD → contratos = suelo(riesgo / riesgo_por_contrato).
* ``cushion``: riesgo = min(r_max, κ·colchón) con colchón = equity − umbral; mínimo 1 contrato mientras la
  cuenta viva (sin cuentas "zombi").

El tamaño solo depende del colchón actual: tras una pérdida el colchón baja y el tamaño NO sube
(antimartingala). Los topes del programa (max_contracts y escalado) los aplica el motor después.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SizingPolicy:
    kind: str                       # "fixed" | "cushion"
    risk_per_contract: float        # USD que se pierden por contrato en un stop, costes incluidos
    risk_usd: float = 0.0           # fixed
    kappa: float = 0.0              # cushion
    r_max: float = 0.0              # cushion
    min_contracts: int = 1          # cushion

    def __post_init__(self) -> None:
        if self.kind not in {"fixed", "cushion"}:
            raise ValueError(f"política desconocida: {self.kind}")
        if self.risk_per_contract <= 0:
            raise ValueError("risk_per_contract > 0")
        if self.kind == "fixed" and self.risk_usd <= 0:
            raise ValueError("risk_usd > 0")
        if self.kind == "cushion" and (self.kappa <= 0 or self.r_max <= 0):
            raise ValueError("kappa y r_max > 0")

    @property
    def name(self) -> str:
        if self.kind == "fixed":
            return f"fixed_{self.risk_usd:g}"
        return f"cushion_k{self.kappa:g}_max{self.r_max:g}"

    def contracts(self, cushion):
        """Contratos para el colchón dado (escalar o array). Nunca negativos."""
        c = np.maximum(np.asarray(cushion, dtype=np.float64), 0.0)
        if self.kind == "fixed":
            k = np.full(c.shape, int(np.floor(self.risk_usd / self.risk_per_contract + 1e-9)))
        else:
            risk = np.minimum(self.r_max, self.kappa * c)
            k = np.maximum(np.floor(risk / self.risk_per_contract + 1e-9).astype(int), self.min_contracts)
        return int(k) if k.ndim == 0 else k.astype(int)
