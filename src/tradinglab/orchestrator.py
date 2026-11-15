from __future__ import annotations

import inspect
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .accounts import AccountDefinition, effective_limits, load_accounts, rules_for_account
from .alerts import send as send_alert
from .asset_aliases import symbol_allowed
from .clock import STATUS_FALLA as CLOCK_FALLA
from .clock import check_clock
from .conditioners import bot_multiplier_table, flags_series
from .config import DEFAULT_DB, ROOT, Settings
from .data import fetch
from .db import connect, utcnow
from .freshness import STATUS_FALLA as FRESHNESS_FALLA
from .freshness import check as check_freshness
from .indicators import atr
from .intel.calendar import calendar_block_for_settings, rules_from_settings
from .killswitch import allows_order
from .killswitch import ensure as ensure_killswitch
from .portfolio import load_clusters
from .profiles import BotProfile, load_profiles
from .prop.guard import AccountLimits, AccountSnapshot, PropGuard, evaluate_account
from .risk import check_order, size_position
from .risk_budget import assess_open, news_blackout
from .runtime import effective_enabled, record_console_action
from .session import session_block
from .strategies import STRATEGIES
from .strategies.base import exposure_multiplier

BOTS_FILE = ROOT / "config" / "bots.yaml"
ARCHIVE_FILE = ROOT / "config" / "bots_archive.yaml"
INTRADAY_BOTS_FILE = ROOT / "config" / "intraday_bots.yaml"


@dataclass
class BotSpec:
    id: str
    type: str
    strategy: str
    universe: list[str]
    timeframe: str = "1d"
    enabled: bool = False
    profile: str | None = None
    cluster: str | None = None
    account: str = "paper_main"
    params: dict = field(default_factory=dict)
    description: str = ""
    exposure: float = 1.0
    archived: bool = False
    yaml_enabled: bool = False
    family: str | None = None
    grid: dict = field(default_factory=dict)


@dataclass
class BotAction:
    bot: str
    ticker: str
    target: float
    price: float
    held: float
    desired: int
    delta: int
    status: str
    detail: str = ""
    order: dict | None = None


def load_archive_ids(path: Path | None = None) -> set[str]:
    path = path or ARCHIVE_FILE
    if not path.exists():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(x) for x in raw.get("archived", [])}


def _load_bots_file(path: Path) -> list[BotSpec]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    archived = load_archive_ids()
    bots = []
    for item in raw.get("bots", []):
        yaml_enabled = bool(item.get("enabled", False))
        profile = item.get("profile")
        universe = [
            str(t) if profile == "intraday_fx" else str(t).upper()
            for t in item.get("universe", [])
        ]
        bots.append(
            BotSpec(
                id=item["id"],
                type=item.get("type", "deterministic"),
                strategy=item["strategy"],
                universe=universe,
                timeframe=item.get("timeframe", "1d"),
                enabled=effective_enabled(DEFAULT_DB, item["id"], yaml_enabled),
                yaml_enabled=yaml_enabled,
                profile=profile,
                cluster=item.get("cluster"),
                account=str(item.get("account") or "paper_main"),
                params=item.get("params", {}) or {},
                description=item.get("description", ""),
                exposure=float(item.get("exposure", 1.0)),
                archived=item["id"] in archived,
                family=item.get("family"),
                grid=item.get("grid", {}) or {},
            )
        )
    return bots


def load_bots(path: Path | None = None) -> list[BotSpec]:
    """Catálogo de bots.yaml más los bots intradía declarados en un archivo propio."""
    return _load_bots_file(path or BOTS_FILE) + _load_bots_file(INTRADAY_BOTS_FILE)


def _filtered_params(func, params: dict) -> dict:
    allowed = set(inspect.signature(func).parameters)
    return {k: v for k, v in params.items() if k in allowed}


