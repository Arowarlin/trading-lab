"""Onboarding de una cuenta simulada: sin MT5 real, sin login/shutdown."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import yaml

from tradinglab.broker_costs import init_db, persist_spreads
from tradinglab.discovery import databank, engine
from tradinglab.learning import count_tests
from tradinglab.propfund import onboarding as onboarding_module
from tradinglab.propfund import snapshots
from tradinglab.propfund.models import (
    AccountLimits,
    AccountPhase,
    AutomationPermission,
    AutomationPolicy,
    ConnectionState,
    Firm,
    FirmRule,
    Market,
    Program,
    PropAccount,
    RiskPolicy,
    Source,
    VerificationStatus,
)
from tradinglab.propfund.onboarding import collect_symbols, onboard
from tradinglab.propfund.registry import Registry

NOW = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)
SOURCE = Source(url="https://example.invalid/rules", consulted_at=date(2026, 11, 21))


class FakeBroker:
    def __init__(self) -> None:
        self.login_calls = 0
        self.shutdown_calls = 0
        self.connect_calls = 0
        self.symbol_calls = 0

    def connect(self) -> dict:
        self.connect_calls += 1
        return {
            "login": 123456,
            "server": "Sim-Server",
            "mode": "demo",
            "connected": True,
        }

    def symbols(self) -> list[dict]:
        self.symbol_calls += 1
        return [
            {
                "symbol": "NDX100",
                "group": "Indices",
                "path": "Indices\\NDX100",
                "digits": 2,
                "tick_size": 0.01,
                "contract_size": 1.0,
                "volume_min": 0.1,
            }
        ]

    def login(self, *args, **kwargs):
        self.login_calls += 1
        raise AssertionError("onboarding no puede hacer login")

    def shutdown(self):
        self.shutdown_calls += 1
        raise AssertionError("onboarding no puede hacer shutdown")


def _rule(key: str, value, *, unit: str = "") -> FirmRule:
    return FirmRule(
        key=key,
        value=value,
        unit=unit,
        phase="evaluation",
        status=VerificationStatus.VERIFIED_OFFICIAL,
        source=SOURCE,
    )


def _registry() -> Registry:
    firm = Firm(
        id="simfirm",
        name="Sim Firm",
        market=Market.CFD,
        website="https://example.invalid",
        platforms=["mt5"],
        execution_providers=["mt5"],
        rules_version="test.1",
        automation=AutomationPolicy(
            permission=AutomationPermission.CONDITIONAL,
            status=VerificationStatus.VERIFIED_OFFICIAL,
            conditions=["EA propio con prueba de propiedad"],
            sources=[SOURCE],
        ),
        firm_constraints=[
            _rule("news_trading", "allowed"),
            _rule("weekend_holding", True),
            _rule("overnight_holding", True),
            _rule("max_lots", 20, unit="lots_per_trade"),
            _rule("max_trades_per_day", None),
        ],
        programs=[
            Program(
                id="simp",
                name="Sim Program",
                phases=[AccountPhase.EVALUATION],
                platforms=["mt5"],
                sizes=[100000],
                rules=[
                    _rule("min_trading_days", 0, unit="days_per_phase"),
                    _rule("max_daily_loss_pct", 0.03, unit="fraction"),
                    _rule("max_loss_pct", 0.06, unit="fraction"),
                    _rule("drawdown_mode", "static"),
                    _rule("profit_target_pct", 0.06, unit="fraction"),
                    _rule("leverage_forex", 100, unit="ratio"),
                    _rule("trial_time_limit_days", 14, unit="calendar_days_per_phase"),
                    _rule(
                        "news_evaluation",
                        "Sin restricciones en evaluación",
                    ),
                    _rule("weekend_holding_evaluation", True),
                    _rule("ea_policy", "EA propio con prueba de propiedad"),
                ],
            )
        ],
    )
    account = PropAccount(
        id="SIM-001",
        firm="simfirm",
        program="simp",
        market=Market.CFD,
        phase=AccountPhase.EVALUATION,
        nominal_size=100000,
        platform="mt5",
        execution_provider="mt5",
        connection_state=ConnectionState.DEMO,
        template=False,
        allowed_instruments=["US100"],
        terminal_path="C:/fake/terminal64.exe",
        login=123456,
        server="Sim-Server",
        broker_symbols={"US100": "NDX100"},
        spread_source="broker:SIM-001",
        limits=AccountLimits(
            daily_loss=3000,
            max_loss=6000,
            drawdown_mode="static",
            profit_target=6000,
            min_trading_days=0,
            max_lots=20,
        ),
        risk=RiskPolicy(),
    )
    return Registry(firms={firm.id: firm}, accounts={account.id: account})


def _costs_yaml(path):
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "accounts": {
                    "SIM-001": {
                        "symbols": {
                            "US100": {
                                "spread_price": 1.0,
                                "spread_p75_price": 1.2,
                                "slippage_price": 1.0,
                                "commission_type": "zero",
                                "commission_value": 0.0,
                                "commission_side": "per_side",
                                "commission_source": "Sim · oficial · 2026-11-21",
                                "source": "sim",
                                "needs_verification": False,
                            }
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _seed_spreads(path) -> None:
    init_db(path)
    rows = []
    for hour in range(24):
        rows.append(
            {
                "symbol": "NDX100",
                "hour_utc": hour,
                "median_bps": 0.8 + hour * 0.01,
                "p75_bps": 1.0 + hour * 0.01,
                "n_ticks": 100,
                "from_ts": f"2026-11-20T{hour:02d}:00:00+00:00",
                "to_ts": f"2026-11-20T{hour:02d}:59:59+00:00",
                "source": "broker:SIM-001",
            }
        )
    persist_spreads(pd.DataFrame(rows), path)


def _bars_loader(symbol: str, timeframe: str) -> pd.DataFrame:
    return engine.synthetic_frame(years=1.0, seed=7)


def test_onboarding_simulado_sin_mt5_real_y_sin_dsr(tmp_path, monkeypatch) -> None:
    registry = _registry()
    costs_path = tmp_path / "costs.yaml"
    _costs_yaml(costs_path)
    costs_db = tmp_path / "lab.db"
    _seed_spreads(costs_db)
    discovery_db = tmp_path / "discovery.db"
    databank.init_databank(discovery_db)
    learning_db = tmp_path / "learning.db"
    fake = FakeBroker()

    from tradinglab.propfund.costs import load_profile as real_load_profile

    monkeypatch.setattr(
        "tradinglab.discovery.costs.load_registry", lambda: registry
    )
    monkeypatch.setattr(
        "tradinglab.discovery.costs.load_profile",
        lambda account, symbol, firm=None: real_load_profile(
            account, symbol, firm=firm, path=costs_path
        ),
    )
    before = count_tests(learning_db, discovery_db=discovery_db)
    report = onboard(
        "SIM-001",
        registry=registry,
        broker=fake,
        costs_path=costs_path,
        costs_db=costs_db,
        discovery_db=discovery_db,
        cache_dir=tmp_path / "cache",
        ai_trader_path=tmp_path / "ai_trader.yaml",
        bars_loader=_bars_loader,
        out=tmp_path / "SIM-001_onboarding.md",
        now=NOW,
        n_paths=200,
    )
    after = count_tests(learning_db, discovery_db=discovery_db)

    assert after == before
    assert discovery_db.exists()
    assert databank.count_strategies("SIM-001", db_path=discovery_db) == 0
    assert fake.login_calls == 0
    assert fake.shutdown_calls == 0
    assert fake.connect_calls == 1
    assert fake.symbol_calls == 1
    assert report["account"] == "SIM-001"
    assert report["rules"]["verified"] >= 5
    assert (report["symbols"]["symbols"][0]["broker_symbol"]) == "NDX100"
    assert report["costs"]["status"] == "ok"
    assert round(report["costs"]["hourly"]["US100"]["hours"]["7"], 6) == 1.12
    assert report["scan"]["n_rows"] == 0
    assert report["scan"]["label"] == "por probar"
    assert report["scan"]["cost_mode"] == "target"
    assert report["matrix"]["rows"] == []
    assert "nivel ≥ 3" in report["matrix"]["note"]
    assert report["count_tests_changed"] is False
    assert report["path"].endswith("SIM-001_onboarding.md")
    markdown = (tmp_path / "SIM-001_onboarding.md").read_text(encoding="utf-8")
    for section in (
        "## 1. Reglas del programa",
        "## 2. Costes de la cuenta",
        "## 3. Mapa de viabilidad",
        "## 4. Restricciones de la firma",
        "## 5. Matriz de estrategias nivel ≥ 3",
        "## 6. Resumen",
    ):
        assert section in markdown
    assert "verification_status" in markdown
    assert "Sin PnL" in markdown or "sin PnL" in markdown


def test_symbols_attach_only_sin_login_ni_shutdown(monkeypatch) -> None:
    registry = _registry()
    account = registry.accounts["SIM-001"]

    class FakeSymbol:
        name = "NDX100"
        path = "Indices\\NDX100"
        digits = 2
        point = 0.01
        trade_tick_size = 0.01
        trade_contract_size = 1.0
        volume_min = 0.1

    class FakeAccount:
        login = 123456
        server = "Sim-Server"
        trade_mode = 0
        name = "Sim"
        company = "Sim"
        currency = "USD"
        leverage = 100
        balance = 100000.0
        equity = 100000.0
        margin = 0.0
        margin_free = 100000.0
        margin_level = 0.0
        profit = 0.0

    class FakeTerminal:
        connected = True
        trade_allowed = False
        path = "C:/fake/terminal64.exe"
        build = 4000

    class FakeMT5:
        def __init__(self) -> None:
            self.initialize_kwargs = None
            self.shutdown_called = False
            self.login_called = False
            self.symbols_get_calls = 0

        def initialize(self, **kwargs):
            self.initialize_kwargs = dict(kwargs)
            return True

        def last_error(self):
            return 0, "ok"

        def account_info(self):
            return FakeAccount()

        def terminal_info(self):
            return FakeTerminal()

        def symbol_info_tick(self, symbol):
            return None

        def symbols_get(self):
            self.symbols_get_calls += 1
            return [FakeSymbol()]

        def login(self, *args, **kwargs):
            self.login_called = True
            return True

        def shutdown(self):
            self.shutdown_called = True

    fake = FakeMT5()
    monkeypatch.setattr(snapshots, "_mt5_module", lambda: fake)
    monkeypatch.setattr("tradinglab.execution.mt5._mt5", lambda: fake)
    monkeypatch.setattr(snapshots, "_terminal_running", lambda: True)

    result = collect_symbols(account)

    assert fake.initialize_kwargs is not None
    assert "login" not in fake.initialize_kwargs
    assert "password" not in fake.initialize_kwargs
    assert "server" not in fake.initialize_kwargs
    assert fake.login_called is False
    assert fake.shutdown_called is False
    assert fake.symbols_get_calls == 1
    assert result["identity"]["identity_ok"] is True
    assert result["symbols"][0]["found"] is True


def test_login_distinto_deja_sin_datos() -> None:
    registry = _registry()
    account = registry.accounts["SIM-001"]
    other = account.model_copy(update={"login": 999999})
    result = collect_symbols(other, broker=FakeBroker())

    assert result["status"] == "Sin datos"
    assert result["symbols"] == []
    assert any("login" in note for note in result["notes"])


def test_render_no_inventa_valores_ausentes() -> None:
    registry = _registry()
    account = registry.accounts["SIM-001"]
    firm = registry.firms["simfirm"]
    program = firm.program("simp")
    rules = onboarding_module.collect_rules(account, firm, program)
    rows = {row["label"]: row for row in rules["rows"]}

    assert rows["Máximo de operaciones/día"]["display"] == "Sin datos"
    assert rows["Máximo de operaciones/día"]["verification_status"] == "unverified"
