"""Restricciones de firma comprobables y etiqueta de incompatibilidad."""

from __future__ import annotations

from datetime import date

from tradinglab.discovery import genetic
from tradinglab.propfund.constraints import check_strategy, constraint_rows
from tradinglab.propfund.models import FirmRule, Source, VerificationStatus
from tradinglab.propfund.registry import load_registry


def _rule(key: str, value, *, phase: str = "evaluation") -> FirmRule:
    return FirmRule(
        key=key,
        value=value,
        phase=phase,
        status=VerificationStatus.VERIFIED_OFFICIAL,
        source=Source(
            url="https://help.fundingpips.com/",
            consulted_at=date(2026, 11, 21),
        ),
    )


def _strategy(template: str):
    return genetic.configured_template(
        template, instrument="US100", timeframe="M5"
    )


def _context():
    registry = load_registry()
    firm = registry.firms["fundingpips"]
    account = registry.accounts["CFD-006"]
    program = firm.program(account.program)
    return firm, account, program


def test_fundingpips_trial_compatible_en_evaluacion() -> None:
    firm, account, program = _context()
    check = check_strategy(
        _strategy("ny_open_vol_filter"),
        firm=firm,
        program=program,
        account=account,
    )

    assert check.compatible is True
    assert check.label.startswith("compatible con fundingpips")
    assert check.violations == ()


def test_noticias_prohibidas_marcan_incompatible() -> None:
    firm, account, program = _context()
    restricted = firm.model_copy(
        update={
            "firm_constraints": [
                _rule("news_trading", "forbidden"),
            ]
        }
    )
    check = check_strategy(
        _strategy("ny_open_vol_filter"),
        firm=restricted,
        program=program,
        account=account,
    )

    assert check.compatible is False
    assert check.label.startswith("incompatible con fundingpips")
    assert any("noticias" in item for item in check.violations)


def test_overnight_y_fin_de_semana_en_sesion_que_cruza_medianoche() -> None:
    firm, account, program = _context()
    restricted = firm.model_copy(
        update={
            "firm_constraints": [
                _rule("overnight_holding", False),
                _rule("weekend_holding", False),
            ]
        }
    )
    check = check_strategy(
        _strategy("asia_range_reversion"),
        firm=restricted,
        program=program,
        account=account,
    )

    assert check.compatible is False
    assert any("overnight" in item for item in check.violations)
    assert any("fin de semana" in item for item in check.violations)
    assert check.label.startswith("incompatible con fundingpips")


def test_max_operaciones_y_max_lotes() -> None:
    firm, account, program = _context()
    restricted = firm.model_copy(
        update={
            "firm_constraints": [
                _rule("max_trades_per_day", 1),
                _rule("max_lots", 1),
            ]
        }
    )
    check = check_strategy(
        _strategy("ny_open_vol_filter"),
        firm=restricted,
        program=program,
        account=account,
    )

    assert check.compatible is False
    assert any("operaciones/día" in item for item in check.violations)
    assert any("lotes" in item for item in check.violations)


def test_constraint_rows_muestra_sin_datos() -> None:
    firm, account, program = _context()
    rows = constraint_rows(firm, program, phase=account.phase.value)
    by_key = {row["key"]: row for row in rows}

    assert by_key["news_trading"]["display"] == "Permitido"
    assert by_key["overnight_holding"]["display"] == "Permitido"
    assert by_key["max_lots"]["value"] == 20
    assert by_key["max_trades_per_day"]["display"] == "Sin datos"
    assert by_key["max_trades_per_day"]["status"] == "unverified"
