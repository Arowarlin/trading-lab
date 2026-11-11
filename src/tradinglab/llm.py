from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .config import LLMSettings
from .db import connect, init_db, utcnow


class LLMError(RuntimeError):
    pass


class LLMSchemaError(LLMError):
    pass


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_schema(value: Any, schema: dict, path: str = "$") -> None:
    """Valida el subconjunto de JSON Schema usado por los agentes."""
    if not isinstance(schema, dict):
        return
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(value, item) for item in expected):
            raise LLMSchemaError(f"{path}: se esperaba {expected}, llegó {_type_name(value)}")
    elif expected and not _matches_type(value, str(expected)):
        raise LLMSchemaError(
            f"{path}: se esperaba {expected}, llegó {_type_name(value)}"
        )
    if "enum" in schema and value not in schema["enum"]:
        raise LLMSchemaError(f"{path}: valor fuera del enum")
    if isinstance(value, str):
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise LLMSchemaError(f"{path}: texto demasiado largo")
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise LLMSchemaError(f"{path}: texto demasiado corto")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise LLMSchemaError(f"{path}: valor por debajo del mínimo")
        if "maximum" in schema and value > schema["maximum"]:
            raise LLMSchemaError(f"{path}: valor por encima del máximo")
    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                raise LLMSchemaError(f"{path}: falta {key}")
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise LLMSchemaError(f"{path}: campos no permitidos: {sorted(extra)}")
        for key, child in properties.items():
            if key in value:
                validate_schema(value[key], child, f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise LLMSchemaError(f"{path}: demasiados pocos elementos")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise LLMSchemaError(f"{path}: demasiados elementos")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_schema(item, item_schema, f"{path}[{index}]")


class LLMClient:
    """Cliente OpenAI-compatible para LM Studio / vLLM / llama.cpp."""

    def __init__(self, cfg: LLMSettings, db_path: str | Path | None = None) -> None:
        self.cfg = cfg
        self.db_path = Path(db_path) if db_path else None
        self._last_call_id: int | None = None

    def _record_schema(self, ok: bool, error: str | None) -> None:
        if not self.db_path or self._last_call_id is None:
            return
        try:
            with connect(self.db_path) as con:
                con.execute(
                    "UPDATE llm_calls SET schema_ok=?, schema_error=? WHERE id=?",
                    (1 if ok else 0, error[:500] if error else None, self._last_call_id),
                )
        except Exception:
            pass

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
        self._last_call_id = None

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
            choice = choices[0]
            message = choice.get("message") or {}
            content = message.get("content")
            if not content:
                # Los modelos de razonamiento (qwen3, deepseek...) se gastan el
                # presupuesto de max_tokens en `reasoning_content` y devuelven
                # el content vacío. Sin este detalle el fallo parece del servidor.
                finish = choice.get("finish_reason")
                reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
                reasoning_tokens = (usage.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens"
                )
                budget = self.cfg.max_tokens if max_tokens is None else max_tokens
                if finish == "length":
                    raise LLMError(
                        f"El modelo agotó max_tokens={budget} razonando y no llegó a "
                        f"responder (tokens de razonamiento: {reasoning_tokens}). "
                        "Sube max_tokens."
                    )
                raise LLMError(
                    "Respuesta vacía del modelo"
                    + (f" (finish_reason={finish})" if finish else "")
                    + (f"; razonó: {reasoning[:200]!r}" if reasoning else "")
                )
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
                        cursor = con.execute(
                            "INSERT INTO llm_calls(ts, model, purpose, prompt_tokens, "
                            "completion_tokens, latency_ms, ok, error) "
                            "VALUES(?,?,?,?,?,?,?,?)",
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
                        self._last_call_id = int(cursor.lastrowid)
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
            value = json.loads(_strip_fences(raw))
            if schema:
                validate_schema(value, schema)
        except json.JSONDecodeError as exc:
            message = f"JSON inválido: {raw[:400]}"
            self._record_schema(False, message)
            raise LLMError(message) from exc
        except LLMSchemaError as exc:
            self._record_schema(False, str(exc))
            raise
        self._record_schema(True, None)
        return value


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


def schema_summary(db_path: str | Path) -> dict:
    """Conteo explícito de llamadas con esquema válido, fallido o sin validar."""
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN schema_ok=1 THEN 1 ELSE 0 END) AS ok, "
            "SUM(CASE WHEN schema_ok=0 THEN 1 ELSE 0 END) AS failed, "
            "SUM(CASE WHEN schema_ok IS NULL THEN 1 ELSE 0 END) AS unchecked "
            "FROM llm_calls"
        ).fetchone()
        recent = con.execute(
            "SELECT ts, model, purpose, schema_error FROM llm_calls "
            "WHERE schema_ok=0 ORDER BY id DESC LIMIT 10"
        ).fetchall()
        by_model = con.execute(
            "SELECT model, COUNT(*) AS n, "
            "SUM(CASE WHEN schema_ok=0 THEN 1 ELSE 0 END) AS failed "
            "FROM llm_calls WHERE schema_ok IS NOT NULL "
            "GROUP BY model ORDER BY n DESC"
        ).fetchall()
    return {
        "total_calls": int(row["total"] or 0),
        "checked": int((row["ok"] or 0) + (row["failed"] or 0)),
        "ok": int(row["ok"] or 0),
        "failed": int(row["failed"] or 0),
        "unchecked": int(row["unchecked"] or 0),
        "recent_failures": [dict(item) for item in recent],
        "by_model": [dict(item) for item in by_model],
    }


__all__ = [
    "LLMClient",
    "LLMError",
    "LLMSchemaError",
    "schema_summary",
    "validate_schema",
]
