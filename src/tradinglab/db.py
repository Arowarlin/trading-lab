from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    bot TEXT,
    params TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_id INTEGER,
    ticker TEXT NOT NULL,
    bot TEXT NOT NULL,
    side TEXT NOT NULL,
    strength REAL,
    price REAL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'market',
    limit_price REAL,
    status TEXT NOT NULL,
    broker_id TEXT,
    bot TEXT,
    reason TEXT,
    run_id INTEGER,
    risk_usd REAL,
    stop_price REAL,
    magic INTEGER,
    prev_hash TEXT,
    row_hash TEXT
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    commission REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    qty REAL NOT NULL,
    avg_price REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    equity REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    model TEXT,
    purpose TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    ok INTEGER NOT NULL,
    error TEXT,
    schema_ok INTEGER,
    schema_error TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT,
    message TEXT,
    data TEXT
);

CREATE TABLE IF NOT EXISTS killswitch (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    triggered_at TEXT,
    reset_at TEXT,
    equity REAL,
    peak REAL,
    day_start REAL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    severity TEXT,
    channel TEXT,
    ok INTEGER NOT NULL,
    error TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS reconciliation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    broker_equity REAL,
    db_equity REAL,
    diff_equity REAL,
    broker_positions INTEGER,
    db_positions INTEGER,
    diff_positions INTEGER,
    status TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS f13_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    bot TEXT NOT NULL,
    symbol TEXT NOT NULL,
    start_date TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    criteria TEXT NOT NULL,
    frozen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS f13_refreezes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    new_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    changed_files TEXT,
    file_hashes TEXT,
    actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS f13_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    daily_return REAL NOT NULL,
    drawdown REAL NOT NULL,
    spy_close REAL,
    spy_return REAL,
    open_positions INTEGER NOT NULL,
    trades INTEGER NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS bot_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot TEXT NOT NULL,
    strategy TEXT NOT NULL,
    universe TEXT NOT NULL,
    params TEXT NOT NULL,
    exposure REAL NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_return REAL,
    sharpe REAL,
    max_drawdown REAL,
    num_trades INTEGER,
    win_rate REAL,
    expectancy REAL,
    status TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS decision_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    rating TEXT NOT NULL,
    confidence REAL,
    model TEXT,
    prompt_version TEXT,
    prompt_hash TEXT,
    ref_price REAL,
    return_1d REAL,
    return_5d REAL,
    return_20d REAL,
    updated_at TEXT,
    analysts TEXT,
    duration_s REAL,
    UNIQUE(ticker, decision_date, mode)
);
CREATE TABLE IF NOT EXISTS agent_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    lite_rating TEXT,
    lite_confidence REAL,
    lite_target REAL,
    deep_rating TEXT,
    deep_confidence REAL,
    deep_target REAL,
    lite_model TEXT,
    deep_model TEXT,
    lite_prompt_hash TEXT,
    deep_prompt_hash TEXT,
    lite_analysts TEXT,
    deep_analysts TEXT,
    lite_duration_s REAL,
    deep_duration_s REAL,
    agreement INTEGER,
    retrospective INTEGER NOT NULL DEFAULT 0,
    lite_error TEXT,
    deep_error TEXT,
    UNIQUE(ticker, decision_date, retrospective)
);

CREATE TABLE IF NOT EXISTS lite_model_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    model_a TEXT NOT NULL,
    model_b TEXT NOT NULL,
    rating_a TEXT,
    confidence_a REAL,
    elapsed_a REAL,
    rating_b TEXT,
    confidence_b REAL,
    elapsed_b REAL,
    agreement INTEGER,
    prompt_hash_a TEXT,
    prompt_hash_b TEXT,
    error_a TEXT,
    error_b TEXT,
    UNIQUE(ticker, decision_date, model_a, model_b)
);

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    published_at TEXT,
    hash TEXT NOT NULL UNIQUE,
    trusted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS news_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL,
    ticker TEXT,
    sentiment REAL,
    relevance REAL,
    model TEXT,
    version TEXT,
    scored_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS macro_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    ts_utc TEXT NOT NULL,
    importance TEXT,
    forecast TEXT,
    actual TEXT,
    source TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_fetches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    status TEXT NOT NULL,
    events_count INTEGER NOT NULL,
    message TEXT
);

