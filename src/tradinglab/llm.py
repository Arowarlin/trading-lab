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
        return {
            "ok": True,
            "base_url": self.cfg.base_url,
            "models": models,
            "lmstudio": self._lmstudio_info(),
        }

    def _lmstudio_info(self) -> dict | None:
        """Contexto cargado, si el servidor es LM Studio (endpoint propio).

        Es opcional: cualquier OpenAI-compatible que no exponga /api/v0/models
        simplemente devuelve None. Sirve para detectar el fallo clásico de
        cargar el modelo con 8k de contexto y romper los prompts de agentes.
        """
        base = self.cfg.base_url.rstrip("/")
        origin = base[:-3] if base.endswith("/v1") else base
        try:
            with httpx.Client(timeout=5) as client:
                r = client.get(f"{origin}/api/v0/models")
                if r.status_code != 200:
                    return None
                data = r.json()
        except Exception:
            return None

        for m in data.get("data", []):
            if m.get("state") != "loaded":
                continue
            mid = str(m.get("id", ""))
            if mid == self.cfg.model or self.cfg.model in mid or mid.endswith(self.cfg.model):
                ctx = m.get("loaded_context_length") or m.get("max_context_length")
                return {"id": mid, "context": int(ctx) if ctx else None}
        return None

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
            # LM Studio rechaza "json_object" (solo admite json_schema o text).
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "strict": False,
                    "schema": {"type": "object", "additionalProperties": True},
                },
            }

        try:
            raw = self.chat(messages, purpose=purpose, response_format=response_format)
        except LLMError as exc:
            # Compatibilidad con backends que no soportan response_format:
            # se reintenta sin él y se confía en el prompt.
            if "response_format" not in str(exc):
                raise
            raw = self.chat(messages, purpose=purpose, response_format=None)

        try:
            return json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON inválido: {raw[:400]}") from exc


def _strip_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text.split("```", 2)
    if len(body) < 2:
        return text
    inner = body[1]
    if inner.lower().startswith("json"):
        inner = inner[4:]
    return inner.strip()
