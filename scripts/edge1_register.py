"""EDGE-1 X1: registra la matriz congelada (dry-run o real)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tradinglab.discovery import campaigns

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "TL3_REPORTS" / "edge1_plan.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", default=None)
    args = parser.parse_args()
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    for item in payload["campaigns"]:
        if args.only and item["campaign_id"] != args.only:
            continue
        segments = {
            "is": [item["is_start"], item["is_end"]],
            "oos1": [item["oos1_start"], item["oos1_end"]],
            "oos2": [item["oos2_start"], item["oos2_end"]],
        }
        try:
            campaign = campaigns.register(
                item["instrument"],
                item["timeframe"],
                item["template"],
                item["profile"],
                segments=segments,
                seed=item["seed"],
                campaign_id=item["campaign_id"],
                mode=item["mode"],
                data_source=item["data_source"],
                cost_accounts=item["cost_accounts"],
                cost_mode=item["cost_mode"],
                dry_run=args.dry_run,
            )
            quality = (campaign.get("quality") or {}).get("status", "Sin datos")
            print(
                f"OK {'DRY' if args.dry_run else 'REAL'} {item['campaign_id']} "
                f"n_total={campaign.get('n_total')} rows={campaign.get('rows')} "
                f"quality={quality} dataset={str(campaign.get('dataset_hash'))[:12]}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"FAIL {'DRY' if args.dry_run else 'REAL'} {item['campaign_id']} "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )


if __name__ == "__main__":
    main()
