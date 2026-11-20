"""Cliente SEC EDGAR con caché, rate limit y estados explícitos.

Reglas:
  * User-Agent obligatorio con contacto; sin él no se hace ninguna petición.
  * 4 req/s por defecto (por debajo del máximo de SEC).
  * Caché local de JSON; si SEC falla y hay caché, se devuelve `stale`, no
    datos inventados.
  * `empty` significa respuesta válida sin filings/facts; `error`/`unconfigured`
    significan que NO se puede afirmar nada.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

import httpx

from ..config import DEFAULT_DB, ROOT
from ..db import connect, init_db, utcnow

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

FORMS = ("10-K", "10-Q", "8-K")
KEY_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "EarningsPerShareDiluted",
)

SecStatus = Literal["ok", "empty", "unconfigured", "error", "stale", "not_found"]


class SecError(RuntimeError):
    pass


class SecConfigError(SecError):
    pass


def validate_user_agent(value: str | None) -> bool:
    text = (value or "").strip()
    return text.startswith("TradingLab/") and "@" in text


@dataclass
class SecResult:
    status: SecStatus
    data: Any = None
    error: str = ""
    fetched_at: str | None = None
    cache_hit: bool = False
    stale: bool = False
    http_status: int | None = None

    @property
    def usable(self) -> bool:
        return self.status in {"ok", "empty"}


def _cik10(value: str | int) -> str:
    return str(int(value)).zfill(10)


def parse_recent_filings(
    payload: dict,
    *,
    forms: Iterable[str] = FORMS,
    limit: int = 20,
) -> list[dict]:
    recent = ((payload.get("filings") or {}).get("recent") or {})
    keys = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
        "primaryDocDescription",
    )
    rows = []
    count = len(recent.get("form") or [])
    wanted = set(forms)
    for index in range(count):
        form = str(recent.get("form", [""] * count)[index] or "")
        if form not in wanted:
            continue
        row = {}
        for key in keys:
            values = recent.get(key) or []
            row[key] = values[index] if index < len(values) else None
        rows.append(row)
    rows.sort(key=lambda row: str(row.get("filingDate") or ""), reverse=True)
    return rows[:limit]


def extract_key_facts(facts: dict) -> list[dict]:
    out: list[dict] = []
    for namespace in ("us-gaap", "ifrs-full"):
        block = facts.get(namespace) or {}
        for tag in KEY_TAGS:
            node = block.get(tag)
            if not node:
                continue
            units = node.get("units") or {}
            for unit, values in units.items():
                candidates = [
                    value
                    for value in values
                    if value.get("val") is not None
                    and str(value.get("form") or "") in {"10-K", "10-Q"}
                ]
                if not candidates:
                    continue
                latest = max(
                    candidates,
                    key=lambda value: (
                        str(value.get("filed") or ""),
                        str(value.get("end") or ""),
                    ),
                )
                out.append(
                    {
                        "tag": tag,
                        "namespace": namespace,
                        "unit": unit,
                        "value": latest.get("val"),
                        "end": latest.get("end"),
                        "fy": latest.get("fy"),
                        "fp": latest.get("fp"),
                        "form": latest.get("form"),
                        "filed": latest.get("filed"),
                    }
                )
                break
    return out


class SecClient:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        cache_dir: str | Path | None = None,
        db_path: str | Path = DEFAULT_DB,
        min_interval_s: float = 0.25,
        cache_ttl_s: float = 6 * 3600,
        timeout_s: float = 20.0,
        client: httpx.Client | None = None,
        sleeper=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.user_agent = (user_agent if user_agent is not None else os.getenv("SEC_USER_AGENT", "")).strip()
        self.cache_dir = Path(cache_dir) if cache_dir else ROOT / "data" / "cache" / "sec"
        self.db_path = Path(db_path)
        self.min_interval_s = max(0.0, float(min_interval_s))
        self.cache_ttl_s = max(0.0, float(cache_ttl_s))
        self.timeout_s = float(timeout_s)
        self._owns_client = client is None
        self._http = client or httpx.Client(timeout=self.timeout_s)
        self._sleeper = sleeper
        self._clock = clock
        self._last_request = 0.0
        self._lock = threading.Lock()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------- estado

    @property
    def configured(self) -> bool:
        return validate_user_agent(self.user_agent)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def status(self) -> dict:
        init_db(self.db_path)
        with connect(self.db_path) as con:
            last = con.execute(
                "SELECT ts, endpoint, cik, status, http_status, cache_hit, error "
                "FROM sec_fetches ORDER BY id DESC LIMIT 5"
            ).fetchall()
        return {
            "configured": self.configured,
            "user_agent_ok": validate_user_agent(self.user_agent),
            "cache_dir": str(self.cache_dir),
            "min_interval_s": self.min_interval_s,
            "last": [dict(row) for row in last],
        }

    # -------------------------------------------------------------- interno

    def _throttle(self) -> None:
        with self._lock:
            now = self._clock()
            wait = self.min_interval_s - (now - self._last_request)
            if wait > 0:
                self._sleeper(wait)
            self._last_request = self._clock()

    def _cache_path(self, name: str) -> Path:
        return self.cache_dir / name

    def _read_cache(self, path: Path) -> tuple[Any, str, float] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mtime = path.stat().st_mtime
            fetched = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(timespec="seconds")
            return data, fetched, time.time() - mtime
        except (OSError, ValueError):
            return None

    def _log(
        self,
        *,
        endpoint: str,
        cik: str | None,
        status: str,
        http_status: int | None,
        cache_hit: bool,
        error: str = "",
    ) -> None:
        try:
            init_db(self.db_path)
            with connect(self.db_path) as con:
                con.execute(
                    "INSERT INTO sec_fetches"
                    "(ts, endpoint, cik, status, http_status, cache_hit, error) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (utcnow(), endpoint, cik, status, http_status, 1 if cache_hit else 0, error[:500]),
                )
        except Exception:
            pass

    def _get_json(self, url: str, *, cache_name: str, cik: str | None = None, ttl_s: float | None = None) -> SecResult:
        if not self.configured:
            return SecResult(
                "unconfigured",
                error="falta SEC_USER_AGENT con formato TradingLab/... y email de contacto",
            )
        path = self._cache_path(cache_name)
        cached = self._read_cache(path)
        ttl = self.cache_ttl_s if ttl_s is None else ttl_s
        if cached and cached[2] <= ttl:
            return SecResult("ok", cached[0], fetched_at=cached[1], cache_hit=True)

        self._throttle()
        http_status = None
        try:
            response = self._http.get(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            http_status = response.status_code
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
            if cached:
                self._log(
                    endpoint=cache_name,
                    cik=cik,
                    status="stale",
                    http_status=http_status,
                    cache_hit=True,
                    error=error,
                )
                return SecResult(
                    "stale",
                    cached[0],
                    error=error,
                    fetched_at=cached[1],
                    cache_hit=True,
                    stale=True,
                    http_status=http_status,
                )
            self._log(
                endpoint=cache_name,
                cik=cik,
                status="error",
                http_status=http_status,
                cache_hit=False,
                error=error,
            )
            return SecResult("error", error=error, http_status=http_status)

        fetched = utcnow()
        try:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        self._log(
            endpoint=cache_name,
            cik=cik,
            status="ok",
            http_status=http_status,
            cache_hit=False,
        )
        return SecResult(
            ("empty" if not data else "ok"),
            data,
            fetched_at=fetched,
            http_status=http_status,
        )

    # -------------------------------------------------------------- público

    def cik_for_ticker(self, ticker: str) -> SecResult:
        ticker = ticker.strip().upper()
        result = self._get_json(
            SEC_TICKERS_URL,
            cache_name="company_tickers.json",
            ttl_s=24 * 3600,
        )
        if not result.usable and result.status != "stale":
            return result
        payload = result.data or {}
        for item in payload.values():
            if not isinstance(item, dict):
                continue
            if str(item.get("ticker") or "").upper() == ticker:
                return SecResult(
                    "ok",
                    {"ticker": ticker, "cik": _cik10(item["cik_str"]), "title": item.get("title")},
                    fetched_at=result.fetched_at,
                    cache_hit=result.cache_hit,
                    stale=result.stale,
                )
        return SecResult("not_found", error=f"ticker no encontrado en SEC: {ticker}", fetched_at=result.fetched_at)

    def submissions(self, ticker: str, *, forms: Iterable[str] = FORMS, limit: int = 20) -> SecResult:
        cik_result = self.cik_for_ticker(ticker)
        if not cik_result.usable:
            return cik_result
        cik = cik_result.data["cik"]
        result = self._get_json(
            SEC_SUBMISSIONS_URL.format(cik=cik),
            cache_name=f"submissions_{cik}.json",
            cik=cik,
        )
        if result.status not in {"ok", "empty", "stale"}:
            return result
        filings = parse_recent_filings(result.data or {}, forms=forms, limit=limit)
        return SecResult(
            "ok" if filings else "empty",
            {"ticker": ticker.upper(), "cik": cik, "filings": filings},
            fetched_at=result.fetched_at,
            cache_hit=result.cache_hit,
            stale=result.stale,
        )

    def company_facts(self, ticker: str) -> SecResult:
        cik_result = self.cik_for_ticker(ticker)
        if not cik_result.usable:
            return cik_result
        cik = cik_result.data["cik"]
        result = self._get_json(
            SEC_FACTS_URL.format(cik=cik),
            cache_name=f"companyfacts_{cik}.json",
            cik=cik,
        )
        if result.status not in {"ok", "empty", "stale"}:
            return result
        facts = (result.data or {}).get("facts") or {}
        key_facts = extract_key_facts(facts)
        return SecResult(
            "ok" if key_facts else "empty",
            {
                "ticker": ticker.upper(),
                "cik": cik,
                "key_facts": key_facts,
                "fact_namespaces": sorted(facts),
            },
            fetched_at=result.fetched_at,
            cache_hit=result.cache_hit,
            stale=result.stale,
        )


__all__ = [
    "FORMS",
    "KEY_TAGS",
    "SecClient",
    "SecConfigError",
    "SecError",
    "SecResult",
    "extract_key_facts",
    "parse_recent_filings",
    "validate_user_agent",
]
