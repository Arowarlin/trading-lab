"""Guardas de TradingLab para Claude Code (hooks del proyecto).

Convierte en controles duros las prohibiciones de ``AGENTS.md``. Es una red de
seguridad determinista, **no un sandbox**: lo que no reconoce lo deja pasar, y
si algo falla (JSON ilegible, intérprete ausente) no bloquea.

Modos (los llama ``.claude/hooks/run.sh``):

* ``bash``: PreToolUse de Bash. Deniega campañas y barridos que suman al DSR,
  ``record-informal``, push a master/main o forzado, reescribir historial,
  ``git add -A``/``.``/``-u``, ``git commit -a``, borrados, tareas
  programadas, tocar ``.env`` y ``ALLOW_LIVE=YES``.
* ``path``: PreToolUse de Edit/Write/NotebookEdit. Deniega ``.env*`` y los
  ficheros que exigen aprobación del operador en la misma sesión; pide
  confirmación (``ask``) en los ficheros de producción del manifiesto protegido.
* ``ruff``: PostToolUse de Edit/Write. ``ruff check`` solo del ``.py`` editado.
* ``stop``: Stop. Avisa si hay cambios en producción sin entrada en
  ``docs/CHANGELOG-produccion.md``. Nunca bloquea.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OPERATORS = {";", "&&", "||", "|", "&", "|&", ";;", "(", ")", "{", "}"}
WRAPPERS = {"sudo", "command", "exec", "nohup", "time", "env", "builtin"}
DELETE_PROGS = {"rm", "rmdir", "unlink", "shred", "del", "erase", "rd", "remove-item", "ri"}
SCHEDULER_PROGS = {
    "schtasks",
    "crontab",
    "register-scheduledtask",
    "unregister-scheduledtask",
    "new-scheduledtask",
    "set-scheduledtask",
}
LAB_RESEARCH = {"research", "research-intraday", "research-swing"}
DISCOVERY_BLOCKED = {"run", "approve", "confirm", "supersede"}
PROTECTED_BRANCHES = {"master", "main"}
BLOCKED_PATHS = {
    "config/propfund/protected_manifest.json": "el manifiesto protegido solo lo cambia el operador",
    "scripts/register_tasks_tz.ps1": "corre como administrador: exige aprobación del operador en esta sesión",
    "config/schedule.yaml": "lo usa una tarea con RunLevel Highest: exige aprobación del operador en esta sesión",
}
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
ENV_FILE = re.compile(r"^\.env(\..+)?$")

RULE = "AGENTS.md"


# ---------------------------------------------------------------- utilidades


def _decision(kind: str, reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason": reason,
        }
    }


def _strip_heredocs(command: str) -> str:
    """Quita los cuerpos de heredoc y convierte saltos de línea sin comillas en ';'."""
    out: list[str] = []
    pending: list[tuple[str, bool]] = []
    in_single = in_double = False
    for line in command.split("\n"):
        if pending:
            delim, dash = pending[0]
            if (line.lstrip("\t") if dash else line).strip() == delim:
                pending.pop(0)
            continue
        escaped = False
        for ch in line:
            if escaped:
                escaped = False
                continue
            if ch == "\\" and not in_single:
                escaped = True
            elif ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
        if not (in_single or in_double):
            for match in HEREDOC.finditer(line):
                pending.append((match.group(2), match.group(0).startswith("<<-")))
        out.append(line)
        out.append("\n" if (in_single or in_double) else " ; ")
    return "".join(out)


def _tokens(text: str, *, escapes: bool = True) -> list[str]:
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    if not escapes:  # PowerShell / rutas de Windows: la barra invertida es literal
        lexer.escape = ""
    try:
        return list(lexer)
    except ValueError:  # comillas sin cerrar: se analiza lo que se pueda
        return text.split()


def segments(command: str, *, escapes: bool = True) -> list[list[str]]:
    """Divide el comando en órdenes simples (respeta comillas y heredocs)."""
    result: list[list[str]] = []
    current: list[str] = []
    for token in _tokens(_strip_heredocs(command), escapes=escapes):
        if token in OPERATORS or token == "$":
            if current:
                result.append(current)
            current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def _program(segment: list[str]) -> tuple[str, list[str]]:
    words = list(segment)
    while words:
        head = words[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", head):
            words.pop(0)
            continue
        if head.lower() in WRAPPERS:
            words.pop(0)
            continue
        break
    if not words:
        return "", []
    name = re.split(r"[\\/]", words[0])[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name, words[1:]


def _current_branch(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------- bash


def _check_git(args: list[str], root: Path, branch_of=_current_branch) -> str | None:
    rest = list(args)
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag in {"-C", "-c"} and rest:
            rest.pop(0)
    if not rest:
        return None
    sub, opts = rest[0], rest[1:]
    if sub in {"rm", "clean"}:
        return f"git {sub} borra ficheros: prohibido ({RULE}: no borrar archivos)"
    if sub in {"rebase", "filter-branch", "filter-repo"}:
        return f"git {sub} reescribe el historial: prohibido sin autorización del operador ({RULE})"
    if sub == "reset" and "--hard" in opts:
        return f"git reset --hard descarta trabajo: prohibido ({RULE})"
    if sub == "commit":
        for opt in opts:
            if opt in {"-a", "--all"} or (
                opt.startswith("-") and not opt.startswith("--") and "a" in opt[1:] and len(opt) <= 4
            ):
                return f"git commit -a está prohibido: commits por ruta ({RULE})"
            if opt == "--amend":
                return f"git commit --amend reescribe el historial ({RULE})"
    if sub == "add":
        for opt in opts:
            if opt in {"-A", "--all", ".", ":/", "*", "-u", "--update"}:
                return f"git add {opt} está prohibido: git add <rutas> ({RULE})"
    if sub in {"branch", "tag"} and any(o in {"-d", "-D", "--delete"} for o in opts):
        return f"git {sub} -d borra referencias: prohibido sin autorización del operador ({RULE})"
    if sub == "push":
        for opt in opts:
            if opt in {"--force", "-f", "--force-with-lease", "--mirror", "--delete", "-d"} or opt.startswith(
                "--force-with-lease="
            ):
                return f"git push {opt} está prohibido sin autorización del operador ({RULE})"
        refs = [o for o in opts if not o.startswith("-")]
        targets = refs[1:]
        for ref in targets:
            if ref.startswith("+"):
                return f"git push con '+' fuerza el historial ({RULE})"
            dest = ref.split(":")[-1].removeprefix("refs/heads/")
            if dest in PROTECTED_BRANCHES:
                return f"git push a {dest} está prohibido: solo ramas de trabajo ({RULE})"
        if not targets and branch_of(root) in PROTECTED_BRANCHES:
            return f"git push desde {branch_of(root)} está prohibido: solo ramas de trabajo ({RULE})"
    return None


def _check_lab(args: list[str]) -> str | None:
    words = [a for a in args if not a.startswith("-")]
    if "record-informal" in args:
        return f"record-informal solo lo usa el operador ({RULE})"
    if not words:
        return None
    if words[0] in LAB_RESEARCH:
        return f"lab {words[0]} suma pruebas al DSR: exige aprobación del operador en esta sesión ({RULE})"
    if words[:2] == ["campaign", "run"]:
        return f"lab campaign run exige aprobación del operador y --approved-by-operator ({RULE})"
    if len(words) >= 2 and words[0] == "discovery" and words[1] in DISCOVERY_BLOCKED:
        return f"lab discovery {words[1]} exige aprobación del operador en esta sesión ({RULE})"
    return None


def check_segment(segment: list[str], root: Path = ROOT, branch_of=_current_branch) -> str | None:
    for token in segment:
        if token == "record-informal":
            return f"record-informal solo lo usa el operador ({RULE})"
        if token.upper().startswith("ALLOW_LIVE=") and token.split("=", 1)[1].upper() not in {"", "NO", "0", "FALSE"}:
            return f"Nunca live ni dinero real ({RULE})"
        name = re.split(r"[\\/]", token.strip("'\""))[-1]
        if ENV_FILE.match(name) and name != ".env.example":
            return f"No se toca {name}: los secretos viven en el Credential Manager ({RULE})"
    prog, args = _program(segment)
    if not prog:
        return None
    if prog in DELETE_PROGS:
        return f"{prog} borra ficheros: prohibido ({RULE}: no borrar archivos; archivar con git mv)"
    if prog == "find" and ("-delete" in args or any(a in DELETE_PROGS for a in args)):
        return f"find con borrado está prohibido ({RULE})"
    if prog in SCHEDULER_PROGS:
        return f"{prog}: registrar tareas programadas exige autorización del operador ({RULE})"
    if prog == "git":
        return _check_git(args, root, branch_of)
    if prog in {"lab", "tradinglab"}:
        return _check_lab(args)
    if prog.startswith("python") and "tradinglab.cli" in args:
        return _check_lab(args[args.index("tradinglab.cli") + 1 :])
    if prog in {"uv", "uvx"}:
        rest = list(args)
        if prog == "uv":
            if not rest or rest[0] != "run":
                return None
            rest = rest[1:]
        while rest and rest[0].startswith("-"):
            rest.pop(0)
        return check_segment(rest, root, branch_of) if rest else None
    return None


def check_bash(command: str, root: Path = ROOT, branch_of=_current_branch) -> str | None:
    """Bloquea si el comando, leído como bash o con la barra invertida literal, infringe una regla."""
    for escapes in (True, False):
        for segment in segments(command or "", escapes=escapes):
            reason = check_segment(segment, root, branch_of)
            if reason:
                return reason
    return None


# ---------------------------------------------------------------- rutas


def _relative(path: str, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()


def protected_files(root: Path = ROOT) -> dict[str, str]:
    try:
        manifest = json.loads((root / "config/propfund/protected_manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for group, body in (manifest.get("groups") or {}).items():
        for name in (body or {}).get("files") or {}:
            out[str(name).replace("\\", "/")] = group
    return out


def check_path(path: str, root: Path = ROOT) -> tuple[str, str] | None:
    if not path:
        return None
    rel = _relative(path, root)
    name = rel.rsplit("/", 1)[-1]
    if ENV_FILE.match(name) and name != ".env.example":
        return "deny", f"No se toca {name}: los secretos viven en el Credential Manager ({RULE})"
    if rel in BLOCKED_PATHS:
        return "deny", f"{rel}: {BLOCKED_PATHS[rel]} ({RULE})"
    group = protected_files(root).get(rel)
    if group:
        return "ask", (
            f"{rel} es producción (grupo {group}). Antes: baseline (lab propfund baseline --reason ...), "
            f"test de regresión, entrada en docs/CHANGELOG-produccion.md y tag tl2-<id>-pre ({RULE})."
        )
    return None


# ---------------------------------------------------------------- ruff y stop


def _ruff(root: Path) -> str | None:
    for candidate in (root / ".venv/bin/ruff", root / ".venv/Scripts/ruff.exe"):
        if candidate.exists():
            return str(candidate)
    return shutil.which("ruff")


def check_ruff(path: str, root: Path = ROOT) -> str | None:
    if not path or not path.endswith(".py"):
        return None
    rel = _relative(path, root)
    if rel.startswith("/") or not (root / rel).exists():
        return None
    ruff = _ruff(root)
    if not ruff:
        return None
    try:
        proc = subprocess.run(
            [ruff, "check", "--force-exclude", "--quiet", rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 1 and proc.stdout.strip():
        return f"ruff encontró problemas en {rel}:\n{proc.stdout.strip()[:3000]}"
    return None


def check_stop(root: Path = ROOT) -> str | None:
    try:
        changed = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    paths = {line[3:].strip().split(" -> ")[-1] for line in changed if len(line) > 3}
    production = sorted(p for p in paths if p in protected_files(root))
    if production and "docs/CHANGELOG-produccion.md" not in paths:
        return (
            "Aviso TradingLab: hay cambios en producción sin entrada en docs/CHANGELOG-produccion.md: "
            + ", ".join(production)
        )
    return None


# ---------------------------------------------------------------- entrada


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        payload = json.load(sys.stdin) if mode != "stop" else {}
    except ValueError:
        return 0
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ROOT)
    tool_input = payload.get("tool_input") or {}
    if mode == "bash":
        reason = check_bash(str(tool_input.get("command") or ""), root)
        if reason:
            print(json.dumps(_decision("deny", reason), ensure_ascii=False))
    elif mode == "path":
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        verdict = check_path(str(target), root)
        if verdict:
            print(json.dumps(_decision(*verdict), ensure_ascii=False))
    elif mode == "ruff":
        response = payload.get("tool_response") or {}
        target = tool_input.get("file_path") or response.get("filePath") or ""
        reason = check_ruff(str(target), root)
        if reason:
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    elif mode == "stop":
        message = check_stop(root)
        if message:
            print(json.dumps({"systemMessage": message}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
