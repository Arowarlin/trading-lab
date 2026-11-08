"""Puente Telegram para el laboratorio.

Solo responde al chat/usuario autorizado. El token vive en Windows Credential
Manager (keyring), nunca en `.env` ni en logs. No envía órdenes, no activa bots
y no permite live: el modo agente ejecuta OpenCode con un agente restringido.

Dos modos:
- `commands`: solo comandos seguros (`/status`, `/f13`, `/decisions`, ...).
- `agent`: las instrucciones libres se pasan a `opencode run --agent telegram`.

El puente hace long polling contra Telegram; no abre puertos ni necesita IP
pública. El PC debe estar encendido y con la sesión de Windows iniciada.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
import yaml

from .config import DEFAULT_DB, KEYRING_SERVICE, ROOT, get_settings, load_secrets

CONFIG_PATH = ROOT / "config" / "telegram.yaml"
EXAMPLE_PATH = ROOT / "config" / "telegram.example.yaml"
STATE_PATH = ROOT / "data" / "telegram_state.json"
LOG_DIR = ROOT / "logs" / "telegram"
TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
CHAT_KEY = "TELEGRAM_CHAT_ID"
MAX_CHARS = 3800
MODES = ("commands", "agent")


class TelegramError(RuntimeError):
    """Error del puente; nunca incluye el token en el mensaje."""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class TelegramConfig:
    enabled: bool = False
    mode: str = "commands"
    agent: str = "telegram"
    working_dir: str = str(ROOT)
    session_id: str = ""
    allowed_chat_id: str = ""
    allowed_user_id: str = ""
    poll_timeout_s: int = 30
    agent_timeout_s: int = 1800
    max_chars: int = MAX_CHARS

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "TelegramConfig":
        if not path.exists():
            return cls()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return cls()
        if not isinstance(data, dict):
            return cls()
        mode = str(data.get("mode") or "commands").lower()
        if mode not in MODES:
            mode = "commands"
        return cls(
            enabled=bool(data.get("enabled", False)),
            mode=mode,
            agent=str(data.get("agent") or "telegram"),
            working_dir=str(data.get("working_dir") or ROOT),
            session_id=str(data.get("session_id") or ""),
            allowed_chat_id=str(data.get("allowed_chat_id") or "").strip(),
            allowed_user_id=str(data.get("allowed_user_id") or "").strip(),
            poll_timeout_s=_safe_int(data.get("poll_timeout_s"), 30),
            agent_timeout_s=_safe_int(data.get("agent_timeout_s"), 1800),
            max_chars=_safe_int(data.get("max_chars"), MAX_CHARS),
        )

    def save(self, path: Path = CONFIG_PATH) -> None:
        payload = {
            "enabled": bool(self.enabled),
            "mode": self.mode if self.mode in MODES else "commands",
            "agent": self.agent,
            "working_dir": self.working_dir,
            "session_id": self.session_id,
            "allowed_chat_id": self.allowed_chat_id,
            "allowed_user_id": self.allowed_user_id,
            "poll_timeout_s": int(self.poll_timeout_s),
            "agent_timeout_s": int(self.agent_timeout_s),
            "max_chars": int(self.max_chars),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        tmp.replace(path)


@dataclass
class BridgeState:
    last_update_id: int = 0
    pending_action: str = ""
    pending_code: str = ""
    pending_expires_at: float = 0.0

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "BridgeState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                last_update_id=int(data.get("last_update_id") or 0),
                pending_action=str(data.get("pending_action") or ""),
                pending_code=str(data.get("pending_code") or ""),
                pending_expires_at=float(data.get("pending_expires_at") or 0.0),
            )
        except Exception:
            return cls()

    def save(self, path: Path = STATE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "last_update_id": int(self.last_update_id),
                    "pending_action": self.pending_action,
                    "pending_code": self.pending_code,
                    "pending_expires_at": self.pending_expires_at,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)

    def clear_pending(self) -> None:
        self.pending_action = ""
        self.pending_code = ""
        self.pending_expires_at = 0.0


@dataclass(frozen=True)
class Inbound:
    update_id: int
    chat_id: str
    user_id: str
    chat_type: str
    text: str
    command: str = ""
    args: str = ""
    forwarded: bool = False


@dataclass
class AgentResult:
    text: str
    session_id: str = ""
    returncode: int = 0
    duration_s: float = 0.0


def _keyring_get(key: str) -> str | None:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, key)
    except Exception:
        return None


def _keyring_set(key: str, value: str) -> None:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, key, value)
    except Exception as exc:
        raise TelegramError("No se pudo guardar el secreto en el keyring.") from exc


def get_token() -> str:
    load_secrets()
    token = os.getenv(TOKEN_KEY) or _keyring_get(TOKEN_KEY) or ""
    if not token:
        raise TelegramError("Falta TELEGRAM_BOT_TOKEN (keyring o variable de entorno).")
    return token


def get_chat_id() -> str:
    load_secrets()
    return os.getenv(CHAT_KEY) or _keyring_get(CHAT_KEY) or ""


def save_secrets(token: str, chat_id: str) -> None:
    """Guarda token y chat ID en keyring. Nunca escribe `.env`."""
    if not token or not chat_id:
        raise TelegramError("Token y chat ID son obligatorios.")
    _keyring_set(TOKEN_KEY, token)
    _keyring_set(CHAT_KEY, str(chat_id))


class TelegramAPI:
    """Cliente mínimo de Telegram. Los errores no incluyen la URL con token."""

    def __init__(self, token: str, *, timeout: float = 30.0) -> None:
        self.token = token
        self.timeout = timeout

    def _post(self, method: str, payload: dict | None = None, timeout: float | None = None) -> Any:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        try:
            with httpx.Client(timeout=timeout or self.timeout) as client:
                response = client.post(url, json=payload or {})
            data = response.json()
        except Exception as exc:
            raise TelegramError(f"Telegram {method}: {type(exc).__name__}") from None
        if not isinstance(data, dict) or not data.get("ok"):
            description = data.get("description") if isinstance(data, dict) else ""
            raise TelegramError(f"Telegram {method}: {description or 'error'}")
        return data.get("result")

    def get_me(self) -> dict:
        return self._post("getMe")

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict]:
        payload: dict[str, Any] = {
            "timeout": int(timeout),
            "allowed_updates": ["message"],
        }
        if offset:
            payload["offset"] = int(offset)
        result = self._post("getUpdates", payload, timeout=timeout + 10)
        return list(result or [])

    def send_message(self, chat_id: str, text: str) -> Any:
        return self._post(
            "sendMessage",
            {
                "chat_id": str(chat_id),
                "text": text,
                "disable_web_page_preview": True,
            },
        )


def chunk_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Trocea sin romper palabras si es posible. Telegram admite 4096."""
    text = (text or "").strip()
    if not text:
        return []
    limit = min(4000, max(500, int(limit)))
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def send_text(
    api: TelegramAPI,
    chat_id: str,
    text: str,
    *,
    limit: int = MAX_CHARS,
    sender: Callable[[str, str], Any] | None = None,
) -> int:
    send = sender or api.send_message
    chunks = chunk_text(text, limit)
    for chunk in chunks:
        send(str(chat_id), chunk)
    return len(chunks)


