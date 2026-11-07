from __future__ import annotations

from tradinglab.config import _apply_keyring_secrets


def test_keyring_pisa_dotenv_pero_no_shell():
    env = {"ALPACA_API_KEY": "desde-dotenv"}

    def getter(key: str) -> str | None:
        return {"ALPACA_API_KEY": "desde-keyring"}.get(key)

    applied = _apply_keyring_secrets(env, getter)
    assert env["ALPACA_API_KEY"] == "desde-keyring"
    assert applied == {"ALPACA_API_KEY": "keyring"}


def test_shell_tiene_prioridad_sobre_keyring():
    env = {"ALPACA_API_KEY": "desde-shell"}

    def getter(key: str) -> str | None:
        return "desde-keyring"

    _apply_keyring_secrets(env, getter, shell_keys={"ALPACA_API_KEY"})
    assert env["ALPACA_API_KEY"] == "desde-shell"


def test_fallback_dotenv_si_no_hay_keyring():
    env = {"ALPACA_API_KEY": "desde-dotenv"}

    def getter(key: str) -> str | None:
        return None

    applied = _apply_keyring_secrets(env, getter)
    assert env["ALPACA_API_KEY"] == "desde-dotenv"
    assert applied == {}
