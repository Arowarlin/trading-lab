from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.continuous import ContinuousError, stitch_continuous


def _contract(start: str, prices: list[float], volume: list[float]) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [value + 1 for value in prices],
            "low": [value - 1 for value in prices],
            "close": prices,
            "volume": volume,
        },
        index=index,
    )


def test_stitch_ratio_elimina_salto_de_roll():
    old = _contract("2026-01-01", [100, 101, 102], [10, 11, 12])
    new = _contract("2026-01-04", [200, 201, 202], [20, 21, 22])
    out = stitch_continuous(
        [("OLD", old), ("NEW", new)],
        ["2026-01-04"],
        method="ratio",
    )
    assert len(out) == 6
    assert list(out["contract"]) == ["OLD", "OLD", "OLD", "NEW", "NEW", "NEW"]
    assert out.loc["2026-01-03", "close"] == pytest.approx(200.0)
    assert out.loc["2026-01-04", "open"] == pytest.approx(200.0)
    assert out.loc["2026-01-04", "volume"] == pytest.approx(20.0)


def test_stitch_difference_y_validaciones():
    old = _contract("2026-01-01", [100, 101, 102], [1, 1, 1])
    new = _contract("2026-01-04", [200, 201, 202], [1, 1, 1])
    out = stitch_continuous(
        [("OLD", old), ("NEW", new)],
        ["2026-01-04"],
        method="difference",
    )
    assert out.loc["2026-01-03", "close"] == pytest.approx(200.0)
    assert out.loc["2026-01-04", "open"] == pytest.approx(200.0)

    with pytest.raises(ContinuousError, match="roll_dates"):
        stitch_continuous([("A", old), ("B", new)], [])
    with pytest.raises(ContinuousError, match="método|method"):
        stitch_continuous([("A", old), ("B", new)], ["2026-01-04"], method="otro")
    with pytest.raises(ContinuousError, match="segmento vacío"):
        stitch_continuous(
            [("A", old), ("B", new)],
            ["2026-01-01"],
        )