def _trades_today(bot: str, account_id: str = "paper_main") -> int:
    """Cuenta órdenes del bot en la fecha UTC actual y en su cuenta.

    F13 puede haber operado hoy en paper_main y reiniciarse en alpaca_paper:
    sin la cuenta, el límite diario contaría la orden vieja y bloquearía la
    primera apertura del bróker nuevo.
    """
    try:
        with connect(DEFAULT_DB) as con:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM orders o "
                "JOIN order_accounts oa ON oa.order_id = o.id "
                "WHERE o.bot = ? AND o.ts >= ? AND oa.account_id = ?",
                (bot, utcnow()[:10], account_id),
            ).fetchone()
        return int(row["n"])
    except Exception:
        try:
            with connect(DEFAULT_DB) as con:
                row = con.execute(
                    "SELECT COUNT(*) AS n FROM orders WHERE bot = ? AND ts >= ?",
                    (bot, utcnow()[:10]),
                ).fetchone()
            return int(row["n"])
        except Exception:
            return 0


def _open_risk_usd(positions: list[dict]) -> float:
    """Estimación conservadora del riesgo abierto (2% del nocional)."""
    return sum(abs(float(p.get("value") or 0.0)) * 0.02 for p in positions)


def _cluster_for(spec: BotSpec, clusters: list[dict]) -> int | None:
    if spec.cluster:
        return None
    symbol = (spec.universe[0] if spec.universe else "").upper()
    if not symbol:
        return None
    for index, cluster in enumerate(clusters):
        for label in cluster.get("members") or []:
            text = str(label).upper()
            if symbol in text and spec.strategy.upper() in text:
                return index
    return None


def _cluster_key(spec: BotSpec, clusters: list[dict]) -> str | None:
    """Clúster estático del bot o, si no lo tiene, el dinámico por correlación."""
    if spec.cluster:
        return f"static:{spec.cluster}"
    index = _cluster_for(spec, clusters)
    return f"corr:{index}" if index is not None else None


