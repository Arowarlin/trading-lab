#!/usr/bin/env python
"""Ejecuta TradingAgents contra un endpoint OpenAI-compatible (LM Studio) y escribe
la decisión en un JSON estable. Se ejecuta con el intérprete de .venv-ta.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MIN_CONTEXT = 16_384
DEFAULT_TIMEOUT_S = 1800


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


def _install_opencode_headers(base_url: str, session_id: str) -> bool:
    """El gateway de OpenCode Go exige `x-opencode-session`; sin ella da 400.

    Se inyecta como cabecera por defecto del cliente de LangChain, sin tocar
    el código de TradingAgents. Devuelve True si se instaló.
    """
    if "opencode.ai" not in base_url:
        return False
    from langchain_openai import ChatOpenAI

    if getattr(ChatOpenAI, "_tradinglab_session_header", False):
        return True
    original = ChatOpenAI.__init__

    def patched(self, *args, **kwargs):
        headers = dict(kwargs.get("default_headers") or {})
        headers.setdefault("x-opencode-session", session_id)
        headers.setdefault("User-Agent", "trading-lab/1.0")
        kwargs["default_headers"] = headers
        original(self, *args, **kwargs)

    ChatOpenAI.__init__ = patched
    ChatOpenAI._tradinglab_session_header = True
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--analysts", default="market,news")
    parser.add_argument("--debate-rounds", type=int, default=1)
    parser.add_argument("--risk-rounds", type=int, default=1)
    parser.add_argument("--language", default="Spanish")
    parser.add_argument("--max-tool-rounds", type=int, default=8)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.getenv("LAB_DEEP_MAX_TOKENS", "8192")),
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--save", action="store_true")
    parser.add_argument(
        "--timeout-s",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help="Presupuesto de tiempo del run; al agotarlo se aborta con un mensaje",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()

    def _abort() -> None:
        """Watchdog: si el run se pasa de presupuesto, se corta con un error claro."""
        message = (
            f"TradingAgents excedió el presupuesto de {args.timeout_s}s "
            f"para {args.ticker.upper()}"
        )
        payload = {
            "ok": False,
            "ticker": args.ticker.upper(),
            "date": args.date,
            "error": message,
            "elapsed_s": round(time.time() - started, 1),
        }
        try:
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), flush=True)
        os._exit(3)

    if args.timeout_s > 0:
        watchdog = threading.Timer(args.timeout_s, _abort)
        watchdog.daemon = True
        watchdog.start()

    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")

        # El cliente `openai_compatible` de TradingAgents lee su clave de
        # OPENAI_COMPATIBLE_API_KEY. El deep usa una credencial distinta de la
        # del servidor local, así que se inyecta aquí sin tocar el .env global.
        deep_key = os.getenv("LAB_DEEP_LLM_API_KEY")
        if deep_key:
            os.environ["OPENAI_COMPATIBLE_API_KEY"] = deep_key

        from tradingagents.agents.rating import extract_rating
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # El lado deep puede usar otro proveedor que el lab (p. ej. DeepSeek en
        # la nube) sin tocar el cliente local: LAB_DEEP_* tiene prioridad y, si
        # no existe, se cae al LLM del laboratorio (LM Studio).
        model = (
            os.getenv("LAB_DEEP_LLM_MODEL")
            or os.getenv("LAB_LLM_MODEL", "qwen3.8-27b")
        )
        backend = (
            os.getenv("LAB_DEEP_LLM_BASE_URL")
            or os.getenv("LAB_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
        )
        provider = os.getenv("LAB_DEEP_LLM_PROVIDER", "").strip() or "openai_compatible"

        # OpenCode Go rechaza con 400 las peticiones sin `x-opencode-session`.
        _install_opencode_headers(
            backend, f"lab-deep-{args.ticker.lower()}-{args.date}"
        )

        # El chequeo de contexto solo aplica a LM Studio (endpoint /api/v0/models).
        # En un proveedor de nube no hay que comprobar nada.
        is_local = "127.0.0.1" in backend or "localhost" in backend
        if is_local:
            loaded_ctx = _loaded_context(backend, model)
            if loaded_ctx is not None and loaded_ctx < MIN_CONTEXT:
                raise RuntimeError(
                    f"El modelo '{model}' está cargado con {loaded_ctx:,} tokens de contexto; "
                    f"TradingAgents necesita al menos {MIN_CONTEXT:,}. "
                    f"Recarga con: lms unload --all && lms load {model} "
                    "--context-length 32768 --parallel 1 --yes"
                )
        elif provider == "openai_compatible" and not deep_key:
            # Sin esto la clave local (lm-studio) viajaría al gateway y el
            # fallo saldría como un 401 sin explicación.
            raise RuntimeError(
                "Falta la credencial del lado deep: define LAB_DEEP_LLM_API_KEY en "
                f"{ROOT / '.env'}. Sin ella el gateway responde 401. Se crea en "
                "OpenCode Console > Settings > Service accounts > Add API Key "
                "(Permissions: Restricted, Models: Request); empieza por oc_sk_."
            )

        cfg = DEFAULT_CONFIG.copy()
        cfg.update(
            {
                "llm_provider": provider,
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