CREATE TABLE IF NOT EXISTS sec_fetches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    cik TEXT,
    status TEXT NOT NULL,
    http_status INTEGER,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS data_freshness (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    last_bar_utc TEXT,
    fetched_at_utc TEXT,
    source TEXT NOT NULL,
    ts TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS tca (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fill_id INTEGER,
    bot TEXT,
    account TEXT,
    symbol TEXT NOT NULL,
    side TEXT,
    signal_px REAL,
    order_px REAL,
    fill_px REAL,
    slippage_bps REAL,
    latency_ms REAL,
    expected_cost_bps REAL,
    realized_cost_bps REAL,
    ts_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tca_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot TEXT NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_budget (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    channel TEXT,
    severity TEXT
);

CREATE TABLE IF NOT EXISTS console_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT NOT NULL,
    ok INTEGER NOT NULL,
    actor TEXT,
    detail TEXT,
    prev_hash TEXT,
    row_hash TEXT
);

CREATE TABLE IF NOT EXISTS bot_runtime_state (
    bot TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS bot_runtime_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot TEXT NOT NULL,
    before_enabled INTEGER,
    after_enabled INTEGER NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS account_cash_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT,
    origin TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'lesson',
    hypothesis TEXT NOT NULL,
    evidence TEXT,
    author TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    champion TEXT,
    challenger TEXT,
    action TEXT,
    approved_at TEXT,
    approved_by TEXT,
    rejected_at TEXT,
    rejected_by TEXT,
    reject_reason TEXT,
    applied_at TEXT,
    applied_by TEXT,
    applied_action TEXT,
    reversal TEXT,
    reverted_at TEXT,
    reverted_by TEXT
);

CREATE TABLE IF NOT EXISTS lesson_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    lesson_id INTEGER NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    metric TEXT,
    value REAL,
    passed INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS learning_holdout (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    hash TEXT NOT NULL,
    sealed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS optimization_trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    study TEXT NOT NULL,
    trial INTEGER NOT NULL,
    symbol TEXT,
    strategy TEXT,
    params TEXT,
    value REAL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_optimization_trials_study
    ON optimization_trials(study);
CREATE TABLE IF NOT EXISTS holdout_evaluations (
    config_hash TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT NOT NULL,
    first_read_at TEXT NOT NULL,
    last_read_at TEXT NOT NULL,
    reads INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS holdout_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    symbol TEXT,
    strategy TEXT,
    params TEXT,
    cached INTEGER NOT NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_holdout_reads_hash
    ON holdout_reads(config_hash);
CREATE TABLE IF NOT EXISTS strategy_trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    family TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    symbol TEXT NOT NULL,
    params TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    result TEXT,
    outcome TEXT NOT NULL DEFAULT 'failed',
    reason TEXT,
    source TEXT NOT NULL DEFAULT 'humano',
    run_id TEXT,
    lesson_id INTEGER,
    fingerprint TEXT,
    counted INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_strategy_trials_family
    ON strategy_trials(family, symbol, fingerprint);
CREATE INDEX IF NOT EXISTS idx_strategy_trials_symbol_ts
    ON strategy_trials(symbol, ts);
CREATE INDEX IF NOT EXISTS idx_strategy_trials_run
    ON strategy_trials(run_id);
CREATE TABLE IF NOT EXISTS broker_spreads (
    symbol TEXT NOT NULL,
    hour_utc INTEGER NOT NULL,
    median_bps REAL,
    p75_bps REAL,
    n_ticks INTEGER NOT NULL,
    from_ts TEXT,
    to_ts TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY(symbol, hour_utc, source)
);
CREATE INDEX IF NOT EXISTS idx_broker_spreads_symbol
    ON broker_spreads(symbol, source);
CREATE TABLE IF NOT EXISTS broker_slippage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    hour_utc INTEGER NOT NULL,
    requested REAL NOT NULL,
    filled REAL,
    slippage_bps REAL,
    volume REAL NOT NULL,
    order_type TEXT NOT NULL,
    leg TEXT NOT NULL DEFAULT 'entry',
    requote INTEGER NOT NULL DEFAULT 0,
    retcode INTEGER,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_broker_slippage_symbol
    ON broker_slippage(symbol, leg, ts);
CREATE TABLE IF NOT EXISTS asset_aliases (
    canonical TEXT PRIMARY KEY,
    broker_symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    profile TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_slice_overrides (
    bot TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    slice_pct REAL NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS risk_slice_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    asset TEXT NOT NULL,
    bot TEXT NOT NULL,
    old_slice_pct REAL,
    new_slice_pct REAL NOT NULL,
    action TEXT NOT NULL,
    actor TEXT,
    reason TEXT,
    reverted_at TEXT
);
CREATE TABLE IF NOT EXISTS lifecycle_bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot TEXT NOT NULL UNIQUE,
    asset TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'candidato',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    criteria TEXT,
    criteria_hash TEXT,
    frozen_at TEXT,
    evidence TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT,
    reason TEXT,
    criteria_hash TEXT
);

CREATE TABLE IF NOT EXISTS model_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    kind TEXT NOT NULL,
    symbol TEXT NOT NULL,
    features TEXT NOT NULL,
    train_start TEXT,
    train_end TEXT,
    test_start TEXT,
    test_end TEXT,
    metrics TEXT NOT NULL,
    coefficients TEXT NOT NULL,
    hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS model_registry_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    model_id INTEGER,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS account_limit_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    limits TEXT NOT NULL,
    effective TEXT NOT NULL,
    hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    reason TEXT,
    UNIQUE(account_id, version)
);

CREATE TABLE IF NOT EXISTS bot_capital_limits (
    bot TEXT PRIMARY KEY,
    max_capital_usd REAL NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_capital_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot TEXT NOT NULL,
    old_value REAL,
    new_value REAL NOT NULL,
    updated_by TEXT NOT NULL,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_lesson_tests_lesson ON lesson_tests(lesson_id);
CREATE INDEX IF NOT EXISTS idx_account_cash_flows_account
    ON account_cash_flows(account_id, ts);
CREATE INDEX IF NOT EXISTS idx_console_actions_ts ON console_actions(ts);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
CREATE INDEX IF NOT EXISTS idx_reconciliation_ts ON reconciliation(ts);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);
CREATE INDEX IF NOT EXISTS idx_orders_ts ON orders(ts);
CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity(ts);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db(path: str | Path) -> None:
    with connect(path) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        _migrate_equity(con)
        _migrate_bot_evaluations(con)
        _migrate_decision_outcomes(con)
        _migrate_llm_calls(con)
        _migrate_orders(con)
        _migrate_order_accounts(con)
        _migrate_audit_chain(con)
        _migrate_f13(con)
        _migrate_strategy_trials(con)
        _migrate_fills_mt5(con)
        _migrate_forward_state(con)
        _migrate_chain_orders(con)
        _migrate_ai_trades(con)


def _migrate_strategy_trials(con: sqlite3.Connection) -> None:
    """Añade `counted` a bases anteriores y marca todo lo previo como contado.

    Una prueba antigua no nació de una campaña, así que cuenta entera en el
    DSR. Las celdas de campaña se insertan después con `counted = 0` para no
    contarse dos veces (su `N_total` ya está en `campaign_registry`), y esta
    migración **no** las toca: solo rellena la columna cuando falta y los NULL.
    """
    columns = [
        row["name"] for row in con.execute("PRAGMA table_info(strategy_trials)").fetchall()
    ]
    if not columns:
        return
    if "counted" not in columns:
        con.execute(
            "ALTER TABLE strategy_trials "
            "ADD COLUMN counted INTEGER NOT NULL DEFAULT 1"
        )
    con.execute("UPDATE strategy_trials SET counted = 1 WHERE counted IS NULL")


def _migrate_f13(con: sqlite3.Connection) -> None:
    """Huellas por archivo e historial de re-congelados. Solo aditivo."""
    columns = [
        row["name"] for row in con.execute("PRAGMA table_info(f13_config)").fetchall()
    ]
    if not columns:
        return
    for column in ("file_hashes", "previous_hash", "refreeze_reason", "refrozen_at"):
        if column not in columns:
            con.execute(f"ALTER TABLE f13_config ADD COLUMN {column} TEXT")


def _migrate_equity(con: sqlite3.Connection) -> None:
    """`equity` pasó de ts como PK a id autoincremental (varios snapshots por segundo)."""
    columns = [row["name"] for row in con.execute("PRAGMA table_info(equity)").fetchall()]
    if columns and "id" not in columns:
        con.executescript(
            """
            ALTER TABLE equity RENAME TO equity_old;
            CREATE TABLE equity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                equity REAL NOT NULL
            );
            INSERT INTO equity(ts, cash, positions_value, equity)
                SELECT ts, cash, positions_value, equity FROM equity_old ORDER BY ts;
            DROP TABLE equity_old;
            CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity(ts);
            """
        )


def _migrate_orders(con: sqlite3.Connection) -> None:
    """Añade el riesgo inicial, el stop y el magic a órdenes antiguas."""
    columns = [
        row["name"] for row in con.execute("PRAGMA table_info(orders)").fetchall()
    ]
    if columns and "risk_usd" not in columns:
        con.execute("ALTER TABLE orders ADD COLUMN risk_usd REAL")
    if columns and "stop_price" not in columns:
        con.execute("ALTER TABLE orders ADD COLUMN stop_price REAL")
    if columns and "magic" not in columns:
        con.execute("ALTER TABLE orders ADD COLUMN magic INTEGER")


def _migrate_order_accounts(con: sqlite3.Connection) -> None:
    """Separa las órdenes por cuenta sin tocar la tabla auditada `orders`.

    `orders` tiene una cadena de hash que se calcula con todas sus columnas;
    añadirle una columna rompería los hashes antiguos. Esta tabla auxiliar
    guarda la cuenta de cada orden. Las órdenes previas se asignan a
    `paper_main`, que era la única cuenta del orquestador diario.
    """
    con.execute(
        "CREATE TABLE IF NOT EXISTS order_accounts ("
        "order_id INTEGER PRIMARY KEY,"
        "account_id TEXT NOT NULL,"
        "created_at TEXT NOT NULL"
        ")"
    )
    con.execute(
        "INSERT OR IGNORE INTO order_accounts(order_id, account_id, created_at) "
        "SELECT id, 'paper_main', ts FROM orders "
        "WHERE id NOT IN (SELECT order_id FROM order_accounts)"
    )


def _migrate_audit_chain(con: sqlite3.Connection) -> None:
    """Añade las columnas de la cadena de hash. Solo aditivo e idempotente.

    Las filas anteriores se quedan con `prev_hash` y `row_hash` a NULL: son
    "antes de la cadena" y no rompen la verificación.
    """
    for table in ("console_actions", "orders"):
        columns = [
            row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if not columns:
            continue
        if "prev_hash" not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN prev_hash TEXT")
        if "row_hash" not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN row_hash TEXT")


def _migrate_bot_evaluations(con: sqlite3.Connection) -> None:
    columns = [
        row["name"]
        for row in con.execute("PRAGMA table_info(bot_evaluations)").fetchall()
    ]
    if columns and "expectancy" not in columns:
        con.execute("ALTER TABLE bot_evaluations ADD COLUMN expectancy REAL")


def _migrate_decision_outcomes(con: sqlite3.Connection) -> None:
    """Añade procedencia (analistas/duración) sin perder el historial."""
    columns = [
        row["name"]
        for row in con.execute("PRAGMA table_info(decision_outcomes)").fetchall()
    ]
    if columns and "analysts" not in columns:
        con.execute("ALTER TABLE decision_outcomes ADD COLUMN analysts TEXT")
    if columns and "duration_s" not in columns:
        con.execute("ALTER TABLE decision_outcomes ADD COLUMN duration_s REAL")


def _migrate_llm_calls(con: sqlite3.Connection) -> None:
    """Añade el resultado de validación de esquema sin perder llamadas."""
    columns = [
        row["name"] for row in con.execute("PRAGMA table_info(llm_calls)").fetchall()
    ]
    if columns and "schema_ok" not in columns:
        con.execute("ALTER TABLE llm_calls ADD COLUMN schema_ok INTEGER")
    if columns and "schema_error" not in columns:
        con.execute("ALTER TABLE llm_calls ADD COLUMN schema_error TEXT")


def _migrate_fills_mt5(con: sqlite3.Connection) -> None:
    """Amplía `fills` para los deals de MT5 sin perder los fills del paper.

    `order_id` deja de ser NOT NULL (un deal no siempre tiene orden en el
    laboratorio) y se añaden las columnas del deal. `deal_id` es único: la
    sincronización es idempotente. Es una reconstrucción de tabla, pero solo
    añade columnas y conserva todas las filas.
    """
    columns = [row["name"] for row in con.execute("PRAGMA table_info(fills)").fetchall()]
    if not columns:
        return
    if "deal_id" not in columns:
        con.executescript(
            """
            CREATE TABLE fills_mt5_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                ts TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL NOT NULL,
                commission REAL NOT NULL DEFAULT 0,
                bot TEXT,
                account TEXT,
                symbol TEXT,
                side TEXT,
                volume REAL,
                swap REAL,
                deal_id INTEGER,
                magic INTEGER,
                ts_utc TEXT
            );
            INSERT INTO fills_mt5_new (id, order_id, ts, qty, price, commission)
                SELECT id, order_id, ts, qty, price, commission FROM fills;
            DROP TABLE fills;
            ALTER TABLE fills_mt5_new RENAME TO fills;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fills_deal_id
                ON fills(deal_id) WHERE deal_id IS NOT NULL;
            """
        )
        columns = [
            row["name"] for row in con.execute("PRAGMA table_info(fills)").fetchall()
        ]
    if "contract_size" not in columns:
        con.execute("ALTER TABLE fills ADD COLUMN contract_size REAL")


def _migrate_forward_state(con: sqlite3.Connection) -> None:
    """Estado mínimo del forward y cursor de deals de MT5. Solo aditivo."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS forward_state (
            bot TEXT PRIMARY KEY,
            last_signal REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mt5_fills_sync (
            account TEXT PRIMARY KEY,
            last_deal_time TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _migrate_ai_trades(con: sqlite3.Connection) -> None:
    """Tabla del carril IA discrecional. Solo aditivo."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT UNIQUE,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            setup TEXT NOT NULL,
            side TEXT NOT NULL,
            thesis TEXT,
            confidence INTEGER,
            snapshot_hash TEXT,
            playbook_version INTEGER,
            timeframe TEXT,
            cost_ratio REAL,
            entry REAL,
            sl REAL,
            tp REAL,
            volume REAL,
            risk_usd REAL,
            magic INTEGER,
            ticket INTEGER,
            status TEXT NOT NULL DEFAULT 'proposed',
            source TEXT NOT NULL DEFAULT 'forward',
            exit_price REAL,
            exit_ts TEXT,
            pnl REAL,
            r_multiple REAL,
            shadow_side TEXT,
            shadow_entry REAL,
            shadow_sl REAL,
            shadow_tp REAL,
            shadow_status TEXT,
            shadow_exit REAL,
            shadow_pnl REAL,
            shadow_r REAL,
            shadow_seed INTEGER,
            shadow2_side TEXT,
            shadow2_entry REAL,
            shadow2_sl REAL,
            shadow2_tp REAL,
            shadow2_status TEXT,
            shadow2_r REAL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_trades_status ON ai_trades(status);
        CREATE INDEX IF NOT EXISTS idx_ai_trades_ts ON ai_trades(ts);
        CREATE TABLE IF NOT EXISTS ai_cell_state (
            strategy TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            reason TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (strategy, symbol, timeframe)
        );
        CREATE TABLE IF NOT EXISTS ai_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT UNIQUE NOT NULL,
            ts TEXT NOT NULL,
            session_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            setups TEXT NOT NULL,
            bias TEXT NOT NULL,
            forbidden_hours TEXT,
            reason TEXT,
            playbook_version INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_plans_active
            ON ai_plans(session_date, symbol, active);
        CREATE TABLE IF NOT EXISTS ai_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            decision_date TEXT,
            session TEXT,
            style TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT,
            strategy TEXT NOT NULL,
            setup_valid INTEGER NOT NULL DEFAULT 0,
            decision TEXT NOT NULL,
            reason TEXT,
            confidence INTEGER,
            snapshot TEXT,
            playbook_version INTEGER,
            source TEXT NOT NULL DEFAULT 'forward',
            plan_id TEXT,
            result_r REAL,
            shadow_r REAL,
            entry REAL,
            sl REAL,
            tp REAL,
            exit_ts TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_decisions_ts ON ai_decisions(ts);
        CREATE INDEX IF NOT EXISTS idx_ai_decisions_style ON ai_decisions(style, decision);
        CREATE INDEX IF NOT EXISTS idx_ai_decisions_source
            ON ai_decisions(source, decision);
        CREATE TABLE IF NOT EXISTS ai_learn_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            style TEXT,
            symbol TEXT,
            strategy TEXT,
            timeframe TEXT,
            detail TEXT,
            evidence TEXT,
            playbook_version INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_ai_learn_changes_ts
            ON ai_learn_changes(ts);
        CREATE TABLE IF NOT EXISTS ai_distill_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            style TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            bot TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            filter TEXT,
            evidence TEXT,
            validation TEXT,
            playbook_version INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_ai_distill_runs_ts
            ON ai_distill_runs(ts);
        CREATE INDEX IF NOT EXISTS idx_ai_distill_runs_bot
            ON ai_distill_runs(bot, status);
        CREATE TABLE IF NOT EXISTS execution_lease (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            host TEXT NOT NULL,
            pid INTEGER,
            session TEXT,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        """
    )
    columns = [row["name"] for row in con.execute("PRAGMA table_info(ai_trades)").fetchall()]
    for column, kind in (
        ("timeframe", "TEXT"), ("cost_ratio", "REAL"),
        ("style", "TEXT"), ("result_r", "REAL"),
        ("source", "TEXT NOT NULL DEFAULT 'forward'"),
        ("shadow2_side", "TEXT"), ("shadow2_entry", "REAL"),
        ("shadow2_sl", "REAL"), ("shadow2_tp", "REAL"),
        ("shadow2_status", "TEXT"), ("shadow2_r", "REAL"),
    ):
        if column not in columns:
            con.execute(f"ALTER TABLE ai_trades ADD COLUMN {column} {kind}")
    decision_columns = [
        row["name"] for row in con.execute("PRAGMA table_info(ai_decisions)").fetchall()
    ]
    for column, kind in (("decision_date", "TEXT"), ("session", "TEXT"),
                         ("snapshot", "TEXT"), ("source", "TEXT DEFAULT 'forward'"),
                         ("plan_id", "TEXT"), ("result_r", "REAL"),
                         ("shadow_r", "REAL"), ("entry", "REAL"),
                         ("sl", "REAL"), ("tp", "REAL"), ("exit_ts", "TEXT")):
        if column not in decision_columns:
            con.execute(f"ALTER TABLE ai_decisions ADD COLUMN {column} {kind}")


def _migrate_chain_orders(con: sqlite3.Connection) -> None:
    """Rehashea una sola vez la cadena de `orders` con la fila almacenada.

    `append_hashed` hasheaba el dict de entrada; una columna con DEFAULT
    (p. ej. `order_type`) quedaba con un hash que no coincidía al leerla.
    La migración es única (tabla `schema_migrations`) y solo toca orders.
    """
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations("
        "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    done = con.execute(
        "SELECT 1 FROM schema_migrations WHERE name = 'orders_chain_stored_hash'"
    ).fetchone()
    if done:
        return
    from .audit import row_hash

    rows = con.execute(
        "SELECT * FROM orders WHERE row_hash IS NOT NULL ORDER BY id"
    ).fetchall()
    prev: str | None = None
    for row in rows:
        data = dict(row)
        digest = row_hash(con, "orders", data, prev)
        con.execute(
            "UPDATE orders SET prev_hash = ?, row_hash = ? WHERE id = ?",
            (prev, digest, row["id"]),
        )
        prev = digest
    con.execute(
        "INSERT INTO schema_migrations(name, applied_at) VALUES(?, ?)",
        ("orders_chain_stored_hash", utcnow()),
    )


def log_event(path: str | Path, level: str, source: str, message: str, data: str | None = None) -> None:
    with connect(path) as con:
        con.execute(
            "INSERT INTO events(ts, level, source, message, data) VALUES(?,?,?,?,?)",
            (utcnow(), level, source, message, data),
        )
