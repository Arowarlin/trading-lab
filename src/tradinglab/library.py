"""Biblioteca de conocimiento original sobre herramientas y metodologías."""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import ROOT

LIBRARY_PATH = ROOT / "docs" / "biblioteca" / "library.yaml"
REQUIRED_FIELDS = (
    "id",
    "name",
    "category",
    "problem",
    "official_url",
    "license",
    "version",
    "dependencies",
    "data_costs",
    "advantages",
    "risks",
    "tests",
    "status",
    "reason",
)
STATUSES = {"adoptada", "evaluada", "descartada", "verificacion"}


class LibraryError(ValueError):
    pass


def load_library(path: str | Path = LIBRARY_PATH) -> dict:
    source = Path(path)
    if not source.exists():
        return {"reviewed_at": None, "entries": []}
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        raise LibraryError("library.yaml: entries debe ser una lista")
    seen: set[str] = set()
    for entry in entries:
        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            raise LibraryError(
                f"library.yaml: {entry.get('id', '?')} faltan {missing}"
            )
        if entry["status"] not in STATUSES:
            raise LibraryError(
                f"library.yaml: estado inválido en {entry['id']}: {entry['status']}"
            )
        if entry["id"] in seen:
            raise LibraryError(f"library.yaml: id duplicado {entry['id']}")
        seen.add(entry["id"])
    return {
        "reviewed_at": data.get("reviewed_at"),
        "entries": entries,
    }


def list_library(
    *,
    status: str | None = None,
    path: str | Path = LIBRARY_PATH,
) -> list[dict]:
    entries = load_library(path)["entries"]
    if status:
        entries = [entry for entry in entries if entry["status"] == status]
    return entries


def get_entry(entry_id: str, path: str | Path = LIBRARY_PATH) -> dict:
    key = entry_id.strip().lower()
    for entry in load_library(path)["entries"]:
        if entry["id"].lower() == key:
            return entry
    raise LibraryError(f"entrada no encontrada: {entry_id}")


def render_markdown(path: str | Path = LIBRARY_PATH) -> str:
    payload = load_library(path)
    lines = [
        "# Biblioteca de conocimiento",
        "",
        f"Revisado: {payload.get('reviewed_at') or 'Sin datos'}",
        "",
        "Fichas originales. No se copia texto de terceros; enlaces y licencias",
        "se revisan antes de adoptar una dependencia.",
        "",
        "| Herramienta | Categoría | Licencia | Versión | Estado |",
        "|---|---|---|---|---|",
    ]
    for entry in payload["entries"]:
        lines.append(
            f"| [{entry['name']}]({entry['official_url']}) | {entry['category']} | "
            f"{entry['license']} | {entry['version']} | {entry['status']} |"
        )
    lines += ["", "## Fichas", ""]
    for entry in payload["entries"]:
        lines += [
            f"### {entry['name']}",
            "",
            f"- **ID**: `{entry['id']}`",
            f"- **Categoría**: {entry['category']}",
            f"- **Problema**: {entry['problem']}",
            f"- **Enlace oficial**: {entry['official_url']}",
            f"- **Licencia**: {entry['license']}",
            f"- **Versión**: {entry['version']}",
            f"- **Dependencias**: {entry['dependencies']}",
            f"- **Datos/costes**: {entry['data_costs']}",
            f"- **Ventajas**: {entry['advantages']}",
            f"- **Riesgos**: {entry['risks']}",
            f"- **Pruebas en TradingLab**: {entry['tests']}",
            f"- **Estado**: {entry['status']}",
            f"- **Motivo**: {entry['reason']}",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "LIBRARY_PATH",
    "LibraryError",
    "STATUSES",
    "get_entry",
    "list_library",
    "load_library",
    "render_markdown",
]
