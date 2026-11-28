"""``ProjectXAdapter``: envoltorio en DRY-RUN de ``execution/projectx.py`` (sin modificarlo) — FUT-J3.

Traduce un ``OrderIntent`` aprobado por el control a ``ProjectXClient.place_order``. En esta fase solo se
admite dry-run: un cliente o un intent que no estén en dry-run se rechazan (R16, live bloqueado).
TopstepX exige que los brackets estén a 4 ticks o más (ficha de Topstep).
"""

from __future__ import annotations

from typing import Any

from .intent import OrderIntent, contract_spec
from .paper import Ack
from .riskcheck import RiskResult

MIN_BRACKET_TICKS = 4


class LiveBlockedError(RuntimeError):
    pass


class ProjectXAdapter:
    name = "projectx"

    def __init__(self, client: Any):
        self.client = client

    def submit(self, intent: OrderIntent, result: RiskResult, *, contract_id: str) -> Ack:
        if intent.adapter != "projectx":
            return Ack(intent.intent_id, None, "rejected", ("wrong_adapter",))
        if not result.ok:
            return Ack(intent.intent_id, None, "rejected", tuple(result.reasons))
        if not intent.dry_run or not getattr(self.client, "dry_run", False):
            raise LiveBlockedError("live_blocked: esta fase solo admite dry-run")
        tick = contract_spec(intent.root).tick_size
        sl_ticks = round(abs(intent.entry_price - intent.stop_price) / tick)
        tp_ticks = None if intent.target_price is None else round(abs(intent.target_price - intent.entry_price) / tick)
        if sl_ticks < MIN_BRACKET_TICKS or (tp_ticks is not None and tp_ticks < MIN_BRACKET_TICKS):
            return Ack(intent.intent_id, None, "rejected", ("bracket_too_close",))
        kwargs = {"order_type": intent.entry_type, "stop_loss_ticks": sl_ticks, "take_profit_ticks": tp_ticks,
                  "custom_tag": intent.intent_id[:64], "bot": intent.strategy_id, "reason": intent.hypothesis_id}
        if intent.entry_type == "limit":
            kwargs["limit_price"] = intent.entry_price
        elif intent.entry_type == "stop":
            kwargs["stop_price"] = intent.entry_price
        resp = self.client.place_order(contract_id, intent.side, intent.qty, **kwargs)
        return Ack(intent.intent_id, resp.get("order_id"), str(resp.get("status")))
