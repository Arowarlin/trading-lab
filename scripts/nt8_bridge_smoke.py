"""Prueba de humo del puente NT8 (FUT-J4) en el PC del operador: SOLO Sim101/Playback, 1 MNQ.

Requisitos: NinjaTrader 8 abierto, TradingLabBridge compilado y activo en un gráfico de MNQ con la cuenta
Sim101, BridgeDir = <repo>/data/futures/nt8_bridge y MaxContracts = 1.

    .\\.venv\\Scripts\\python.exe scripts\\nt8_bridge_smoke.py --account Sim101 --price 21000 --stop-pts 20

Construye un intent (Lucid Flex, evaluación, semimanual NO: automático por el puente), lo pasa por el
RiskCheck completo y, si es válido, lo deja en la bandeja; espera el ack hasta ``--timeout`` segundos.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tradinglab.config import ROOT
from tradinglab.futures.execution.intent import build_intent, load_execution_config
from tradinglab.futures.execution.nt8_bridge import NT8Bridge
from tradinglab.futures.execution.riskcheck import AccountView, CheckContext, check
from tradinglab.prop_economics.rules import load_program

NY = ZoneInfo("America/New_York")


def build(account: str, price: float, stop_pts: float, now: datetime):
    prog = load_program(ROOT / "config" / "prop_economics" / "programs" / "lucid_flex_50k.yaml")
    cfg = load_execution_config()
    intent = build_intent(program=prog, cfg=cfg, strategy_id="smoke", hypothesis_id="smoke:nt8", account_id=account,
                          phase="evaluation", root="MNQ", contract="MNQ", side="buy", qty=1, entry_type="market",
                          entry_price=price, stop_price=price - stop_pts, target_price=price + 1.5 * stop_pts,
                          exit_by=now + timedelta(minutes=30), origin="automated", adapter="nt8", signal_hash="smoke",
                          created_at=now)
    res = check(intent, prog, AccountView(account, 50000.0, 50000.0),
                CheckContext(now=now, firm_category="allowed", policy_risk_usd=100.0), cfg)
    return intent, res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="Sim101")
    ap.add_argument("--price", type=float, required=True)
    ap.add_argument("--stop-pts", type=float, default=20.0)
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()
    now = datetime.now(NY)
    intent, res = build(args.account, args.price, args.stop_pts, now)
    print(json.dumps({"risk_ok": res.ok, "reasons": res.reasons, "risk_usd": intent.risk_usd}, ensure_ascii=False))
    if not res.ok:
        raise SystemExit("el control de riesgo rechazó el intent; no se envía nada")
    bridge = NT8Bridge(nt_account=args.account, max_contracts=1)
    print(bridge.submit(intent, res))
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        ack = bridge.read_ack(intent.intent_id)
        if ack is not None:
            print(json.dumps(ack, ensure_ascii=False))
            return
        time.sleep(1)
    raise SystemExit("sin ack: ¿la estrategia TradingLabBridge está activa en Sim101 con ese BridgeDir?")


if __name__ == "__main__":
    main()