def parse_inbound(update: dict) -> Inbound | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from") or {}
    if sender.get("is_bot"):
        return None
    text = str(message.get("text") or "").strip()
    if not text:
        return None
    chat = message.get("chat") or {}
    if not chat.get("id") or not sender.get("id"):
        return None
    command = ""
    args = ""
    if text.startswith("/"):
        head, _, rest = text.partition(" ")
        command = head.split("@", 1)[0].lower()
        args = rest.strip()
    forwarded = any(
        message.get(key)
        for key in ("forward_origin", "forward_from", "forward_from_chat", "forward_date")
    )
    return Inbound(
        update_id=int(update.get("update_id") or 0),
        chat_id=str(chat.get("id")),
        user_id=str(sender.get("id")),
        chat_type=str(chat.get("type") or ""),
        text=text,
        command=command,
        args=args,
        forwarded=forwarded,
    )


def is_authorized(msg: Inbound, config: TelegramConfig) -> bool:
    if not config.allowed_chat_id or msg.chat_id != config.allowed_chat_id:
        return False
    if config.allowed_user_id and msg.user_id != config.allowed_user_id:
        return False
    return True


def discover_chats(api: TelegramAPI) -> tuple[list[dict], int]:
    """Devuelve chats vistos y el mayor update_id, sin textos de mensajes."""
    updates = api.get_updates(offset=None, timeout=0)
    seen: dict[str, dict] = {}
    max_id = 0
    for update in updates:
        max_id = max(max_id, int(update.get("update_id") or 0))
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if not chat.get("id") or not sender.get("id"):
            continue
        key = str(chat["id"])
        seen[key] = {
            "chat_id": key,
            "user_id": str(sender["id"]),
            "type": str(chat.get("type") or ""),
            "username": str(sender.get("username") or chat.get("username") or ""),
        }
    return list(seen.values()), max_id


