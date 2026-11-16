from __future__ import annotations

import json
import os
import subprocess

from ..config import ROOT
from ..time_utils import market_today

TA_PYTHON = ROOT / ".venv-ta" / "Scripts" / "python.exe"
TA_SCRIPT = ROOT / "scripts" / "run_tradingagents.py"

# Salida máxima del lado deep. En local 2048 basta; con un proveedor de nube
# (DeepSeek admite hasta 384K) un informe de analista completo no cabe en 2k.
DEFAULT_MAX_TOKENS = int(os.getenv("LAB_DEEP_MAX_TOKENS", "8192"))

RATING_TO_TARGET: dict[str, float | None] = {
    "Buy": 1.0,
    "Overweight": 0.5,
    "Hold": None,        # mantener la posición actual
    "Underweight": 0.0,
    "Sell": 0.0,
    "REVIEW": None,      # decisión ilegible: no operar
}


class AgentError(RuntimeError):
    pass


def run_tradingagents(
    ticker: str,
    analysis_date: str | None = None,
    analysts: str = "market,news",
    *,
    debate_rounds: int = 1,
    risk_rounds: int = 1,
    language: str = "Spanish",
    save: bool = True,
    timeout: int = 1800,
    max_tool_rounds: int = 8,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """Lanza un run de TradingAgents en su propio venv y devuelve la decisión.

    `timeout` es el presupuesto de tiempo del run (por defecto 30 min): el
    script se corta solo con un error claro y el padre mata el proceso si
    aun así se pasa. El modelo local de 27B no cabe en ese presupuesto, así
    que el lado deep puede apuntarse a un proveedor de nube con
    `LAB_DEEP_LLM_PROVIDER` / `LAB_DEEP_LLM_MODEL` / `LAB_DEEP_LLM_BASE_URL`
    y dejar el lite en LM Studio.
    """
    if not TA_PYTHON.exists():
        raise AgentError(f"No existe el intérprete de TradingAgents: {TA_PYTHON}")
    if not TA_SCRIPT.exists():
        raise AgentError(f"No existe el script: {TA_SCRIPT}")

    day = analysis_date or market_today().isoformat()
    out_dir = ROOT / "data" / "agent_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ta_{ticker.upper()}_{day}.json"

    cmd = [
        str(TA_PYTHON),
        str(TA_SCRIPT),
        "--ticker",
        ticker.upper(),
        "--date",
        day,
        "--analysts",
        analysts,
        "--debate-rounds",
        str(debate_rounds),
        "--risk-rounds",
        str(risk_rounds),
        "--language",
        language,
        "--max-tool-rounds",
        str(max_tool_rounds),
        "--max-tokens",
        str(max_tokens),
        "--out",
        str(out_path),
        "--timeout-s",
        str(max(60, int(timeout) - 60)),
    ]
    if save:
        cmd.append("--save")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentError(f"TradingAgents superó {timeout}s para {ticker}") from exc

    if not out_path.exists():
        raise AgentError(
            f"TradingAgents no generó resultado (exit={proc.returncode}).\n"
            f"STDOUT:\n{proc.stdout[-2000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
        )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    if not payload.get("ok"):
        raise AgentError(payload.get("error", "fallo desconocido") + "\n" + payload.get("traceback", "")[-1500:])

    payload["_stderr_tail"] = proc.stderr[-800:]
    return payload
