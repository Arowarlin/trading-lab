"""FUT-H2/P6: carga útil del panel con bloques real, nominal y simulado separados."""

from __future__ import annotations

import json
from datetime import date

from tradinglab.prop_economics.dashboard import economics_payload
from tradinglab.prop_economics.ledger import add_account, add_event, open_ledger


def _keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{prefix}{k}"
            yield from _keys(v, f"{prefix}{k}.")


def test_payload_without_ledger(tmp_path):
    p = economics_payload(today=date(2026, 12, 1), ledger_path=tmp_path / "none.db", reports_dir=tmp_path)
    assert p["real"]["status"].startswith("Sin datos")
    assert p["simulated"]["label"].startswith("SIMULADO")
    assert set(p["catalog"]) >= {"topstep", "lucid", "alphafutures"}
    assert p["ranking"]["ranking"][0]["firm"] == "myfundedfutures"
    assert json.dumps(p, default=str)


def test_real_and_simulated_never_mixed(tmp_path):
    db = tmp_path / "ledger.db"
    con = open_ledger(db)
    add_account(con, "A1", firm_id="topstep", program_id="topstep_50k_combine_xfa", rules_version="1",
                origin="semi_manual", opened_at="2026-11-30")
    add_event(con, ts="2026-11-30", account_id="A1", event="fee_paid", amount_usd=-49.0)
    con.close()
    p = economics_payload(today=date(2026, 12, 1), ledger_path=db, reports_dir=tmp_path)
    assert p["real"]["net_real"] == -49.0
    for key in _keys({k: v for k, v in p.items() if k in ("real", "simulated", "nominal")}):
        assert not ("real" in key and "simulated" in key)
    assert "net_real" not in json.dumps(p["simulated"])


def test_ui_has_futures_economics_view():
    from tradinglab import web

    html = web.INDEX_FILE.read_text(encoding="utf-8")
    for piece in ('data-view="futecon"', 'id="view-futecon"', "/api/futures/economics", "SIMULADO · ventaja supuesta",
                  "Neto REAL", "loadFutEcon"):
        assert piece in html
