from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.orchestrator import BotAction, write_dry_run_log


def test_write_dry_run_log_is_json_and_never_orders(tmp_path):
    actions = [
        BotAction(
            bot="trend-spy",
            ticker="SPY",
            target=1.0,
            price=500.0,
            held=0.0,
            desired=100,
            delta=100,
            status="dry_run",
            detail="",
        )
    ]
    path = write_dry_run_log(
        actions,
        tmp_path,
        broker="paper",
        when=datetime(2026, 11, 9, 21, 50, tzinfo=timezone.utc),
    )

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["broker"] == "paper"
    assert payload["actions"][0]["status"] == "dry_run"
    assert payload["actions"][0]["order"] is None
    assert path.endswith("dryrun_20261109_215000.json")
