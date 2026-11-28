"""Instantáneas de páginas oficiales y detección de cambios (PFIE; FUT-P2). SIN red.

El operador guarda las páginas desde su navegador (varias firmas prohíben el acceso automatizado en sus
términos). Este módulo solo las archiva con hash (copia; nunca borra) y compara el texto normalizado
con la instantánea anterior de la misma página.
"""

from __future__ import annotations

import difflib
import hashlib
import html
import re
import shutil
from datetime import date
from pathlib import Path

from ..config import ROOT

SNAPSHOTS = ROOT / "data" / "prop_economics" / "snapshots"


def normalize(raw: str) -> str:
    """Texto visible normalizado: sin scripts, estilos ni etiquetas; espacios colapsados; una frase por línea."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"(?<=[.!?])\s+", "\n", text)


def archive(firm: str, page: str, saved_file: str | Path, *, day: date, root: Path = SNAPSHOTS) -> Path:
    """Copia la página guardada a ``<root>/<firma>/<página>/<fecha>_<sha256>.html`` y devuelve la ruta."""
    data = Path(saved_file).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    dest = root / firm / page / f"{day.isoformat()}_{sha[:16]}.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(saved_file, dest)
    return dest


def latest_change(firm: str, page: str, *, root: Path = SNAPSHOTS) -> dict:
    """Compara las dos últimas instantáneas de la página: ``changed`` y el diff del texto normalizado."""
    snaps = sorted((root / firm / page).glob("*.html"))
    if len(snaps) < 2:
        return {"firm": firm, "page": page, "changed": None, "snapshots": len(snaps), "diff": ""}
    old, new = (normalize(p.read_text(encoding="utf-8", errors="ignore")) for p in snaps[-2:])
    diff = "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), snaps[-2].name, snaps[-1].name,
                                          lineterm="", n=1))
    return {"firm": firm, "page": page, "changed": old != new, "snapshots": len(snaps), "diff": diff}
