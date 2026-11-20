from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tradinglab import telegram as tg


@pytest.fixture(autouse=True)
def _logs_en_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tg, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(tg, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(tg, "_audit_action", lambda *args, **kwargs: None)


def _config(path: Path, **overrides) -> tg.TelegramConfig:
    config = tg.TelegramConfig(
        enabled=True,
        mode=str(overrides.pop("mode", "commands")),
        allowed_chat_id="10",
        allowed_user_id="20",
        **overrides,
    )
    config.save(path)
    return config


def _message(text: str, *, chat: str = "10", user: str = "20", update_id: int = 1) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": int(user), "is_bot": False, "username": "owner"},
            "chat": {"id": int(chat), "type": "private"},
            "text": text,
        },
    }


def test_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    config = tg.TelegramConfig(
        enabled=True,
        mode="agent",
        allowed_chat_id="123",
        allowed_user_id="456",
        session_id="ses_1",
    )
    config.save(path)
    loaded = tg.TelegramConfig.load(path)
    assert loaded.enabled is True
    assert loaded.mode == "agent"
    assert loaded.allowed_chat_id == "123"
    assert loaded.allowed_user_id == "456"
    assert loaded.session_id == "ses_1"


def test_modo_invalido_cae_en_commands(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text("mode: shell\nallowed_chat_id: '1'\n", encoding="utf-8")
    assert tg.TelegramConfig.load(path).mode == "commands"


def test_numeros_invalidos_caen_en_default(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text(
        "poll_timeout_s: abc\nagent_timeout_s: x\nmax_chars: y\n",
        encoding="utf-8",
    )
    config = tg.TelegramConfig.load(path)
    assert config.poll_timeout_s == 30
    assert config.agent_timeout_s == 1800
    assert config.max_chars == tg.MAX_CHARS


def test_parse_inbound_y_autorizacion() -> None:
    config = tg.TelegramConfig(allowed_chat_id="10", allowed_user_id="20")
    msg = tg.parse_inbound(_message("/status@MiBot ahora"))
    assert msg is not None
    assert msg.command == "/status"
    assert msg.args == "ahora"
    assert tg.is_authorized(msg, config)

    other_chat = tg.parse_inbound(_message("hola", chat="11"))
    assert other_chat is not None and not tg.is_authorized(other_chat, config)

    other_user = tg.parse_inbound(_message("hola", user="21"))
    assert other_user is not None and not tg.is_authorized(other_user, config)

    forwarded_raw = _message("hola")
    forwarded_raw["message"]["forward_origin"] = {"type": "user"}
    forwarded = tg.parse_inbound(forwarded_raw)
    assert forwarded is not None and forwarded.forwarded
    # Sigue siendo el usuario autorizado; handle_inbound rechaza reenviados.
    assert tg.is_authorized(forwarded, config)

    # Sin user_id configurado vale cualquier emisor del chat autorizado.
    open_user = tg.TelegramConfig(allowed_chat_id="10", allowed_user_id="")
    assert tg.is_authorized(msg, open_user)


def test_chunk_text_no_pierde_contenido() -> None:
    text = ("palabra " * 2000).strip()
    chunks = tg.chunk_text(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert " ".join(chunks).split() == text.split()

    long_word = "x" * 2500
    chunks = tg.chunk_text(long_word, limit=1000)
    assert "".join(chunks) == long_word


def test_parse_opencode_output_ultimo_mensaje() -> None:
    lines = [
        {"type": "text", "sessionID": "ses_1", "part": {"messageID": "m1", "text": "hola"}},
        {"type": "tool", "sessionID": "ses_1", "part": {"messageID": "m1"}},
        {"type": "text", "sessionID": "ses_1", "part": {"messageID": "m1", "text": "mundo"}},
        {"type": "text", "sessionID": "ses_1", "part": {"messageID": "m2", "text": "final"}},
    ]
    stdout = "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
    text, session_id = tg.parse_opencode_output(stdout)
    assert text == "final"
    assert session_id == "ses_1"

    text, session_id = tg.parse_opencode_output("basura\n")
    assert text == ""
    assert session_id == ""


def test_save_setup_guarda_keyring_y_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, str] = {}
    monkeypatch.setattr(tg, "_keyring_set", lambda key, value: saved.__setitem__(key, value))
    config_path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    config = tg.save_setup(
        "token-secreto",
        "10",
        "20",
        mode="agent",
        last_update_id=99,
        path=config_path,
        state_path=state_path,
    )
    assert saved == {"TELEGRAM_BOT_TOKEN": "token-secreto", "TELEGRAM_CHAT_ID": "10"}
    assert config.enabled is False
    assert config.mode == "agent"
    assert config.allowed_chat_id == "10"
    assert config.allowed_user_id == "20"
    assert tg.BridgeState.load(state_path).last_update_id == 99


def test_handle_comandos_y_pausa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tg, "status_text", lambda config: "status-ok")
    path = tmp_path / "telegram.yaml"
    config = _config(path)
    replies: list[tuple[str, str]] = []
    msg = tg.parse_inbound(_message("/status"))
    assert msg is not None
    tg.handle_inbound(msg, config, sender=lambda chat, text: replies.append((chat, text)), config_path=path)
    assert replies[-1] == ("10", "status-ok")

    pause = tg.parse_inbound(_message("/pause"))
    assert pause is not None
    tg.handle_inbound(pause, config, sender=lambda chat, text: replies.append((chat, text)), config_path=path)
    assert tg.TelegramConfig.load(path).enabled is False

    free = tg.parse_inbound(_message("hola"))
    assert free is not None
    tg.handle_inbound(free, config, sender=lambda chat, text: replies.append((chat, text)), config_path=path)
    assert "pausado" in replies[-1][1].lower()

    resume = tg.parse_inbound(_message("/resume"))
    assert resume is not None
    tg.handle_inbound(resume, config, sender=lambda chat, text: replies.append((chat, text)), config_path=path)
    assert tg.TelegramConfig.load(path).enabled is True


def test_handle_modo_commands_no_ejecuta(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    config = _config(path, mode="commands")
    replies: list[str] = []
    called = False

    def runner(prompt: str, cfg: tg.TelegramConfig) -> tg.AgentResult:
        nonlocal called
        called = True
        return tg.AgentResult(text="no")

    msg = tg.parse_inbound(_message("haz algo"))
    assert msg is not None
    tg.handle_inbound(
        msg,
        config,
        sender=lambda chat, text: replies.append(text),
        agent_runner=runner,
        config_path=path,
    )
    assert called is False
    assert "Modo comandos" in replies[-1]


def test_handle_agente_guarda_sesion(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    config = _config(path, mode="agent")
    replies: list[str] = []
    seen: list[str] = []

    def runner(prompt: str, cfg: tg.TelegramConfig) -> tg.AgentResult:
        seen.append(prompt)
        return tg.AgentResult(text="Hecho\n1. ok", session_id="ses_nueva", returncode=0)

    msg = tg.parse_inbound(_message("/continue revisa F13"))
    assert msg is not None
    tg.handle_inbound(
        msg,
        config,
        sender=lambda chat, text: replies.append(text),
        agent_runner=runner,
        config_path=path,
    )
    assert any("Recibido" in reply for reply in replies)
    assert replies[-1] == "Hecho\n1. ok"
    assert seen and "revisa F13" in seen[0]
    assert tg.TelegramConfig.load(path).session_id == "ses_nueva"


def test_handle_reenviado_no_ejecuta(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    config = _config(path, mode="agent")
    replies: list[str] = []
    raw = _message("haz algo")
    raw["message"]["forward_origin"] = {"type": "user"}
    msg = tg.parse_inbound(raw)
    assert msg is not None
    tg.handle_inbound(
        msg,
        config,
        sender=lambda chat, text: replies.append(text),
        config_path=path,
    )
    assert "reenviados" in replies[-1].lower()


def test_run_agent_bloquea_live(monkeypatch: pytest.MonkeyPatch) -> None:
    class LiveSettings:
        mode = "live"

    monkeypatch.setattr(tg, "get_settings", lambda: LiveSettings())
    result = tg.run_agent("hola", tg.TelegramConfig())
    assert result.returncode == 2
    assert "Bloqueado" in result.text


def test_run_bridge_once_autorizado(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    updates = [_message("/ping", update_id=7)]
    sent: list[tuple[str, str]] = []

    class FakeAPI:
        def get_updates(self, offset=None, timeout=30):
            return updates

        def send_message(self, chat_id, text):
            sent.append((chat_id, text))

    tg.run_bridge(
        FakeAPI(),
        config_path=path,
        state_path=state_path,
        once=True,
        sender=lambda chat, text: sent.append((chat, text)),
    )
    assert sent == [("10", "pong · TradingLab conectado.")]
    assert tg.BridgeState.load(state_path).last_update_id == 7


def test_run_bridge_ignora_no_autorizado(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    updates = [_message("/ping", chat="99", user="98", update_id=3)]
    sent: list[str] = []

    class FakeAPI:
        def get_updates(self, offset=None, timeout=30):
            return updates

        def send_message(self, chat_id, text):
            sent.append(text)

    tg.run_bridge(
        FakeAPI(),
        config_path=path,
        state_path=state_path,
        once=True,
        sender=lambda chat, text: sent.append(text),
    )
    assert sent == []
    assert tg.BridgeState.load(state_path).last_update_id == 3


def test_discover_chats_sin_textos() -> None:
    class FakeAPI:
        def get_updates(self, offset=None, timeout=30):
            return [_message("/start", update_id=5)]

    chats, max_id = tg.discover_chats(FakeAPI())
    assert max_id == 5
    assert chats == [
        {"chat_id": "10", "user_id": "20", "type": "private", "username": "owner"}
    ]
    assert "text" not in chats[0]


def test_wait_for_chat_espera_al_siguiente_mensaje() -> None:
    class SeqAPI:
        def __init__(self) -> None:
            self.calls = 0

        def get_updates(self, offset=None, timeout=30):
            self.calls += 1
            return [] if self.calls == 1 else [_message("/start", update_id=8)]

    api = SeqAPI()
    chats, max_id = tg.wait_for_chat(api, 5, sleep=lambda _: None)
    assert api.calls == 2
    assert max_id == 8
    assert chats[0]["chat_id"] == "10"


def test_send_text_trocea_y_llama_al_sender() -> None:
    sent: list[str] = []
    count = tg.send_text(
        object(),
        "10",
        "x" * 9000,
        limit=1000,
        sender=lambda chat, text: sent.append(text),
    )
    assert count == len(sent) > 1
    assert "".join(sent) == "x" * 9000


def _cp(command, code=0, out="", err=""):
    return subprocess.CompletedProcess(command, code, out, err)


def _git_runner(commands, *, ahead="2", push_code=0, backup_code=0):
    def runner(command, **kwargs):
        commands.append(command)
        joined = " ".join(command)
        if "rev-parse --abbrev-ref HEAD" in joined:
            return _cp(command, 0, "master\n")
        if "fetch --quiet origin" in joined:
            return _cp(command, 0, "")
        if "rev-list --count origin/master..HEAD" in joined:
            return _cp(command, 0, ahead + "\n")
        if "diff --stat" in joined:
            return _cp(
                command,
                0,
                " src/a.py | 2 +-\n src/b.py | 1 +\n 2 files changed, 3 insertions(+), 1 deletion(-)\n",
            )
        if "diff --name-only" in joined:
            return _cp(command, 0, "src/a.py\nsrc/b.py\n")
        if "status --porcelain" in joined:
            return _cp(command, 0, "")
        if "push origin master" in joined:
            return _cp(
                command,
                push_code,
                "abc..def  master -> master\n" if push_code == 0 else "",
                "" if push_code == 0 else "rejected\n",
            )
        if "backup.ps1" in joined:
            return _cp(
                command,
                backup_code,
                "Backup: F:\\TradingLabBackups\\test.zip\nPASS: backup restaurado\n",
                "" if backup_code == 0 else "fallo\n",
            )
        return _cp(command, 0, "")
    return runner


def _handle(path: Path, state_path: Path, replies: list[str], runner, command: str) -> None:
    msg = tg.parse_inbound(_message(command))
    assert msg is not None
    tg.handle_inbound(
        msg,
        tg.TelegramConfig.load(path),
        sender=lambda chat, text: replies.append(text),
        config_path=path,
        state_path=state_path,
        command_runner=runner,
    )


def test_push_pide_codigo_y_confirma(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    replies: list[str] = []
    commands: list[list[str]] = []
    runner = _git_runner(commands)
    _handle(path, state_path, replies, runner, "/push")
    assert "Push pendiente" in replies[-1]
    assert "diffstat:" in replies[-1]
    assert "src/a.py" in replies[-1]
    assert "archivos:" in replies[-1]
    match = re.search(r"/confirm (\d{6})", replies[-1])
    assert match
    code = match.group(1)
    state = tg.BridgeState.load(state_path)
    assert state.pending_action == "push"
    assert state.pending_code == code
    assert not any(command[:2] == ["git", "push"] for command in commands)

    wrong = "000000" if code != "000000" else "111111"
    _handle(path, state_path, replies, runner, f"/confirm {wrong}")
    assert "incorrecto" in replies[-1].lower()
    assert not any(command[:2] == ["git", "push"] for command in commands)

    _handle(path, state_path, replies, runner, f"/confirm {code}")
    assert any(command[:2] == ["git", "push"] for command in commands)
    assert "Push completado" in replies[-1]
    assert tg.BridgeState.load(state_path).pending_action == ""


def test_push_sin_commits_no_pide_confirmacion(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    replies: list[str] = []
    commands: list[list[str]] = []
    runner = _git_runner(commands, ahead="0")
    _handle(path, state_path, replies, runner, "/push")
    assert "Nada que subir" in replies[-1]
    assert tg.BridgeState.load(state_path).pending_action == ""
    assert not any(command[:2] == ["git", "push"] for command in commands)


def test_backup_pide_codigo_y_confirma(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    replies: list[str] = []
    commands: list[list[str]] = []
    runner = _git_runner(commands)
    _handle(path, state_path, replies, runner, "/backup")
    match = re.search(r"/confirm (\d{6})", replies[-1])
    assert match
    _handle(path, state_path, replies, runner, f"/confirm {match.group(1)}")
    assert any("backup.ps1" in " ".join(command) for command in commands)
    assert "Backup completado" in replies[-1]


def test_pushbackup_ejecuta_ambos(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    replies: list[str] = []
    commands: list[list[str]] = []
    runner = _git_runner(commands)
    _handle(path, state_path, replies, runner, "/pushbackup")
    match = re.search(r"/confirm (\d{6})", replies[-1])
    assert match
    _handle(path, state_path, replies, runner, f"/confirm {match.group(1)}")
    assert any(command[:2] == ["git", "push"] for command in commands)
    assert any("backup.ps1" in " ".join(command) for command in commands)
    assert "Push completado" in replies[-1]
    assert "Backup completado" in replies[-1]


def test_confirm_caducado(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    tg.BridgeState(
        pending_action="push",
        pending_code="123456",
        pending_expires_at=0.0,
    ).save(state_path)
    replies: list[str] = []
    _handle(path, state_path, replies, _git_runner([]), "/confirm 123456")
    assert "caducado" in replies[-1].lower()
    assert tg.BridgeState.load(state_path).pending_action == ""


def test_pause_cancela_pendiente(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    state_path = tmp_path / "state.json"
    _config(path)
    tg.BridgeState(
        pending_action="push",
        pending_code="123456",
        pending_expires_at=9_999_999_999.0,
    ).save(state_path)
    replies: list[str] = []
    _handle(path, state_path, replies, _git_runner([]), "/pause")
    assert tg.BridgeState.load(state_path).pending_action == ""


def test_agente_telegram_deny_edicion() -> None:
    import fnmatch

    import yaml

    path = Path(__file__).resolve().parents[1] / ".opencode" / "agents" / "telegram.md"
    text = path.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    data = yaml.safe_load(frontmatter)
    rules = [rule for rule in data["permissions"] if rule.get("action") == "edit"]
    required = {
        "scripts/*",
        "AGENTS.md",
        "src/tradinglab/operator.py",
        "src/tradinglab/killswitch.py",
        "src/tradinglab/risk.py",
        "src/tradinglab/propfund/*",
        "src/tradinglab/prop/*",
    }
    denied = {rule["resource"] for rule in rules if rule.get("effect") == "deny"}
    assert denied == required

    def effect(resource: str) -> str | None:
        result = None
        for rule in rules:
            if fnmatch.fnmatch(resource, rule["resource"]):
                result = rule["effect"]
        return result

    for pattern in required:
        sample = pattern.replace("*", "x.py")
        assert effect(sample) == "deny", pattern
    assert effect("src/tradinglab/cli.py") == "allow"
    assert effect("README.md") == "allow"
    assert effect("tests/test_telegram.py") == "allow"