def wait_for_chat(
    api: TelegramAPI,
    timeout_s: int = 60,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[dict], int]:
    """Espera a que el usuario escriba al bot y devuelve los chats vistos."""
    deadline = time.monotonic() + max(0, int(timeout_s))
    while True:
        candidates, max_id = discover_chats(api)
        if candidates or time.monotonic() >= deadline:
            return candidates, max_id
        sleep(3)


def save_setup(
    token: str,
    chat_id: str,
    user_id: str = "",
    *,
    mode: str = "commands",
    last_update_id: int = 0,
    path: Path = CONFIG_PATH,
    state_path: Path = STATE_PATH,
) -> TelegramConfig:
    save_secrets(token, chat_id)
    config = TelegramConfig.load(path)
    config.allowed_chat_id = str(chat_id)
    config.allowed_user_id = str(user_id or chat_id)
    config.mode = mode if mode in MODES else "commands"
    config.enabled = False
    config.session_id = ""
    config.working_dir = str(ROOT)
    config.save(path)
    if last_update_id:
        BridgeState(last_update_id=int(last_update_id)).save(state_path)
    return config


def opencode_executable() -> str:
    appdata = os.environ.get("APPDATA")
    candidates = []
    if appdata:
        candidates.append(Path(appdata) / "npm" / "node_modules" / "@opencode" / "cli" / "bin" / "opencode.exe")
    candidates.append(Path.home() / ".opencode" / "bin" / "opencode.exe")
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("opencode")
    if found and Path(found).suffix.lower() == ".exe":
        return found
    raise TelegramError("No encuentro opencode.exe. Revisa la instalación de OpenCode.")


def parse_opencode_output(stdout: str) -> tuple[str, str]:
    """Extrae el texto final y el sessionID de la salida JSON de `opencode run`."""
    texts: list[tuple[str, str]] = []
    session_id = ""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("sessionID"):
            session_id = str(event["sessionID"])
        if event.get("type") != "text":
            continue
        part = event.get("part") or {}
        text = str(part.get("text") or event.get("text") or "").strip()
        if text:
            texts.append((str(part.get("messageID") or ""), text))
    if not texts:
        return "", session_id
    last_message = texts[-1][0]
    final = "\n".join(text for message_id, text in texts if message_id == last_message)
    return final.strip(), session_id


def _agent_log(prompt: str, stdout: str, stderr: str, returncode: int, duration_s: float) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"agent_{stamp}.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"ts={datetime.now(timezone.utc).isoformat()}\n")
        handle.write(f"returncode={returncode} duration_s={duration_s:.1f} prompt_chars={len(prompt)}\n")
        handle.write("--- stdout ---\n")
        handle.write(stdout or "")
        handle.write("\n--- stderr ---\n")
        handle.write(stderr or "")
        handle.write("\n")
    return path


