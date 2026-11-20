from __future__ import annotations

import httpx
import pytest

from tradinglab.db import connect
from tradinglab.intel.sec import SecClient, extract_key_facts, parse_recent_filings, validate_user_agent

TICKERS = {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}}
SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": ["0001045810-26-000001", "0001045810-25-000009"],
            "filingDate": ["2026-01-15", "2025-10-01"],
            "reportDate": ["2025-12-31", "2025-09-30"],
            "acceptanceDateTime": ["2026-01-15T20:00:00.000Z", "2025-10-01T20:00:00.000Z"],
            "form": ["10-K", "8-K"],
            "primaryDocument": ["nvda-10k.htm", "nvda-8k.htm"],
            "primaryDocDescription": ["10-K", "8-K"],
        }
    }
}
FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "val": 1000,
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2026-01-15",
                        }
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "val": 500,
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2026-01-15",
                        }
                    ]
                }
            },
        }
    }
}


class Fixture:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_submissions = False
        self.seen_headers: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        self.seen_headers.append(request.headers.get("User-Agent", ""))
        path = request.url.path
        if path.endswith("company_tickers.json"):
            return httpx.Response(200, json=TICKERS)
        if "submissions" in path:
            if self.fail_submissions:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json=SUBMISSIONS)
        if "companyfacts" in path:
            return httpx.Response(200, json=FACTS)
        return httpx.Response(404)


def _client(tmp_path, fixture, *, user_agent="TradingLab/0.1 test@example.com", ttl=3600, interval=0):
    return SecClient(
        user_agent=user_agent,
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "lab.db",
        min_interval_s=interval,
        cache_ttl_s=ttl,
        client=httpx.Client(transport=httpx.MockTransport(fixture)),
    )


def test_valida_user_agent():
    assert validate_user_agent("TradingLab/0.1 test@example.com")
    assert not validate_user_agent("Mozilla/5.0")
    assert not validate_user_agent("TradingLab/0.1")


def test_sin_user_agent_no_hace_peticiones(tmp_path):
    fixture = Fixture()
    client = _client(tmp_path, fixture, user_agent="")
    result = client.submissions("NVDA")
    assert result.status == "unconfigured"
    assert fixture.calls == []


def test_cik_filings_y_facts(tmp_path):
    fixture = Fixture()
    client = _client(tmp_path, fixture)

    cik = client.cik_for_ticker("NVDA")
    assert cik.status == "ok"
    assert cik.data["cik"] == "0001045810"

    filings = client.submissions("NVDA", forms=["10-K", "8-K"], limit=5)
    assert filings.status == "ok"
    assert [f["form"] for f in filings.data["filings"]] == ["10-K", "8-K"]
    assert all("test@example.com" in header for header in fixture.seen_headers)

    facts = client.company_facts("NVDA")
    assert facts.status == "ok"
    assert {f["tag"] for f in facts.data["key_facts"]} == {"Revenues", "NetIncomeLoss"}
    assert facts.data["key_facts"][0]["value"] == 1000


def test_cache_evita_segunda_peticion(tmp_path):
    fixture = Fixture()
    client = _client(tmp_path, fixture)
    assert client.submissions("NVDA").status == "ok"
    first_calls = len(fixture.calls)
    assert client.submissions("NVDA").status == "ok"
    assert len(fixture.calls) == first_calls


def test_http_error_no_inventa_datos(tmp_path):
    fixture = Fixture()
    fixture.fail_submissions = True
    client = _client(tmp_path, fixture, ttl=0)
    result = client.submissions("NVDA")
    assert result.status == "error"
    assert result.data is None
    with connect(tmp_path / "lab.db") as con:
        row = con.execute("SELECT status FROM sec_fetches ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "error"


def test_cache_stale_si_falla_sec(tmp_path):
    fixture = Fixture()
    client = _client(tmp_path, fixture, ttl=0)
    assert client.submissions("NVDA").status == "ok"
    fixture.fail_submissions = True
    result = client.submissions("NVDA")
    assert result.status == "ok"
    assert result.stale is True
    assert result.data["filings"]


def test_parse_filings_y_facts_puros():
    rows = parse_recent_filings(SUBMISSIONS, forms=["10-K"], limit=10)
    assert len(rows) == 1
    assert rows[0]["form"] == "10-K"

    facts = extract_key_facts(FACTS["facts"])
    assert len(facts) == 2
    assert all(f["form"] == "10-K" for f in facts)


def test_rate_limit_usa_sleeper(tmp_path):
    waits: list[float] = []
    times = iter([0.0, 0.0, 0.2, 0.2])
    client = SecClient(
        user_agent="TradingLab/0.1 test@example.com",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "lab.db",
        min_interval_s=1.0,
        sleeper=waits.append,
        clock=lambda: next(times),
    )
    client._throttle()
    client._throttle()
    assert waits == pytest.approx([1.0, 0.8])