def run_bot(
    spec: BotSpec,
    settings: Settings,
    broker,
    *,
    dry_run: bool = False,
    start: str | None = None,
    profile: BotProfile | None = None,
    account: AccountDefinition | None = None,
    limits: AccountLimits | None = None,
    cluster_open_risk_usd: float = 0.0,
    max_cluster_risk_pct: float | None = None,
) -> list[BotAction]:
    """Evalúa un bot sobre su universo y ejecuta (o simula) los cambios."""
    if spec.strategy not in STRATEGIES:
        if spec.profile == "intraday_fx":
            # Familia intradía declarada en la Etapa 2: el motor diario no la
            # ejecuta todavía. Se bloquea la apertura, nunca se lanza una orden.
            symbol = spec.universe[0] if spec.universe else "?"
            return [
                BotAction(
                    spec.id,
                    symbol,
                    0.0,
                    0.0,
                    0.0,
                    0,
                    0,
                    "bloqueado",
                    "familia intradía pendiente de implementación (Etapa 3)",
                )
            ]
        raise ValueError(f"Estrategia desconocida en bot {spec.id}: {spec.strategy}")

    from datetime import date, timedelta

    start = start or (date.today() - timedelta(days=365 * 8)).isoformat()
    today = date.today().isoformat()
    strategy_fn = STRATEGIES[spec.strategy]
    params = _filtered_params(strategy_fn, spec.params)

    actions: list[BotAction] = []
    snap = broker.snapshot({})
    ks, _ = ensure_killswitch(
        DEFAULT_DB,
        broker.equity_series(),
        settings.risk,
        current=snap["equity"],
        tz=settings.timezone,
    )
    prop_rules = (
        rules_for_account(account)
        if account is not None
        else rules_from_settings(settings)
    )
    open_risk_usd = _open_risk_usd(snap.get("positions") or [])
    trades_today = _trades_today(
        spec.id, account.id if account is not None else "paper_main"
    )
    opened_today = 0
    opened_risk = 0.0
    try:
        account_state = PropGuard.state_from_equity(
            prop_rules,
            broker.equity_series(),
            initial_balance=prop_rules.account_size,
            open_positions=len(snap.get("positions") or []),
        )
        day_start_equity = account_state.day_start_equity
        peak_equity = account_state.peak_equity or snap["equity"]
        realized_today = account_state.closed_pnl_today
    except Exception:
        day_start_equity = snap["equity"]
        peak_equity = snap["equity"]
        realized_today = 0.0
    session = session_block(
        prop_rules,
        asset_class="equity",
    )
    flatten_session = (
        not prop_rules.weekend_holding and session.kind in {"friday", "weekend"}
    )

    for ticker in spec.universe:
        try:
            df = fetch(ticker, start, today, settings.data.cache_dir)
            result = strategy_fn(df, **params)
            price = float(df["close"].iloc[-1])
            atr_value = float(atr(df).iloc[-1])
            target = float(result.target.iloc[-1])
            # Condicionadores: multiplicador de exposición antes de los guards.
            table = bot_multiplier_table(spec.id)
            if table:
                frame, _warnings = flags_series(
                    ticker, df["close"].astype(float), db_path=DEFAULT_DB
                )
                if not frame.empty:
                    last = frame.iloc[-1]
                    flags = {name: bool(last.get(name, False)) for name in frame.columns}
                    target *= exposure_multiplier(flags, table)
        except Exception as exc:
            actions.append(
                BotAction(spec.id, ticker, 0.0, 0.0, 0.0, 0, 0, "error", str(exc)[:200])
            )
            continue

        snap = broker.snapshot({ticker: price})
        held = next((p["qty"] for p in snap["positions"] if p["ticker"] == ticker), 0.0)

        if not dry_run:
            try:
                with connect(DEFAULT_DB) as con:
                    con.execute(
                        "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (
                            utcnow(),
                            ticker,
                            spec.id,
                            "long" if target > 0 else "flat",
                            target,
                            price,
                            f"target={target:.2f}",
                        ),
                    )
            except Exception:
                pass

        if target > 0:
            max_pct = settings.risk.max_position_pct * max(0.0, min(spec.exposure, 1.0))
            desired = size_position(
                snap["equity"],
                price,
                atr_value,
                settings.risk,
                max_pct=max_pct,
            )
        else:
            desired = 0
        if flatten_session:
            desired = 0
        risk_per_share = max(atr_value * settings.risk.atr_stop_mult, price * 0.005)
        if limits is not None:
            effective_risk_pct = min(
                profile.max_risk_pct if profile else limits.per_trade_risk_pct,
                limits.per_trade_risk_pct,
            )
        else:
            effective_risk_pct = profile.max_risk_pct if profile else None
        if effective_risk_pct is not None and risk_per_share > 0:
            desired = min(
                desired,
                int(snap["equity"] * effective_risk_pct / risk_per_share),
            )

        from .limit_versions import bot_capital, cap_quantity

        capital_cap = bot_capital(DEFAULT_DB, spec.id)
        if capital_cap is not None and target > 0:
            desired = cap_quantity(desired, price, capital_cap)

        delta = int(desired - held)
        action = BotAction(spec.id, ticker, target, price, held, desired, delta, "sin_cambios")

        if delta == 0:
            actions.append(action)
            continue

        if delta > 0:
            # Datos frescos y reloj sano: sin esto no se abre nada. Los
            # cierres y reducciones (delta < 0) nunca pasan por aquí.
            fresh = check_freshness(ticker, spec.timeframe or "1d")
            if fresh["status"] == FRESHNESS_FALLA:
                action.status = "bloqueado"
                action.detail = f"datos: {fresh['reason']}"
                actions.append(action)
                record_console_action(
                    DEFAULT_DB,
                    action="freshness_block",
                    params={"bot": spec.id, "ticker": ticker},
                    result=fresh["reason"],
                    ok=False,
                    actor="orchestrator",
                )
                send_alert(
                    "freshness_block",
                    f"{spec.id}/{ticker}: {fresh['reason']}",
                    severity="warning",
                )
                continue
            clock_state = check_clock()
            if clock_state["status"] == CLOCK_FALLA:
                action.status = "bloqueado"
                action.detail = f"reloj: {clock_state['reason']}"
                actions.append(action)
                record_console_action(
                    DEFAULT_DB,
                    action="clock_block",
                    params={"bot": spec.id, "ticker": ticker},
                    result=clock_state["reason"],
                    ok=False,
                    actor="orchestrator",
                )
                send_alert(
                    "clock_block",
                    f"{spec.id}/{ticker}: {clock_state['reason']}",
                    severity="warning",
                )
                continue

        if delta > 0 and spec.profile == "intraday_fx":
            allowed, reason = symbol_allowed(DEFAULT_DB, ticker)
            if not allowed:
                action.status = "bloqueado"
                action.detail = f"universo intraday_fx: {reason}"
                actions.append(action)
                send_alert(
                    "universe_block",
                    f"{spec.id}/{ticker}: {reason}",
                    severity="warning",
                )
                continue

        if delta > 0:
            budget_check = assess_open(
                DEFAULT_DB,
                symbol=ticker,
                side="buy" if delta > 0 else "sell",
                proposed_risk_usd=abs(delta) * risk_per_share,
                equity=snap["equity"],
                positions=snap.get("positions") or [],
                limits=limits,
                bot=spec.id,
            )
            if not budget_check["allowed"]:
                action.status = "bloqueado"
                action.detail = budget_check["reason"]
                actions.append(action)
                send_alert(
                    "risk_budget_block",
                    f"{spec.id}/{ticker}: {budget_check['reason']}",
                    severity="warning",
                )
                continue
            if spec.profile == "intraday_fx":
                news = news_blackout(DEFAULT_DB, ticker)
                if news["blocked"]:
                    action.status = "bloqueado"
                    action.detail = f"noticias: {news['reason']}"
                    actions.append(action)
                    send_alert(
                        "news_blackout",
                        f"{spec.id}/{ticker}: {news['reason']}",
                        severity="warning",
                    )
                    continue

        if delta > 0:
            # Reevaluar SIEMPRE antes de cada apertura. Los cierres/reducciones
            # no pasan por estos filtros.
            ks, _ = ensure_killswitch(
                DEFAULT_DB,
                broker.equity_series(),
                settings.risk,
                current=snap["equity"],
                tz=settings.timezone,
            )
            blackout = calendar_block_for_settings(DEFAULT_DB, settings)
            session = session_block(prop_rules, asset_class="equity")

        if not allows_order(ks, delta):
            action.status = "bloqueado"
            action.detail = f"kill switch: {ks.reason}"
            actions.append(action)
            send_alert(
                "killswitch_block",
                f"{spec.id}/{ticker}: {ks.reason}",
                severity="warning",
            )
            continue

        if delta > 0 and blackout.blocked:
            action.status = "bloqueado"
            action.detail = f"calendario: {blackout.reason}"
            actions.append(action)
            send_alert(
                "calendar_block",
                f"{spec.id}/{ticker}: {blackout.reason}",
                severity="warning",
            )
            continue

        if delta > 0 and session.blocked:
            action.status = "bloqueado"
            action.detail = f"sesión: {session.reason}"
            actions.append(action)
            send_alert(
                "session_block",
                f"{spec.id}/{ticker}: {session.reason}",
                severity="warning",
            )
            continue

        if delta > 0 and account is not None:
            try:
                from .riskpause import pause_status

                pause = pause_status(
                    DEFAULT_DB, account.id, tz=settings.timezone
                )
            except Exception as exc:
                action.status = "bloqueado"
                action.detail = f"pausa de riesgo no disponible: {exc}"[:200]
                actions.append(action)
                continue
            if pause.get("paused"):
                action.status = "bloqueado"
                action.detail = f"pausa de aperturas: {pause.get('reason')}"
                actions.append(action)
                send_alert(
                    "risk_pause_block",
                    f"{spec.id}/{ticker}: {pause.get('reason')}",
                    severity="warning",
                )
                continue

        if delta > 0:
            proposed_risk = abs(delta) * risk_per_share
            from .symbol_risk import open_risk_by_symbol, symbol_cap_usd

            symbol_risk = open_risk_by_symbol(
                snap.get("positions") or [],
                broker,
                account_id=account.id if account is not None else "paper_main",
            ).get(ticker.upper(), 0.0)
            symbol_cap = symbol_cap_usd(account, ticker)
            account_guard = evaluate_account(
                prop_rules,
                AccountSnapshot(
                    equity=snap["equity"],
                    day_start_equity=day_start_equity,
                    initial_balance=prop_rules.account_size,
                    peak_equity=peak_equity,
                    realized_pnl_today=realized_today,
                    open_positions=len(snap.get("positions") or []),
                    open_risk_usd=open_risk_usd + opened_risk,
                    trades_today=trades_today + opened_today,
                ),
                limits=limits,
                max_risk_pct=profile.max_risk_pct if profile else None,
                max_trades_per_day=profile.max_trades_per_day if profile else None,
                proposed_risk_usd=proposed_risk,
                cluster_open_risk_usd=cluster_open_risk_usd,
                max_cluster_risk_pct=max_cluster_risk_pct,
                symbol_open_risk_usd=symbol_risk,
                symbol_risk_cap_usd=symbol_cap,
                symbol=ticker,
            )
            if not account_guard.allowed:
                action.status = "bloqueado"
                action.detail = f"guard de cuenta: {account_guard.reason}"
                actions.append(action)
                send_alert(
                    "account_guard_block",
                    f"{spec.id}/{ticker}: {account_guard.reason}",
                    severity="warning",
                )
                continue

        if delta > 0:
            check = check_order(
                equity=snap["equity"],
                cash=snap["cash"],
                price=price,
                qty=delta,
                current_positions=len(snap["positions"]),
                gross_exposure=snap["positions_value"],
                cfg=settings.risk,
            )
            if not check.approved or check.qty <= 0:
                action.status = "bloqueado"
                action.detail = check.reason
                actions.append(action)
                send_alert(
                    "guard_block",
                    f"{spec.id}/{ticker}: {check.reason}",
                    severity="warning",
                )
                continue
            if check.qty < delta:
                action.detail = check.reason
            delta = check.qty
            action.delta = delta

        if dry_run:
            action.status = "dry_run"
            actions.append(action)
            continue

        entry_risk = abs(delta) * risk_per_share if delta > 0 else None
        entry_stop = price - risk_per_share if delta > 0 else None
        try:
            order = broker.submit_market(
                ticker,
                delta,
                price,
                bot=spec.id,
                reason=f"target={target:.2f}",
                risk_usd=entry_risk,
                stop_price=entry_stop,
            )
            action.status = "ejecutado"
            action.order = order
            if delta > 0:
                opened_risk += abs(delta) * risk_per_share
                opened_today += 1
        except Exception as exc:
            action.status = "error"
            action.detail = str(exc)[:200]

        actions.append(action)

    return actions


