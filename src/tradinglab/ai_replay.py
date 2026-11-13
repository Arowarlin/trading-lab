"""Replay ciego de setups históricos del carril IA.

Lee las barras cacheadas de MT5, elige momentos anteriores al corte de la
campaña 2026-11-A y pide a un modelo (por lotes) take/skip sobre un snapshot
anonimizado. Las filas van a `ai_decisions` con `source='replay'`; solo sirven
para descartar celdas, nunca para el marcador forward ni para las lecciones.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from .ai_setups import plan as setup_plan
from .ai_setups import supports, validate
from .ai_trader import (
    LONDON,
    NEW_YORK,
    STRATEGY_EXTRA,
    STRATEGY_FIELDS,
    TF_MINUTES,
    TF_SECTION,
    _audit,
    _block_from_bars,
    _bootstrap_ci,
    _cell_status,
    _cost_ratio,
    _daily,
    _daily_block,
    _session,
    _shadow_sim,
    _trend_label,
    _twin_levels,
    load_config,
)
from .alerts import send as send_alert
from .config import DEFAULT_DB, ROOT
from .db import connect, init_db
from .intraday import load_bars

REPLAY_SEED = 20261112
BATCH_SIZE = 10
CAMPAIGN_PATH = ROOT / "config" / "campaigns" / "2026-11-A.yaml"
CACHE_DIR = ROOT / "data" / "cache"
MODEL = "opencode-go/deepseek-v4.1-flash"
HORIZON = {"M15": 200, "H1": 200, "H4": 120, "D1": 100}
POINTS = {
    "US100.CASH": 0.01,
    "US500.CASH": 0.01,
    "XAUUSD": 0.01,
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "USDJPY": 0.001,
}
PRICE_FIELDS = {
    "atr", "sma5", "sma20", "sma200", "ema8", "ema9", "ema13", "ema21",
    "ema50", "bb_upper", "bb_mid", "bb_lower", "vwap", "vwap_sigma",
    "orb_high", "orb_low", "orb5_high", "orb5_low", "asian_high",
    "asian_low", "prev_high", "prev_low", "prev_mid", "prev_close",
    "dc20_high", "dc20_low", "dc55_high", "dc55_low", "open", "high",
    "low", "close", "mother_high", "mother_low",
}


class ReplayError(ValueError):
    pass


@dataclass
class ReplayMoment:
    symbol: str
    strategy: str
    timeframe: str
    side: str
    moment: pd.Timestamp
    price: float
    spread: float
    point: float
    cost_ratio: float | None
    sl: float
    tp: float | None
    rr: float | None
    snapshot: dict
    anonymized: dict
    future: pd.DataFrame


@dataclass
class ReplayPlan:
    style: str
    n: int
    moments: list[ReplayMoment]
    calls: int
    tokens_est: int
    cutoff: pd.Timestamp | None
    skipped: list[dict]
    config: dict

    def summary(self) -> dict:
        return {
            "style": self.style,
            "requested": self.n,
            "decisions": len(self.moments),
            "calls": self.calls,
            "tokens_est": self.tokens_est,
            "cutoff_utc": str(self.cutoff) if self.cutoff is not None else None,
            "skipped": self.skipped,
            "yes": False,
        }


def load_cutoff(path: str | Path = CAMPAIGN_PATH) -> pd.Timestamp | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        cutoff = raw.get("cutoff_utc")
    except Exception:
        return None
    if not cutoff:
        return None
    stamp = pd.Timestamp(cutoff)
    if stamp.tz is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _asset_class(symbol: str) -> str:
    name = str(symbol).upper()
    if name.startswith(("US100", "US500", "US30", "US2000", "GER40", "FRA40",
                        "UK100", "JP225", "HK50", "EU50", "AUS200")):
        return "index"
    if name.startswith(("XAU", "XAG", "XPT", "XPD")):
        return "metal"
    return "forex"


def _point(symbol: str) -> float:
    return POINTS.get(str(symbol).upper(), 0.01)


def _load_bars(symbol: str, timeframe: str, cache_dir: str | Path) -> pd.DataFrame:
    if str(timeframe).upper() == "D1":
        h4 = load_bars(cache_dir, symbol, "H4")
        return _daily(h4)
    return load_bars(cache_dir, symbol, timeframe)


def _normalize_value(field: str, value, factor: float):
    if value in (None, "", "Sin datos") or isinstance(value, bool):
        return value
    if field not in PRICE_FIELDS:
        return value
    try:
        return round(float(value) * factor, 4)
    except (TypeError, ValueError):
        return value


def _anonymized(moment: ReplayMoment) -> dict:
    factor = 100.0 / float(moment.price) if moment.price else 1.0
    block = moment.snapshot.get(TF_SECTION.get(moment.timeframe, ""), {}) or {}
    data: dict = {}
    for field in STRATEGY_FIELDS.get(moment.strategy, ()):
        data[field] = _normalize_value(field, block.get(field), factor)
    for section, fields in STRATEGY_EXTRA.get(moment.strategy, {}).items():
        extra = moment.snapshot.get(section) or {}
        data[section] = {
            field: _normalize_value(field, extra.get(field), factor)
            for field in fields
        }
    if moment.strategy in {
        "rsi2_connors", "donchian_turtle", "inside_bar", "trend_pullback",
    } and "d1" in moment.snapshot:
        data["trend_d1"] = _trend_label(moment.snapshot.get("d1") or {}, d1=True)
    if moment.strategy == "trend_pullback" and "h4" in moment.snapshot:
        data["trend_h4"] = _trend_label(moment.snapshot.get("h4") or {})
    sl_norm = round(100.0 + (moment.sl - moment.price) * factor, 4)
    tp_norm = (
        round(100.0 + (moment.tp - moment.price) * factor, 4)
        if moment.tp is not None else None
    )
    return {
        "asset_class": _asset_class(moment.symbol),
        "style": "replay",
        "strategy": moment.strategy,
        "timeframe": moment.timeframe,
        "side": moment.side,
        "price": 100.0,
        "sl": sl_norm,
        "tp": tp_norm,
        "rr": moment.rr,
        "cost_r": round(moment.cost_ratio, 4) if moment.cost_ratio is not None else None,
        "data": data,
    }


def _assignments(style: str, strategy: str | None, symbol: str | None,
                 config: dict) -> list[tuple[str, str, str]]:
    item = config["styles"].get(style)
    if item is None:
        raise ReplayError(f"estilo desconocido: {style}")
    universe = {str(name).lower(): str(name) for name in config["universe"]}
    wanted_symbol = None
    if symbol:
        raw = str(symbol).strip()
        if raw.lower() not in universe:
            raise ReplayError(f"símbolo fuera del universo: {symbol}")
        wanted_symbol = universe[raw.lower()]
    allowed = item["allowed"]
    out: list[tuple[str, str, str]] = []
    for raw_symbol, strategies in allowed.items():
        canonical = universe.get(raw_symbol.lower(), raw_symbol)
        if wanted_symbol and canonical.upper() != wanted_symbol.upper():
            continue
        for name, frames in strategies.items():
            if strategy and name != strategy:
                continue
            if not supports(name, frames[0]):
                continue
            for frame in frames:
                out.append((canonical, name, frame))
    if not out:
        raise ReplayError(
            f"Sin datos: no hay asignaciones para style={style} "
            f"strategy={strategy or '*'} symbol={symbol or '*'}"
        )
    return out


def _session_end(moment: pd.Timestamp, strategy: str) -> pd.Timestamp | None:
    if strategy == "orb_ny":
        zone, close_at = NEW_YORK, time(16, 0)
    elif strategy == "london_breakout":
        zone, close_at = LONDON, time(16, 0)
    else:
        return None
    local = moment.astimezone(zone)
    return pd.Timestamp(
        local.replace(hour=close_at.hour, minute=close_at.minute,
                      second=0, microsecond=0)
    ).tz_convert("UTC")


def _future_for(moment: pd.Timestamp, bars: pd.DataFrame, timeframe: str,
                strategy: str, cutoff: pd.Timestamp | None) -> pd.DataFrame:
    future = bars[bars.index >= moment]
    if cutoff is not None:
        future = future[future.index < cutoff]
    end = _session_end(moment, strategy)
    if end is not None:
        future = future[future.index < end]
    return future.head(HORIZON.get(timeframe, 200))


def _snapshot_at(bars: pd.DataFrame, d1: pd.DataFrame, signal_index: int,
                 timeframe: str, symbol: str, entry_index: int) -> tuple[dict, float, float]:
    point = _point(symbol)
    entry_bar = bars.iloc[entry_index]
    price = float(entry_bar["open"])
    moment = bars.index[entry_index]
    raw_spread = float(entry_bar.get("spread") or 0.0) * point
    spread = max(raw_spread, point)
    window = bars.iloc[max(0, signal_index - 500):signal_index + 1]
    if timeframe == "D1":
        block = _daily_block(window)
        d1_block = block
        snap = {
            "symbol": symbol,
            "price": price,
            "spread": spread,
            "now": moment.isoformat(),
            "is_index": _asset_class(symbol) == "index",
            "d1": d1_block,
        }
    else:
        d1_window = d1[d1.index < moment.normalize()].tail(400)
        if len(d1_window) < 2:
            raise ReplayError("Sin datos D1")
        block = _block_from_bars(window, timeframe, d1_window, price, moment)
        d1_block = _daily_block(d1_window)
        snap = {
            "symbol": symbol,
            "price": price,
            "spread": spread,
            "now": moment.isoformat(),
            "is_index": _asset_class(symbol) == "index",
            TF_SECTION[timeframe]: block,
            "d1": d1_block,
        }
        if timeframe == "H4":
            snap["h4"] = block
    return snap, price, spread


def _valid_for_assignment(symbol: str, strategy: str, timeframe: str,
                          bars: pd.DataFrame, d1: pd.DataFrame,
                          cutoff: pd.Timestamp | None, rng: random.Random,
                          cap: int = 450) -> list[ReplayMoment]:
    frame = bars
    slippage_price = load_config().get("slippage_price", {}).get(
        str(symbol).upper()
    )
    if slippage_price is None:
        return []
    duration = timedelta(days=1) if timeframe == "D1" else timedelta(
        minutes=TF_MINUTES.get(timeframe, 60)
    )
    positions = [
        i for i, stamp in enumerate(frame.index)
        if i >= 60 and i + 1 < len(frame)
        and (cutoff is None or frame.index[i + 1] + duration < cutoff)
    ]
    if not positions:
        return []
    sample = rng.sample(positions, min(cap, len(positions)))
    out: list[ReplayMoment] = []
    for index in sample:
        entry_index = index + 1
        stamp = frame.index[entry_index]
        try:
            snap, price, spread = _snapshot_at(
                frame, d1, index, timeframe, symbol, entry_index
            )
        except Exception:
            continue
        for side in ("buy", "sell"):
            try:
                ok, _reason = validate(strategy, side, snap, timeframe)
                if not ok:
                    continue
                level = setup_plan(strategy, side, snap, timeframe)
                cost = _cost_ratio(
                    symbol, price, spread, level.stop_distance,
                    slippage_price=slippage_price,
                )
            except Exception:
                continue
            future = _future_for(stamp, frame, timeframe, strategy, cutoff)
            if len(future) < 2:
                continue
            moment = ReplayMoment(
                symbol=symbol, strategy=strategy, timeframe=timeframe,
                side=side, moment=stamp, price=price, spread=spread,
                point=_point(symbol), cost_ratio=cost,
                sl=level.sl, tp=level.tp, rr=level.rr,
                snapshot=snap, anonymized={}, future=future,
            )
            moment.anonymized = _anonymized(moment)
            out.append(moment)
            if len(out) >= 40:
                return out
    return out


def prepare_replay(style: str, n: int = 200, strategy: str | None = None,
                   symbol: str | None = None, *, cache_dir: str | Path = CACHE_DIR,
                   cutoff: pd.Timestamp | None = None,
                   seed: int = REPLAY_SEED) -> ReplayPlan:
    if str(style).lower() == "scalping":
        raise ReplayError(
            "replay no disponible para scalping: no hay barras M1 históricas garantizadas"
        )
    if n < 1:
        raise ReplayError("--n debe ser >= 1")
    cfg = load_config()
    moment_cutoff = cutoff if cutoff is not None else load_cutoff()
    assignments = _assignments(style, strategy, symbol, cfg)
    rng = random.Random(seed)
    moments: list[ReplayMoment] = []
    skipped: list[dict] = []
    for sym, strat, tf in assignments:
        try:
            bars = _load_bars(sym, tf, cache_dir)
        except Exception as exc:
            skipped.append({
                "symbol": sym, "strategy": strat, "timeframe": tf,
                "reason": f"Sin datos: {exc}",
            })
            continue
        if moment_cutoff is not None:
            before = bars[bars.index < moment_cutoff]
            if len(before) < 60:
                skipped.append({
                    "symbol": sym, "strategy": strat, "timeframe": tf,
                    "reason": "Sin datos antes del corte",
                })
                continue
        if tf == "D1":
            d1 = bars
            h4 = None
        else:
            try:
                h4 = _load_bars(sym, "H4", cache_dir)
                d1 = _daily(h4)
            except Exception:
                d1 = _daily(bars)
        found = _valid_for_assignment(
            sym, strat, tf, bars, d1, moment_cutoff, rng
        )
        if not found:
            skipped.append({
                "symbol": sym, "strategy": strat, "timeframe": tf,
                "reason": "sin setup válido en la muestra",
            })
            continue
        moments.extend(found)
    if not moments:
        raise ReplayError(
            "Sin datos: no hay momentos con setup válido antes del corte"
        )
    rng.shuffle(moments)
    moments = moments[:n]
    calls = math.ceil(len(moments) / BATCH_SIZE)
    tokens_est = len(moments) * 320 + calls * 260
    return ReplayPlan(
        style=style, n=n, moments=moments, calls=calls,
        tokens_est=tokens_est, cutoff=moment_cutoff,
        skipped=skipped, config=cfg,
    )


def _batch_prompt(batch: list[dict]) -> str:
    payload = json.dumps(batch, ensure_ascii=False, separators=(",", ":"))
    return (
        "Eres un evaluador ciego de setups. No conoces el activo ni la fecha; "
        "solo la clase de activo, la estrategia, el timeframe, el lado y un "
        "snapshot con precios normalizados a 100. Decide take o skip para cada "
        "id, con un motivo breve. No uses herramientas. Devuelve SOLO un array "
        "JSON con objetos {\"id\":<int>,\"decision\":\"take\"|\"skip\","
        "\"reason\":\"<=200 caracteres\"}. Setup batch:\n" + payload
    )


def _extract_json_array(text: str) -> list:
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        raise ReplayError("el modelo no devolvió un array JSON")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ReplayError(f"JSON del modelo inválido: {exc}") from exc
    if not isinstance(data, list):
        raise ReplayError("el modelo no devolvió una lista")
    return data


def _ask_opencode(prompt: str, *, timeout: int = 180) -> list:
    executable = shutil.which("opencode")
    if not executable:
        raise ReplayError("opencode no está en PATH")
    path = Path(executable)
    if path.suffix.lower() in {".cmd", ".bat"}:
        candidate = (
            path.parent / "node_modules" / "@opencode" / "cli" / "bin" /
            "opencode.exe"
        )
        if candidate.exists():
            executable = str(candidate)
    command = [
        executable, "run", "--agent", "ai-replay", "--model", MODEL,
        "--auto", prompt,
    ]
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReplayError(f"opencode agotó {timeout}s") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:400]
        raise ReplayError(f"opencode falló ({proc.returncode}): {detail}")
    return _extract_json_array(proc.stdout)


def _parse_batch(raw: list, batch: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        decision = str(item.get("decision") or "").lower()
        if decision not in {"take", "skip"}:
            decision = "skip"
            reason = "respuesta inválida del modelo"
        else:
            reason = str(item.get("reason") or "").strip() or "sin motivo"
        if item_id not in {entry["id"] for entry in batch}:
            continue
        out[item_id] = {"decision": decision, "reason": reason[:200]}
    for entry in batch:
        out.setdefault(
            entry["id"], {"decision": "skip", "reason": "sin respuesta del modelo"}
        )
    return out


def _insert_decision(db_path: str | Path, moment: ReplayMoment, *,
                     run_id: str, decision: str, reason: str,
                     result_r: float | None, shadow_r: float | None,
                     config: dict) -> int:
    anonymized = dict(moment.anonymized)
    anonymized.pop("id", None)
    init_db(db_path)
    with connect(db_path) as con:
        cursor = con.execute(
            "INSERT INTO ai_decisions"
            "(ts, decision_date, session, style, symbol, timeframe, strategy, "
            " setup_valid, decision, reason, confidence, snapshot, "
            " playbook_version, source, plan_id, result_r, shadow_r, "
            " entry, sl, tp, exit_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(),
                moment.moment.date().isoformat(),
                _session(moment.moment),
                "replay",
                moment.symbol,
                moment.timeframe,
                moment.strategy,
                1,
                decision,
                reason[:200],
                None,
                json.dumps(anonymized, ensure_ascii=False, separators=(",", ":")),
                config["playbook_version"],
                "replay",
                run_id,
                result_r,
                shadow_r,
                moment.price,
                moment.sl,
                moment.tp,
                None,
            ),
        )
        return int(cursor.lastrowid)


def _simulate(moment: ReplayMoment, side: str, entry: float,
              sl: float, tp: float | None) -> float | None:
    row = {
        "shadow_side": side,
        "shadow_entry": entry,
        "shadow_sl": sl,
        "shadow_tp": tp,
        "setup": moment.strategy,
        "timeframe": moment.timeframe,
    }
    try:
        result = _shadow_sim(
            row, moment.future, prefix="shadow", strategy=moment.strategy
        )
    except Exception:
        return None
    return result.get("r")


def _shadow_seed(run_id: str, moment: ReplayMoment) -> int:
    raw = (
        f"{run_id}|{moment.symbol}|{moment.strategy}|{moment.timeframe}|"
        f"{moment.moment.isoformat()}"
    )
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8], 16)


def pause_by_replay(db_path: str | Path = DEFAULT_DB) -> list[dict]:
    """Pausa celdas con n>=50 en replay y diferencia vs sombra con IC90 <0."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(row) for row in con.execute(
            "SELECT style, symbol, strategy, timeframe, result_r, shadow_r "
            "FROM ai_decisions WHERE source='replay' AND decision='take' "
            "AND result_r IS NOT NULL AND shadow_r IS NOT NULL"
        ).fetchall()]
    groups: dict[tuple, list] = {}
    for row in rows:
        key = (
            row.get("style") or "replay", row["strategy"],
            row["symbol"], row["timeframe"],
        )
        groups.setdefault(key, []).append(row)
    paused: list[dict] = []
    for (style, strategy, symbol, timeframe), items in sorted(groups.items()):
        if len(items) < 50:
            continue
        diffs = [
            float(item["result_r"]) - float(item["shadow_r"])
            for item in items
        ]
        ci = _bootstrap_ci(diffs, seed=int(hashlib.sha256(
            f"{style}|{strategy}|{symbol}|{timeframe}".encode()
        ).hexdigest()[:8], 16))
        if not ci or ci[1] >= 0:
            continue
        if _cell_status(db_path, strategy, symbol, timeframe) == "paused":
            continue
        reason = (
            f"replay: n={len(items)} R-sombra media "
            f"{sum(diffs)/len(diffs):+.3f}R IC90 [{ci[0]:+.3f}, {ci[1]:+.3f}] < 0"
        )
        with connect(db_path) as con:
            con.execute(
                "INSERT INTO ai_cell_state(strategy, symbol, timeframe, "
                "status, reason, updated_at) VALUES(?,?,?,'paused',?,?) "
                "ON CONFLICT(strategy,symbol,timeframe) DO UPDATE SET "
                "status='paused', reason=excluded.reason, updated_at=excluded.updated_at",
                (strategy, symbol, timeframe, reason,
                 datetime.now(timezone.utc).isoformat()),
            )
        entry = {
            "style": style, "strategy": strategy, "symbol": symbol,
            "timeframe": timeframe, "n": len(items),
            "diff_r": round(sum(diffs) / len(diffs), 4),
            "ci90": ci, "reason": reason,
        }
        _audit(db_path, "ai_trader_replay_pause", entry, "paused", detail=reason)
        try:
            send_alert("ai_trader_replay_pause", reason, severity="warning",
                       db_path=db_path)
        except Exception:
            pass
        paused.append(entry)
    return paused