def run_agent(
    prompt: str,
    config: TelegramConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> AgentResult:
    """Ejecuta OpenCode headless con el agente restringido `telegram`."""
    settings = get_settings()
    if settings.mode != "paper":
        return AgentResult(text="Bloqueado: el modo agente solo funciona en paper.", returncode=2)
    exe = opencode_executable()
    command = [exe, "run", "--agent", config.agent, "--auto", "--format", "json"]
    if config.session_id:
        command.extend(["--session", config.session_id])
    else:
        command.extend(["--title", "Telegram remoto"])
    command.append(prompt)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    started = time.monotonic()
    try:
        result = runner(
            command,
            cwd=config.working_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(60, _safe_int(config.agent_timeout_s, 1800)),
            env=env,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        text = f"Tiempo de espera agotado ({config.agent_timeout_s}s). Revisa logs/telegram."
        _agent_log(prompt, str(exc.stdout or ""), str(exc.stderr or ""), 124, duration)
        return AgentResult(text=text, session_id=config.session_id, returncode=124, duration_s=duration)
    except Exception as exc:
        duration = time.monotonic() - started
        text = f"No se pudo ejecutar OpenCode: {type(exc).__name__}."
        _agent_log(prompt, "", "", 1, duration)
        return AgentResult(text=text, session_id=config.session_id, returncode=1, duration_s=duration)
    duration = time.monotonic() - started
    text, session_id = parse_opencode_output(result.stdout or "")
    _agent_log(prompt, result.stdout or "", result.stderr or "", result.returncode, duration)
    if not text:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        text = tail[-1][:500] if tail else "El agente terminó sin texto."
    return AgentResult(
        text=text,
        session_id=session_id or config.session_id,
        returncode=int(result.returncode),
        duration_s=duration,
    )


def status_text(config: TelegramConfig) -> str:
    settings = get_settings()
    lines = [
        "TradingLab · estado",
        f"- Modo: {settings.mode}",
        f"- Telegram: {'activo' if config.enabled else 'pausado'} · modo={config.mode}",
    ]
    try:
        from .f13 import status as f13_status

        f13 = f13_status(DEFAULT_DB)
        if f13:
            lines.append(
                f"- F13: congelado · inicio={f13.get('start_date')} · "
                f"hash={str(f13.get('config_hash') or '')[:8]}"
            )
        else:
            lines.append("- F13: no iniciado")
    except Exception:
        lines.append("- F13: Sin datos")
    try:
        from .db import connect

        with connect(DEFAULT_DB) as con:
            total = con.execute("SELECT COUNT(*) AS n FROM decision_outcomes").fetchone()["n"]
            with20 = con.execute(
                "SELECT COUNT(*) AS n FROM decision_outcomes WHERE return_20d IS NOT NULL"
            ).fetchone()["n"]
            lessons = con.execute("SELECT COUNT(*) AS n FROM lessons").fetchone()["n"]
        lines.append(f"- Decisiones: {total} · con retorno 20d: {with20} · lecciones: {lessons}")
    except Exception:
        lines.append("- Decisiones: Sin datos")
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        first = (result.stdout or "").splitlines()[:1]
        dirty = len((result.stdout or "").splitlines()) - 1 if result.stdout else 0
        lines.append(f"- Repo: {first[0] if first else 'Sin datos'} · cambios={max(0, dirty)}")
    except Exception:
        lines.append("- Repo: Sin datos")
    if config.session_id:
        lines.append(f"- Sesión remota: {config.session_id[:18]}…")
    return "\n".join(lines)


def f13_text() -> str:
    try:
        from .f13 import load_criteria
        from .f13 import status as f13_status

        row = f13_status(DEFAULT_DB)
        criteria = load_criteria()
        if not row:
            return "F13 · no iniciado\n" + json.dumps(criteria, ensure_ascii=False, indent=2)
        return "\n".join(
            [
                "F13 · estado",
                f"- Bot: {row.get('bot')}",
                f"- Símbolo: {row.get('symbol')}",
                f"- Inicio: {row.get('start_date')}",
                f"- Congelado: {row.get('frozen_at')}",
                f"- Hash: {str(row.get('config_hash') or '')[:16]}…",
                f"- Ventana: {criteria.get('window_weeks')} semanas",
                f"- Trades esperados 8s: {criteria.get('expected_trades_8w_low')}–{criteria.get('expected_trades_8w_high')}",
                "- El bot sigue enabled:false; la activación es manual y en paper.",
            ]
        )
    except Exception as exc:
        return f"F13 · Sin datos ({type(exc).__name__})"


def decisions_text() -> str:
    try:
        from .decisions import report

        rows = report(DEFAULT_DB, min_sample=30)
        if not rows:
            return "Decisiones · Sin datos: no hay decisiones con retorno 20d."
        lines = ["Decisiones · retorno 20d"]
        for row in rows:
            if row.get("insufficient"):
                lines.append(f"- {row['rating']}: n={row['n']} (insuficiente)")
                continue
            mean = row.get("mean_20d")
            hit = row.get("hit_rate_20d")
            p_value = row.get("p_value")
            lines.append(
                f"- {row['rating']}: n={row['n']} · media={mean:.2%} · "
                f"acierto={hit:.1%} · p={p_value:.3f}"
                if mean is not None and hit is not None and p_value is not None
                else f"- {row['rating']}: n={row['n']}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"Decisiones · Sin datos ({type(exc).__name__})"


HELP_TEXT = """TradingLab · comandos
/status · estado del laboratorio
/f13 · estado de F13
/decisions · resultados con retorno 20d
/ping · comprobar conexión
/pause · pausar el puente (solo /status, /help y /resume)
/resume · reactivar
/mode commands|agent · cambiar modo
/new · empezar una sesión de agente nueva
/continue <texto> · enviar una instrucción al agente
/push · preparar push a origin/master (pide confirmación)
/backup · preparar backup + restore test (pide confirmación)
/pushbackup · preparar push y backup (pide confirmación)
/confirm <código> · confirmar la acción pendiente
/cancel · cancelar la acción pendiente
/help · esta ayuda

Modo agente: solo paper, sin live, sin .env, sin borrar, sin push y sin
activar F13. El agente trabaja en E:\\trading-lab y responde con el resumen.
Push/backup solo se ejecutan con /confirm y el código temporal.
"""


def _agent_prompt(user_text: str) -> str:
    return (
        "[Instrucción remota de Telegram]\n"
        f"{user_text.strip()}\n\n"
        "Trabaja en E:\\trading-lab. Sigue PLAN.md, README.md y AGENTS.md.\n"
        "No live, no .env, no borrar archivos, no push, no activar F13.\n"
        "Al terminar responde en español con el formato: Hecho / 1..N / Aviso / Siguiente."
    )


PENDING_TTL_S = 300
PUSH_BRANCH = "master"
PUSH_REMOTE = "origin"
ACTION_LABELS = {
    "push": "Push",
    "backup": "Backup",
    "pushbackup": "Push + backup",
}


def _creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _run(
    command: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = 120,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess:
    return runner(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_creationflags(),
    )


def _clean_output(text: str) -> str:
    return "".join(ch for ch in (text or "") if ch in "\n\r\t" or ord(ch) >= 32).strip()


def _out(result: subprocess.CompletedProcess) -> str:
    text = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return _clean_output(text)


def _tail(text: str, limit: int = 1500) -> str:
    clean = _clean_output(text)
    return clean[-limit:] if len(clean) > limit else clean


def _new_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def prepare_push(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    """Comprueba rama, fetch y commits pendientes antes de pedir confirmación."""
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], runner=runner, timeout=30)
    branch_name = _out(branch).strip()
    if branch.returncode != 0:
        return {"ok": False, "error": "No se pudo leer la rama: " + _tail(_out(branch), 300)}
    if branch_name != PUSH_BRANCH:
        return {
            "ok": False,
            "error": f"Rama actual {branch_name}; solo se hace push de {PUSH_BRANCH}.",
        }
    fetch = _run(["git", "fetch", "--quiet", PUSH_REMOTE], runner=runner, timeout=60)
    if fetch.returncode != 0:
        return {"ok": False, "error": "No se pudo consultar origin: " + _tail(_out(fetch), 300)}
    ahead = _run(
        ["git", "rev-list", "--count", f"{PUSH_REMOTE}/{PUSH_BRANCH}..HEAD"],
        runner=runner,
        timeout=30,
    )
    if ahead.returncode != 0:
        return {"ok": False, "error": "No se pudo contar commits: " + _tail(_out(ahead), 300)}
    try:
        pending = int(_out(ahead).strip() or "0")
    except ValueError:
        pending = 0
    if pending <= 0:
        return {"ok": False, "error": "Nada que subir: no hay commits por delante de origin/master."}
    dirty = _run(["git", "status", "--porcelain"], runner=runner, timeout=30)
    dirty_lines = [line for line in _out(dirty).splitlines() if line.strip()]
    diffstat = _run(
        ["git", "diff", "--stat", f"{PUSH_REMOTE}/{PUSH_BRANCH}..HEAD"],
        runner=runner,
        timeout=30,
    )
    names = _run(
        ["git", "diff", "--name-only", f"{PUSH_REMOTE}/{PUSH_BRANCH}..HEAD"],
        runner=runner,
        timeout=30,
    )
    return {
        "ok": True,
        "branch": branch_name,
        "ahead": pending,
        "dirty": len(dirty_lines),
        "diffstat": _tail(_out(diffstat), 2000) or "Sin datos",
        "files": _tail(_out(names), 1500) or "Sin datos",
        "summary": (
            f"rama={branch_name} · commits={pending} · "
            f"cambios_sin_commit={len(dirty_lines)}"
        ),
    }


def execute_push(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    result = _run(
        ["git", "push", PUSH_REMOTE, PUSH_BRANCH],
        runner=runner,
        timeout=300,
    )
    output = _tail(_out(result), 1500)
    if result.returncode == 0:
        return True, "Push completado.\n" + (output or "sin salida")
    return False, f"Push falló (código {result.returncode}).\n" + (output or "sin salida")


def execute_backup(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    script = ROOT / "scripts" / "backup.ps1"
    if not script.exists():
        return False, "No existe scripts/backup.ps1."
    result = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        runner=runner,
        timeout=900,
    )
    output = _tail(_out(result), 2000)
    if result.returncode == 0:
        return True, "Backup completado.\n" + (output or "sin salida")
    return False, f"Backup falló (código {result.returncode}).\n" + (output or "sin salida")


def _audit_action(
    action: str,
    *,
    user_id: str,
    ok: bool,
    detail: str = "",
) -> None:
    try:
        from .runtime import record_console_action

        record_console_action(
            DEFAULT_DB,
            action=f"telegram_{action}",
            params={"action": action},
            result="ok" if ok else "fail",
            ok=ok,
            actor=f"telegram:{user_id}",
            detail=_tail(detail, 1000),
        )
    except Exception:
        pass


def execute_action(
    action: str,
    *,
    user_id: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    if action == "push":
        ok, text = execute_push(runner=runner)
    elif action == "backup":
        ok, text = execute_backup(runner=runner)
    elif action == "pushbackup":
        ok, text = execute_push(runner=runner)
        if not ok:
            _audit_action(action, user_id=user_id, ok=False, detail=text)
            return ok, text
        ok_backup, text_backup = execute_backup(runner=runner)
        ok = ok_backup
        text = text + "\n\n" + text_backup
    else:
        return False, "Acción desconocida."
    _audit_action(action, user_id=user_id, ok=ok, detail=text)
    return ok, text


def begin_action(
    action: str,
    *,
    state: BridgeState,
    state_path: Path = STATE_PATH,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    if action in ("push", "pushbackup"):
        plan = prepare_push(runner=runner)
        if not plan["ok"]:
            return False, str(plan["error"])
        summary = (
            f"{plan['summary']}\n\n"
            f"diffstat:\n{plan['diffstat']}\n\n"
            f"archivos:\n{plan['files']}"
        )
    elif action == "backup":
        summary = "zip + restore test + integrity_check; puede tardar 1-2 minutos"
    else:
        return False, "Acción desconocida."
    code = _new_code()
    state.pending_action = action
    state.pending_code = code
    state.pending_expires_at = time.time() + PENDING_TTL_S
    state.save(state_path)
    label = ACTION_LABELS[action]
    return True, (
        f"{label} pendiente.\n{summary}\n\n"
        f"Para confirmar, envía:\n/confirm {code}\n\n"
        f"Caduca en {PENDING_TTL_S // 60} minutos."
    )


def confirm_action(
    code: str,
    *,
    state: BridgeState,
    state_path: Path = STATE_PATH,
    user_id: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    if not state.pending_action or not state.pending_code:
        return False, "No hay ninguna acción pendiente."
    if time.time() > state.pending_expires_at:
        state.clear_pending()
        state.save(state_path)
        return False, "El código ha caducado. Solicita la acción de nuevo."
    if not secrets.compare_digest(code.strip(), state.pending_code):
        return False, "Código incorrecto."
    action = state.pending_action
    state.clear_pending()
    state.save(state_path)
    return execute_action(action, user_id=user_id, runner=runner)


def handle_inbound(
    msg: Inbound,
    config: TelegramConfig,
    *,
    sender: Callable[[str, str], Any],
    agent_runner: Callable[[str, TelegramConfig], AgentResult] = run_agent,
    config_path: Path = CONFIG_PATH,
    state_path: Path = STATE_PATH,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    def reply(text: str) -> None:
        for chunk in chunk_text(text, config.max_chars):
            sender(msg.chat_id, chunk)

    config = TelegramConfig.load(config_path)
    state = BridgeState.load(state_path)
    if not is_authorized(msg, config):
        return
    if msg.forwarded:
        reply("No acepto mensajes reenviados. Escríbeme directamente.")
        return
    if msg.command in ("/start", "/help"):
        reply(HELP_TEXT)
        return
    if msg.command == "/ping":
        reply("pong · TradingLab conectado.")
        return
    if msg.command == "/status":
        reply(status_text(config))
        return
    if msg.command == "/f13":
        reply(f13_text())
        return
    if msg.command == "/decisions":
        reply(decisions_text())
        return
    if msg.command == "/pause":
        config.enabled = False
        config.save(config_path)
        state.clear_pending()
        state.save(state_path)
        reply("Puente pausado. Solo responderé a /status, /help, /resume y /ping.")
        return
    if msg.command == "/resume":
        config.enabled = True
        config.save(config_path)
        reply("Puente reactivado.")
        return
    if not config.enabled:
        reply("Puente pausado. Envía /resume para reactivarlo.")
        return
    if msg.command in ("/push", "/backup", "/pushbackup"):
        action = msg.command.lstrip("/")
        ok, text = begin_action(
            action,
            state=state,
            state_path=state_path,
            runner=command_runner,
        )
        reply(text)
        return
    if msg.command == "/confirm":
        if not msg.args.strip():
            reply("Uso: /confirm <código>")
            return
        if (
            state.pending_action
            and state.pending_code
            and time.time() <= state.pending_expires_at
            and secrets.compare_digest(msg.args.strip(), state.pending_code)
        ):
            label = ACTION_LABELS.get(state.pending_action, state.pending_action)
            reply(f"Confirmado. Ejecutando {label}…")
        ok, text = confirm_action(
            msg.args,
            state=state,
            state_path=state_path,
            user_id=msg.user_id,
            runner=command_runner,
        )
        reply(text)
        return
    if msg.command == "/cancel":
        state.clear_pending()
        state.save(state_path)
        reply("Acción pendiente cancelada.")
        return
    if msg.command == "/mode":
        mode = msg.args.strip().lower()
        if mode not in MODES:
            reply("Uso: /mode commands|agent")
            return
        config.mode = mode
        config.save(config_path)
        reply(
            "Modo agente activado. Instrucciones libres irán a OpenCode con permisos restringidos."
            if mode == "agent"
            else "Modo comandos activado. Las instrucciones libres no se ejecutarán."
        )
        return
    if msg.command == "/new":
        config.session_id = ""
        config.save(config_path)
        reply("Sesión remota reiniciada. El próximo mensaje creará una nueva.")
        return
    text = msg.args if msg.command == "/continue" else msg.text
    if msg.command == "/continue" and not text:
        reply("Uso: /continue <instrucción>")
        return
    if msg.command and msg.command != "/continue":
        reply("Comando desconocido. Envía /help.")
        return
    if config.mode != "agent":
        reply(
            "Modo comandos: no ejecuto instrucciones libres.\n"
            "Usa /help o cambia con /mode agent (solo paper y con permisos restringidos)."
        )
        return
    reply("Recibido. Trabajando… puede tardar varios minutos.")
    result = agent_runner(_agent_prompt(text), config)
    if result.session_id and result.session_id != config.session_id:
        config.session_id = result.session_id
        config.save(config_path)
    prefix = ""
    if result.returncode != 0:
        prefix = f"Aviso: el agente terminó con código {result.returncode}.\n\n"
    reply(prefix + (result.text or "El agente no devolvió texto."))


def _log_event(message: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"bridge_{datetime.now():%Y%m%d}.log"
        line = f"{datetime.now(timezone.utc).isoformat()} {message}\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass


def run_bridge(
    api: TelegramAPI,
    *,
    config_path: Path = CONFIG_PATH,
    state_path: Path = STATE_PATH,
    once: bool = False,
    dry_run: bool = False,
    sender: Callable[[str, str], Any] | None = None,
    agent_runner: Callable[[str, TelegramConfig], AgentResult] = run_agent,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Bucle de long polling. Serializa los mensajes de una en una."""
    send = sender or api.send_message
    if dry_run:
        def dry_send(chat_id: str, text: str) -> None:
            print(f"[dry-run] {chat_id}: {text}")

        send = dry_send
    backoff = 5
    while True:
        config = TelegramConfig.load(config_path)
        state = BridgeState.load(state_path)
        try:
            updates = api.get_updates(offset=state.last_update_id + 1, timeout=config.poll_timeout_s)
            backoff = 5
        except Exception as exc:
            _log_event(f"poll_error={type(exc).__name__}")
            if once:
                raise
            sleep(backoff)
            backoff = min(60, backoff * 2)
            continue
        if updates:
            state.last_update_id = max(int(item.get("update_id") or 0) for item in updates)
            state.save(state_path)
        for update in updates:
            msg = parse_inbound(update)
            if msg is None:
                continue
            if not is_authorized(msg, config):
                _log_event(f"ignored update_id={msg.update_id} chat={msg.chat_id}")
                continue
            _log_event(f"inbound update_id={msg.update_id} command={msg.command or 'text'}")
            try:
                handle_inbound(
                    msg,
                    config,
                    sender=send,
                    agent_runner=agent_runner,
                    config_path=config_path,
                    state_path=state_path,
                    command_runner=command_runner,
                )
            except Exception as exc:
                _log_event(f"handle_error update_id={msg.update_id} error={type(exc).__name__}")
                try:
                    send(msg.chat_id, f"Error interno: {type(exc).__name__}. Revisa logs/telegram.")
                except Exception:
                    pass
        if once:
            return
        if not updates:
            sleep(1)


def doctor_status() -> dict:
    try:
        load_secrets()
        token = os.getenv(TOKEN_KEY) or _keyring_get(TOKEN_KEY) or ""
        config = TelegramConfig.load()
        configured = bool(token and config.allowed_chat_id)
        if not configured:
            return {"configured": False, "detail": "sin configurar"}
        return {
            "configured": True,
            "detail": (
                f"modo={config.mode} · remoto={'on' if config.enabled else 'off'} · "
                f"chat={config.allowed_chat_id}"
            ),
        }
    except Exception:
        return {"configured": False, "detail": "sin configurar"}


def send_configured(text: str) -> None:
    token = get_token()
    chat_id = get_chat_id() or TelegramConfig.load().allowed_chat_id
    if not chat_id:
        raise TelegramError("Falta el chat ID autorizado. Ejecuta `lab telegram setup`.")
    api = TelegramAPI(token)
    send_text(api, chat_id, text)


__all__ = [
    "AgentResult",
    "BridgeState",
    "CONFIG_PATH",
    "EXAMPLE_PATH",
    "Inbound",
    "MAX_CHARS",
    "PENDING_TTL_S",
    "STATE_PATH",
    "TelegramAPI",
    "TelegramConfig",
    "TelegramError",
    "begin_action",
    "chunk_text",
    "confirm_action",
    "decisions_text",
    "discover_chats",
    "doctor_status",
    "execute_action",
    "execute_backup",
    "execute_push",
    "f13_text",
    "get_chat_id",
    "get_token",
    "handle_inbound",
    "is_authorized",
    "opencode_executable",
    "parse_inbound",
    "parse_opencode_output",
    "prepare_push",
    "run_agent",
    "run_bridge",
    "save_secrets",
    "save_setup",
    "send_configured",
    "send_text",
    "status_text",
    "wait_for_chat",
]