def run_all(
    settings: Settings,
    broker=None,
    *,
    broker_factory=None,
    only: str | None = None,
    dry_run: bool = False,
    include_disabled: bool = False,
    now: datetime | None = None,
    profiles: dict[str, BotProfile] | None = None,
    cluster_report: dict | None = None,
) -> list[BotAction]:
    """Ejecuta los bots habilitados, cada uno contra el bróker de su cuenta.

    `broker_factory(account)` permite que F13 use `alpaca_paper` mientras
    `trend-spy` sigue en `paper_main`. Si no se pasa fábrica, se usa el
    `broker` recibido (comportamiento anterior y tests existentes).
    """
    if broker is None and broker_factory is None:
        raise ValueError("run_all necesita un broker o un broker_factory")
    actions: list[BotAction] = []
    current = now or datetime.now(timezone.utc)
    profile_map = profiles if profiles is not None else load_profiles()
    clusters = (cluster_report if cluster_report is not None else load_clusters()).get(
        "clusters", []
    )
    specs = load_bots()
    account_map = load_accounts()
    needs_cluster = bool(clusters) or any(spec.cluster for spec in specs)
    from .market_pilots import active_market, market_for_bot

    active_pilot = active_market(DEFAULT_DB)
    brokers: dict[str, object] = {}
    account_equity: dict[str, float] = {}

    def _broker_for(account):
        if broker_factory is None:
            return broker
        key = str(account.id)
        if key not in brokers:
            brokers[key] = broker_factory(account)
        return brokers[key]

    cluster_used: dict[str, float] = {}
    for spec in specs:
        if only and spec.id != only:
            continue
        if spec.archived:
            continue
        if not spec.enabled and not include_disabled:
            continue
        if spec.type not in ("deterministic", "hybrid"):
            continue
        if active_pilot is not None and market_for_bot(spec) != active_pilot:
            continue
        profile = profile_map.get(spec.profile or "")
        if profile is None:
            # Regla dura: un bot sin perfil (o con perfil desconocido) no corre.
            continue
        account = account_map.get(spec.account or "paper_main")
        if account is None:
            continue
        # El orquestador diario solo enruta cuentas de acciones paper/Alpaca.
        # Los bots MT5/futuros tienen su propio motor intradía.
        if str(account.platform).lower() not in {"internal", "paper", "alpaca"}:
            continue
        try:
            active_broker = _broker_for(account)
        except Exception as exc:
            actions.append(
                BotAction(
                    spec.id,
                    spec.universe[0] if spec.universe else "?",
                    0.0,
                    0.0,
                    0.0,
                    0,
                    0,
                    "error",
                    f"bróker {account.id}: {exc}"[:200],
                )
            )
            continue
        limits = effective_limits(DEFAULT_DB, account)
        if not profile.schedule.allows(current):
            continue
        equity = account_equity.get(account.id)
        if equity is None:
            equity = (
                float(active_broker.snapshot({}).get("equity") or 0.0)
                if needs_cluster
                else 0.0
            )
            account_equity[account.id] = equity
        cluster = _cluster_key(spec, clusters)
        cluster_key = f"{account.id}:{cluster}" if cluster else None
        risk_pct = min(profile.max_risk_pct, limits.per_trade_risk_pct)
        reserved = equity * risk_pct if equity > 0 else 0.0
        if (
            cluster_key is not None
            and equity > 0
            and cluster_used.get(cluster_key, 0.0) + reserved
            > equity * profile.max_cluster_risk_pct + 1e-9
        ):
            continue
        actions.extend(
            run_bot(
                spec,
                settings,
                active_broker,
                dry_run=dry_run,
                profile=profile,
                account=account,
                limits=limits,
                cluster_open_risk_usd=cluster_used.get(cluster_key, 0.0)
                if cluster_key is not None
                else 0.0,
                max_cluster_risk_pct=profile.max_cluster_risk_pct,
            )
        )
        if cluster_key is not None and any(
            action.delta > 0 and action.status in {"dry_run", "ejecutado"}
            for action in actions
            if action.bot == spec.id
        ):
            cluster_used[cluster_key] = cluster_used.get(cluster_key, 0.0) + reserved
    return actions


def write_dry_run_log(
    actions: list[BotAction],
    out_dir: str | Path,
    *,
    broker: str,
    when: datetime | None = None,
) -> str:
    """Persiste un dry-run en JSON para revisar la fase paper sin órdenes."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = when or datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "broker": broker,
        "dry_run": True,
        "actions": [asdict(a) for a in actions],
    }
    path = out / f"dryrun_{now.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


__all__ = [
    "BotAction",
    "BotSpec",
    "load_archive_ids",
    "load_bots",
    "run_all",
    "run_bot",
    "write_dry_run_log",
]
