"""``NT8Bridge``: intercambio por ficheros con una estrategia NinjaScript (execution_spec.md §5) — FUT-J4.

Python escribe cada intent APROBADO en ``outbox/<intent_id>.json``; la estrategia
``integrations/nt8/TradingLabBridge.cs`` lo lee, lo envía SOLO a una cuenta Sim/Playback y escribe
``inbox/<intent_id>.ack.json``. Nada de live: el puente rechaza cuentas que no sean de simulación y la
NinjaScript lo vuelve a comprobar (defensa en profundidad), con su propio límite de contratos.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ...config import ROOT
from .intent import OrderIntent
from .paper import Ack
from .riskcheck import RiskResult

BRIDGE_DIR = ROOT / "data" / "futures" / "nt8_bridge"
SIM_PREFIXES = ("Sim", "Playback")


class NT8Bridge:
    name = "nt8"

    def __init__(self, root: str | Path = BRIDGE_DIR, *, nt_account: str, max_contracts: int):
        if not nt_account.startswith(SIM_PREFIXES):
            raise ValueError("el puente solo admite cuentas Sim o Playback de NinjaTrader")
        self.outbox = Path(root) / "outbox"
        self.inbox = Path(root) / "inbox"
        self.outbox.mkdir(parents=True, exist_ok=True)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.nt_account = nt_account
        self.max_contracts = int(max_contracts)

    def submit(self, intent: OrderIntent, result: RiskResult) -> Ack:
        if intent.adapter != "nt8":
            return Ack(intent.intent_id, None, "rejected", ("wrong_adapter",))
        if not result.ok:
            return Ack(intent.intent_id, None, "rejected", tuple(result.reasons))
        if intent.qty > self.max_contracts:
            return Ack(intent.intent_id, None, "rejected", ("bridge_max_contracts",))
        payload = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(intent).items()}
        payload.update(nt_account=self.nt_account, max_contracts=self.max_contracts, version=1)
        tmp = self.outbox / f"{intent.intent_id}.json.tmp"
        tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
        tmp.replace(self.outbox / f"{intent.intent_id}.json")       # escritura atómica: NT8 nunca lee a medias
        return Ack(intent.intent_id, None, "queued_nt8")

    def read_ack(self, intent_id: str) -> dict | None:
        path = self.inbox / f"{intent_id}.ack.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