def run_replay(plan: ReplayPlan, *, yes: bool = False,
               db_path: str | Path = DEFAULT_DB,
               ask=None) -> dict:
    if not yes:
        return {**plan.summary(), "executed": False}
    asker = ask or _ask_opencode
    run_id = uuid.uuid4().hex
    snapshots = [
        {"id": index, **moment.anonymized}
        for index, moment in enumerate(plan.moments)
    ]
    decisions: dict[int, dict] = {}
    errors: list[str] = []
    for start in range(0, len(snapshots), BATCH_SIZE):
        batch = snapshots[start:start + BATCH_SIZE]
        try:
            raw = asker(_batch_prompt(batch))
            decisions.update(_parse_batch(raw, batch))
        except Exception as exc:
            errors.append(str(exc)[:200])
            for entry in batch:
                decisions[entry["id"]] = {
                    "decision": "skip",
                    "reason": f"LLM no disponible: {exc}"[:200],
                }
    taken = 0
    skipped = 0
    for index, moment in enumerate(plan.moments):
        choice = decisions.get(index, {
            "decision": "skip", "reason": "sin respuesta del modelo",
        })
        decision = choice["decision"]
        reason = choice["reason"]
        result_r = None
        shadow_r = None
        if decision == "take":
            if moment.cost_ratio is None:
                decision = "skip"
                reason = "coste/R Sin datos"
            else:
                gross = _simulate(moment, moment.side, moment.price,
                                  moment.sl, moment.tp)
                if gross is None:
                    decision = "skip"
                    reason = "Sin datos de simulación"
                else:
                    result_r = round(float(gross) - float(moment.cost_ratio), 4)
                    twin = _twin_levels(
                        moment.price, moment.sl, moment.tp,
                        seed=_shadow_seed(run_id, moment),
                    )
                    shadow_gross = _simulate(
                        moment, twin["side"], twin["entry"],
                        twin["sl"], twin["tp"],
                    )
                    if shadow_gross is not None:
                        shadow_r = round(
                            float(shadow_gross) - float(moment.cost_ratio), 4
                        )
        _insert_decision(
            db_path, moment, run_id=run_id, decision=decision,
            reason=reason, result_r=result_r, shadow_r=shadow_r,
            config=plan.config,
        )
        if decision == "take":
            taken += 1
        else:
            skipped += 1
    paused = pause_by_replay(db_path)
    return {
        "run_id": run_id,
        "executed": True,
        "style": plan.style,
        "decisions": len(plan.moments),
        "take": taken,
        "skip": skipped,
        "calls": plan.calls,
        "tokens_est": plan.tokens_est,
        "cutoff_utc": str(plan.cutoff) if plan.cutoff is not None else None,
        "errors": errors,
        "paused": paused,
    }
