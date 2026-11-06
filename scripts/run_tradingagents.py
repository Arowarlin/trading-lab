#!/usr/bin/env python
"""Ejecuta TradingAgents contra un endpoint OpenAI-compatible (LM Studio) y escribe
la decisión en un JSON estable. Se ejecuta con el intérprete de .venv-ta.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MIN_CONTEXT = 16_384


def _loaded_context(base_url: str, model: str) -> int | None:
    """Contexto real cargado en LM Studio, o None si no se puede saber.

    Sin esto, un modelo cargado con 8k falla a los 8 minutos con un 400 opaco
    (`exceed_context_size_error`) en mitad del analista.
    """
    from urllib.request import urlopen

    origin = base_url.rstrip("/")
    if origin.endswith("/v1"):
        origin = origin[:-3]
    try:
        with urlopen(f"{origin}/api/v0/models", timeout=5) as resp:
            data = json.load(resp)
    except Exception:
        return None

    for m in data.get("data", []):
        if m.get("state") != "loaded":
            continue
        mid = str(m.get("id", ""))
        if mid == model or model in mid or mid.endswith(model):
            ctx = m.get("loaded_context_length") or m.get("max_context_length")
            return int(ctx) if ctx else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--analysts", default="market,news")
    parser.add_argument("--debate-rounds", type=int, default=1)
    parser.add_argument("--risk-rounds", type=int, default=1)
    parser.add_argument("--language", default="Spanish")
    parser.add_argument("--max-tool-rounds", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--out", required=True)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()

    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")

        from tradingagents.agents.rating import extract_rating
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        model = os.getenv("LAB_LLM_MODEL", "qwen3.8-27b")
        backend = os.getenv("LAB_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
        loaded_ctx = _loaded_context(backend, model)
        if loaded_ctx is not None and loaded_ctx < MIN_CONTEXT:
            raise RuntimeError(
                f"El modelo '{model}' está cargado con {loaded_ctx:,} tokens de contexto; "
                f"TradingAgents necesita al menos {MIN_CONTEXT:,}. "
                f"Recarga con: lms unload --all && lms load {model} "
                "--context-length 32768 --parallel 1 --yes"
            )

        cfg = DEFAULT_CONFIG.copy()
        cfg.update(
            {
                "llm_provider": "openai_compatible",
                "backend_url": backend,
                "deep_think_llm": model,
                "quick_think_llm": model,
                "temperature": 0.2,
                "max_debate_rounds": args.debate_rounds,
                "max_risk_discuss_rounds": args.risk_rounds,
                "max_tool_rounds": args.max_tool_rounds,
                "max_tokens": args.max_tokens,
                "output_language": args.language,
                "checkpoint_enabled": True,
                "results_dir": str(ROOT / "data" / "tradingagents" / "reports"),
                "data_cache_dir": str(ROOT / "data" / "tradingagents" / "cache"),
                "memory_log_path": str(ROOT / "data" / "tradingagents" / "memory.md"),
            }
        )

        analysts = tuple(a.strip() for a in args.analysts.split(",") if a.strip())
        graph = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=cfg)
        final_state, signal = graph.propagate(args.ticker.upper(), args.date)

        decision = (final_state or {}).get("final_trade_decision", "")
        rating = signal or extract_rating(decision or "") or "REVIEW"

        payload = {
            "ok": True,
            "ticker": args.ticker.upper(),
            "date": args.date,
            "rating": rating,
            "decision": decision,
            "analysts": list(analysts),
            "model": model,
            "elapsed_s": round(time.time() - started, 1),
            "state_keys": sorted((final_state or {}).keys()),
        }

        if args.save:
            try:
                save_path = graph.save_reports(final_state, args.ticker.upper(), args.date)
                payload["reports_path"] = str(save_path)
            except Exception as exc:  # el informe no debe tumbar la decisión
                payload["reports_error"] = str(exc)

    except Exception as exc:
        payload = {
            "ok": False,
            "ticker": args.ticker.upper(),
            "date": args.date,
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "elapsed_s": round(time.time() - started, 1),
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "ticker": payload["ticker"], "rating": payload["rating"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
