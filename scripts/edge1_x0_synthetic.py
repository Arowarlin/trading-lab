"""EDGE-1 X0.5: ensayo sintetico por TF (no suma al DSR)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tradinglab.discovery import campaigns, engine

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "TL3_REPORTS" / "edge1_x0_synthetic.txt"
SEGMENTS = {
    "is": ["2023-01-02", "2023-09-30"],
    "oos1": ["2023-10-01", "2023-11-30"],
    "oos2": ["2023-12-01", None],
}


def main() -> None:
    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "discovery.db"
        frame = engine.synthetic_frame(years=1.0, seed=15)
        from tradinglab.discovery.resample import resample_session

        for index, tf in enumerate(["M15", "M30", "H1", "H4"], start=1):
            identifier = f"edge1-synth-{tf.lower()}"
            tf_frame = frame if tf == "M5" else resample_session(frame, tf)
            campaigns.register_synthetic(
                tf_frame,
                instrument="US100",
                timeframe=tf,
                template="vol_squeeze_breakout",
                profile="small",
                segments=SEGMENTS,
                seed=index,
                campaign_id=identifier,
                data_source="dukascopy",
                db_path=db,
            )
            summary = engine.run_campaign(
                identifier,
                workers=4,
                time_limit=5,
                synthetic=True,
                db_path=db,
                bars=tf_frame,
            )
            line = (
                f"{tf}: n_total={summary['n_total']} evaluados={summary['n_evaluated']} "
                f"efectivas={summary['n_effective']} factibles={summary['feasible']} "
                f"frontera={summary['frontier']} finalistas={len(summary['finalists'])} "
                f"tiempo={summary['elapsed_s']:.1f}s semilla={summary['seed']}"
            )
            print(line, flush=True)
            lines.append(line)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
