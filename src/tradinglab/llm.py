from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .config import LLMSettings
from .db import connect, utcnow


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Cliente OpenAI-compatible para LM Studio / vLLM / llama.cpp."""

    def __init__(self, cfg: LLMSettings, db_path: str | Path | None = None) -> None:
        self.cfg = cfg
        self.db_path = Path(db_path) if db_path else None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"}

    def health(self) -> dict:
        url = f"{self.cfg.base_url.rstrip('/')}/models"
        with httpx.Client(timeout=10) as client:
            r = client.get(url, headers=self._headers())
            r.raise_for_status()
            data = r.json()
        models = [m.get("id") for m in data.get("data", [])]
        return {"ok": True, "base_url": self.cfg.base_url, "models": models}

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str = "chat",
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        url = f"{self.cfg.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "max_tokens": self.cfg.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format

        started = time.perf_counter()
        ok = False
        error: str | None = None
        prompt_tokens = completion_tokens = None

        try:
            with httpx.Client(timeout=self.cfg.timeout_s) as client:
                r = client.post(url, headers=self._headers(), json=payload)
                if r.status_code >= 400:
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:500]}")
                data = r.json()

            usage = data.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            choices = data.get("choices") or []
            if not choices:
                raise LLMError(f"Respuesta sin choices: {str(data)[:500]}")
            content = choices[0].get("message", {}).get("content")
            if not content:
                raise LLMError("Respuesta vacía del modelo")
            ok = True
            return content
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            if self.db_path:
                try:
                    with connect(self.db_path) as con:
                        con.execute(
                            "INSERT INTO llm_calls(ts, model, purpose, prompt_tokens, completion_tokens, "
                            "latency_ms, ok, error) VALUES(?,?,?,?,?,?,?,?)",
                            (
                                utcnow(),
                                self.cfg.model,
                                purpose,
                                prompt_tokens,
                                completion_tokens,
                                latency_ms,
                                1 if ok else 0,
                                error,
                            ),
                        )
                except Exception:
                    pass

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str = "json",
        schema: dict[str, Any] | None = None,
    ) -> dict:
        if schema:
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            }
        else:
            response_format = {"type": "json_object"}

        raw = self.chat(messages, purpose=purpose, response_format=response_format)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON inválido: {raw[:400]}") from exc
