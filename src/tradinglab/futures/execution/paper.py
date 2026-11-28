"""``PaperAdapter``: acepta intents que pasan el control y los guarda; sin red ni órdenes reales — FUT-J1."""

from __future__ import annotations

from dataclasses import dataclass, field

from .intent import OrderIntent
from .riskcheck import RiskResult


@dataclass(frozen=True)
class Ack:
    intent_id: str
    broker_order_id: str | None
    status: str          # "accepted_paper" | "rejected"
    reasons: tuple[str, ...] = ()


@dataclass
class PaperAdapter:
    name: str = "paper"
    accepted: list[OrderIntent] = field(default_factory=list)

    def submit(self, intent: OrderIntent, result: RiskResult) -> Ack:
        if intent.adapter != "paper":
            return Ack(intent.intent_id, None, "rejected", ("wrong_adapter",))
        if not result.ok:
            return Ack(intent.intent_id, None, "rejected", tuple(result.reasons))
        self.accepted.append(intent)
        return Ack(intent.intent_id, f"paper-{len(self.accepted)}", "accepted_paper")
