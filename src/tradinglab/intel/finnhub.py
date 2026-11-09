"""Noticias generales de Finnhub como proveedor alternativo al RSS.

Solo lectura. La clave se lee del almacén de secretos y nunca se imprime ni se
guarda en logs. El texto se sanea igual que el RSS y entra con trusted=false.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

import httpx

from .news import NewsItem, sanitize_untrusted

FINNHUB_BASE = "https://finnhub.io/api/v1"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class FinnhubError(RuntimeError):
    pass


def parse_news(payload: list, *, limit: int = 30) -> list[NewsItem]:
    if not isinstance(payload, list):
        raise FinnhubError("respuesta de Finnhub sin lista")
    items: list[NewsItem] = []
    for row in payload[: max(1, int(limit))]:
        if not isinstance(row, dict):
            continue
        title = sanitize_untrusted(str(row.get("headline") or ""), 300)
        url = sanitize_untrusted(str(row.get("url") or ""), 500)
        summary = sanitize_untrusted(str(row.get("summary") or ""), 1_500)
        if not title or not url.startswith(("http://", "https://")):
            continue
        stamp = row.get("datetime")
        try:
            published = datetime.fromtimestamp(
                float(stamp), tz=timezone.utc
            ).isoformat(timespec="seconds")
        except (TypeError, ValueError, OSError):
            published = datetime.now(timezone.utc).isoformat(timespec="seconds")
        news_id = str(row.get("id") or "")
        digest = hashlib.sha256(
            f"finnhub|{news_id}|{url}|{title}|{published}".encode("utf-8")
        ).hexdigest()
        items.append(
            NewsItem(
                source="finnhub",
                url=url,
                title=title,
                summary=summary,
                published_at=published,
                hash=digest,
            )
        )
    return items


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRY_STATUSES
    return isinstance(exc, (httpx.TransportError, TimeoutError))


def fetch_news(
    api_key: str | None,
    *,
    category: str = "general",
    limit: int = 30,
    client: httpx.Client | None = None,
    retries: int = 2,
    backoff_s: float = 0.5,
) -> list[NewsItem]:
    if not api_key:
        raise FinnhubError("falta FINNHUB_API_KEY")
    own = client is None
    http = client or httpx.Client(timeout=15)
    attempts = max(1, int(retries) + 1)
    try:
        for attempt in range(attempts):
            try:
                response = http.get(
                    f"{FINNHUB_BASE}/news",
                    params={"category": category, "minId": 0, "token": api_key},
                )
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise FinnhubError("respuesta no JSON") from exc
                return parse_news(payload, limit=limit)
            except Exception as exc:
                if attempt >= attempts - 1 or not _retryable(exc):
                    if isinstance(exc, FinnhubError):
                        raise
                    if isinstance(exc, httpx.HTTPStatusError):
                        raise FinnhubError(
                            f"Finnhub HTTP {exc.response.status_code}"
                        ) from exc
                    raise FinnhubError(
                        f"Finnhub no disponible: {type(exc).__name__}"
                    ) from exc
                if backoff_s > 0:
                    time.sleep(float(backoff_s) * (2**attempt))
        raise FinnhubError("Finnhub sin intentos")  # pragma: no cover
    finally:
        if own:
            http.close()


__all__ = [
    "FINNHUB_BASE",
    "FinnhubError",
    "fetch_news",
    "parse_news",
]
