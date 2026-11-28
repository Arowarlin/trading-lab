"""FUT-P2 (instantáneas sin red y diff) y FUT-P5 (avisos)."""

from __future__ import annotations

from datetime import date

from tradinglab.prop_economics.alerts import collect_alerts
from tradinglab.prop_economics.sources import archive, latest_change, normalize


def test_normalize_drops_markup_and_scripts():
    raw = "<html><script>var x=1;</script><p>Payout cap: $2,000.</p><p>Split 90/10.</p></html>"
    assert normalize(raw) == "Payout cap: $2,000.\nSplit 90/10."


def test_archive_and_detect_change(tmp_path):
    root = tmp_path / "snaps"
    a = tmp_path / "a.html"
    a.write_text("<p>Payout cap: $2,000.</p>", encoding="utf-8")
    p1 = archive("topstep", "payout-policy", a, day=date(2026, 11, 27), root=root)
    assert archive("topstep", "payout-policy", a, day=date(2026, 11, 27), root=root) == p1   # idempotente
    assert latest_change("topstep", "payout-policy", root=root)["changed"] is None
    b = tmp_path / "b.html"
    b.write_text("<p>Payout cap: $1,500.</p>", encoding="utf-8")
    archive("topstep", "payout-policy", b, day=date(2026, 12, 5), root=root)
    ch = latest_change("topstep", "payout-policy", root=root)
    assert ch["changed"] is True and "-Payout cap: $2,000." in ch["diff"] and "+Payout cap: $1,500." in ch["diff"]
    assert a.exists() and b.exists()      # nunca borra los originales


def test_alerts_expiry_unknowns_and_sources(tmp_path):
    root = tmp_path / "snaps"
    for i, cap in enumerate(("2,000", "1,500")):
        f = tmp_path / f"{i}.html"
        f.write_text(f"<p>cap {cap}</p>", encoding="utf-8")
        archive("lucid", "payouts", f, day=date(2026, 11, 20 + i), root=root)
    early = collect_alerts(date(2026, 12, 1), snapshots=root)
    kinds = {a["alert"] for a in early}
    assert "source_changed" in kinds and "rules_unknown" in kinds and "rules_expired" not in kinds
    soon = {a["alert"] for a in collect_alerts(date(2026, 12, 22), snapshots=root)}
    assert "rules_expiring" in soon
    late = [a for a in collect_alerts(date(2026, 12, 27), snapshots=root) if a["alert"] == "rules_expired"]
    assert {a["program"] for a in late} == {"lucid_flex_50k", "myfundedfutures_rapid_50k", "topstep_50k_combine_xfa"}
